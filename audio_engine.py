"""
Audio Engine - Pitch analysis, correction, and export logic.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import mido
import numpy as np
import parselmouth
import soundfile as sf
from parselmouth.praat import call

# ============================================
# DEFAULT PARAMETERS
# ============================================

DEFAULT_TIME_RESOLUTION_MS = 20
DEFAULT_MIN_FREQUENCY = 75
DEFAULT_MAX_FREQUENCY = 600
DEFAULT_FREQUENCY_TOLERANCE_CENTS = 100
DEFAULT_MIN_NOTE_DURATION_MS = 100
DEFAULT_MAX_GAP_TO_BRIDGE_MS = 500
DEFAULT_SILENCE_THRESHOLD_DB = -30
DEFAULT_TRANSITION_RAMP_MS = 50
DEFAULT_GAP_THRESHOLD_MS = 150
DEFAULT_CORRECTION_STRENGTH = 90
DEFAULT_MIDI_THRESHOLD_CENTS = 80
DEFAULT_SMOOTHING_PERCENT = 0
DEFAULT_AUTOCORRECT_SMOOTHING = 0
DEFAULT_SMOOTHING_THRESHOLD_CENTS = 0
DEFAULT_SMOOTH_CURVE = 1.0
DEFAULT_RUBBERBAND_COMMAND = "rubberband-r3"
DEFAULT_RUBBERBAND_CRISP = 3
DEFAULT_RUBBERBAND_FORMANT = True
DEFAULT_RUBBERBAND_PITCH_HQ = True
DEFAULT_RUBBERBAND_WINDOW_LONG = True
DEFAULT_RUBBERBAND_SMOOTHING = True
CROSSFADE_MS = 5

# Rubberband's --pitchmap implies realtime mode (-R), which introduces a
# processing lead: per-frame pitch shifts are applied earlier than the
# specified sample frame.  For rapidly varying corrections (vibrato
# smoothing) this causes phase errors that can exaggerate rather than
# reduce pitch variation.  We measure the exact lead for each sample rate
# on first use and compensate by shifting every pitch-map frame forward.
_rubberband_lead_cache = {}  # sr -> lead_samples

# Pitch-map target resolution for smoothed clusters.  The analysis hop
# (DEFAULT_TIME_RESOLUTION_MS) is typically 20 ms which gives only ~10
# points per vibrato cycle at 5 Hz.  Rubberband linearly interpolates
# between entries, so a coarser grid under-corrects at higher smoothing
# percentages.  We upsample the per-frame shifts with cubic
# interpolation to this finer grid so rubberband can follow the curve.
PITCHMAP_HOP_MS = 5


# ============================================
# MUSIC THEORY HELPERS
# ============================================

NOTE_FREQ_MAP = [
    ("C2", 65.41),
    ("C#2", 69.30),
    ("D2", 73.42),
    ("D#2", 77.78),
    ("E2", 82.41),
    ("F2", 87.31),
    ("F#2", 92.50),
    ("G2", 98.00),
    ("G#2", 103.83),
    ("A2", 110.00),
    ("A#2", 116.54),
    ("B2", 123.47),
    ("C3", 130.81),
    ("C#3", 138.59),
    ("D3", 146.83),
    ("D#3", 155.56),
    ("E3", 164.81),
    ("F3", 174.61),
    ("F#3", 185.00),
    ("G3", 196.00),
    ("G#3", 207.65),
    ("A3", 220.00),
    ("A#3", 233.08),
    ("B3", 246.94),
    ("C4", 261.63),
    ("C#4", 277.18),
    ("D4", 293.66),
    ("D#4", 311.13),
    ("E4", 329.63),
    ("F4", 349.23),
    ("F#4", 369.99),
    ("G4", 392.00),
    ("G#4", 415.30),
    ("A4", 440.00),
    ("A#4", 466.16),
    ("B4", 493.88),
    ("C5", 523.25),
    ("C#5", 554.37),
    ("D5", 587.33),
    ("D#5", 622.25),
]


def hz_to_note(frequency):
    if frequency <= 0 or np.isnan(frequency):
        return None
    A4 = 440.0
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    semitones_from_a4 = 12 * np.log2(frequency / A4)
    note_number = int(round(semitones_from_a4)) + 9
    octave = 4 + (note_number // 12)
    note_index = note_number % 12
    return f"{note_names[note_index]}{octave}"


def hz_to_cents(frequency, reference_frequency):
    if frequency <= 0 or reference_frequency <= 0:
        return None
    return 1200 * np.log2(frequency / reference_frequency)


def note_to_hz(note_name):
    if note_name is None:
        return None
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    if "#" in note_name:
        note = note_name[:2]
        try:
            octave = int(note_name[2:])
        except (ValueError, IndexError):
            return None
    else:
        note = note_name[0]
        try:
            octave = int(note_name[1:])
        except (ValueError, IndexError):
            return None
    if note not in note_names:
        return None
    note_index = note_names.index(note)
    semitones_from_a4 = (octave - 4) * 12 + note_index - 9
    return 440.0 * (2 ** (semitones_from_a4 / 12))


# ============================================
# MIDI PARSING
# ============================================


def parse_midi_file(midi_path):
    try:
        midi = mido.MidiFile(midi_path)
    except Exception as e:
        return [], str(e)

    ticks_per_beat = midi.ticks_per_beat
    tempo = 500000
    notes = []
    active_notes = {}
    current_time = 0.0

    for track in midi.tracks:
        current_time = 0.0
        for msg in track:
            if msg.time > 0:
                tick_duration = tempo / ticks_per_beat / 1000000.0
                current_time += msg.time * tick_duration
            if msg.type == "set_tempo":
                tempo = msg.tempo
            elif msg.type == "note_on" and msg.velocity > 0:
                active_notes[msg.note] = current_time
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                if msg.note in active_notes:
                    frequency = 440.0 * (2 ** ((msg.note - 69) / 12.0))
                    notes.append(
                        {
                            "start_time": active_notes[msg.note],
                            "end_time": current_time,
                            "note_number": msg.note,
                            "frequency": frequency,
                            "note_name": hz_to_note(frequency),
                        }
                    )
                    del active_notes[msg.note]

    return notes, f"Loaded {len(notes)} MIDI notes"


# ============================================
# PITCH ANALYSIS
# ============================================


def analyze_pitch(audio_path, params):
    sound = parselmouth.Sound(audio_path)
    time_step = params.get("time_resolution_ms", DEFAULT_TIME_RESOLUTION_MS) / 1000.0
    min_freq = params.get("min_frequency", DEFAULT_MIN_FREQUENCY)
    max_freq = params.get("max_frequency", DEFAULT_MAX_FREQUENCY)

    pitch = call(sound, "To Pitch", time_step, min_freq, max_freq)
    time_values = pitch.xs()

    frequencies = []
    for t in time_values:
        f0 = call(pitch, "Get value at time", t, "Hertz", "Linear")
        frequencies.append(
            f0 if (f0 is not None and not np.isnan(f0) and f0 > 0) else np.nan
        )

    frequencies = np.array(frequencies)
    times = np.array(time_values)
    notes = [hz_to_note(f) if not np.isnan(f) else None for f in frequencies]

    audio_array = sound.values
    if len(audio_array.shape) > 1:
        audio_array = audio_array.T

    return times, frequencies, notes, float(sound.sampling_frequency), audio_array


def detect_silence_in_gap(audio, sr, start_time, end_time, silence_db=-30):
    start_s = int(start_time * sr)
    end_s = int(end_time * sr)
    segment = audio[start_s:end_s]
    if len(segment) == 0:
        return False
    if len(segment.shape) > 1:
        segment = segment.mean(axis=1)
    rms = np.sqrt(np.mean(segment**2))
    if rms == 0:
        return True
    return 20 * np.log10(rms + 1e-10) < silence_db


def cluster_notes(times, frequencies, notes, audio, sr, params):
    freq_tolerance = params.get(
        "frequency_tolerance_cents", DEFAULT_FREQUENCY_TOLERANCE_CENTS
    )
    min_duration = params.get("min_note_duration_ms", DEFAULT_MIN_NOTE_DURATION_MS)
    max_gap = params.get("max_gap_to_bridge_ms", DEFAULT_MAX_GAP_TO_BRIDGE_MS)
    silence_db = params.get("silence_threshold_db", DEFAULT_SILENCE_THRESHOLD_DB)
    transition_ramp = params.get("transition_ramp_ms", DEFAULT_TRANSITION_RAMP_MS)
    correction_strength = params.get("correction_strength", DEFAULT_CORRECTION_STRENGTH)

    # Assign notes to semitone buckets
    assigned = []
    for f in frequencies:
        if np.isnan(f) or f <= 0:
            assigned.append(None)
            continue
        best, best_dev = None, float("inf")
        for name, base in NOTE_FREQ_MAP:
            dev = abs(hz_to_cents(f, base))
            if dev <= freq_tolerance and dev < best_dev:
                best, best_dev = name, dev
        assigned.append(best)

    # First pass: build clusters with wobble detection
    clusters = []
    current = None
    WOBBLE_MS = 150

    for i, (t, f, note) in enumerate(zip(times, frequencies, assigned)):
        if note is None:
            if current:
                clusters.append(current)
                current = None
            continue
        if current is None:
            current = {
                "note": note,
                "start_time": t,
                "end_time": t,
                "frequencies": [f],
                "times": [t],
                "primary_note": note,
            }
        elif current["note"] == note:
            current["end_time"] = t
            current["frequencies"].append(f)
            current["times"].append(t)
        else:
            # Check for wobble
            returns = False
            look = 0
            for j in range(i, min(i + 10, len(assigned))):
                if assigned[j] == current["primary_note"]:
                    returns = True
                    look = j - i
                    break
                elif assigned[j] is not None and assigned[j] != note:
                    break
            if returns and look > 0:
                wobble_ms = (times[min(i + look, len(times) - 1)] - t) * 1000
                if wobble_ms < WOBBLE_MS:
                    current["end_time"] = t
                    current["frequencies"].append(f)
                    current["times"].append(t)
                    continue
            clusters.append(current)
            current = {
                "note": note,
                "start_time": t,
                "end_time": t,
                "frequencies": [f],
                "times": [t],
                "primary_note": note,
            }

    if current:
        clusters.append(current)

    # Second pass: merge adjacent same-note clusters
    merged = []
    i = 0
    while i < len(clusters):
        cur = clusters[i]
        while i + 1 < len(clusters):
            nxt = clusters[i + 1]
            if cur["note"] != nxt["note"]:
                break
            gap_ms = (nxt["start_time"] - cur["end_time"]) * 1000
            if gap_ms > max_gap:
                break
            if detect_silence_in_gap(
                audio, sr, cur["end_time"], nxt["start_time"], silence_db
            ):
                break
            cur["end_time"] = nxt["end_time"]
            cur["frequencies"].extend(nxt["frequencies"])
            cur["times"].extend(nxt["times"])
            i += 1
        merged.append(cur)
        i += 1

    # Filter and finalize
    result = []
    for idx, c in enumerate(merged):
        dur_ms = (c["end_time"] - c["start_time"]) * 1000
        if dur_ms >= min_duration:
            c["id"] = idx
            c["mean_freq"] = float(np.mean(c["frequencies"]))
            c["duration_ms"] = dur_ms
            c["pitch_shift_semitones"] = 0.0
            c["ramp_in_ms"] = transition_ramp
            c["ramp_out_ms"] = transition_ramp
            c["correction_strength"] = correction_strength
            c["smoothing_percent"] = DEFAULT_SMOOTHING_PERCENT
            c["manually_edited"] = False
            c["pitch_variation_cents"] = compute_cluster_pitch_variation(c)
            result.append(c)

    return result


def compute_cluster_pitch_variation(cluster):
    """Average absolute cents deviation of each pitch frame from the cluster mean_freq."""
    freqs = cluster.get("frequencies", [])
    mean_freq = cluster.get("mean_freq", 0)
    if not freqs or mean_freq <= 0:
        return 0.0
    deviations = []
    for f in freqs:
        if f is not None and not np.isnan(f) and f > 0:
            deviations.append(abs(1200 * np.log2(f / mean_freq)))
    return float(np.mean(deviations)) if deviations else 0.0


def compute_avg_pitch_deviation(clusters, midi_notes, params):
    """Average absolute cents deviation of each cluster from its best-matching MIDI note."""
    midi_threshold = params.get("midi_threshold_cents", DEFAULT_MIDI_THRESHOLD_CENTS)
    deviations = []
    for cluster in clusters:
        cluster_freq = cluster["mean_freq"]
        best_midi = None
        max_overlap = 0.0
        for midi_note in midi_notes:
            overlap = max(
                0,
                min(cluster["end_time"], midi_note["end_time"])
                - max(cluster["start_time"], midi_note["start_time"]),
            )
            if overlap > max_overlap:
                max_overlap = overlap
                best_midi = midi_note
        if best_midi is None or max_overlap == 0:
            continue
        cents_off = abs(hz_to_cents(cluster_freq, best_midi["frequency"]))
        if cents_off is not None:
            deviations.append(cents_off)
    return float(np.mean(deviations)) if deviations else 0.0


# ============================================
# PITCH CORRECTION
# ============================================


def autocorrect_midi(clusters, midi_notes, params):
    midi_threshold = params.get("midi_threshold_cents", DEFAULT_MIDI_THRESHOLD_CENTS)
    transition_ramp = params.get("transition_ramp_ms", DEFAULT_TRANSITION_RAMP_MS)
    correction_strength = params.get("correction_strength", DEFAULT_CORRECTION_STRENGTH)
    autocorrect_smoothing = params.get("autocorrect_smoothing", DEFAULT_AUTOCORRECT_SMOOTHING)
    smoothing_threshold = params.get("smoothing_threshold_cents", DEFAULT_SMOOTHING_THRESHOLD_CENTS)

    for cluster in clusters:
        if cluster.get("manually_edited"):
            continue

        cluster_freq = cluster["mean_freq"]
        cluster_note = cluster["note"]

        # Find best overlapping MIDI note
        best_midi = None
        max_overlap = 0.0
        for midi_note in midi_notes:
            overlap = max(
                0,
                min(cluster["end_time"], midi_note["end_time"])
                - max(cluster["start_time"], midi_note["start_time"]),
            )
            if overlap > max_overlap:
                max_overlap = overlap
                best_midi = midi_note

        # Determine target note
        if best_midi is None or max_overlap == 0:
            target_note = cluster_note
        elif best_midi["note_name"] == cluster_note:
            target_note = cluster_note
        else:
            cents_from_midi = abs(hz_to_cents(cluster_freq, best_midi["frequency"]))
            target_note = (
                best_midi["note_name"]
                if cents_from_midi <= midi_threshold
                else cluster_note
            )

        ideal_freq = note_to_hz(target_note)
        if ideal_freq is None:
            continue

        cents_off = hz_to_cents(cluster_freq, ideal_freq)
        strength = cluster.get("correction_strength", correction_strength) / 100.0
        cluster["pitch_shift_semitones"] = (-cents_off / 100.0) * strength
        cluster["ramp_in_ms"] = transition_ramp
        cluster["ramp_out_ms"] = transition_ramp

        # Apply smoothing if cluster pitch variation exceeds threshold
        variation = cluster.get("pitch_variation_cents", 0)
        if autocorrect_smoothing > 0 and variation >= smoothing_threshold:
            cluster["smoothing_percent"] = autocorrect_smoothing

    return clusters


def autocorrect_standard(clusters, params):
    transition_ramp = params.get("transition_ramp_ms", DEFAULT_TRANSITION_RAMP_MS)
    correction_strength = params.get("correction_strength", DEFAULT_CORRECTION_STRENGTH)
    autocorrect_smoothing = params.get("autocorrect_smoothing", DEFAULT_AUTOCORRECT_SMOOTHING)
    smoothing_threshold = params.get("smoothing_threshold_cents", DEFAULT_SMOOTHING_THRESHOLD_CENTS)

    for cluster in clusters:
        if cluster.get("manually_edited"):
            continue
        ideal_freq = note_to_hz(cluster["note"])
        if ideal_freq is None:
            continue
        cents_off = hz_to_cents(cluster["mean_freq"], ideal_freq)
        strength = cluster.get("correction_strength", correction_strength) / 100.0
        cluster["pitch_shift_semitones"] = (-cents_off / 100.0) * strength
        cluster["ramp_in_ms"] = transition_ramp
        cluster["ramp_out_ms"] = transition_ramp

        # Apply smoothing if cluster pitch variation exceeds threshold
        variation = cluster.get("pitch_variation_cents", 0)
        if autocorrect_smoothing > 0 and variation >= smoothing_threshold:
            cluster["smoothing_percent"] = autocorrect_smoothing

    return clusters


# ============================================
# PITCH MAP GENERATION
# ============================================


def _compute_smoothed_frames(cluster, sr, smooth_curve=1.0):
    """
    Compute per-frame (frame, total_shift_semitones) pairs for a cluster with smoothing.
    The total shift at each frame is pitch_shift_semitones + smoothing_shift, where
    smoothing_shift pulls the frame deviation from mean_freq toward zero.

    smooth_curve controls how smoothing is distributed across deviations:
      1.0 = linear (uniform reduction),
      >1  = power curve (outliers corrected more, near-center points left alone).
    Formula: smoothed = sign(d) * (|d|/max_dev)^(1/curve) * max_dev * (1-smoothing)

    NaN frames are interpolated between neighbouring voiced frames.
    Returns list of (frame, shift) tuples.
    """
    times = cluster.get("times", [])
    freqs = cluster.get("frequencies", [])
    if not times or not freqs:
        print(f"[DEBUG] _compute_smoothed_frames: no times/freqs, returning []")
        return []

    # Filter to only frames within cluster boundaries
    filtered = [
        (t, f)
        for t, f in zip(times, freqs)
        if cluster["start_time"] <= t <= cluster["end_time"]
    ]
    if not filtered:
        print(
            f"[DEBUG] _compute_smoothed_frames: no frames within cluster boundaries, returning []"
        )
        return []
    times, freqs = zip(*filtered)

    base_shift = cluster["pitch_shift_semitones"]
    mean_freq = cluster["mean_freq"]
    smoothing = cluster.get("smoothing_percent", 0) / 100.0
    print(
        f"[DEBUG] _compute_smoothed_frames: note={cluster.get('note')} smoothing={smoothing:.2f} "
        f"smooth_curve={smooth_curve:.2f} base_shift={base_shift:.3f} frames={len(times)}"
    )

    # Pre-compute max deviation for power curve normalization
    max_dev = 0.0
    if smooth_curve > 1.0:
        for f in freqs:
            if f is not None and not (isinstance(f, float) and np.isnan(f)) and f > 0:
                dev = abs(12.0 * np.log2(f / mean_freq))
                if dev > max_dev:
                    max_dev = dev
        if max_dev == 0:
            max_dev = 1.0  # avoid division by zero

    raw = []
    for t, f in zip(times, freqs):
        frame = int(t * sr)
        if f is None or (isinstance(f, float) and np.isnan(f)) or f <= 0:
            raw.append((frame, None))
        else:
            deviation_semitones = 12.0 * np.log2(f / mean_freq)

            if smooth_curve <= 1.0 or max_dev == 0:
                # Linear smoothing (original behavior)
                smoothed_deviation = deviation_semitones * (1.0 - smoothing)
            else:
                # Power curve: remaining = sign(d) * (|d|/max)^(1/curve) * max * (1-smoothing)
                abs_dev = abs(deviation_semitones)
                norm = abs_dev / max_dev
                curved_norm = norm ** (1.0 / smooth_curve)
                smoothed_deviation = np.sign(deviation_semitones) * curved_norm * max_dev * (1.0 - smoothing)

            frame_shift = (smoothed_deviation - deviation_semitones) + base_shift
            raw.append((frame, frame_shift))

    if not raw:
        return []

    result = list(raw)
    n = len(result)

    # Find first and last known values
    first_known = next((i for i, (_, v) in enumerate(result) if v is not None), None)
    if first_known is None:
        return [(f, base_shift) for f, _ in raw]
    last_known = next(
        (i for i, (_, v) in enumerate(reversed(result)) if v is not None), None
    )
    last_known = n - 1 - last_known

    # Forward fill leading Nones
    for i in range(first_known):
        result[i] = (result[i][0], result[first_known][1])

    # Backward fill trailing Nones
    for i in range(last_known + 1, n):
        result[i] = (result[i][0], result[last_known][1])

    # Linear interpolation for interior Nones
    i = 0
    while i < n:
        if result[i][1] is None:
            j = i + 1
            while j < n and result[j][1] is None:
                j += 1
            if j < n:
                f0, v0 = result[i - 1]
                f1, v1 = result[j]
                for k in range(i, j):
                    fk = result[k][0]
                    t_interp = (fk - f0) / (f1 - f0) if f1 != f0 else 0.0
                    result[k] = (fk, v0 + (v1 - v0) * t_interp)
            i = j
        else:
            i += 1

    return result


def generate_pitch_map_from_frames(
    original_times, original_freqs, corrected_freqs, sr, audio_length
):
    """
    Build a pitch map directly from per-frame original and corrected frequencies.
    shift = log2(corrected / original) in semitones, exactly matching the client visualization.
    Frames where either frequency is invalid are skipped (rubberband interpolates between them).
    """
    pitch_map = [(0, 0.0)]

    for t, orig_f, corr_f in zip(original_times, original_freqs, corrected_freqs):
        if orig_f is None or corr_f is None:
            continue
        if np.isnan(orig_f) or np.isnan(corr_f):
            continue
        if orig_f <= 0 or corr_f <= 0:
            continue
        frame = int(t * sr)
        shift = 12.0 * np.log2(corr_f / orig_f)
        pitch_map.append((frame, shift))

    pitch_map.append((audio_length - 1, 0.0))
    return sorted(pitch_map, key=lambda x: x[0])


def generate_pitch_map(clusters, sr, audio_length, gap_threshold_ms=None, smooth_curve=1.0):
    if gap_threshold_ms is None:
        gap_threshold_ms = DEFAULT_GAP_THRESHOLD_MS

    pitch_map = [(0, 0.0)]
    total_frames = audio_length

    # Include clusters with non-zero shift OR non-zero smoothing
    corrected = [
        (i, c)
        for i, c in enumerate(clusters)
        if c["pitch_shift_semitones"] != 0 or c.get("smoothing_percent", 0) != 0
    ]
    if not corrected:
        pitch_map.append((total_frames - 1, 0.0))
        return sorted(pitch_map, key=lambda x: x[0])

    # Build sorted list of (start_frame, end_frame) for ALL clusters,
    # so ramps can be clamped to avoid overlapping any cluster.
    all_cluster_frames = sorted(
        (int(c["start_time"] * sr), int(c["end_time"] * sr))
        for c in clusters
    )

    for idx, (orig_idx, cluster) in enumerate(corrected):
        start_frame = int(cluster["start_time"] * sr)
        end_frame = int(cluster["end_time"] * sr)
        base_shift = cluster["pitch_shift_semitones"]
        smoothing = cluster.get("smoothing_percent", 0)
        ramp_in_frames = int((cluster.get("ramp_in_ms", DEFAULT_TRANSITION_RAMP_MS) / 1000.0) * sr)
        ramp_out_frames = int((cluster.get("ramp_out_ms", DEFAULT_TRANSITION_RAMP_MS) / 1000.0) * sr)

        prev_corr = corrected[idx - 1][1] if idx > 0 else None
        nxt_corr = corrected[idx + 1][1] if idx < len(corrected) - 1 else None

        # Find the nearest cluster (any, including uncorrected) before/after this one.
        # Ramps must not extend into any cluster's time range.
        nearest_end_before = 0  # latest end_frame of any cluster ending before this one starts
        for cs, ce in all_cluster_frames:
            if ce <= start_frame and ce > nearest_end_before:
                nearest_end_before = ce
        nearest_start_after = total_frames  # earliest start_frame of any cluster starting after this one ends
        for cs, ce in all_cluster_frames:
            if cs >= end_frame and cs < nearest_start_after:
                nearest_start_after = cs

        # Available space for ramps (frames between this cluster and nearest neighbor)
        space_before = start_frame - nearest_end_before
        space_after = nearest_start_after - end_frame

        # Clamp ramp to available space (never overlap another cluster)
        eff_ramp_in = min(ramp_in_frames, space_before)
        eff_ramp_out = min(ramp_out_frames, space_after)

        # Check if gap to prev/next corrected cluster is too small for full ramps
        # (direct transition between two corrected clusters)
        gap_prev_frames = (start_frame - int(prev_corr["end_time"] * sr)) if prev_corr else float("inf")
        gap_next_frames = (int(nxt_corr["start_time"] * sr) - end_frame) if nxt_corr else float("inf")

        gap_overlaps_prev = False
        intrusion_in = 0   # frames to eat into start of this cluster
        if prev_corr is not None:
            prev_ramp_out = int((prev_corr.get("ramp_out_ms", DEFAULT_TRANSITION_RAMP_MS) / 1000.0) * sr)
            desired_transition = prev_ramp_out + ramp_in_frames
            if gap_prev_frames <= 0:
                eff_ramp_in = 0
                gap_overlaps_prev = True
            elif gap_prev_frames < desired_transition:
                gap_overlaps_prev = True
                eff_ramp_in = 0
                # Maintain full transition time by eating into clusters
                shortfall = desired_transition - gap_prev_frames
                cluster_half = (end_frame - start_frame) // 2
                intrusion_in = min(shortfall // 2, cluster_half)

        gap_overlaps_next = False
        intrusion_out = 0  # frames to eat into end of this cluster
        if nxt_corr is not None:
            nxt_ramp_in = int((nxt_corr.get("ramp_in_ms", DEFAULT_TRANSITION_RAMP_MS) / 1000.0) * sr)
            desired_transition = ramp_out_frames + nxt_ramp_in
            if gap_next_frames <= 0:
                eff_ramp_out = 0
                gap_overlaps_next = True
            elif gap_next_frames < desired_transition:
                gap_overlaps_next = True
                eff_ramp_out = 0
                # Maintain full transition time by eating into clusters
                shortfall = desired_transition - gap_next_frames
                cluster_half = (end_frame - start_frame) // 2
                intrusion_out = min(shortfall // 2, cluster_half)

        if smoothing > 0:
            frames = _compute_smoothed_frames(cluster, sr, smooth_curve)
            # Upsample to finer grid so rubberband's linear interpolation
            # can accurately follow the correction curve.
            if len(frames) >= 2:
                src_frames = np.array([f for f, _ in frames], dtype=float)
                src_shifts = np.array([s for _, s in frames], dtype=float)
                fine_hop = int(PITCHMAP_HOP_MS / 1000.0 * sr)
                fine_frames = np.arange(
                    int(src_frames[0]), int(src_frames[-1]) + 1, fine_hop
                )
                fine_shifts = np.interp(fine_frames, src_frames, src_shifts)
                frames = list(zip(fine_frames.astype(int), fine_shifts))
            print(
                f"[DEBUG] generate_pitch_map: note={cluster.get('note')} smoothing={smoothing} "
                f"frames={len(frames)}"
            )
        else:
            frames = []
            print(
                f"[DEBUG] generate_pitch_map: note={cluster.get('note')} smoothing=0 — flat hold"
            )

        # Ramp zones are entirely outside the cluster (for non-overlap case)
        ramp_in_start = max(0, start_frame - eff_ramp_in)
        ramp_out_end = min(total_frames - 1, end_frame + eff_ramp_out)

        # Adjusted cluster boundaries when intrusions eat into the cluster
        adjusted_start = start_frame + intrusion_in
        adjusted_end = end_frame - intrusion_out

        # Ramp in: ramp up to base_shift at cluster start.
        # When overlap with intrusion: transition extends into this cluster,
        # so the flat hold starts at adjusted_start.
        # When overlap without intrusion (gap<=0): direct interpolation.
        # When no overlap: ramp from 0 before cluster.
        if not gap_overlaps_prev:
            if eff_ramp_in > 0:
                pitch_map.append((ramp_in_start, 0.0))
            elif prev_corr is None:
                pitch_map.append((max(0, start_frame - 1), 0.0))
            pitch_map.append((start_frame, base_shift))
        else:
            # Overlap: transition ends at adjusted_start (inside cluster)
            pitch_map.append((adjusted_start, base_shift))

        # Interior: per-frame smoothing points, or flat hold
        if smoothing > 0 and frames:
            for frame, shift in frames:
                if frame >= adjusted_start and frame <= adjusted_end:
                    pitch_map.append((frame, shift))
        else:
            pitch_map.append((adjusted_start, base_shift))
            pitch_map.append((adjusted_end, base_shift))

        # Ramp out: from base_shift at cluster end.
        # When overlap with intrusion: transition starts inside this cluster
        # at adjusted_end. When no overlap: ramp to 0 after cluster.
        if not gap_overlaps_next:
            pitch_map.append((end_frame, base_shift))
            if eff_ramp_out > 0:
                pitch_map.append((ramp_out_end, 0.0))
            elif nxt_corr is None:
                pitch_map.append((min(total_frames - 1, end_frame + 1), 0.0))
        else:
            # Overlap: transition starts at adjusted_end (inside cluster)
            pitch_map.append((adjusted_end, base_shift))

    pitch_map.append((total_frames - 1, 0.0))
    return sorted(pitch_map, key=lambda x: x[0])


# ============================================
# RUBBERBAND PROCESSING
# ============================================


def get_audio_mono(audio):
    if len(audio.shape) == 1:
        return audio
    elif audio.shape[0] == 1:
        return audio[0]
    elif audio.shape[1] == 1:
        return audio[:, 0]
    elif audio.shape[0] < audio.shape[1]:
        return audio.mean(axis=0)
    else:
        return audio.mean(axis=1)


def _build_rubberband_cmd(rb_params):
    """Build the rubberband command list (without pitchmap/input/output args)."""
    if rb_params is None:
        rb_params = {}
    command = rb_params.get("command", DEFAULT_RUBBERBAND_COMMAND)
    cmd = [command]
    if rb_params.get("formant", DEFAULT_RUBBERBAND_FORMANT):
        cmd.append("--formant")
    cmd.extend(["--crisp", str(rb_params.get("crisp", DEFAULT_RUBBERBAND_CRISP))])
    if rb_params.get("pitch_hq", DEFAULT_RUBBERBAND_PITCH_HQ):
        cmd.append("--pitch-hq")
    if rb_params.get("window_long", DEFAULT_RUBBERBAND_WINDOW_LONG):
        cmd.append("--window-long")
    if rb_params.get("smoothing", DEFAULT_RUBBERBAND_SMOOTHING):
        cmd.append("--smoothing")
    return cmd


def _measure_rubberband_lead(sr, rb_params=None):
    """
    Measure the exact RT-mode processing lead for a given sample rate by
    running rubberband on a short test signal with a sharp step in the
    pitch map and detecting where the step actually lands in the output.
    The result is cached per sample rate.
    """
    if sr in _rubberband_lead_cache:
        return _rubberband_lead_cache[sr]

    sr = int(sr)
    duration_s = 0.5
    n_samples = int(duration_s * sr)
    step_frame = n_samples // 2  # step at midpoint
    shift_st = 3.0

    # Synthesise a pure tone
    t = np.arange(n_samples) / sr
    audio = (0.5 * np.sin(2 * np.pi * 247.0 * t)).astype(np.float32)

    work_dir = os.path.join(tempfile.gettempdir(), "vocal_editor")
    os.makedirs(work_dir, exist_ok=True)
    in_path = os.path.join(work_dir, "lead_test_in.wav")
    out_path = os.path.join(work_dir, "lead_test_out.wav")
    pm_path = os.path.join(work_dir, "lead_test_pm.txt")

    sf.write(in_path, audio, sr)
    with open(pm_path, "w") as f:
        f.write(f"0 0.0\n")
        f.write(f"{step_frame - 1} 0.0\n")
        f.write(f"{step_frame} {shift_st}\n")
        f.write(f"{n_samples - 1} {shift_st}\n")

    cmd = _build_rubberband_cmd(rb_params)
    cmd.extend(["--pitchmap", pm_path, in_path, out_path])
    subprocess.run(cmd, capture_output=True, text=True)

    # Detect where the step actually occurs in the output via Parselmouth
    snd = parselmouth.Sound(out_path)
    pitch = snd.to_pitch(time_step=0.001, pitch_floor=75, pitch_ceiling=600)
    half_target = 247.0 * 2 ** (shift_st / 2 / 12)  # 50 % of step
    step_time = step_frame / sr

    lead_samples = 0
    for probe in np.arange(step_time * 0.5, step_time * 1.2, 0.001):
        f_val = pitch.get_value_at_time(probe)
        if f_val and f_val > half_target:
            lead_samples = int((step_time - probe) * sr)
            break

    # Clean up
    for p in (in_path, out_path, pm_path):
        if os.path.exists(p):
            os.remove(p)

    lead_samples = max(lead_samples, 0)
    _rubberband_lead_cache[sr] = lead_samples
    print(
        f"[INFO] Measured rubberband RT lead for sr={sr}: "
        f"{lead_samples} samples ({lead_samples / sr * 1000:.1f} ms)"
    )
    return lead_samples


def run_rubberband(audio_mono, sr, pitch_map, output_path, rb_params=None):
    if rb_params is None:
        rb_params = {}

    pitch_map_file = os.path.join(
        tempfile.gettempdir(), "vocal_editor", "last_pitch_map.txt"
    )
    os.makedirs(os.path.dirname(pitch_map_file), exist_ok=True)

    # Compensate for rubberband RT-mode processing lead: shift every
    # pitch-map frame forward so the corrections land at the right time.
    lead_samples = _measure_rubberband_lead(sr, rb_params)
    compensated = [(frame + lead_samples, s) for frame, s in pitch_map]
    # Ensure the file still starts at frame 0 with no shift.
    compensated = [(0, 0.0)] + compensated

    with open(pitch_map_file, "w") as f:
        for frame, semitones in compensated:
            f.write(f"{frame} {semitones}\n")

    print(f"[DEBUG] pitch_map saved to: {pitch_map_file}")
    print(f"[DEBUG] pitch_map ({len(pitch_map)} entries, lead={lead_samples} samples):")
    for frame, semitones in pitch_map[:20]:
        print(f"  {frame} {semitones:.6f}")
    if len(pitch_map) > 20:
        print(f"  ... ({len(pitch_map) - 20} more entries)")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_input = f.name

    sf.write(temp_input, audio_mono, int(sr))

    try:
        cmd = _build_rubberband_cmd(rb_params)
        cmd.extend(["--pitchmap", pitch_map_file, temp_input, str(output_path)])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr

        return True, "OK"

    finally:
        for f in [temp_input]:
            if os.path.exists(f):
                os.remove(f)


def process_full_audio(audio, sr, clusters, params, output_path):
    """Process entire audio file with all corrections.

    The pitch map is always computed server-side from the cluster parameters
    and the original analysis frequencies stored in each cluster.  This avoids
    precision loss from client round-trips and keeps the server as the single
    source of truth.
    """
    audio_mono = get_audio_mono(audio)
    audio_length = len(audio_mono)

    gap_threshold = params.get("gap_threshold_ms", DEFAULT_GAP_THRESHOLD_MS)
    smooth_curve = params.get("smooth_curve", DEFAULT_SMOOTH_CURVE)
    pitch_map = generate_pitch_map(clusters, sr, audio_length, gap_threshold, smooth_curve)

    rb_params = params.get("rb", {})
    success, msg = run_rubberband(audio_mono, sr, pitch_map, output_path, rb_params)
    return success, msg


def process_segment(audio, sr, clusters, cluster_idx, params, corrected_audio_path):
    """
    Process a single cluster + buffer, splice back into corrected audio with crossfade.
    Returns updated corrected audio array.
    """
    audio_mono = get_audio_mono(audio)
    buffer_s = 0.3  # 300ms buffer each side
    crossfade_s = CROSSFADE_MS / 1000.0
    crossfade_samples = int(crossfade_s * sr)

    cluster = clusters[cluster_idx]
    seg_start = max(0, cluster["start_time"] - buffer_s)
    seg_end = min(len(audio_mono) / sr, cluster["end_time"] + buffer_s)

    seg_start_sample = int(seg_start * sr)
    seg_end_sample = int(seg_end * sr)
    segment = audio_mono[seg_start_sample:seg_end_sample]

    # Build pitch map relative to segment
    seg_length = len(segment)
    shift = cluster["pitch_shift_semitones"]
    ramp_in_frames = int((cluster.get("ramp_in_ms", DEFAULT_TRANSITION_RAMP_MS) / 1000.0) * sr)
    ramp_out_frames = int((cluster.get("ramp_out_ms", DEFAULT_TRANSITION_RAMP_MS) / 1000.0) * sr)

    # Convert cluster times to segment-relative frames
    start_frame = int((cluster["start_time"] - seg_start) * sr)
    end_frame = int((cluster["end_time"] - seg_start) * sr)
    start_frame = max(0, start_frame)
    end_frame = min(seg_length - 1, end_frame)

    # Ramp zones are entirely outside the cluster
    ramp_in_start = max(0, start_frame - ramp_in_frames)
    ramp_out_end = min(seg_length - 1, end_frame + ramp_out_frames)

    pitch_map = [
        (0, 0.0),
        (ramp_in_start, 0.0),
        (start_frame, shift),
        (end_frame, shift),
        (ramp_out_end, 0.0),
        (seg_length - 1, 0.0),
    ]
    pitch_map = sorted(set(pitch_map), key=lambda x: x[0])

    # Process segment
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        processed_path = f.name

    rb_params = params.get("rb", {})
    success, msg = run_rubberband(segment, sr, pitch_map, processed_path, rb_params)

    if not success:
        if os.path.exists(processed_path):
            os.remove(processed_path)
        return None, msg

    # Load processed segment
    processed_seg, _ = sf.read(processed_path)
    os.remove(processed_path)

    # Load current corrected audio
    if os.path.exists(corrected_audio_path):
        corrected, _ = sf.read(corrected_audio_path)
    else:
        corrected = audio_mono.copy()

    # Ensure mono
    if len(processed_seg.shape) > 1:
        processed_seg = processed_seg.mean(axis=1)
    if len(corrected.shape) > 1:
        corrected = corrected.mean(axis=1)

    # Trim/pad processed segment to match original segment length
    if len(processed_seg) > seg_length:
        processed_seg = processed_seg[:seg_length]
    elif len(processed_seg) < seg_length:
        processed_seg = np.pad(processed_seg, (0, seg_length - len(processed_seg)))

    # Splice with crossfade
    result = corrected.copy()

    # Crossfade at start
    if seg_start_sample > 0 and crossfade_samples > 0:
        fade_in = np.linspace(0, 1, crossfade_samples)
        fade_out = np.linspace(1, 0, crossfade_samples)
        end_cf = min(
            seg_start_sample + crossfade_samples,
            len(result),
            len(processed_seg) + seg_start_sample,
        )
        cf_len = end_cf - seg_start_sample
        if cf_len > 0:
            result[seg_start_sample:end_cf] = (
                result[seg_start_sample:end_cf] * fade_out[:cf_len]
                + processed_seg[:cf_len] * fade_in[:cf_len]
            )
        result[end_cf:seg_end_sample] = processed_seg[cf_len:seg_length]
    else:
        result[seg_start_sample:seg_end_sample] = processed_seg[:seg_length]

    # Crossfade at end
    if seg_end_sample < len(result) and crossfade_samples > 0:
        fade_in = np.linspace(0, 1, crossfade_samples)
        fade_out = np.linspace(1, 0, crossfade_samples)
        start_cf = max(0, seg_end_sample - crossfade_samples)
        cf_len = seg_end_sample - start_cf
        seg_offset = seg_length - cf_len
        if cf_len > 0 and seg_offset >= 0:
            result[start_cf:seg_end_sample] = (
                processed_seg[seg_offset : seg_offset + cf_len] * fade_out[:cf_len]
                + result[start_cf:seg_end_sample] * fade_in[:cf_len]
            )

    return result, "OK"


def clusters_to_json(clusters):
    """Convert clusters to JSON-serializable format."""
    result = []
    for i, c in enumerate(clusters):
        result.append(
            {
                "id": i,
                "note": c["note"],
                "start_time": c["start_time"],
                "end_time": c["end_time"],
                "mean_freq": c["mean_freq"],
                "duration_ms": c["duration_ms"],
                "pitch_shift_semitones": c["pitch_shift_semitones"],
                "ramp_in_ms": c.get("ramp_in_ms", DEFAULT_TRANSITION_RAMP_MS),
                "ramp_out_ms": c.get("ramp_out_ms", DEFAULT_TRANSITION_RAMP_MS),
                "correction_strength": c["correction_strength"],
                "smoothing_percent": c["smoothing_percent"],
                "pitch_variation_cents": c.get("pitch_variation_cents", 0),
                "manually_edited": c.get("manually_edited", False),
            }
        )
    return result
