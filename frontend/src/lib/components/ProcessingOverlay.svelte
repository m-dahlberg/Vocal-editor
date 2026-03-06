<script lang="ts">
  import { processing } from '$lib/stores/appState';
</script>

<div id="processingOverlay" class="processing-overlay" class:hidden={!$processing}>
  <div class="processing-text">Processing...</div>
</div>
