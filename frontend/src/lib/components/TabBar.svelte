<script lang="ts">
  import { activeTab, timeEdits, clusters } from '$lib/stores/appState';

  const hasTimeEdits = $derived($timeEdits.length > 0);
  const hasPitchEdits = $derived($clusters.some(c => c.pitch_shift_semitones !== 0 || (c.smoothing_percent ?? 0) !== 0));
</script>

<div class="tab-bar">
  <button
    class="tab-btn"
    class:active={$activeTab === 'pitch'}
    onclick={() => $activeTab = 'pitch'}
  >
    Pitch
    {#if hasTimeEdits}
      <span class="badge" title="Time edits active"></span>
    {/if}
  </button>
  <button
    class="tab-btn"
    class:active={$activeTab === 'time'}
    onclick={() => $activeTab = 'time'}
  >
    Time Alignment
    {#if hasPitchEdits}
      <span class="badge" title="Pitch edits active"></span>
    {/if}
  </button>
</div>

<style>
  .tab-bar {
    display: flex;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    padding: 0 60px;
  }
  .tab-btn {
    position: relative;
    padding: 8px 20px;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-dim);
    font-size: 0.82rem;
    font-weight: 500;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s;
  }
  .tab-btn:hover {
    color: var(--text);
  }
  .tab-btn.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }
  .badge {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent2, #f0a);
    margin-left: 5px;
    vertical-align: super;
  }
</style>
