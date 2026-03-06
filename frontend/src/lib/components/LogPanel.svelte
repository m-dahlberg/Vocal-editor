<script lang="ts">
  import { logMessages } from '$lib/stores/appState';

  let logEl: HTMLDivElement;

  $effect(() => {
    // Auto-scroll on new messages
    if ($logMessages.length && logEl) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  });
</script>

<div class="log-container">
  <div id="logArea" bind:this={logEl}>
    {#each $logMessages as msg}
      <div class="log-{msg.type}">[{msg.timestamp}] {msg.text}</div>
    {/each}
  </div>
</div>
