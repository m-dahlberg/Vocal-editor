<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import {
    clusters, times, frequencies, midiNotes,
    selectedIdx, selectedIndices, showMidi, showCorrectionCurve,
    activeTab, viewXRange
  } from '$lib/stores/appState';
  import { NOTE_FREQ_MAP, getYRange, clusterDisplayFreq, boxHeight } from '$lib/utils/pitchMath';
  import { play as sinePlay, updateFrequency as sineUpdate, stop as sineStop } from '$lib/utils/sinePlayer';
  import ProcessingOverlay from './ProcessingOverlay.svelte';
  import type { Cluster, MidiNote } from '$lib/utils/types';

  interface Props {
    onClusterSelect: (idx: number, cluster: Cluster) => void;
    onClusterDrag: (idx: number, newShift: number) => void;
    onClusterResize: (idx: number) => void;
    onDrawBox: (start: number, end: number) => void;
    onClusterSmoothing: (idx: number, smoothing: number) => void;
    onClusterRampDrag: (idx: number, rampIn: number, rampOut: number) => void;
    onResetView: () => void;
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
  }

  let {
    onClusterSelect, onClusterDrag, onClusterResize,
    onDrawBox, onClusterSmoothing, onClusterRampDrag,
    onResetView, syncWaveform, onSeek
  }: Props = $props();

  let plotEl: HTMLDivElement;
  let Plotly: any = null;

  // Internal view state
  let _xRange: [number, number] = [0, 10];
  let _yRange: [number, number] = [75, 600];
  let _fullXRange: [number, number] = [0, 10];
  let _fullYRange: [number, number] = [75, 600];

  /** Update _xRange and push to shared store so the other tab stays in sync. */
  function setXRange(range: [number, number]) {
    _xRange = range;
    $viewXRange = range;
  }
  let _correctionCurveTimes: (number | null)[] = [];
  let _correctionCurveCents: (number | null)[] = [];
  let _playheadSvgPath: SVGPathElement | null = null;
  let _sineTimeout: ReturnType<typeof setTimeout> | null = null;
  let _dragGhosts: HTMLDivElement[] = [];
  let _playheadTime = 0;
  let _interacting = false;
  let _suppressStoreEffect = false;
  let _redrawScheduled = false;

  const COLORS = {
    pitchLine: '#2E86AB',
    correctionCurve: '#FFA500',
    noteBox: 'rgba(255,140,66,0.25)',
    noteBoxEdge: '#D96C2C',
    noteSelected: 'rgba(233,69,96,0.35)',
    noteSelEdge: '#e94560',
    midi: '#06D6A0',
    playhead: '#e94560',
  };

  function buildLayout(xRange: [number, number], yRange: [number, number]) {
    const visibleNotes = NOTE_FREQ_MAP.filter(([, f]) => f >= yRange[0] && f <= yRange[1]);
    return {
      paper_bgcolor: '#1a1a2e',
      plot_bgcolor: '#16213e',
      font: { color: '#e0e0e0', size: 11 },
      margin: { l: 60, r: 60, t: 30, b: 50 },
      xaxis: {
        range: xRange,
        title: { text: 'Time (s)', font: { size: 11 } },
        gridcolor: '#2a2a4a',
        zerolinecolor: '#2a2a4a',
        tickfont: { size: 10 },
        fixedrange: true,
      },
      yaxis: {
        range: yRange,
        tickvals: visibleNotes.map(([, f]) => f),
        ticktext: visibleNotes.map(([n]) => n),
        gridcolor: '#2a2a4a',
        zerolinecolor: '#2a2a4a',
        tickfont: { size: 10 },
        fixedrange: true,
      },
      yaxis2: {
        title: { text: 'Correction (cents)', font: { size: 10 } },
        overlaying: 'y',
        side: 'right',
        range: [-300, 300],
        zeroline: true,
        zerolinecolor: '#FFA50044',
        zerolinewidth: 1,
        gridcolor: 'rgba(255,165,0,0.1)',
        tickfont: { size: 9, color: '#FFA500' },
        fixedrange: true,
        showgrid: false,
      },
      showlegend: true,
      legend: {
        x: 1, xanchor: 'right', y: 1,
        bgcolor: 'rgba(22,33,62,0.8)',
        bordercolor: '#2a2a4a',
        borderwidth: 1,
        font: { size: 10 },
      },
      dragmode: false,
      hovermode: 'closest',
    };
  }

  function buildTraces(
    t: number[], f: (number | null)[], cls: Cluster[], midi: MidiNote[],
    selIndices: Set<number>, showMidiFlag: boolean, showCorrFlag: boolean
  ) {
    const traces: any[] = [];

    // Pitch line
    traces.push({
      x: t, y: f,
      type: 'scatter', mode: 'lines',
      name: 'Detected Pitch',
      line: { color: COLORS.pitchLine, width: 1.5 },
      hoverinfo: 'skip',
    });

    // MIDI reference
    if (midi && midi.length > 0) {
      const mx: (number | null)[] = [], my: (number | null)[] = [];
      if (showMidiFlag) {
        for (const n of midi) {
          mx.push(n.start_time, n.end_time, null);
          my.push(n.frequency, n.frequency, null);
        }
      }
      traces.push({
        x: mx, y: my,
        type: 'scatter', mode: 'lines',
        name: 'MIDI Reference',
        line: { color: COLORS.midi, width: 2 },
        hoverinfo: 'skip',
      });
    }

    // Correction curve
    traces.push({
      x: showCorrFlag ? _correctionCurveTimes : [],
      y: showCorrFlag ? _correctionCurveCents : [],
      type: 'scatter', mode: 'lines',
      name: 'Correction (cents)',
      line: { color: COLORS.correctionCurve, width: 2 },
      yaxis: 'y2',
      hoverinfo: 'skip',
    });

    // Note boxes
    const spacing = (_fullYRange[1] - _fullYRange[0]) / 30;
    const h = spacing * 0.8;

    for (let i = 0; i < cls.length; i++) {
      const c = cls[i];
      const isSelected = selIndices.has(i);
      const freq = clusterDisplayFreq(c);

      traces.push({
        x: [c.start_time, c.end_time, c.end_time, c.start_time, c.start_time],
        y: [freq - h/2, freq - h/2, freq + h/2, freq + h/2, freq - h/2],
        type: 'scatter', mode: 'lines',
        fill: 'toself',
        fillcolor: isSelected ? COLORS.noteSelected : COLORS.noteBox,
        line: { color: isSelected ? COLORS.noteSelEdge : COLORS.noteBoxEdge, width: isSelected ? 2 : 1 },
        name: '', showlegend: false,
        hoverinfo: 'skip',
        customdata: [i, i, i, i, i],
      });

      traces.push({
        x: [(c.start_time + c.end_time) / 2], y: [freq],
        type: 'scatter', mode: 'text',
        text: [`${i+1}:${c.note}`],
        textfont: { size: 9, color: isSelected ? '#fff' : '#ccc' },
        showlegend: false, hoverinfo: 'skip', name: '',
      });
    }

    // Playhead
    traces.push({
      x: [_playheadTime, _playheadTime], y: _yRange,
      type: 'scatter', mode: 'lines',
      name: 'Playhead',
      line: { color: COLORS.playhead, width: 1.5, dash: 'dot' },
      hoverinfo: 'skip', showlegend: false,
    });

    return traces;
  }

  function _getClusterAtMouse(e: MouseEvent): number | null {
    const rect = plotEl.getBoundingClientRect();
    const layout = (plotEl as any)._fullLayout;
    if (!layout) return null;
    const x = layout.xaxis.p2d(e.clientX - rect.left - layout.margin.l);
    const y = layout.yaxis.p2d(e.clientY - rect.top - layout.margin.t);
    const h = boxHeight(_fullYRange);
    const cls = $clusters;
    for (let i = cls.length - 1; i >= 0; i--) {
      const c = cls[i];
      const freq = clusterDisplayFreq(c);
      if (x >= c.start_time && x <= c.end_time && y >= freq - h/2 && y <= freq + h/2) return i;
    }
    return null;
  }

  function _getResizeEdge(e: MouseEvent): { clusterIdx: number; edge: 'left' | 'right' } | null {
    const rect = plotEl.getBoundingClientRect();
    const layout = (plotEl as any)._fullLayout;
    if (!layout) return null;
    const px = e.clientX - rect.left - layout.margin.l;
    const y = layout.yaxis.p2d(e.clientY - rect.top - layout.margin.t);
    const resizeThresholdPx = 10;
    const h = boxHeight(_fullYRange);
    const cls = $clusters;

    for (let i = cls.length - 1; i >= 0; i--) {
      const c = cls[i];
      const freq = clusterDisplayFreq(c);
      if (y < freq - h/2 || y > freq + h/2) continue;
      const leftPx = layout.xaxis.d2p(c.start_time);
      const rightPx = layout.xaxis.d2p(c.end_time);
      if (Math.abs(px - leftPx) < resizeThresholdPx) return { clusterIdx: i, edge: 'left' };
      if (Math.abs(px - rightPx) < resizeThresholdPx) return { clusterIdx: i, edge: 'right' };
    }
    return null;
  }

  function _isInPlotArea(e: MouseEvent): boolean {
    const rect = plotEl.getBoundingClientRect();
    const layout = (plotEl as any)._fullLayout;
    if (!layout) return false;
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    return px > layout.margin.l && px < rect.width - layout.margin.r &&
           py > layout.margin.t && py < rect.height - layout.margin.b;
  }

  function _boxTraceIndex(clusterIdx: number): number {
    const hasMidi = $midiNotes.length > 0 ? 1 : 0;
    return 2 + hasMidi + clusterIdx * 2;
  }

  function _findPlayheadSvg() {
    if (!plotEl) return;
    const svg = plotEl.querySelector('.plotly .main-svg');
    if (!svg) return;
    const paths = svg.querySelectorAll('.scatterlayer .trace:last-child path.js-line');
    if (paths && paths.length > 0) {
      _playheadSvgPath = paths[0] as SVGPathElement;
    }
  }

  function _redrawImmediate() {
    if (!Plotly || !plotEl) return;
    Plotly.react(plotEl,
      buildTraces($times, $frequencies, $clusters, $midiNotes, $selectedIndices, $showMidi, $showCorrectionCurve),
      buildLayout(_xRange, _yRange),
      { responsive: true, displayModeBar: false }
    );
    Plotly.relayout(plotEl, { shapes: [] });
    _findPlayheadSvg();
  }

  function _redraw() {
    if (_redrawScheduled) return;
    _redrawScheduled = true;
    requestAnimationFrame(() => {
      _redrawScheduled = false;
      _redrawImmediate();
    });
  }

  function _redrawSync() {
    _redrawScheduled = false;
    _redrawImmediate();
  }

  function _redrawDragBox(clusterIdx: number) {
    const h = boxHeight(_fullYRange);
    const c = $clusters[clusterIdx];
    const freq = clusterDisplayFreq(c);
    const boxIdx = _boxTraceIndex(clusterIdx);
    const labelIdx = boxIdx + 1;

    Plotly.restyle(plotEl,
      { y: [[freq - h/2, freq - h/2, freq + h/2, freq + h/2, freq - h/2]] },
      [boxIdx]
    );
    Plotly.restyle(plotEl, { y: [[freq]] }, [labelIdx]);
  }

  function selectCluster(idx: number) {
    $selectedIndices = new Set([idx]);
    $selectedIdx = idx;
    _redrawSync();
    onClusterSelect(idx, $clusters[idx]);
  }

  function toggleCluster(idx: number) {
    const s = new Set($selectedIndices);
    if (s.has(idx)) s.delete(idx); else s.add(idx);
    $selectedIndices = s;
    const first = s.size > 0 ? s.values().next().value! : null;
    $selectedIdx = first;
    _redrawSync();
    if (first !== null) onClusterSelect(first, $clusters[first]);
  }

  function selectClusters(idxArray: number[]) {
    $selectedIndices = new Set(idxArray);
    $selectedIdx = idxArray.length > 0 ? idxArray[0] : null;
    _redrawSync();
    if (idxArray.length > 0) onClusterSelect(idxArray[0], $clusters[idxArray[0]]);
  }

  function _setupInteractions() {
    let mode: string | null = null;
    let startX: number | null = null, startY: number | null = null;
    let dragIdx: number | null = null, startShift: number | null = null, startSmoothing: number | null = null;
    let resizeData: any = null;
    let drawStartTime: number | null = null;
    let panStartXRange: [number, number] | null = null, panStartYRange: [number, number] | null = null;
    let dragStartYRange: [number, number] | null = null;
    let hasMoved = false;
    let rampDragData: any = null;
    let _multiDragStartShifts: Map<number, number> | null = null;
    let _currentSemitoneDelta = 0;
    let _selectStartTime: number | null = null;
    let _selectStartFreq: number | null = null;

    plotEl.addEventListener('mousedown', (e: MouseEvent) => {
      if (e.button !== 0) return;

      // Alt+empty → draw-box
      if (e.altKey && _isInPlotArea(e)) {
        mode = 'draw-box';
        const rect = plotEl.getBoundingClientRect();
        const layout = (plotEl as any)._fullLayout;
        if (!layout) return;
        drawStartTime = layout.xaxis.p2d(e.clientX - rect.left - layout.margin.l);
        startX = e.clientX;
        hasMoved = false;
        plotEl.style.cursor = 'crosshair';
        e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
        return;
      }

      // Ctrl+Shift+empty → pan
      if (e.ctrlKey && e.shiftKey && _isInPlotArea(e)) {
        const clusterIdx = _getClusterAtMouse(e);
        if (clusterIdx === null) {
          mode = 'pan';
          startX = e.clientX; startY = e.clientY;
          panStartXRange = [..._xRange] as [number, number];
          panStartYRange = [..._yRange] as [number, number];
          hasMoved = false;
          plotEl.style.cursor = 'grabbing';
          e.preventDefault();
          return;
        }
      }

      // Ctrl+edge → ramp-drag
      if (e.ctrlKey) {
        const resizeEdge = _getResizeEdge(e);
        if (resizeEdge) {
          mode = 'ramp-drag';
          _interacting = true;
          const c = $clusters[resizeEdge.clusterIdx];
          rampDragData = {
            clusterIdx: resizeEdge.clusterIdx,
            edge: resizeEdge.edge,
            startX: e.clientX,
            originalRampIn: c.ramp_in_ms || 100,
            originalRampOut: c.ramp_out_ms || 100,
          };
          hasMoved = false;
          e.preventDefault();
          selectCluster(resizeEdge.clusterIdx);
          return;
        }
        // Ctrl+body → smooth-note
        const ctrlClusterIdx = _getClusterAtMouse(e);
        if (ctrlClusterIdx !== null) {
          mode = 'smooth-note';
          _interacting = true;
          dragIdx = ctrlClusterIdx;
          startY = e.clientY;
          startSmoothing = $clusters[dragIdx].smoothing_percent || 0;
          hasMoved = false;
          e.preventDefault();
          selectCluster(dragIdx);
          return;
        }
      }

      // Edge → resize-box
      const resizeEdge = _getResizeEdge(e);
      if (resizeEdge) {
        mode = 'resize-box';
        _interacting = true;
        const c = $clusters[resizeEdge.clusterIdx];
        resizeData = {
          clusterIdx: resizeEdge.clusterIdx,
          edge: resizeEdge.edge,
          originalStart: c.start_time,
          originalEnd: c.end_time,
        };
        startX = e.clientX;
        hasMoved = false;
        e.preventDefault();
        selectCluster(resizeEdge.clusterIdx);

        // Create ghost overlay for resize
        const layout = (plotEl as any)._fullLayout;
        if (layout) {
          const h = boxHeight(_fullYRange);
          const freq = clusterDisplayFreq(c);
          const x0px = layout.xaxis.d2p(c.start_time) + layout.margin.l;
          const x1px = layout.xaxis.d2p(c.end_time) + layout.margin.l;
          const y0px = layout.yaxis.d2p(freq + h / 2) + layout.margin.t;
          const y1px = layout.yaxis.d2p(freq - h / 2) + layout.margin.t;
          const ghost = document.createElement('div');
          ghost.style.cssText = `position:absolute;left:${x0px}px;top:${y0px}px;width:${x1px - x0px}px;height:${y1px - y0px}px;background:rgba(233,69,96,0.35);border:2px solid #e94560;pointer-events:none;z-index:100;box-sizing:border-box;`;
          ghost.dataset.startLeft = String(x0px);
          ghost.dataset.startWidth = String(x1px - x0px);
          plotEl.appendChild(ghost);
          _dragGhosts.push(ghost);
        }
        return;
      }

      // Shift+body → toggle
      const clusterIdx = _getClusterAtMouse(e);
      if (e.shiftKey && clusterIdx !== null) {
        toggleCluster(clusterIdx);
        e.preventDefault();
        return;
      }

      // Body → drag-note
      if (clusterIdx !== null) {
        if (!$selectedIndices.has(clusterIdx)) {
          selectCluster(clusterIdx);
        }
        mode = 'drag-note';
        _interacting = true;
        dragIdx = clusterIdx;
        startY = e.clientY;
        dragStartYRange = [..._yRange] as [number, number];
        hasMoved = false;
        e.preventDefault();

        _multiDragStartShifts = new Map();
        for (const idx of $selectedIndices) {
          _multiDragStartShifts.set(idx, $clusters[idx].pitch_shift_semitones);
        }
        startShift = $clusters[dragIdx].pitch_shift_semitones;

        // Create ghost overlay divs for each selected cluster
        const layout = (plotEl as any)._fullLayout;
        if (layout) {
          const plotRect = plotEl.getBoundingClientRect();
          const h = boxHeight(_fullYRange);
          for (const idx of $selectedIndices) {
            const c = $clusters[idx];
            const freq = clusterDisplayFreq(c);
            const x0px = layout.xaxis.d2p(c.start_time) + layout.margin.l;
            const x1px = layout.xaxis.d2p(c.end_time) + layout.margin.l;
            const y0px = layout.yaxis.d2p(freq + h / 2) + layout.margin.t;
            const y1px = layout.yaxis.d2p(freq - h / 2) + layout.margin.t;
            const ghost = document.createElement('div');
            ghost.style.cssText = `position:absolute;left:${x0px}px;top:${y0px}px;width:${x1px - x0px}px;height:${y1px - y0px}px;background:rgba(233,69,96,0.35);border:2px solid #e94560;pointer-events:none;z-index:100;box-sizing:border-box;`;
            ghost.dataset.startTop = String(y0px);
            plotEl.appendChild(ghost);
            _dragGhosts.push(ghost);
          }
        }

        // Sine preview after delay
        const shiftFactor = Math.pow(2, startShift / 12);
        const correctedFreq = $clusters[dragIdx].mean_freq * shiftFactor;
        const capturedIdx = clusterIdx;
        _sineTimeout = setTimeout(() => {
          if (mode === 'drag-note' && dragIdx === capturedIdx) {
            sinePlay(correctedFreq);
          }
        }, 300);
        return;
      }

      // Empty space → rubber-band select
      if (_isInPlotArea(e)) {
        mode = 'select';
        startX = e.clientX; startY = e.clientY;
        const rect = plotEl.getBoundingClientRect();
        const layout = (plotEl as any)._fullLayout;
        if (layout) {
          _selectStartTime = layout.xaxis.p2d(e.clientX - rect.left - layout.margin.l);
          _selectStartFreq = layout.yaxis.p2d(e.clientY - rect.top - layout.margin.t);
        }
        hasMoved = false;
        e.preventDefault();
      }
    });

    window.addEventListener('mousemove', (e: MouseEvent) => {
      if (!mode) return;

      if (mode === 'drag-note' && dragIdx !== null && startY !== null && startShift !== null && dragStartYRange) {
        const dy = startY - e.clientY;
        if (Math.abs(dy) > 2) hasMoved = true;
        if (!hasMoved) return;
        const plotH = plotEl.clientHeight - 80;
        const freqPerPx = (dragStartYRange[1] - dragStartYRange[0]) / plotH;
        const freqDelta = dy * freqPerPx;
        const baseCents = 1200 * Math.log2(
          ($clusters[dragIdx].mean_freq + freqDelta) / $clusters[dragIdx].mean_freq
        );
        _currentSemitoneDelta = baseCents / 100;

        // Compute sine frequency from original data + delta (no store write)
        const currentShift = startShift + _currentSemitoneDelta;
        const shiftFactor = Math.pow(2, currentShift / 12);
        sineUpdate($clusters[dragIdx].mean_freq * shiftFactor);

        // Move ghost overlays via CSS — zero Plotly overhead
        const dy_px = startY - e.clientY;
        for (const ghost of _dragGhosts) {
          const startTop = parseFloat(ghost.dataset.startTop!);
          ghost.style.top = `${startTop - dy_px}px`;
        }
      } else if (mode === 'smooth-note' && dragIdx !== null && startY !== null && startSmoothing !== null) {
        const dy = startY - e.clientY;
        if (Math.abs(dy) > 2) hasMoved = true;
        if (!hasMoved) return;
        const SMOOTH_PX_RANGE = 200;
        const newSmoothing = Math.max(0, Math.min(100, startSmoothing + (dy / SMOOTH_PX_RANGE) * 100));
        const updatedClusters = [...$clusters];
        updatedClusters[dragIdx] = { ...updatedClusters[dragIdx], smoothing_percent: newSmoothing };
        $clusters = updatedClusters;
        onClusterSmoothing(dragIdx, newSmoothing);
      } else if (mode === 'ramp-drag' && rampDragData) {
        const dx = e.clientX - rampDragData.startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;
        const layout = (plotEl as any)._fullLayout;
        if (!layout) return;
        const plotW = plotEl.clientWidth - layout.margin.l - layout.margin.r;
        const xSpan = _xRange[1] - _xRange[0];
        const deltaMs = (dx / plotW) * xSpan * 1000 * 3;
        const updatedClusters = [...$clusters];
        const c = { ...updatedClusters[rampDragData.clusterIdx] };
        if (rampDragData.edge === 'left') {
          c.ramp_in_ms = Math.max(0, rampDragData.originalRampIn - deltaMs);
        } else {
          c.ramp_out_ms = Math.max(0, rampDragData.originalRampOut + deltaMs);
        }
        updatedClusters[rampDragData.clusterIdx] = c;
        $clusters = updatedClusters;
      } else if (mode === 'resize-box' && resizeData && startX !== null) {
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;

        // Move ghost overlay via CSS
        const ghost = _dragGhosts[0];
        if (ghost) {
          const startLeft = parseFloat(ghost.dataset.startLeft!);
          const startWidth = parseFloat(ghost.dataset.startWidth!);
          if (resizeData.edge === 'left') {
            ghost.style.left = `${startLeft + dx}px`;
            ghost.style.width = `${startWidth - dx}px`;
          } else {
            ghost.style.width = `${startWidth + dx}px`;
          }
        }
      } else if (mode === 'draw-box' && startX !== null && drawStartTime !== null) {
        if (Math.abs(e.clientX - startX) > 2) hasMoved = true;
        if (!hasMoved) return;
        const rect = plotEl.getBoundingClientRect();
        const layout = (plotEl as any)._fullLayout;
        if (layout) {
          const px = e.clientX - rect.left - layout.margin.l;
          const currentTime = layout.xaxis.p2d(px);
          const x0 = Math.min(drawStartTime, currentTime);
          const x1 = Math.max(drawStartTime, currentTime);
          Plotly.relayout(plotEl, {
            shapes: [{
              type: 'rect', xref: 'x', yref: 'y',
              x0, x1, y0: _yRange[0], y1: _yRange[1],
              fillcolor: 'rgba(255,140,66,0.12)',
              line: { color: '#D96C2C', width: 1.5, dash: 'dot' },
              layer: 'above',
            }],
          });
        }
        plotEl.style.cursor = 'crosshair';
      } else if (mode === 'select' && startX !== null && startY !== null && _selectStartTime !== null && _selectStartFreq !== null) {
        const dx2 = e.clientX - startX;
        const dy2 = e.clientY - startY;
        if (Math.abs(dx2) > 2 || Math.abs(dy2) > 2) hasMoved = true;
        if (!hasMoved) return;
        const rectS = plotEl.getBoundingClientRect();
        const layoutS = (plotEl as any)._fullLayout;
        if (layoutS) {
          const pxS = e.clientX - rectS.left - layoutS.margin.l;
          const pyS = e.clientY - rectS.top - layoutS.margin.t;
          const currentTime = layoutS.xaxis.p2d(pxS);
          const currentFreq = layoutS.yaxis.p2d(pyS);
          const x0 = Math.min(_selectStartTime, currentTime);
          const x1 = Math.max(_selectStartTime, currentTime);
          const y0 = Math.min(_selectStartFreq, currentFreq);
          const y1 = Math.max(_selectStartFreq, currentFreq);
          Plotly.relayout(plotEl, {
            shapes: [{
              type: 'rect', xref: 'x', yref: 'y',
              x0, x1, y0, y1,
              fillcolor: 'rgba(255,255,255,0.06)',
              line: { color: 'rgba(255,255,255,0.5)', width: 1, dash: 'dash' },
              layer: 'above',
            }],
          });
        }
      } else if (mode === 'pan' && startX !== null && startY !== null && panStartXRange && panStartYRange) {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        if (Math.abs(dx) > 2 || Math.abs(dy) > 2) hasMoved = true;
        if (!hasMoved) return;
        const layout = (plotEl as any)._fullLayout;
        if (!layout) return;
        const plotW = plotEl.clientWidth - layout.margin.l - layout.margin.r;
        const xSpan = panStartXRange[1] - panStartXRange[0];
        const xDelta = -(dx / plotW) * xSpan;
        let x0 = panStartXRange[0] + xDelta;
        let x1 = panStartXRange[1] + xDelta;
        if (x0 < _fullXRange[0]) { x1 += _fullXRange[0] - x0; x0 = _fullXRange[0]; }
        if (x1 > _fullXRange[1]) { x0 -= x1 - _fullXRange[1]; x1 = _fullXRange[1]; }

        const plotH = plotEl.clientHeight - layout.margin.t - layout.margin.b;
        const ySpan = panStartYRange[1] - panStartYRange[0];
        const yDelta = (dy / plotH) * ySpan;
        let y0 = panStartYRange[0] + yDelta;
        let y1 = panStartYRange[1] + yDelta;
        if (y0 < _fullYRange[0] * 0.9) { y1 += _fullYRange[0] * 0.9 - y0; y0 = _fullYRange[0] * 0.9; }
        if (y1 > _fullYRange[1] * 1.1) { y0 -= y1 - _fullYRange[1] * 1.1; y1 = _fullYRange[1] * 1.1; }

        setXRange([x0, x1]);
        _yRange = [y0, y1];
        Plotly.relayout(plotEl, { 'xaxis.range': _xRange, 'yaxis.range': _yRange });
        syncWaveform(_xRange, _fullXRange[1]);
      }
    });

    window.addEventListener('mouseup', (e: MouseEvent) => {
      if (_sineTimeout) { clearTimeout(_sineTimeout); _sineTimeout = null; }
      sineStop();

      if (mode === 'drag-note') {
        // Remove ghost overlays
        for (const ghost of _dragGhosts) ghost.remove();
        _dragGhosts = [];

        if (hasMoved && _multiDragStartShifts) {
          // Commit drag delta to store once on mouseup
          const updatedClusters = [...$clusters];
          for (const [idx, origShift] of _multiDragStartShifts) {
            updatedClusters[idx] = { ...updatedClusters[idx], pitch_shift_semitones: origShift + _currentSemitoneDelta };
          }
          $clusters = updatedClusters;

          const capturedIndices = Array.from($selectedIndices);
          requestAnimationFrame(() => {
            for (const idx of capturedIndices) {
              onClusterDrag(idx, $clusters[idx].pitch_shift_semitones);
            }
          });
        }
        _currentSemitoneDelta = 0;
        dragStartYRange = null;
        _multiDragStartShifts = null;
      } else if (mode === 'smooth-note') {
        if (hasMoved && dragIdx !== null) {
          const capturedIdx = dragIdx;
          const capturedSmoothing = $clusters[dragIdx].smoothing_percent;
          requestAnimationFrame(() => onClusterSmoothing(capturedIdx, capturedSmoothing));
        }
        startSmoothing = null;
      } else if (mode === 'ramp-drag') {
        if (hasMoved && rampDragData) {
          const capturedIdx = rampDragData.clusterIdx;
          const c = $clusters[capturedIdx];
          requestAnimationFrame(() => onClusterRampDrag(capturedIdx, c.ramp_in_ms, c.ramp_out_ms));
        }
        rampDragData = null;
      } else if (mode === 'resize-box') {
        // Remove ghost overlay
        for (const ghost of _dragGhosts) ghost.remove();
        _dragGhosts = [];

        if (hasMoved && resizeData && startX !== null) {
          // Commit the resize to the store
          const layout = (plotEl as any)._fullLayout;
          if (layout) {
            const rect = plotEl.getBoundingClientRect();
            const px = e.clientX - rect.left - layout.margin.l;
            const currentTime = layout.xaxis.p2d(px);
            const updatedClusters = [...$clusters];
            const c = { ...updatedClusters[resizeData.clusterIdx] };

            if (resizeData.edge === 'left') {
              let newStart = currentTime;
              if (newStart >= c.end_time) newStart = c.end_time - 0.01;
              if (resizeData.clusterIdx > 0) {
                const prev = updatedClusters[resizeData.clusterIdx - 1];
                if (newStart < prev.end_time) newStart = prev.end_time;
              }
              c.start_time = Math.max(0, newStart);
            } else {
              let newEnd = currentTime;
              if (newEnd <= c.start_time) newEnd = c.start_time + 0.01;
              if (resizeData.clusterIdx < updatedClusters.length - 1) {
                const next = updatedClusters[resizeData.clusterIdx + 1];
                if (newEnd > next.start_time) newEnd = next.start_time;
              }
              c.end_time = newEnd;
            }
            c.duration_ms = (c.end_time - c.start_time) * 1000;
            updatedClusters[resizeData.clusterIdx] = c;
            $clusters = updatedClusters;
          }
          onClusterResize(resizeData.clusterIdx);
        }
        resizeData = null;
      } else if (mode === 'draw-box') {
        if (hasMoved && drawStartTime !== null) {
          const rect = plotEl.getBoundingClientRect();
          const layout = (plotEl as any)._fullLayout;
          if (layout) {
            const px = e.clientX - rect.left - layout.margin.l;
            const drawEndTime = layout.xaxis.p2d(px);
            const start = Math.min(drawStartTime, drawEndTime);
            const end = Math.max(drawStartTime, drawEndTime);
            onDrawBox(start, end);
          }
        }
        Plotly.relayout(plotEl, { shapes: [] });
        drawStartTime = null;
        plotEl.style.cursor = '';
      } else if (mode === 'select') {
        if (hasMoved && _selectStartTime !== null && _selectStartFreq !== null) {
          const rectS = plotEl.getBoundingClientRect();
          const layoutS = (plotEl as any)._fullLayout;
          if (layoutS) {
            const pxS = e.clientX - rectS.left - layoutS.margin.l;
            const pyS = e.clientY - rectS.top - layoutS.margin.t;
            const endTime = layoutS.xaxis.p2d(pxS);
            const endFreq = layoutS.yaxis.p2d(pyS);
            const selX0 = Math.min(_selectStartTime, endTime);
            const selX1 = Math.max(_selectStartTime, endTime);
            const selY0 = Math.min(_selectStartFreq, endFreq);
            const selY1 = Math.max(_selectStartFreq, endFreq);

            const h = boxHeight(_fullYRange);
            const intersecting: number[] = [];
            const cls = $clusters;
            for (let i = 0; i < cls.length; i++) {
              const c = cls[i];
              const freq = clusterDisplayFreq(c);
              const boxY0 = freq - h / 2;
              const boxY1 = freq + h / 2;
              if (c.start_time <= selX1 && c.end_time >= selX0 && boxY0 <= selY1 && boxY1 >= selY0) {
                intersecting.push(i);
              }
            }
            if (intersecting.length > 0) {
              selectClusters(intersecting);
            } else {
              $selectedIndices = new Set();
              $selectedIdx = null;
              _redraw();
            }
          }
        } else {
          // Click on empty space without dragging — move playhead
          $selectedIndices = new Set();
          $selectedIdx = null;
          _redraw();
          if (_selectStartTime !== null && onSeek) {
            onSeek(_selectStartTime);
          }
        }
        Plotly.relayout(plotEl, { shapes: [] });
        _selectStartTime = null;
        _selectStartFreq = null;
      } else if (mode === 'pan') {
        plotEl.style.cursor = '';
      }

      if (_interacting) {
        _interacting = false;
        _redrawSync();
      }
      mode = null; dragIdx = null; startX = null; startY = null;
      startShift = null; startSmoothing = null; rampDragData = null;
      panStartXRange = null; panStartYRange = null; hasMoved = false;
      _multiDragStartShifts = null;
    });

    // Scroll zoom
    let _rafPending = false;
    let _pendingZoom: any = null;

    plotEl.addEventListener('wheel', (e: WheelEvent) => {
      e.preventDefault();
      const rect = plotEl.getBoundingClientRect();
      const layout = (plotEl as any)._fullLayout;
      if (!layout) return;
      const px = e.clientX - rect.left - layout.margin.l;
      const py = e.clientY - rect.top - layout.margin.t;
      const plotW = rect.width - layout.margin.l - layout.margin.r;
      const plotH = rect.height - layout.margin.t - layout.margin.b;

      let delta = e.deltaY;
      if (e.deltaMode === 1) delta *= 20;
      if (e.deltaMode === 2) delta *= 400;
      delta = Math.sign(delta) * Math.min(Math.abs(delta), 100);

      if (!_pendingZoom) {
        _pendingZoom = { delta: 0, px, py, shiftKey: e.shiftKey };
      }
      _pendingZoom.delta += delta;
      _pendingZoom.px = px;
      _pendingZoom.py = py;

      if (!_rafPending) {
        _rafPending = true;
        requestAnimationFrame(() => {
          _rafPending = false;
          if (!_pendingZoom) return;
          const { delta, px, py, shiftKey } = _pendingZoom;
          _pendingZoom = null;
          const factor = Math.pow(1.002, delta);

          if (shiftKey) {
            if (py < 0 || py > plotH) return;
            const yAtMouse = layout.yaxis.p2d(py);
            let y0 = yAtMouse - (yAtMouse - _yRange[0]) * factor;
            let y1 = yAtMouse + (_yRange[1] - yAtMouse) * factor;
            if (y1 - y0 < 10) return;
            y0 = Math.max(_fullYRange[0] * 0.9, y0);
            y1 = Math.min(_fullYRange[1] * 1.1, y1);
            _yRange = [y0, y1];
            Plotly.relayout(plotEl, { 'yaxis.range': _yRange });
          } else {
            if (px < 0 || px > plotW) return;
            const center = _playheadTime;
            let x0 = center - (center - _xRange[0]) * factor;
            let x1 = center + (_xRange[1] - center) * factor;
            x0 = Math.max(_fullXRange[0], x0);
            x1 = Math.min(_fullXRange[1], x1);
            if (x1 - x0 < 0.5) return;
            setXRange([x0, x1]);
            Plotly.relayout(plotEl, { 'xaxis.range': _xRange });
            syncWaveform(_xRange, _fullXRange[1]);
          }
        });
      }
    }, { passive: false });

    // Cursor hints
    plotEl.addEventListener('mousemove', (e: MouseEvent) => {
      if (mode) return;
      let newCursor = 'default';
      const resizeEdge = _getResizeEdge(e);
      if (resizeEdge) {
        newCursor = 'ew-resize';
      } else if (e.altKey && _isInPlotArea(e)) {
        newCursor = 'crosshair';
      } else if (e.ctrlKey && e.shiftKey) {
        const ci = _getClusterAtMouse(e);
        newCursor = ci === null && _isInPlotArea(e) ? 'grab' : ci !== null ? 'ns-resize' : 'default';
      } else if (e.ctrlKey) {
        const ci = _getClusterAtMouse(e);
        if (ci !== null) newCursor = 'ns-resize';
      } else {
        const ci = _getClusterAtMouse(e);
        if (ci !== null) newCursor = 'ns-resize';
      }
      plotEl.style.cursor = newCursor;
      const dragLayer = plotEl.querySelector('.nsewdrag') as HTMLElement;
      if (dragLayer) dragLayer.style.cursor = newCursor;
    });
  }

  onMount(async () => {
    const PlotlyLib = await import('plotly.js-dist-min');
    Plotly = PlotlyLib.default || PlotlyLib;

    Plotly.newPlot(plotEl, [], buildLayout(_xRange, _yRange), {
      responsive: true,
      displayModeBar: false,
      doubleClick: false,
      modeBarButtonsToRemove: ['select2d', 'lasso2d'],
    });

    _setupInteractions();
    _findPlayheadSvg();
  });

  // React to store changes
  $effect(() => {
    const t = $times;
    const f = $frequencies;
    if (!Plotly || !plotEl) return;

    // Skip full redraw when updatePitchSegment already handled the Plotly update
    if (_suppressStoreEffect) return;

    if (t.length > 0) {
      const newFullX: [number, number] = [0, t[t.length - 1]];
      const newFullY = getYRange(f);

      // Only reset zoom when the data extent actually changes (new audio loaded),
      // not when a segment is updated during editing
      const extentChanged =
        Math.abs(newFullX[1] - _fullXRange[1]) > 0.01 ||
        Math.abs(newFullY[0] - _fullYRange[0]) > 1 ||
        Math.abs(newFullY[1] - _fullYRange[1]) > 1;

      _fullXRange = newFullX;
      _fullYRange = [...newFullY] as [number, number];

      if (extentChanged) {
        setXRange([..._fullXRange] as [number, number]);
        _yRange = [..._fullYRange] as [number, number];
      }
    }

    // untrack prevents _redraw()'s internal store reads from becoming
    // dependencies of this effect, so only $times/$frequencies trigger it
    untrack(() => _redraw());
  });

  $effect(() => {
    // Re-render when clusters or midi change, without resetting zoom
    void $clusters;
    void $midiNotes;
    untrack(() => { if (Plotly && plotEl && !_interacting) _redraw(); });
  });

  $effect(() => {
    // Re-render when visibility toggles change
    void $showMidi;
    void $showCorrectionCurve;
    untrack(() => { if (Plotly && plotEl) _redraw(); });
  });

  // Relayout Plotly when switching back to pitch tab (container was display:none)
  $effect(() => {
    const tab = $activeTab;
    untrack(() => {
      if (tab === 'pitch' && Plotly && plotEl) {
        // Restore shared x-range from the other tab
        _xRange = [...$viewXRange] as [number, number];
        // Use requestAnimationFrame to wait for the container to be visible
        requestAnimationFrame(() => {
          Plotly.Plots.resize(plotEl);
          Plotly.relayout(plotEl, { 'xaxis.range': _xRange });
          syncWaveform(_xRange, _fullXRange[1]);
          _redraw();
        });
      }
    });
  });

  // Public API for parent to call
  export function updatePlayhead(time: number) {
    _playheadTime = time;
    if (!$times?.length) return;

    const span = _xRange[1] - _xRange[0];
    if (time > _xRange[1] - span * 0.1 && _xRange[1] < _fullXRange[1]) {
      let x0 = Math.max(_fullXRange[0], time - span * 0.1);
      let x1 = x0 + span;
      if (x1 > _fullXRange[1]) {
        x1 = _fullXRange[1];
        x0 = Math.max(_fullXRange[0], x1 - span);
      }
      setXRange([x0, x1]);
      Plotly.relayout(plotEl, { 'xaxis.range': _xRange });
      syncWaveform(_xRange, _fullXRange[1]);
      _findPlayheadSvg();
    }

    if (_playheadSvgPath) {
      const layout = (plotEl as any)._fullLayout;
      if (layout) {
        const x_px = layout.xaxis.d2p(time);
        const y0_px = layout.yaxis.d2p(_yRange[0]);
        const y1_px = layout.yaxis.d2p(_yRange[1]);
        _playheadSvgPath.setAttribute('d', `M${x_px},${y0_px}L${x_px},${y1_px}`);
      }
    }
  }

  export function updatePitchSegment(segTimes: number[], segFreqs: (number | null)[], startTime: number, endTime: number) {
    if (!Plotly || !plotEl) return;
    const buffer = 0.05;
    const curTimes = $times;
    const curFreqs = $frequencies;
    const newTimes: number[] = [];
    const newFreqs: (number | null)[] = [];

    for (let i = 0; i < curTimes.length; i++) {
      if (curTimes[i] < startTime - buffer) {
        newTimes.push(curTimes[i]);
        newFreqs.push(curFreqs[i]);
      }
    }
    for (let i = 0; i < segTimes.length; i++) {
      newTimes.push(segTimes[i]);
      newFreqs.push(segFreqs[i]);
    }
    for (let i = 0; i < curTimes.length; i++) {
      if (curTimes[i] > endTime + buffer) {
        newTimes.push(curTimes[i]);
        newFreqs.push(curFreqs[i]);
      }
    }

    _suppressStoreEffect = true;
    $times = newTimes;
    $frequencies = newFreqs;
    _suppressStoreEffect = false;
    Plotly.restyle(plotEl, { x: [newTimes], y: [newFreqs] }, [0]);
  }

  export function updateCorrectionCurve(curveTimes: (number | null)[], curveCents: (number | null)[]) {
    _correctionCurveTimes = curveTimes;
    _correctionCurveCents = curveCents;
    if (!Plotly || !plotEl) return;
    const hasMidi = $midiNotes.length > 0 ? 1 : 0;
    const curveTraceIdx = 1 + hasMidi;
    const tx = $showCorrectionCurve ? curveTimes : [];
    const ty = $showCorrectionCurve ? curveCents : [];
    Plotly.restyle(plotEl, { x: [tx], y: [ty] }, [curveTraceIdx]);

    const validCents = curveCents.filter((v): v is number => v !== null && !isNaN(v));
    if (validCents.length > 0) {
      const maxAbs = Math.max(Math.abs(Math.min(...validCents)), Math.abs(Math.max(...validCents)), 50);
      const range = Math.ceil(maxAbs / 50) * 50 + 50;
      Plotly.relayout(plotEl, { 'yaxis2.range': [-range, range] });
    }
  }

  export function resetView() {
    setXRange([..._fullXRange] as [number, number]);
    _yRange = [..._fullYRange] as [number, number];
    Plotly.relayout(plotEl, { 'xaxis.range': _xRange, 'yaxis.range': _yRange });
    syncWaveform(_xRange, _fullXRange[1]);
    _findPlayheadSvg();
  }

  /** Update playhead time without triggering redraws (for use when tab is hidden). */
  export function setPlayheadTime(time: number) {
    _playheadTime = time;
  }

  export function getSelectedIndices(): number[] {
    return Array.from($selectedIndices);
  }
</script>

<div class="plot-container">
  <div bind:this={plotEl} style="width:100%;height:100%;"></div>
  <div class="plot-controls">
    <button class="btn btn-secondary btn-sm" onclick={resetView}>⟲ Reset View</button>
    <span class="zoom-hint">Scroll to zoom X · Shift+Scroll to zoom Y · Ctrl+Shift+Drag to pan · Drag to select · Shift+click to multi-select</span>
  </div>
  <ProcessingOverlay />
</div>

