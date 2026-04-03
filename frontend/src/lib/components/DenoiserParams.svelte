<script lang="ts">
  import { denoiserApplied, denoiserSpectrogramBefore, denoiserHeatmapRange, audioLoaded } from '$lib/stores/appState';
  import type { DenoiserParams as DenoiserParamsType } from '$lib/utils/types';

  interface Props {
    onAnalyze: () => void;
    onApply: () => void;
    onReset: () => void;
    onExport: () => void;
    onClearNoiseSelection?: () => void;
  }

  let { onAnalyze, onApply, onReset, onExport, onClearNoiseSelection }: Props = $props();

  // Local parameter state
  let stationary = $state(true);
  let propDecrease = $state(1.0);
  let timeConstantS = $state(2.0);
  let freqMaskSmoothHz = $state(500);
  let timeMaskSmoothMs = $state(50);
  let nFft = $state(1024);

  // Noise profile selection (seconds)
  let noiseStart = $state<string>('');
  let noiseEnd = $state<string>('');

  const hasAnalysis = $derived($denoiserSpectrogramBefore !== null);

  export function getParams(): DenoiserParamsType {
    const p: DenoiserParamsType = {
      stationary,
      prop_decrease: propDecrease,
      time_constant_s: timeConstantS,
      freq_mask_smooth_hz: freqMaskSmoothHz,
      time_mask_smooth_ms: timeMaskSmoothMs,
      n_fft: nFft,
    };
    const ns = parseFloat(noiseStart);
    const ne = parseFloat(noiseEnd);
    if (!isNaN(ns) && !isNaN(ne) && ne > ns) {
      p.noise_start = ns;
      p.noise_end = ne;
    }
    return p;
  }

  export function setNoiseRange(start: number, end: number) {
    noiseStart = start.toFixed(3);
    noiseEnd = end.toFixed(3);
  }

  function clearNoiseSelection() {
    noiseStart = '';
    noiseEnd = '';
    onClearNoiseSelection?.();
  }
</script>

<aside class="param-panel">
  <h2>Denoise</h2>

  <section>
    <h3>Noise Profile</h3>
    <div class="param-group">
      <div class="noise-range">
        <label>Start (s)
          <input type="number" min="0" step="0.01" bind:value={noiseStart} placeholder="auto">
        </label>
        <label>End (s)
          <input type="number" min="0" step="0.01" bind:value={noiseEnd} placeholder="auto">
        </label>
      </div>
      {#if noiseStart || noiseEnd}
        <button class="btn btn-secondary btn-small" onclick={clearNoiseSelection}>
          Clear Selection (auto)
        </button>
      {:else}
        <span class="dim">Auto-estimated from full signal</span>
      {/if}
    </div>
  </section>

  <section>
    <h3>Algorithm</h3>
    <div class="param-group">
      <label class="toggle-label">
        <input type="checkbox" bind:checked={stationary}>
        Stationary noise
      </label>
      <span class="dim">{stationary ? 'Fixed threshold (constant noise)' : 'Adaptive threshold (varying noise)'}</span>
    </div>
  </section>

  <section>
    <h3>Reduction</h3>
    <div class="param-group">
      <label>Strength ({(propDecrease * 100).toFixed(0)}%)
        <input type="range" min="0" max="1" step="0.05" bind:value={propDecrease}>
      </label>
      <label>FFT Size
        <select bind:value={nFft}>
          <option value={512}>512</option>
          <option value={1024}>1024</option>
          <option value={2048}>2048</option>
          <option value={4096}>4096</option>
        </select>
      </label>
    </div>
  </section>

  <section>
    <h3>Display</h3>
    <div class="param-group">
      <label>Heatmap gain ({$denoiserHeatmapRange} dB)
        <input type="range" min="0" max="80" step="1" bind:value={$denoiserHeatmapRange}>
      </label>
      <span class="dim">Boost to reveal quiet sounds</span>
    </div>
  </section>

  <section>
    <h3>Smoothing</h3>
    <div class="param-group">
      <label>Freq smoothing ({freqMaskSmoothHz} Hz)
        <input type="range" min="0" max="2000" step="10" bind:value={freqMaskSmoothHz}>
      </label>
      <label>Time smoothing ({timeMaskSmoothMs} ms)
        <input type="range" min="0" max="200" step="5" bind:value={timeMaskSmoothMs}>
      </label>
      {#if !stationary}
        <label>Time constant ({timeConstantS.toFixed(1)} s)
          <input type="range" min="0.5" max="5" step="0.1" bind:value={timeConstantS}>
        </label>
      {/if}
    </div>
  </section>

  <section>
    <div class="param-group">
      <div class="status-info">
        {#if $denoiserApplied}
          <span class="applied-badge">Denoise applied</span>
        {:else if hasAnalysis}
          <span class="dim">Analysis ready — click Apply to process</span>
        {:else}
          <span class="dim">No analysis yet</span>
        {/if}
      </div>

      <button class="btn-accent" disabled={!$audioLoaded} onclick={onAnalyze}>
        Analyze
      </button>
      <button class="btn-accent btn-apply" disabled={!$audioLoaded} onclick={onApply}>
        Apply Denoise
      </button>
      {#if $denoiserApplied}
        <button class="btn btn-secondary btn-small" onclick={onExport}>
          Export Denoised
        </button>
      {/if}
      {#if hasAnalysis || $denoiserApplied}
        <button class="btn btn-secondary btn-small" onclick={onReset}>
          Reset
        </button>
      {/if}
    </div>
  </section>
</aside>

<style>
  .noise-range {
    display: flex;
    gap: 8px;
  }
  .noise-range label {
    flex: 1;
  }
  .noise-range input {
    width: 100%;
  }
  .toggle-label {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }
  .toggle-label input[type="checkbox"] {
    width: auto;
  }
  .status-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.8rem;
    padding: 4px 0;
  }
  .applied-badge {
    color: var(--success, #2dd4bf);
    font-weight: 500;
  }
  .dim {
    opacity: 0.5;
    color: var(--text2, #888);
    font-size: 0.75rem;
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
  select {
    width: 100%;
    padding: 4px;
    background: var(--bg3, #2a2a4a);
    color: var(--text, #ccc);
    border: 1px solid var(--border, #444);
    border-radius: 3px;
    font-size: 0.78rem;
  }
</style>
