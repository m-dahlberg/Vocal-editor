<script lang="ts">
  import { stretchMarkers, selectedMarkerIdx, clusters, advancedView } from '$lib/stores/appState';
  import { params } from '$lib/stores/params';

  interface Props {
    onProcessSegment: () => void;
  }

  let { onProcessSegment }: Props = $props();

  let processingSegment = $state(false);

  let movedMarkerCount = $derived($stretchMarkers.filter(m => Math.abs(m.currentTime - m.originalTime) > 0.0001).length);

  let selectedMarker = $derived($selectedMarkerIdx !== null ? $stretchMarkers[$selectedMarkerIdx] ?? null : null);
  let selectedDeltaMs = $derived(selectedMarker
    ? (selectedMarker.currentTime - selectedMarker.originalTime) * 1000
    : 0);
  let selectedIsMoved = $derived(Math.abs(selectedDeltaMs) > 0.1);

  // Left/right cluster names for the selected marker
  let leftClusterNote = $derived.by(() => {
    if (!selectedMarker) return null;
    const idx = selectedMarker.leftClusterIdx;
    if (idx >= 0 && idx < $clusters.length) return $clusters[idx].note;
    return null;
  });
  let rightClusterNote = $derived.by(() => {
    if (!selectedMarker) return null;
    const idx = selectedMarker.rightClusterIdx;
    if (idx >= 0 && idx < $clusters.length) return $clusters[idx].note;
    return null;
  });
</script>

<aside class="cluster-panel">
  <h2>Time Info</h2>
  <div class="cluster-details">
    <div class="marker-info-section">
      {#if $stretchMarkers.length > 0}
        <div class="cluster-detail-row">
          <span class="label">Markers</span>
          <span class="value">{$stretchMarkers.length}</span>
        </div>
        {#if movedMarkerCount > 0}
          <div class="cluster-detail-row">
            <span class="label">Moved</span>
            <span class="value edited">{movedMarkerCount}</span>
          </div>
        {/if}
      {:else}
        <p class="placeholder">No markers (analyze audio first)</p>
      {/if}
    </div>

    {#if selectedMarker}
      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Selected Marker</div>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Position</span>
        <span class="value">{selectedMarker.currentTime.toFixed(3)}s</span>
      </div>
      {#if selectedIsMoved}
        <div class="cluster-detail-row">
          <span class="label">Delta</span>
          <span class="value edited">{selectedDeltaMs > 0 ? '+' : ''}{selectedDeltaMs.toFixed(1)}ms</span>
        </div>
      {/if}
      {#if leftClusterNote || rightClusterNote}
        <div class="cluster-detail-row">
          <span class="label">Between</span>
          <span class="value">{leftClusterNote ?? '—'} / {rightClusterNote ?? '—'}</span>
        </div>
      {/if}
    {/if}

    {#if $advancedView}
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
    {/if}
  </div>
</aside>

<style>
  .edited {
    color: var(--warning) !important;
  }
  .marker-info-section {
    margin-bottom: 4px;
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
