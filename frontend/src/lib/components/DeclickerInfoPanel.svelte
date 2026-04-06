<script lang="ts">
  import {
    declickerDetections, declickerBandCenters, selectedClickIdx, declickerApplied, viewXRange,
    declickerCheckedIndices, declickerProcessedClicks, declickerFilterState, declickerVisibleIndices,
  } from '$lib/stores/appState';

  interface Props {
    onSeekTime?: (t: number) => void;
  }

  let { onSeekTime }: Props = $props();

  const clickCount = $derived($declickerDetections.length);
  const visibleCount = $derived($declickerVisibleIndices.length);
  const crackleCount = $derived($declickerDetections.filter(c => c.is_crackle).length);
  const totalAffectedMs = $derived(
    $declickerDetections.reduce((sum, c) => sum + (c.end_time - c.start_time) * 1000, 0)
  );
  const checkedCount = $derived($declickerCheckedIndices.size);

  const selectedClick = $derived(
    $selectedClickIdx !== null && $selectedClickIdx < $declickerDetections.length
      ? $declickerDetections[$selectedClickIdx]
      : null
  );

  // Frequency range from detected bands
  const freqMin = $derived($declickerBandCenters.length > 0 ? Math.floor($declickerBandCenters[0]) : 20);
  const freqMax = $derived($declickerBandCenters.length > 0 ? Math.ceil($declickerBandCenters[$declickerBandCenters.length - 1]) : 20000);

  // Map log scale slider (0-1000) to Hz
  function sliderToHz(val: number, min: number, max: number): number {
    const logMin = Math.log10(Math.max(1, min));
    const logMax = Math.log10(Math.max(1, max));
    return Math.round(Math.pow(10, logMin + (val / 1000) * (logMax - logMin)));
  }

  function hzToSlider(hz: number, min: number, max: number): number {
    const logMin = Math.log10(Math.max(1, min));
    const logMax = Math.log10(Math.max(1, max));
    const logHz = Math.log10(Math.max(1, hz));
    return Math.round(((logHz - logMin) / (logMax - logMin)) * 1000);
  }

  let freqLowSlider = $derived(hzToSlider($declickerFilterState.freqLowHz, freqMin, freqMax));
  let freqHighSlider = $derived(hzToSlider($declickerFilterState.freqHighHz, freqMin, freqMax));

  function onFreqLowSlider(e: Event) {
    const val = parseInt((e.target as HTMLInputElement).value);
    const hz = sliderToHz(val, freqMin, freqMax);
    $declickerFilterState = { ...$declickerFilterState, freqLowHz: Math.min(hz, $declickerFilterState.freqHighHz - 1) };
  }

  function onFreqHighSlider(e: Event) {
    const val = parseInt((e.target as HTMLInputElement).value);
    const hz = sliderToHz(val, freqMin, freqMax);
    $declickerFilterState = { ...$declickerFilterState, freqHighHz: Math.max(hz, $declickerFilterState.freqLowHz + 1) };
  }

  function formatHz(hz: number): string {
    return hz >= 1000 ? `${(hz / 1000).toFixed(1)}k` : `${hz}`;
  }

  function bandName(idx: number): string {
    if (idx < $declickerBandCenters.length) {
      const hz = $declickerBandCenters[idx];
      return hz >= 1000 ? `${(hz / 1000).toFixed(1)}k` : `${Math.round(hz)}`;
    }
    return `#${idx}`;
  }

  function isProcessed(idx: number): boolean {
    const click = $declickerDetections[idx];
    if (!click) return false;
    return $declickerProcessedClicks.some(p =>
      Math.abs(p.start_time - click.start_time) < 0.001 && Math.abs(p.end_time - click.end_time) < 0.001
    );
  }

  function selectClick(idx: number) {
    $selectedClickIdx = idx;
    const click = $declickerDetections[idx];
    if (click) {
      onSeekTime?.(click.start_time);
      const span = $viewXRange[1] - $viewXRange[0];
      const center = (click.start_time + click.end_time) / 2;
      $viewXRange = [Math.max(0, center - span / 2), center + span / 2];
    }
  }

  function toggleCheck(idx: number) {
    const s = new Set($declickerCheckedIndices);
    if (s.has(idx)) {
      s.delete(idx);
      // If this click was processed, remove it from processed list too
      if (isProcessed(idx)) {
        const click = $declickerDetections[idx];
        $declickerProcessedClicks = $declickerProcessedClicks.filter(p =>
          !(Math.abs(p.start_time - click.start_time) < 0.001 && Math.abs(p.end_time - click.end_time) < 0.001)
        );
      }
    } else {
      s.add(idx);
    }
    $declickerCheckedIndices = s;
  }

  function toggleSelectAll() {
    const visible = $declickerVisibleIndices;
    const allChecked = visible.every(i => $declickerCheckedIndices.has(i));
    const s = new Set($declickerCheckedIndices);
    if (allChecked) {
      visible.forEach(i => s.delete(i));
    } else {
      visible.forEach(i => s.add(i));
    }
    $declickerCheckedIndices = s;
  }

  const allVisibleChecked = $derived(() => {
    const visible = $declickerVisibleIndices;
    return visible.length > 0 && visible.every(i => $declickerCheckedIndices.has(i));
  });
</script>

