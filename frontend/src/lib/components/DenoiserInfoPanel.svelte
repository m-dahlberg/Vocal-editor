<script lang="ts">
  import { denoiserApplied, denoiserSpectrogramBefore } from '$lib/stores/appState';

  const hasAnalysis = $derived($denoiserSpectrogramBefore !== null);
</script>

<aside class="cluster-panel">
  <h2>Denoise Info</h2>
  <div class="cluster-details">
    <div class="summary-section">
      {#if $denoiserApplied}
        <div class="cluster-detail-row">
          <span class="label">Status</span>
          <span class="value applied">Applied</span>
        </div>
      {:else if hasAnalysis}
        <div class="cluster-detail-row">
          <span class="label">Status</span>
          <span class="value">Analyzed</span>
        </div>
      {:else}
        <p class="placeholder">No analysis yet</p>
        <p class="hint">Click Analyze to preview noise reduction, or Apply to process.</p>
        <p class="hint">Double-click the spectrogram to toggle before/after view.</p>
      {/if}
    </div>
  </div>
</aside>

<style>
  .summary-section {
    padding-bottom: 8px;
  }
  .applied {
    color: var(--success, #2dd4bf);
    font-weight: 500;
  }
  .hint {
    font-size: 0.72rem;
    color: var(--text2, #888);
    opacity: 0.6;
    margin-top: 6px;
    line-height: 1.4;
  }
</style>
