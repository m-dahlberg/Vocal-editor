<script lang="ts">
  import { onMount } from 'svelte';
  import {
    declickerDetections, declickerBandCenters, selectedClickIdx,
    activeTab, viewXRange, waveformReset, audioLoaded,
    declickerCheckedIndices, declickerVisibleIndices,
  } from '$lib/stores/appState';
  import type { DeclickerDetection } from '$lib/utils/types';

  interface Props {
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
    onClicksChecked?: (clickIndices: number[], allChecked: boolean) => void;
  }

  let { syncWaveform, onSeek, onClicksChecked }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let containerEl: HTMLDivElement;
  let ctx: CanvasRenderingContext2D;
  let _rafPending = false;

  // View state
  let _xRange: [number, number] = [0, 10];
  let _fullXRange: [number, number] = [0, 10];
  let _pendingZoomReset = false;

  function setXRange(range: [number, number]) {
    _xRange = range;
    $viewXRange = range;
  }
  let _playheadTime = 0;
  let _mounted = false;

  // Audio waveform data (for drawing)
  let _waveformData: Float32Array | null = null;
  let _waveformSr = 0;
  let _audioDuration = 0;

  const COLORS = {
    bg: '#16213e',
    gridLine: '#2a2a4a',
    text: '#ccc',
    textDim: '#888',
    playhead: '#e94560',
    waveform: 'rgba(100, 180, 255, 0.5)',
  };

  const MARGIN = { l: 60, r: 20, t: 30, b: 40 };

  // --- Waveform loading ---
  export async function loadWaveform() {
    try {
      const resp = await fetch(`/api/audio?t=${Date.now()}`);
      if (!resp.ok) {
        // Try original upload
        const resp2 = await fetch(`/api/declicker/audio?t=${Date.now()}`);
        if (!resp2.ok) return;
        const buf = await resp2.arrayBuffer();
        const audioCtx = new AudioContext();
        const decoded = await audioCtx.decodeAudioData(buf);
        _waveformData = decoded.getChannelData(0);
        _waveformSr = decoded.sampleRate;
        _audioDuration = decoded.duration;
        audioCtx.close();
      } else {
        const buf = await resp.arrayBuffer();
        const audioCtx = new AudioContext();
        const decoded = await audioCtx.decodeAudioData(buf);
        _waveformData = decoded.getChannelData(0);
        _waveformSr = decoded.sampleRate;
        _audioDuration = decoded.duration;
        audioCtx.close();
      }
      if (_audioDuration > 0) {
        _fullXRange = [0, _audioDuration];
        if (_pendingZoomReset) {
          setXRange([..._fullXRange] as [number, number]);
          _pendingZoomReset = false;
        }
        // Sync waveform now that we have duration
        syncWaveform(_xRange, _audioDuration);
      }
      requestDraw();
    } catch {
      // ignore
    }
  }

  // --- Drawing ---
  function requestDraw() {
    if (_rafPending || !_mounted) return;
    _rafPending = true;
    requestAnimationFrame(() => {
      _rafPending = false;
      draw();
    });
  }

  function draw() {
    if (!ctx || !canvasEl) return;
    const W = canvasEl.width;
    const H = canvasEl.height;
    const plotW = W - MARGIN.l - MARGIN.r;
    const plotH = H - MARGIN.t - MARGIN.b;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    if (plotW <= 0 || plotH <= 0) return;

    const [xMin, xMax] = _xRange;
    const xSpan = xMax - xMin;
    if (xSpan <= 0) return;

    const toX = (t: number) => MARGIN.l + ((t - xMin) / xSpan) * plotW;

    // Draw time grid
    drawTimeGrid(ctx, xMin, xMax, plotW, plotH, toX);

    // Draw waveform
    if (_waveformData) {
      drawWaveform(ctx, plotW, plotH, xMin, xMax, toX);
    }

    // Draw click detections
    drawClickRegions(ctx, plotH, toX);

    // Draw alt-drag selection region
    if (_isAltDragging) {
      const tDrag1 = _xToTime(Math.min(_altDragStartX, _altDragCurrentX));
      const tDrag2 = _xToTime(Math.max(_altDragStartX, _altDragCurrentX));
      const dragX1 = Math.max(MARGIN.l, toX(tDrag1));
      const dragX2 = Math.min(MARGIN.l + plotW, toX(tDrag2));
      if (dragX2 > dragX1) {
        ctx.fillStyle = 'rgba(255, 200, 50, 0.18)';
        ctx.fillRect(dragX1, MARGIN.t, dragX2 - dragX1, plotH);
        ctx.strokeStyle = 'rgba(255, 200, 50, 0.7)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(dragX1, MARGIN.t);
        ctx.lineTo(dragX1, MARGIN.t + plotH);
        ctx.moveTo(dragX2, MARGIN.t);
        ctx.lineTo(dragX2, MARGIN.t + plotH);
        ctx.stroke();
      }
    }

    // Draw playhead
    const px = toX(_playheadTime);
    if (px >= MARGIN.l && px <= MARGIN.l + plotW) {
      ctx.strokeStyle = COLORS.playhead;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px, MARGIN.t);
      ctx.lineTo(px, MARGIN.t + plotH);
      ctx.stroke();
    }
  }

  function drawTimeGrid(ctx: CanvasRenderingContext2D, xMin: number, xMax: number, plotW: number, plotH: number, toX: (t: number) => number) {
    const span = xMax - xMin;
    const rawStep = span / 8;
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    const steps = [1, 2, 5, 10];
    const step = mag * (steps.find(s => s * mag >= rawStep) || 10);

    ctx.fillStyle = COLORS.textDim;
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';

    const start = Math.ceil(xMin / step) * step;
    for (let t = start; t <= xMax; t += step) {
      const x = toX(t);
      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(x, MARGIN.t);
      ctx.lineTo(x, MARGIN.t + plotH);
      ctx.stroke();
      ctx.fillText(t.toFixed(2) + 's', x, MARGIN.t + plotH + 14);
    }
  }

  function drawWaveform(ctx: CanvasRenderingContext2D, plotW: number, plotH: number, xMin: number, xMax: number, toX: (t: number) => number) {
    if (!_waveformData || !_waveformSr) return;
    const midY = MARGIN.t + plotH / 2;
    const halfH = plotH / 2 * 0.9;
    const startSample = Math.max(0, Math.floor(xMin * _waveformSr));
    const endSample = Math.min(_waveformData.length, Math.ceil(xMax * _waveformSr));
    const samplesPerPixel = Math.max(1, Math.floor((endSample - startSample) / plotW));

    ctx.fillStyle = COLORS.waveform;
    ctx.beginPath();

    for (let px = 0; px < plotW; px++) {
      const s0 = startSample + Math.floor(px * (endSample - startSample) / plotW);
      const s1 = Math.min(s0 + samplesPerPixel, _waveformData.length);
      let mn = 0, mx = 0;
      for (let s = s0; s < s1; s++) {
        const v = _waveformData[s];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      const x = MARGIN.l + px;
      const y1 = midY - mx * halfH;
      const y2 = midY - mn * halfH;
      ctx.rect(x, y1, 1, Math.max(1, y2 - y1));
    }
    ctx.fill();
  }

  /**
   * Map dB ratio to a blue→purple→red color.
   * 0 dB = blue (hue 240), 35 dB+ = red (hue 0).
   */
  function clickColor(ratioDB: number, alpha: number): string {
    const t = Math.min(1, Math.max(0, ratioDB / 35));
    const hue = 240 * (1 - t);
    return `hsla(${hue}, 90%, 50%, ${alpha})`;
  }

  function drawClickRegions(ctx: CanvasRenderingContext2D, plotH: number, toX: (t: number) => number) {
    const clicks = $declickerDetections;
    const visible = new Set($declickerVisibleIndices);
    const checked = $declickerCheckedIndices;

    for (let i = 0; i < clicks.length; i++) {
      if (!visible.has(i)) continue;

      const click = clicks[i];
      const x1 = toX(click.start_time);
      const x2 = toX(click.end_time);
      const w = Math.max(2, x2 - x1);

      const isSelected = i === $selectedClickIdx;
      const isChecked = checked.has(i);

      if (isChecked) {
        // Checked (selected for removal) → grey
        ctx.fillStyle = `rgba(128, 128, 128, ${isSelected ? 0.7 : 0.45})`;
        ctx.fillRect(x1, MARGIN.t, w, plotH);
        ctx.fillStyle = isSelected ? 'rgba(255,255,255,0.9)' : 'rgba(180, 180, 180, 0.8)';
        ctx.fillRect(x1, MARGIN.t, w, 3);
      } else {
        // Unchecked → colored
        const alpha = isSelected ? 0.95 : 0.7;
        ctx.fillStyle = clickColor(click.max_ratio_db, alpha);
        ctx.fillRect(x1, MARGIN.t, w, plotH);
        if (w >= 2) {
          ctx.fillStyle = isSelected ? '#fff' : clickColor(click.max_ratio_db, 0.9);
          ctx.fillRect(x1, MARGIN.t, w, 3);
        }
      }
    }
  }

  // --- Interaction ---
  function onCanvasClick(e: MouseEvent) {
    if (!canvasEl) return;
    const rect = canvasEl.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (canvasEl.width / rect.width);
    const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
    const [xMin, xMax] = _xRange;
    const t = xMin + ((x - MARGIN.l) / plotW) * (xMax - xMin);

    // Check if clicking on a detection
    const clicks = $declickerDetections;
    let found = -1;
    for (let i = 0; i < clicks.length; i++) {
      if (t >= clicks[i].start_time && t <= clicks[i].end_time) {
        found = i;
        break;
      }
    }

    if (e.altKey) return; // already handled in onMouseDown

    if (found >= 0) {
      $selectedClickIdx = found;
    } else {
      $selectedClickIdx = null;
      onSeek?.(Math.max(0, t));
    }
    requestDraw();
  }

  // Pan/zoom
  let _isPanning = false;
  let _panStartX = 0;
  let _panStartRange: [number, number] = [0, 10];

  // Alt+drag state
  let _isAltDragging = false;
  let _altDragStartX = 0;
  let _altDragCurrentX = 0;
  const ALT_DRAG_THRESHOLD = 5; // px before treating as drag vs click

  function _xToTime(clientX: number): number {
    const rect = canvasEl.getBoundingClientRect();
    const x = clientX - rect.left;
    const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
    const [xMin, xMax] = _xRange;
    return xMin + ((x - MARGIN.l) / plotW) * (xMax - xMin);
  }

  function onMouseDown(e: MouseEvent) {
    if (e.button !== 0) return;

    if (e.altKey) {
      e.preventDefault();
      _isAltDragging = true;
      _altDragStartX = e.clientX;
      _altDragCurrentX = e.clientX;
      return;
    }

    _isPanning = true;
    _panStartX = e.clientX;
    _panStartRange = [..._xRange] as [number, number];
    e.preventDefault();
  }

  function onMouseMove(e: MouseEvent) {
    if (_isAltDragging) {
      _altDragCurrentX = e.clientX;
      requestDraw();
      return;
    }
    if (!_isPanning || !canvasEl) return;
    const rect = canvasEl.getBoundingClientRect();
    const dx = e.clientX - _panStartX;
    const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
    const scale = rect.width > 0 ? (canvasEl.width / rect.width) : 1;
    const span = _panStartRange[1] - _panStartRange[0];
    const dt = -(dx * scale / plotW) * span;
    const newMin = Math.max(0, _panStartRange[0] + dt);
    const newMax = newMin + span;
    setXRange([newMin, Math.min(newMax, _fullXRange[1])]);
    requestDraw();
    syncWaveform(_xRange, _audioDuration);
  }

  function onMouseUp(e?: MouseEvent) {
    if (_isAltDragging) {
      _isAltDragging = false;
      const dragDist = Math.abs(_altDragCurrentX - _altDragStartX);

      if (dragDist < ALT_DRAG_THRESHOLD) {
        // Treat as click: toggle single click under cursor
        const t = _xToTime(_altDragStartX);
        const clicks = $declickerDetections;
        for (let i = 0; i < clicks.length; i++) {
          if (t >= clicks[i].start_time && t <= clicks[i].end_time) {
            const s = new Set($declickerCheckedIndices);
            const wasChecked = s.has(i);
            if (wasChecked) s.delete(i); else s.add(i);
            $declickerCheckedIndices = s;
            onClicksChecked?.([i], !wasChecked);
            requestDraw();
            return;
          }
        }
      } else {
        // Alt+drag: find all visible clicks overlapping the drag time range
        const tStart = Math.min(_xToTime(_altDragStartX), _xToTime(_altDragCurrentX));
        const tEnd = Math.max(_xToTime(_altDragStartX), _xToTime(_altDragCurrentX));
        const clicks = $declickerDetections;
        const visible = new Set($declickerVisibleIndices);
        const s = new Set($declickerCheckedIndices);
        const newlyChecked: number[] = [];
        for (let i = 0; i < clicks.length; i++) {
          if (!visible.has(i)) continue;
          // Overlaps if click starts before drag end and ends after drag start
          if (clicks[i].start_time <= tEnd && clicks[i].end_time >= tStart) {
            if (!s.has(i)) {
              s.add(i);
              newlyChecked.push(i);
            }
          }
        }
        $declickerCheckedIndices = s;
        if (newlyChecked.length > 0) {
          onClicksChecked?.(newlyChecked, true);
        }
        requestDraw();
      }
      return;
    }
    _isPanning = false;
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    if (!canvasEl) return;
    const rect = canvasEl.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / rect.width;
    const span = _xRange[1] - _xRange[0];
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const maxSpan = _fullXRange[1] - _fullXRange[0];
    const newSpan = Math.max(0.1, Math.min(span * factor, maxSpan));
    const center = _xRange[0] + mx * span;
    let newMin = center - mx * newSpan;
    let newMax = newMin + newSpan;
    // Clamp both ends, adjusting the other end to preserve the span
    if (newMin < _fullXRange[0]) {
      newMin = _fullXRange[0];
      newMax = Math.min(_fullXRange[1], newMin + newSpan);
    }
    if (newMax > _fullXRange[1]) {
      newMax = _fullXRange[1];
      newMin = Math.max(_fullXRange[0], newMax - newSpan);
    }
    setXRange([newMin, newMax]);
    requestDraw();
    syncWaveform(_xRange, _audioDuration);
  }

  // --- Resize ---
  function resizeCanvas() {
    if (!canvasEl || !containerEl) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = containerEl.getBoundingClientRect();
    canvasEl.width = rect.width * dpr;
    canvasEl.height = rect.height * dpr;
    canvasEl.style.width = rect.width + 'px';
    canvasEl.style.height = rect.height + 'px';
    ctx = canvasEl.getContext('2d')!;
    ctx.scale(dpr, dpr);
    // Revert scale for drawing (we'll use CSS pixels)
    canvasEl.width = rect.width;
    canvasEl.height = rect.height;
    ctx = canvasEl.getContext('2d')!;
    requestDraw();
  }

  // --- Public methods ---
  export function setPlayheadTime(t: number) {
    _playheadTime = t;
    requestDraw();
  }

  // --- Lifecycle ---
  onMount(() => {
    _mounted = true;
    resizeCanvas();
    const ro = new ResizeObserver(() => resizeCanvas());
    ro.observe(containerEl);

    return () => {
      _mounted = false;
      ro.disconnect();
    };
  });

  // Watch for store changes
  $effect(() => {
    // Re-read reactively
    void $declickerDetections;
    void $selectedClickIdx;
    void $declickerBandCenters;
    void $declickerVisibleIndices;
    void $declickerCheckedIndices;
    requestDraw();
  });

  $effect(() => {
    void $viewXRange;
    if ($activeTab === 'declicker') {
      _xRange = $viewXRange;
      requestDraw();
      syncWaveform(_xRange, _audioDuration);
    }
  });

  $effect(() => {
    void $waveformReset;
    _pendingZoomReset = true;
    loadWaveform();
  });

  $effect(() => {
    if ($audioLoaded && $activeTab === 'declicker') {
      loadWaveform();
    }
  });
</script>

<div class="declicker-view" bind:this={containerEl}>
  <canvas
    bind:this={canvasEl}
    onclick={onCanvasClick}
    onmousedown={onMouseDown}
    onmousemove={onMouseMove}
    onmouseup={onMouseUp}
    onmouseleave={onMouseUp}
    onwheel={onWheel}
  ></canvas>
</div>

<style>
  .declicker-view {
    flex: 1;
    min-height: 200px;
    position: relative;
    overflow: hidden;
  }
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    cursor: crosshair;
  }
</style>
