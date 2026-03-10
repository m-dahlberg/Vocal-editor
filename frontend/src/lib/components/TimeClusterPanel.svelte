<script lang="ts">
  import { selectedCluster, selectedIdx, clusters, timeEdits } from '$lib/stores/appState';

  // Find the time edit for the currently selected cluster
  let edit = $derived.by(() => {
    if ($selectedIdx === null) return null;
    return $timeEdits.find(e => e.clusterIdx === $selectedIdx) ?? null;
  });

  let originalCluster = $derived.by(() => {
    if ($selectedIdx === null) return null;
    return $clusters[$selectedIdx] ?? null;
  });

  let newStart = $derived(edit ? edit.newStart : (originalCluster?.start_time ?? 0));
  let newEnd = $derived(edit ? edit.newEnd : (originalCluster?.end_time ?? 0));
  let origDuration = $derived(originalCluster ? (originalCluster.end_time - originalCluster.start_time) * 1000 : 0);
  let newDuration = $derived((newEnd - newStart) * 1000);
  let timeShiftMs = $derived(edit ? (edit.newStart - (originalCluster?.start_time ?? 0)) * 1000 : 0);
  let tempoRatio = $derived(newDuration > 0 ? origDuration / newDuration : 1);
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

      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Original</div>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Start</span>
        <span class="value">{originalCluster.start_time.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">End</span>
        <span class="value">{originalCluster.end_time.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Duration</span>
        <span class="value">{origDuration.toFixed(0)} ms</span>
      </div>

      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Edited</div>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Start</span>
        <span class="value" class:edited={edit !== null}>{newStart.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">End</span>
        <span class="value" class:edited={edit !== null}>{newEnd.toFixed(3)}s</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Duration</span>
        <span class="value" class:edited={edit !== null}>{newDuration.toFixed(0)} ms</span>
      </div>

      <div style="margin-top: 10px; border-top: 1px solid var(--border); padding-top: 8px;">
        <div style="font-size:0.75rem; color:var(--accent2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">Delta</div>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Time shift</span>
        <span class="value">{timeShiftMs.toFixed(1)} ms</span>
      </div>
      <div class="cluster-detail-row">
        <span class="label">Tempo ratio</span>
        <span class="value">{tempoRatio.toFixed(3)}</span>
      </div>
    {:else}
      <p class="placeholder">Click a note box to select it</p>
    {/if}
  </div>
</aside>

<style>
  .edited {
    color: var(--warning) !important;
  }
</style>
