<script lang="ts">
  import { params } from '$lib/stores/params';
  import { avgPitchDeviation, timeEdits } from '$lib/stores/appState';

  interface Props {
    onAnalyze: () => void;
    onCorrect: () => void;
    onUpdateAudio: () => void;
    onExport: () => void;
  }

  let { onAnalyze, onCorrect, onUpdateAudio, onExport }: Props = $props();

  const timeEditCount = $derived($timeEdits.length);
</script>

<aside class="param-panel">
  <h2>Parameters</h2>

  <section>
    <h3>Analysis</h3>
    <div class="param-group">
      <label>Min freq (Hz)<input type="number" bind:value={$params.min_frequency}></label>
      <label>Max freq (Hz)<input type="number" bind:value={$params.max_frequency}></label>
      <label>Time resolution (ms)<input type="number" bind:value={$params.time_resolution_ms}></label>
      <label>Freq tolerance (cents)<input type="number" bind:value={$params.frequency_tolerance_cents}></label>
      <label>Min note duration (ms)<input type="number" bind:value={$params.min_note_duration_ms}></label>
      <label>Max gap to bridge (ms)<input type="number" bind:value={$params.max_gap_to_bridge_ms}></label>
      <label>Silence threshold (dB)<input type="number" bind:value={$params.silence_threshold_db}></label>
    </div>
    <div class="param-group" style="margin-top:6px;">
      <label>Avg pitch deviation (cents)<span style="float:right; color:var(--accent2);">{$avgPitchDeviation != null ? $avgPitchDeviation.toFixed(1) : '—'}</span></label>
    </div>
  </section>

  <section>
    <h3>Correction</h3>
    <div class="param-group">
      <label>Transition ramp (ms)<input type="number" bind:value={$params.transition_ramp_ms}></label>
      <label>Gap threshold (ms)<input type="number" bind:value={$params.gap_threshold_ms}></label>
      <label>Correction strength (%)<input type="number" bind:value={$params.correction_strength} min="0" max="100"></label>
      <label>MIDI threshold (cents)<input type="number" bind:value={$params.midi_threshold_cents}></label>
      <label>Auto smooth (%)<input type="number" bind:value={$params.autocorrect_smoothing} min="0" max="100"></label>
      <label>Smooth threshold (cents)<input type="number" bind:value={$params.smoothing_threshold_cents} min="0"></label>
      <label>Smooth threshold (ms)<input type="number" bind:value={$params.smoothing_threshold_ms} min="0"></label>
      <label>Smooth curve<input type="number" bind:value={$params.smooth_curve} min="1.0" step="0.1"></label>
    </div>
  </section>

  <section>
    <h3>Pitch Engine</h3>
    <div class="param-group">
      <label>Engine
        <select bind:value={$params.pitch_engine}>
          <option value="rubberband">Rubberband</option>
          <option value="sms">SMS (Spectral Modeling)</option>
          <option value="psola">PSOLA (Praat)</option>
          <option value="fd_psola">FD-PSOLA (Freq Domain)</option>
        </select>
      </label>
    </div>
  </section>

  {#if $params.pitch_engine === 'rubberband'}
  <section>
    <h3>Rubberband</h3>
    <div class="param-group">
      <label>Command<input type="text" bind:value={$params.rb.command}></label>
      <label>Crisp level (0-6)<input type="number" bind:value={$params.rb.crisp} min="0" max="6"></label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.formant}> Formant
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.pitch_hq}> Pitch HQ
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.window_long}> Window long
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.smoothing}> Smoothing
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.enable_pitchmap}> Enable pitchmap
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.rb.enable_timemap}> Enable timemap
      </label>
    </div>
  </section>
  {:else if $params.pitch_engine === 'psola'}
  <section>
    <h3>PSOLA</h3>
    <div class="param-group">
      <label>Min pitch (Hz)<input type="number" bind:value={$params.psola.min_pitch} min="50" max="300"></label>
      <label>Max pitch (Hz)<input type="number" bind:value={$params.psola.max_pitch} min="200" max="1000"></label>
      <label>Time step (s)<input type="number" bind:value={$params.psola.time_step} min="0.001" max="0.05" step="0.001"></label>
    </div>
  </section>
  {:else if $params.pitch_engine === 'fd_psola'}
  <section>
    <h3>FD-PSOLA</h3>
    <div class="param-group">
      <label>FFT Size
        <select bind:value={$params.fd_psola.fft_size}>
          <option value={1024}>1024</option>
          <option value={2048}>2048</option>
          <option value={4096}>4096</option>
        </select>
      </label>
      <label>Window Type
        <select bind:value={$params.fd_psola.window_type}>
          <option value="hanning">Hanning</option>
          <option value="blackman">Blackman</option>
          <option value="kaiser">Kaiser</option>
        </select>
      </label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.fd_psola.formant_preservation}> Formant Preservation
      </label>
      <label>Formant Method
        <select bind:value={$params.fd_psola.formant_method}>
          <option value="cepstral">Cepstral</option>
          <option value="lpc">LPC</option>
        </select>
      </label>
      <label>Envelope Order<input type="number" bind:value={$params.fd_psola.envelope_order} min="10" max="60"></label>
      <label>Overlap Factor
        <select bind:value={$params.fd_psola.overlap_factor}>
          <option value={2}>2</option>
          <option value={3}>3</option>
          <option value={4}>4</option>
        </select>
      </label>
      <label>Phase Handling
        <select bind:value={$params.fd_psola.phase_mode}>
          <option value="pitch_sync">Pitch Synchronous</option>
          <option value="phase_lock">Phase Lock</option>
        </select>
      </label>
      <label>Min Pitch (Hz)<input type="number" bind:value={$params.fd_psola.min_pitch} min="50" max="200"></label>
      <label>Max Pitch (Hz)<input type="number" bind:value={$params.fd_psola.max_pitch} min="300" max="1000"></label>
    </div>
  </section>
  {:else}
  <section>
    <h3>SMS Analysis</h3>
    <div class="param-group">
      <label>Max harmonics<input type="number" bind:value={$params.sms.max_harmonics} min="10" max="100"></label>
      <label>Peak threshold (dB)<input type="number" bind:value={$params.sms.peak_threshold} min="-120" max="-20"></label>
      <label>Stochastic factor<input type="number" bind:value={$params.sms.stochastic_factor} min="0.05" max="0.5" step="0.05"></label>
      <label>Hop size (samples)<input type="number" bind:value={$params.sms.hop_size} min="64" max="1024" step="64"></label>
      <label>Harmonic deviation slope<input type="number" bind:value={$params.sms.harm_dev_slope} min="0.001" max="0.1" step="0.005"></label>
      <label>Min sine duration (s)<input type="number" bind:value={$params.sms.min_sine_dur} min="0.005" max="0.1" step="0.005"></label>
    </div>
  </section>
  <section>
    <h3>SMS Synthesis</h3>
    <div class="param-group">
      <label>Synthesis FFT size<input type="number" bind:value={$params.sms.synth_fft_size} min="512" max="8192" step="512"></label>
      <label>Residual level<input type="number" bind:value={$params.sms.residual_level} min="0" max="1" step="0.05"></label>
      <label class="checkbox-label">
        <input type="checkbox" bind:checked={$params.sms.timbre_preserve}> Timbre preservation
      </label>
    </div>
  </section>
  {/if}

  {#if timeEditCount > 0}
    <div class="cross-tab-info">+ {timeEditCount} time edit{timeEditCount !== 1 ? 's' : ''} will also be applied</div>
  {/if}

  <div class="action-buttons">
    <button class="btn btn-primary" onclick={onAnalyze}>Re-analyze</button>
    <button class="btn btn-primary" onclick={onCorrect}>Correct</button>
    <button class="btn btn-warning" onclick={onUpdateAudio}>Update Audio</button>
    <button class="btn btn-success" onclick={onExport}>Export</button>
  </div>
</aside>

<style>
  .cross-tab-info {
    padding: 4px 10px;
    margin: 4px 8px;
    font-size: 0.75rem;
    color: var(--accent2, #f0a);
    background: rgba(255, 0, 170, 0.08);
    border-radius: 4px;
    text-align: center;
  }
</style>
