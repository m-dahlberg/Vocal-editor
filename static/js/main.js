/* main.js - App initialization and UI coordination */

const App = (() => {

  let _state = {
    audioLoaded: false,
    midiLoaded: false,
    clusters: [],
    selectedCluster: null,
    selectedIdx: null,
    dirtyClusters: new Set(), // Track clusters that need rubberband processing
    times: [],
    frequencies: [],
    originalTimes: [],       // Immutable copy from analysis - never modified after set
    originalFrequencies: [], // Immutable copy from analysis - never modified after set
  };

  // ---- LOGGING ----

  function log(msg, type = 'info') {
    const el = document.getElementById('logArea');
    const line = document.createElement('div');
    line.className = `log-${type}`;
    const ts = new Date().toLocaleTimeString('en', { hour12: false });
    line.textContent = `[${ts}] ${msg}`;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
  }

  // ---- PARAMS ----

  function getParams() {
    const n = id => parseFloat(document.getElementById(id).value);
    const b = id => document.getElementById(id).checked;
    const s = id => document.getElementById(id).value;

    return {
      min_frequency:             n('p_min_frequency'),
      max_frequency:             n('p_max_frequency'),
      time_resolution_ms:        n('p_time_resolution_ms'),
      frequency_tolerance_cents: n('p_frequency_tolerance_cents'),
      min_note_duration_ms:      n('p_min_note_duration_ms'),
      max_gap_to_bridge_ms:      n('p_max_gap_to_bridge_ms'),
      silence_threshold_db:      n('p_silence_threshold_db'),
      transition_ramp_ms:        n('p_transition_ramp_ms'),
      gap_threshold_ms:          n('p_gap_threshold_ms'),
      correction_strength:       n('p_correction_strength'),
      midi_threshold_cents:      n('p_midi_threshold_cents'),
      autocorrect_smoothing:     n('p_autocorrect_smoothing'),
      smoothing_threshold_cents: n('p_smoothing_threshold_cents'),
      smooth_curve:             n('p_smooth_curve'),
      rb: {
        command:     s('p_rb_command'),
        crisp:       parseInt(document.getElementById('p_rb_crisp').value),
        formant:     b('p_rb_formant'),
        pitch_hq:    b('p_rb_pitch_hq'),
        window_long: b('p_rb_window_long'),
        smoothing:   b('p_rb_smoothing'),
      },
    };
  }

  // ---- CLUSTER PANEL ----

  function showClusterDetails(idx, cluster) {
    _state.selectedIdx = idx;
    _state.selectedCluster = cluster;

    const panel = document.getElementById('clusterDetails');
    const shift_cents = (cluster.pitch_shift_semitones * 100).toFixed(1);
    const selectedIndices = PitchPlot.getSelectedIndices();
    const multiCount = selectedIndices.length;

    panel.innerHTML = `
      ${multiCount > 1 ? `<div class="cluster-detail-row" style="background:var(--bg3);border-radius:4px;padding:6px;margin-bottom:6px;">
        <span class="label" style="font-weight:600;color:var(--accent);">${multiCount} notes selected</span>
      </div>` : ''}
      <div class="cluster-detail-row">
        <span class="label">Cluster</span>
        <span class="value">#${idx + 1}</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Note</span>
        <span class="value">${cluster.note}</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Start</span>
        <span class="value">${cluster.start_time.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">End</span>
        <span class="value">${cluster.end_time.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Duration</span>
        <span class="value">${cluster.duration_ms.toFixed(0)} ms</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Mean freq</span>
        <span class="value">${cluster.mean_freq.toFixed(1)} Hz</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Pitch variation</span>
        <span class="value">${(cluster.pitch_variation_cents || 0).toFixed(1)} cents</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Correction</span>
        <span class="value">${shift_cents} cents</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Edited</span>
        <span class="value">${cluster.manually_edited ? '✏️ Yes' : 'No'}</span>
      </div>

      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Per-note parameters</div>
      </div>

      <div class="cluster-param-row">
        <label>Ramp in (ms)</label>
        <div class="slider-input-pair">
          <input type="range" id="cn_ramp_in_ms_slider" min="0" max="1000" value="${cluster.ramp_in_ms}">
          <input type="number" id="cn_ramp_in_ms" value="${cluster.ramp_in_ms}" min="0">
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Ramp out (ms)</label>
        <div class="slider-input-pair">
          <input type="range" id="cn_ramp_out_ms_slider" min="0" max="1000" value="${cluster.ramp_out_ms}">
          <input type="number" id="cn_ramp_out_ms" value="${cluster.ramp_out_ms}" min="0">
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Smoothing (%)</label>
        <div class="slider-input-pair">
          <input type="range" id="cn_smoothing_percent_slider" min="0" max="100" value="${cluster.smoothing_percent}">
          <input type="number" id="cn_smoothing_percent" value="${cluster.smoothing_percent}" min="0" max="100">
        </div>
      </div>
    `;

    // Wire bidirectional sync between sliders and number inputs,
    // and apply changes live to the pitch graph on every input event.
    const sliderPairs = [
      ['cn_ramp_in_ms_slider', 'cn_ramp_in_ms'],
      ['cn_ramp_out_ms_slider', 'cn_ramp_out_ms'],
      ['cn_smoothing_percent_slider', 'cn_smoothing_percent'],
    ];
    for (const [sliderId, numberId] of sliderPairs) {
      const slider = document.getElementById(sliderId);
      const number = document.getElementById(numberId);
      slider.addEventListener('input', () => { number.value = slider.value; applyPanelEditsLive(); });
      number.addEventListener('input', () => { slider.value = number.value; applyPanelEditsLive(); });
    }
  }

  function applyPanelEditsLive() {
    if (_state.selectedIdx === null) return;

    const rampIn    = parseFloat(document.getElementById('cn_ramp_in_ms').value);
    const rampOut   = parseFloat(document.getElementById('cn_ramp_out_ms').value);
    const smoothing = parseFloat(document.getElementById('cn_smoothing_percent').value);

    const selectedIndices = PitchPlot.getSelectedIndices();
    const indices = selectedIndices.length > 0 ? selectedIndices : [_state.selectedIdx];

    for (const idx of indices) {
      const cluster = _state.clusters[idx];
      cluster.ramp_in_ms = rampIn;
      cluster.ramp_out_ms = rampOut;
      cluster.smoothing_percent = smoothing;
      cluster.manually_edited = true;
      _state.dirtyClusters.add(idx);
      updatePitchCurveForCluster(idx);
    }

    generateCorrectionCurve();
  }

  // ---- PROCESSING OVERLAY ----

  function showProcessing(show) {
    document.getElementById('processingOverlay').classList.toggle('hidden', !show);
  }

  // ---- DRAG CALLBACK ----

  async function onClusterDrag(idx, newShift) {
    _state.clusters[idx].pitch_shift_semitones = newShift;
    _state.clusters[idx].manually_edited = true;
    _state.dirtyClusters.add(idx);

    if (_state.selectedIdx === idx) {
      const shiftCents = (newShift * 100).toFixed(1);
      const el = document.getElementById('clusterDetails');
      const correctionEl = el?.querySelector('.cluster-detail-row:nth-child(7) .value');
      if (correctionEl) correctionEl.textContent = `${shiftCents} cents`;
    }

    // Update visual immediately
    PitchPlot.updateCluster(idx, _state.clusters[idx]);
    
    // Calculate and update the expected pitch curve for this segment
    updatePitchCurveForCluster(idx);
    generateCorrectionCurve();

    log(`✓ Cluster ${idx + 1} moved to ${(newShift * 100).toFixed(1)} cents (will process on playback)`);
  }

  // ---- RESIZE CALLBACK ----

  async function onClusterResize(idx) {
    const cluster = _state.clusters[idx];
    
    // Don't recalculate mean frequency - keep the same target pitch
    // User has already set this, just update the boundaries
    
    cluster.manually_edited = true;
    _state.dirtyClusters.add(idx);
    
    PitchPlot.updateCluster(idx, cluster);
    updatePitchCurveForCluster(idx);
    generateCorrectionCurve();

    if (_state.selectedIdx === idx) {
      showClusterDetails(idx, cluster);
    }

    log(`✓ Cluster ${idx + 1} resized to ${cluster.duration_ms.toFixed(0)}ms`);
  }

  // ---- SMOOTHING CALLBACK ----

  async function onClusterSmoothing(idx, newSmoothing) {
    const selectedIndices = PitchPlot.getSelectedIndices();
    const indices = selectedIndices.length > 1 && selectedIndices.includes(idx) ? selectedIndices : [idx];

    for (const i of indices) {
      _state.clusters[i].smoothing_percent = newSmoothing;
      _state.clusters[i].manually_edited = true;
      _state.dirtyClusters.add(i);
      updatePitchCurveForCluster(i);
    }

    // Update the smoothing input in the details panel if this cluster is selected
    if (_state.selectedIdx === idx) {
      const smoothingInput = document.getElementById('cn_smoothing_percent');
      if (smoothingInput) smoothingInput.value = newSmoothing.toFixed(1);
      const smoothingSlider = document.getElementById('cn_smoothing_percent_slider');
      if (smoothingSlider) smoothingSlider.value = newSmoothing.toFixed(1);
    }

    log(`✓ ${indices.length} cluster(s) smoothing set to ${newSmoothing.toFixed(1)}%`);
  }

  // ---- RAMP DRAG CALLBACK ----

  async function onClusterRampDrag(idx, rampInMs, rampOutMs) {
    const selectedIndices = PitchPlot.getSelectedIndices();
    const indices = selectedIndices.length > 1 && selectedIndices.includes(idx) ? selectedIndices : [idx];

    for (const i of indices) {
      _state.clusters[i].ramp_in_ms = rampInMs;
      _state.clusters[i].ramp_out_ms = rampOutMs;
      _state.clusters[i].manually_edited = true;
      _state.dirtyClusters.add(i);
      updatePitchCurveForCluster(i);
    }

    generateCorrectionCurve();

    if (_state.selectedIdx === idx) {
      showClusterDetails(idx, _state.clusters[idx]);
    }

    log(`✓ ${indices.length} cluster(s) ramp: in=${rampInMs.toFixed(0)}ms, out=${rampOutMs.toFixed(0)}ms`);
  }

  // ---- DRAW BOX CALLBACK ----

  async function onDrawBox(startTime, endTime) {
    // Check for overlaps with existing clusters
    for (const c of _state.clusters) {
      if (!(endTime <= c.start_time || startTime >= c.end_time)) {
        log('Cannot draw box: overlaps with existing cluster', 'warn');
        return;
      }
    }
    
    // Gather pitch points in this range
    const points = [];
    for (let i = 0; i < _state.times.length; i++) {
      const t = _state.times[i];
      const f = _state.frequencies[i];
      if (t >= startTime && t <= endTime && f && !isNaN(f)) {
        points.push({ time: t, freq: f });
      }
    }
    
    if (points.length === 0) {
      log('No pitch data in selected range', 'warn');
      return;
    }
    
    // Calculate mean frequency
    const meanFreq = points.reduce((sum, p) => sum + p.freq, 0) / points.length;
    
    // Determine note name
    const noteFreqMap = [
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
    
    let bestNote = 'A4';
    let bestDev = Infinity;
    for (const [note, baseFreq] of noteFreqMap) {
      const cents = Math.abs(1200 * Math.log2(meanFreq / baseFreq));
      if (cents < bestDev) {
        bestDev = cents;
        bestNote = note;
      }
    }
    
    // Create new cluster
    const newCluster = {
      id: _state.clusters.length,
      note: bestNote,
      start_time: startTime,
      end_time: endTime,
      mean_freq: meanFreq,
      duration_ms: (endTime - startTime) * 1000,
      pitch_shift_semitones: 0,
      ramp_in_ms: getParams().transition_ramp_ms,
      ramp_out_ms: getParams().transition_ramp_ms,
      correction_strength: getParams().correction_strength,
      smoothing_percent: 0,
      manually_edited: true,
      times: points.map(p => p.time),
      frequencies: points.map(p => p.freq),
    };
    
    // Insert in correct position (sorted by start_time)
    let insertIdx = _state.clusters.findIndex(c => c.start_time > startTime);
    if (insertIdx === -1) insertIdx = _state.clusters.length;
    
    _state.clusters.splice(insertIdx, 0, newCluster);
    _state.dirtyClusters.add(insertIdx);
    
    // Re-render (null times/freqs to preserve zoom)
    PitchPlot.render(null, null, _state.clusters, null);
    generateCorrectionCurve();

    log(`✓ New cluster created: ${bestNote} at ${startTime.toFixed(2)}s, ${points.length} points`);
  }

  // ---- DELETE CALLBACK (from PitchPlot) ----
  // No-op: actual deletion is handled by deleteSelectedCluster() via keyboard/UI.
  // PitchPlot.deleteCluster() is no longer called directly — main.js drives deletion.
  function onClusterDelete(idx) {}

  // ---- CALCULATE PITCH CURVE ----

  // Find the maximum available ramp space before/after a cluster by checking ALL clusters.
  // Returns { spaceBefore, spaceAfter } in seconds.
  function _getRampSpace(cluster) {
    const allClusters = _state.clusters;
    let spaceBefore = cluster.start_time;  // default: from time 0
    let spaceAfter = Infinity;
    for (const other of allClusters) {
      if (other === cluster) continue;
      // Nearest cluster ending before this one starts
      if (other.end_time <= cluster.start_time) {
        const gap = cluster.start_time - other.end_time;
        if (gap < spaceBefore) spaceBefore = gap;
      }
      // Nearest cluster starting after this one ends
      if (other.start_time >= cluster.end_time) {
        const gap = other.start_time - cluster.end_time;
        if (gap < spaceAfter) spaceAfter = gap;
      }
    }
    return { spaceBefore, spaceAfter };
  }

  // Calculate intrusion of clusterA's ramp-out into clusterA when transitioning to clusterB.
  function _getIntrusionOutForCluster(clusterA, clusterB) {
    if (!clusterA || !clusterB) return 0;
    const gap = clusterB.start_time - clusterA.end_time;
    if (gap <= 0) return 0;
    const rampOutA = (clusterA.ramp_out_ms || 50) / 1000.0;
    const rampInB  = (clusterB.ramp_in_ms  || 50) / 1000.0;
    const desired = rampOutA + rampInB;
    if (gap >= desired) return 0;
    const shortfall = desired - gap;
    const halfA = (clusterA.end_time - clusterA.start_time) / 2;
    return Math.min(shortfall / 2, halfA);
  }

  // Calculate intrusion of clusterB's ramp-in into clusterB when transitioning from clusterA.
  function _getIntrusionInForCluster(clusterA, clusterB) {
    if (!clusterA || !clusterB) return 0;
    const gap = clusterB.start_time - clusterA.end_time;
    if (gap <= 0) return 0;
    const rampOutA = (clusterA.ramp_out_ms || 50) / 1000.0;
    const rampInB  = (clusterB.ramp_in_ms  || 50) / 1000.0;
    const desired = rampOutA + rampInB;
    if (gap >= desired) return 0;
    const shortfall = desired - gap;
    const halfB = (clusterB.end_time - clusterB.start_time) / 2;
    return Math.min(shortfall / 2, halfB);
  }

  // Direct JS mirror of audio_engine.py::generate_pitch_map.
  // Returns the semitone shift that rubberband will apply at time t (in seconds),
  // using the same corrected-only filter, gap threshold, and ramp logic as the server.
  // This ensures the preview and the processed audio are calculated identically.
  function computeShiftAtTime(t) {
    // Mirror server: only clusters with a non-zero shift or smoothing enter the pitch map.
    const corrected = _state.clusters.filter(c => c.pitch_shift_semitones !== 0 || (c.smoothing_percent || 0) !== 0);
    if (corrected.length === 0) return 0;

    for (let i = 0; i < corrected.length; i++) {
      const c = corrected[i];
      const rampInS  = (c.ramp_in_ms  || 50) / 1000.0;
      const rampOutS = (c.ramp_out_ms || 50) / 1000.0;

      const prev = i > 0 ? corrected[i - 1] : null;
      const nxt  = i < corrected.length - 1 ? corrected[i + 1] : null;

      // Clamp ramps to not overlap ANY cluster (including uncorrected)
      const { spaceBefore, spaceAfter } = _getRampSpace(c);
      let effRampInS  = Math.min(rampInS, spaceBefore);
      let effRampOutS = Math.min(rampOutS, spaceAfter);

      // Handle gap overlap between adjacent CORRECTED clusters
      const gapPrevS = prev ? (c.start_time - prev.end_time) : Infinity;
      const gapNextS = nxt  ? (nxt.start_time - c.end_time)  : Infinity;
      const clusterDuration = c.end_time - c.start_time;
      const clusterHalfS = clusterDuration / 2;

      let gapOverlapsPrev = false;
      let intrusionInS = 0;
      if (prev !== null) {
        const prevRampOutS = (prev.ramp_out_ms || 50) / 1000.0;
        const desiredTransition = prevRampOutS + rampInS;
        if (gapPrevS <= 0) {
          effRampInS = 0;
          gapOverlapsPrev = true;
        } else if (gapPrevS < desiredTransition) {
          gapOverlapsPrev = true;
          effRampInS = 0;
          const shortfall = desiredTransition - gapPrevS;
          intrusionInS = Math.min(shortfall / 2, clusterHalfS);
        }
      }

      let gapOverlapsNext = false;
      let intrusionOutS = 0;
      if (nxt !== null) {
        const nxtRampInS = (nxt.ramp_in_ms || 50) / 1000.0;
        const desiredTransition = rampOutS + nxtRampInS;
        if (gapNextS <= 0) {
          effRampOutS = 0;
          gapOverlapsNext = true;
        } else if (gapNextS < desiredTransition) {
          gapOverlapsNext = true;
          effRampOutS = 0;
          const shortfall = desiredTransition - gapNextS;
          intrusionOutS = Math.min(shortfall / 2, clusterHalfS);
        }
      }

      const adjustedStart = c.start_time + intrusionInS;
      const adjustedEnd   = c.end_time   - intrusionOutS;

      const rampInStart = gapOverlapsPrev
        ? (prev ? prev.end_time - _getIntrusionOutForCluster(prev, c) : c.start_time)
        : c.start_time - effRampInS;
      const rampOutEnd  = gapOverlapsNext
        ? (nxt ? nxt.start_time + _getIntrusionInForCluster(c, nxt) : c.end_time)
        : c.end_time + effRampOutS;

      // Skip clusters whose zone doesn't cover t.
      if (t < rampInStart || t > rampOutEnd) continue;

      // Interior of cluster (non-intruded zone): full shift.
      if (t >= adjustedStart && t <= adjustedEnd) {
        return c.pitch_shift_semitones;
      }

      // Intrusion zone at start: transition from prev's shift to this shift
      if (gapOverlapsPrev && intrusionInS > 0 && t >= c.start_time && t < adjustedStart) {
        const fromShift = prev ? prev.pitch_shift_semitones : 0;
        const totalTransition = gapPrevS + intrusionInS + _getIntrusionOutForCluster(prev, c);
        const transitionStart = prev ? prev.end_time - _getIntrusionOutForCluster(prev, c) : c.start_time;
        const progress = (t - transitionStart) / totalTransition;
        return fromShift + (c.pitch_shift_semitones - fromShift) * Math.max(0, Math.min(1, progress));
      }

      // Intrusion zone at end: transition from this shift to next's shift
      if (gapOverlapsNext && intrusionOutS > 0 && t > adjustedEnd && t <= c.end_time) {
        const toShift = nxt ? nxt.pitch_shift_semitones : 0;
        const totalTransition = intrusionOutS + gapNextS + _getIntrusionInForCluster(c, nxt);
        const progress = (t - adjustedEnd) / totalTransition;
        return c.pitch_shift_semitones + (toShift - c.pitch_shift_semitones) * Math.max(0, Math.min(1, progress));
      }

      // Ramp in (outside cluster): blend to base_shift at cluster start.
      if (t >= rampInStart && t < c.start_time) {
        const fromShift = (prev && gapOverlapsPrev) ? prev.pitch_shift_semitones : 0;
        const totalRamp = gapOverlapsPrev
          ? gapPrevS + intrusionInS + _getIntrusionOutForCluster(prev, c)
          : effRampInS;
        if (totalRamp <= 0) return c.pitch_shift_semitones;
        const transitionStart = gapOverlapsPrev && prev
          ? prev.end_time - _getIntrusionOutForCluster(prev, c)
          : rampInStart;
        const progress = (t - transitionStart) / totalRamp;
        return fromShift + (c.pitch_shift_semitones - fromShift) * Math.max(0, Math.min(1, progress));
      }

      // Ramp out (outside cluster): blend from base_shift at cluster end.
      if (t > c.end_time && t <= rampOutEnd) {
        const toShift = (nxt && gapOverlapsNext) ? nxt.pitch_shift_semitones : 0;
        const totalRamp = gapOverlapsNext
          ? intrusionOutS + gapNextS + _getIntrusionInForCluster(c, nxt)
          : effRampOutS;
        if (totalRamp <= 0) return c.pitch_shift_semitones;
        const progress = (t - adjustedEnd) / totalRamp;
        return c.pitch_shift_semitones + (toShift - c.pitch_shift_semitones) * Math.max(0, Math.min(1, progress));
      }
    }

    return 0; // t is between clusters, outside all ramp zones.
  }

  // Generate correction curve: shows cents of correction relative to zero.
  // Ramps happen entirely outside clusters; interior is flat at correction value.
  // When gap is large enough: ramp to 0, break, ramp from 0.
  // When gap is too small for full ramps: direct line from A's correction to B's.
  function generateCorrectionCurve() {
    const corrected = _state.clusters.filter(c =>
      c.pitch_shift_semitones !== 0 || (c.smoothing_percent || 0) !== 0
    );

    if (corrected.length === 0) {
      PitchPlot.updateCorrectionCurve([], []);
      return;
    }

    const times = [];
    const cents = [];

    for (let i = 0; i < corrected.length; i++) {
      const c = corrected[i];
      const corrCents = c.pitch_shift_semitones * 100;
      const rampInS  = (c.ramp_in_ms  || 50) / 1000.0;
      const rampOutS = (c.ramp_out_ms || 50) / 1000.0;

      const prev = i > 0 ? corrected[i - 1] : null;
      const nxt  = i < corrected.length - 1 ? corrected[i + 1] : null;

      // Clamp ramps to not overlap ANY cluster (including uncorrected)
      const { spaceBefore, spaceAfter } = _getRampSpace(c);
      const clampedRampInS  = Math.min(rampInS, spaceBefore);
      const clampedRampOutS = Math.min(rampOutS, spaceAfter);

      const gapPrevS = prev ? (c.start_time - prev.end_time) : Infinity;
      const gapNextS = nxt  ? (nxt.start_time - c.end_time)  : Infinity;
      const clusterHalfS = (c.end_time - c.start_time) / 2;

      // Determine if gap is too small for full ramps (overlap case).
      let gapOverlapsPrev = false;
      let intrusionInS = 0;
      if (prev !== null) {
        const prevRampOutS = (prev.ramp_out_ms || 50) / 1000.0;
        const desiredTransition = prevRampOutS + rampInS;
        if (gapPrevS <= 0) {
          gapOverlapsPrev = true;
        } else if (gapPrevS < desiredTransition) {
          gapOverlapsPrev = true;
          const shortfall = desiredTransition - gapPrevS;
          intrusionInS = Math.min(shortfall / 2, clusterHalfS);
        }
      }

      let gapOverlapsNext = false;
      let intrusionOutS = 0;
      if (nxt !== null) {
        const nxtRampInS = (nxt.ramp_in_ms || 50) / 1000.0;
        const desiredTransition = rampOutS + nxtRampInS;
        if (gapNextS <= 0) {
          gapOverlapsNext = true;
        } else if (gapNextS < desiredTransition) {
          gapOverlapsNext = true;
          const shortfall = desiredTransition - gapNextS;
          intrusionOutS = Math.min(shortfall / 2, clusterHalfS);
        }
      }

      const adjustedStart = c.start_time + intrusionInS;
      const adjustedEnd   = c.end_time   - intrusionOutS;

      // --- Ramp in ---
      // When gap overlaps with intrusion: prev's ramp-out already emitted the
      // transition start; we emit (adjustedStart, corrCents) so the line extends
      // into the cluster maintaining the full transition time.
      // When no overlap: emit ramp from 0 to corrCents before cluster start.
      if (!gapOverlapsPrev) {
        const rampInStart = c.start_time - clampedRampInS;
        times.push(rampInStart);
        cents.push(0);
        // Cluster start
        times.push(c.start_time);
        cents.push(corrCents);
      } else {
        // Overlap: transition ends at adjustedStart inside the cluster
        times.push(adjustedStart);
        cents.push(corrCents);
      }

      // --- Interior: flat at correction value ---
      times.push(adjustedEnd);
      cents.push(corrCents);

      // --- Ramp out ---
      // When gap overlaps with intrusion: transition starts at adjustedEnd inside
      // the cluster. Next cluster's ramp-in will close the transition.
      // When no overlap: ramp down to 0.
      if (!gapOverlapsNext) {
        const rampOutEnd = c.end_time + clampedRampOutS;
        times.push(rampOutEnd);
        cents.push(0);

        // Add null separator if there's a real gap to next cluster's ramp zone
        if (nxt) {
          times.push(null);
          cents.push(null);
        }
      }
      // When gapOverlapsNext: line goes from (adjustedEnd, corrCents) to next's adjustedStart
    }

    console.log('[DEBUG] generateCorrectionCurve v3: points=', times.length,
      'sample cents=', cents.filter(v => v !== null).slice(0, 12));
    PitchPlot.updateCorrectionCurve(times, cents);
  }

  function updatePitchCurveForCluster(idx) {
    const cluster      = _state.clusters[idx];
    const buffer       = 0.3;
    const segmentStart = cluster.start_time - buffer;
    const segmentEnd   = cluster.end_time   + buffer;

    const newTimes = [];
    const newFreqs = [];
    const smoothCurve = parseFloat(document.getElementById('p_smooth_curve').value) || 1.0;

    // Precompute max deviation per cluster for power curve smoothing
    const clusterMaxDevCache = new Map();
    if (smoothCurve > 1.0) {
      for (const c of _state.clusters) {
        if (!c.smoothing_percent) continue;
        let maxDev = 0;
        for (let j = 0; j < _state.originalTimes.length; j++) {
          const tj = _state.originalTimes[j];
          const fj = _state.originalFrequencies[j];
          if (tj >= c.start_time && tj <= c.end_time && fj && !isNaN(fj)) {
            const dev = Math.abs(12 * Math.log2(fj / c.mean_freq));
            if (dev > maxDev) maxDev = dev;
          }
        }
        clusterMaxDevCache.set(c, maxDev || 1);
      }
    }

    for (let i = 0; i < _state.originalTimes.length; i++) {
      const t     = _state.originalTimes[i];
      const origF = _state.originalFrequencies[i];

      if (t < segmentStart || t > segmentEnd) continue;

      newTimes.push(t);

      if (origF === null || isNaN(origF)) {
        newFreqs.push(null);
        continue;
      }

      // Apply overall pitch shift
      const shiftedF = origF * Math.pow(2, computeShiftAtTime(t) / 12);

      // Find which cluster owns this frame and apply its smoothing.
      // Smoothing reduces per-frame deviation from mean_freq in semitone space,
      // independently of the correction shift (which is already baked into shiftedF).
      // This way smoothing always targets mean_freq, never the chromatic reference.
      const owningCluster = _state.clusters.find(c => t >= c.start_time && t <= c.end_time);
      if (owningCluster && owningCluster.smoothing_percent > 0) {
        const smoothing          = owningCluster.smoothing_percent / 100;
        const deviationSemitones = 12 * Math.log2(origF / owningCluster.mean_freq);
        const correctionShift    = owningCluster.pitch_shift_semitones;

        let smoothedDeviation;
        if (smoothCurve <= 1.0) {
          // Linear (original behavior)
          smoothedDeviation = deviationSemitones * (1 - smoothing);
        } else {
          // Power curve: remaining = sign(d) * (|d|/max)^(1/curve) * max * (1-smoothing)
          const maxDev = clusterMaxDevCache.get(owningCluster) || 1;
          const absDev = Math.abs(deviationSemitones);
          const norm = absDev / maxDev;
          const curvedNorm = Math.pow(norm, 1.0 / smoothCurve);
          smoothedDeviation = Math.sign(deviationSemitones) * curvedNorm * maxDev * (1 - smoothing);
        }

        newFreqs.push(owningCluster.mean_freq * Math.pow(2, (smoothedDeviation + correctionShift) / 12));
      } else {
        newFreqs.push(shiftedF);
      }
    }

    if (newTimes.length > 0) {
      PitchPlot.updatePitchSegment(newTimes, newFreqs, segmentStart, segmentEnd);
    }
  }

  // ---- PROCESS DIRTY CLUSTERS ----

  async function processDirtyClusters() {
    if (_state.dirtyClusters.size === 0) return;

    showProcessing(true);
    log(`Syncing ${_state.clusters.length} cluster(s) via full-audio pass...`);

    try {
      // Send the entire cluster list — the server replaces its state wholesale.
      const clusterUpdates = _state.clusters.map((c, idx) => ({
        idx,
        start_time:            c.start_time,
        end_time:              c.end_time,
        note:                  c.note,
        mean_freq:             c.mean_freq,
        pitch_shift_semitones: c.pitch_shift_semitones,
        ramp_in_ms:            c.ramp_in_ms,
        ramp_out_ms:           c.ramp_out_ms,
        correction_strength:   c.correction_strength,
        smoothing_percent:     c.smoothing_percent,
        manually_edited:       c.manually_edited || false,
      }));

      // Pitch map is computed entirely server-side from cluster parameters
      // and the original analysis frequencies.  The client pitch preview is
      // a visual aid, not a source of truth.
      const result = await API.syncClusters(clusterUpdates);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      // Sync server-returned cluster states back to client.
      _state.clusters = result.clusters;

      // Re-sync PitchPlot's internal cluster references to the freshly baked state.
      PitchPlot.render(null, null, _state.clusters, null);

      // Re-analyze pitch for each cluster so the plot shows actual corrected pitch.
      const buffer = 0.3;
      for (const cluster of _state.clusters) {
        if (!cluster) continue;
        const segResult = await API.analyzeSegment(
          cluster.start_time - buffer,
          cluster.end_time   + buffer
        );
        if (segResult.ok) {
          PitchPlot.updatePitchSegment(
            segResult.times, segResult.frequencies,
            segResult.start_time, segResult.end_time
          );
        }
      }

      Waveform.load(API.audioUrl());
      _state.dirtyClusters.clear();
      generateCorrectionCurve();
      log(`✓ All edits processed`);

    } catch (e) {
      log(`Error: ${e}`, 'error');
    } finally {
      showProcessing(false);
    }
  }

  // ---- ANALYZE ----

  async function runAnalyze() {
    if (!_state.audioLoaded) {
      log('Please upload an audio file first', 'warn');
      return;
    }

    showProcessing(true);
    log('Analyzing audio...');

    try {
      const params = getParams();
      const result = await API.analyze(params);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      _state.clusters = result.clusters;
      _state.times = result.times;
      _state.frequencies = result.frequencies;
      _state.originalTimes = [...result.times];
      _state.originalFrequencies = [...result.frequencies];

      PitchPlot.render(
        result.times,
        result.frequencies,
        result.clusters,
        result.midi_notes
      );

      Waveform.load(API.audioUrl());

      // Update avg pitch deviation display
      const devEl = document.getElementById('avgPitchDeviation');
      if (result.avg_pitch_deviation_cents != null) {
        devEl.textContent = result.avg_pitch_deviation_cents.toFixed(1);
      } else {
        devEl.textContent = '—';
      }

      generateCorrectionCurve();

      log(`✓ Analysis complete: ${result.cluster_count} clusters, ${result.duration.toFixed(1)}s`);
      document.getElementById('clusterDetails').innerHTML = '<p class="placeholder">Click a note box to select it</p>';

    } catch (e) {
      log(`Error: ${e}`, 'error');
    } finally {
      showProcessing(false);
    }
  }

  // ---- CORRECT ----

  async function runCorrect() {
    if (!_state.clusters.length) {
      log('Please run analysis first', 'warn');
      return;
    }

    showProcessing(true);
    log('Applying corrections...');

    try {
      const params = getParams();
      const result = await API.correct(params);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      _state.clusters = result.clusters;

      // Update cluster boxes
      PitchPlot.render(null, null, result.clusters, null);

      // Update pitch curve for every cluster and mark all dirty
      for (let i = 0; i < _state.clusters.length; i++) {
        updatePitchCurveForCluster(i);
        _state.dirtyClusters.add(i);
      }
      generateCorrectionCurve();

      log('✓ Corrections calculated — press Update Audio to apply');

    } catch (e) {
      log(`Error: ${e}`, 'error');
    } finally {
      showProcessing(false);
    }
  }

  // ---- EXPORT ----

  function runExport() {
    log('Downloading corrected audio...');
    window.location.href = API.exportUrl();
  }

  // ---- FILE UPLOADS ----

  async function handleAudioUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    showProcessing(true);
    log(`Uploading ${file.name}...`);

    try {
      const result = await API.uploadAudio(file);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }
      _state.audioLoaded = true;
      document.getElementById('fileStatus').textContent = `🎵 ${file.name}`;
      log(`✓ Audio uploaded: ${file.name}`);

      // Auto-analyze
      await runAnalyze();
    } catch (e) {
      log(`Error: ${e}`, 'error');
    } finally {
      showProcessing(false);
    }
  }

  async function handleMidiUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    showProcessing(true);
    log(`Uploading MIDI ${file.name}...`);

    try {
      const result = await API.uploadMidi(file);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }
      _state.midiLoaded = true;
      const existing = document.getElementById('fileStatus').textContent;
      document.getElementById('fileStatus').textContent = existing + ` | 🎹 ${file.name} (${result.note_count} notes)`;
      log(`✓ MIDI loaded: ${result.message}`);
      if (_state.audioLoaded) await runAnalyze();
    } catch (e) {
      log(`Error: ${e}`, 'error');
    } finally {
      showProcessing(false);
    }
  }

  // ---- DELETE SELECTED CLUSTER ----

  async function deleteSelectedCluster() {
    if (_state.selectedIdx === null) return;

    const idx = _state.selectedIdx;
    const cluster = _state.clusters[idx];

    showProcessing(true);
    log(`Deleting cluster ${idx + 1} (${cluster.note}), restoring original audio...`);

    try {
      const result = await API.deleteCluster(idx);

      if (result.error) {
        log(`Error deleting cluster: ${result.error}`, 'error');
        return;
      }

      // Remap dirty cluster indices: anything above deleted idx shifts down by 1,
      // the deleted index itself is dropped.
      const newDirty = new Set();
      for (const dirtyIdx of _state.dirtyClusters) {
        if (dirtyIdx < idx) newDirty.add(dirtyIdx);
        else if (dirtyIdx > idx) newDirty.add(dirtyIdx - 1);
        // dirtyIdx === idx: silently drop — cluster no longer exists
      }
      _state.dirtyClusters = newDirty;

      // Update client-side cluster list to match server
      _state.clusters = result.clusters;
      _state.selectedIdx = null;

      // Re-analyze pitch for the restored segment so the plot reflects the original audio
      const buffer = 0.3;
      const segResult = await API.analyzeSegment(
        cluster.start_time - buffer,
        cluster.end_time + buffer
      );
      if (segResult.ok) {
        PitchPlot.updatePitchSegment(
          segResult.times, segResult.frequencies,
          segResult.start_time, segResult.end_time
        );
      }

      // Sync plot boxes and reload waveform audio (null times/freqs to preserve zoom)
      PitchPlot.render(null, null, _state.clusters, null);
      Waveform.load(API.audioUrl());
      generateCorrectionCurve();

      document.getElementById('clusterDetails').innerHTML =
        '<p class="placeholder">Click a note box to select it</p>';

      log(`✓ Cluster ${idx + 1} deleted and audio restored`);

    } catch (e) {
      log(`Error: ${e}`, 'error');
    } finally {
      showProcessing(false);
    }
  }

  // ---- INIT ----

  function init() {
    // Wire up file inputs
    document.getElementById('audioFile').addEventListener('change', handleAudioUpload);
    document.getElementById('midiFile').addEventListener('change', handleMidiUpload);

    // Wire up buttons
    document.getElementById('btnAnalyze').addEventListener('click', runAnalyze);
    document.getElementById('btnCorrect').addEventListener('click', runCorrect);
    document.getElementById('btnUpdateAudio').addEventListener('click', processDirtyClusters);
    document.getElementById('btnExport').addEventListener('click', runExport);

    // Overlay toggles
    document.getElementById('chkMidi').addEventListener('change', (e) => {
      PitchPlot.setShowMidi(e.target.checked);
    });
    document.getElementById('chkCorrectionCurve').addEventListener('change', (e) => {
      PitchPlot.setShowCorrectionCurve(e.target.checked);
    });

    // Initialize pitch plot
    PitchPlot.init({
      onSelect: (idx, cluster) => showClusterDetails(idx, cluster),
      onDrag: (idx, shift) => onClusterDrag(idx, shift),
      onResize: (idx) => onClusterResize(idx),
      onDrawBox: (start, end) => onDrawBox(start, end),
      onDelete: (idx) => onClusterDelete(idx),
      onSmoothing: (idx, smoothing) => onClusterSmoothing(idx, smoothing),
      onRampDrag: (idx, rampIn, rampOut) => onClusterRampDrag(idx, rampIn, rampOut),
    });

    // Initialize waveform with playhead sync
    Waveform.init((time) => {
      PitchPlot.updatePlayhead(time);
    });

    // Play button - just plays (no auto-processing)
    const btnPlay = document.getElementById('btnPlay');
    btnPlay.addEventListener('click', () => {
      Waveform.togglePlay();
    });

    // Spacebar play/pause
    document.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        Waveform.togglePlay();
      }
      
      // Delete key to delete selected cluster
      if ((e.key === 'Delete' || e.key === 'Backspace') && e.target.tagName !== 'INPUT') {
        if (_state.selectedIdx !== null) {
          e.preventDefault();
          deleteSelectedCluster(); // async — fire and forget is fine here
        }
      }
    });

    log('Vocal Editor GUI ready. Upload an audio file to begin.');
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', () => App.init());
