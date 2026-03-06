<script lang="ts">
  import { showHelp } from '$lib/stores/appState';

  function close() {
    $showHelp = false;
  }

  function onOverlayClick(e: MouseEvent) {
    if (e.target === e.currentTarget) close();
  }
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') close(); }} />

{#if $showHelp}
<div class="help-overlay" onclick={onOverlayClick} role="dialog" aria-modal="true">
  <div class="help-lightbox">
    <div class="help-header">
      <h2>User Guide</h2>
      <button class="btn btn-icon help-close" onclick={close}>&times;</button>
    </div>
    <div class="help-body">

      <h2>Getting Started</h2>
      <ol>
        <li><strong>Upload audio</strong> — Click the <strong>Audio</strong> button to load a vocal file (WAV, MP3, FLAC, or AIFF). Pitch analysis runs automatically after upload.</li>
        <li><strong>Upload MIDI (optional)</strong> — Click the <strong>MIDI</strong> button to load a reference MIDI file.</li>
        <li><strong>Review the pitch plot</strong> — The blue line shows detected pitch. Orange boxes represent detected note clusters.</li>
        <li><strong>Auto-correct</strong> — Click <strong>Correct</strong> to calculate pitch corrections.</li>
        <li><strong>Manual editing</strong> — Drag boxes, adjust ramps, and smoothing.</li>
        <li><strong>Update Audio</strong> — Click to apply all edits via Rubberband.</li>
        <li><strong>Preview</strong> — Press <strong>Space</strong> to listen.</li>
        <li><strong>Export</strong> — Download the corrected audio as WAV.</li>
      </ol>

      <hr>

      <h2>Pitch Plot Controls</h2>

      <h3>Selecting Notes</h3>
      <ul>
        <li><strong>Click a box</strong> — Select that cluster.</li>
        <li><strong>Shift + Click</strong> — Add/remove from multi-selection.</li>
        <li><strong>Drag on empty space</strong> — Rubber-band select.</li>
        <li><strong>Click empty space</strong> — Clear selection.</li>
      </ul>

      <h3>Adjusting Pitch</h3>
      <ul>
        <li><strong>Drag a box up/down</strong> — Shift pitch. Multi-selection moves together.</li>
      </ul>

      <h3>Adjusting Timing</h3>
      <ul>
        <li><strong>Drag left/right edge</strong> — Resize cluster.</li>
      </ul>

      <h3>Adjusting Ramps</h3>
      <ul>
        <li><strong>Ctrl + Drag edge</strong> — Adjust ramp in/out duration.</li>
      </ul>

      <h3>Adjusting Smoothing</h3>
      <ul>
        <li><strong>Ctrl + Drag body vertically</strong> — Adjust smoothing.</li>
      </ul>

      <h3>Drawing New Clusters</h3>
      <ul>
        <li><strong>Alt + Drag</strong> — Draw a new note cluster.</li>
      </ul>

      <h3>Deleting Clusters</h3>
      <ul>
        <li><strong>Delete / Backspace</strong> — Remove selected cluster.</li>
      </ul>

      <h3>Navigation</h3>
      <ul>
        <li><strong>Scroll</strong> — Zoom time axis.</li>
        <li><strong>Shift + Scroll</strong> — Zoom frequency axis.</li>
        <li><strong>Ctrl + Shift + Drag</strong> — Pan.</li>
      </ul>

      <hr>

      <h2>Keyboard Shortcuts</h2>
      <table>
        <thead><tr><th>Key</th><th>Action</th></tr></thead>
        <tbody>
          <tr><td><strong>Space</strong></td><td>Play / Pause</td></tr>
          <tr><td><strong>Delete / Backspace</strong></td><td>Delete selected cluster</td></tr>
        </tbody>
      </table>

    </div>
  </div>
</div>
{/if}
