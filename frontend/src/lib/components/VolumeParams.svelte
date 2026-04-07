<script lang="ts">
  import { audioLoaded, volumeMacroParams } from '$lib/stores/appState';
  import type { BreathDetectionParams, VolumeParams } from '$lib/utils/types';

  interface Props {
    onDetectNotes: () => void;
    onDetectBreaths: (params: BreathDetectionParams) => void;
    onApplyVolume: (volumeParams: VolumeParams) => void;
    onReset: () => void;
  }

  let { onDetectNotes, onDetectBreaths, onApplyVolume, onReset }: Props = $props();

  // Breath detection params
  let minBreathLengthMs = $state(80);
  let minBreathVolumeDb = $state(-50);
  let maxBreathVolumeDb = $state(-15);

  // Note macro controls
  let noteMinRmsDb = $state(-60);
  let noteMaxRmsDb = $state(0);
  let noteGlobalOffsetDb = $state(0);

  // Breath macro controls
  let breathMinRmsDb = $state(-60);
  let breathMaxRmsDb = $state(0);
  let breathGlobalOffsetDb = $state(0);

  export function getVolumeParams(): VolumeParams {
    return {
      note_min_rms_db: noteMinRmsDb,
      note_max_rms_db: noteMaxRmsDb,
      note_global_offset_db: noteGlobalOffsetDb,
      breath_min_rms_db: breathMinRmsDb,
      breath_max_rms_db: breathMaxRmsDb,
      breath_global_offset_db: breathGlobalOffsetDb,
    };
  }

  // Sync to store for real-time preview
  $effect(() => {
    $volumeMacroParams = {
      note_min_rms_db: noteMinRmsDb,
      note_max_rms_db: noteMaxRmsDb,
      note_global_offset_db: noteGlobalOffsetDb,
      breath_min_rms_db: breathMinRmsDb,
      breath_max_rms_db: breathMaxRmsDb,
      breath_global_offset_db: breathGlobalOffsetDb,
    };
  });

  function handleDetect() {
    onDetectBreaths({
      min_breath_length_ms: minBreathLengthMs,
      min_breath_volume_db: minBreathVolumeDb,
      max_breath_volume_db: maxBreathVolumeDb,
    });
  }

  function handleApply() {
    onApplyVolume(getVolumeParams());
  }
</script>

<aside>
  <div class="param-group">
    <div class="section-title">Breath Detection</div>

    <label for="bd-min-len">
      Min Length
      <span class="unit">{minBreathLengthMs} ms</span>
    </label>
    <input id="bd-min-len" type="range" min="30" max="500" step="10" bind:value={minBreathLengthMs} />

    <label for="bd-min-vol">
      Min Volume
      <span class="unit">{minBreathVolumeDb} dB</span>
    </label>
    <input id="bd-min-vol" type="range" min="-80" max="-10" step="1" bind:value={minBreathVolumeDb} />

    <label for="bd-max-vol">
      Max Volume
      <span class="unit">{maxBreathVolumeDb} dB</span>
    </label>
    <input id="bd-max-vol" type="range" min="-40" max="0" step="1" bind:value={maxBreathVolumeDb} />

    <button class="btn-action" onclick={handleDetect} disabled={!$audioLoaded}>
      Detect Breaths
    </button>
  </div>

  <div class="param-group">
    <div class="section-title">Note Detection</div>

    <button class="btn-action" onclick={onDetectNotes} disabled={!$audioLoaded}>
      Detect Notes
    </button>
  </div>

  <div class="param-group">
    <div class="section-title">Note Volume</div>

    <label for="nv-min-rms">
      Min RMS Floor
      <span class="unit">{noteMinRmsDb} dB</span>
    </label>
    <input id="nv-min-rms" type="range" min="-80" max="0" step="0.5" bind:value={noteMinRmsDb} />

    <label for="nv-max-rms">
      Max RMS Ceiling
      <span class="unit">{noteMaxRmsDb} dB</span>
    </label>
    <input id="nv-max-rms" type="range" min="-80" max="0" step="0.5" bind:value={noteMaxRmsDb} />

    <label for="nv-offset">
      Global Offset
      <span class="unit">{noteGlobalOffsetDb > 0 ? '+' : ''}{noteGlobalOffsetDb} dB</span>
    </label>
    <input id="nv-offset" type="range" min="-20" max="20" step="0.5" bind:value={noteGlobalOffsetDb} />
  </div>

  <div class="param-group">
    <div class="section-title">Breath Volume</div>

    <label for="bv-min-rms">
      Min RMS Floor
      <span class="unit">{breathMinRmsDb} dB</span>
    </label>
    <input id="bv-min-rms" type="range" min="-80" max="0" step="0.5" bind:value={breathMinRmsDb} />

    <label for="bv-max-rms">
      Max RMS Ceiling
      <span class="unit">{breathMaxRmsDb} dB</span>
    </label>
    <input id="bv-max-rms" type="range" min="-80" max="0" step="0.5" bind:value={breathMaxRmsDb} />

    <label for="bv-offset">
      Global Offset
      <span class="unit">{breathGlobalOffsetDb > 0 ? '+' : ''}{breathGlobalOffsetDb} dB</span>
    </label>
    <input id="bv-offset" type="range" min="-20" max="20" step="0.5" bind:value={breathGlobalOffsetDb} />
  </div>

  <div class="param-group">
    <button class="btn-primary" onclick={handleApply} disabled={!$audioLoaded}>
      Apply Volume
    </button>
    <button class="btn-secondary" onclick={onReset} disabled={!$audioLoaded}>
      Reset
    </button>
  </div>
</aside>

<style>
  aside {
    width: var(--panel-w);
    flex-shrink: 0;
    background: var(--bg2);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding: 12px 0;
  }

  .param-group {
    padding: 8px 14px 10px;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .section-title {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }

  label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
    color: var(--text);
    margin-top: 4px;
  }

  .unit {
    color: var(--accent2);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
  }

  input[type="range"] {
    width: 100%;
    accent-color: var(--accent);
    margin-bottom: 2px;
  }

  .btn-action {
    margin-top: 6px;
    padding: 6px 12px;
    background: var(--accent2);
    color: #fff;
    border: none;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
  }
  .btn-action:hover:not(:disabled) { opacity: 0.85; }
  .btn-action:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-primary {
    padding: 7px 12px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
  }
  .btn-primary:hover:not(:disabled) { opacity: 0.85; }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-secondary {
    padding: 6px 12px;
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.75rem;
    cursor: pointer;
    width: 100%;
    margin-top: 4px;
  }
  .btn-secondary:hover:not(:disabled) { color: var(--text); border-color: var(--text-dim); }
  .btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
