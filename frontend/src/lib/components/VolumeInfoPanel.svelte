<script lang="ts">
  import { breaths, selectedBreathIdx, clusters } from '$lib/stores/appState';
  import type { Breath } from '$lib/utils/types';

  interface Props {
    onSeekTime?: (t: number) => void;
    onRemoveBreath?: (id: number) => void;
  }

  let { onSeekTime, onRemoveBreath }: Props = $props();

  function fmt(s: number): string {
    const m = Math.floor(s / 60);
    const sec = (s - m * 60).toFixed(2).padStart(5, '0');
    return `${m}:${sec}`;
  }

  function selectBreath(idx: number, breath: Breath) {
    $selectedBreathIdx = idx;
    onSeekTime?.(breath.start_time);
  }

  function removeBreath(e: MouseEvent, id: number) {
    e.stopPropagation();
    onRemoveBreath?.(id);
  }

  const notesWithGain = $derived($clusters.filter(c => (c.gain_db ?? 0) !== 0).length);
</script>

<aside>
  <div class="panel-header">Volume Info</div>

  <div class="summary">
    <div class="stat">
      <span class="stat-val">{$breaths.length}</span>
      <span class="stat-label">Breaths</span>
    </div>
    <div class="stat">
      <span class="stat-val">{notesWithGain}</span>
      <span class="stat-label">Notes adjusted</span>
    </div>
  </div>

  {#if $breaths.length === 0}
    <div class="empty-msg">No breaths detected.<br>Use "Detect Breaths" or click on the waveform to add one.</div>
  {:else}
    <div class="list-header">
      <span>Start</span>
      <span>End</span>
      <span>RMS</span>
      <span></span>
    </div>
    <div class="breath-list">
      {#each $breaths as breath, i}
        <div
          class="breath-row"
          class:selected={$selectedBreathIdx === i}
          class:manual={breath.manually_created}
          role="button"
          tabindex="0"
          onclick={() => selectBreath(i, breath)}
          onkeydown={(e) => e.key === 'Enter' && selectBreath(i, breath)}
        >
          <span class="time">{fmt(breath.start_time)}</span>
          <span class="time">{fmt(breath.end_time)}</span>
          <span class="rms">{breath.rms_db.toFixed(1)} dB</span>
          <button
            class="remove-btn"
            title="Remove breath"
            onclick={(e) => removeBreath(e, breath.id)}
          >×</button>
        </div>
      {/each}
    </div>
  {/if}

  {#if $selectedBreathIdx !== null && $breaths[$selectedBreathIdx]}
    {@const b = $breaths[$selectedBreathIdx]}
    <div class="detail-panel">
      <div class="detail-title">Selected Breath</div>
      <div class="detail-row">
        <span>Start</span><span>{fmt(b.start_time)}</span>
      </div>
      <div class="detail-row">
        <span>End</span><span>{fmt(b.end_time)}</span>
      </div>
      <div class="detail-row">
        <span>Duration</span><span>{b.duration_ms.toFixed(0)} ms</span>
      </div>
      <div class="detail-row">
        <span>RMS</span><span>{b.rms_db.toFixed(1)} dB</span>
      </div>
      <div class="detail-row">
        <span>Gain</span><span class:positive={b.gain_db > 0} class:negative={b.gain_db < 0}>
          {b.gain_db > 0 ? '+' : ''}{b.gain_db.toFixed(1)} dB
        </span>
      </div>
      {#if b.manually_created}
        <div class="manual-badge">Manual</div>
      {/if}
    </div>
  {/if}
</aside>

<style>
  aside {
    flex: 1;
    overflow-y: auto;
    padding: 0;
    font-size: 0.78rem;
    color: var(--text);
  }

  .panel-header {
    padding: 10px 14px 6px;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border);
  }

  .summary {
    display: flex;
    gap: 12px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }

  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
  }

  .stat-val {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--accent2);
  }

  .stat-label {
    font-size: 0.65rem;
    color: var(--text-dim);
    margin-top: 1px;
  }

  .empty-msg {
    padding: 16px 14px;
    color: var(--text-dim);
    font-size: 0.75rem;
    line-height: 1.5;
  }

  .list-header {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 20px;
    gap: 4px;
    padding: 4px 14px;
    font-size: 0.65rem;
    color: var(--text-dim);
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
  }

  .breath-list {
    overflow-y: auto;
    max-height: 220px;
  }

  .breath-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 20px;
    gap: 4px;
    padding: 5px 14px;
    width: 100%;
    border: none;
    background: none;
    color: var(--text);
    font-size: 0.72rem;
    cursor: pointer;
    text-align: left;
    border-bottom: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
  }

  .breath-row:hover {
    background: var(--bg3);
  }

  .breath-row.selected {
    background: rgba(15, 155, 142, 0.15);
    color: var(--accent2);
  }

  .breath-row.manual {
    border-left: 2px solid var(--accent);
  }

  .time { font-variant-numeric: tabular-nums; }

  .rms { color: var(--text-dim); }

  .remove-btn {
    background: none;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.9rem;
    line-height: 1;
    padding: 0;
  }
  .remove-btn:hover { color: var(--accent); }

  .detail-panel {
    padding: 10px 14px;
    border-top: 1px solid var(--border);
    background: var(--bg);
  }

  .detail-title {
    font-size: 0.68rem;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
    font-size: 0.75rem;
  }

  .detail-row span:first-child { color: var(--text-dim); }

  .positive { color: #4caf50; }
  .negative { color: var(--accent); }

  .manual-badge {
    margin-top: 6px;
    display: inline-block;
    padding: 2px 6px;
    background: rgba(233, 69, 96, 0.2);
    color: var(--accent);
    border-radius: 3px;
    font-size: 0.65rem;
    font-weight: 600;
  }
</style>
