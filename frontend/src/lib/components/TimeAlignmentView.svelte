<script lang="ts">
  import { onMount } from 'svelte';
  import {
    clusters, selectedIdx, selectedIndices, timeEdits, dirtyTimeEdits,
    referenceClusters, midiNotes, showCorrectionCurve, backendTimemap,
    activeTab, viewXRange, waveformReset
  } from '$lib/stores/appState';
  import { params } from '$lib/stores/params';
  import ProcessingOverlay from './ProcessingOverlay.svelte';
  import type { Cluster, MidiNote, TimeEdit, TimemapEntry } from '$lib/utils/types';

  interface Props {
    onClusterSelect: (idx: number, cluster: Cluster) => void;
    onDrawBox: (start: number, end: number) => void;
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
    onEditComplete?: () => void;
  }

  let { onClusterSelect, onDrawBox, syncWaveform, onSeek, onEditComplete }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let containerEl: HTMLDivElement;
  let ctx: CanvasRenderingContext2D;
  let _rafPending = false;

  // View state
  let _xRange: [number, number] = [0, 10];
  let _fullXRange: [number, number] = [0, 10];
  let _pendingZoomReset = false;

  /** Update _xRange and push to shared store so the other tab stays in sync. */
  function setXRange(range: [number, number]) {
    _xRange = range;
    $viewXRange = range;
  }
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
    refBox: 'rgba(76,175,80,0.25)',
    refBoxEdge: '#4CAF50',
    refText: '#a5d6a7',
    midiLine: '#ab47bc',
    midiText: '#ce93d8',
    timeCurveLine: '#f0c040',
    timeCurveFill: 'rgba(240,192,64,0.15)',
    timeCurveBaseline: 'rgba(240,192,64,0.3)',
  };

  const MARGIN = { l: 60, r: 60, t: 30, b: 50 };
  const BOX_HEIGHT = 40;
  const BOX_GAP = 8;
  const REF_BOX_Y_CENTER = 0.25; // reference row (above)
  const BOX_Y_CENTER = 0.45; // main row (below)
  const MIDI_LINE_HEIGHT = 3;
  const MIDI_ROW_TOP = 0.68; // midi pitch lines row (below main)
  const EDGE_THRESHOLD_PX = 8;
  const TIME_CURVE_TOP = 0.06;
  const TIME_CURVE_HEIGHT = 0.14;

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

    // Draw reference boxes (green row above main)
    const refCls = $referenceClusters;
    if (refCls.length > 0) {
      const refBoxY = MARGIN.t + plotH * REF_BOX_Y_CENTER - BOX_HEIGHT / 2;

      for (let i = 0; i < refCls.length; i++) {
        const rc = refCls[i];
        const x0 = timeToPx(rc.start_time);
        const x1 = timeToPx(rc.end_time);

        if (x1 < MARGIN.l || x0 > w - MARGIN.r) continue;

        ctx.fillStyle = COLORS.refBox;
        ctx.fillRect(x0, refBoxY, x1 - x0, BOX_HEIGHT);

        ctx.strokeStyle = COLORS.refBoxEdge;
        ctx.lineWidth = 1;
        ctx.strokeRect(x0, refBoxY, x1 - x0, BOX_HEIGHT);

        const boxW = x1 - x0;
        if (boxW > 20) {
          ctx.fillStyle = COLORS.refText;
          ctx.font = '11px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(`${i + 1}:${rc.note}`, (x0 + x1) / 2, refBoxY + BOX_HEIGHT / 2);
        }
      }
    }

    // MIDI reference pitch lines
    const midiData = $midiNotes;
    if (midiData.length > 0) {
      // Compute frequency range from MIDI notes
      const midiFreqs = midiData.map(n => n.frequency);
      const minFreq = Math.min(...midiFreqs);
      const maxFreq = Math.max(...midiFreqs);
      // Reserve vertical space for MIDI row
      const midiRowTop = MARGIN.t + plotH * MIDI_ROW_TOP;
      const midiRowHeight = plotH * 0.25;

      // Map frequency to Y position within the MIDI row (higher pitch = higher on screen)
      const freqRange = maxFreq - minFreq;
      const freqToY = (freq: number): number => {
        if (freqRange < 1) return midiRowTop + midiRowHeight / 2;
        const ratio = (freq - minFreq) / freqRange;
        return midiRowTop + midiRowHeight - ratio * midiRowHeight;
      };

      // Row label
      ctx.fillStyle = COLORS.textDim;
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'top';
      ctx.fillText('MIDI', MARGIN.l - 6, midiRowTop);

      for (let i = 0; i < midiData.length; i++) {
        const mn = midiData[i];
        const x0 = timeToPx(mn.start_time);
        const x1 = timeToPx(mn.end_time);

        if (x1 < MARGIN.l || x0 > w - MARGIN.r) continue;

        const y = freqToY(mn.frequency);

        // Draw line
        ctx.strokeStyle = COLORS.midiLine;
        ctx.lineWidth = MIDI_LINE_HEIGHT;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(Math.max(x0, MARGIN.l), y);
        ctx.lineTo(Math.min(x1, w - MARGIN.r), y);
        ctx.stroke();

        // Note label
        const lineW = x1 - x0;
        if (lineW > 18) {
          ctx.fillStyle = COLORS.midiText;
          ctx.font = '9px sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'bottom';
          ctx.fillText(mn.note_name, Math.max(x0, MARGIN.l) + 2, y - 3);
        }
      }
    }

    // Time correction curve — based on timemap keypoints (same as Rubberband).
    // Uses backend timemap when available, otherwise computes a live preview
    // matching the backend's generate_time_map algorithm.
    if ($showCorrectionCurve && cls.length > 0) {
      const curveTop = MARGIN.t + plotH * TIME_CURVE_TOP;
      const curveH = plotH * TIME_CURVE_HEIGHT;
      const baselineY = curveTop + curveH / 2;

      // Build timemap keypoints mirroring backend's generate_time_map:
      // For each edited cluster, add (src_start, tgt_start) and (src_end, tgt_end).
      // Add identity anchors at neighboring unedited cluster boundaries.
      // Use backend timemap if no new dirty edits; otherwise compute live preview.
      let keypoints: { src: number; tgt: number }[];

      const hasDirtyEdits = $dirtyTimeEdits.size > 0;

      if (!hasDirtyEdits && $backendTimemap.length > 0) {
        // Use the actual backend timemap
        keypoints = $backendTimemap.map(e => ({ src: e.source_s, tgt: e.target_s }));
      } else {
        // Compute live preview matching backend anchor logic:
        // Pin both start AND end of unedited neighbors so gaps absorb changes.
        const editMap = new Map<number, TimeEdit>();
        for (const edit of $timeEdits) {
          editMap.set(edit.clusterIdx, edit);
        }

        const kpSet = new Map<number, number>(); // src → tgt (deduplicates)
        kpSet.set(0, 0); // start anchor

        for (const [idx, edit] of editMap) {
          if (idx >= cls.length) continue;
          const c = cls[idx];

          // Edited cluster keyframes
          kpSet.set(c.start_time, edit.newStart);
          kpSet.set(c.end_time, edit.newEnd);

          // Previous neighbor: pin both start AND end (if not also edited)
          if (idx > 0 && !editMap.has(idx - 1)) {
            const prev = cls[idx - 1];
            if (!kpSet.has(prev.start_time)) kpSet.set(prev.start_time, prev.start_time);
            if (!kpSet.has(prev.end_time)) kpSet.set(prev.end_time, prev.end_time);
          }

          // Next neighbor: pin both start AND end (if not also edited)
          if (idx < cls.length - 1 && !editMap.has(idx + 1)) {
            const nxt = cls[idx + 1];
            if (!kpSet.has(nxt.start_time)) kpSet.set(nxt.start_time, nxt.start_time);
            if (!kpSet.has(nxt.end_time)) kpSet.set(nxt.end_time, nxt.end_time);
          }
        }

        // End anchor — use last cluster end or a rough audio end
        const lastEnd = cls[cls.length - 1].end_time + 1;
        if (!kpSet.has(lastEnd)) {
          kpSet.set(lastEnd, lastEnd);
        }

        keypoints = Array.from(kpSet.entries())
          .map(([src, tgt]) => ({ src, tgt }))
          .sort((a, b) => a.src - b.src);
      }

      // Compute log2 speed ratio between adjacent keypoints
      const MAX_DEV = 4;
      type KpSegment = { tgtStart: number; tgtEnd: number; dev: number };
      const kpSegments: KpSegment[] = [];
      let maxDev = 0;

      for (let i = 1; i < keypoints.length; i++) {
        const srcDur = keypoints[i].src - keypoints[i - 1].src;
        const tgtDur = keypoints[i].tgt - keypoints[i - 1].tgt;
        let dev = 0;
        if (srcDur > 0.001 && tgtDur > 0.001) {
          dev = Math.log2(srcDur / tgtDur);
        } else if (srcDur > 0.001 && tgtDur <= 0.001) {
          dev = MAX_DEV;
        } else if (srcDur <= 0.001 && tgtDur > 0.001) {
          dev = -MAX_DEV;
        }
        dev = Math.max(-MAX_DEV, Math.min(MAX_DEV, dev));
        kpSegments.push({ tgtStart: keypoints[i - 1].tgt, tgtEnd: keypoints[i].tgt, dev });
        if (Math.abs(dev) > maxDev) maxDev = Math.abs(dev);
      }

      const scale = Math.max(maxDev * 1.3, 3.0);

      // Draw baseline
      ctx.strokeStyle = COLORS.timeCurveBaseline;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(MARGIN.l, baselineY);
      ctx.lineTo(w - MARGIN.r, baselineY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label
      ctx.fillStyle = COLORS.timeCurveLine;
      ctx.font = '9px sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText('Time', MARGIN.l - 6, baselineY);

      // Helper to draw the curve path
      function drawCurvePath() {
        ctx.beginPath();
        ctx.moveTo(MARGIN.l, baselineY);
        for (const seg of kpSegments) {
          const devY = baselineY - (seg.dev / scale) * (curveH / 2);
          const x0 = timeToPx(seg.tgtStart);
          const x1 = timeToPx(seg.tgtEnd);
          ctx.lineTo(x0, devY);
          ctx.lineTo(x1, devY);
        }
        ctx.lineTo(w - MARGIN.r, baselineY);
      }

      // Fill
      drawCurvePath();
      ctx.lineTo(w - MARGIN.r, baselineY);
      ctx.closePath();
      ctx.fillStyle = COLORS.timeCurveFill;
      ctx.fill();

      // Stroke
      drawCurvePath();
      ctx.strokeStyle = COLORS.timeCurveLine;
      ctx.lineWidth = 1.5;
      ctx.stroke();
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
    let moveDragData: { clusterIdx: number; origStart: number; origEnd: number } | null = null;
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

      // Click on cluster body (not edge) → start move-drag
      const clusterAtPx = getClusterAtPx(px, py);
      if (clusterAtPx !== null && !e.shiftKey) {
        const bounds = getEditedBounds(clusterAtPx);
        mode = 'move-drag';
        moveDragData = {
          clusterIdx: clusterAtPx,
          origStart: bounds.start,
          origEnd: bounds.end,
        };
        startX = e.clientX;
        hasMoved = false;

        // Select the cluster
        $selectedIndices = new Set([clusterAtPx]);
        $selectedIdx = clusterAtPx;
        onClusterSelect(clusterAtPx, $clusters[clusterAtPx]);
        scheduleDraw();
        e.preventDefault();
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
        } else if (getClusterAtPx(px, py) !== null) {
          canvasEl.style.cursor = 'grab';
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

      if (mode === 'move-drag' && moveDragData) {
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;

        const rect = canvasEl.getBoundingClientRect();
        const plotW = rect.width - MARGIN.l - MARGIN.r;
        const timePerPx = (_xRange[1] - _xRange[0]) / plotW;
        const deltaTime = dx * timePerPx;

        canvasEl.style.cursor = 'grabbing';
        applyMoveDrag(moveDragData.clusterIdx, deltaTime, moveDragData.origStart, moveDragData.origEnd);
        scheduleDraw();
      } else if (mode === 'edge-drag' && edgeDragData) {
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
        setXRange([x0, x1]);
        syncWaveform(_xRange, _fullXRange[1]);
        scheduleDraw();
      }
    });

    window.addEventListener('mouseup', (e: MouseEvent) => {
      if (mode === 'move-drag') {
        canvasEl.style.cursor = '';
        if (hasMoved) onEditComplete?.();
      } else if (mode === 'edge-drag') {
        canvasEl.style.cursor = '';
        if (hasMoved) onEditComplete?.();
      } else if (mode === 'draw-box') {
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
      moveDragData = null;
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
          const center = _playheadTime;
          let x0 = center - (center - _xRange[0]) * factor;
          let x1 = center + (_xRange[1] - center) * factor;
          x0 = Math.max(_fullXRange[0], x0);
          x1 = Math.min(_fullXRange[1], x1);
          if (x1 - x0 < 0.5) return;
          setXRange([x0, x1]);
          syncWaveform(_xRange, _fullXRange[1]);
          draw();
        });
      }
    }, { passive: false });
  }

  // --- Limit helpers ---
  // All limits are relative to ORIGINAL durations.
  // max_note_stretch: 200 means note can be at most 200% of original (2x).
  // max_note_compress: 50 means note can be at most compressed to 50% of original.
  // max_gap_compress: 0 means gap can be fully removed.

  function getOrigGapDuration(idx: number, side: 'before' | 'after'): number {
    const cls = $clusters;
    if (side === 'before') {
      if (idx === 0) return cls[0].start_time; // gap from 0 to first cluster
      return cls[idx].start_time - cls[idx - 1].end_time;
    } else {
      if (idx >= cls.length - 1) return 0;
      return cls[idx + 1].start_time - cls[idx].end_time;
    }
  }

  function getOrigNoteDuration(idx: number): number {
    const cls = $clusters;
    return cls[idx].end_time - cls[idx].start_time;
  }

  function noteMinDur(idx: number): number {
    return getOrigNoteDuration(idx) * ($params.max_note_compress / 100);
  }

  function noteMaxDur(idx: number): number {
    return getOrigNoteDuration(idx) * ($params.max_note_stretch / 100);
  }

  function gapMinDur(origGapDur: number): number {
    return origGapDur * ($params.max_gap_compress / 100);
  }

  function gapMaxDur(origGapDur: number): number {
    return origGapDur * ($params.max_gap_stretch / 100);
  }

  /**
   * Compute the available space in a given direction from gap compression
   * and neighbor note compression. Does NOT include the note's own stretch.
   */
  function computeAvailableSpace(clusterIdx: number, direction: 'right' | 'left'): number {
    const cls = $clusters;

    let neighborIdx: number | null = null;
    let origGapDur = 0;

    if (direction === 'right' && clusterIdx < cls.length - 1) {
      neighborIdx = clusterIdx + 1;
      origGapDur = getOrigGapDuration(clusterIdx, 'after');
    } else if (direction === 'left' && clusterIdx > 0) {
      neighborIdx = clusterIdx - 1;
      origGapDur = getOrigGapDuration(clusterIdx, 'before');
    }

    const gapCompressRoom = origGapDur - gapMinDur(origGapDur);
    if (neighborIdx === null) return gapCompressRoom;

    const neighborCompressRoom = getOrigNoteDuration(neighborIdx) - noteMinDur(neighborIdx);

    return gapCompressRoom + neighborCompressRoom;
  }

  /**
   * Apply cascading logic for an edge moving outward by `expansion` amount.
   * Cascading order: gap compresses first, then neighbor note compresses.
   * Only creates a time edit on the neighbor when its duration actually changes
   * (i.e., gap fully absorbed and neighbor starts compressing).
   */
  function applyCascadingExpansion(
    clusterIdx: number,
    direction: 'right' | 'left',
    edgePos: number, // the desired new edge position
  ) {
    const cls = $clusters;
    const neighborIdx = direction === 'right'
      ? (clusterIdx < cls.length - 1 ? clusterIdx + 1 : null)
      : (clusterIdx > 0 ? clusterIdx - 1 : null);

    if (neighborIdx === null) return;

    const origGapDur = direction === 'right'
      ? getOrigGapDuration(clusterIdx, 'after')
      : getOrigGapDuration(clusterIdx, 'before');

    const origNeighborDur = getOrigNoteDuration(neighborIdx);

    // How much the edge has expanded past the original cluster boundary
    const origEdge = direction === 'right' ? cls[clusterIdx].end_time : cls[clusterIdx].start_time;
    const expansion = direction === 'right' ? edgePos - origEdge : origEdge - edgePos;

    if (expansion <= 0) {
      // Edge hasn't expanded past original — restore neighbor if needed
      restoreNeighbor(neighborIdx);
      return;
    }

    // Phase 1: gap absorbs expansion (gap compresses)
    const gapCompressRoom = origGapDur - gapMinDur(origGapDur);
    const gapAbsorbed = Math.min(expansion, gapCompressRoom);
    const remainingAfterGap = expansion - gapAbsorbed;

    // Phase 2: neighbor note absorbs remaining (neighbor compresses)
    const neighborCompressRoom = origNeighborDur - noteMinDur(neighborIdx);
    const neighborAbsorbed = Math.min(remainingAfterGap, neighborCompressRoom);

    // Only edit the neighbor if its duration actually changes (phase 2 kicks in)
    const neighborOrigStart = cls[neighborIdx].start_time;
    const neighborOrigEnd = cls[neighborIdx].end_time;

    if (neighborAbsorbed > 0.001) {
      // Neighbor compresses: only its facing edge moves
      if (direction === 'right') {
        updateTimeEdit(neighborIdx, neighborOrigStart + neighborAbsorbed, neighborOrigEnd);
      } else {
        updateTimeEdit(neighborIdx, neighborOrigStart, neighborOrigEnd - neighborAbsorbed);
      }
    } else {
      restoreNeighbor(neighborIdx);
    }
  }

  function restoreNeighbor(neighborIdx: number) {
    const cls = $clusters;
    const existingEdit = $timeEdits.find(e => e.clusterIdx === neighborIdx);
    if (existingEdit) {
      if (Math.abs(existingEdit.newStart - cls[neighborIdx].start_time) < 0.001 &&
          Math.abs(existingEdit.newEnd - cls[neighborIdx].end_time) < 0.001) {
        removeTimeEdit(neighborIdx);
      }
    }
  }

  function applyMoveDrag(
    clusterIdx: number,
    deltaTime: number,
    origStart: number,
    origEnd: number
  ) {
    const cls = $clusters;
    const duration = origEnd - origStart;
    let delta = deltaTime;

    // Compute max move in each direction
    if (delta > 0) {
      // Moving right: right side expands, left side contracts
      const maxRight = computeAvailableSpace(clusterIdx, 'right');
      delta = Math.min(delta, maxRight);
    } else if (delta < 0) {
      const maxLeft = computeAvailableSpace(clusterIdx, 'left');
      delta = Math.max(delta, -maxLeft);
    }

    // Don't go below 0
    if (origStart + delta < 0) delta = -origStart;

    const newStart = origStart + delta;
    const newEnd = origEnd + delta;

    // Apply cascading on both sides
    applyCascadingExpansion(clusterIdx, 'right', newEnd);
    applyCascadingExpansion(clusterIdx, 'left', newStart);

    // Also handle restoring neighbors when moving back toward original
    if (clusterIdx > 0) {
      const prevIdx = clusterIdx - 1;
      const prevBounds = getEditedBounds(prevIdx);
      const origPrevEnd = cls[prevIdx].end_time;
      if (newStart > origPrevEnd && prevBounds.end < origPrevEnd) {
        restoreNeighbor(prevIdx);
      }
    }
    if (clusterIdx < cls.length - 1) {
      const nextIdx = clusterIdx + 1;
      const nextBounds = getEditedBounds(nextIdx);
      const origNextStart = cls[nextIdx].start_time;
      if (newEnd < origNextStart && nextBounds.start > origNextStart) {
        restoreNeighbor(nextIdx);
      }
    }

    updateTimeEdit(clusterIdx, newStart, newEnd);
  }

  function applyEdgeDrag(
    clusterIdx: number,
    edge: 'left' | 'right',
    deltaTime: number,
    origStart: number,
    origEnd: number
  ) {
    const cls = $clusters;
    const bounds = cls.map((_, i) => getEditedBounds(i));
    const origNoteDur = getOrigNoteDuration(clusterIdx);

    if (edge === 'right') {
      let newEnd = origEnd + deltaTime;
      const fixedStart = bounds[clusterIdx].start;

      // Clamp: note stretch limit
      const maxEnd = cls[clusterIdx].start_time + noteMaxDur(clusterIdx);
      if (newEnd > maxEnd) newEnd = maxEnd;

      // Clamp: note compress limit
      const minEnd = fixedStart + noteMinDur(clusterIdx);
      if (newEnd < minEnd) newEnd = minEnd;

      // Clamp: cascading limit (gap + neighbor)
      const availableSpace = computeAvailableSpace(clusterIdx, 'right');
      const origEdge = cls[clusterIdx].end_time;
      if (newEnd > origEdge + availableSpace) newEnd = origEdge + availableSpace;

      // Apply cascading effects on neighbor
      applyCascadingExpansion(clusterIdx, 'right', newEnd);

      updateTimeEdit(clusterIdx, fixedStart, newEnd);

    } else {
      let newStart = origStart + deltaTime;
      const fixedEnd = bounds[clusterIdx].end;

      // Clamp: note stretch limit
      const minStart = cls[clusterIdx].end_time - noteMaxDur(clusterIdx);
      if (newStart < minStart) newStart = minStart;

      // Clamp: note compress limit
      const maxStart = fixedEnd - noteMinDur(clusterIdx);
      if (newStart > maxStart) newStart = maxStart;

      // Clamp: cascading limit (gap + neighbor)
      const availableSpace = computeAvailableSpace(clusterIdx, 'left');
      const origEdge = cls[clusterIdx].start_time;
      if (newStart < origEdge - availableSpace) newStart = origEdge - availableSpace;

      // Don't go below 0
      if (newStart < 0) newStart = 0;

      // Apply cascading effects on neighbor
      applyCascadingExpansion(clusterIdx, 'left', newStart);

      updateTimeEdit(clusterIdx, newStart, fixedEnd);
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
    // Re-draw when clusters, selection, time edits, reference, or correction toggle change
    void $clusters;
    void $selectedIndices;
    void $timeEdits;
    void $referenceClusters;
    void $midiNotes;
    void $showCorrectionCurve;
    void $backendTimemap;
    if (_mounted) scheduleDraw();
  });

  // Flag a zoom reset when a new file is loaded
  $effect(() => {
    void $waveformReset;
    _pendingZoomReset = true;
  });

  $effect(() => {
    // Update full x range when clusters change
    const cls = $clusters;
    const refCls2 = $referenceClusters;
    const midiNts = $midiNotes;
    if (cls.length > 0 || refCls2.length > 0 || midiNts.length > 0) {
      const mainMax = cls.length > 0 ? Math.max(...cls.map(c => c.end_time)) : 0;
      const refMax = refCls2.length > 0 ? Math.max(...refCls2.map(c => c.end_time)) : 0;
      const midiMax = midiNts.length > 0 ? Math.max(...midiNts.map(n => n.end_time)) : 0;
      const maxEnd = Math.max(mainMax, refMax, midiMax);
      _fullXRange = [0, maxEnd * 1.05];

      // Only reset zoom when a new file was loaded, never during editing
      if (_pendingZoomReset) {
        _pendingZoomReset = false;
        setXRange([..._fullXRange] as [number, number]);
      }
    }
  });

  // Restore shared x-range and sync waveform when switching to time tab
  $effect(() => {
    const tab = $activeTab;
    if (tab === 'time' && _mounted) {
      _xRange = [...$viewXRange] as [number, number];
      syncWaveform(_xRange, _fullXRange[1]);
      scheduleDraw();
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
      setXRange([x0, x1]);
      syncWaveform(_xRange, _fullXRange[1]);
    }
    scheduleDraw();
  }

  /** Update playhead time without triggering redraws (for use when tab is hidden). */
  export function setPlayheadTime(time: number) {
    _playheadTime = time;
  }

  export function syncToRange(xRange: [number, number]) {
    _xRange = xRange;
    scheduleDraw();
  }
</script>

<div class="plot-container" bind:this={containerEl}>
  <canvas bind:this={canvasEl}></canvas>
  <div class="plot-controls">
    <span class="zoom-hint">Scroll to zoom X · Ctrl+Shift+Drag to pan · Drag box to move · Drag edges to stretch/compress · Alt+Drag to draw box · Shift+click to multi-select · Delete to remove</span>
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
