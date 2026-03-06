<script lang="ts">
  import { params } from '$lib/stores/params';
  import { avgPitchDeviation } from '$lib/stores/appState';

  interface Props {
    onAnalyze: () => void;
    onCorrect: () => void;
    onUpdateAudio: () => void;
    onExport: () => void;
  }

  let { onAnalyze, onCorrect, onUpdateAudio, onExport }: Props = $props();
</script>

<aside class="param-panel">
  <h2>Parameters</h2>

  <section>
    <h3>Analysis</h3>
    <div class="param-group">
      <label>Min freq (Hz)<input type="number" bind:value={$params.min_frequency}></label>
      <label>Max freq (Hz)<input type="number" bind:value={$params.max_frequency}></label>
      <label>Time resolution (ms)<input type="number" bind:value={$params.time_resolution_ms}></label>
      <label>Freq tolerance (cents)<input type="number" bind:value={$params.frequency_tolerance_cents}></label>
      <label>Min note duration (ms)<input type="number" bind:value={$params.min_note_duration_ms}></label>
      <label>Max gap to bridge (ms)<input type="number" bind:value={$params.max_gap_to_bridge_ms}></label>
      <label>Silence threshold (dB)<input type="number" bind:value={$params.silence_threshold_db}></label>
    </div>
    <div class="param-group" style="margin-top:6px;">
      <label>Avg pitch deviation (cents)<span style="float:right; color:var(--accent2);">{$avgPitchDeviation != null ? $avgPitchDeviation.toFixed(1) : '—'}</span></label>
    </div>
  </section>

  <section>
    <h3>Correction</h3>
    <div class="param-group">
      <label>Transition ramp (ms)<input type="number" bind:value={$params.transition_ramp_ms}></label>
      <label>Gap threshold (ms)<input type="number" bind:value={$params.gap_threshold_ms}></label>
      <label>Correction strength (%)<input type="number" bind:value={$params.correction_strength} min="0" max="100"></label>
      <label>MIDI threshold (cents)<input type="number" bind:value={$params.midi_threshold_cents}></label>
      <label>Auto smooth (%)<input type="number" bind:value={$params.autocorrect_smoothing} min="0" max="100"></label>
      <label>Smooth threshold (cents)<input type="number" bind:value={$params.smoothing_threshold_cents} min="0"></label>
      <label>Smooth threshold (ms)<input type="number" bind:value={$params.smoothing_threshold_ms} min="0"></label>
      <label>Smooth curve<input type="number" bind:value={$params.smooth_curve} min="1.0" step="0.1"></label>
    </div>
  </section>

  <section>
    <h3>Rubberband</h3>
    <div class="param-group">
      <label>Command<input type="text" bind:value={$params.rb.command}></label>
      <label>Crisp level (0-6)<input type="number" bind:value={$params.rb.crisp} min="0" max="6"></label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.formant}> Formant
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.pitch_hq}> Pitch HQ
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.window_long}> Window long
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.smoothing}> Smoothing
      </label>
    </div>
  </section>

  <div class="action-buttons">
    <button class="btn btn-primary" onclick={onAnalyze}>Re-analyze</button>
    <button class="btn btn-primary" onclick={onCorrect}>Correct</button>
    <button class="btn btn-warning" onclick={onUpdateAudio}>Update Audio</button>
    <button class="btn btn-success" onclick={onExport}>Export</button>
  </div>
</aside>
