<script lang="ts">
  import { declickerDetections, declickerBandCenters, selectedClickIdx, declickerApplied, viewXRange } from '$lib/stores/appState';

  interface Props {
    onSeekTime?: (t: number) => void;
  }

  let { onSeekTime }: Props = $props();

  const clickCount = $derived($declickerDetections.length);
  const crackleCount = $derived($declickerDetections.filter(c => c.is_crackle).length);
  const totalAffectedMs = $derived(
    $declickerDetections.reduce((sum, c) => sum + (c.end_time - c.start_time) * 1000, 0)
  );

  const selectedClick = $derived(
    $selectedClickIdx !== null && $selectedClickIdx < $declickerDetections.length
      ? $declickerDetections[$selectedClickIdx]
      : null
  );

  function bandName(idx: number): string {
    if (idx < $declickerBandCenters.length) {
      const hz = $declickerBandCenters[idx];
      return hz >= 1000 ? `${(hz / 1000).toFixed(1)}k` : `${Math.round(hz)}`;
    }
    return `#${idx}`;
  }

  function selectClick(idx: number) {
    $selectedClickIdx = idx;
    const click = $declickerDetections[idx];
    if (click) {
      onSeekTime?.(click.start_time);
      // Center view on click
      const span = $viewXRange[1] - $viewXRange[0];
      const center = (click.start_time + click.end_time) / 2;
      $viewXRange = [Math.max(0, center - span / 2), center + span / 2];
    }
  }
</script>

<aside class="cluster-panel">
  <h2>Click Info</h2>
  <div class="cluster-details">
    <div class="summary-section">
      {#if clickCount > 0}
        <div class="cluster-detail-row">
          <span class="label">Clicks</span>
          <span class="value">{clickCount}</span>
        </div>
        {#if crackleCount > 0}
          <div class="cluster-detail-row">
            <span class="label">Crackle</span>
            <span class="value">{crackleCount}</span>
          </div>
        {/if}
        <div class="cluster-detail-row">
          <span class="label">Affected</span>
          <span class="value">{totalAffectedMs.toFixed(1)} ms</span>
        </div>
        {#if $declickerApplied}
          <div class="cluster-detail-row">
            <span class="label">Status</span>
            <span class="value applied">Applied</span>
          </div>
        {/if}
      {:else}
        <p class="placeholder">No clicks detected</p>
      {/if}
    </div>

    {#if selectedClick}
      <div class="selected-section">
        <div class="section-label">Selected Click</div>
        <div class="cluster-detail-row">
          <span class="label">Time</span>
          <span class="value">{selectedClick.start_time.toFixed(3)}s &ndash; {selectedClick.end_time.toFixed(3)}s</span>
        </div>
        <div class="cluster-detail-row">
          <span class="label">Duration</span>
          <span class="value">{((selectedClick.end_time - selectedClick.start_time) * 1000).toFixed(1)} ms</span>
        </div>
        <div class="cluster-detail-row">
          <span class="label">Ratio</span>
          <span class="value">{selectedClick.max_ratio_db.toFixed(1)} dB</span>
        </div>
        <div class="cluster-detail-row">
          <span class="label">Bands</span>
          <span class="value">{selectedClick.bands.map(b => bandName(b) + ' Hz').join(', ')}</span>
        </div>
        {#if selectedClick.is_crackle}
          <div class="cluster-detail-row">
            <span class="label">Type</span>
            <span class="value crackle">Crackle</span>
          </div>
        {/if}
      </div>
    {/if}

    {#if clickCount > 0}
      <div class="click-list-section">
        <div class="section-label">All Clicks</div>
        <div class="click-list">
          {#each $declickerDetections as click, i}
            <button
              class="click-item"
              class:selected={i === $selectedClickIdx}
              onclick={() => selectClick(i)}
            >
              <span class="click-time">{click.start_time.toFixed(3)}s</span>
              <span class="click-ratio">{click.max_ratio_db.toFixed(1)} dB</span>
              <span class="click-bands">{click.bands.length} band{click.bands.length !== 1 ? 's' : ''}</span>
            </button>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</aside>

<style>
  .summary-section {
    padding-bottom: 8px;
  }
  .selected-section {
    margin-top: 8px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .section-label {
    font-size: 0.75rem;
    color: var(--accent2, #f0a);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
  }
  .applied {
    color: var(--success, #2dd4bf);
    font-weight: 500;
  }
  .crackle {
    color: orange;
    font-weight: 500;
  }
  .click-list-section {
    margin-top: 8px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .click-list {
    max-height: 300px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .click-item {
    display: flex;
    gap: 8px;
    padding: 3px 6px;
    border: none;
    background: none;
    color: var(--text2, #ccc);
    font-size: 0.72rem;
    cursor: pointer;
    border-radius: 3px;
    text-align: left;
  }
  .click-item:hover {
    background: var(--bg3, #2a2a4a);
  }
  .click-item.selected {
    background: var(--bg3, #2a2a4a);
    color: var(--accent, #e94560);
  }
  .click-time {
    min-width: 60px;
  }
  .click-ratio {
    min-width: 50px;
    color: var(--warning, #f0a);
  }
  .click-bands {
    opacity: 0.6;
  }
</style>
