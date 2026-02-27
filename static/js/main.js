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

    panel.innerHTML = `
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
        <label>Transition ramp (ms)</label>
        <input type="number" id="cn_transition_ramp_ms" value="${cluster.transition_ramp_ms}">
      </div>
      <div class="cluster-param-row">
        <label>Correction strength (%)</label>
        <input type="number" id="cn_correction_strength" value="${cluster.correction_strength}" min="0" max="100">
      </div>
      <div class="cluster-param-row">
        <label>Smoothing (%)</label>
        <input type="number" id="cn_smoothing_percent" value="${cluster.smoothing_percent}" min="0" max="100">
      </div>

      <button class="btn btn-primary" id="btnApplyCluster">Apply to note</button>
    `;

    document.getElementById('btnApplyCluster').addEventListener('click', applyClusterEdit);
  }

  async function applyClusterEdit() {
    if (_state.selectedIdx === null) return;

    const idx = _state.selectedIdx;
    const updates = {
      transition_ramp_ms:  parseFloat(document.getElementById('cn_transition_ramp_ms').value),
      correction_strength: parseFloat(document.getElementById('cn_correction_strength').value),
      smoothing_percent:   parseFloat(document.getElementById('cn_smoothing_percent').value),
    };

    const cluster = _state.clusters[idx];
    Object.assign(cluster, updates);
    cluster.manually_edited = true;
    _state.dirtyClusters.add(idx);

    PitchPlot.updateCluster(idx, cluster);
    updatePitchCurveForCluster(idx); // Update pitch curve with new ramp/strength
    showClusterDetails(idx, cluster);
    log(`✓ Cluster ${idx + 1} parameters updated (will process on playback)`);
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
    
    if (_state.selectedIdx === idx) {
      showClusterDetails(idx, cluster);
    }
    
    log(`✓ Cluster ${idx + 1} resized to ${cluster.duration_ms.toFixed(0)}ms`);
  }

  // ---- SMOOTHING CALLBACK ----

  async function onClusterSmoothing(idx, newSmoothing) {
    _state.clusters[idx].smoothing_percent = newSmoothing;
    _state.clusters[idx].manually_edited = true;
    _state.dirtyClusters.add(idx);

    // Update the smoothing input in the details panel if this cluster is selected
    if (_state.selectedIdx === idx) {
      const smoothingInput = document.getElementById('cn_smoothing_percent');
      if (smoothingInput) smoothingInput.value = newSmoothing.toFixed(1);
    }

    // Immediate approximate preview
    updatePitchCurveForCluster(idx);

    log(`✓ Cluster ${idx + 1} smoothing set to ${newSmoothing.toFixed(1)}%`);
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
      transition_ramp_ms: getParams().transition_ramp_ms,
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
    
    // Re-render
    PitchPlot.render(_state.times, _state.frequencies, _state.clusters, null);
    
    log(`✓ New cluster created: ${bestNote} at ${startTime.toFixed(2)}s, ${points.length} points`);
  }

  // ---- DELETE CALLBACK (from PitchPlot) ----
  // No-op: actual deletion is handled by deleteSelectedCluster() via keyboard/UI.
  // PitchPlot.deleteCluster() is no longer called directly — main.js drives deletion.
  function onClusterDelete(idx) {}

  // ---- CALCULATE PITCH CURVE ----

  // Direct JS mirror of audio_engine.py::generate_pitch_map.
  // Returns the semitone shift that rubberband will apply at time t (in seconds),
  // using the same corrected-only filter, gap threshold, and ramp logic as the server.
  // This ensures the preview and the processed audio are calculated identically.
  function computeShiftAtTime(t) {
    const gapThresholdMs = parseFloat(document.getElementById('p_gap_threshold_ms').value) || 150;

    // Mirror server: only clusters with a non-zero shift enter the pitch map.
    const corrected = _state.clusters.filter(c => c.pitch_shift_semitones !== 0);
    if (corrected.length === 0) return 0;

    for (let i = 0; i < corrected.length; i++) {
      const c         = corrected[i];
      const halfRampS = c.transition_ramp_ms / 2000.0;
      const prev      = i > 0 ? corrected[i - 1] : null;
      const nxt       = i < corrected.length - 1 ? corrected[i + 1] : null;

      const gapPrevMs = prev ? (c.start_time - prev.end_time) * 1000 : Infinity;
      const gapNextMs = nxt  ? (nxt.start_time - c.end_time)  * 1000 : Infinity;

      const rampInStart  = c.start_time - halfRampS;
      const rampInEnd    = c.start_time + halfRampS;
      const rampOutStart = c.end_time   - halfRampS;
      const rampOutEnd   = c.end_time   + halfRampS;

      // Skip clusters whose ramp zone doesn't cover t.
      if (t < rampInStart || t > rampOutEnd) continue;

      if (t >= rampInEnd && t <= rampOutStart) {
        // Interior of cluster: full shift.
        return c.pitch_shift_semitones;
      }

      if (t >= rampInStart && t < rampInEnd) {
        // Ramp in: blend from previous note's shift (if close) or 0.
        const fromShift = (gapPrevMs < gapThresholdMs && prev)
          ? prev.pitch_shift_semitones : 0;
        const progress = (t - rampInStart) / (rampInEnd - rampInStart);
        return fromShift + (c.pitch_shift_semitones - fromShift) * progress;
      }

      if (t > rampOutStart && t <= rampOutEnd) {
        // Ramp out: blend to next note's shift (if close) or 0.
        const toShift = (gapNextMs < gapThresholdMs && nxt)
          ? nxt.pitch_shift_semitones : 0;
        const progress = (t - rampOutStart) / (rampOutEnd - rampOutStart);
        return c.pitch_shift_semitones + (toShift - c.pitch_shift_semitones) * progress;
      }
    }

    return 0; // t is between clusters, outside all ramp zones.
  }

  function updatePitchCurveForCluster(idx) {
    const cluster      = _state.clusters[idx];
    const buffer       = 0.3;
    const segmentStart = cluster.start_time - buffer;
    const segmentEnd   = cluster.end_time   + buffer;

    const newTimes = [];
    const newFreqs = [];

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
        const smoothedDeviation  = deviationSemitones * (1 - smoothing);
        const correctionShift    = owningCluster.pitch_shift_semitones;
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
        transition_ramp_ms:    c.transition_ramp_ms,
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

      // Sync plot boxes and reload waveform audio
      PitchPlot.render(_state.times, _state.frequencies, _state.clusters, null);
      Waveform.load(API.audioUrl());

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

    // Initialize pitch plot
    PitchPlot.init({
      onSelect: (idx, cluster) => showClusterDetails(idx, cluster),
      onDrag: (idx, shift) => onClusterDrag(idx, shift),
      onResize: (idx) => onClusterResize(idx),
      onDrawBox: (start, end) => onDrawBox(start, end),
      onDelete: (idx) => onClusterDelete(idx),
      onSmoothing: (idx, smoothing) => onClusterSmoothing(idx, smoothing),
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
