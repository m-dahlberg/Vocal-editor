<script lang="ts">
  import { editClips, editSelectedClipIds, editApplied, audioLoaded } from '$lib/stores/appState';

  interface Props {
    onCommit: () => void;
    onReset: () => void;
    onDeleteSelected: () => void;
    zoomPercent: number;
    nudgeMs: number;
  }

  let { onCommit, onReset, onDeleteSelected, zoomPercent = $bindable(20), nudgeMs = $bindable(50) }: Props = $props();

  const clipCount = $derived($editClips.length);
  const selectedCount = $derived($editSelectedClipIds.size);
  const totalDuration = $derived(
    $editClips.length > 0
      ? Math.max(...$editClips.map(c => c.position + c.duration))
      : 0
  );
</script>

<aside class="param-panel">
  <h2>Fine Edit</h2>

  <section>
    <h3>Settings</h3>
    <div class="setting-row">
      <label for="zoom-pct">Zoom step (%)</label>
      <input id="zoom-pct" type="number" min="1" max="200" step="1" bind:value={zoomPercent} />
    </div>
    <div class="setting-row">
      <label for="nudge-ms">Nudge (ms)</label>
      <input id="nudge-ms" type="number" min="1" max="10000" step="1" bind:value={nudgeMs} />
    </div>
  </section>

  <section>
    <h3>Shortcuts</h3>
    <div class="shortcut-list">
      <div class="shortcut-row"><kbd>T</kbd> <span>Zoom in</span></div>
      <div class="shortcut-row"><kbd>R</kbd> <span>Zoom out</span></div>
      <div class="shortcut-row"><kbd>,</kbd> <span>Nudge left</span></div>
      <div class="shortcut-row"><kbd>.</kbd> <span>Nudge right</span></div>
      <div class="shortcut-row"><kbd>B</kbd> <span>Split at cursor</span></div>
      <div class="shortcut-row"><kbd>A</kbd> <span>Trim start to cursor</span></div>
      <div class="shortcut-row"><kbd>S</kbd> <span>Trim end to cursor</span></div>
      <div class="shortcut-row"><kbd>D</kbd> <span>Fade in to cursor</span></div>
      <div class="shortcut-row"><kbd>G</kbd> <span>Fade out from cursor</span></div>
      <div class="shortcut-row"><kbd>Del</kbd> <span>Delete selected</span></div>
      <div class="shortcut-row"><kbd>Shift+Click</kbd> <span>Multi-select</span></div>
    </div>
  </section>

  <section>
    <div class="param-group">
      <div class="status-info">
        {#if clipCount > 0}
          <span class="clip-count">{clipCount} clip{clipCount !== 1 ? 's' : ''}</span>
          <span class="dim">{totalDuration.toFixed(2)}s total</span>
          {#if selectedCount > 0}
            <span class="dim">{selectedCount} selected</span>
          {/if}
        {:else}
          <span class="dim">No audio loaded</span>
        {/if}
        {#if $editApplied}
          <span class="applied-badge">Edit committed</span>
        {/if}
      </div>

      <button class="btn-secondary btn-small" disabled={selectedCount === 0} onclick={onDeleteSelected}>
        Delete Selected
      </button>

      <button class="btn-accent" disabled={!$audioLoaded || clipCount === 0} onclick={onCommit}>
        Commit Edit
      </button>

      {#if clipCount > 0 || $editApplied}
        <button class="btn btn-secondary btn-small" onclick={onReset}>
          Reset
        </button>
      {/if}
    </div>
  </section>
</aside>

<style>
  .setting-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 0.75rem;
    color: var(--text2, #ccc);
    margin-bottom: 4px;
  }
  .setting-row label {
    flex: 1;
  }
  .setting-row input[type="number"] {
    width: 60px;
    background: var(--bg3, #2a2a4a);
    border: 1px solid var(--border, #333);
    border-radius: 3px;
    color: var(--text, #eee);
    font-size: 0.75rem;
    padding: 2px 4px;
    text-align: right;
  }
  .shortcut-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.75rem;
  }
  .shortcut-row {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text2, #ccc);
  }
  kbd {
    background: var(--bg3, #2a2a4a);
    border: 1px solid var(--border, #333);
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 0.7rem;
    font-family: monospace;
    color: var(--text, #eee);
    min-width: 32px;
    text-align: center;
  }
  .status-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.8rem;
    padding: 4px 0;
  }
  .clip-count {
    color: var(--accent2, #f0a);
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
    background: var(--accent, #e94560);
    color: #fff;
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
  .btn-secondary {
    width: 100%;
    padding: 3px 8px;
    font-size: 0.72rem;
    margin-top: 4px;
    background: none;
    border: 1px solid var(--border, #333);
    border-radius: 4px;
    color: var(--text2, #ccc);
    cursor: pointer;
  }
  .btn-secondary:hover:not(:disabled) {
    background: var(--bg3, #2a2a4a);
  }
  .btn-secondary:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .btn-small {
    padding: 3px 8px;
    font-size: 0.72rem;
    margin-top: 4px;
  }
</style>
