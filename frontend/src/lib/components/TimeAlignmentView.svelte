<script lang="ts">
  import { onMount } from 'svelte';
  import {
    clusters, selectedIdx, selectedIndices, stretchMarkers, dirtyStretchMarkers, selectedMarkerIdx,
    referenceClusters, referenceStretchMarkers, referenceLoaded,
    midiNotes, showCorrectionCurve, backendTimemap,
    activeTab, viewXRange, waveformReset
  } from '$lib/stores/appState';
  import { params } from '$lib/stores/params';
  import ProcessingOverlay from './ProcessingOverlay.svelte';
  import type { Cluster, MidiNote, StretchMarker, TimemapEntry } from '$lib/utils/types';

  interface Props {
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
    onEditComplete?: (markerIdx: number) => void;
  }

  let { syncWaveform, onSeek, onEditComplete }: Props = $props();

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

  const COLORS = {
    bg: '#16213e',
    gridLine: '#2a2a4a',
    noteLabel: '#ccc',
    noteLabelDim: '#888',
    playhead: '#e94560',
    text: '#ccc',
    textDim: '#888',
    midiLine: '#ab47bc',
    midiText: '#ce93d8',
    timeCurveLine: '#f0c040',
    timeCurveFill: 'rgba(240,192,64,0.15)',
    timeCurveBaseline: 'rgba(240,192,64,0.3)',
    // Main audio markers
    markerDefault: '#888',
    markerMoved: '#2dd4bf',
    markerGhost: 'rgba(45,212,191,0.35)',
    noteRegion: 'rgba(255,140,66,0.10)',
    noteRegionEdge: 'rgba(255,140,66,0.25)',
    // Reference markers
    refMarker: '#4CAF50',
    refNoteRegion: 'rgba(76,175,80,0.10)',
    refNoteRegionEdge: 'rgba(76,175,80,0.25)',
    refNoteLabel: '#a5d6a7',
    // Split divider
    splitLine: '#3a3a5a',
    splitLabel: '#666',
  };

  const MARGIN = { l: 60, r: 60, t: 30, b: 50 };
  const MARKER_HANDLE_SIZE = 7;
  const MARKER_HIT_THRESHOLD = 10;
  const MIDI_LINE_HEIGHT = 3;
  const TIME_CURVE_TOP_FRAC = 0.06;
  const TIME_CURVE_HEIGHT_FRAC = 0.12;

  // --- Marker generation ---

  function generateMarkersFromClusters(cls: Cluster[], prefix: string): StretchMarker[] {
    const markers: StretchMarker[] = [];
    const padding = $params.cluster_padding_ms / 1000;

    if (cls.length === 0) return markers;

    // Edge marker before first cluster (if there's enough space)
    if (cls[0].start_time >= padding) {
      markers.push({
        id: `${prefix}-pre-0`,
        originalTime: cls[0].start_time - padding,
        currentTime: cls[0].start_time - padding,
        leftClusterIdx: -1,
        rightClusterIdx: 0,
      });
    }

    // Gap markers between consecutive clusters
    for (let i = 0; i < cls.length - 1; i++) {
      const gapStart = cls[i].end_time;
      const gapEnd = cls[i + 1].start_time;
      const gapDuration = gapEnd - gapStart;

      if (gapDuration > padding * 2) {
        // Long pause: place post-cluster and pre-cluster markers
        markers.push({
          id: `${prefix}-${i}-post`,
          originalTime: gapStart + padding,
          currentTime: gapStart + padding,
          leftClusterIdx: i,
          rightClusterIdx: i + 1,
        });
        markers.push({
          id: `${prefix}-${i + 1}-pre`,
          originalTime: gapEnd - padding,
          currentTime: gapEnd - padding,
          leftClusterIdx: i,
          rightClusterIdx: i + 1,
        });
      } else {
        // Short gap: single midpoint marker
        const midpoint = gapStart >= gapEnd ? gapStart : (gapStart + gapEnd) / 2;
        markers.push({
          id: `${prefix}-${i}-${i + 1}`,
          originalTime: midpoint,
          currentTime: midpoint,
          leftClusterIdx: i,
          rightClusterIdx: i + 1,
        });
      }
    }

    // Edge marker after last cluster
    const lastEnd = cls[cls.length - 1].end_time;
    markers.push({
      id: `${prefix}-post-${cls.length - 1}`,
      originalTime: lastEnd + padding,
      currentTime: lastEnd + padding,
      leftClusterIdx: cls.length - 1,
      rightClusterIdx: cls.length,
    });

    return markers;
  }

  // Auto-generate main markers when clusters change and no markers exist
  $effect(() => {
    const cls = $clusters;
    if (cls.length > 0 && $stretchMarkers.length === 0) {
      $stretchMarkers = generateMarkersFromClusters(cls, 'gap');
    }
  });

  // Auto-generate reference markers when reference clusters change
  $effect(() => {
    const refCls = $referenceClusters;
    if (refCls.length > 0) {
      $referenceStretchMarkers = generateMarkersFromClusters(refCls, 'ref');
    } else {
      $referenceStretchMarkers = [];
    }
  });

  // --- Layout helpers ---

  /** Whether to show split view (reference loaded) */
  let hasRef = $derived($referenceClusters.length > 0);

  /** Get the pixel boundary between reference (top) and main (bottom) halves */
  function getSplitY(h: number): number {
    const plotH = h - MARGIN.t - MARGIN.b;
    return MARGIN.t + plotH * 0.5;
  }

  // --- Drawing ---

  function timeToPx(time: number): number {
    const w = canvasEl.width / window.devicePixelRatio - MARGIN.l - MARGIN.r;
    return MARGIN.l + ((time - _xRange[0]) / (_xRange[1] - _xRange[0])) * w;
  }

  function pxToTime(px: number): number {
    const w = canvasEl.width / window.devicePixelRatio - MARGIN.l - MARGIN.r;
    return _xRange[0] + ((px - MARGIN.l) / w) * (_xRange[1] - _xRange[0]);
  }

  /** Draw note regions, labels, and markers for a set of clusters/markers within a vertical band */
  function drawHalf(
    cls: Cluster[],
    markers: StretchMarker[],
    yTop: number,
    yBot: number,
    w: number,
    isRef: boolean,
  ) {
    const halfH = yBot - yTop;
    const regionColor = isRef ? COLORS.refNoteRegion : COLORS.noteRegion;
    const regionEdge = isRef ? COLORS.refNoteRegionEdge : COLORS.noteRegionEdge;
    const labelColor = isRef ? COLORS.refNoteLabel : COLORS.noteLabel;
    const markerColor = isRef ? COLORS.refMarker : COLORS.markerDefault;

    // Note region backgrounds
    for (let i = 0; i < cls.length; i++) {
      const x0 = timeToPx(cls[i].start_time);
      const x1 = timeToPx(cls[i].end_time);
      if (x1 < MARGIN.l || x0 > w - MARGIN.r) continue;

      ctx.fillStyle = regionColor;
      ctx.fillRect(x0, yTop, x1 - x0, halfH);
      ctx.strokeStyle = regionEdge;
      ctx.lineWidth = 0.5;
      ctx.strokeRect(x0, yTop, x1 - x0, halfH);
    }

    // Note labels
    const labelY = yTop + halfH * 0.4;
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < cls.length; i++) {
      const x0 = timeToPx(cls[i].start_time);
      const x1 = timeToPx(cls[i].end_time);
      if (x1 < MARGIN.l || x0 > w - MARGIN.r) continue;
      if (x1 - x0 > 18) {
        ctx.fillStyle = labelColor;
        ctx.fillText(`${i + 1}:${cls[i].note}`, (x0 + x1) / 2, labelY);
      }
    }

    // Markers
    for (const marker of markers) {
      const isMoved = !isRef && Math.abs(marker.currentTime - marker.originalTime) > 0.0001;
      const x = timeToPx(marker.currentTime);
      if (x < MARGIN.l || x > w - MARGIN.r) continue;

      // Ghost line (moved main markers only)
      if (isMoved) {
        const origX = timeToPx(marker.originalTime);
        if (origX >= MARGIN.l && origX <= w - MARGIN.r) {
          ctx.strokeStyle = COLORS.markerGhost;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(origX, yTop);
          ctx.lineTo(origX, yBot);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      // Main line
      ctx.strokeStyle = isMoved ? COLORS.markerMoved : markerColor;
      ctx.lineWidth = isMoved ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(x, yTop);
      ctx.lineTo(x, yBot);
      ctx.stroke();

      // Diamond handle
      const cy = yTop + halfH * 0.5;
      const s = MARKER_HANDLE_SIZE;
      ctx.fillStyle = isMoved ? COLORS.markerMoved : markerColor;
      ctx.beginPath();
      ctx.moveTo(x, cy - s);
      ctx.lineTo(x + s, cy);
      ctx.lineTo(x, cy + s);
      ctx.lineTo(x - s, cy);
      ctx.closePath();
      ctx.fill();

      // Delta label (moved main markers only)
      if (isMoved) {
        const deltaMs = (marker.currentTime - marker.originalTime) * 1000;
        const label = `${deltaMs > 0 ? '+' : ''}${deltaMs.toFixed(0)}ms`;
        ctx.fillStyle = COLORS.markerMoved;
        ctx.font = '9px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(label, x, yTop - 2);
      }

      // Side note labels
      if (marker.leftClusterIdx >= 0 && marker.leftClusterIdx < cls.length &&
          marker.rightClusterIdx >= 0 && marker.rightClusterIdx < cls.length) {
        const leftNote = cls[marker.leftClusterIdx].note;
        const rightNote = cls[marker.rightClusterIdx].note;
        ctx.fillStyle = COLORS.textDim;
        ctx.font = '8px sans-serif';
        ctx.textBaseline = 'top';
        ctx.textAlign = 'right';
        ctx.fillText(leftNote, x - 4, yBot + 1);
        ctx.textAlign = 'left';
        ctx.fillText(rightNote, x + 4, yBot + 1);
      }
    }
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

    const plotH = h - MARGIN.t - MARGIN.b;

    // Background
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    // Grid lines
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

    const cls = $clusters;
    const refCls = $referenceClusters;
    const showSplit = refCls.length > 0;

    if (showSplit) {
      // ---- SPLIT VIEW ----
      const splitY = getSplitY(h);
      const refTop = MARGIN.t;
      const refBot = splitY - 8;  // gap for split line
      const mainTop = splitY + 8;
      const mainBot = h - MARGIN.b;

      // Draw reference half (top)
      drawHalf(refCls, $referenceStretchMarkers, refTop, refBot, w, true);

      // Draw main half (bottom)
      drawHalf(cls, $stretchMarkers, mainTop, mainBot, w, false);

      // Split line
      ctx.strokeStyle = COLORS.splitLine;
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(MARGIN.l, splitY);
      ctx.lineTo(w - MARGIN.r, splitY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Labels
      ctx.fillStyle = COLORS.splitLabel;
      ctx.font = '9px sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText('REF', MARGIN.l - 6, splitY - 2);
      ctx.textBaseline = 'top';
      ctx.fillText('MAIN', MARGIN.l - 6, splitY + 2);

      // MIDI reference note bars (drawn in the main half)
      const midiData = $midiNotes;
      if (midiData.length > 0) {
        const mainHalfHeight = mainBot - mainTop;
        const midiRowTop = mainTop + mainHalfHeight * 0.70;
        const midiRowHeight = mainHalfHeight * 0.25;
        const midiFreqs = midiData.map(n => n.frequency);
        const minFreq = Math.min(...midiFreqs);
        const maxFreq = Math.max(...midiFreqs);
        const freqRange = maxFreq - minFreq;
        const freqToY = (freq: number): number => {
          if (freqRange < 1) return midiRowTop + midiRowHeight / 2;
          const ratio = (freq - minFreq) / freqRange;
          return midiRowTop + midiRowHeight - ratio * midiRowHeight;
        };

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
          ctx.strokeStyle = COLORS.midiLine;
          ctx.lineWidth = MIDI_LINE_HEIGHT;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.moveTo(Math.max(x0, MARGIN.l), y);
          ctx.lineTo(Math.min(x1, w - MARGIN.r), y);
          ctx.stroke();

          if (x1 - x0 > 18) {
            ctx.fillStyle = COLORS.midiText;
            ctx.font = '9px sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            ctx.fillText(mn.note_name, Math.max(x0, MARGIN.l) + 2, y - 3);
          }
        }

        // Also draw boundary lines across both halves
        if (midiData.length > 1) {
          ctx.strokeStyle = 'rgba(171,71,188,0.25)';
          ctx.lineWidth = 1;
          ctx.setLineDash([2, 3]);
          for (let i = 0; i < midiData.length - 1; i++) {
            const boundary = midiData[i].end_time;
            const x = timeToPx(boundary);
            if (x < MARGIN.l || x > w - MARGIN.r) continue;
            ctx.beginPath();
            ctx.moveTo(x, MARGIN.t);
            ctx.lineTo(x, h - MARGIN.b);
            ctx.stroke();
          }
          ctx.setLineDash([]);
        }
      }

      // Time correction curve in main half
      if ($showCorrectionCurve && $stretchMarkers.length > 0) {
        drawTimeCurve(cls, $stretchMarkers, mainTop, mainBot - mainTop, w);
      }

    } else {
      // ---- SINGLE VIEW (no reference) ----
      drawHalf(cls, $stretchMarkers, MARGIN.t, h - MARGIN.b, w, false);

      // MIDI reference pitch lines
      const midiData = $midiNotes;
      if (midiData.length > 0) {
        const midiFreqs = midiData.map(n => n.frequency);
        const minFreq = Math.min(...midiFreqs);
        const maxFreq = Math.max(...midiFreqs);
        const midiRowTop = MARGIN.t + plotH * 0.70;
        const midiRowHeight = plotH * 0.25;

        const freqRange = maxFreq - minFreq;
        const freqToY = (freq: number): number => {
          if (freqRange < 1) return midiRowTop + midiRowHeight / 2;
          const ratio = (freq - minFreq) / freqRange;
          return midiRowTop + midiRowHeight - ratio * midiRowHeight;
        };

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
          ctx.strokeStyle = COLORS.midiLine;
          ctx.lineWidth = MIDI_LINE_HEIGHT;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.moveTo(Math.max(x0, MARGIN.l), y);
          ctx.lineTo(Math.min(x1, w - MARGIN.r), y);
          ctx.stroke();

          if (x1 - x0 > 18) {
            ctx.fillStyle = COLORS.midiText;
            ctx.font = '9px sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            ctx.fillText(mn.note_name, Math.max(x0, MARGIN.l) + 2, y - 3);
          }
        }
      }

      // Time correction curve full height
      if ($showCorrectionCurve && $stretchMarkers.length > 0) {
        drawTimeCurve(cls, $stretchMarkers, MARGIN.t, plotH, w);
      }
    }

    // Playhead (full height)
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

    // Time axis label
    ctx.fillStyle = COLORS.textDim;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Time (s)', w / 2, h - 6);
  }

  function drawTimeCurve(cls: Cluster[], markers: StretchMarker[], areaTop: number, areaH: number, w: number) {
    const curveTop = areaTop + areaH * TIME_CURVE_TOP_FRAC;
    const curveH = areaH * TIME_CURVE_HEIGHT_FRAC;
    const baselineY = curveTop + curveH / 2;

    let keypoints: { src: number; tgt: number }[];

    if (!$dirtyStretchMarkers && $backendTimemap.length > 0) {
      keypoints = $backendTimemap.map(e => ({ src: e.source_s, tgt: e.target_s }));
    } else {
      const kpSet = new Map<number, number>();
      kpSet.set(0, 0);

      const movedMarkers = markers.filter(m => Math.abs(m.currentTime - m.originalTime) > 0.0001);
      const movedAdjacentLeft = new Set<number>();
      const movedAdjacentRight = new Set<number>();

      for (const m of movedMarkers) {
        kpSet.set(m.originalTime, m.currentTime);
        movedAdjacentLeft.add(m.leftClusterIdx);
        movedAdjacentRight.add(m.rightClusterIdx);
      }

      for (let i = 0; i < cls.length; i++) {
        if (!movedAdjacentRight.has(i)) {
          if (!kpSet.has(cls[i].start_time)) kpSet.set(cls[i].start_time, cls[i].start_time);
        }
        if (!movedAdjacentLeft.has(i)) {
          if (!kpSet.has(cls[i].end_time)) kpSet.set(cls[i].end_time, cls[i].end_time);
        }
      }

      const lastEnd = cls.length > 0 ? cls[cls.length - 1].end_time + 1 : 1;
      if (!kpSet.has(lastEnd)) kpSet.set(lastEnd, lastEnd);

      keypoints = Array.from(kpSet.entries())
        .map(([src, tgt]) => ({ src, tgt }))
        .sort((a, b) => a.src - b.src);
    }

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
      } else if (srcDur > 0.001) {
        dev = MAX_DEV;
      } else if (tgtDur > 0.001) {
        dev = -MAX_DEV;
      }
      dev = Math.max(-MAX_DEV, Math.min(MAX_DEV, dev));
      kpSegments.push({ tgtStart: keypoints[i - 1].tgt, tgtEnd: keypoints[i].tgt, dev });
      if (Math.abs(dev) > maxDev) maxDev = Math.abs(dev);
    }

    const scale = Math.max(maxDev * 1.3, 3.0);

    ctx.strokeStyle = COLORS.timeCurveBaseline;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(MARGIN.l, baselineY);
    ctx.lineTo(w - MARGIN.r, baselineY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = COLORS.timeCurveLine;
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText('Time', MARGIN.l - 6, baselineY);

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

    drawCurvePath();
    ctx.lineTo(w - MARGIN.r, baselineY);
    ctx.closePath();
    ctx.fillStyle = COLORS.timeCurveFill;
    ctx.fill();

    drawCurvePath();
    ctx.strokeStyle = COLORS.timeCurveLine;
    ctx.lineWidth = 1.5;
    ctx.stroke();
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

  function getMarkerAtPx(px: number, py: number): number | null {
    // Only allow interaction with main markers (not reference)
    const h = containerEl.getBoundingClientRect().height;
    const showSplit = $referenceClusters.length > 0;
    if (showSplit) {
      const splitY = getSplitY(h);
      if (py < splitY) return null;  // in reference half — no interaction
    }

    const markers = $stretchMarkers;
    for (let i = 0; i < markers.length; i++) {
      const x = timeToPx(markers[i].currentTime);
      if (Math.abs(px - x) < MARKER_HIT_THRESHOLD) return i;
    }
    return null;
  }

  function isInPlotArea(px: number, py: number): boolean {
    const rect = containerEl.getBoundingClientRect();
    return px > MARGIN.l && px < rect.width - MARGIN.r &&
           py > MARGIN.t && py < rect.height - MARGIN.b;
  }

  function clampMarker(markerIdx: number, time: number): number {
    const markers = $stretchMarkers;
    const minTime = markerIdx > 0
      ? markers[markerIdx - 1].currentTime + 0.005
      : 0.005;
    const maxTime = markerIdx < markers.length - 1
      ? markers[markerIdx + 1].currentTime - 0.005
      : Infinity;
    return Math.max(minTime, Math.min(maxTime, time));
  }

  function setupInteractions() {
    let mode: string | null = null;
    let startX = 0;
    let hasMoved = false;
    let dragMarkerIdx: number | null = null;
    let dragMarkerOrigTime = 0;
    let panStartXRange: [number, number] | null = null;

    canvasEl.addEventListener('mousedown', (e: MouseEvent) => {
      if (e.button !== 0) return;
      const rect = canvasEl.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      // Alt+click on marker → remove marker
      if (e.altKey && isInPlotArea(px, py)) {
        const markerIdx = getMarkerAtPx(px, py);
        if (markerIdx !== null) {
          const markers = [...$stretchMarkers];
          markers.splice(markerIdx, 1);
          $stretchMarkers = markers;
          $dirtyStretchMarkers = true;
          $selectedMarkerIdx = null;
          scheduleDraw();
          e.preventDefault();
          return;
        }
      }

      if (e.ctrlKey && e.shiftKey && isInPlotArea(px, py)) {
        mode = 'pan';
        startX = e.clientX;
        panStartXRange = [..._xRange] as [number, number];
        hasMoved = false;
        canvasEl.style.cursor = 'grabbing';
        e.preventDefault();
        return;
      }

      // Ctrl+click → add marker
      if (e.ctrlKey && isInPlotArea(px, py)) {
        const clickTime = pxToTime(px);
        const markers = [...$stretchMarkers];
        // Find insertion point (markers are sorted by currentTime)
        let insertIdx = markers.findIndex(m => m.currentTime > clickTime);
        if (insertIdx === -1) insertIdx = markers.length;
        // Determine adjacent cluster indices
        const cls = $clusters;
        let leftClusterIdx = -1;
        let rightClusterIdx = cls.length;
        for (let i = 0; i < cls.length; i++) {
          if (cls[i].end_time <= clickTime) leftClusterIdx = i;
          if (cls[i].start_time >= clickTime && rightClusterIdx === cls.length) rightClusterIdx = i;
        }
        const newMarker: StretchMarker = {
          id: `manual-${Date.now()}`,
          originalTime: clickTime,
          currentTime: clickTime,
          leftClusterIdx,
          rightClusterIdx,
        };
        markers.splice(insertIdx, 0, newMarker);
        $stretchMarkers = markers;
        $dirtyStretchMarkers = true;
        $selectedMarkerIdx = insertIdx;
        scheduleDraw();
        e.preventDefault();
        return;
      }

      const markerIdx = getMarkerAtPx(px, py);
      if (markerIdx !== null) {
        mode = 'marker-drag';
        dragMarkerIdx = markerIdx;
        dragMarkerOrigTime = $stretchMarkers[markerIdx].currentTime;
        startX = e.clientX;
        hasMoved = false;
        $selectedMarkerIdx = markerIdx;
        canvasEl.style.cursor = 'ew-resize';
        scheduleDraw();
        e.preventDefault();
        return;
      }

      if (isInPlotArea(px, py)) {
        $selectedMarkerIdx = null;
        scheduleDraw();
        const time = pxToTime(px);
        if (onSeek) onSeek(time);
        e.preventDefault();
      }
    });

    canvasEl.addEventListener('dblclick', (e: MouseEvent) => {
      const rect = canvasEl.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const markerIdx = getMarkerAtPx(px, py);
      if (markerIdx !== null) {
        const markers = [...$stretchMarkers];
        markers[markerIdx] = { ...markers[markerIdx], currentTime: markers[markerIdx].originalTime };
        $stretchMarkers = markers;
        $dirtyStretchMarkers = true;
        scheduleDraw();
        onEditComplete?.(markerIdx);
        e.preventDefault();
      }
    });

    window.addEventListener('mousemove', (e: MouseEvent) => {
      if (!mode) {
        const rect = canvasEl.getBoundingClientRect();
        const px = e.clientX - rect.left;
        const py = e.clientY - rect.top;
        const markerIdx = getMarkerAtPx(px, py);
        if (markerIdx !== null) {
          canvasEl.style.cursor = 'ew-resize';
        } else if (e.ctrlKey && e.shiftKey && isInPlotArea(px, py)) {
          canvasEl.style.cursor = 'grab';
        } else {
          canvasEl.style.cursor = 'default';
        }
        return;
      }

      if (mode === 'marker-drag' && dragMarkerIdx !== null) {
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;

        const rect = canvasEl.getBoundingClientRect();
        const plotW = rect.width - MARGIN.l - MARGIN.r;
        const timePerPx = (_xRange[1] - _xRange[0]) / plotW;
        const deltaTime = dx * timePerPx;
        const newTime = clampMarker(dragMarkerIdx, dragMarkerOrigTime + deltaTime);

        const markers = [...$stretchMarkers];
        markers[dragMarkerIdx] = { ...markers[dragMarkerIdx], currentTime: newTime };
        $stretchMarkers = markers;
        $dirtyStretchMarkers = true;
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
      if (mode === 'marker-drag') {
        canvasEl.style.cursor = '';
        if (hasMoved && dragMarkerIdx !== null) onEditComplete?.(dragMarkerIdx);
      } else if (mode === 'pan') {
        canvasEl.style.cursor = '';
      }
      mode = null;
      dragMarkerIdx = null;
      panStartXRange = null;
      hasMoved = false;
    });

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

  // --- Reactive drawing ---

  $effect(() => {
    void $clusters;
    void $selectedIndices;
    void $stretchMarkers;
    void $referenceClusters;
    void $referenceStretchMarkers;
    void $midiNotes;
    void $showCorrectionCurve;
    void $backendTimemap;
    if (_mounted) scheduleDraw();
  });

  $effect(() => {
    void $waveformReset;
    _pendingZoomReset = true;
  });

  $effect(() => {
    const cls = $clusters;
    const refCls2 = $referenceClusters;
    const midiNts = $midiNotes;
    if (cls.length > 0 || refCls2.length > 0 || midiNts.length > 0) {
      const mainMax = cls.length > 0 ? Math.max(...cls.map(c => c.end_time)) : 0;
      const refMax = refCls2.length > 0 ? Math.max(...refCls2.map(c => c.end_time)) : 0;
      const midiMax = midiNts.length > 0 ? Math.max(...midiNts.map(n => n.end_time)) : 0;
      const maxEnd = Math.max(mainMax, refMax, midiMax);
      _fullXRange = [0, maxEnd * 1.05];

      if (_pendingZoomReset) {
        _pendingZoomReset = false;
        setXRange([..._fullXRange] as [number, number]);
      }
    }
  });

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
    <span class="zoom-hint">Scroll to zoom · Ctrl+Shift+Drag to pan · Drag markers to stretch · Double-click marker to reset · Ctrl+Click to add marker · Alt+Click to remove marker</span>
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
