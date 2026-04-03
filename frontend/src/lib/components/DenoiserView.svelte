<script lang="ts">
  import { onMount } from 'svelte';
  import {
    denoiserSpectrogramBefore, denoiserSpectrogramAfter,
    denoiserFreqAxis, denoiserTimeAxis, denoiserHeatmapRange,
    activeTab, viewXRange, waveformReset, audioLoaded
  } from '$lib/stores/appState';

  interface Props {
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
    onNoiseSelection?: (start: number, end: number) => void;
  }

  let { syncWaveform, onSeek, onNoiseSelection }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let containerEl: HTMLDivElement;
  let ctx: CanvasRenderingContext2D;
  let _rafPending = false;

  // View state
  let _xRange: [number, number] = [0, 10];
  let _fullXRange: [number, number] = [0, 10];
  let _pendingZoomReset = false;
  let _playheadTime = 0;
  let _mounted = false;

  // Display mode
  let _showAfter = $state(false);

  // Noise selection drag state
  let _isSelecting = false;
  let _selStartX = 0;
  let _selStartTime = 0;
  let _selEndTime = 0;
  let _hasSelection = $state(false);
  let _noiseSelStart = 0;
  let _noiseSelEnd = 0;

  // Waveform data (for when no spectrogram is available)
  let _waveformData: Float32Array | null = null;
  let _waveformSr = 0;
  let _audioDuration = 0;

  // Custom frequency scale — evenly spaced along Y axis
  const FREQ_SCALE = [100, 200, 300, 400, 500, 700, 1000, 1200, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 7000, 8000, 9000, 10000, 12000, 15000, 20000];

  const COLORS = {
    bg: '#000000',
    gridLine: '#333333',
    text: '#ccc',
    textDim: '#888',
    playhead: '#e94560',
    waveform: 'rgba(100, 180, 255, 0.5)',
    selection: 'rgba(45, 212, 191, 0.25)',
    selectionBorder: 'rgba(45, 212, 191, 0.8)',
  };

  const MARGIN = { l: 60, r: 20, t: 30, b: 40 };

  // --- Color map: designed so only absolute silence is black ---
  // t=0 → black, t>0 immediately shows color, ramps through blue → purple → red → yellow → white
  function dbToColor(db: number, minDb: number, maxDb: number, gamma: number = 1): [number, number, number] {
    let t = Math.max(0, Math.min(1, (db - minDb) / (maxDb - minDb)));
    if (gamma !== 1 && t > 0) t = Math.pow(t, gamma);
    if (t < 0.001) {
      // True silence → black
      return [0, 0, 0];
    } else if (t < 0.12) {
      // Faintest noise → dark blue (visible immediately)
      const s = (t - 0.001) / 0.119;
      return [0, 0, Math.floor(50 + s * 130)];
    } else if (t < 0.25) {
      // Blue → blue/purple
      const s = (t - 0.12) / 0.13;
      return [Math.floor(s * 100), 0, Math.floor(180 + s * 75)];
    } else if (t < 0.5) {
      // Purple → red/magenta
      const s = (t - 0.25) / 0.25;
      return [Math.floor(100 + s * 155), Math.floor(s * 30), Math.floor(255 - s * 150)];
    } else if (t < 0.7) {
      // Red → orange
      const s = (t - 0.5) / 0.2;
      return [255, Math.floor(30 + s * 140), Math.floor(105 - s * 105)];
    } else if (t < 0.85) {
      // Orange → yellow
      const s = (t - 0.7) / 0.15;
      return [255, Math.floor(170 + s * 85), Math.floor(s * 30)];
    } else {
      // Yellow → white
      const s = (t - 0.85) / 0.15;
      return [255, 255, Math.floor(30 + s * 225)];
    }
  }

  // Map frequency to Y position using custom scale (evenly spaced)
  function freqToY(freq: number, plotH: number): number {
    // Find where freq falls in our custom scale
    if (freq <= FREQ_SCALE[0]) return MARGIN.t + plotH;
    if (freq >= FREQ_SCALE[FREQ_SCALE.length - 1]) return MARGIN.t;

    for (let i = 1; i < FREQ_SCALE.length; i++) {
      if (freq <= FREQ_SCALE[i]) {
        const frac = (freq - FREQ_SCALE[i - 1]) / (FREQ_SCALE[i] - FREQ_SCALE[i - 1]);
        const bandFrac = ((i - 1) + frac) / (FREQ_SCALE.length - 1);
        return MARGIN.t + plotH * (1 - bandFrac);
      }
    }
    return MARGIN.t;
  }

  // Map Y position back to frequency
  function yToFreq(y: number, plotH: number): number {
    const bandFrac = 1 - (y - MARGIN.t) / plotH;
    const idx = bandFrac * (FREQ_SCALE.length - 1);
    const i = Math.floor(idx);
    const frac = idx - i;
    if (i < 0) return FREQ_SCALE[0];
    if (i >= FREQ_SCALE.length - 1) return FREQ_SCALE[FREQ_SCALE.length - 1];
    return FREQ_SCALE[i] + frac * (FREQ_SCALE[i + 1] - FREQ_SCALE[i]);
  }

  // --- Waveform loading ---
  async function loadWaveform() {
    try {
      const resp = await fetch(`/api/audio?t=${Date.now()}`);
      if (!resp.ok) return;
      const buf = await resp.arrayBuffer();
      const audioCtx = new AudioContext();
      const decoded = await audioCtx.decodeAudioData(buf);
      _waveformData = decoded.getChannelData(0);
      _waveformSr = decoded.sampleRate;
      _audioDuration = decoded.duration;
      audioCtx.close();
      if (_audioDuration > 0) {
        _fullXRange = [0, _audioDuration];
        if (_pendingZoomReset) {
          setXRange([..._fullXRange] as [number, number]);
          _pendingZoomReset = false;
        }
      }
      requestDraw();
    } catch {
      // ignore
    }
  }

  function setXRange(range: [number, number]) {
    _xRange = range;
    $viewXRange = range;
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

    const specData = _showAfter ? $denoiserSpectrogramAfter : $denoiserSpectrogramBefore;
    const specOther = _showAfter ? $denoiserSpectrogramBefore : $denoiserSpectrogramAfter;
    const freqAxis = $denoiserFreqAxis;
    const timeAxis = $denoiserTimeAxis;

    if (specData && freqAxis && timeAxis && specData.length > 0) {
      drawSpectrogram(ctx, specData, freqAxis, timeAxis, plotW, plotH, xMin, xMax, specOther);
    } else if (_waveformData) {
      drawWaveform(ctx, plotW, plotH, xMin, xMax, toX);
    } else {
      // Placeholder
      ctx.fillStyle = COLORS.textDim;
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Click Analyze to view spectrograms', W / 2, H / 2);
    }

    // Draw time grid
    drawTimeGrid(ctx, xMin, xMax, plotW, plotH, toX);

    // Draw frequency labels (always, on top of spectrogram)
    drawFreqLabels(ctx, plotW, plotH);

    // Draw noise selection
    if (_hasSelection || _isSelecting) {
      const selStart = _isSelecting ? Math.min(_selStartTime, _selEndTime) : _noiseSelStart;
      const selEnd = _isSelecting ? Math.max(_selStartTime, _selEndTime) : _noiseSelEnd;
      const x1 = toX(selStart);
      const x2 = toX(selEnd);
      ctx.fillStyle = COLORS.selection;
      ctx.fillRect(x1, MARGIN.t, x2 - x1, plotH);
      ctx.strokeStyle = COLORS.selectionBorder;
      ctx.lineWidth = 1;
      ctx.strokeRect(x1, MARGIN.t, x2 - x1, plotH);
      // Label
      ctx.fillStyle = COLORS.selectionBorder;
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Noise Profile', (x1 + x2) / 2, MARGIN.t - 6);
    }

    // Draw toggle label
    if (specData) {
      ctx.fillStyle = COLORS.text;
      ctx.font = '11px sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(_showAfter ? 'After' : 'Before', W - MARGIN.r - 4, MARGIN.t - 8);
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

  function drawSpectrogram(
    ctx: CanvasRenderingContext2D,
    specData: number[][],
    freqAxis: number[],
    timeAxis: number[],
    plotW: number, plotH: number,
    xMin: number, xMax: number,
    specOther?: number[][] | null
  ) {
    const numFreq = specData.length;
    const numTime = specData[0]?.length || 0;
    if (numFreq === 0 || numTime === 0) return;

    // Find peak dB across both spectrograms for consistent color scale
    let peakDb = -Infinity;
    for (const data of [specData, specOther]) {
      if (!data) continue;
      for (let fi = 0; fi < data.length; fi++) {
        for (let ti = 0; ti < (data[0]?.length || 0); ti++) {
          if (data[fi][ti] > peakDb) peakDb = data[fi][ti];
        }
      }
    }
    console.log(`[Spectrogram] view: ${_showAfter ? 'After' : 'Before'}, peakDb: ${peakDb.toFixed(1)}, numFreq: ${numFreq}, numTime: ${numTime}`);

    // 110 dB range from peak — wider than Audacity's 80 dB default because
    // our 4096 FFT spreads broadband noise across more bins (~12 dB lower per bin).
    const DB_RANGE = 110;
    const maxDb = peakDb;
    const minDb = peakDb - DB_RANGE;

    // Gain slider applies gamma boost to amplify low-level detail
    const gain = $denoiserHeatmapRange;
    const gamma = gain > 0 ? 1 / (1 + gain * 0.05) : 1;

    console.log('[Spectrogram] peakDb:', peakDb.toFixed(1), 'minDb:', minDb.toFixed(1), 'gamma:', gamma.toFixed(3));

    // Use ImageData for performance
    const imgData = ctx.createImageData(plotW, plotH);
    const pixels = imgData.data;

    // Precompute: for each pixel Y, find the closest freq bin
    const yToFreqBin = new Int32Array(plotH);
    for (let py = 0; py < plotH; py++) {
      const freq = yToFreq(MARGIN.t + py, plotH);
      let bestFi = 0;
      let bestDist = Math.abs(freqAxis[0] - freq);
      for (let i = 1; i < numFreq; i++) {
        const dist = Math.abs(freqAxis[i] - freq);
        if (dist < bestDist) { bestDist = dist; bestFi = i; }
      }
      yToFreqBin[py] = bestFi;
    }

    // Precompute: for each pixel X, find the closest time bin
    const xToTimeBin = new Int32Array(plotW);
    for (let px = 0; px < plotW; px++) {
      const t = xMin + (px / plotW) * (xMax - xMin);
      let bestTi = 0;
      let bestDist = Math.abs(timeAxis[0] - t);
      for (let i = 1; i < numTime; i++) {
        const dist = Math.abs(timeAxis[i] - t);
        if (dist < bestDist) { bestDist = dist; bestTi = i; }
      }
      xToTimeBin[px] = bestTi;
    }

    for (let py = 0; py < plotH; py++) {
      const fi = yToFreqBin[py];
      for (let px = 0; px < plotW; px++) {
        const ti = xToTimeBin[px];
        const db = specData[fi][ti];
        const [r, g, b] = dbToColor(db, minDb, maxDb, gamma);
        const idx = (py * plotW + px) * 4;
        pixels[idx] = r;
        pixels[idx + 1] = g;
        pixels[idx + 2] = b;
        pixels[idx + 3] = 255;
      }
    }

    ctx.putImageData(imgData, MARGIN.l, MARGIN.t);
  }

  function drawFreqLabels(ctx: CanvasRenderingContext2D, plotW: number, plotH: number) {
    ctx.fillStyle = COLORS.textDim;
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';

    // Show a subset of frequency labels to avoid clutter
    const labelFreqs = [100, 200, 500, 1000, 2000, 3000, 5000, 7000, 10000, 15000, 20000];
    for (const f of labelFreqs) {
      const y = freqToY(f, plotH);
      if (y < MARGIN.t || y > MARGIN.t + plotH) continue;
      const label = f >= 1000 ? `${f / 1000}k` : `${f}`;
      ctx.fillText(label, MARGIN.l - 4, y + 3);
      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(MARGIN.l, y);
      ctx.lineTo(MARGIN.l + plotW, y);
      ctx.stroke();
    }
  }

  function drawWaveform(ctx: CanvasRenderingContext2D, plotW: number, plotH: number, xMin: number, xMax: number, toX: (t: number) => number) {
    if (!_waveformData || !_waveformSr) return;
    const midY = MARGIN.t + plotH / 2;
    const halfH = plotH / 2 * 0.9;
    const startSample = Math.max(0, Math.floor(xMin * _waveformSr));
    const endSample = Math.min(_waveformData.length, Math.ceil(xMax * _waveformSr));

    ctx.fillStyle = COLORS.waveform;
    ctx.beginPath();

    for (let px = 0; px < plotW; px++) {
      const s0 = startSample + Math.floor(px * (endSample - startSample) / plotW);
      const s1 = Math.min(s0 + Math.max(1, Math.floor((endSample - startSample) / plotW)), _waveformData.length);
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
      ctx.fillText(t.toFixed(2) + 's', x, MARGIN.t + plotH + 14);
    }
  }

  // --- Pixel to time ---
  function pixelToTime(clientX: number): number {
    if (!canvasEl) return 0;
    const rect = canvasEl.getBoundingClientRect();
    const x = (clientX - rect.left) * (canvasEl.width / rect.width);
    const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
    const [xMin, xMax] = _xRange;
    return xMin + ((x - MARGIN.l) / plotW) * (xMax - xMin);
  }

  // --- Interaction: click-drag for noise selection, shift+drag for pan ---
  function onMouseDown(e: MouseEvent) {
    if (e.button !== 0) return;
    e.preventDefault();

    if (e.shiftKey) {
      // Shift+drag = pan
      _isPanning = true;
      _panStartX = e.clientX;
      _panStartRange = [..._xRange] as [number, number];
    } else {
      // Normal drag = noise profile selection
      _isSelecting = true;
      _selStartTime = pixelToTime(e.clientX);
      _selEndTime = _selStartTime;
      _hasSelection = false;
      requestDraw();
    }
  }

  function onMouseMove(e: MouseEvent) {
    if (_isSelecting) {
      _selEndTime = pixelToTime(e.clientX);
      requestDraw();
      return;
    }
    if (_isPanning && canvasEl) {
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
  }

  function onMouseUp(e: MouseEvent) {
    if (_isSelecting) {
      _isSelecting = false;
      const start = Math.max(0, Math.min(_selStartTime, _selEndTime));
      const end = Math.max(_selStartTime, _selEndTime);
      if (end - start > 0.01) {
        // Valid selection
        _hasSelection = true;
        _noiseSelStart = start;
        _noiseSelEnd = end;
        onNoiseSelection?.(start, end);
      } else {
        // Too small — treat as a click/seek
        _hasSelection = false;
        onSeek?.(Math.max(0, _selStartTime));
      }
      requestDraw();
      return;
    }
    _isPanning = false;
  }

  let _isPanning = false;
  let _panStartX = 0;
  let _panStartRange: [number, number] = [0, 10];

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    if (!canvasEl) return;
    const rect = canvasEl.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / rect.width;
    const span = _xRange[1] - _xRange[0];
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const newSpan = Math.max(0.1, Math.min(span * factor, _fullXRange[1]));
    const center = _xRange[0] + mx * span;
    const newMin = Math.max(0, center - mx * newSpan);
    const newMax = Math.min(_fullXRange[1], newMin + newSpan);
    setXRange([newMin, newMax]);
    requestDraw();
    syncWaveform(_xRange, _audioDuration);
  }

  function onDblClick() {
    _showAfter = !_showAfter;
    requestDraw();
  }

  // --- Resize ---
  function resizeCanvas() {
    if (!canvasEl || !containerEl) return;
    const rect = containerEl.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    canvasEl.width = rect.width;
    canvasEl.height = rect.height;
    ctx = canvasEl.getContext('2d')!;
    requestDraw();
  }

  // --- Public methods ---
  export function setPlayheadTime(t: number) {
    _playheadTime = t;
    if (_mounted && canvasEl && canvasEl.width > 0) {
      requestDraw();
    }
  }

  export function clearSelection() {
    _hasSelection = false;
    _noiseSelStart = 0;
    _noiseSelEnd = 0;
    requestDraw();
  }

  export function setSelection(start: number, end: number) {
    _hasSelection = true;
    _noiseSelStart = start;
    _noiseSelEnd = end;
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
    void $denoiserSpectrogramBefore;
    void $denoiserSpectrogramAfter;
    void $denoiserFreqAxis;
    void $denoiserTimeAxis;
    void $denoiserHeatmapRange;
    requestDraw();
  });

  $effect(() => {
    void $viewXRange;
    if ($activeTab === 'denoise') {
      _xRange = $viewXRange;
      requestDraw();
    }
  });

  $effect(() => {
    void $waveformReset;
    _pendingZoomReset = true;
    loadWaveform();
  });

  $effect(() => {
    if ($audioLoaded && $activeTab === 'denoise') {
      loadWaveform();
    }
  });
</script>

<div class="denoiser-view" bind:this={containerEl}>
  <canvas
    bind:this={canvasEl}
    ondblclick={onDblClick}
    onmousedown={onMouseDown}
    onmousemove={onMouseMove}
    onmouseup={onMouseUp}
    onmouseleave={onMouseUp}
    onwheel={onWheel}
    title="Drag to select noise profile region. Shift+drag to pan. Double-click to toggle Before/After. Scroll to zoom."
  ></canvas>
</div>

<style>
  .denoiser-view {
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
