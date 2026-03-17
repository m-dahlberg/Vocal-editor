<script lang="ts">
  import { params } from '$lib/stores/params';
  import { clusters } from '$lib/stores/appState';

  interface Props {
    onAnalyze: () => void;
    onApplyTimeEdits: () => void;
    onExport: () => void;
  }

  let { onAnalyze, onApplyTimeEdits, onExport }: Props = $props();

  const hasPitchEdits = $derived($clusters.some(c => c.pitch_shift_semitones !== 0 || (c.smoothing_percent ?? 0) !== 0));
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
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.enable_pitchmap}> Enable pitchmap
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.enable_timemap}> Enable timemap
      </label>
    </div>
  </section>

  <section>
    <h3>Correction Limits</h3>
    <div class="param-group">
      <label>Note max stretch ({$params.max_note_stretch}%)
        <input type="range" min="100" max="500" step="10" bind:value={$params.max_note_stretch}>
      </label>
      <label>Note max compress ({$params.max_note_compress}%)
        <input type="range" min="0" max="100" step="5" bind:value={$params.max_note_compress}>
      </label>
      <label>Gap max stretch ({$params.max_gap_stretch}%)
        <input type="range" min="100" max="500" step="10" bind:value={$params.max_gap_stretch}>
      </label>
      <label>Gap max compress ({$params.max_gap_compress}%)
        <input type="range" min="0" max="100" step="5" bind:value={$params.max_gap_compress}>
      </label>
    </div>
  </section>

  {#if hasPitchEdits}
    <div class="cross-tab-info">+ pitch edits will also be applied</div>
  {/if}

  <div class="action-buttons">
    <button class="btn btn-primary" onclick={onAnalyze}>Re-analyze</button>
    <button class="btn btn-warning" onclick={onApplyTimeEdits}>Update Audio</button>
    <button class="btn btn-success" onclick={onExport}>Export</button>
  </div>
</aside>

<style>
  .cross-tab-info {
    padding: 4px 10px;
    margin: 4px 8px;
    font-size: 0.75rem;
    color: var(--accent2, #f0a);
    background: rgba(255, 0, 170, 0.08);
    border-radius: 4px;
    text-align: center;
  }
</style>
