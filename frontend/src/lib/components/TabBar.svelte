<script lang="ts">
  import { activeTab } from '$lib/stores/appState';
</script>

<div class="tab-bar">
  <button
    class="tab-btn"
    class:active={$activeTab === 'pitch'}
    onclick={() => $activeTab = 'pitch'}
  >Pitch</button>
  <button
    class="tab-btn"
    class:active={$activeTab === 'time'}
    onclick={() => $activeTab = 'time'}
  >Time Alignment</button>
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
</style>
