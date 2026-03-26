<script lang="ts">
  import { params } from '$lib/stores/params';
  import { clusters, stretchMarkers } from '$lib/stores/appState';

  interface Props {
    onAnalyze: () => void;
    onApplyTimeEdits: () => void;
    onExport: () => void;
    onResetMarkers?: () => void;
  }

  let { onAnalyze, onApplyTimeEdits, onExport, onResetMarkers }: Props = $props();

  const hasPitchEdits = $derived($clusters.some(c => c.pitch_shift_semitones !== 0 || (c.smoothing_percent ?? 0) !== 0));
  const movedMarkerCount = $derived($stretchMarkers.filter(m => Math.abs(m.currentTime - m.originalTime) > 0.0001).length);
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
    <h3>Stretch Markers</h3>
    <div class="param-group">
      <div class="marker-info">
        {#if $stretchMarkers.length > 0}
          <span>{$stretchMarkers.length} markers · {movedMarkerCount} moved</span>
        {:else}
          <span class="dim">No markers (analyze audio first)</span>
        {/if}
      </div>
      {#if movedMarkerCount > 0 && onResetMarkers}
        <button class="btn btn-small" onclick={onResetMarkers}>Reset All Markers</button>
      {/if}
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
  .marker-info {
    font-size: 0.8rem;
    color: var(--text2, #ccc);
    padding: 2px 0;
  }
  .marker-info .dim {
    opacity: 0.5;
  }
  .btn-small {
    padding: 3px 8px;
    font-size: 0.72rem;
    margin-top: 4px;
  }
</style>
