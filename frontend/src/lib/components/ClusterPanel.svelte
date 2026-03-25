<script lang="ts">
  import { selectedCluster, selectedIdx, selectedIndices, clusters, dirtyClusters, midiWarnings, midiLoaded } from '$lib/stores/appState';
  import { params } from '$lib/stores/params';
  import type { Cluster } from '$lib/utils/types';

  interface Props {
    onClusterParamChange: () => void;
    onProcessSegment: () => void;
    onEditComplete: () => void;
    onSeekTime: (time: number) => void;
  }

  let { onClusterParamChange, onProcessSegment, onEditComplete, onSeekTime }: Props = $props();

  function formatTimecode(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds - m * 60;
    return `${m}:${s < 10 ? '0' : ''}${s.toFixed(2)}`;
  }

  let processingSegment = $state(false);

  let rampIn = $state(0);
  let rampOut = $state(0);
  let smoothing = $state(0);
  let _skipSync = false;

  // Sync local state only when the selected index changes (not on data changes)
  let _prevIdx: number | null = null;
  $effect(() => {
    const idx = $selectedIdx;
    if (idx !== _prevIdx) {
      _prevIdx = idx;
      const c = idx !== null ? $clusters[idx] : null;
      if (c) {
        rampIn = c.ramp_in_ms;
        rampOut = c.ramp_out_ms;
        smoothing = c.smoothing_percent;
      }
    }
  });

  function applyLive() {
    if ($selectedIdx === null) return;
    const indices = $selectedIndices.size > 0 ? Array.from($selectedIndices) : [$selectedIdx];

    _skipSync = true;
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
    _skipSync = false;

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
          <input type="range" min="0" max="1000" bind:value={rampIn} onchange={() => { applyLive(); onEditComplete(); }}>
          <input type="number" bind:value={rampIn} min="0" onchange={() => { applyLive(); onEditComplete(); }}>
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Ramp out (ms)</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="1000" bind:value={rampOut} onchange={() => { applyLive(); onEditComplete(); }}>
          <input type="number" bind:value={rampOut} min="0" onchange={() => { applyLive(); onEditComplete(); }}>
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Smoothing (%)</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="100" bind:value={smoothing} onchange={() => { applyLive(); onEditComplete(); }}>
          <input type="number" bind:value={smoothing} min="0" max="100" onchange={() => { applyLive(); onEditComplete(); }}>
        </div>
      </div>

      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Segment processing</div>
      </div>
      <div class="cluster-param-row">
        <label>Padding (ms)</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="1000" bind:value={$params.segment_padding_ms}>
          <input type="number" bind:value={$params.segment_padding_ms} min="0" max="1000">
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Crossfade (ms)</label>
        <div class="slider-input-pair">
          <input type="range" min="1" max="100" bind:value={$params.segment_crossfade_ms}>
          <input type="number" bind:value={$params.segment_crossfade_ms} min="1" max="100">
        </div>
      </div>
      <div class="cluster-param-row">
        <label>Crop (ms)</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="100" bind:value={$params.segment_crop_ms}>
          <input type="number" bind:value={$params.segment_crop_ms} min="0" max="100">
        </div>
      </div>

      <div class="cluster-param-row">
        <label>Neighbors</label>
        <div class="slider-input-pair">
          <input type="range" min="0" max="5" bind:value={$params.segment_neighbor_count}>
          <input type="number" bind:value={$params.segment_neighbor_count} min="0" max="5">
        </div>
      </div>

      <div class="cluster-param-row" style="margin-top:4px;">
        <label>
          <input type="checkbox" bind:checked={$params.segment_auto_process}>
          Auto process
        </label>
      </div>

      <button
        class="process-segment-btn"
        disabled={processingSegment}
        onclick={async () => {
          processingSegment = true;
          try { await onProcessSegment(); } finally { processingSegment = false; }
        }}
      >
        {processingSegment ? 'Processing...' : 'Process Segment'}
      </button>
    {:else}
      {#if $midiWarnings.length > 0}
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">
          MIDI Errors ({$midiWarnings.length})
        </div>
        <div class="error-list">
          {#each $midiWarnings as warning, i}
            <div class="error-item-row">
              <button
                class="error-item"
                onclick={() => onSeekTime(warning.start_time)}
              >
                <span class="error-time">{formatTimecode(warning.start_time)}</span>
                <span class="error-badge {warning.type}">{warning.type === 'mismatch' ? 'WRONG' : 'MISSING'}</span>
                <span class="error-desc">
                  {#if warning.type === 'mismatch'}
                    Expected {warning.midi_note}, got {warning.cluster_note} ({Math.round(warning.cents_off ?? 0)}c off)
                  {:else}
                    Missing note {warning.midi_note}
                  {/if}
                </span>
              </button>
              <button
                class="error-dismiss"
                onclick={() => { $midiWarnings = $midiWarnings.filter((_, j) => j !== i); }}
                title="Dismiss"
              >&times;</button>
            </div>
          {/each}
        </div>
      {:else if $midiLoaded}
        <p class="placeholder">No MIDI errors found</p>
      {:else}
        <p class="placeholder">Click a note box to select it</p>
      {/if}
    {/if}
  </div>
</aside>

<style>
  .process-segment-btn {
    width: 100%;
    margin-top: 10px;
    padding: 6px 12px;
    background: var(--accent);
    color: var(--bg1);
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
  }
  .process-segment-btn:hover:not(:disabled) {
    filter: brightness(1.15);
  }
  .process-segment-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .error-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 60vh;
    overflow-y: auto;
  }

  .error-item-row {
    display: flex;
    align-items: stretch;
    gap: 0;
  }

  .error-item {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 4px 0 0 4px;
    cursor: pointer;
    text-align: left;
    color: var(--text);
    font-size: 0.78rem;
    flex: 1;
    min-width: 0;
  }

  .error-item:hover {
    border-color: var(--accent2);
    background: rgba(15, 155, 142, 0.1);
  }

  .error-dismiss {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    flex-shrink: 0;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-left: none;
    border-radius: 0 4px 4px 0;
    color: var(--text-dim);
    font-size: 0.9rem;
    cursor: pointer;
    padding: 0;
  }

  .error-dismiss:hover {
    background: rgba(233, 69, 96, 0.2);
    color: #e94560;
  }

  .error-time {
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--accent2);
    flex-shrink: 0;
  }

  .error-badge {
    font-size: 0.65rem;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    flex-shrink: 0;
  }

  .error-badge.mismatch {
    background: rgba(233, 69, 96, 0.25);
    color: #e94560;
  }

  .error-badge.missing {
    background: rgba(255, 165, 0, 0.25);
    color: #ffa500;
  }

  .error-desc {
    color: var(--text-dim);
    font-size: 0.72rem;
    width: 100%;
  }
</style>
