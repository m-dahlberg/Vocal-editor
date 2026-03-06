<script lang="ts">
  import { selectedCluster, selectedIdx, selectedIndices, clusters, dirtyClusters } from '$lib/stores/appState';
  import type { Cluster } from '$lib/utils/types';

  interface Props {
    onClusterParamChange: () => void;
  }

  let { onClusterParamChange }: Props = $props();

  let rampIn = $state(0);
  let rampOut = $state(0);
  let smoothing = $state(0);

  // Sync local state when selection changes
  $effect(() => {
    const c = $selectedCluster;
    if (c) {
      rampIn = c.ramp_in_ms;
      rampOut = c.ramp_out_ms;
      smoothing = c.smoothing_percent;
    }
  });

  function applyLive() {
    if ($selectedIdx === null) return;
    const indices = $selectedIndices.size > 0 ? Array.from($selectedIndices) : [$selectedIdx];

    $clusters = $clusters.map((c, i) => {
      if (indices.includes(i)) {
        return {
          ...c,
          ramp_in_ms: rampIn,
          ramp_out_ms: rampOut,
          smoothing_percent: smoothing,
          manually_edited: true,
        };
      }
      return c;
    });

    $dirtyClusters = new Set([...$dirtyClusters, ...indices]);
    onClusterParamChange();
  }
</script>

<aside class="cluster-panel">
  <h2>Selected Note</h2>
  <div class="cluster-details">
    {#if $selectedCluster}
      {@const cluster = $selectedCluster}
      {@const shiftCents = (cluster.pitch_shift_semitones * 100).toFixed(1)}
      {@const multiCount = $selectedIndices.size}

      {#if multiCount > 1}
        <div class="cluster-detail-row" style="background:var(--bg3);border-radius:4px;padding:6px;margin-bottom:6px;">
          <span class="label" style="font-weight:600;color:var(--accent);">{multiCount} notes selected</span>
        </div>
      {/if}

      <div class="cluster-detail-row">
        <span class="label">Cluster</span>
        <span class="value">#{($selectedIdx ?? 0) + 1}</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Note</span>
        <span class="value">{cluster.note}</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Start</span>
        <span class="value">{cluster.start_time.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">End</span>
        <span class="value">{cluster.end_time.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Duration</span>
        <span class="value">{cluster.duration_ms.toFixed(0)} ms</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Mean freq</span>
        <span class="value">{cluster.mean_freq.toFixed(1)} Hz</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Pitch variation</span>
        <span class="value">{(cluster.pitch_variation_cents || 0).toFixed(1)} cents</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Correction</span>
        <span class="value">{shiftCents} cents</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Edited</span>
        <span class="value">{cluster.manually_edited ? 'Yes' : 'No'}</span>
      </div>

      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Per-note parameters</div>
      </div>

      <div class="cluster-param-row">
        <label>Ramp in (ms)</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="1000" bind:value={rampIn} oninput={applyLive}>
          <input type="number" bind:value={rampIn} min="0" oninput={applyLive}>
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Ramp out (ms)</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="1000" bind:value={rampOut} oninput={applyLive}>
          <input type="number" bind:value={rampOut} min="0" oninput={applyLive}>
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Smoothing (%)</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="100" bind:value={smoothing} oninput={applyLive}>
          <input type="number" bind:value={smoothing} min="0" max="100" oninput={applyLive}>
        </div>
      </div>
    {:else}
      <p class="placeholder">Click a note box to select it</p>
    {/if}
  </div>
</aside>
