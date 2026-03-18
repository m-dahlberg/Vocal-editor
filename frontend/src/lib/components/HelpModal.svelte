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
        <li><strong>Upload audio</strong> — Click <strong>Audio</strong> to load a vocal file (WAV, MP3, FLAC, AIFF). Pitch analysis runs automatically.</li>
        <li><strong>Upload MIDI (optional)</strong> — Click <strong>MIDI</strong> to load a reference melody. Clusters will snap toward MIDI notes during auto-correct.</li>
        <li><strong>Upload Reference (optional)</strong> — Load a second vocal take for A/B comparison. Use the Mixer to blend levels.</li>
        <li><strong>Upload Backing (optional)</strong> — Load an instrumental track to play alongside the vocal.</li>
        <li><strong>Review the pitch plot</strong> — The blue line shows detected pitch. Orange boxes are detected note clusters.</li>
        <li><strong>Auto-correct</strong> — Click <strong>Correct</strong> to calculate and apply pitch corrections for all clusters.</li>
        <li><strong>Manual editing</strong> — Drag boxes up/down, adjust ramps and smoothing. With auto-process on, edits are applied immediately.</li>
        <li><strong>Preview</strong> — Press <strong>Space</strong> to play/pause.</li>
        <li><strong>Export</strong> — Download the corrected audio as WAV.</li>
      </ol>

      <hr>

      <h2>Pitch Plot Controls</h2>

      <h3>Selecting Notes</h3>
      <ul>
        <li><strong>Click a box</strong> — Select that cluster.</li>
        <li><strong>Shift + Click</strong> — Add/remove from multi-selection.</li>
        <li><strong>Drag on empty space</strong> — Rubber-band select multiple clusters.</li>
        <li><strong>Click empty space</strong> — Clear selection.</li>
      </ul>

      <h3>Adjusting Pitch</h3>
      <ul>
        <li><strong>Drag a box up/down</strong> — Shift pitch in semitones. Multi-selection moves together.</li>
      </ul>

      <h3>Adjusting Timing</h3>
      <ul>
        <li><strong>Drag left/right edge</strong> — Resize cluster boundaries.</li>
      </ul>

      <h3>Adjusting Ramps</h3>
      <ul>
        <li><strong>Ctrl + Drag edge</strong> — Adjust ramp in/out duration. Ramps control how quickly the pitch correction fades in/out at the edges of a cluster, creating smooth transitions.</li>
      </ul>

      <h3>Adjusting Smoothing</h3>
      <ul>
        <li><strong>Ctrl + Drag body vertically</strong> — Adjust smoothing percentage. Higher smoothing flattens pitch variation within the cluster (removes vibrato/wobble).</li>
      </ul>

      <h3>Drawing New Clusters</h3>
      <ul>
        <li><strong>Alt + Drag</strong> — Draw a new note cluster in empty space.</li>
      </ul>

      <h3>Deleting Clusters</h3>
      <ul>
        <li><strong>Delete / Backspace</strong> — Remove selected cluster(s) and restore original audio.</li>
      </ul>

      <h3>Navigation</h3>
      <ul>
        <li><strong>Scroll</strong> — Zoom time axis (centered on playhead).</li>
        <li><strong>Shift + Scroll</strong> — Zoom frequency axis.</li>
        <li><strong>Ctrl + Shift + Drag</strong> — Pan the view.</li>
      </ul>

      <hr>

      <h2>Time Tab</h2>
      <p>Switch to the <strong>Time</strong> tab to adjust note timing. Drag clusters left/right to shift their position in time, or resize them to stretch/compress. Click <strong>Update Audio</strong> to render timing changes. Both pitch and time edits are combined when rendering.</p>

      <hr>

      <h2>Keyboard Shortcuts</h2>
      <table>
        <thead><tr><th>Key</th><th>Action</th></tr></thead>
        <tbody>
          <tr><td><strong>Space</strong></td><td>Play / Pause</td></tr>
          <tr><td><strong>Delete / Backspace</strong></td><td>Delete selected cluster(s)</td></tr>
        </tbody>
      </table>

      <hr>

      <h2>Parameters Reference</h2>

      <h3>Analysis Parameters</h3>
      <p>These control how the pitch detection and note clustering works. Changes take effect on <strong>Re-analyze</strong>.</p>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Typical Value</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Min freq (Hz)</strong></td>
            <td>Lowest pitch to detect. Set to the lowest note the singer reaches. Too low adds noise; too high misses low notes.</td>
            <td>75 Hz (bass voice: 65, soprano: 150)</td>
          </tr>
          <tr>
            <td><strong>Max freq (Hz)</strong></td>
            <td>Highest pitch to detect. Set above the singer's highest note including falsetto.</td>
            <td>600 Hz (bass: 400, soprano: 1000)</td>
          </tr>
          <tr>
            <td><strong>Time resolution (ms)</strong></td>
            <td>How often pitch is sampled. Lower values give finer detail but take longer to process.</td>
            <td>5 ms</td>
          </tr>
          <tr>
            <td><strong>Freq tolerance (cents)</strong></td>
            <td>How much pitch variation is allowed within a single note cluster. Higher values merge more pitch wobble into one note; lower values split into separate clusters. 100 cents = 1 semitone.</td>
            <td>100 cents (tight: 50, loose: 150)</td>
          </tr>
          <tr>
            <td><strong>Min note duration (ms)</strong></td>
            <td>Shortest cluster allowed. Clusters shorter than this are discarded. Helps filter out pitch detection glitches.</td>
            <td>100 ms (speech: 50, singing: 100-200)</td>
          </tr>
          <tr>
            <td><strong>Max gap to bridge (ms)</strong></td>
            <td>Maximum silence gap between two segments of the same note that will be merged into one cluster. Helps join notes broken by brief consonants or breaths.</td>
            <td>500 ms (short notes: 100, legato: 500)</td>
          </tr>
          <tr>
            <td><strong>Silence threshold (dB)</strong></td>
            <td>Audio quieter than this is treated as silence. Lower values detect quieter passages; higher values ignore more background noise.</td>
            <td>-30 dB (clean recording: -40, noisy: -20)</td>
          </tr>
        </tbody>
      </table>

      <h3>Correction Parameters</h3>
      <p>These control how auto-correction calculates pitch shifts. Changes take effect on <strong>Correct</strong>.</p>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Typical Value</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Transition ramp (ms)</strong></td>
            <td>Default ramp in/out duration for new corrections. Ramps fade the pitch correction in/out at cluster edges to avoid abrupt jumps. Short ramps sound tighter; long ramps sound more natural.</td>
            <td>50 ms (tight: 20, natural: 100)</td>
          </tr>
          <tr>
            <td><strong>Gap threshold (ms)</strong></td>
            <td>Gaps between clusters shorter than this will have their ramps blended together for smooth transitions.</td>
            <td>150 ms</td>
          </tr>
          <tr>
            <td><strong>Correction strength (%)</strong></td>
            <td>How much of the calculated correction to apply. 100% snaps fully to the target note; lower values leave some natural pitch variation. Applies to auto-correct only.</td>
            <td>90% (subtle: 50, hard tune: 100)</td>
          </tr>
          <tr>
            <td><strong>MIDI threshold (cents)</strong></td>
            <td>When MIDI is loaded, clusters within this distance of a MIDI note snap to it instead of the nearest chromatic note. Larger values match more loosely.</td>
            <td>80 cents (strict: 50, loose: 150)</td>
          </tr>
          <tr>
            <td><strong>Auto smooth (%)</strong></td>
            <td>Smoothing applied to all clusters during auto-correct. Smoothing flattens pitch variation (vibrato, wobble) within each cluster. 0% preserves natural vibrato; 100% makes each note completely flat.</td>
            <td>0% (natural), 30-50% (pop), 100% (robotic)</td>
          </tr>
          <tr>
            <td><strong>Smooth threshold (cents)</strong></td>
            <td>Only apply auto-smoothing to clusters with pitch variation exceeding this threshold. Use to selectively smooth only unstable notes while preserving intentional vibrato.</td>
            <td>0 (apply to all), 30-50 (only wobbly notes)</td>
          </tr>
          <tr>
            <td><strong>Smooth threshold (ms)</strong></td>
            <td>Only apply auto-smoothing to clusters longer than this duration. Use to smooth only long, unstable notes while leaving shorter notes with their natural vibrato.</td>
            <td>0 (apply to all), 800-1000 (only long notes)</td>
          </tr>
          <tr>
            <td><strong>Smooth curve</strong></td>
            <td>Controls how aggressively the pitch curve is straightened. Higher values produce more aggressive flattening. 1.0 is linear interpolation toward the target.</td>
            <td>1.0 (gentle), 2.0-3.0 (aggressive)</td>
          </tr>
        </tbody>
      </table>

      <h3>Per-Note Parameters (Selected Note Panel)</h3>
      <p>These are set per cluster (or multi-selection) and override global defaults. Changes apply on mouse release.</p>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Typical Value</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Ramp in / out (ms)</strong></td>
            <td>Fade-in/out duration for this cluster's pitch correction. Short ramps give a tighter, more "auto-tuned" sound. Long ramps give a more gradual, natural transition.</td>
            <td>50 ms (tight: 10-20, natural: 80-150)</td>
          </tr>
          <tr>
            <td><strong>Smoothing (%)</strong></td>
            <td>How much pitch variation within this cluster is flattened. 0% keeps all natural vibrato. Higher values progressively remove wobble.</td>
            <td>0% (natural), 30-60% (controlled), 100% (flat)</td>
          </tr>
        </tbody>
      </table>

      <h3>Segment Processing Parameters (Selected Note Panel)</h3>
      <p>These control how individual note corrections are rendered into the audio.</p>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Typical Value</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Padding (ms)</strong></td>
            <td>Extra audio included before and after the cluster when processing a single segment. More padding gives the pitch engine more context for natural-sounding results but takes longer.</td>
            <td>300 ms</td>
          </tr>
          <tr>
            <td><strong>Crossfade (ms)</strong></td>
            <td>Overlap crossfade when splicing the processed segment back into the full audio. Prevents clicks at the splice boundary.</td>
            <td>10 ms</td>
          </tr>
          <tr>
            <td><strong>Crop (ms)</strong></td>
            <td>Trim this much from the edges of the processed segment before splicing. Helps remove pitch engine artifacts at segment boundaries.</td>
            <td>50 ms</td>
          </tr>
          <tr>
            <td><strong>Neighbors</strong></td>
            <td>Number of neighboring clusters to include when processing a segment. Including neighbors helps the pitch engine produce smoother transitions between notes.</td>
            <td>1 (isolated: 0, smooth: 2-3)</td>
          </tr>
          <tr>
            <td><strong>Auto process</strong></td>
            <td>When enabled, automatically renders audio after each edit (drag, resize, ramp, smoothing change). Disable for faster editing if you want to batch changes.</td>
            <td>On</td>
          </tr>
        </tbody>
      </table>

      <h3>Pitch Engine</h3>
      <p>Choose which algorithm processes pitch corrections. Each has different quality characteristics.</p>
      <table>
        <thead><tr><th>Engine</th><th>Description</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>FD-PSOLA</strong></td>
            <td>Frequency-domain PSOLA. Good quality with formant preservation. Recommended default for most vocals.</td>
          </tr>
          <tr>
            <td><strong>Rubberband</strong></td>
            <td>Industry-standard time-stretching and pitch-shifting library. Very high quality, especially with the R3 engine. Best for large pitch shifts or combined pitch + time edits.</td>
          </tr>
          <tr>
            <td><strong>PSOLA</strong></td>
            <td>Time-domain PSOLA via Praat. Simple and fast. Works well for small corrections but can sound robotic on large shifts.</td>
          </tr>
          <tr>
            <td><strong>SMS</strong></td>
            <td>Spectral Modeling Synthesis. Decomposes audio into harmonics + noise and resynthesizes. Experimental; can produce unique tonal qualities.</td>
          </tr>
        </tbody>
      </table>

      <h3>Rubberband Engine Options</h3>
      <p>Shown when Rubberband is selected as the pitch engine. Also used for time-stretching regardless of pitch engine.</p>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Default</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Command</strong></td>
            <td>Rubberband executable name. Use <code>rubberband-r3</code> for the newer R3 engine (higher quality) or <code>rubberband</code> for the classic engine.</td>
            <td>rubberband-r3</td>
          </tr>
          <tr>
            <td><strong>Crisp level (0-6)</strong></td>
            <td>Transient handling. 0 = smeared transients (smooth), 6 = very crisp transients. Higher values preserve consonant attacks but may introduce artifacts.</td>
            <td>3</td>
          </tr>
          <tr>
            <td><strong>Formant</strong></td>
            <td>Preserve vocal formants when shifting pitch. Without this, large pitch shifts sound like chipmunks (up) or giants (down). Keep enabled for vocals.</td>
            <td>On</td>
          </tr>
          <tr>
            <td><strong>Pitch HQ</strong></td>
            <td>High-quality pitch shifting mode. Slower but reduces artifacts. Recommended for final renders.</td>
            <td>On</td>
          </tr>
          <tr>
            <td><strong>Window long</strong></td>
            <td>Use longer analysis windows. Better frequency resolution for sustained notes, but less precise timing. Good for legato vocals.</td>
            <td>On</td>
          </tr>
          <tr>
            <td><strong>Smoothing</strong></td>
            <td>Smooth pitch transitions in the pitch map. Reduces abrupt pitch changes between adjacent frames.</td>
            <td>On</td>
          </tr>
          <tr>
            <td><strong>Enable pitchmap</strong></td>
            <td>Use frame-by-frame pitch mapping (required for pitch correction). Disable only if using Rubberband purely for time-stretching.</td>
            <td>On</td>
          </tr>
          <tr>
            <td><strong>Enable timemap</strong></td>
            <td>Use sample-accurate time mapping for time edits. Disable if not using time alignment features.</td>
            <td>On</td>
          </tr>
        </tbody>
      </table>

      <h3>FD-PSOLA Engine Options</h3>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Default</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>FFT Size</strong></td>
            <td>Analysis window size. Larger = better frequency resolution but less time precision. 2048 is a good balance for most vocals.</td>
            <td>2048</td>
          </tr>
          <tr>
            <td><strong>Window Type</strong></td>
            <td>Spectral analysis window shape. Kaiser offers good sidelobe suppression; Hanning is smoother; Blackman has narrower main lobe.</td>
            <td>Kaiser</td>
          </tr>
          <tr>
            <td><strong>Formant Preservation</strong></td>
            <td>Preserve vocal character when shifting pitch. Essential for natural-sounding vocals.</td>
            <td>On</td>
          </tr>
          <tr>
            <td><strong>Formant Method</strong></td>
            <td>Algorithm for estimating vocal formants. Cepstral is generally more robust; LPC can be more precise for clean recordings.</td>
            <td>Cepstral</td>
          </tr>
          <tr>
            <td><strong>Envelope Order</strong></td>
            <td>Resolution of the spectral envelope estimate. Higher values capture finer formant detail but may introduce noise. 20-40 is typical for voice.</td>
            <td>30</td>
          </tr>
          <tr>
            <td><strong>Overlap Factor</strong></td>
            <td>Analysis frame overlap. Higher values give smoother output but take longer. 4 is recommended for quality.</td>
            <td>4</td>
          </tr>
          <tr>
            <td><strong>Phase Handling</strong></td>
            <td>How phase is managed between frames. Pitch Synchronous aligns to pitch periods (more natural); Phase Lock preserves inter-channel phase (less smearing).</td>
            <td>Pitch Synchronous</td>
          </tr>
          <tr>
            <td><strong>Min / Max Pitch</strong></td>
            <td>Pitch range for the PSOLA algorithm. Should match or be wider than the Analysis min/max freq settings.</td>
            <td>75 / 600 Hz</td>
          </tr>
        </tbody>
      </table>

      <h3>PSOLA Engine Options</h3>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Default</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Min / Max Pitch</strong></td>
            <td>Pitch detection range for Praat's PSOLA. Should cover the singer's full range.</td>
            <td>75 / 600 Hz</td>
          </tr>
          <tr>
            <td><strong>Time step (s)</strong></td>
            <td>Analysis time step. Smaller values give finer control but take longer.</td>
            <td>0.01 s</td>
          </tr>
        </tbody>
      </table>

      <h3>SMS Engine Options</h3>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Default</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Max harmonics</strong></td>
            <td>Maximum number of harmonic partials to track. More harmonics capture richer timbre but cost more CPU.</td>
            <td>60</td>
          </tr>
          <tr>
            <td><strong>Peak threshold (dB)</strong></td>
            <td>Minimum spectral peak amplitude to be considered a harmonic. Lower values detect quieter harmonics.</td>
            <td>-80 dB</td>
          </tr>
          <tr>
            <td><strong>Stochastic factor</strong></td>
            <td>Amount of noise/breath component in the resynthesis. Higher values add more breathiness.</td>
            <td>0.05</td>
          </tr>
          <tr>
            <td><strong>Hop size</strong></td>
            <td>Analysis hop in samples. Smaller = finer time resolution, slower processing.</td>
            <td>128</td>
          </tr>
          <tr>
            <td><strong>Harmonic deviation slope</strong></td>
            <td>Allowed frequency deviation for harmonic tracking. Higher values are more permissive.</td>
            <td>0.01</td>
          </tr>
          <tr>
            <td><strong>Min sine duration (s)</strong></td>
            <td>Shortest harmonic track to keep. Filters out transient spectral peaks.</td>
            <td>0.02 s</td>
          </tr>
          <tr>
            <td><strong>Synthesis FFT size</strong></td>
            <td>FFT size for resynthesis. Larger values produce smoother output.</td>
            <td>2048</td>
          </tr>
          <tr>
            <td><strong>Residual level</strong></td>
            <td>Mix level of the noise/residual component. 1.0 = full noise, 0.0 = pure harmonics (synthetic sound).</td>
            <td>1.0</td>
          </tr>
          <tr>
            <td><strong>Timbre preservation</strong></td>
            <td>Attempt to preserve timbral characteristics when shifting pitch.</td>
            <td>On</td>
          </tr>
        </tbody>
      </table>

      <h3>Time Alignment Limits (Time Tab)</h3>
      <table>
        <thead><tr><th>Parameter</th><th>Description</th><th>Default</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Note max stretch (%)</strong></td>
            <td>Maximum allowed time-stretch for a note cluster. 200% means a note can be stretched to twice its original length.</td>
            <td>200%</td>
          </tr>
          <tr>
            <td><strong>Note max compress (%)</strong></td>
            <td>Maximum allowed compression for a note. 50% means a note can be shortened to half its length.</td>
            <td>50%</td>
          </tr>
          <tr>
            <td><strong>Gap max stretch (%)</strong></td>
            <td>Maximum time-stretch allowed for gaps between notes.</td>
            <td>300%</td>
          </tr>
          <tr>
            <td><strong>Gap max compress (%)</strong></td>
            <td>Maximum compression for gaps between notes.</td>
            <td>50%</td>
          </tr>
        </tbody>
      </table>

      <h3>Mixer</h3>
      <table>
        <thead><tr><th>Control</th><th>Description</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Main</strong></td>
            <td>Volume of the processed vocal audio.</td>
          </tr>
          <tr>
            <td><strong>Reference</strong></td>
            <td>Volume of the reference vocal (loaded via the Reference button). Useful for A/B comparison.</td>
          </tr>
          <tr>
            <td><strong>Backing</strong></td>
            <td>Volume of the backing/instrumental track. Plays in sync with the vocal for context while editing.</td>
          </tr>
        </tbody>
      </table>

      <h3>Display Toggles</h3>
      <table>
        <thead><tr><th>Toggle</th><th>Description</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>MIDI</strong></td>
            <td>Show/hide MIDI reference notes on the pitch plot (green lines).</td>
          </tr>
          <tr>
            <td><strong>Correction</strong></td>
            <td>Show/hide the correction curve overlay (orange line showing pitch shift in cents over time).</td>
          </tr>
        </tbody>
      </table>

    </div>
  </div>
</div>
{/if}
