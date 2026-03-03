/* pitch_plot.js - Plotly pitch figure with draggable note boxes, scroll zoom, drag pan */

const PitchPlot = (() => {
  let _clusters = [];
  let _times = [];
  let _frequencies = [];
  let _midiNotes = [];
  let _selectedIndices = new Set();
  let _onClusterSelect = null;
  let _onClusterDrag = null;
  let _onClusterResize = null;
  let _onDrawBox = null;
  let _onDeleteCluster = null;
  let _onClusterSmoothing = null;
  let _onClusterRampDrag = null;
  let _playheadTime = 0;
  let _yRange = [75, 600];
  let _xRange = [0, 10];
  let _fullXRange = [0, 10];
  let _fullYRange = [75, 600];
  let _correctionCurveTimes = [];
  let _correctionCurveCents = [];
  let _playheadSvgPath = null; // Direct SVG reference for fast playhead updates
  let _sineTimeout = null; // Timeout for delayed sine wave start
  let _showMidi = true;
  let _showCorrectionCurve = false;

  const COLORS = {
    pitchLine:    '#2E86AB',
    correctionCurve: '#FFA500',
    noteBox:      'rgba(255,140,66,0.25)',
    noteBoxEdge:  '#D96C2C',
    noteSelected: 'rgba(233,69,96,0.35)',
    noteSelEdge:  '#e94560',
    midi:         '#06D6A0',
    playhead:     '#e94560',
  };

  const NOTE_FREQ_MAP = [
    ['C2',65.41],['C#2',69.30],['D2',73.42],['D#2',77.78],
    ['E2',82.41],['F2',87.31],['F#2',92.50],['G2',98.00],
    ['G#2',103.83],['A2',110.00],['A#2',116.54],['B2',123.47],
    ['C3',130.81],['C#3',138.59],['D3',146.83],['D#3',155.56],
    ['E3',164.81],['F3',174.61],['F#3',185.00],['G3',196.00],
    ['G#3',207.65],['A3',220.00],['A#3',233.08],['B3',246.94],
    ['C4',261.63],['C#4',277.18],['D4',293.66],['D#4',311.13],
    ['E4',329.63],['F4',349.23],['F#4',369.99],['G4',392.00],
    ['G#4',415.30],['A4',440.00],['A#4',466.16],['B4',493.88],
    ['C5',523.25],['C#5',554.37],['D5',587.33],['D#5',622.25],
  ];

  function getYRange(frequencies) {
    const valid = (frequencies || []).filter(f => f != null && !isNaN(f));
    if (valid.length === 0) return [75, 600];
    return [Math.min(...valid) * 0.93, Math.max(...valid) * 1.07];
  }

  function buildLayout(xRange, yRange) {
    const visibleNotes = NOTE_FREQ_MAP.filter(([, f]) => f >= yRange[0] && f <= yRange[1]);
    return {
      paper_bgcolor: '#1a1a2e',
      plot_bgcolor:  '#16213e',
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

  function buildTraces(times, frequencies, clusters, midiNotes, selectedIndices) {
    const traces = [];

    traces.push({
      x: times, y: frequencies,
      type: 'scatter', mode: 'lines',
      name: 'Detected Pitch',
      line: { color: COLORS.pitchLine, width: 1.5 },
      hoverinfo: 'skip',
    });

    if (midiNotes && midiNotes.length > 0) {
      const mx = [], my = [];
      if (_showMidi) {
        for (const n of midiNotes) {
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

    // Correction curve on secondary Y-axis (cents of correction)
    traces.push({
      x: _showCorrectionCurve ? _correctionCurveTimes : [],
      y: _showCorrectionCurve ? _correctionCurveCents : [],
      type: 'scatter', mode: 'lines',
      name: 'Correction (cents)',
      line: { color: COLORS.correctionCurve, width: 2 },
      yaxis: 'y2',
      hoverinfo: 'skip',
    });

    // Always use _fullYRange for box height so boxes maintain constant data-space
    // size and naturally scale when the user zooms in/out vertically.
    const spacing = (_fullYRange[1] - _fullYRange[0]) / 30;
    const h = spacing * 0.8;

    for (let i = 0; i < clusters.length; i++) {
      const c = clusters[i];
      const isSelected = selectedIndices.has(i);
      const freq = c.mean_freq + (c.pitch_shift_semitones * c.mean_freq * (Math.pow(2, 1/12) - 1));

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

    traces.push({
      x: [_playheadTime, _playheadTime], y: _yRange,
      type: 'scatter', mode: 'lines',
      name: 'Playhead',
      line: { color: COLORS.playhead, width: 1.5, dash: 'dot' },
      hoverinfo: 'skip', showlegend: false,
    });

    return traces;
  }

  function _getClusterAtMouse(e, el) {
    const rect = el.getBoundingClientRect();
    const layout = el._fullLayout;
    if (!layout) return null;
    const x = layout.xaxis.p2d(e.clientX - rect.left - layout.margin.l);
    const y = layout.yaxis.p2d(e.clientY - rect.top - layout.margin.t);
    const spacing = (_fullYRange[1] - _fullYRange[0]) / 30;
    const h = spacing * 0.8;
    for (let i = _clusters.length - 1; i >= 0; i--) {
      const c = _clusters[i];
      const freq = c.mean_freq + (c.pitch_shift_semitones * c.mean_freq * (Math.pow(2, 1/12) - 1));
      if (x >= c.start_time && x <= c.end_time && y >= freq - h/2 && y <= freq + h/2) return i;
    }
    return null;
  }

  function _getResizeEdge(e, el) {
    // Returns { clusterIdx, edge: 'left'|'right' } or null
    const rect = el.getBoundingClientRect();
    const layout = el._fullLayout;
    if (!layout) return null;
    
    const px = e.clientX - rect.left - layout.margin.l;
    const py = e.clientY - rect.top - layout.margin.t;
    const x = layout.xaxis.p2d(px);
    const y = layout.yaxis.p2d(py);
    
    const resizeThresholdPx = 10;
    const spacing = (_fullYRange[1] - _fullYRange[0]) / 30;
    const h = spacing * 0.8;

    for (let i = _clusters.length - 1; i >= 0; i--) {
      const c = _clusters[i];
      const freq = c.mean_freq + (c.pitch_shift_semitones * c.mean_freq * (Math.pow(2, 1/12) - 1));
      
      // Check if within vertical bounds
      if (y < freq - h/2 || y > freq + h/2) continue;
      
      // Check horizontal proximity to edges
      const leftPx = layout.xaxis.d2p(c.start_time);
      const rightPx = layout.xaxis.d2p(c.end_time);
      
      if (Math.abs(px - leftPx) < resizeThresholdPx) {
        return { clusterIdx: i, edge: 'left' };
      }
      if (Math.abs(px - rightPx) < resizeThresholdPx) {
        return { clusterIdx: i, edge: 'right' };
      }
    }
    return null;
  }

  function _isInPlotArea(e, el) {
    const rect = el.getBoundingClientRect();
    const layout = el._fullLayout;
    if (!layout) return false;
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    return px > layout.margin.l &&
           px < rect.width - layout.margin.r &&
           py > layout.margin.t &&
           py < rect.height - layout.margin.b;
  }

  // Returns the Plotly trace index of the box shape for a given cluster.
  // Trace layout: 0=pitch line, 1=MIDI (optional), then per cluster: [box, label] pairs, last=playhead.
  function _boxTraceIndex(clusterIdx) {
    const hasMidi = _midiNotes.length > 0 ? 1 : 0;
    // Trace order: 0=pitch, 1(opt)=MIDI, next=correction curve, then boxes (2 per cluster)
    return 2 + hasMidi + clusterIdx * 2;
  }

  function _setupInteractions(el) {
    let mode = null; // 'drag-note' | 'resize-box' | 'draw-box' | 'pan' | 'smooth-note' | 'ramp-drag' | 'select'
    let startX = null, startY = null;
    let dragIdx = null, startShift = null, startSmoothing = null;
    let resizeData = null; // { clusterIdx, edge, originalStart, originalEnd }
    let drawStartTime = null;
    let panStartXRange = null, panStartYRange = null;
    let dragStartYRange = null;
    let hasMoved = false;
    let rampDragData = null; // { clusterIdx, edge, startX, originalRampIn, originalRampOut }
    // SVG element refs cached at drag start for direct manipulation during drag
    let _dragBoxSvgCache = []; // array of { paths, label, x0px, x1px } per selected cluster
    let _dragBoxSvgPaths = null; // all path elements in the box trace (single drag fallback)
    let _dragLabelSvgEl  = null; // text element in the label trace (single drag fallback)
    let _dragBoxX0px     = 0;    // box left edge in pixels (constant during vertical drag)
    let _dragBoxX1px     = 0;    // box right edge in pixels (constant during vertical drag)
    // Multi-drag: per-cluster starting shifts
    let _multiDragStartShifts = null; // Map(idx → shift)
    // Rubber-band select start position
    let _selectStartTime = null;
    let _selectStartFreq = null;

    el.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;

      // 1. Alt+empty → draw-box
      if (e.altKey && _isInPlotArea(e, el)) {
        mode = 'draw-box';
        const rect = el.getBoundingClientRect();
        const layout = el._fullLayout;
        if (!layout) return;
        const px = e.clientX - rect.left - layout.margin.l;
        drawStartTime = layout.xaxis.p2d(px);
        startX = e.clientX;
        hasMoved = false;
        el.style.cursor = 'crosshair';
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return;
      }

      // 2. Ctrl+Shift+empty → pan
      if (e.ctrlKey && e.shiftKey && _isInPlotArea(e, el)) {
        const clusterIdx = _getClusterAtMouse(e, el);
        if (clusterIdx === null) {
          mode = 'pan';
          startX = e.clientX;
          startY = e.clientY;
          panStartXRange = [..._xRange];
          panStartYRange = [..._yRange];
          hasMoved = false;
          el.style.cursor = 'grabbing';
          e.preventDefault();
          return;
        }
      }

      // 3. Ctrl+edge → ramp-drag
      if (e.ctrlKey) {
        const resizeEdge = _getResizeEdge(e, el);
        if (resizeEdge) {
          mode = 'ramp-drag';
          const c = _clusters[resizeEdge.clusterIdx];
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
        // 4. Ctrl+body → smooth-note
        const ctrlClusterIdx = _getClusterAtMouse(e, el);
        if (ctrlClusterIdx !== null) {
          mode = 'smooth-note';
          dragIdx = ctrlClusterIdx;
          startY = e.clientY;
          startSmoothing = _clusters[dragIdx].smoothing_percent || 0;
          hasMoved = false;
          e.preventDefault();
          selectCluster(dragIdx);
          return;
        }
      }

      // 5. Edge → resize-box
      const resizeEdge = _getResizeEdge(e, el);
      if (resizeEdge) {
        mode = 'resize-box';
        const c = _clusters[resizeEdge.clusterIdx];
        resizeData = {
          clusterIdx: resizeEdge.clusterIdx,
          edge: resizeEdge.edge,
          originalStart: c.start_time,
          originalEnd: c.end_time,
        };
        startX = e.clientX;
        hasMoved = false;
        e.preventDefault();
        return;
      }

      // 7. Shift+body → toggle cluster in/out of selection
      const clusterIdx = _getClusterAtMouse(e, el);
      if (e.shiftKey && clusterIdx !== null) {
        toggleCluster(clusterIdx);
        e.preventDefault();
        return;
      }

      // 6. Body → drag-note (drags all selected if target is in selection)
      if (clusterIdx !== null) {
        // If cluster is NOT in selection, clear and select just this one
        if (!_selectedIndices.has(clusterIdx)) {
          selectCluster(clusterIdx);
        }
        // Now start drag for all selected clusters
        mode = 'drag-note';
        dragIdx = clusterIdx;
        startY = e.clientY;
        dragStartYRange = [..._yRange];
        hasMoved = false;
        e.preventDefault();

        // Store starting shifts for all selected clusters
        _multiDragStartShifts = new Map();
        for (const idx of _selectedIndices) {
          _multiDragStartShifts.set(idx, _clusters[idx].pitch_shift_semitones);
        }
        startShift = _clusters[dragIdx].pitch_shift_semitones;

        // Cache SVG elements for all selected clusters
        _dragBoxSvgCache = [];
        const allTraceEls = el.querySelectorAll('.scatterlayer .trace');
        const layout = el._fullLayout;
        for (const idx of _selectedIndices) {
          const boxIdx   = _boxTraceIndex(idx);
          const labelIdx = boxIdx + 1;
          const entry = { paths: null, label: null, x0px: 0, x1px: 0 };
          if (allTraceEls.length > labelIdx) {
            entry.paths = allTraceEls[boxIdx].querySelectorAll('path');
            entry.label = allTraceEls[labelIdx].querySelector('text');
          }
          if (layout) {
            entry.x0px = layout.xaxis.d2p(_clusters[idx].start_time);
            entry.x1px = layout.xaxis.d2p(_clusters[idx].end_time);
          }
          _dragBoxSvgCache.push({ idx, ...entry });
        }
        // Legacy single-drag refs for fallback
        _dragBoxSvgPaths = null;
        _dragLabelSvgEl  = null;
        if (layout) {
          _dragBoxX0px = layout.xaxis.d2p(_clusters[dragIdx].start_time);
          _dragBoxX1px = layout.xaxis.d2p(_clusters[dragIdx].end_time);
        }

        // Start sine wave after 300ms delay
        const shiftFactor = Math.pow(2, startShift / 12);
        const correctedFreq = _clusters[dragIdx].mean_freq * shiftFactor;
        if (typeof SinePlayer !== 'undefined') {
          const capturedClusterIdx = clusterIdx;
          const sineTimeout = setTimeout(() => {
            if (mode === 'drag-note' && dragIdx === capturedClusterIdx) {
              SinePlayer.play(correctedFreq);
            }
          }, 300);
          _sineTimeout = sineTimeout;
        }
        return;
      }

      // 8. Empty space → rubber-band select
      if (_isInPlotArea(e, el)) {
        mode = 'select';
        startX = e.clientX;
        startY = e.clientY;
        const rect = el.getBoundingClientRect();
        const layout = el._fullLayout;
        if (layout) {
          const px = e.clientX - rect.left - layout.margin.l;
          const py = e.clientY - rect.top - layout.margin.t;
          _selectStartTime = layout.xaxis.p2d(px);
          _selectStartFreq = layout.yaxis.p2d(py);
        }
        hasMoved = false;
        e.preventDefault();
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (!mode) return;

      if (mode === 'drag-note') {
        const dy = startY - e.clientY;
        if (Math.abs(dy) > 2) hasMoved = true;
        if (!hasMoved) return;
        const plotH = el.clientHeight - 80;
        const freqPerPx = (dragStartYRange[1] - dragStartYRange[0]) / plotH;
        const freqDelta = dy * freqPerPx;
        const baseCents = 1200 * Math.log2(
          (_clusters[dragIdx].mean_freq + freqDelta) / _clusters[dragIdx].mean_freq
        );
        const semitoneDelta = baseCents / 100;

        // Apply same semitone delta to all selected clusters
        if (_multiDragStartShifts) {
          for (const [idx, origShift] of _multiDragStartShifts) {
            _clusters[idx].pitch_shift_semitones = origShift + (semitoneDelta - (startShift - origShift + semitoneDelta - semitoneDelta));
            // Simplified: each cluster shifts by the same delta from its own start
            _clusters[idx].pitch_shift_semitones = origShift + semitoneDelta;
          }
        }

        if (typeof SinePlayer !== 'undefined') {
          const shiftFactor = Math.pow(2, _clusters[dragIdx].pitch_shift_semitones / 12);
          const correctedFreq = _clusters[dragIdx].mean_freq * shiftFactor;
          SinePlayer.updateFrequency(correctedFreq);
        }

        // Move all selected boxes via direct SVG writes
        const layout = el._fullLayout;
        const hasSvgRefs = layout && _dragBoxSvgCache.length > 0 &&
          _dragBoxSvgCache.some(c => c.paths && c.paths.length > 0);
        if (hasSvgRefs) {
          const spacing = (_fullYRange[1] - _fullYRange[0]) / 30;
          const h = spacing * 0.8;
          for (const cached of _dragBoxSvgCache) {
            const c    = _clusters[cached.idx];
            const freq = c.mean_freq + (c.pitch_shift_semitones * c.mean_freq * (Math.pow(2, 1/12) - 1));
            const y0px = layout.yaxis.d2p(freq - h / 2);
            const y1px = layout.yaxis.d2p(freq + h / 2);
            const d    = `M${cached.x0px},${y0px}` +
                         `L${cached.x1px},${y0px}` +
                         `L${cached.x1px},${y1px}` +
                         `L${cached.x0px},${y1px}Z`;
            if (cached.paths) {
              cached.paths.forEach(p => p.setAttribute('d', d));
            }
            if (cached.label) {
              cached.label.setAttribute('y', layout.yaxis.d2p(freq));
            }
          }
        } else {
          // Fallback: use Plotly.restyle for all selected clusters
          for (const idx of _selectedIndices) {
            _redrawDragBox(idx);
          }
        }

      } else if (mode === 'smooth-note') {
        const dy = startY - e.clientY;
        if (Math.abs(dy) > 2) hasMoved = true;
        if (!hasMoved) return;
        const SMOOTH_PX_RANGE = 200; // 200px = 100%
        const newSmoothing = Math.max(0, Math.min(100, startSmoothing + (dy / SMOOTH_PX_RANGE) * 100));
        _clusters[dragIdx].smoothing_percent = newSmoothing;
        if (_onClusterSmoothing) _onClusterSmoothing(dragIdx, newSmoothing);

      } else if (mode === 'ramp-drag') {
        const dx = e.clientX - rampDragData.startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;

        // Convert pixel delta to time delta (ms)
        const layout = el._fullLayout;
        if (!layout) return;
        const plotW = el.clientWidth - layout.margin.l - layout.margin.r;
        const xSpan = _xRange[1] - _xRange[0];
        const deltaMs = (dx / plotW) * xSpan * 1000 * 3;

        const c = _clusters[rampDragData.clusterIdx];
        if (rampDragData.edge === 'left') {
          // Dragging left increases ramp_in, dragging right decreases
          c.ramp_in_ms = Math.max(0, rampDragData.originalRampIn - deltaMs);
        } else {
          // Dragging right increases ramp_out, dragging left decreases
          c.ramp_out_ms = Math.max(0, rampDragData.originalRampOut + deltaMs);
        }

      } else if (mode === 'resize-box') {
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 2) hasMoved = true;
        if (!hasMoved) return;
        
        const layout = el._fullLayout;
        if (!layout) return;
        const rect = el.getBoundingClientRect();
        const px = e.clientX - rect.left - layout.margin.l;
        const currentTime = layout.xaxis.p2d(px);
        
        const c = _clusters[resizeData.clusterIdx];
        
        if (resizeData.edge === 'left') {
          let newStart = currentTime;
          // Clamp to not go past end
          if (newStart >= c.end_time) newStart = c.end_time - 0.01;
          // Check overlap with previous cluster
          if (resizeData.clusterIdx > 0) {
            const prev = _clusters[resizeData.clusterIdx - 1];
            if (newStart < prev.end_time) newStart = prev.end_time;
          }
          c.start_time = Math.max(0, newStart);
        } else {
          let newEnd = currentTime;
          // Clamp to not go before start
          if (newEnd <= c.start_time) newEnd = c.start_time + 0.01;
          // Check overlap with next cluster
          if (resizeData.clusterIdx < _clusters.length - 1) {
            const next = _clusters[resizeData.clusterIdx + 1];
            if (newEnd > next.start_time) newEnd = next.start_time;
          }
          c.end_time = newEnd;
        }
        
        c.duration_ms = (c.end_time - c.start_time) * 1000;
        _redraw();

      } else if (mode === 'draw-box') {
        if (Math.abs(e.clientX - startX) > 2) hasMoved = true;
        if (!hasMoved) return;

        // Draw a live rubber-band rectangle as a Plotly shape
        const rect2 = el.getBoundingClientRect();
        const layout2 = el._fullLayout;
        if (layout2) {
          const px2 = e.clientX - rect2.left - layout2.margin.l;
          const currentTime = layout2.xaxis.p2d(px2);
          const x0 = Math.min(drawStartTime, currentTime);
          const x1 = Math.max(drawStartTime, currentTime);
          Plotly.relayout(el, {
            shapes: [{
              type: 'rect',
              xref: 'x', yref: 'y',
              x0, x1,
              y0: _yRange[0],
              y1: _yRange[1],
              fillcolor: 'rgba(255,140,66,0.12)',
              line: { color: '#D96C2C', width: 1.5, dash: 'dot' },
              layer: 'above',
            }],
          });
        }

        el.style.cursor = 'crosshair';

      } else if (mode === 'select') {
        const dx2 = e.clientX - startX;
        const dy2 = e.clientY - startY;
        if (Math.abs(dx2) > 2 || Math.abs(dy2) > 2) hasMoved = true;
        if (!hasMoved) return;

        // Draw rubber-band rectangle with distinct style
        const rectS = el.getBoundingClientRect();
        const layoutS = el._fullLayout;
        if (layoutS) {
          const pxS = e.clientX - rectS.left - layoutS.margin.l;
          const pyS = e.clientY - rectS.top - layoutS.margin.t;
          const currentTime = layoutS.xaxis.p2d(pxS);
          const currentFreq = layoutS.yaxis.p2d(pyS);
          const x0 = Math.min(_selectStartTime, currentTime);
          const x1 = Math.max(_selectStartTime, currentTime);
          const y0 = Math.min(_selectStartFreq, currentFreq);
          const y1 = Math.max(_selectStartFreq, currentFreq);
          Plotly.relayout(el, {
            shapes: [{
              type: 'rect',
              xref: 'x', yref: 'y',
              x0, x1, y0, y1,
              fillcolor: 'rgba(255,255,255,0.06)',
              line: { color: 'rgba(255,255,255,0.5)', width: 1, dash: 'dash' },
              layer: 'above',
            }],
          });
        }

      } else if (mode === 'pan') {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        if (Math.abs(dx) > 2 || Math.abs(dy) > 2) hasMoved = true;
        if (!hasMoved) return;

        const layout = el._fullLayout;
        if (!layout) return;

        const plotW = el.clientWidth - layout.margin.l - layout.margin.r;
        const xSpan = panStartXRange[1] - panStartXRange[0];
        const xDelta = -(dx / plotW) * xSpan;
        let x0 = panStartXRange[0] + xDelta;
        let x1 = panStartXRange[1] + xDelta;
        if (x0 < _fullXRange[0]) { x1 += _fullXRange[0] - x0; x0 = _fullXRange[0]; }
        if (x1 > _fullXRange[1]) { x0 -= x1 - _fullXRange[1]; x1 = _fullXRange[1]; }

        const plotH = el.clientHeight - layout.margin.t - layout.margin.b;
        const ySpan = panStartYRange[1] - panStartYRange[0];
        const yDelta = (dy / plotH) * ySpan;
        let y0 = panStartYRange[0] + yDelta;
        let y1 = panStartYRange[1] + yDelta;
        if (y0 < _fullYRange[0] * 0.9) { y1 += _fullYRange[0] * 0.9 - y0; y0 = _fullYRange[0] * 0.9; }
        if (y1 > _fullYRange[1] * 1.1) { y0 -= y1 - _fullYRange[1] * 1.1; y1 = _fullYRange[1] * 1.1; }

        _xRange = [x0, x1];
        _yRange = [y0, y1];
        Plotly.relayout(el, { 'xaxis.range': _xRange, 'yaxis.range': _yRange });
        Waveform.syncToRange(_xRange, _fullXRange[1]);
      }
    });

    window.addEventListener('mouseup', (e) => {
      // Cancel sine wave timeout if released quickly
      if (_sineTimeout) {
        clearTimeout(_sineTimeout);
        _sineTimeout = null;
      }
      
      // Always stop sine wave on release (whether it was playing or not)
      if (typeof SinePlayer !== 'undefined') {
        SinePlayer.stop();
      }
      
      if (mode === 'drag-note') {
        _dragBoxSvgCache = [];
        _dragBoxSvgPaths = null;
        _dragLabelSvgEl  = null;
        if (hasMoved && _onClusterDrag) {
          // Fire onDrag for each selected cluster
          const capturedIndices = Array.from(_selectedIndices);
          const capturedShifts = capturedIndices.map(idx => _clusters[idx].pitch_shift_semitones);
          requestAnimationFrame(() => {
            for (let i = 0; i < capturedIndices.length; i++) {
              _onClusterDrag(capturedIndices[i], capturedShifts[i]);
            }
          });
        }
        dragStartYRange = null;
        _multiDragStartShifts = null;

      } else if (mode === 'smooth-note') {
        if (hasMoved && _onClusterSmoothing) {
          const capturedIdx      = dragIdx;
          const capturedSmoothing = _clusters[dragIdx].smoothing_percent;
          requestAnimationFrame(() => _onClusterSmoothing(capturedIdx, capturedSmoothing));
        }
        startSmoothing = null;

      } else if (mode === 'ramp-drag') {
        if (hasMoved && _onClusterRampDrag) {
          const capturedIdx = rampDragData.clusterIdx;
          const c = _clusters[capturedIdx];
          const capturedIn = c.ramp_in_ms;
          const capturedOut = c.ramp_out_ms;
          requestAnimationFrame(() => _onClusterRampDrag(capturedIdx, capturedIn, capturedOut));
        }
        rampDragData = null;

      } else if (mode === 'resize-box') {
        if (hasMoved && _onClusterResize) {
          _onClusterResize(resizeData.clusterIdx);
        }
        resizeData = null;
        
      } else if (mode === 'draw-box') {
        if (hasMoved) {
          const rect = el.getBoundingClientRect();
          const layout = el._fullLayout;
          if (layout) {
            const px = e.clientX - rect.left - layout.margin.l;
            const drawEndTime = layout.xaxis.p2d(px);
            const start = Math.min(drawStartTime, drawEndTime);
            const end = Math.max(drawStartTime, drawEndTime);
            
            if (_onDrawBox) {
              _onDrawBox(start, end);
            }
          }
        }
        // Always clear the preview shape, whether or not we committed a box
        Plotly.relayout(el, { shapes: [] });
        drawStartTime = null;
        el.style.cursor = '';
        
      } else if (mode === 'select') {
        if (hasMoved) {
          // Find all clusters whose boxes intersect the rubber-band rectangle
          const rectS = el.getBoundingClientRect();
          const layoutS = el._fullLayout;
          if (layoutS) {
            const pxS = e.clientX - rectS.left - layoutS.margin.l;
            const pyS = e.clientY - rectS.top - layoutS.margin.t;
            const endTime = layoutS.xaxis.p2d(pxS);
            const endFreq = layoutS.yaxis.p2d(pyS);
            const selX0 = Math.min(_selectStartTime, endTime);
            const selX1 = Math.max(_selectStartTime, endTime);
            const selY0 = Math.min(_selectStartFreq, endFreq);
            const selY1 = Math.max(_selectStartFreq, endFreq);

            const spacing = (_fullYRange[1] - _fullYRange[0]) / 30;
            const h = spacing * 0.8;
            const intersecting = [];
            for (let i = 0; i < _clusters.length; i++) {
              const c = _clusters[i];
              const freq = c.mean_freq + (c.pitch_shift_semitones * c.mean_freq * (Math.pow(2, 1/12) - 1));
              const boxY0 = freq - h / 2;
              const boxY1 = freq + h / 2;
              // Check AABB intersection
              if (c.start_time <= selX1 && c.end_time >= selX0 &&
                  boxY0 <= selY1 && boxY1 >= selY0) {
                intersecting.push(i);
              }
            }
            if (intersecting.length > 0) {
              selectClusters(intersecting);
            } else {
              _selectedIndices.clear();
              _redraw();
            }
          }
        } else {
          // Click on empty space with no drag → clear selection
          _selectedIndices.clear();
          _redraw();
        }
        Plotly.relayout(el, { shapes: [] });
        _selectStartTime = null;
        _selectStartFreq = null;

      } else if (mode === 'pan') {
        el.style.cursor = '';
      }

      mode = null; dragIdx = null; startX = null; startY = null;
      startShift = null; startSmoothing = null; rampDragData = null; panStartXRange = null; panStartYRange = null; hasMoved = false;
      _multiDragStartShifts = null;
    });

    // Smooth zoom using requestAnimationFrame
    let _rafPending = false;
    let _pendingZoom = null;

    el.addEventListener('wheel', (e) => {
      e.preventDefault();

      const rect = el.getBoundingClientRect();
      const layout = el._fullLayout;
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
            Plotly.relayout(el, { 'yaxis.range': _yRange });
          } else {
            if (px < 0 || px > plotW) return;
            const xAtMouse = layout.xaxis.p2d(px);
            let x0 = xAtMouse - (xAtMouse - _xRange[0]) * factor;
            let x1 = xAtMouse + (_xRange[1] - xAtMouse) * factor;
            x0 = Math.max(_fullXRange[0], x0);
            x1 = Math.min(_fullXRange[1], x1);
            if (x1 - x0 < 0.5) return;
            _xRange = [x0, x1];
            Plotly.relayout(el, { 'xaxis.range': _xRange });
            Waveform.syncToRange(_xRange, _fullXRange[1]);
          }
        });
      }
    }, { passive: false });

    // Mousemove for cursor hints - attach to plot element
    el.addEventListener('mousemove', (e) => {
      if (mode) return;

      let newCursor = 'default';

      const resizeEdge = _getResizeEdge(e, el);
      if (resizeEdge) {
        // Show ew-resize for both normal resize and ctrl+edge (ramp drag)
        newCursor = 'ew-resize';
      } else if (e.altKey && _isInPlotArea(e, el)) {
        newCursor = 'crosshair';
      } else if (e.ctrlKey && e.shiftKey) {
        // Ctrl+Shift on empty space → grab (pan mode)
        const clusterIdx = _getClusterAtMouse(e, el);
        if (clusterIdx === null && _isInPlotArea(e, el)) {
          newCursor = 'grab';
        } else if (clusterIdx !== null) {
          newCursor = 'ns-resize';
        }
      } else if (e.ctrlKey) {
        const clusterIdx = _getClusterAtMouse(e, el);
        if (clusterIdx !== null) {
          newCursor = 'ns-resize'; // ctrl+body = smoothing
        }
      } else {
        const clusterIdx = _getClusterAtMouse(e, el);
        if (clusterIdx !== null) {
          newCursor = 'ns-resize';
        }
      }

      // Set cursor on multiple elements to override Plotly
      el.style.cursor = newCursor;
      const dragLayer = el.querySelector('.nsewdrag');
      if (dragLayer) dragLayer.style.cursor = newCursor;
    });

    // Global Alt key handlers for cursor feedback
    let altPressed = false;
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Alt' && !mode) {
        altPressed = true;
      }
    });

    document.addEventListener('keyup', (e) => {
      if (e.key === 'Alt') {
        altPressed = false;
        if (!mode) {
          el.style.cursor = 'default';
        }
      }
    });
  }

  function _redraw() {
    const el = document.getElementById('pitchPlot');
    Plotly.react(el,
      buildTraces(_times, _frequencies, _clusters, _midiNotes, _selectedIndices),
      buildLayout(_xRange, _yRange),
      { responsive: true, displayModeBar: false }
    );
    // Clear any draw-box preview shape left over from a cancelled gesture
    Plotly.relayout(el, { shapes: [] });
    _findPlayheadSvg();
  }

  // Fast path: update only the dragged box and its label during mousemove.
  // Avoids rebuilding and diffing the full trace list (including the entire pitch line)
  // on every mousemove event. Full _redraw() still runs on mouseup to sync everything.
  function _redrawDragBox(clusterIdx) {
    const el = document.getElementById('pitchPlot');
    const spacing = (_fullYRange[1] - _fullYRange[0]) / 30;
    const h = spacing * 0.8;
    const c = _clusters[clusterIdx];
    const freq = c.mean_freq + (c.pitch_shift_semitones * c.mean_freq * (Math.pow(2, 1/12) - 1));

    const boxIdx   = _boxTraceIndex(clusterIdx);
    const labelIdx = boxIdx + 1;

    Plotly.restyle(el,
      { y: [[freq - h/2, freq - h/2, freq + h/2, freq + h/2, freq - h/2]] },
      [boxIdx]
    );
    Plotly.restyle(el,
      { y: [[freq]] },
      [labelIdx]
    );
  }

  function _findPlayheadSvg() {
    const el = document.getElementById('pitchPlot');
    if (!el) return;
    const svg = el.querySelector('.plotly .main-svg');
    if (!svg) return;
    // Find the last path in the scatter layer (playhead is last trace)
    const paths = svg.querySelectorAll('.scatterlayer .trace:last-child path.js-line');
    if (paths && paths.length > 0) {
      _playheadSvgPath = paths[0];
    }
  }

  function init(callbacks) {
    _onClusterSelect = callbacks.onSelect;
    _onClusterDrag = callbacks.onDrag;
    _onClusterResize = callbacks.onResize;
    _onDrawBox = callbacks.onDrawBox;
    _onDeleteCluster = callbacks.onDelete;
    _onClusterSmoothing = callbacks.onSmoothing;
    _onClusterRampDrag = callbacks.onRampDrag;
    const el = document.getElementById('pitchPlot');
    Plotly.newPlot(el, [], buildLayout(_xRange, _yRange), { 
      responsive: true, 
      displayModeBar: false,
      doubleClick: false,
      modeBarButtonsToRemove: ['select2d', 'lasso2d'],
    });
    // Cluster selection is handled entirely in _setupInteractions mousedown
    // to support multi-select (Shift+click toggle). Plotly_click is disabled
    // to avoid conflicts with the custom interaction model.
    _setupInteractions(el);
    document.getElementById('btnResetView')?.addEventListener('click', resetView);
    _findPlayheadSvg();
  }

  function render(times, frequencies, clusters, midiNotes) {
    if (times) _times = times;
    if (frequencies) _frequencies = frequencies;
    if (clusters) _clusters = clusters;
    if (midiNotes !== null) _midiNotes = midiNotes || [];
    if (times?.length > 0) {
      _yRange = getYRange(frequencies);
      _fullYRange = [..._yRange];
      _fullXRange = [0, times[times.length - 1]];
      _xRange = [..._fullXRange];
    }
    _selectedIndices.clear();
    _redraw();
  }

  function selectCluster(idx) {
    _selectedIndices.clear();
    _selectedIndices.add(idx);
    _redraw();
    if (_onClusterSelect) _onClusterSelect(idx, _clusters[idx]);
  }

  function toggleCluster(idx) {
    if (_selectedIndices.has(idx)) {
      _selectedIndices.delete(idx);
    } else {
      _selectedIndices.add(idx);
    }
    _redraw();
    // Fire callback with first selected cluster for panel update
    const first = _selectedIndices.size > 0 ? _selectedIndices.values().next().value : null;
    if (first !== null && _onClusterSelect) {
      _onClusterSelect(first, _clusters[first]);
    }
  }

  function selectClusters(idxArray) {
    _selectedIndices.clear();
    for (const idx of idxArray) _selectedIndices.add(idx);
    _redraw();
    const first = idxArray.length > 0 ? idxArray[0] : null;
    if (first !== null && _onClusterSelect) {
      _onClusterSelect(first, _clusters[first]);
    }
  }

  function getSelectedIndices() {
    return Array.from(_selectedIndices);
  }

  function updateCluster(idx, updates) {
    Object.assign(_clusters[idx], updates);
    _redraw();
  }

  function updatePitchSegment(segTimes, segFreqs, startTime, endTime) {
    const buffer = 0.05;
    const newTimes = [];
    const newFreqs = [];

    for (let i = 0; i < _times.length; i++) {
      if (_times[i] < startTime - buffer) {
        newTimes.push(_times[i]);
        newFreqs.push(_frequencies[i]);
      }
    }
    for (let i = 0; i < segTimes.length; i++) {
      newTimes.push(segTimes[i]);
      newFreqs.push(segFreqs[i]);
    }
    for (let i = 0; i < _times.length; i++) {
      if (_times[i] > endTime + buffer) {
        newTimes.push(_times[i]);
        newFreqs.push(_frequencies[i]);
      }
    }

    _times = newTimes;
    _frequencies = newFreqs;

    // Only the pitch line (trace 0) has changed - restyle it directly instead of
    // calling _redraw(), which would rebuild layout + all traces via Plotly.react().
    // The box traces and playhead are unaffected by a pitch data splice.
    const el = document.getElementById('pitchPlot');
    Plotly.restyle(el, { x: [_times], y: [_frequencies] }, [0]);
  }

  function updateCorrectionCurve(curveTimes, curveCents) {
    _correctionCurveTimes = curveTimes;
    _correctionCurveCents = curveCents;
    // Correction curve trace index: 1 + hasMidi
    const hasMidi = _midiNotes.length > 0 ? 1 : 0;
    const curveTraceIdx = 1 + hasMidi;
    const el = document.getElementById('pitchPlot');
    const tx = _showCorrectionCurve ? curveTimes : [];
    const ty = _showCorrectionCurve ? curveCents : [];
    Plotly.restyle(el, { x: [tx], y: [ty] }, [curveTraceIdx]);

    // Auto-scale yaxis2 range based on correction values
    const validCents = curveCents.filter(v => v !== null && !isNaN(v));
    if (validCents.length > 0) {
      const maxAbs = Math.max(Math.abs(Math.min(...validCents)), Math.abs(Math.max(...validCents)), 50);
      const range = Math.ceil(maxAbs / 50) * 50 + 50; // Round up to next 50 + padding
      Plotly.relayout(el, { 'yaxis2.range': [-range, range] });
    }
  }

  function deleteCluster(idx) {
    if (idx >= 0 && idx < _clusters.length) {
      _clusters.splice(idx, 1);
      _selectedIndices.clear();
      _redraw();
      if (_onDeleteCluster) {
        _onDeleteCluster(idx);
      }
    }
  }

  function updatePlayhead(time) {
    _playheadTime = time;
    if (!_times?.length) return;

    // Auto-scroll if playhead nears right edge
    const span = _xRange[1] - _xRange[0];
    if (time > _xRange[1] - span * 0.1) {
      let x0 = Math.max(_fullXRange[0], time - span * 0.1);
      let x1 = Math.min(_fullXRange[1], x0 + span);
      _xRange = [x0, x1];
      Plotly.relayout(document.getElementById('pitchPlot'), { 'xaxis.range': _xRange });
      Waveform.syncToRange(_xRange, _fullXRange[1]);
      _findPlayheadSvg(); // Re-find after relayout
    }

    // Fast playhead update via direct SVG manipulation
    if (_playheadSvgPath) {
      const el = document.getElementById('pitchPlot');
      const layout = el._fullLayout;
      if (layout) {
        const x_px = layout.xaxis.d2p(time);
        const y0_px = layout.yaxis.d2p(_yRange[0]);
        const y1_px = layout.yaxis.d2p(_yRange[1]);
        _playheadSvgPath.setAttribute('d', `M${x_px},${y0_px}L${x_px},${y1_px}`);
      }
    }
  }

  function resetView() {
    _xRange = [..._fullXRange];
    _yRange = [..._fullYRange];
    Plotly.relayout(document.getElementById('pitchPlot'), {
      'xaxis.range': _xRange,
      'yaxis.range': _yRange,
    });
    Waveform.syncToRange(_xRange, _fullXRange[1]);
    _findPlayheadSvg();
  }

  function syncXRange(xRange) {
    _xRange = xRange;
    Plotly.relayout(document.getElementById('pitchPlot'), { 'xaxis.range': _xRange });
  }

  function setShowMidi(show) {
    _showMidi = show;
    _redraw();
  }

  function setShowCorrectionCurve(show) {
    _showCorrectionCurve = show;
    _redraw();
  }

  return { init, render, selectCluster, toggleCluster, selectClusters, getSelectedIndices, updateCluster, updatePitchSegment, updateCorrectionCurve, updatePlayhead, resetView, syncXRange, deleteCluster, setShowMidi, setShowCorrectionCurve };
})();
