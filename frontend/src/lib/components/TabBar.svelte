<script lang="ts">
  import { activeTab, pipelineStatus, log } from '$lib/stores/appState';
  import type { PipelineStep } from '$lib/stores/appState';

  const TAB_TO_STEP: Record<string, PipelineStep> = {
    declicker: 'declicker',
    denoise: 'denoise',
    edit: 'edit',
    pitch: 'pitchtime',
    time: 'pitchtime',
  };

  function getStepStatus(tab: string): string {
    return $pipelineStatus[TAB_TO_STEP[tab]];
  }

  function handleTabClick(tab: 'declicker' | 'denoise' | 'edit' | 'pitch' | 'time') {
    const status = getStepStatus(tab);
    if (status === 'stale') {
      log('Press Update All to refresh stale tabs', 'warn');
      return;
    }
    $activeTab = tab;
  }
</script>

<div class="tab-bar">
  {#each [
    { id: 'declicker' as const, label: 'De-Click' },
    { id: 'denoise' as const, label: 'Denoise' },
    { id: 'edit' as const, label: 'Fine Edit' },
    { id: 'pitch' as const, label: 'Pitch' },
    { id: 'time' as const, label: 'Time Alignment' },
  ] as tab}
    {@const status = getStepStatus(tab.id)}
    <button
      class="tab-btn"
      class:active={$activeTab === tab.id}
      class:stale={status === 'stale'}
      onclick={() => handleTabClick(tab.id)}
      title={status === 'stale' ? 'Source audio changed — press Update All' : ''}
    >
      {tab.label}
      {#if status === 'done'}
        <span class="badge badge-done" title="Up to date"></span>
      {:else if status === 'stale'}
        <span class="badge badge-stale" title="Needs update"></span>
      {/if}
    </button>
  {/each}
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
  .tab-btn.stale {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .badge {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-left: 5px;
    vertical-align: super;
  }
  .badge-done {
    background: #4caf50;
  }
  .badge-stale {
    background: #f44336;
  }
</style>
