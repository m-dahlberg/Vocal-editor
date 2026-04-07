"""
Volume Engine - Breath detection and volume automation logic.
"""

import numpy as np


# ============================================
# RMS UTILITIES
# ============================================

def compute_rms_db(audio, sr, start_time, end_time):
    """Compute RMS in dB for an audio region."""
    s = int(start_time * sr)
    e = int(end_time * sr)
    s = max(0, s)
    e = min(len(audio), e)
    if e <= s:
        return -100.0
    segment = audio[s:e]
    rms = np.sqrt(np.mean(segment.astype(np.float64) ** 2))
    return float(20 * np.log10(rms + 1e-10))


def _compute_rms_db_segment(segment):
    """Compute RMS dB for a numpy segment."""
    if len(segment) == 0:
        return -100.0
    rms = np.sqrt(np.mean(segment.astype(np.float64) ** 2))
    return float(20 * np.log10(rms + 1e-10))


# ============================================
# BREATH DETECTION
# ============================================

def _find_silence_boundary(audio, sr, center_sample, direction, silence_db=-55.0, window_ms=20):
    """
    Search from center_sample in direction (+1 = forward, -1 = backward)
    until the RMS drops below silence_db. Returns the sample index.
    """
    window_samples = int(window_ms * sr / 1000)
    if window_samples < 1:
        window_samples = 1
    n = len(audio)
    pos = center_sample

    while True:
        start = max(0, pos - window_samples // 2)
        end = min(n, pos + window_samples // 2)
        if start >= end:
            break
        rms_db = _compute_rms_db_segment(audio[start:end])
        if rms_db <= silence_db:
            return pos
        pos += direction * window_samples
        if pos < 0 or pos >= n:
            return max(0, min(n - 1, pos))

    return max(0, min(n - 1, pos))


def _is_non_harmonic(frequencies, times, start_time, end_time):
    """
    Check that the region is mostly unvoiced (NaN frequencies from parselmouth).
    Breaths are typically unvoiced noise.
    """
    if frequencies is None or times is None:
        return True
    times = np.asarray(times, dtype=np.float64)
    frequencies = np.asarray(frequencies, dtype=np.float64)
    mask = (times >= start_time) & (times <= end_time)
    region_freqs = frequencies[mask]
    if len(region_freqs) == 0:
        return True
    voiced_ratio = np.sum(~np.isnan(region_freqs)) / len(region_freqs)
    return voiced_ratio < 0.3  # < 30% voiced means likely breath/noise


def detect_breaths(audio, sr, clusters, frequencies, times, params):
    """
    Detect breath regions in audio gaps between notes.

    Parameters
    ----------
    audio       : 1D numpy array, mono audio
    sr          : sample rate
    clusters    : list of cluster dicts (must have start_time, end_time)
    frequencies : numpy array of pitch frequencies (NaN = unvoiced)
    times       : numpy array of time points corresponding to frequencies
    params      : dict with:
                  - min_breath_length_ms (default 80)
                  - min_breath_volume_db (default -50)
                  - max_breath_volume_db (default -15)

    Returns list of breath dicts.
    """
    min_length_ms = params.get('min_breath_length_ms', 80)
    min_vol_db = params.get('min_breath_volume_db', -50)
    max_vol_db = params.get('max_breath_volume_db', -15)
    silence_db = params.get('silence_threshold_db', -55.0)
    window_ms = 20  # sliding window for RMS analysis

    window_samples = int(window_ms * sr / 1000)
    n = len(audio)

    # Sort clusters by start time
    sorted_clusters = sorted(clusters, key=lambda c: c['start_time'])

    breaths = []
    breath_id = 0

    for i, cluster in enumerate(sorted_clusters):
        # Determine gap before this note
        if i == 0:
            gap_start = 0.0
        else:
            gap_start = sorted_clusters[i - 1]['end_time']

        gap_end = cluster['start_time']
        gap_duration_ms = (gap_end - gap_start) * 1000

        if gap_duration_ms < min_length_ms:
            continue

        # Convert to samples
        gap_start_s = int(gap_start * sr)
        gap_end_s = int(gap_end * sr)
        gap_start_s = max(0, gap_start_s)
        gap_end_s = min(n, gap_end_s)

        if gap_end_s - gap_start_s < window_samples:
            continue

        # Compute sliding-window RMS across the gap to find quietest point
        rms_vals = []
        positions = []
        pos = gap_start_s
        while pos + window_samples <= gap_end_s:
            seg = audio[pos:pos + window_samples]
            rms_vals.append(_compute_rms_db_segment(seg))
            positions.append(pos + window_samples // 2)
            pos += window_samples // 2

        if not rms_vals:
            continue

        rms_arr = np.array(rms_vals)
        quietest_idx = int(np.argmin(rms_arr))
        quietest_sample = positions[quietest_idx]

        # Search backward from quietest_sample to find silence boundary
        silence_sample = _find_silence_boundary(
            audio, sr, quietest_sample, direction=-1,
            silence_db=silence_db, window_ms=window_ms
        )

        # Candidate breath region: from silence boundary to quietest point
        cand_start_s = silence_sample
        cand_end_s = gap_end_s

        # Clamp to gap boundaries
        cand_start_s = max(gap_start_s, cand_start_s)
        cand_end_s = min(gap_end_s, cand_end_s)

        if cand_end_s <= cand_start_s:
            continue

        cand_start_t = cand_start_s / sr
        cand_end_t = cand_end_s / sr
        cand_duration_ms = (cand_end_t - cand_start_t) * 1000

        if cand_duration_ms < min_length_ms:
            continue

        # Validate: must overlap with gap (between notes)
        if cand_start_t < gap_start or cand_end_t > gap_end + 0.001:
            continue

        # Validate: non-harmonic (mostly unvoiced)
        if not _is_non_harmonic(frequencies, times, cand_start_t, cand_end_t):
            continue

        # Compute RMS for the breath region
        rms_db = compute_rms_db(audio, sr, cand_start_t, cand_end_t)

        # Validate volume range
        if rms_db < min_vol_db or rms_db > max_vol_db:
            continue

        breaths.append({
            'id': breath_id,
            'start_time': round(cand_start_t, 4),
            'end_time': round(cand_end_t, 4),
            'duration_ms': round(cand_duration_ms, 1),
            'rms_db': round(rms_db, 2),
            'gain_db': 0.0,
            'manually_created': False,
        })
        breath_id += 1

    return breaths


def create_breath_at_point(audio, sr, click_time, clusters, frequencies, times, params):
    """
    Create a breath region by scanning outward from click_time.
    Returns a breath dict or None if the region is invalid.
    """
    min_length_ms = params.get('min_breath_length_ms', 80)
    min_vol_db = params.get('min_breath_volume_db', -50)
    max_vol_db = params.get('max_breath_volume_db', -15)
    silence_db = params.get('silence_threshold_db', -55.0)
    window_ms = 20

    n = len(audio)
    click_sample = int(click_time * sr)
    click_sample = max(0, min(n - 1, click_sample))

    # Sort clusters
    sorted_clusters = sorted(clusters, key=lambda c: c['start_time'])

    # Check click is not inside a note cluster
    for c in sorted_clusters:
        if c['start_time'] <= click_time <= c['end_time']:
            return None  # Click is inside a note

    # Find the gap this click is in
    gap_start = 0.0
    gap_end = audio.shape[0] / sr
    for i, c in enumerate(sorted_clusters):
        if c['start_time'] > click_time:
            gap_end = c['start_time']
            break
        gap_start = c['end_time']

    # Scan backward from click to find left boundary
    left_sample = _find_silence_boundary(
        audio, sr, click_sample, direction=-1,
        silence_db=silence_db, window_ms=window_ms
    )
    # Scan forward from click to find right boundary
    right_sample = _find_silence_boundary(
        audio, sr, click_sample, direction=+1,
        silence_db=silence_db, window_ms=window_ms
    )

    # Clamp to gap boundaries
    left_sample = max(int(gap_start * sr), left_sample)
    right_sample = min(int(gap_end * sr), right_sample)

    if right_sample <= left_sample:
        return None

    start_t = left_sample / sr
    end_t = right_sample / sr
    duration_ms = (end_t - start_t) * 1000

    if duration_ms < min_length_ms:
        return None

    if not _is_non_harmonic(frequencies, times, start_t, end_t):
        return None

    rms_db = compute_rms_db(audio, sr, start_t, end_t)

    if rms_db < min_vol_db or rms_db > max_vol_db:
        return None

    return {
        'id': -1,  # will be assigned by caller
        'start_time': round(start_t, 4),
        'end_time': round(end_t, 4),
        'duration_ms': round(duration_ms, 1),
        'rms_db': round(rms_db, 2),
        'gain_db': 0.0,
        'manually_created': True,
    }


# ============================================
# GAIN COMPUTATION
# ============================================

def compute_effective_gains(clusters, breaths, volume_params):
    """
    Compute effective gain_db for each cluster and breath based on macro controls.

    Processing order:
      1. Apply min RMS clamp (raise quiet items)
      2. Apply max RMS clamp (lower loud items)
      3. Add global offset

    Returns dict: { ('note', id): gain_db, ('breath', id): gain_db }
    """
    note_min = volume_params.get('note_min_rms_db', -60.0)
    note_max = volume_params.get('note_max_rms_db', 0.0)
    note_offset = volume_params.get('note_global_offset_db', 0.0)
    breath_min = volume_params.get('breath_min_rms_db', -60.0)
    breath_max = volume_params.get('breath_max_rms_db', 0.0)
    breath_offset = volume_params.get('breath_global_offset_db', 0.0)

    result = {}

    for c in clusters:
        rms = c.get('rms_db', -60.0)
        gain = c.get('gain_db', 0.0)
        if c.get('manual', False):
            # Manual override: bypass all macro controls
            result[('note', c.get('id', 0))] = gain
            continue
        # Min clamp: raise quiet notes
        if rms + gain < note_min:
            gain = note_min - rms
        # Max clamp: lower loud notes
        if rms + gain > note_max:
            gain = note_max - rms
        # Global offset
        gain += note_offset
        result[('note', c.get('id', 0))] = gain

    for b in breaths:
        rms = b.get('rms_db', -60.0)
        gain = b.get('gain_db', 0.0)
        if b.get('manual', False):
            result[('breath', b.get('id', 0))] = gain
            continue
        if rms + gain < breath_min:
            gain = breath_min - rms
        if rms + gain > breath_max:
            gain = breath_max - rms
        gain += breath_offset
        result[('breath', b.get('id', 0))] = gain

    return result


# ============================================
# GAIN ENVELOPE GENERATION AND APPLICATION
# ============================================

def generate_gain_envelope(clusters, breaths, effective_gains, sr, audio_length):
    """
    Build a sample-by-sample gain envelope in dB.

    Each note/breath region = flat segment at its effective gain.
    Between adjacent segments = linear ramp.
    Outside all segments = 0 dB (no change).

    Returns a numpy float32 array of shape (audio_length,).
    """
    envelope = np.zeros(audio_length, dtype=np.float32)

    # Build list of (start_s, end_s, gain_db) segments from clusters and breaths
    segments = []
    for c in clusters:
        cid = c.get('id', 0)
        gain = effective_gains.get(('note', cid), 0.0)
        start_s = int(c['start_time'] * sr)
        end_s = int(c['end_time'] * sr)
        segments.append((start_s, end_s, gain))

    for b in breaths:
        bid = b.get('id', 0)
        gain = effective_gains.get(('breath', bid), 0.0)
        start_s = int(b['start_time'] * sr)
        end_s = int(b['end_time'] * sr)
        segments.append((start_s, end_s, gain))

    if not segments:
        return envelope

    # Sort segments by start
    segments.sort(key=lambda x: x[0])

    # Fill flat segments
    for start_s, end_s, gain in segments:
        start_s = max(0, start_s)
        end_s = min(audio_length, end_s)
        if end_s > start_s:
            envelope[start_s:end_s] = gain

    # Add linear ramps between adjacent segments
    for i in range(len(segments) - 1):
        _, end_prev, gain_prev = segments[i]
        start_next, _, gain_next = segments[i + 1]
        end_prev = max(0, min(audio_length, end_prev))
        start_next = max(0, min(audio_length, start_next))
        if start_next > end_prev:
            ramp_len = start_next - end_prev
            ramp = np.linspace(gain_prev, gain_next, ramp_len, dtype=np.float32)
            envelope[end_prev:start_next] = ramp

    return envelope


def apply_gain_envelope(audio, gain_envelope_db):
    """
    Apply a dB gain envelope to audio.
    output = audio * 10^(gain_db / 20)
    """
    linear_gain = np.power(10.0, gain_envelope_db / 20.0).astype(np.float32)
    return (audio.astype(np.float32) * linear_gain)
