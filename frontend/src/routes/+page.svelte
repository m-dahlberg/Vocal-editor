<script lang="ts">
  import Header from '$lib/components/Header.svelte';
  import ParameterPanel from '$lib/components/ParameterPanel.svelte';
  import ClusterPanel from '$lib/components/ClusterPanel.svelte';
  import PitchPlot from '$lib/components/PitchPlot.svelte';
  import WaveformPlayer from '$lib/components/WaveformPlayer.svelte';
  import LogPanel from '$lib/components/LogPanel.svelte';
  import HelpModal from '$lib/components/HelpModal.svelte';
  import * as api from '$lib/api';
  import {
    clusters, times, frequencies, originalTimes, originalFrequencies,
    midiNotes, selectedIdx, selectedIndices, dirtyClusters,
    audioLoaded, audioUrl, processing, log
  } from '$lib/stores/appState';
  import { params, getAllParams } from '$lib/stores/params';
  import { computeShiftAtTime, generateCorrectionCurve, computePitchCurve, closestNote } from '$lib/utils/pitchMath';
  import { get } from 'svelte/store';
  import type { Cluster } from '$lib/utils/types';

  let pitchPlot: PitchPlot;
  let waveformPlayer: WaveformPlayer;

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

  function onClusterDrag(idx: number, newShift: number) {
    $clusters[idx].pitch_shift_semitones = newShift;
    $clusters[idx].manually_edited = true;
    $dirtyClusters = new Set([...$dirtyClusters, idx]);
    $clusters = $clusters; // trigger reactivity

    updatePitchCurveForCluster(idx);
    refreshCorrectionCurve();
    log(`Cluster ${idx + 1} moved to ${(newShift * 100).toFixed(1)} cents`);
  }

  function onClusterResize(idx: number) {
    $clusters[idx].manually_edited = true;
    $dirtyClusters = new Set([...$dirtyClusters, idx]);
    $clusters = $clusters;

    updatePitchCurveForCluster(idx);
    refreshCorrectionCurve();
    log(`Cluster ${idx + 1} resized to ${$clusters[idx].duration_ms.toFixed(0)}ms`);
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
      $times = result.times;
      $frequencies = result.frequencies;
      $originalTimes = [...result.times];
      $originalFrequencies = [...result.frequencies];
      $midiNotes = result.midi_notes;
      $audioUrl = api.audioUrl();

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
      const p = getAllParams();
      const result = await api.correct(p);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      $clusters = result.clusters;

      updateAllPitchCurves();
      const newDirty = new Set<number>();
      for (let i = 0; i < result.clusters.length; i++) newDirty.add(i);
      $dirtyClusters = newDirty;
      refreshCorrectionCurve();

      log('Corrections calculated — press Update Audio to apply');
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function processDirtyClusters() {
    if (get(dirtyClusters).size === 0) return;

    $processing = true;
    const cls = get(clusters);
    log(`Syncing ${cls.length} cluster(s) via full-audio pass...`);

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

      const result = await api.syncClusters(clusterUpdates);

      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      $clusters = result.clusters;

      if (result.corrected_times && result.corrected_freqs) {
        pitchPlot?.updatePitchSegment(result.corrected_times, result.corrected_freqs, -Infinity, Infinity);
      }

      $audioUrl = api.audioUrl();
      $dirtyClusters = new Set();
      refreshCorrectionCurve();
      log('All edits processed');
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

  async function deleteSelectedCluster() {
    if ($selectedIdx === null) return;

    const idx = $selectedIdx;
    const cluster = get(clusters)[idx];

    $processing = true;
    log(`Deleting cluster ${idx + 1} (${cluster.note}), restoring original audio...`);

    try {
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

      $clusters = result.clusters;
      $selectedIdx = null;

      // Re-analyze pitch for the restored segment
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

      $audioUrl = api.audioUrl();
      refreshCorrectionCurve();
      log(`Cluster ${idx + 1} deleted and audio restored`);
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  // --- Playhead sync ---
  function onTimeUpdate(time: number) {
    pitchPlot?.updatePlayhead(time);
  }

  function syncWaveform(xRange: [number, number], totalDuration: number) {
    waveformPlayer?.syncToRange(xRange, totalDuration);
  }

  // --- Keyboard shortcuts ---
  function onKeyDown(e: KeyboardEvent) {
    if (e.code === 'Space' && (e.target as HTMLElement)?.tagName !== 'INPUT') {
      e.preventDefault();
      waveformPlayer?.togglePlay();
    }

    if ((e.key === 'Delete' || e.key === 'Backspace') && (e.target as HTMLElement)?.tagName !== 'INPUT') {
      if ($selectedIdx !== null) {
        e.preventDefault();
        deleteSelectedCluster();
      }
    }
  }
</script>

<svelte:window onkeydown={onKeyDown} />

<Header />
<HelpModal />

<div class="main-layout">
  <ParameterPanel
    onAnalyze={runAnalyze}
    onCorrect={runCorrect}
    onUpdateAudio={processDirtyClusters}
    onExport={runExport}
  />

  <main class="center-panel">
    <PitchPlot
      bind:this={pitchPlot}
      {onClusterSelect}
      {onClusterDrag}
      {onClusterResize}
      {onDrawBox}
      {onClusterSmoothing}
      {onClusterRampDrag}
      onResetView={() => pitchPlot?.resetView()}
      {syncWaveform}
    />

    <WaveformPlayer
      bind:this={waveformPlayer}
      {onTimeUpdate}
    />

    <LogPanel />
  </main>

  <ClusterPanel {onClusterParamChange} />
</div>
