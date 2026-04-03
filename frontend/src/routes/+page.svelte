<script lang="ts">
  import Header from '$lib/components/Header.svelte';
  import ParameterPanel from '$lib/components/ParameterPanel.svelte';
  import ClusterPanel from '$lib/components/ClusterPanel.svelte';
  import PitchPlot from '$lib/components/PitchPlot.svelte';
  import WaveformPlayer from '$lib/components/WaveformPlayer.svelte';
  import LogPanel from '$lib/components/LogPanel.svelte';
  import HelpModal from '$lib/components/HelpModal.svelte';
  import TabBar from '$lib/components/TabBar.svelte';
  import TimeAlignmentView from '$lib/components/TimeAlignmentView.svelte';
  import TimeAlignmentParams from '$lib/components/TimeAlignmentParams.svelte';
  import TimeClusterPanel from '$lib/components/TimeClusterPanel.svelte';
  import MixerPanel from '$lib/components/MixerPanel.svelte';
  import DeclickerParams from '$lib/components/DeclickerParams.svelte';
  import DeclickerView from '$lib/components/DeclickerView.svelte';
  import DeclickerInfoPanel from '$lib/components/DeclickerInfoPanel.svelte';
  import DenoiserParams from '$lib/components/DenoiserParams.svelte';
  import DenoiserView from '$lib/components/DenoiserView.svelte';
  import DenoiserInfoPanel from '$lib/components/DenoiserInfoPanel.svelte';
  import EditParams from '$lib/components/EditParams.svelte';
  import EditView from '$lib/components/EditView.svelte';
  import EditInfoPanel from '$lib/components/EditInfoPanel.svelte';
  import * as api from '$lib/api';
  import {
    clusters, times, frequencies, originalTimes, originalFrequencies,
    midiNotes, midiWarnings, selectedIdx, selectedIndices, dirtyClusters,
    audioLoaded, audioUrl, processing, log,
    activeTab, timeEdits, dirtyTimeEdits, backendTimemap, advancedView,
    stretchMarkers, dirtyStretchMarkers,
    referenceClusters, referenceStretchMarkers,
    declickerDetections, declickerBandCenters, declickerBandPeaks, declickerApplied, selectedClickIdx,
    denoiserApplied, denoiserSpectrogramBefore, denoiserSpectrogramAfter, denoiserFreqAxis, denoiserTimeAxis,
    editClips, editSelectedClipIds, editAudioBuffer, editApplied, editCursorTime,
    editTimeSelection, waveformReset
  } from '$lib/stores/appState';
  import { params, getAllParams } from '$lib/stores/params';
  import { computeShiftAtTime, generateCorrectionCurve, computePitchCurve, closestNote } from '$lib/utils/pitchMath';
  import { get } from 'svelte/store';
  import type { Cluster, MidiWarning, StretchMarker, MidiNote } from '$lib/utils/types';
  import { encodeWav } from '$lib/utils/wavEncoder';

  let pitchPlot: PitchPlot;
  let timeAlignmentView: TimeAlignmentView;
  let declickerView: DeclickerView;
  let declickerParams: DeclickerParams;
  let denoiserView: DenoiserView;
  let denoiserParamsRef: DenoiserParams;
  let editView: EditView;
  let waveformPlayer: WaveformPlayer;

  // Edit tab settings
  let editZoomPercent = $state(20);
  let editNudgeMs = $state(50);


  // --- Pitch curve helpers ---

  function updatePitchCurveForCluster(idx: number) {
    const cls = get(clusters);
    const cluster = cls[idx];
    const buffer = 0.3;
    const segmentStart = cluster.start_time - buffer;
    const segmentEnd = cluster.end_time + buffer;
    const p = getAllParams();

    const result = computePitchCurve(
      get(originalTimes), get(originalFrequencies),
      cls, p.smooth_curve, segmentStart, segmentEnd
    );

    if (result.times.length > 0) {
      pitchPlot?.updatePitchSegment(result.times, result.freqs, segmentStart, segmentEnd);
    }
  }

  function updateAllPitchCurves() {
    const p = getAllParams();
    const result = computePitchCurve(
      get(originalTimes), get(originalFrequencies),
      get(clusters), p.smooth_curve
    );
    pitchPlot?.updatePitchSegment(result.times, result.freqs, -Infinity, Infinity);
  }

  function refreshCorrectionCurve() {
    const curve = generateCorrectionCurve(get(clusters));
    pitchPlot?.updateCorrectionCurve(curve.times, curve.cents);
  }

  // --- Callbacks from PitchPlot ---

  function onClusterSelect(idx: number, cluster: Cluster) {
    $selectedIdx = idx;
  }

  let _dragBatch: { idx: number; newShift: number }[] = [];
  let _dragBatchRaf: number | null = null;

  function onClusterDrag(idx: number, newShift: number) {
    _dragBatch.push({ idx, newShift });
    if (_dragBatchRaf !== null) return;
    _dragBatchRaf = requestAnimationFrame(() => {
      _dragBatchRaf = null;
      const batch = _dragBatch;
      _dragBatch = [];

      const newDirty = new Set($dirtyClusters);
      for (const { idx, newShift } of batch) {
        $clusters[idx].pitch_shift_semitones = newShift;
        $clusters[idx].manually_edited = true;
        newDirty.add(idx);
        updatePitchCurveForCluster(idx);
      }
      $dirtyClusters = newDirty;
      $clusters = $clusters;
      refreshCorrectionCurve();
      log(`${batch.length} cluster(s) moved`);
      autoProcessSegment();
    });
  }

  function onClusterResize(idx: number) {
    $clusters[idx].manually_edited = true;
    $dirtyClusters = new Set([...$dirtyClusters, idx]);
    $clusters = $clusters;

    updatePitchCurveForCluster(idx);
    refreshCorrectionCurve();
    log(`Cluster ${idx + 1} resized to ${$clusters[idx].duration_ms.toFixed(0)}ms`);
    autoProcessSegment();
  }

  function onClusterSmoothing(idx: number, newSmoothing: number) {
    const selIndices = get(selectedIndices);
    const indices = selIndices.size > 1 && selIndices.has(idx) ? Array.from(selIndices) : [idx];

    for (const i of indices) {
      $clusters[i].smoothing_percent = newSmoothing;
      $clusters[i].manually_edited = true;
      $dirtyClusters = new Set([...$dirtyClusters, i]);
      updatePitchCurveForCluster(i);
    }
    $clusters = $clusters;
    refreshCorrectionCurve();
    log(`${indices.length} cluster(s) smoothing set to ${newSmoothing.toFixed(1)}%`);
    autoProcessSegment();
  }

  function onClusterRampDrag(idx: number, rampIn: number, rampOut: number) {
    const selIndices = get(selectedIndices);
    const indices = selIndices.size > 1 && selIndices.has(idx) ? Array.from(selIndices) : [idx];

    for (const i of indices) {
      $clusters[i].ramp_in_ms = rampIn;
      $clusters[i].ramp_out_ms = rampOut;
      $clusters[i].manually_edited = true;
      $dirtyClusters = new Set([...$dirtyClusters, i]);
      updatePitchCurveForCluster(i);
    }
    $clusters = $clusters;
    refreshCorrectionCurve();
    log(`${indices.length} cluster(s) ramp: in=${rampIn.toFixed(0)}ms, out=${rampOut.toFixed(0)}ms`);
    autoProcessSegment();
  }

  async function onWarningFix(warning: MidiWarning) {
    const cls = get(clusters);
    const p = getAllParams();
    let targetIdx: number;

    if (warning.type === 'mismatch') {
      // Fix existing cluster: find by time range (not index, which may be stale)
      const matchIdx = cls.findIndex(c =>
        Math.abs(c.start_time - warning.start_time) < 0.01 &&
        Math.abs(c.end_time - warning.end_time) < 0.01
      );
      if (matchIdx === -1) return;
      const c = cls[matchIdx];
      const centsOff = 1200 * Math.log2(c.mean_freq / warning.midi_freq);
      c.pitch_shift_semitones = -centsOff / 100.0;
      c.correction_strength = 100;
      c.manually_edited = true;
      targetIdx = matchIdx;
      $clusters = cls;
      $dirtyClusters = new Set([...$dirtyClusters, targetIdx]);
      log(`Fixed cluster ${targetIdx + 1}: corrected to ${warning.midi_note}`);
    } else if (warning.type === 'missing') {
      // Create a new cluster at the MIDI position
      const t = get(times);
      const f = get(frequencies);
      const points: { time: number; freq: number }[] = [];
      for (let i = 0; i < t.length; i++) {
        const freq = f[i];
        if (t[i] >= warning.start_time && t[i] <= warning.end_time && freq && !isNaN(freq)) {
          points.push({ time: t[i], freq });
        }
      }

      if (points.length === 0) {
        log(`No audio to correct at ${warning.start_time.toFixed(2)}s–${warning.end_time.toFixed(2)}s`, 'warn');
        return;
      }

      // Check overlaps with existing clusters
      for (const c of cls) {
        if (!(warning.end_time <= c.start_time || warning.start_time >= c.end_time)) {
          log('Cannot create cluster: overlaps with existing cluster', 'warn');
          return;
        }
      }

      const meanFreq = points.reduce((sum, pt) => sum + pt.freq, 0) / points.length;
      const centsOff = 1200 * Math.log2(meanFreq / warning.midi_freq);

      const newCluster: Cluster = {
        note: warning.midi_note,
        start_time: warning.start_time,
        end_time: warning.end_time,
        mean_freq: meanFreq,
        duration_ms: (warning.end_time - warning.start_time) * 1000,
        pitch_shift_semitones: -centsOff / 100.0,
        ramp_in_ms: p.transition_ramp_ms,
        ramp_out_ms: p.transition_ramp_ms,
        correction_strength: 100,
        smoothing_percent: 0,
        manually_edited: true,
        times: points.map(pt => pt.time),
        frequencies: points.map(pt => pt.freq),
      };

      let insertIdx = cls.findIndex(c => c.start_time > warning.start_time);
      if (insertIdx === -1) insertIdx = cls.length;
      cls.splice(insertIdx, 0, newCluster);
      targetIdx = insertIdx;
      $clusters = cls;
      $dirtyClusters = new Set([...$dirtyClusters, targetIdx]);
      log(`Created cluster for MIDI ${warning.midi_note} at ${warning.start_time.toFixed(2)}s`);
    } else {
      return;
    }

    // Remove the resolved warning
    $midiWarnings = $midiWarnings.filter(w => w !== warning);

    // Update visuals
    updatePitchCurveForCluster(targetIdx);
    refreshCorrectionCurve();

    // Process the segment immediately
    $selectedIdx = targetIdx;
    await processSegment();
  }

  function onDrawBox(startTime: number, endTime: number) {
    const cls = get(clusters);
    // Check overlaps
    for (const c of cls) {
      if (!(endTime <= c.start_time || startTime >= c.end_time)) {
        log('Cannot draw box: overlaps with existing cluster', 'warn');
        return;
      }
    }

    const t = get(times);
    const f = get(frequencies);
    const points: { time: number; freq: number }[] = [];
    for (let i = 0; i < t.length; i++) {
      const freq = f[i];
      if (t[i] >= startTime && t[i] <= endTime && freq && !isNaN(freq)) {
        points.push({ time: t[i], freq });
      }
    }

    if (points.length === 0) {
      log('No pitch data in selected range', 'warn');
      return;
    }

    const meanFreq = points.reduce((sum, p) => sum + p.freq, 0) / points.length;
    const bestNote = closestNote(meanFreq);
    const p = getAllParams();

    const newCluster: Cluster = {
      note: bestNote,
      start_time: startTime,
      end_time: endTime,
      mean_freq: meanFreq,
      duration_ms: (endTime - startTime) * 1000,
      pitch_shift_semitones: 0,
      ramp_in_ms: p.transition_ramp_ms,
      ramp_out_ms: p.transition_ramp_ms,
      correction_strength: p.correction_strength,
      smoothing_percent: 0,
      manually_edited: true,
      times: points.map(p => p.time),
      frequencies: points.map(p => p.freq),
    };

    let insertIdx = cls.findIndex(c => c.start_time > startTime);
    if (insertIdx === -1) insertIdx = cls.length;

    const newClusters = [...cls];
    newClusters.splice(insertIdx, 0, newCluster);
    $clusters = newClusters;
    $dirtyClusters = new Set([...$dirtyClusters, insertIdx]);

    refreshCorrectionCurve();
    log(`New cluster created: ${bestNote} at ${startTime.toFixed(2)}s, ${points.length} points`);
  }

  async function processSegment() {
    const idx = $selectedIdx;
    if (idx === null) return;

    const cls = get(clusters);
    const c = cls[idx];
    const p = getAllParams();
    log(`Processing segment for cluster ${idx + 1} (${c.note})...`);

    try {
      const clusterUpdates = cls.map((c, i) => ({
        idx: i,
        start_time: c.start_time,
        end_time: c.end_time,
        note: c.note,
        mean_freq: c.mean_freq,
        pitch_shift_semitones: c.pitch_shift_semitones,
        ramp_in_ms: c.ramp_in_ms,
        ramp_out_ms: c.ramp_out_ms,
        correction_strength: c.correction_strength,
        smoothing_percent: c.smoothing_percent,
        manually_edited: c.manually_edited || false,
      }));
      const currentTimeEdits = get(timeEdits);
      const result = await api.correctCluster(idx, clusterUpdates, currentTimeEdits, p.segment_padding_ms, p.segment_crossfade_ms, p.segment_crop_ms, p.segment_neighbor_count);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      $audioUrl = api.audioUrl();
      const newDirty = new Set($dirtyClusters);
      newDirty.delete(idx);
      $dirtyClusters = newDirty;

      // Splice re-analyzed pitch data into the plot for the processed region
      if (result.times && result.frequencies && result.start_time != null && result.end_time != null) {
        pitchPlot?.updatePitchSegment(result.times, result.frequencies, result.start_time, result.end_time);
      }

      log(`Segment processed for cluster ${idx + 1}`);
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    }
  }

  function onClusterParamChange() {
    // Called when cluster panel sliders change
    const cls = get(clusters);
    const selIndices = get(selectedIndices);
    const indices = selIndices.size > 0 ? Array.from(selIndices) : ($selectedIdx !== null ? [$selectedIdx] : []);

    for (const i of indices) {
      updatePitchCurveForCluster(i);
    }
    refreshCorrectionCurve();
  }

  function autoProcessSegment() {
    const p = getAllParams();
    if (p.segment_auto_process && $selectedIdx !== null) {
      processSegment();
    }
  }

  async function processTimeSegment(markerIdx: number) {
    const p = getAllParams();
    const cls = get(clusters);
    const markers = get(stretchMarkers);

    if (markerIdx < 0 || markerIdx >= markers.length) return;

    log(`Processing time segment for marker ${markerIdx + 1}...`);

    try {
      const clusterUpdates = cls.map((c, i) => ({
        idx: i,
        start_time: c.start_time,
        end_time: c.end_time,
        note: c.note,
        mean_freq: c.mean_freq,
        pitch_shift_semitones: c.pitch_shift_semitones,
        ramp_in_ms: c.ramp_in_ms,
        ramp_out_ms: c.ramp_out_ms,
        correction_strength: c.correction_strength,
        smoothing_percent: c.smoothing_percent,
        manually_edited: c.manually_edited || false,
      }));

      const result = await api.processTimeSegment(
        markerIdx, clusterUpdates, markers,
        p.segment_padding_ms, p.segment_crossfade_ms, p.segment_crop_ms
      );

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      $audioUrl = api.audioUrl();
      $dirtyStretchMarkers = false;
      log(`Time segment processed for marker ${markerIdx + 1}`);
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    }
  }

  function autoProcessTimeSegment(markerIdx: number) {
    const p = getAllParams();
    if (p.segment_auto_process) {
      processTimeSegment(markerIdx);
    }
  }

  // --- Action buttons ---

  async function runAnalyze() {
    if (!get(audioLoaded)) {
      log('Please upload an audio file first', 'warn');
      return;
    }

    $processing = true;
    log('Analyzing audio...');

    try {
      const p = getAllParams();
      const result = await api.analyze(p);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      $clusters = result.clusters;
      $midiWarnings = [];
      $times = result.times;
      $frequencies = result.frequencies;
      $originalTimes = [...result.times];
      $originalFrequencies = [...result.frequencies];
      $midiNotes = result.midi_notes;
      $audioUrl = api.audioUrl();

      // Clear all edits (pitch + time)
      $dirtyClusters = new Set();
      $timeEdits = [];
      $dirtyTimeEdits = new Set();
      $stretchMarkers = [];
      $dirtyStretchMarkers = false;
      $backendTimemap = [];
      $selectedIndices = new Set();

      refreshCorrectionCurve();
      log(`Analysis complete: ${result.cluster_count} clusters, ${result.duration.toFixed(1)}s`);
      $selectedIdx = null;
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function runCorrect() {
    if (!get(clusters).length) {
      log('Please run analysis first', 'warn');
      return;
    }

    $processing = true;
    log('Applying corrections...');

    try {
      // Sync any unsynced clusters to backend first
      if (get(dirtyClusters).size > 0) {
        const cls = get(clusters);
        const clusterUpdates = cls.map((c, idx) => ({
          idx,
          start_time: c.start_time,
          end_time: c.end_time,
          note: c.note,
          mean_freq: c.mean_freq,
          pitch_shift_semitones: c.pitch_shift_semitones,
          ramp_in_ms: c.ramp_in_ms,
          ramp_out_ms: c.ramp_out_ms,
          correction_strength: c.correction_strength,
          smoothing_percent: c.smoothing_percent,
          manually_edited: c.manually_edited || false,
        }));
        const syncResult = await api.syncClusters(clusterUpdates, get(timeEdits), undefined, get(stretchMarkers));
        if (syncResult.error) {
          log(`Error syncing: ${syncResult.error}`, 'error');
          return;
        }
        $clusters = syncResult.clusters;
        $dirtyClusters = new Set();
      }

      const p = getAllParams();
      const result = await api.correct(p);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      $clusters = result.clusters;
      $midiWarnings = result.warnings ?? [];

      updateAllPitchCurves();
      refreshCorrectionCurve();

      // Apply corrections to audio
      const cls2 = get(clusters);
      const clusterUpdates2 = cls2.map((c, idx) => ({
        idx,
        start_time: c.start_time,
        end_time: c.end_time,
        note: c.note,
        mean_freq: c.mean_freq,
        pitch_shift_semitones: c.pitch_shift_semitones,
        ramp_in_ms: c.ramp_in_ms,
        ramp_out_ms: c.ramp_out_ms,
        correction_strength: c.correction_strength,
        smoothing_percent: c.smoothing_percent,
        manually_edited: c.manually_edited || false,
      }));
      const syncResult2 = await api.syncClusters(clusterUpdates2, get(timeEdits), undefined, get(stretchMarkers));
      if (syncResult2.error) {
        log(`Error applying: ${syncResult2.error}`, 'error');
        return;
      }
      $clusters = syncResult2.clusters;
      if (syncResult2.corrected_times && syncResult2.corrected_freqs) {
        pitchPlot?.updatePitchSegment(syncResult2.corrected_times, syncResult2.corrected_freqs, -Infinity, Infinity);
      }
      if (syncResult2.timemap) {
        $backendTimemap = syncResult2.timemap;
      }
      $audioUrl = api.audioUrl();
      $dirtyClusters = new Set();
      $dirtyTimeEdits = new Set();
      $dirtyStretchMarkers = false;

      log('Corrections applied');
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  function runExport() {
    log('Downloading corrected audio...');
    window.location.href = api.exportUrl();
  }

  // --- De-Clicker actions ---

  async function runDeclickerDetect() {
    if (!get(audioLoaded)) return;
    $processing = true;
    log('Detecting clicks...');
    try {
      const p = declickerParams.getParams();
      const result = await api.declickerDetect(p);
      if (result.ok) {
        $declickerDetections = result.clicks || [];
        $declickerBandCenters = result.band_centers || [];
        $declickerBandPeaks = result.band_peaks || [];
        $selectedClickIdx = null;
        log(`Detected ${result.click_count} clicks`);
      } else {
        log(`Detection failed: ${result.error}`, 'error');
      }
    } catch (e) {
      log(`Detection error: ${e}`, 'error');
    }
    $processing = false;
  }

  async function runDeclickerApply() {
    if (!get(audioLoaded)) return;
    $processing = true;
    log('Applying de-click...');
    try {
      const p = declickerParams.getParams();
      const result = await api.declickerApply(p);
      console.log('[declicker apply] response:', result);
      if (result.ok) {
        $declickerDetections = result.clicks || [];
        $declickerApplied = true;
        $selectedClickIdx = null;
        $audioUrl = api.declickerAudioUrl();
        log(`De-click applied: ${result.click_count} clicks repaired in ${result.num_passes_run} pass(es)`);
      } else {
        log(`Apply failed: ${result.error}`, 'error');
        console.error('[declicker apply] error:', result.error, result.traceback);
      }
    } catch (e) {
      log(`Apply error: ${e}`, 'error');
    }
    $processing = false;
  }

  async function runDeclickerPreview() {
    $processing = true;
    log('Generating click preview...');
    try {
      const result = await api.declickerPreview();
      if (result.ok) {
        log('Preview ready — isolated clicks audio generated');
      } else {
        log(`Preview failed: ${result.error}`, 'error');
      }
    } catch (e) {
      log(`Preview error: ${e}`, 'error');
    }
    $processing = false;
  }

  async function runDeclickerReset() {
    try {
      await api.declickerReset();
      $declickerDetections = [];
      $declickerBandCenters = [];
      $declickerBandPeaks = [];
      $declickerApplied = false;
      $selectedClickIdx = null;
      $audioUrl = api.audioUrl();
      log('De-clicker reset');
    } catch (e) {
      log(`Reset error: ${e}`, 'error');
    }
  }

  function runDeclickerExport() {
    log('Downloading de-clicked audio...');
    window.location.href = api.declickerExportUrl();
  }

  // --- Denoiser actions ---

  async function runDenoiserAnalyze() {
    if (!get(audioLoaded)) return;
    $processing = true;
    log('Analyzing noise...');
    try {
      const p = denoiserParamsRef.getParams();
      const result = await api.denoiserAnalyze(p);
      if (result.ok) {
        $denoiserSpectrogramBefore = result.spectrogram_before || null;
        $denoiserSpectrogramAfter = result.spectrogram_after || null;
        $denoiserFreqAxis = result.freq_axis || null;
        $denoiserTimeAxis = result.time_axis || null;
        log('Noise analysis complete');
      } else {
        log(`Analysis failed: ${result.error}`, 'error');
      }
    } catch (e) {
      log(`Analysis error: ${e}`, 'error');
    }
    $processing = false;
  }

  async function runDenoiserApply() {
    if (!get(audioLoaded)) return;
    $processing = true;
    log('Applying denoise...');
    try {
      const p = denoiserParamsRef.getParams();
      const result = await api.denoiserApply(p);
      if (result.ok) {
        $denoiserSpectrogramBefore = result.spectrogram_before || null;
        $denoiserSpectrogramAfter = result.spectrogram_after || null;
        $denoiserFreqAxis = result.freq_axis || null;
        $denoiserTimeAxis = result.time_axis || null;
        $denoiserApplied = true;
        $audioUrl = api.denoiserAudioUrl();
        log('Denoise applied');
      } else {
        log(`Denoise failed: ${result.error}`, 'error');
      }
    } catch (e) {
      log(`Denoise error: ${e}`, 'error');
    }
    $processing = false;
  }

  async function runDenoiserReset() {
    try {
      await api.denoiserReset();
      $denoiserApplied = false;
      $denoiserSpectrogramBefore = null;
      $denoiserSpectrogramAfter = null;
      $denoiserFreqAxis = null;
      $denoiserTimeAxis = null;
      $audioUrl = api.audioUrl();
      denoiserView?.clearSelection();
      log('Denoiser reset');
    } catch (e) {
      log(`Reset error: ${e}`, 'error');
    }
  }

  function runDenoiserExport() {
    log('Downloading denoised audio...');
    window.location.href = api.denoiserExportUrl();
  }

  // --- Fine Edit ---
  async function runEditCommit() {
    const buffer = get(editAudioBuffer);
    const clips = get(editClips);
    if (!buffer || clips.length === 0) {
      log('No audio or clips to commit', 'warn');
      return;
    }

    $processing = true;
    log('Rendering edit arrangement...');

    try {
      const totalDuration = Math.max(...clips.map(c => c.position + c.duration));
      const offlineCtx = new OfflineAudioContext(
        1,
        Math.ceil(totalDuration * buffer.sampleRate),
        buffer.sampleRate
      );

      const crossfades = editView?.getCrossfades() ?? [];

      for (const clip of clips) {
        const source = offlineCtx.createBufferSource();
        source.buffer = buffer;

        const gainNode = offlineCtx.createGain();
        gainNode.connect(offlineCtx.destination);
        source.connect(gainNode);

        const clipEnd = clip.position + clip.duration;

        // Apply explicit fade-in
        if (clip.fadeIn && clip.fadeIn > 0) {
          gainNode.gain.setValueAtTime(0, clip.position);
          gainNode.gain.linearRampToValueAtTime(1, clip.position + clip.fadeIn);
        }

        // Apply explicit fade-out
        if (clip.fadeOut && clip.fadeOut > 0) {
          const fadeOutStart = clipEnd - clip.fadeOut;
          gainNode.gain.setValueAtTime(1, fadeOutStart);
          gainNode.gain.linearRampToValueAtTime(0, clipEnd);
        }

        // Apply crossfades
        for (const xf of crossfades) {
          if (xf.clipA.id === clip.id) {
            gainNode.gain.setValueAtTime(1, xf.startTime);
            gainNode.gain.linearRampToValueAtTime(0, xf.endTime);
          } else if (xf.clipB.id === clip.id) {
            gainNode.gain.setValueAtTime(0, xf.startTime);
            gainNode.gain.linearRampToValueAtTime(1, xf.endTime);
          }
        }

        source.start(clip.position, clip.sourceOffset, clip.duration);
      }

      const rendered = await offlineCtx.startRendering();
      const wavBlob = encodeWav(rendered);
      const result = await api.editUploadRender(wavBlob, clips);

      if (result.error) {
        log(`Edit commit failed: ${result.error}`, 'error');
        return;
      }

      $editApplied = true;
      $audioUrl = api.editAudioUrl();
      log('Edit committed successfully');
    } catch (e: any) {
      log(`Edit commit error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function runEditReset() {
    try {
      await api.editReset();
      $editClips = [];
      $editSelectedClipIds = new Set();
      $editApplied = false;
      $editCursorTime = 0;
      $editTimeSelection = null;
      $audioUrl = api.audioUrl();
      // Reload the edit view's source audio and reinitialize clips
      $waveformReset = $waveformReset + 1;
      log('Edit reset');
    } catch (e) {
      log(`Edit reset error: ${e}`, 'error');
    }
  }

  function editDeleteSelected() {
    editView?.deleteSelectedClips();
  }

  async function deleteSelectedCluster() {
    if ($selectedIdx === null) return;

    const idx = $selectedIdx;
    const cluster = get(clusters)[idx];

    $processing = true;
    log(`Deleting cluster ${idx + 1} (${cluster.note}), restoring original audio...`);

    try {
      // Sync any unsynced clusters to backend first
      if (get(dirtyClusters).size > 0) {
        const cls = get(clusters);
        const clusterUpdates = cls.map((c, i) => ({
          idx: i,
          start_time: c.start_time,
          end_time: c.end_time,
          note: c.note,
          mean_freq: c.mean_freq,
          pitch_shift_semitones: c.pitch_shift_semitones,
          ramp_in_ms: c.ramp_in_ms,
          ramp_out_ms: c.ramp_out_ms,
          correction_strength: c.correction_strength,
          smoothing_percent: c.smoothing_percent,
          manually_edited: c.manually_edited || false,
        }));
        const syncResult = await api.syncClusters(clusterUpdates, get(timeEdits), undefined, get(stretchMarkers));
        if (syncResult.error) {
          log(`Error syncing: ${syncResult.error}`, 'error');
          return;
        }
        $clusters = syncResult.clusters;
        $dirtyClusters = new Set();
      }

      const result = await api.deleteCluster(idx);

      if (result.error) {
        log(`Error deleting cluster: ${result.error}`, 'error');
        return;
      }

      // Remap dirty indices
      const oldDirty = get(dirtyClusters);
      const newDirty = new Set<number>();
      for (const dirtyIdx of oldDirty) {
        if (dirtyIdx < idx) newDirty.add(dirtyIdx);
        else if (dirtyIdx > idx) newDirty.add(dirtyIdx - 1);
      }
      $dirtyClusters = newDirty;

      // Remap time edits: remove the deleted cluster's edit, shift higher indices down
      $timeEdits = $timeEdits
        .filter(e => e.clusterIdx !== idx)
        .map(e => e.clusterIdx > idx ? { ...e, clusterIdx: e.clusterIdx - 1 } : e);
      const oldDirtyTime = get(dirtyTimeEdits);
      const newDirtyTime = new Set<number>();
      for (const di of oldDirtyTime) {
        if (di < idx) newDirtyTime.add(di);
        else if (di > idx) newDirtyTime.add(di - 1);
      }
      $dirtyTimeEdits = newDirtyTime;
      // Regenerate stretch markers for updated cluster list
      $stretchMarkers = [];
      $dirtyStretchMarkers = false;

      $clusters = result.clusters;
      $selectedIdx = null;

      // Re-analyze pitch for the restored segment (only if pitch plot is active)
      if ($activeTab === 'pitch') {
        const buffer = 0.3;
        const segResult = await api.analyzeSegment(
          cluster.start_time - buffer,
          cluster.end_time + buffer
        );
        if (segResult.ok) {
          pitchPlot?.updatePitchSegment(
            segResult.times, segResult.frequencies,
            segResult.start_time, segResult.end_time
          );
        }
      }

      $audioUrl = api.audioUrl();
      refreshCorrectionCurve();
      log(`Cluster ${idx + 1} deleted and audio restored`);
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  function deleteTimeAlignmentClusters() {
    // Collect indices to delete: multi-select if available, otherwise single selection
    const sel = get(selectedIndices);
    const toDelete = sel.size > 0 ? [...sel].sort((a, b) => b - a) : ($selectedIdx !== null ? [$selectedIdx] : []);
    if (toDelete.length === 0) return;

    let cls = [...get(clusters)];
    let edits = [...get(timeEdits)];
    let dirty = new Set(get(dirtyClusters));
    let dirtyTime = new Set(get(dirtyTimeEdits));

    // Delete from highest index first to keep lower indices stable
    for (const idx of toDelete) {
      log(`Removing cluster ${idx + 1} (${cls[idx].note}) from time alignment`);
      cls.splice(idx, 1);

      // Remove time edits for this cluster and remap higher indices
      edits = edits
        .filter(e => e.clusterIdx !== idx)
        .map(e => e.clusterIdx > idx ? { ...e, clusterIdx: e.clusterIdx - 1 } : e);

      // Remap dirty clusters
      const newDirty = new Set<number>();
      for (const d of dirty) {
        if (d < idx) newDirty.add(d);
        else if (d > idx) newDirty.add(d - 1);
      }
      dirty = newDirty;

      // Remap dirty time edits
      const newDirtyTime = new Set<number>();
      for (const d of dirtyTime) {
        if (d < idx) newDirtyTime.add(d);
        else if (d > idx) newDirtyTime.add(d - 1);
      }
      dirtyTime = newDirtyTime;
    }

    $clusters = cls;
    $timeEdits = edits;
    $dirtyClusters = dirty;
    $dirtyTimeEdits = dirtyTime;
    // Regenerate stretch markers for the new cluster list
    $stretchMarkers = [];
    $dirtyStretchMarkers = false;
    $selectedIdx = null;
    $selectedIndices = new Set();
  }

  // --- Time alignment callbacks ---

  async function applyTimeEdits() {
    const edits = get(timeEdits);
    const markers = get(stretchMarkers);
    const cls = get(clusters);
    const hasPitchEdits = cls.some(c => c.pitch_shift_semitones !== 0 || (c.smoothing_percent ?? 0) !== 0);

    const movedMarkers = markers.filter(m => Math.abs(m.currentTime - m.originalTime) > 0.0001);

    console.log('[applyTimeEdits] edits:', edits.length, 'markers:', movedMarkers.length, 'dirtyClusters:', get(dirtyClusters).size);

    if (edits.length === 0 && movedMarkers.length === 0 && get(dirtyClusters).size === 0) {
      log('No edits to apply', 'warn');
      return;
    }

    $processing = true;
    log(`Applying ${movedMarkers.length} marker(s)${edits.length > 0 ? ` + ${edits.length} time edit(s)` : ''}${hasPitchEdits ? ' + pitch edits' : ''}...`);

    try {
      const clusterUpdates = cls.map((c, idx) => ({
        idx,
        start_time: c.start_time,
        end_time: c.end_time,
        note: c.note,
        mean_freq: c.mean_freq,
        pitch_shift_semitones: c.pitch_shift_semitones,
        ramp_in_ms: c.ramp_in_ms,
        ramp_out_ms: c.ramp_out_ms,
        correction_strength: c.correction_strength,
        smoothing_percent: c.smoothing_percent,
        manually_edited: c.manually_edited || false,
      }));

      const result = await api.syncClusters(clusterUpdates, edits, undefined, markers);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      $clusters = result.clusters;
      $audioUrl = api.audioUrl();
      $dirtyClusters = new Set();
      $dirtyTimeEdits = new Set();
      $dirtyStretchMarkers = false;
      if (result.timemap) {
        $backendTimemap = result.timemap;
      }
      refreshCorrectionCurve();
      log('All edits applied successfully');
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  function resetAllMarkers() {
    const markers = get(stretchMarkers);
    $stretchMarkers = markers.map(m => ({ ...m, currentTime: m.originalTime }));
    $dirtyStretchMarkers = false;
    $backendTimemap = [];
  }


  /**
   * Auto time correct: match main markers to reference markers using MIDI note changes.
   *
   * Algorithm:
   * 1. Find MIDI note boundaries (where one MIDI note ends and another begins)
   * 2. For each MIDI boundary, find the closest main audio marker within max_distance
   * 3. For each matched main marker, find the closest reference marker within max_distance
   * 4. If both found, move the main marker toward the reference marker's position
   *    by strength%, clamped by max_change_ms
   */
  function autoTimeCorrect() {
    const p = getAllParams();
    const mainMarkers = get(stretchMarkers);
    const refMarkers = get(referenceStretchMarkers);
    const midi = get(midiNotes);

    if (mainMarkers.length === 0 || refMarkers.length === 0 || midi.length < 2) {
      log('Need main markers, reference markers, and MIDI notes for auto time correct', 'warn');
      return;
    }

    const maxDistS = p.time_match_max_distance_ms / 1000;
    const strength = p.time_match_strength / 100;
    const maxChangeS = p.time_match_max_change_ms / 1000;

    // Step 1: Find MIDI note boundaries (transitions between consecutive MIDI notes)
    const midiBoundaries: number[] = [];
    for (let i = 0; i < midi.length - 1; i++) {
      // The boundary is where one MIDI note ends / next begins
      // Use the midpoint between end of current and start of next if there's a gap
      const boundary = (midi[i].end_time + midi[i + 1].start_time) / 2;
      midiBoundaries.push(boundary);
    }

    // Helper: find all marker indices within maxDist of a time
    function findMarkersInRange(markers: StretchMarker[], time: number, maxDist: number): number[] {
      const indices: number[] = [];
      for (let i = 0; i < markers.length; i++) {
        if (Math.abs(markers[i].originalTime - time) <= maxDist) {
          indices.push(i);
        }
      }
      return indices;
    }

    // Helper: find closest marker to a time
    function findClosestMarker(markers: StretchMarker[], time: number, maxDist: number): number | null {
      let bestIdx: number | null = null;
      let bestDist = Infinity;
      for (let i = 0; i < markers.length; i++) {
        const dist = Math.abs(markers[i].originalTime - time);
        if (dist < bestDist && dist <= maxDist) {
          bestDist = dist;
          bestIdx = i;
        }
      }
      return bestIdx;
    }

    // Step 2 & 3: Match markers through MIDI boundaries
    let matchCount = 0;
    let moveCount = 0;
    const newMarkers = mainMarkers.map(m => ({ ...m }));

    for (const boundary of midiBoundaries) {
      // Find closest reference marker to this MIDI boundary
      const refIdx = findClosestMarker(refMarkers, boundary, maxDistS);
      if (refIdx === null) continue;

      const refTime = refMarkers[refIdx].originalTime;

      // Find all main markers within range, then pick the one closest to the reference marker
      const mainCandidates = findMarkersInRange(mainMarkers, boundary, maxDistS);
      if (mainCandidates.length === 0) continue;

      let mainIdx = mainCandidates[0];
      let bestDistToRef = Math.abs(mainMarkers[mainIdx].originalTime - refTime);
      for (const idx of mainCandidates) {
        const dist = Math.abs(mainMarkers[idx].originalTime - refTime);
        if (dist < bestDistToRef) {
          bestDistToRef = dist;
          mainIdx = idx;
        }
      }

      matchCount++;

      // Step 4: Move main marker toward reference marker position
      const mainTime = mainMarkers[mainIdx].originalTime;
      const delta = (refTime - mainTime) * strength;

      // Clamp by max change
      const clampedDelta = Math.max(-maxChangeS, Math.min(maxChangeS, delta));

      if (Math.abs(clampedDelta) > 0.0001) {
        newMarkers[mainIdx].currentTime = mainTime + clampedDelta;
        moveCount++;
      }
    }

    // Ensure markers don't cross each other after moving
    for (let i = 1; i < newMarkers.length; i++) {
      if (newMarkers[i].currentTime <= newMarkers[i - 1].currentTime + 0.005) {
        newMarkers[i].currentTime = newMarkers[i - 1].currentTime + 0.005;
      }
    }

    $stretchMarkers = newMarkers;
    $dirtyStretchMarkers = true;

    log(`Auto time correct: ${matchCount} MIDI boundaries matched, ${moveCount} markers moved (strength ${p.time_match_strength}%, max ${p.time_match_max_change_ms}ms)`);
  }

  // --- Playhead sync ---
  function onTimeUpdate(time: number) {
    declickerView?.setPlayheadTime(time);
    denoiserView?.setPlayheadTime(time);
    editView?.setPlayheadTime(time);
    if ($activeTab === 'pitch') {
      pitchPlot?.updatePlayhead(time);
      timeAlignmentView?.setPlayheadTime(time);
    } else if ($activeTab === 'time') {
      timeAlignmentView?.updatePlayhead(time);
      pitchPlot?.setPlayheadTime(time);
    } else {
      pitchPlot?.setPlayheadTime(time);
      timeAlignmentView?.setPlayheadTime(time);
    }
  }

  function syncWaveform(xRange: [number, number], totalDuration: number) {
    waveformPlayer?.syncToRange(xRange, totalDuration);
  }

  function onSeek(time: number) {
    waveformPlayer?.seek(time);
  }

  // --- Keyboard shortcuts ---
  function isTextInput(el: EventTarget | null): boolean {
    if (!el || !(el instanceof HTMLElement)) return false;
    if (el.tagName === 'TEXTAREA' || el.isContentEditable) return true;
    if (el.tagName === 'INPUT') {
      const type = (el as HTMLInputElement).type;
      return type !== 'range' && type !== 'checkbox' && type !== 'radio' && type !== 'button';
    }
    return false;
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.code === 'Space' && !isTextInput(e.target)) {
      e.preventDefault();
      if ($activeTab === 'edit') {
        editView?.togglePlay();
      } else {
        waveformPlayer?.togglePlay();
      }
    }

    if ((e.key === 'Delete' || e.key === 'Backspace') && !isTextInput(e.target)) {
      if ($activeTab === 'edit') {
        e.preventDefault();
        editView?.deleteAtCursorOrSelection();
      } else if ($selectedIdx !== null) {
        e.preventDefault();
        if ($activeTab === 'pitch') {
          deleteSelectedCluster();
        } else if ($activeTab === 'time') {
          deleteTimeAlignmentClusters();
        }
      }
    }

    if ((e.key === 'b' || e.key === 'B') && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.splitAtCursorOrSelection();
    }

    if ((e.key === 'a' || e.key === 'A') && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.trimStartToCursor();
    }

    if ((e.key === 's' || e.key === 'S') && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.trimEndToCursor();
    }

    if ((e.key === 'd' || e.key === 'D') && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.setFadeInToCursor();
    }

    if ((e.key === 'g' || e.key === 'G') && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.setFadeOutToCursor();
    }

    if ((e.key === 't' || e.key === 'T') && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.zoomIn(editZoomPercent);
    }

    if ((e.key === 'r' || e.key === 'R') && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.zoomOut(editZoomPercent);
    }

    if (e.key === ',' && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.nudge(-1, editNudgeMs);
    }

    if (e.key === '.' && !isTextInput(e.target) && $activeTab === 'edit') {
      e.preventDefault();
      editView?.nudge(1, editNudgeMs);
    }
  }
</script>

<svelte:window onkeydowncapture={onKeyDown} />

<Header />
<HelpModal />

<div class="main-layout">
  {#if $activeTab === 'declicker'}
    <DeclickerParams
      bind:this={declickerParams}
      onDetect={runDeclickerDetect}
      onApply={runDeclickerApply}
      onPreview={runDeclickerPreview}
      onReset={runDeclickerReset}
      onExport={runDeclickerExport}
    />
  {:else if $activeTab === 'denoise'}
    <DenoiserParams
      bind:this={denoiserParamsRef}
      onAnalyze={runDenoiserAnalyze}
      onApply={runDenoiserApply}
      onReset={runDenoiserReset}
      onExport={runDenoiserExport}
      onClearNoiseSelection={() => denoiserView?.clearSelection()}
    />
  {:else if $activeTab === 'edit'}
    <EditParams
      onCommit={runEditCommit}
      onReset={runEditReset}
      onDeleteSelected={editDeleteSelected}
      bind:zoomPercent={editZoomPercent}
      bind:nudgeMs={editNudgeMs}
    />
  {:else if $activeTab === 'pitch'}
    <ParameterPanel
      onAnalyze={runAnalyze}
      onCorrect={runCorrect}
      onExport={runExport}
    />
  {:else}
    <TimeAlignmentParams
      onAnalyze={runAnalyze}
      onApplyTimeEdits={applyTimeEdits}
      onExport={runExport}
      onResetMarkers={resetAllMarkers}
      onAutoTimeCorrect={autoTimeCorrect}
    />
  {/if}

  <main class="center-panel">
    <TabBar />
    <div style:display={$activeTab === 'declicker' ? 'contents' : 'none'}>
      <DeclickerView
        bind:this={declickerView}
        {syncWaveform}
        {onSeek}
      />
    </div>
    <div style:display={$activeTab === 'denoise' ? 'contents' : 'none'}>
      <DenoiserView
        bind:this={denoiserView}
        {syncWaveform}
        {onSeek}
        onNoiseSelection={(start, end) => denoiserParamsRef?.setNoiseRange(start, end)}
      />
    </div>
    <div style:display={$activeTab === 'edit' ? 'contents' : 'none'}>
      <EditView
        bind:this={editView}
        {syncWaveform}
        {onSeek}
      />
    </div>
    <div style:display={$activeTab === 'pitch' ? 'contents' : 'none'}>
      <PitchPlot
        bind:this={pitchPlot}
        {onClusterSelect}
        {onClusterDrag}
        {onClusterResize}
        {onDrawBox}
        {onClusterSmoothing}
        {onClusterRampDrag}
        {onWarningFix}
        onResetView={() => pitchPlot?.resetView()}
        {syncWaveform}
        {onSeek}
      />
    </div>
    <div style:display={$activeTab === 'time' ? 'contents' : 'none'}>
      <TimeAlignmentView
        bind:this={timeAlignmentView}
        {syncWaveform}
        {onSeek}
        onEditComplete={autoProcessTimeSegment}
      />
    </div>

    <div style:display={$activeTab === 'edit' ? 'none' : 'contents'}>
    <WaveformPlayer
      bind:this={waveformPlayer}
      {onTimeUpdate}
    />
    </div>

    {#if $advancedView}
    <LogPanel />
    {/if}
  </main>

  <div class="right-panel">
    {#if $activeTab === 'declicker'}
      <DeclickerInfoPanel onSeekTime={(t) => waveformPlayer?.seek(t)} />
    {:else if $activeTab === 'denoise'}
      <DenoiserInfoPanel />
    {:else if $activeTab === 'edit'}
      <EditInfoPanel onSeekTime={(t) => waveformPlayer?.seek(t)} />
    {:else if $activeTab === 'pitch'}
      <ClusterPanel {onClusterParamChange} onProcessSegment={processSegment} onEditComplete={autoProcessSegment} onSeekTime={(t) => waveformPlayer?.seek(t)} />
    {:else}
      <TimeClusterPanel onProcessSegment={processSegment} />
    {/if}
    <MixerPanel />
  </div>
</div>

<style>
  .right-panel {
    display: flex;
    flex-direction: column;
    width: var(--panel-w);
    flex-shrink: 0;
    background: var(--bg2);
    overflow: hidden;
  }

  .right-panel :global(aside) {
    flex: 1;
    overflow-y: auto;
    width: 100%;
    border-right: none;
  }
</style>
