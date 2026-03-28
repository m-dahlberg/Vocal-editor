"""
PSOLA Pitch Engine — TD-PSOLA pitch shifting and time stretching via Praat/Parselmouth.

Uses Parselmouth's Manipulation object with overlap-add resynthesis.
Supports both pitch modification (PitchTier) and time stretching (DurationTier)
in a single resynthesis pass.
"""

import numpy as np
import parselmouth
from parselmouth.praat import call
import soundfile as sf


def _build_manipulation(audio_mono, sr, psola_params, original_times, original_frequencies,
                        pitch_map=None):
    """
    Create a Praat Manipulation object and optionally apply pitch modifications.

    Returns:
        (manipulation, duration, resynthesis_method) or raises on error.
    """
    min_pitch = psola_params.get('min_pitch', 75)
    max_pitch = psola_params.get('max_pitch', 600)
    time_step = psola_params.get('time_step', 0.01)
    resynthesis_method = psola_params.get('resynthesis_method', 'overlap_add')
    pitch_point_step = int(psola_params.get('pitch_point_step', 1))
    pitch_smooth_window_ms = float(psola_params.get('pitch_smooth_window_ms', 0))
    max_shift_semitones = float(psola_params.get('max_shift_semitones', 12))

    sound = parselmouth.Sound(audio_mono, sampling_frequency=sr)
    duration = sound.duration

    manipulation = call(sound, "To Manipulation", time_step, min_pitch, max_pitch)

    if pitch_map is not None:
        orig_t = np.asarray(original_times, dtype=np.float64)
        orig_f = np.asarray(original_frequencies, dtype=np.float64)
        voiced_mask = np.isfinite(orig_f) & (orig_f > 0)

        if not np.any(voiced_mask):
            raise ValueError("No voiced frames found in original F0 data")

        pitch_tier = call(manipulation, "Extract pitch tier")
        call(pitch_tier, "Remove points between...", 0.0, duration)

        pm_frames = np.array([p[0] for p in pitch_map], dtype=np.float64)
        pm_shifts = np.array([p[1] for p in pitch_map], dtype=np.float64)
        pm_times = pm_frames / sr

        shifts_at_orig = np.interp(orig_t, pm_times, pm_shifts)

        if pitch_smooth_window_ms > 0:
            window_frames = int(round(pitch_smooth_window_ms / (time_step * 1000)))
            if window_frames >= 2:
                kernel = np.ones(window_frames) / window_frames
                shifts_at_orig = np.convolve(shifts_at_orig, kernel, mode='same')

        points_added = 0
        for i in range(len(orig_t)):
            if not voiced_mask[i]:
                continue
            if pitch_point_step > 1 and i % pitch_point_step != 0:
                continue

            t = orig_t[i]
            if t < 0 or t > duration:
                continue

            shift_st = np.clip(shifts_at_orig[i], -max_shift_semitones, max_shift_semitones)
            target_hz = orig_f[i] * (2.0 ** (shift_st / 12.0))
            target_hz = max(min_pitch, min(max_pitch, target_hz))

            call(pitch_tier, "Add point...", float(t), float(target_hz))
            points_added += 1

        print(f"[PSOLA] Added {points_added} pitch tier points")
        call([pitch_tier, manipulation], "Replace pitch tier")

    return manipulation, duration, resynthesis_method


def _apply_duration_tier(manipulation, duration, time_map, sr):
    """
    Apply time stretching via Praat's DurationTier on a Manipulation object.

    time_map: list of (source_frame, target_frame) pairs.
    DurationTier uses duration factors: >1 stretches, <1 compresses.

    Places factor points at both edges of each region (with a tiny inset)
    so Praat doesn't interpolate across region boundaries.
    """
    duration_tier = call(manipulation, "Extract duration tier")
    call(duration_tier, "Remove points between...", 0.0, duration)

    # Small inset to avoid placing two points at the exact same time
    EDGE_INSET_S = 0.001

    # Convert frame-pair time map to local duration factors.
    # Each pair of consecutive keypoints defines a region with a stretch ratio.
    print(f"[DURATION_TIER] Converting {len(time_map)} keyframes to duration factors (sr={sr}, duration={duration:.4f}s):")
    point_count = 0
    for i in range(len(time_map) - 1):
        src_start, tgt_start = time_map[i]
        src_end, tgt_end = time_map[i + 1]

        src_dur = (src_end - src_start) / sr
        tgt_dur = (tgt_end - tgt_start) / sr

        if src_dur < 1e-6:
            print(f"  [{i:2d}] SKIP  src_dur={src_dur:.6f}s (too small)")
            continue

        factor = tgt_dur / src_dur
        raw_factor = factor
        factor = max(0.1, min(10.0, factor))

        # Place factor at both edges of the region (inset slightly) for sharp transitions
        left_time = src_start / sr + EDGE_INSET_S
        right_time = src_end / sr - EDGE_INSET_S
        if left_time >= right_time:
            # Region too small for two edge points, use midpoint
            left_time = (src_start + src_end) / 2.0 / sr
            right_time = None

        region_label = "IDENTITY" if abs(factor - 1.0) < 0.001 else "STRETCH"
        if right_time is not None:
            print(f"  [{i:2d}] {region_label:8s}  src=[{src_start/sr:.4f}s..{src_end/sr:.4f}s] ({src_dur:.4f}s)  "
                  f"tgt_dur={tgt_dur:.4f}s  factor={raw_factor:.4f} -> {factor:.4f}  @edges=[{left_time:.4f}s, {right_time:.4f}s]")
        else:
            print(f"  [{i:2d}] {region_label:8s}  src=[{src_start/sr:.4f}s..{src_end/sr:.4f}s] ({src_dur:.4f}s)  "
                  f"tgt_dur={tgt_dur:.4f}s  factor={raw_factor:.4f} -> {factor:.4f}  @midpoint={left_time:.4f}s")

        if 0 < left_time < duration:
            call(duration_tier, "Add point...", float(left_time), float(factor))
            point_count += 1
        if right_time is not None and 0 < right_time < duration:
            call(duration_tier, "Add point...", float(right_time), float(factor))
            point_count += 1

    call([duration_tier, manipulation], "Replace duration tier")
    print(f"[DURATION_TIER] Applied {point_count} duration tier points from {len(time_map) - 1} regions")


