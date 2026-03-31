<script lang="ts">
  import { declickerDetections, declickerApplied, audioLoaded } from '$lib/stores/appState';
  import type { DeclickerParams as DeclickerParamsType } from '$lib/utils/types';

  interface Props {
    onDetect: () => void;
    onApply: () => void;
    onPreview: () => void;
    onReset: () => void;
    onExport: () => void;
  }

  let { onDetect, onApply, onPreview, onReset, onExport }: Props = $props();

  // Local parameter state
  let numPasses = $state(2);
  let sensitivityDb = $state(6.0);
  let stepSizeMs = $state(5.0);
  let maxClickSteps = $state(2);
  let minSeparation = $state(3);
  let denseThresholdDb = $state(-45.0);
  let freqLow = $state(150);
  let freqHigh = $state(9600);
  let numBands = $state(12);
  let crossfadeMs = $state(5.0);

  const clickCount = $derived($declickerDetections.length);

  export function getParams(): DeclickerParamsType {
    return {
      num_passes: numPasses,
      sensitivity_db: sensitivityDb,
      step_size_ms: stepSizeMs,
      max_click_length_steps: maxClickSteps,
      min_separation_steps: minSeparation,
      dense_threshold_db: denseThresholdDb,
      freq_low: freqLow,
      freq_high: freqHigh,
      num_bands: numBands,
      crossfade_ms: crossfadeMs,
    };
  }
</script>

<aside class="param-panel">
  <h2>De-Click</h2>

  <section>
    <h3>Detection</h3>
    <div class="param-group">
      <label>Sensitivity ({sensitivityDb} dB)
        <input type="range" min="0.5" max="42" step="0.5" bind:value={sensitivityDb}>
      </label>
      <label>Step size ({stepSizeMs} ms)
        <input type="range" min="1" max="50" step="1" bind:value={stepSizeMs}>
      </label>
      <label>Max click length ({maxClickSteps} steps)
        <input type="range" min="1" max="10" step="1" bind:value={maxClickSteps}>
      </label>
      <label>Min separation ({minSeparation} steps)
        <input type="range" min="1" max="20" step="1" bind:value={minSeparation}>
      </label>
      <label>Dense click threshold ({denseThresholdDb} dB)
        <input type="range" min="-100" max="0" step="1" bind:value={denseThresholdDb}>
      </label>
    </div>
  </section>

  <section>
    <h3>Frequency Range</h3>
    <div class="param-group">
      <label>Low (Hz)<input type="number" min="20" max="20000" bind:value={freqLow}></label>
      <label>High (Hz)<input type="number" min="20" max="20000" bind:value={freqHigh}></label>
      <label>Bands ({numBands})
        <input type="range" min="1" max="50" step="1" bind:value={numBands}>
      </label>
    </div>
  </section>

  <section>
    <h3>Repair</h3>
    <div class="param-group">
      <label>Passes ({numPasses})
        <input type="range" min="1" max="4" step="1" bind:value={numPasses}>
      </label>
      <label>Crossfade ({crossfadeMs} ms)
        <input type="range" min="1" max="50" step="1" bind:value={crossfadeMs}>
      </label>
    </div>
  </section>

  <section>
    <div class="param-group">
      <div class="status-info">
        {#if clickCount > 0}
          <span class="click-count">{clickCount} clicks detected</span>
        {:else}
          <span class="dim">No clicks detected yet</span>
        {/if}
        {#if $declickerApplied}
          <span class="applied-badge">De-click applied</span>
        {/if}
      </div>

      <button class="btn-accent" disabled={!$audioLoaded} onclick={onDetect}>
        Detect Clicks
      </button>
      <button class="btn-accent btn-apply" disabled={!$audioLoaded} onclick={onApply}>
        Apply De-Click
      </button>
      {#if $declickerApplied}
        <button class="btn btn-secondary btn-small" onclick={onPreview}>
          Preview (Isolate)
        </button>
        <button class="btn btn-secondary btn-small" onclick={onExport}>
          Export De-Clicked
        </button>
      {/if}
      {#if clickCount > 0 || $declickerApplied}
        <button class="btn btn-secondary btn-small" onclick={onReset}>
          Reset
        </button>
      {/if}
    </div>
  </section>
</aside>

<style>
  .status-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.8rem;
    padding: 4px 0;
  }
  .click-count {
    color: var(--warning, #f0a);
    font-weight: 500;
  }
  .applied-badge {
    color: var(--success, #2dd4bf);
    font-weight: 500;
  }
  .dim {
    opacity: 0.5;
    color: var(--text2, #888);
  }
  .btn-accent {
    width: 100%;
    margin-top: 6px;
    padding: 6px 12px;
    background: #2dd4bf;
    color: #16213e;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
  }
  .btn-accent:hover:not(:disabled) {
    filter: brightness(1.15);
  }
  .btn-accent:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .btn-apply {
    background: var(--accent, #e94560);
    color: #fff;
  }
  .btn-small {
    padding: 3px 8px;
    font-size: 0.72rem;
    margin-top: 4px;
  }
</style>
