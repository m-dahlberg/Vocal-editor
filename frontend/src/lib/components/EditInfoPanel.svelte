<script lang="ts">
  import { editClips, editSelectedClipIds, editApplied, viewXRange } from '$lib/stores/appState';

  interface Props {
    onSeekTime?: (t: number) => void;
  }

  let { onSeekTime }: Props = $props();

  const clipCount = $derived($editClips.length);
  const totalDuration = $derived(
    $editClips.length > 0
      ? Math.max(...$editClips.map(c => c.position + c.duration))
      : 0
  );

  const selectedClips = $derived(
    $editClips.filter(c => $editSelectedClipIds.has(c.id))
  );

  const selectedClip = $derived(
    selectedClips.length === 1 ? selectedClips[0] : null
  );

  function selectClip(id: string) {
    $editSelectedClipIds = new Set([id]);
    const clip = $editClips.find(c => c.id === id);
    if (clip) {
      onSeekTime?.(clip.position);
      // Center view on clip
      const span = $viewXRange[1] - $viewXRange[0];
      const center = clip.position + clip.duration / 2;
      $viewXRange = [Math.max(0, center - span / 2), center + span / 2];
    }
  }

  function formatTime(s: number): string {
    return s.toFixed(3) + 's';
  }
</script>

<aside class="cluster-panel">
  <h2>Clip Info</h2>
  <div class="cluster-details">
    <div class="summary-section">
      {#if clipCount > 0}
        <div class="cluster-detail-row">
          <span class="label">Clips</span>
          <span class="value">{clipCount}</span>
        </div>
        <div class="cluster-detail-row">
          <span class="label">Duration</span>
          <span class="value">{formatTime(totalDuration)}</span>
        </div>
        {#if $editApplied}
          <div class="cluster-detail-row">
            <span class="label">Status</span>
            <span class="value applied">Committed</span>
          </div>
        {/if}
      {:else}
        <p class="placeholder">No clips</p>
      {/if}
    </div>

    {#if selectedClip}
      <div class="selected-section">
        <div class="section-label">Selected Clip</div>
        <div class="cluster-detail-row">
          <span class="label">Position</span>
          <span class="value">{formatTime(selectedClip.position)}</span>
        </div>
        <div class="cluster-detail-row">
          <span class="label">Duration</span>
          <span class="value">{(selectedClip.duration * 1000).toFixed(1)} ms</span>
        </div>
        <div class="cluster-detail-row">
          <span class="label">Source</span>
          <span class="value">{formatTime(selectedClip.sourceOffset)}</span>
        </div>
      </div>
    {:else if selectedClips.length > 1}
      <div class="selected-section">
        <div class="section-label">{selectedClips.length} clips selected</div>
      </div>
    {/if}

    {#if clipCount > 0}
      <div class="clip-list-section">
        <div class="section-label">All Clips</div>
        <div class="clip-list">
          {#each [...$editClips].sort((a, b) => a.position - b.position) as clip}
            <button
              class="clip-item"
              class:selected={$editSelectedClipIds.has(clip.id)}
              onclick={() => selectClip(clip.id)}
            >
              <span class="clip-time">{formatTime(clip.position)}</span>
              <span class="clip-dur">{(clip.duration * 1000).toFixed(0)}ms</span>
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
  .clip-list-section {
    margin-top: 8px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  .clip-list {
    max-height: 300px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .clip-item {
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
  .clip-item:hover {
    background: var(--bg3, #2a2a4a);
  }
  .clip-item.selected {
    background: var(--bg3, #2a2a4a);
    color: var(--accent, #e94560);
  }
  .clip-time {
    min-width: 60px;
  }
  .clip-dur {
    opacity: 0.6;
  }
  .placeholder {
    opacity: 0.5;
    font-size: 0.8rem;
  }
</style>