<aside class="cluster-panel">
  <h2>Click Info</h2>
  <div class="cluster-details">
    <div class="summary-section">
      {#if clickCount > 0}
        <div class="cluster-detail-row">
          <span class="label">Clicks</span>
          <span class="value">{visibleCount} / {clickCount}</span>
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
        {#if $declickerProcessedClicks.length > 0}
          <div class="cluster-detail-row">
            <span class="label">Removed</span>
            <span class="value removed">{$declickerProcessedClicks.length}</span>
          </div>
        {/if}
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
      <div class="filter-section">
        <div class="section-label">Filters</div>
        <label class="filter-label">
          <span class="filter-name">Min ratio</span>
          <span class="filter-value">{$declickerFilterState.minRatioDb.toFixed(1)} dB</span>
          <input
            type="range" min="0" max="40" step="0.5"
            value={$declickerFilterState.minRatioDb}
            oninput={(e) => $declickerFilterState = { ...$declickerFilterState, minRatioDb: parseFloat((e.target as HTMLInputElement).value) }}
          >
        </label>
        <label class="filter-label">
          <span class="filter-name">Min length</span>
          <span class="filter-value">{$declickerFilterState.minLengthMs.toFixed(1)} ms</span>
          <input
            type="range" min="0" max="50" step="0.5"
            value={$declickerFilterState.minLengthMs}
            oninput={(e) => $declickerFilterState = { ...$declickerFilterState, minLengthMs: parseFloat((e.target as HTMLInputElement).value) }}
          >
        </label>
        <div class="filter-label">
          <span class="filter-name">Freq low</span>
          <span class="filter-value">{formatHz($declickerFilterState.freqLowHz)} Hz</span>
          <input type="range" min="0" max="1000" step="1" value={freqLowSlider} oninput={onFreqLowSlider}>
        </div>
        <div class="filter-label">
          <span class="filter-name">Freq high</span>
          <span class="filter-value">{formatHz($declickerFilterState.freqHighHz)} Hz</span>
          <input type="range" min="0" max="1000" step="1" value={freqHighSlider} oninput={onFreqHighSlider}>
        </div>
      </div>

      <div class="click-list-section">
        <div class="list-header">
          <div class="section-label">Clicks ({visibleCount})</div>
          <div class="list-header-actions">
            {#if checkedCount > 0}
              <span class="checked-count">{checkedCount} selected</span>
            {/if}
            <label class="select-all-label">
              <input
                type="checkbox"
                checked={allVisibleChecked()}
                onchange={toggleSelectAll}
              >
              All
            </label>
          </div>
        </div>
        <div class="click-list">
          {#each $declickerVisibleIndices as idx}
            {@const click = $declickerDetections[idx]}
            {@const processed = isProcessed(idx)}
            {@const checked = $declickerCheckedIndices.has(idx)}
            <div
              class="click-item"
              class:selected={idx === $selectedClickIdx}
              class:processed
            >
              <input
                type="checkbox"
                checked={checked}
                onchange={() => toggleCheck(idx)}
                onclick={(e) => e.stopPropagation()}
              >
              <button
                class="click-item-body"
                class:selected={idx === $selectedClickIdx}
                onclick={() => selectClick(idx)}
              >
                <span class="click-time">{click.start_time.toFixed(3)}s</span>
                <span class="click-ratio">{click.max_ratio_db.toFixed(1)} dB</span>
                <span class="click-bands">{click.bands.length} band{click.bands.length !== 1 ? 's' : ''}</span>
                {#if processed}
                  <span class="removed-badge">removed</span>
                {/if}
              </button>
            </div>
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
  .removed {
    color: var(--warning, #f0a);
    font-weight: 500;
  }
  .crackle {
    color: orange;
    font-weight: 500;
  }
  .filter-section {
    margin-top: 8px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
    padding-right: 4px;
  }
  .filter-label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 0.7rem;
    color: var(--text2, #ccc);
    margin-bottom: 4px;
  }
  .filter-name {
    min-width: 58px;
    opacity: 0.7;
  }
  .filter-value {
    min-width: 46px;
    text-align: right;
    color: var(--accent, #e94560);
    font-size: 0.68rem;
  }
  .filter-label input[type="range"] {
    flex: 1;
    height: 3px;
    accent-color: var(--accent, #e94560);
  }
  .click-list-section {
    margin-top: 8px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .list-header .section-label {
    margin-bottom: 0;
  }
  .list-header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.7rem;
  }
  .checked-count {
    color: var(--success, #2dd4bf);
    font-size: 0.68rem;
  }
  .select-all-label {
    display: flex;
    align-items: center;
    gap: 3px;
    color: var(--text2, #ccc);
    cursor: pointer;
    font-size: 0.7rem;
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
    align-items: center;
    gap: 4px;
    padding: 1px 2px;
    border-radius: 3px;
  }
  .click-item:hover {
    background: var(--bg3, #2a2a4a);
  }
  .click-item.selected {
    background: var(--bg3, #2a2a4a);
  }
  .click-item.processed {
    opacity: 0.45;
  }
  .click-item input[type="checkbox"] {
    flex-shrink: 0;
    accent-color: var(--accent, #e94560);
    cursor: pointer;
  }
  .click-item-body {
    display: flex;
    gap: 8px;
    flex: 1;
    padding: 2px 4px;
    border: none;
    background: none;
    color: var(--text2, #ccc);
    font-size: 0.72rem;
    cursor: pointer;
    border-radius: 3px;
    text-align: left;
  }
  .click-item-body.selected {
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
  .removed-badge {
    font-size: 0.62rem;
    color: #888;
    font-style: italic;
    margin-left: auto;
  }
</style>