def _resynthesize(manipulation, resynthesis_method, audio_mono, sr, output_path):
    """Resynthesize from Manipulation and write to output file."""
    if resynthesis_method == 'lpc':
        resynthesized = call(manipulation, "Get resynthesis (LPC)")
    else:
        resynthesized = call(manipulation, "Get resynthesis (overlap-add)")

    y_out = resynthesized.values[0]

    audio_length = len(audio_mono)
    if len(y_out) > audio_length:
        y_out = y_out[:audio_length]
    elif len(y_out) < audio_length:
        y_out = np.pad(y_out, (0, audio_length - len(y_out)))

    sf.write(str(output_path), y_out.astype(np.float32), int(sr))
    return True, "OK"


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

        if original_times is None or original_frequencies is None:
            return False, "PSOLA engine requires original Parselmouth F0 data"

        manipulation, duration, resynth = _build_manipulation(
            audio_mono, sr, psola_params, original_times, original_frequencies,
            pitch_map=pitch_map,
        )

        return _resynthesize(manipulation, resynth, audio_mono, sr, output_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"PSOLA processing failed: {e}"


def run_psola_time_stretch(audio_mono, sr, time_map, output_path, psola_params=None,
                           original_times=None, original_frequencies=None):
    """
    TD-PSOLA time stretching using Praat's DurationTier.

    Args:
        audio_mono: Mono audio numpy array
        sr: Sample rate
        time_map: List of (source_frame, target_frame) pairs
        output_path: Path to write output WAV
        psola_params: Optional dict with engine parameters
        original_times: Array of analysis time points (from Parselmouth)
        original_frequencies: Array of F0 values at those times (Hz, NaN for unvoiced)

    Returns:
        (success: bool, message: str)
    """
    try:
        if psola_params is None:
            psola_params = {}

        if original_times is None or original_frequencies is None:
            return False, "PSOLA engine requires original Parselmouth F0 data"

        manipulation, duration, resynth = _build_manipulation(
            audio_mono, sr, psola_params, original_times, original_frequencies,
            pitch_map=None,
        )

        _apply_duration_tier(manipulation, duration, time_map, sr)

        return _resynthesize(manipulation, resynth, audio_mono, sr, output_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"PSOLA time stretch failed: {e}"


def run_psola_combined(audio_mono, sr, pitch_map, time_map, output_path, psola_params=None,
                       original_times=None, original_frequencies=None):
    """
    TD-PSOLA combined pitch shifting + time stretching in a single resynthesis pass.

    Uses Praat's Manipulation object with both PitchTier and DurationTier
    applied before resynthesis, ensuring consistent pitch marks and windowing.

    Args:
        audio_mono: Mono audio numpy array
        sr: Sample rate
        pitch_map: List of (frame, semitones) pairs
        time_map: List of (source_frame, target_frame) pairs
        output_path: Path to write output WAV
        psola_params: Optional dict with engine parameters
        original_times: Array of analysis time points (from Parselmouth)
        original_frequencies: Array of F0 values at those times (Hz, NaN for unvoiced)

    Returns:
        (success: bool, message: str)
    """
    try:
        if psola_params is None:
            psola_params = {}

        if original_times is None or original_frequencies is None:
            return False, "PSOLA engine requires original Parselmouth F0 data"

        manipulation, duration, resynth = _build_manipulation(
            audio_mono, sr, psola_params, original_times, original_frequencies,
            pitch_map=pitch_map,
        )

        _apply_duration_tier(manipulation, duration, time_map, sr)

        return _resynthesize(manipulation, resynth, audio_mono, sr, output_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"PSOLA combined processing failed: {e}"
