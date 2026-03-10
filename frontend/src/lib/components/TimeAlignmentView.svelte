<script lang="ts">
  import { onMount } from 'svelte';
  import {
    clusters, selectedIdx, selectedIndices, timeEdits, dirtyTimeEdits
  } from '$lib/stores/appState';
  import { params } from '$lib/stores/params';
  import ProcessingOverlay from './ProcessingOverlay.svelte';
  import type { Cluster, TimeEdit } from '$lib/utils/types';

  interface Props {
    onClusterSelect: (idx: number, cluster: Cluster) => void;
    onDrawBox: (start: number, end: number) => void;
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
  }

  let { onClusterSelect, onDrawBox, syncWaveform, onSeek }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let containerEl: HTMLDivElement;
  let ctx: CanvasRenderingContext2D;
  let _rafPending = false;

  // View state
  let _xRange: [number, number] = [0, 10];
  let _fullXRange: [number, number] = [0, 10];
  let _playheadTime = 0;
  let _mounted = false;
  let _drawPreview: { startTime: number; endTime: number } | null = null;

  const COLORS = {
    bg: '#16213e',
    gridLine: '#2a2a4a',
    noteBox: 'rgba(255,140,66,0.25)',
    noteBoxEdge: '#D96C2C',
    noteSelected: 'rgba(233,69,96,0.35)',
    noteSelEdge: '#e94560',
    noteEdited: 'rgba(46,134,171,0.30)',
    noteEditedEdge: '#2E86AB',
    playhead: '#e94560',
    text: '#ccc',
    textSelected: '#fff',
    textDim: '#888',
  };

  const MARGIN = { l: 60, r: 60, t: 30, b: 50 };
  const BOX_HEIGHT = 40;
  const BOX_Y_CENTER = 0.45; // relative position in plot area
  const EDGE_THRESHOLD_PX = 8;

  function getEditedBounds(idx: number): { start: number; end: number } {
    const edit = $timeEdits.find(e => e.clusterIdx === idx);
    if (edit) return { start: edit.newStart, end: edit.newEnd };
    const c = $clusters[idx];
    return { start: c.start_time, end: c.end_time };
  }

  function timeToPx(time: number): number {
    const w = canvasEl.width / window.devicePixelRatio - MARGIN.l - MARGIN.r;
    return MARGIN.l + ((time - _xRange[0]) / (_xRange[1] - _xRange[0])) * w;
  }

  function pxToTime(px: number): number {
    const w = canvasEl.width / window.devicePixelRatio - MARGIN.l - MARGIN.r;
    return _xRange[0] + ((px - MARGIN.l) / w) * (_xRange[1] - _xRange[0]);
  }

  function draw() {
    if (!ctx || !canvasEl) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = containerEl.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    canvasEl.width = w * dpr;
    canvasEl.height = h * dpr;
    canvasEl.style.width = w + 'px';
    canvasEl.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const plotW = w - MARGIN.l - MARGIN.r;
    const plotH = h - MARGIN.t - MARGIN.b;

    // Background
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    // Grid lines (time axis)
    const span = _xRange[1] - _xRange[0];
    let step = 1;
    if (span < 2) step = 0.1;
    else if (span < 5) step = 0.5;
    else if (span < 20) step = 1;
    else if (span < 60) step = 5;
    else step = 10;

    ctx.strokeStyle = COLORS.gridLine;
    ctx.lineWidth = 1;
    ctx.fillStyle = COLORS.textDim;
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';

    const gridStart = Math.ceil(_xRange[0] / step) * step;
    for (let t = gridStart; t <= _xRange[1]; t += step) {
      const x = timeToPx(t);
      if (x < MARGIN.l || x > w - MARGIN.r) continue;
      ctx.beginPath();
      ctx.moveTo(x, MARGIN.t);
      ctx.lineTo(x, h - MARGIN.b);
      ctx.stroke();
      ctx.fillText(t.toFixed(step < 1 ? 1 : 0) + 's', x, h - MARGIN.b + 14);
    }

    // Draw boxes for each cluster
    const cls = $clusters;
    const boxY = MARGIN.t + plotH * BOX_Y_CENTER - BOX_HEIGHT / 2;

    for (let i = 0; i < cls.length; i++) {
      const bounds = getEditedBounds(i);
      const x0 = timeToPx(bounds.start);
      const x1 = timeToPx(bounds.end);
      const isSelected = $selectedIndices.has(i);
      const hasEdit = $timeEdits.some(e => e.clusterIdx === i);

      // Skip if completely off-screen
      if (x1 < MARGIN.l || x0 > w - MARGIN.r) continue;

      // Box fill
      if (isSelected) {
        ctx.fillStyle = COLORS.noteSelected;
      } else if (hasEdit) {
        ctx.fillStyle = COLORS.noteEdited;
      } else {
        ctx.fillStyle = COLORS.noteBox;
      }
      ctx.fillRect(x0, boxY, x1 - x0, BOX_HEIGHT);

      // Box border
      if (isSelected) {
        ctx.strokeStyle = COLORS.noteSelEdge;
        ctx.lineWidth = 2;
      } else if (hasEdit) {
        ctx.strokeStyle = COLORS.noteEditedEdge;
        ctx.lineWidth = 1.5;
      } else {
        ctx.strokeStyle = COLORS.noteBoxEdge;
        ctx.lineWidth = 1;
      }
      ctx.strokeRect(x0, boxY, x1 - x0, BOX_HEIGHT);

      // Label
      const boxW = x1 - x0;
      if (boxW > 20) {
        ctx.fillStyle = isSelected ? COLORS.textSelected : COLORS.text;
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${i + 1}:${cls[i].note}`, (x0 + x1) / 2, boxY + BOX_HEIGHT / 2);
      }
    }

    // Playhead
    const phx = timeToPx(_playheadTime);
    if (phx >= MARGIN.l && phx <= w - MARGIN.r) {
      ctx.strokeStyle = COLORS.playhead;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(phx, MARGIN.t);
      ctx.lineTo(phx, h - MARGIN.b);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw-box preview
    if (_drawPreview) {
      const dx0 = timeToPx(Math.min(_drawPreview.startTime, _drawPreview.endTime));
      const dx1 = timeToPx(Math.max(_drawPreview.startTime, _drawPreview.endTime));
      ctx.fillStyle = 'rgba(255,140,66,0.12)';
      ctx.fillRect(dx0, MARGIN.t, dx1 - dx0, plotH);
      ctx.strokeStyle = '#D96C2C';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.strokeRect(dx0, MARGIN.t, dx1 - dx0, plotH);
      ctx.setLineDash([]);
    }

    // Time axis label
    ctx.fillStyle = COLORS.textDim;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Time (s)', w / 2, h - 6);
  }

  function scheduleDraw() {
    if (_rafPending) return;
    _rafPending = true;
    requestAnimationFrame(() => {
      _rafPending = false;
      draw();
    });
  }

  // --- Interactions ---

  function getClusterAtPx(px: number, py: number): number | null {
    const plotH = containerEl.getBoundingClientRect().height - MARGIN.t - MARGIN.b;
    const boxY = MARGIN.t + plotH * BOX_Y_CENTER - BOX_HEIGHT / 2;

    if (py < boxY || py > boxY + BOX_HEIGHT) return null;

    const cls = $clusters;
    for (let i = cls.length - 1; i >= 0; i--) {
      const bounds = getEditedBounds(i);
      const x0 = timeToPx(bounds.start);
      const x1 = timeToPx(bounds.end);
      if (px >= x0 && px <= x1) return i;
    }
    return null;
  }

  function getEdgeAtPx(px: number, py: number): { clusterIdx: number; edge: 'left' | 'right' } | null {
    const plotH = containerEl.getBoundingClientRect().height - MARGIN.t - MARGIN.b;
    const boxY = MARGIN.t + plotH * BOX_Y_CENTER - BOX_HEIGHT / 2;

    if (py < boxY || py > boxY + BOX_HEIGHT) return null;

    const cls = $clusters;
    for (let i = cls.length - 1; i >= 0; i--) {
      const bounds = getEditedBounds(i);
      const x0 = timeToPx(bounds.start);
      const x1 = timeToPx(bounds.end);
      if (py >= boxY && py <= boxY + BOX_HEIGHT) {
        if (Math.abs(px - x0) < EDGE_THRESHOLD_PX) return { clusterIdx: i, edge: 'left' };
        if (Math.abs(px - x1) < EDGE_THRESHOLD_PX) return { clusterIdx: i, edge: 'right' };
      }
    }
    return null;
  }

  function isInPlotArea(px: number, py: number): boolean {
    const rect = containerEl.getBoundingClientRect();
    return px > MARGIN.l && px < rect.width - MARGIN.r &&
           py > MARGIN.t && py < rect.height - MARGIN.b;
  }

  function setupInteractions() {
    let mode: string | null = null;
    let startX = 0;
    let startY = 0;
    let hasMoved = false;
    let edgeDragData: { clusterIdx: number; edge: 'left' | 'right'; origStart: number; origEnd: number } | null = null;
    let panStartXRange: [number, number] | null = null;
    let drawStartTime: number | null = null;

    canvasEl.addEventListener('mousedown', (e: MouseEvent) => {
      if (e.button !== 0) return;
      const rect = canvasEl.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      // Alt+empty → draw-box
      if (e.altKey && isInPlotArea(px, py)) {
        mode = 'draw-box';
        drawStartTime = pxToTime(px);
        startX = e.clientX;
        hasMoved = false;
        canvasEl.style.cursor = 'crosshair';
        e.preventDefault();
        e.stopPropagation();
        return;
      }

      // Ctrl+Shift+Drag → pan
      if (e.ctrlKey && e.shiftKey && isInPlotArea(px, py)) {
        mode = 'pan';
        startX = e.clientX;
        panStartXRange = [..._xRange] as [number, number];
        hasMoved = false;
        canvasEl.style.cursor = 'grabbing';
        e.preventDefault();
        return;
      }

      // Edge → resize
      const edge = getEdgeAtPx(px, py);
      if (edge) {
        const bounds = getEditedBounds(edge.clusterIdx);
        mode = 'edge-drag';
        edgeDragData = {
          clusterIdx: edge.clusterIdx,
          edge: edge.edge,
          origStart: bounds.start,
          origEnd: bounds.end,
        };
        startX = e.clientX;
        hasMoved = false;
        e.preventDefault();

        // Select the cluster
        $selectedIndices = new Set([edge.clusterIdx]);
        $selectedIdx = edge.clusterIdx;
        onClusterSelect(edge.clusterIdx, $clusters[edge.clusterIdx]);
        scheduleDraw();
        return;
      }

      // Shift+Click → toggle multi-select
      const clusterIdx = getClusterAtPx(px, py);
      if (e.shiftKey && clusterIdx !== null) {
        const s = new Set($selectedIndices);
        if (s.has(clusterIdx)) s.delete(clusterIdx); else s.add(clusterIdx);
        $selectedIndices = s;
        const first = s.size > 0 ? s.values().next().value! : null;
        $selectedIdx = first;
        if (first !== null) onClusterSelect(first, $clusters[first]);
        scheduleDraw();
        e.preventDefault();
        return;
      }

      // Click on cluster → select
      if (clusterIdx !== null) {
        $selectedIndices = new Set([clusterIdx]);
        $selectedIdx = clusterIdx;
        onClusterSelect(clusterIdx, $clusters[clusterIdx]);
        scheduleDraw();
        e.preventDefault();
        return;
      }

      // Click on empty → deselect + seek
      if (isInPlotArea(px, py)) {
        $selectedIndices = new Set();
        $selectedIdx = null;
        scheduleDraw();
        const time = pxToTime(px);
        if (onSeek) onSeek(time);
        e.preventDefault();
      }
    });

    window.addEventListener('mousemove', (e: MouseEvent) => {
      if (!mode) {
        // Cursor hints
        const rect = canvasEl.getBoundingClientRect();
        const px = e.clientX - rect.left;
        const py = e.clientY - rect.top;
        const edge = getEdgeAtPx(px, py);
        if (edge) {
          canvasEl.style.cursor = 'ew-resize';
        } else if (e.altKey && isInPlotArea(px, py)) {
          canvasEl.style.cursor = 'crosshair';
        } else if (e.ctrlKey && e.shiftKey && isInPlotArea(px, py)) {
          canvasEl.style.cursor = 'grab';
        } else {
          canvasEl.style.cursor = 'default';
        }
        return;
      }

      if (mode === 'draw-box' && drawStartTime !== null) {
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;
        const rect = canvasEl.getBoundingClientRect();
        const currentTime = pxToTime(e.clientX - rect.left);
        _drawPreview = { startTime: drawStartTime, endTime: currentTime };
        canvasEl.style.cursor = 'crosshair';
        scheduleDraw();
        return;
      }

      if (mode === 'edge-drag' && edgeDragData) {
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;

        const rect = canvasEl.getBoundingClientRect();
        const plotW = rect.width - MARGIN.l - MARGIN.r;
        const timePerPx = (_xRange[1] - _xRange[0]) / plotW;
        const deltaTime = dx * timePerPx;

        applyEdgeDrag(edgeDragData.clusterIdx, edgeDragData.edge, deltaTime, edgeDragData.origStart, edgeDragData.origEnd);
        scheduleDraw();
      } else if (mode === 'pan' && panStartXRange) {
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;
        const rect = canvasEl.getBoundingClientRect();
        const plotW = rect.width - MARGIN.l - MARGIN.r;
        const xSpan = panStartXRange[1] - panStartXRange[0];
        const xDelta = -(dx / plotW) * xSpan;
        let x0 = panStartXRange[0] + xDelta;
        let x1 = panStartXRange[1] + xDelta;
        if (x0 < _fullXRange[0]) { x1 += _fullXRange[0] - x0; x0 = _fullXRange[0]; }
        if (x1 > _fullXRange[1]) { x0 -= x1 - _fullXRange[1]; x1 = _fullXRange[1]; }
        _xRange = [x0, x1];
        syncWaveform(_xRange, _fullXRange[1]);
        scheduleDraw();
      }
    });

    window.addEventListener('mouseup', (e: MouseEvent) => {
      if (mode === 'draw-box') {
        if (hasMoved && drawStartTime !== null) {
          const rect = canvasEl.getBoundingClientRect();
          const endTime = pxToTime(e.clientX - rect.left);
          const start = Math.min(drawStartTime, endTime);
          const end = Math.max(drawStartTime, endTime);
          if (end - start > 0.01) {
            onDrawBox(start, end);
          }
        }
        _drawPreview = null;
        drawStartTime = null;
        canvasEl.style.cursor = '';
        scheduleDraw();
      } else if (mode === 'pan') {
        canvasEl.style.cursor = '';
      }
      mode = null;
      edgeDragData = null;
      panStartXRange = null;
      hasMoved = false;
    });

    // Scroll zoom (X only)
    let _zoomRafPending = false;
    let _pendingZoom: { delta: number; px: number } | null = null;

    canvasEl.addEventListener('wheel', (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvasEl.getBoundingClientRect();
      const px = e.clientX - rect.left;
      if (px < MARGIN.l || px > rect.width - MARGIN.r) return;

      let delta = e.deltaY;
      if (e.deltaMode === 1) delta *= 20;
      if (e.deltaMode === 2) delta *= 400;
      delta = Math.sign(delta) * Math.min(Math.abs(delta), 100);

      if (!_pendingZoom) _pendingZoom = { delta: 0, px };
      _pendingZoom.delta += delta;
      _pendingZoom.px = px;

      if (!_zoomRafPending) {
        _zoomRafPending = true;
        requestAnimationFrame(() => {
          _zoomRafPending = false;
          if (!_pendingZoom) return;
          const { delta, px } = _pendingZoom;
          _pendingZoom = null;
          const factor = Math.pow(1.002, delta);
          const xAtMouse = pxToTime(px);
          let x0 = xAtMouse - (xAtMouse - _xRange[0]) * factor;
          let x1 = xAtMouse + (_xRange[1] - xAtMouse) * factor;
          x0 = Math.max(_fullXRange[0], x0);
          x1 = Math.min(_fullXRange[1], x1);
          if (x1 - x0 < 0.5) return;
          _xRange = [x0, x1];
          syncWaveform(_xRange, _fullXRange[1]);
          draw();
        });
      }
    }, { passive: false });
  }

  function applyEdgeDrag(
    clusterIdx: number,
    edge: 'left' | 'right',
    deltaTime: number,
    origStart: number,
    origEnd: number
  ) {
    const cls = $clusters;
    const minDurationMs = $params.min_note_duration_ms;
    const minDuration = minDurationMs / 1000;

    // Build current bounds for all clusters
    const bounds = cls.map((_, i) => getEditedBounds(i));

    if (edge === 'right') {
      // Dragging right edge of clusterIdx.
      // Only this cluster and the immediate next neighbor are affected.
      let newEnd = origEnd + deltaTime;
      const nextIdx = clusterIdx + 1 < cls.length ? clusterIdx + 1 : null;

      if (nextIdx !== null) {
        // The neighbor's far edge is the hard boundary — it never moves.
        const nextEnd = bounds[nextIdx].end;

        // Clamp: neighbor must keep at least minDuration
        const maxNewEnd = nextEnd - minDuration;
        if (newEnd > maxNewEnd) newEnd = maxNewEnd;

        const origNextStart = cls[nextIdx].start_time;

        if (newEnd >= bounds[nextIdx].start) {
          // Overlapping or touching — push neighbor's start to our edge
          if (nextEnd - newEnd >= minDuration) {
            updateTimeEdit(nextIdx, newEnd, nextEnd);
          }
        } else if (bounds[nextIdx].start > origNextStart) {
          // Gap forming and neighbor was compressed — decompress to follow
          // our edge back, but not past its original position
          const restoredStart = Math.max(newEnd, origNextStart);
          if (Math.abs(restoredStart - origNextStart) < 0.001) {
            // Fully restored to original
            const existingNextEdit = $timeEdits.find(e => e.clusterIdx === nextIdx);
            if (existingNextEdit && Math.abs(existingNextEdit.newEnd - cls[nextIdx].end_time) < 0.001) {
              removeTimeEdit(nextIdx);
            } else if (existingNextEdit) {
              updateTimeEdit(nextIdx, origNextStart, existingNextEdit.newEnd);
            }
          } else {
            updateTimeEdit(nextIdx, restoredStart, nextEnd);
          }
        }
      } else {
        // No next neighbor — can't extend past original end (nothing to absorb)
        if (newEnd > origEnd) newEnd = origEnd;
      }

      // This cluster must keep at least minDuration
      if (newEnd - bounds[clusterIdx].start < minDuration) {
        newEnd = bounds[clusterIdx].start + minDuration;
      }

      updateTimeEdit(clusterIdx, bounds[clusterIdx].start, newEnd);

    } else {
      // Dragging left edge of clusterIdx.
      // Only this cluster and the immediate previous neighbor are affected.
      let newStart = origStart + deltaTime;
      const prevIdx = clusterIdx > 0 ? clusterIdx - 1 : null;

      if (prevIdx !== null) {
        // The neighbor's far edge is the hard boundary — it never moves.
        const prevStart = bounds[prevIdx].start;

        // Clamp: neighbor must keep at least minDuration
        const minNewStart = prevStart + minDuration;
        if (newStart < minNewStart) newStart = minNewStart;

        const origPrevEnd = cls[prevIdx].end_time;

        if (newStart <= bounds[prevIdx].end) {
          // Overlapping or touching — push neighbor's end to our edge
          if (newStart - prevStart >= minDuration) {
            updateTimeEdit(prevIdx, prevStart, newStart);
          }
        } else if (bounds[prevIdx].end < origPrevEnd) {
          // Gap forming and neighbor was compressed — decompress to follow
          // our edge back, but not past its original position
          const restoredEnd = Math.min(newStart, origPrevEnd);
          if (Math.abs(restoredEnd - origPrevEnd) < 0.001) {
            // Fully restored to original
            const existingPrevEdit = $timeEdits.find(e => e.clusterIdx === prevIdx);
            if (existingPrevEdit && Math.abs(existingPrevEdit.newStart - cls[prevIdx].start_time) < 0.001) {
              removeTimeEdit(prevIdx);
            } else if (existingPrevEdit) {
              updateTimeEdit(prevIdx, existingPrevEdit.newStart, origPrevEnd);
            }
          } else {
            updateTimeEdit(prevIdx, prevStart, restoredEnd);
          }
        }
      } else {
        // No prev neighbor — can't extend past original start
        if (newStart < origStart) newStart = origStart;
      }

      // This cluster must keep at least minDuration
      if (bounds[clusterIdx].end - newStart < minDuration) {
        newStart = bounds[clusterIdx].end - minDuration;
      }

      updateTimeEdit(clusterIdx, newStart, bounds[clusterIdx].end);
    }
  }

  function updateTimeEdit(clusterIdx: number, newStart: number, newEnd: number) {
    const existing = $timeEdits.findIndex(e => e.clusterIdx === clusterIdx);
    const c = $clusters[clusterIdx];

    // If the edit returns to original bounds, remove the edit
    if (Math.abs(newStart - c.start_time) < 0.001 && Math.abs(newEnd - c.end_time) < 0.001) {
      if (existing >= 0) {
        removeTimeEdit(clusterIdx);
      }
      return;
    }

    const edit: TimeEdit = { clusterIdx, newStart, newEnd };
    if (existing >= 0) {
      const edits = [...$timeEdits];
      edits[existing] = edit;
      $timeEdits = edits;
    } else {
      $timeEdits = [...$timeEdits, edit];
    }
    $dirtyTimeEdits = new Set([...$dirtyTimeEdits, clusterIdx]);
  }

  function removeTimeEdit(clusterIdx: number) {
    $timeEdits = $timeEdits.filter(e => e.clusterIdx !== clusterIdx);
    const dirty = new Set($dirtyTimeEdits);
    dirty.delete(clusterIdx);
    $dirtyTimeEdits = dirty;
  }

  // --- Reactive drawing ---

  $effect(() => {
    // Re-draw when clusters, selection, or time edits change
    void $clusters;
    void $selectedIndices;
    void $timeEdits;
    if (_mounted) scheduleDraw();
  });

  $effect(() => {
    // Update x range when clusters change
    const cls = $clusters;
    if (cls.length > 0) {
      const maxEnd = Math.max(...cls.map(c => c.end_time));
      const newFullX: [number, number] = [0, maxEnd * 1.05];
      const extentChanged = Math.abs(newFullX[1] - _fullXRange[1]) > 0.01;
      _fullXRange = newFullX;
      if (extentChanged) {
        _xRange = [..._fullXRange] as [number, number];
      }
    }
  });

  onMount(() => {
    ctx = canvasEl.getContext('2d')!;
    _mounted = true;
    setupInteractions();
    draw();

    const observer = new ResizeObserver(() => scheduleDraw());
    observer.observe(containerEl);
    return () => observer.disconnect();
  });

  // Public methods
  export function updatePlayhead(time: number) {
    _playheadTime = time;
    if (!$clusters?.length) return;

    // Auto-scroll playhead
    const span = _xRange[1] - _xRange[0];
    if (time > _xRange[1] - span * 0.1 && _xRange[1] < _fullXRange[1]) {
      let x0 = Math.max(_fullXRange[0], time - span * 0.1);
      let x1 = x0 + span;
      if (x1 > _fullXRange[1]) {
        x1 = _fullXRange[1];
        x0 = Math.max(_fullXRange[0], x1 - span);
      }
      _xRange = [x0, x1];
      syncWaveform(_xRange, _fullXRange[1]);
    }
    scheduleDraw();
  }

  export function syncToRange(xRange: [number, number]) {
    _xRange = xRange;
    scheduleDraw();
  }
</script>

<div class="plot-container" bind:this={containerEl}>
  <canvas bind:this={canvasEl}></canvas>
  <div class="plot-controls">
    <span class="zoom-hint">Scroll to zoom X · Ctrl+Shift+Drag to pan · Drag edges to stretch/compress · Alt+Drag to draw box · Shift+click to multi-select · Delete to remove</span>
  </div>
  <ProcessingOverlay />
</div>

<style>
  canvas {
    display: block;
    width: 100%;
    height: 100%;
  }
</style>
