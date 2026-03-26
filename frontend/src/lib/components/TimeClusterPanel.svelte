<script lang="ts">
  import { selectedCluster, selectedIdx, clusters, stretchMarkers } from '$lib/stores/appState';
  import { params } from '$lib/stores/params';

  interface Props {
    onProcessSegment: () => void;
  }

  let { onProcessSegment }: Props = $props();

  let processingSegment = $state(false);

  // Find stretch markers adjacent to the selected cluster
  let adjacentMarkers = $derived.by(() => {
    if ($selectedIdx === null) return { left: null, right: null };
    const idx = $selectedIdx;
    const markers = $stretchMarkers;
    const left = markers.find(m => m.rightClusterIdx === idx) ?? null;
    const right = markers.find(m => m.leftClusterIdx === idx) ?? null;
    return { left, right };
  });

  let originalCluster = $derived.by(() => {
    if ($selectedIdx === null) return null;
    return $clusters[$selectedIdx] ?? null;
  });

  let origDuration = $derived(originalCluster ? (originalCluster.end_time - originalCluster.start_time) * 1000 : 0);

  // Compute effective time shift from adjacent markers
  let leftDeltaMs = $derived(adjacentMarkers.left
    ? (adjacentMarkers.left.currentTime - adjacentMarkers.left.originalTime) * 1000
    : 0);
  let rightDeltaMs = $derived(adjacentMarkers.right
    ? (adjacentMarkers.right.currentTime - adjacentMarkers.right.originalTime) * 1000
    : 0);

  let movedMarkerCount = $derived($stretchMarkers.filter(m => Math.abs(m.currentTime - m.originalTime) > 0.0001).length);
</script>

<aside class="cluster-panel">
  <h2>Time Info</h2>
  <div class="cluster-details">
    {#if $selectedCluster && originalCluster}
      <div class="cluster-detail-row">
        <span class="label">Cluster</span>
        <span class="value">#{($selectedIdx ?? 0) + 1}</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Note</span>
        <span class="value">{$selectedCluster.note}</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Duration</span>
        <span class="value">{origDuration.toFixed(0)} ms</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Range</span>
        <span class="value">{originalCluster.start_time.toFixed(3)}s – {originalCluster.end_time.toFixed(3)}s</span>
      </div>

      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Adjacent Markers</div>
      </div>

      {#if adjacentMarkers.left}
        <div class="cluster-detail-row">
          <span class="label">Left marker</span>
          <span class="value" class:edited={leftDeltaMs !== 0}>
            {leftDeltaMs !== 0 ? `${leftDeltaMs > 0 ? '+' : ''}${leftDeltaMs.toFixed(1)}ms` : 'unchanged'}
          </span>
        </div>
      {:else}
        <div class="cluster-detail-row">
          <span class="label">Left marker</span>
          <span class="value dim">none (first cluster)</span>
        </div>
      {/if}

      {#if adjacentMarkers.right}
        <div class="cluster-detail-row">
          <span class="label">Right marker</span>
          <span class="value" class:edited={rightDeltaMs !== 0}>
            {rightDeltaMs !== 0 ? `${rightDeltaMs > 0 ? '+' : ''}${rightDeltaMs.toFixed(1)}ms` : 'unchanged'}
          </span>
        </div>
      {:else}
        <div class="cluster-detail-row">
          <span class="label">Right marker</span>
          <span class="value dim">none (last cluster)</span>
        </div>
      {/if}

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
      <p class="placeholder">Click a note region to select it</p>
      {#if movedMarkerCount > 0}
        <div class="marker-summary">{movedMarkerCount} marker{movedMarkerCount > 1 ? 's' : ''} moved</div>
      {/if}
    {/if}
  </div>
</aside>

<style>
  .edited {
    color: var(--warning) !important;
  }
  .dim {
    opacity: 0.5;
  }
  .marker-summary {
    padding: 6px 10px;
    margin-top: 8px;
    font-size: 0.75rem;
    color: #2dd4bf;
    background: rgba(45,212,191,0.08);
    border-radius: 4px;
    text-align: center;
  }
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
</style>
