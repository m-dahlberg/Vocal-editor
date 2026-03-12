<script lang="ts">
  import { mainVolume, referenceVolume, backingVolume, referenceLoaded, backingLoaded } from '$lib/stores/appState';
</script>

<style>
  .mixer {
    padding: 10px 12px;
    border-top: 1px solid var(--border);
  }

  .mixer h3 {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-dim);
    margin-bottom: 8px;
  }

  .mixer-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .mixer-row label {
    font-size: 0.78rem;
    color: var(--text);
    width: 58px;
    flex-shrink: 0;
  }

  .mixer-row input[type="range"] {
    flex: 1;
  }

  .mixer-row .vol-val {
    font-size: 0.72rem;
    color: var(--text-dim);
    width: 28px;
    text-align: right;
    font-family: monospace;
  }
</style>

<div class="mixer">
  <h3>Mixer</h3>
  <div class="mixer-row">
    <label>Main</label>
    <input type="range" min="0" max="1" step="0.01" bind:value={$mainVolume}>
    <span class="vol-val">{Math.round($mainVolume * 100)}</span>
  </div>
  <div class="mixer-row">
    <label>Reference</label>
    <input type="range" min="0" max="1" step="0.01" bind:value={$referenceVolume} disabled={!$referenceLoaded}>
    <span class="vol-val">{Math.round($referenceVolume * 100)}</span>
  </div>
  <div class="mixer-row">
    <label>Backing</label>
    <input type="range" min="0" max="1" step="0.01" bind:value={$backingVolume} disabled={!$backingLoaded}>
    <span class="vol-val">{Math.round($backingVolume * 100)}</span>
  </div>
</div>
