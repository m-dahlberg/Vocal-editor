"""
PSOLA Pitch Engine — TD-PSOLA pitch shifting via Praat/Parselmouth.

Uses Parselmouth's Manipulation object with overlap-add resynthesis.
Requires the original Parselmouth F0 data to convert semitone shifts
(from pitch_map) into absolute target frequencies for the PitchTier.
"""

import numpy as np
import parselmouth
from parselmouth.praat import call
import soundfile as sf


def run_psola_pitch_shift(audio_mono, sr, pitch_map, output_path, psola_params=None,
                          original_times=None, original_frequencies=None):
    """
    TD-PSOLA pitch shifting using Praat's Manipulation object.

    Args:
        audio_mono: Mono audio numpy array
        sr: Sample rate
        pitch_map: List of (frame, semitones) pairs — piecewise-linear shift envelope
        output_path: Path to write output WAV
        psola_params: Optional dict with min_pitch, max_pitch, time_step
        original_times: Array of analysis time points (from Parselmouth)
        original_frequencies: Array of F0 values at those times (Hz, NaN for unvoiced)

    Returns:
        (success: bool, message: str)
    """
    try:
        if psola_params is None:
            psola_params = {}

        min_pitch = psola_params.get('min_pitch', 75)
        max_pitch = psola_params.get('max_pitch', 600)
        time_step = psola_params.get('time_step', 0.01)

        # Create Praat Sound object
        sound = parselmouth.Sound(audio_mono, sampling_frequency=sr)
        duration = sound.duration

        # Create Manipulation object (this analyses pitch pulses internally)
        manipulation = call(sound, "To Manipulation", time_step, min_pitch, max_pitch)

        # Extract the existing PitchTier
        pitch_tier = call(manipulation, "Extract pitch tier")

        # Clear all existing pitch points
        call(pitch_tier, "Remove points between...", 0.0, duration)

        # Build interpolator for original F0
        if original_times is None or original_frequencies is None:
            return False, "PSOLA engine requires original Parselmouth F0 data"

        orig_t = np.asarray(original_times, dtype=np.float64)
        orig_f = np.asarray(original_frequencies, dtype=np.float64)

        # Mask out unvoiced frames (NaN, 0, or negative)
        voiced_mask = np.isfinite(orig_f) & (orig_f > 0)

        if not np.any(voiced_mask):
            return False, "No voiced frames found in original F0 data"

        # Build the semitone-shift envelope from the pitch_map.
        # pitch_map is [(frame, semitones), ...] — piecewise-linear.
        # We interpolate it at every original F0 analysis time to get
        # the shift at each frame, preserving the original pitch contour.
        pm_frames = np.array([p[0] for p in pitch_map], dtype=np.float64)
        pm_shifts = np.array([p[1] for p in pitch_map], dtype=np.float64)
        pm_times = pm_frames / sr

        # Interpolate shift at each original analysis time
        shifts_at_orig = np.interp(orig_t, pm_times, pm_shifts)

        # Add a PitchTier point for every voiced original F0 frame,
        # with the semitone shift applied. This preserves vibrato and
        # natural pitch variation.
        points_added = 0
        for i in range(len(orig_t)):
            if not voiced_mask[i]:
                continue

            t = orig_t[i]
            if t < 0 or t > duration:
                continue

            # Apply semitone shift to original F0
            target_hz = orig_f[i] * (2.0 ** (shifts_at_orig[i] / 12.0))

            # Clamp to valid pitch range
            target_hz = max(min_pitch, min(max_pitch, target_hz))

            call(pitch_tier, "Add point...", float(t), float(target_hz))
            points_added += 1

        if points_added == 0:
            # No pitch points — just write original audio
            sf.write(str(output_path), audio_mono, int(sr))
            return True, "OK (no pitch points to apply)"

        print(f"[PSOLA] Added {points_added} pitch tier points")

        # Replace the pitch tier in the manipulation
        call([pitch_tier, manipulation], "Replace pitch tier")

        # Resynthesize using TD-PSOLA (overlap-add)
        resynthesized = call(manipulation, "Get resynthesis (overlap-add)")

        # Extract audio array
        y_out = resynthesized.values[0]

        # Match original audio length
        audio_length = len(audio_mono)
        if len(y_out) > audio_length:
            y_out = y_out[:audio_length]
        elif len(y_out) < audio_length:
            y_out = np.pad(y_out, (0, audio_length - len(y_out)))

        sf.write(str(output_path), y_out.astype(np.float32), int(sr))
        return True, "OK"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"PSOLA processing failed: {e}"
