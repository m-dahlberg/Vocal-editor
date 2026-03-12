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
  import * as api from '$lib/api';
  import {
    clusters, times, frequencies, originalTimes, originalFrequencies,
    midiNotes, selectedIdx, selectedIndices, dirtyClusters,
    audioLoaded, audioUrl, processing, log,
    activeTab, timeEdits, dirtyTimeEdits, backendTimemap
  } from '$lib/stores/appState';
  import { params, getAllParams } from '$lib/stores/params';
  import { computeShiftAtTime, generateCorrectionCurve, computePitchCurve, closestNote } from '$lib/utils/pitchMath';
  import { get } from 'svelte/store';
  import type { Cluster } from '$lib/utils/types';

  let pitchPlot: PitchPlot;
  let timeAlignmentView: TimeAlignmentView;
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
    });
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

      // Clear all edits (pitch + time)
      $dirtyClusters = new Set();
      $timeEdits = [];
      $dirtyTimeEdits = new Set();
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
        const syncResult = await api.syncClusters(clusterUpdates);
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
        const syncResult = await api.syncClusters(clusterUpdates);
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
    $selectedIdx = null;
    $selectedIndices = new Set();
  }

  // --- Time alignment callbacks ---

  async function applyTimeEdits() {
    const edits = get(timeEdits);
    if (edits.length === 0) {
      log('No time edits to apply', 'warn');
      return;
    }

    $processing = true;
    log(`Applying ${edits.length} time edit(s)...`);

    try {
      const result = await api.syncTimeEdits(edits);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }
      $audioUrl = api.audioUrl();
      $dirtyTimeEdits = new Set();
      if (result.timemap) {
        $backendTimemap = result.timemap;
      }
      log('Time edits applied successfully');

      // Debug: compare visual curve data vs actual backend timemap
      if (result.timemap) {
        const cls = get(clusters);
        console.group('[TIME DEBUG] Visual segments vs Backend timemap');

        // Visual segments: clusters + gaps
        console.log('--- Visual segments (clusters + gaps) ---');
        for (let i = 0; i < cls.length; i++) {
          const edit = edits.find(e => e.clusterIdx === i);
          const editStart = edit ? edit.newStart : cls[i].start_time;
          const editEnd = edit ? edit.newEnd : cls[i].end_time;
          const origDur = cls[i].end_time - cls[i].start_time;
          const editDur = editEnd - editStart;
          const ratio = origDur > 0 && editDur > 0 ? origDur / editDur : NaN;

          // Gap before this cluster
          if (i === 0 && editStart > 0.001) {
            const gapOrigEnd = cls[0].start_time;
            const gapRatio = gapOrigEnd > 0.001 && editStart > 0.001 ? gapOrigEnd / editStart : NaN;
            console.log(`  GAP [0.000 → ${gapOrigEnd.toFixed(3)}] => [0.000 → ${editStart.toFixed(3)}] ratio=${gapRatio.toFixed(3)}`);
          }
          if (i > 0) {
            const prevEdit = edits.find(e => e.clusterIdx === i - 1);
            const prevEditEnd = prevEdit ? prevEdit.newEnd : cls[i - 1].end_time;
            const gapOrigStart = cls[i - 1].end_time;
            const gapOrigEnd = cls[i].start_time;
            const gapOrigDur = gapOrigEnd - gapOrigStart;
            const gapEditDur = editStart - prevEditEnd;
            const gapRatio = gapOrigDur > 0.001 && gapEditDur > 0.001 ? gapOrigDur / gapEditDur : NaN;
            console.log(`  GAP [${gapOrigStart.toFixed(3)} → ${gapOrigEnd.toFixed(3)}] => [${prevEditEnd.toFixed(3)} → ${editStart.toFixed(3)}] ratio=${gapRatio.toFixed(3)}`);
          }

          console.log(`  C${i} ${cls[i].note} [${cls[i].start_time.toFixed(3)} → ${cls[i].end_time.toFixed(3)}] => [${editStart.toFixed(3)} → ${editEnd.toFixed(3)}] ratio=${ratio.toFixed(3)}`);
        }

        console.log('--- Backend timemap (source_s → target_s) ---');
        for (const entry of result.timemap) {
          const delta = entry.target_s - entry.source_s;
          console.log(`  ${entry.source_s.toFixed(3)}s → ${entry.target_s.toFixed(3)}s (delta=${delta >= 0 ? '+' : ''}${delta.toFixed(3)}s)`);
        }

        // Compute speed ratios between timemap keypoints
        console.log('--- Backend timemap speed ratios (between keypoints) ---');
        for (let i = 1; i < result.timemap.length; i++) {
          const prev = result.timemap[i - 1];
          const cur = result.timemap[i];
          const srcDur = cur.source_s - prev.source_s;
          const tgtDur = cur.target_s - prev.target_s;
          const ratio = srcDur > 0.001 && tgtDur > 0.001 ? srcDur / tgtDur : NaN;
          const log2Ratio = isNaN(ratio) ? NaN : Math.log2(ratio);
          console.log(`  [${prev.source_s.toFixed(3)} → ${cur.source_s.toFixed(3)}] src=${srcDur.toFixed(3)}s tgt=${tgtDur.toFixed(3)}s ratio=${ratio.toFixed(3)} log2=${log2Ratio.toFixed(3)}`);
        }

        console.groupEnd();
      }
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  // --- Playhead sync ---
  function onTimeUpdate(time: number) {
    if ($activeTab === 'pitch') {
      pitchPlot?.updatePlayhead(time);
    } else {
      timeAlignmentView?.updatePlayhead(time);
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
      waveformPlayer?.togglePlay();
    }

    if ((e.key === 'Delete' || e.key === 'Backspace') && !isTextInput(e.target)) {
      if ($selectedIdx !== null) {
        e.preventDefault();
        if ($activeTab === 'pitch') {
          deleteSelectedCluster();
        } else if ($activeTab === 'time') {
          deleteTimeAlignmentClusters();
        }
      }
    }
  }
</script>

<svelte:window onkeydowncapture={onKeyDown} />

<Header />
<HelpModal />

<div class="main-layout">
  {#if $activeTab === 'pitch'}
    <ParameterPanel
      onAnalyze={runAnalyze}
      onCorrect={runCorrect}
      onUpdateAudio={processDirtyClusters}
      onExport={runExport}
    />
  {:else}
    <TimeAlignmentParams
      onAnalyze={runAnalyze}
      onApplyTimeEdits={applyTimeEdits}
      onExport={runExport}
    />
  {/if}

  <main class="center-panel">
    <TabBar />
    <div style:display={$activeTab === 'pitch' ? 'contents' : 'none'}>
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
        {onSeek}
      />
    </div>
    <div style:display={$activeTab === 'time' ? 'contents' : 'none'}>
      <TimeAlignmentView
        bind:this={timeAlignmentView}
        {onClusterSelect}
        {onDrawBox}
        {syncWaveform}
        {onSeek}
      />
    </div>

    <WaveformPlayer
      bind:this={waveformPlayer}
      {onTimeUpdate}
    />

    <LogPanel />
  </main>

  <div class="right-panel">
    {#if $activeTab === 'pitch'}
      <ClusterPanel {onClusterParamChange} />
    {:else}
      <TimeClusterPanel />
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
