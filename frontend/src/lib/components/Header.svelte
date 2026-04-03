<script lang="ts">
  import { uploadAudio, uploadMidi, uploadPianoGuide, exportMidiUrl, uploadReference, uploadBacking, audioUrl as getAudioUrl } from '$lib/api';
  import * as api from '$lib/api';
  import {
    audioLoaded, midiLoaded, fileStatus, showHelp, showMidi, showCorrectionCurve,
    processing, clusters, times, frequencies, originalTimes, originalFrequencies,
    midiNotes, avgPitchDeviation, audioUrl, dirtyClusters, log,
    referenceClusters, referenceLoaded, backingLoaded,
    waveformReset, selectedIdx, selectedIndices, timeEdits, dirtyTimeEdits, backendTimemap,
    advancedView, stretchMarkers, dirtyStretchMarkers,
    editClips, editSelectedClipIds, editApplied, editCursorTime, editTimeSelection
  } from '$lib/stores/appState';
  import { params, getAllParams } from '$lib/stores/params';

  let audioFileInput: HTMLInputElement;
  let midiFileInput: HTMLInputElement;
  let pianoGuideFileInput: HTMLInputElement;
  let referenceFileInput: HTMLInputElement;
  let backingFileInput: HTMLInputElement;

  async function handleAudioUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    $processing = true;
    log(`Uploading ${file.name}...`);

    try {
      const result = await uploadAudio(file);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }

      // Reset all correction/editing state for the new file
      $clusters = [];
      $times = [];
      $frequencies = [];
      $originalTimes = [];
      $originalFrequencies = [];
      $midiNotes = [];
      $dirtyClusters = new Set();
      $timeEdits = [];
      $dirtyTimeEdits = new Set();
      $backendTimemap = [];
      $selectedIdx = null;
      $selectedIndices = new Set();
      $avgPitchDeviation = null;
      $stretchMarkers = [];
      $dirtyStretchMarkers = false;

      // Reset edit tab state for the new file
      $editClips = [];
      $editSelectedClipIds = new Set();
      $editApplied = false;
      $editCursorTime = 0;
      $editTimeSelection = null;

      // Force waveform to fully redraw for the new file
      $waveformReset = $waveformReset + 1;

      $audioLoaded = true;
      $fileStatus = `${file.name}`;
      log(`Audio uploaded: ${file.name}`);

      // Auto-analyze
      await runAnalyze();
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function handleReferenceUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    $processing = true;
    log(`Uploading reference ${file.name}...`);

    try {
      const result = await uploadReference(file);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }
      $referenceLoaded = true;
      $referenceClusters = result.clusters;
      log(`Reference loaded: ${file.name} (${result.cluster_count} clusters)`);
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function handleBackingUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    $processing = true;
    log(`Uploading backing track ${file.name}...`);

    try {
      const result = await uploadBacking(file);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }
      $backingLoaded = true;
      log(`Backing track loaded: ${file.name}`);
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function handleMidiUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    $processing = true;
    log(`Uploading MIDI ${file.name}...`);

    try {
      const result = await uploadMidi(file);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }
      $midiLoaded = true;
      $midiNotes = result.midi_notes;
      $fileStatus = $fileStatus + ` | ${file.name} (${result.note_count} notes)`;
      log(`MIDI loaded: ${result.message}`);
      if ($audioLoaded) await runAnalyze();
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function handlePianoGuideUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    $processing = true;
    log(`Analyzing piano guide ${file.name}...`);

    try {
      const result = await uploadPianoGuide(file);
      if (result.error) {
        log(`Error: ${result.error}`, 'error');
        return;
      }
      $midiLoaded = true;
      $midiNotes = result.midi_notes;
      $fileStatus = $fileStatus + ` | Piano: ${file.name} (${result.note_count} notes)`;
      log(`Piano guide loaded: ${result.message}`);
      if ($audioLoaded) await runAnalyze();
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }

  async function runAnalyze() {
    if (!$audioLoaded) {
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
      $audioUrl = getAudioUrl();
      $avgPitchDeviation = result.avg_pitch_deviation_cents;

      log(`Analysis complete: ${result.cluster_count} clusters, ${result.duration.toFixed(1)}s`);
    } catch (e: any) {
      log(`Error: ${e}`, 'error');
    } finally {
      $processing = false;
    }
  }
</script>

<header>
  <h1>Vocal Editor GUI</h1>
  <div class="upload-area">
    <label class="btn btn-secondary">
      Audio
      <input type="file" bind:this={audioFileInput} accept=".wav,.mp3,.flac,.aif,.aiff" hidden onchange={handleAudioUpload}>
    </label>
    <label class="btn btn-secondary">
      Reference
      <input type="file" bind:this={referenceFileInput} accept=".wav,.mp3,.flac,.aif,.aiff" hidden onchange={handleReferenceUpload}>
    </label>
    <label class="btn btn-secondary">
      Backing
      <input type="file" bind:this={backingFileInput} accept=".wav,.mp3,.flac,.aif,.aiff" hidden onchange={handleBackingUpload}>
    </label>
    <label class="btn btn-secondary">
      MIDI
      <input type="file" bind:this={midiFileInput} accept=".mid,.midi" hidden onchange={handleMidiUpload}>
    </label>
    <label class="btn btn-secondary">
      Piano
      <input type="file" bind:this={pianoGuideFileInput} accept=".wav,.mp3,.flac,.aif,.aiff" hidden onchange={handlePianoGuideUpload}>
    </label>
    {#if $midiLoaded}
      <a class="btn btn-secondary" href={exportMidiUrl()} download="piano_guide.mid">Export MIDI</a>
    {/if}
    <span class="file-status">{$fileStatus}</span>
  </div>
  <div class="overlay-toggles">
    <label class="checkbox-label">
      <input type="checkbox" bind:checked={$showMidi}> MIDI
    </label>
    <label class="checkbox-label">
      <input type="checkbox" bind:checked={$showCorrectionCurve}> Correction
    </label>
    <label class="view-toggle">
      <span class="view-toggle-label">{$advancedView ? 'Advanced' : 'Simple'}</span>
      <span class="toggle-switch" class:active={$advancedView}>
        <input type="checkbox" bind:checked={$advancedView} hidden>
        <span class="toggle-track">
          <span class="toggle-thumb"></span>
        </span>
      </span>
    </label>
    <button class="btn btn-secondary" onclick={() => $showHelp = true}>Help</button>
  </div>
</header>

<style>
  .view-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    user-select: none;
  }
  .view-toggle-label {
    font-size: 0.75rem;
    color: var(--text-dim);
    white-space: nowrap;
  }
  .toggle-track {
    display: block;
    width: 32px;
    height: 18px;
    background: var(--bg3);
    border-radius: 9px;
    position: relative;
    transition: background 0.2s;
    border: 1px solid var(--border);
  }
  .toggle-switch.active .toggle-track {
    background: var(--accent);
  }
  .toggle-thumb {
    display: block;
    width: 14px;
    height: 14px;
    background: var(--text);
    border-radius: 50%;
    position: absolute;
    top: 1px;
    left: 1px;
    transition: transform 0.2s;
  }
  .toggle-switch.active .toggle-thumb {
    transform: translateX(14px);
    background: var(--bg1);
  }
</style>
