"""
De-Clicker Engine — Detects and repairs brief amplitude spikes (clicks/crackle)
in audio using multi-band frequency analysis.

Refactored from the Audacity Nyquist De-Clicker plugin.
"""

import numpy as np
from scipy.signal import fftconvolve, lfilter

# ─── Default parameters ──────────────────────────────────────────────────────

DEFAULT_DECLICKER_PARAMS = {
    'num_passes': 2,
    'sensitivity_db': 6.0,
    'step_size_ms': 5.0,
    'max_click_length_steps': 2,
    'min_separation_steps': 3,
    'dense_threshold_db': -45.0,
    'freq_low': 150.0,
    'freq_high': 9600.0,
    'num_bands': 12,
    'crossfade_ms': 5.0,
}


def get_default_declicker_params():
    return dict(DEFAULT_DECLICKER_PARAMS)


# ─── Frequency band decomposition ────────────────────────────────────────────

def build_frequency_bands(freq_low, freq_high, num_bands):
    """Return N+1 log-spaced boundary frequencies defining N bands."""
    return np.geomspace(freq_low, freq_high, num_bands + 1).tolist()


# ─── SFT3F flat-top window & bandpass kernel ──────────────────────────────────

# SFT3F window coefficients (sum-of-cosines flat-top window)
# From: Heinzel, Rüdiger, Schilling — "Spectrum and spectral density estimation"
_SFT3F_COEFFS = [0.26526, -0.5, 0.23474]
# First zero at 3.0 bins, 3dB width at 3.1502 bins
_SFT3F_3DB_WIDTH = 3.1502


def _sft3f_window(n):
    """Generate an SFT3F flat-top window of length n."""
    t = np.arange(n, dtype=np.float64) / n
    w = np.zeros(n, dtype=np.float64)
    for k, coeff in enumerate(_SFT3F_COEFFS):
        w += coeff * np.cos(2.0 * np.pi * k * t)
    return w


def _build_bandpass_kernel(sr, center_freq, bandwidth):
    """
    Build a normalized bandpass convolution kernel for a frequency band.

    Uses a windowed sinusoid approach: multiply a cosine at the center frequency
    by the SFT3F window. The window length is chosen so the 3dB width of the
    main lobe matches the desired bandwidth.

    Returns the kernel as a 1D numpy array.
    """
    # Determine bin_number: how many periods of the center freq fit in the window
    # The 3dB width in Hz = bin_frequency * SFT3F_3DB_WIDTH
    # We want 3dB width >= bandwidth, so bin_frequency <= bandwidth / SFT3F_3DB_WIDTH
    # bin_number = center_freq / bin_frequency
    min_bin_freq = bandwidth / _SFT3F_3DB_WIDTH
    bin_number = max(1, int(center_freq / min_bin_freq))
    bin_freq = center_freq / bin_number

    # Window length = one period of the bin frequency
    window_len = int(round(sr / bin_freq))
    if window_len < 4:
        window_len = 4

    # Build windowed cosine kernel
    t = np.arange(window_len, dtype=np.float64) / sr
    cosine = np.cos(2.0 * np.pi * center_freq * t)
    window = _sft3f_window(window_len)
    kernel = cosine * window

    # Normalize: ensure convolving a sinusoid at center_freq preserves amplitude
    test_cos = np.cos(2.0 * np.pi * center_freq * t)
    norm_factor = np.sum(test_cos * kernel)
    if abs(norm_factor) > 1e-12:
        kernel /= abs(norm_factor)

    return kernel


# ─── Per-band peak computation ────────────────────────────────────────────────

def _compute_band_peaks(audio, sr, kernel, step_samples):
    """
    Convolve audio with a bandpass kernel and compute per-step peak amplitudes.

    Returns a 1D array of peak amplitudes, one per step.
    """
    # Convolve (FFT-based for efficiency)
    filtered = fftconvolve(audio, kernel, mode='same')

    # Compute peak amplitude per step
    n_steps = len(filtered) // step_samples
    if n_steps == 0:
        return np.array([], dtype=np.float64)

    # Trim to exact multiple of step_samples
    trimmed = np.abs(filtered[:n_steps * step_samples])
    peaks = trimmed.reshape(n_steps, step_samples).max(axis=1)

    # Guard against zero (for ratio computation)
    peaks = np.maximum(peaks, 1e-10)
    return peaks


# ─── Per-band click detection ─────────────────────────────────────────────────

def _detect_clicks_in_band(peaks, sensitivity_db, max_click_steps,
                           min_separation, dense_threshold_db):
    """
    Detect clicks in a single frequency band's peak amplitude array.

    A click is detected when:
    1. The peak-to-background ratio on both sides exceeds the sensitivity threshold
    2. The click doesn't exceed max_click_steps in length
    3. Minimum separation between clicks is respected (unless crackle mode)

    Returns list of dicts: {step_idx, num_steps, ratio_db}
    """
    n = len(peaks)
    if n < min_separation * 2 + 1:
        return []

    sensitivity_ratio = 10.0 ** (sensitivity_db / 20.0)
    dense_threshold_linear = 10.0 ** (dense_threshold_db / 20.0)

    detections = []
    step = min_separation  # Start after separation margin

    while step < n - min_separation:
        # Compute background level: look at neighbors outside the separation window
        left_start = max(0, step - min_separation)
        left_end = step
        right_start = step + 1
        right_end = min(n, step + 1 + min_separation)

        left_bg = np.min(peaks[left_start:left_end]) if left_end > left_start else peaks[step]
        right_bg = np.min(peaks[right_start:right_end]) if right_end > right_start else peaks[step]

        # Use the minimum of left and right background
        # (a click should be louder than BOTH sides)
        foreground = peaks[step]
        background = max(left_bg, right_bg)  # Conservative: use the louder side

        ratio = foreground / background if background > 1e-12 else 1.0

        if ratio >= sensitivity_ratio:
            # Found a click candidate — check how wide it is
            width = 1
            max_fg = foreground
            for w in range(1, max_click_steps):
                if step + w >= n - min_separation:
                    break
                next_fg = peaks[step + w]
                # Check if the next step is also above threshold vs right background
                right_start_w = min(n, step + w + 1)
                right_end_w = min(n, step + w + 1 + min_separation)
                if right_end_w > right_start_w:
                    right_bg_w = np.min(peaks[right_start_w:right_end_w])
                    if next_fg / max(right_bg_w, 1e-12) >= sensitivity_ratio:
                        width += 1
                        max_fg = max(max_fg, next_fg)
                    else:
                        break
                else:
                    break

            ratio_db = 20.0 * np.log10(max_fg / background) if background > 1e-12 else 0.0

            detections.append({
                'step_idx': step,
                'num_steps': width,
                'ratio_db': float(ratio_db),
            })

            # Skip past the click plus separation
            # For crackle (dense clicks): allow closer spacing if amplitude is low enough
            if foreground < dense_threshold_linear:
                step += width  # Allow dense packing for quiet crackle
            else:
                step += width + min_separation
        else:
            step += 1

    return detections


# ─── Multi-band detection ─────────────────────────────────────────────────────

def detect_clicks(audio, sr, params=None):
    """
    Run multi-band click detection on audio.

    Returns dict with:
      - clicks: list of merged click detections
      - band_centers: center frequencies of each band
      - band_peaks: per-band peak amplitude arrays (for visualization)
      - step_size_s: step size in seconds
      - num_steps: number of steps
    """
    if params is None:
        params = get_default_declicker_params()

    step_samples = max(1, int(round(sr * params['step_size_ms'] / 1000.0)))
    step_size_s = step_samples / sr

    # Build frequency bands
    boundaries = build_frequency_bands(
        params['freq_low'], params['freq_high'], params['num_bands']
    )

    band_centers = []
    band_peaks_list = []
    all_band_detections = []  # list of (band_idx, detections)

    for i in range(len(boundaries) - 1):
        lo = boundaries[i]
        hi = boundaries[i + 1]
        center = np.sqrt(lo * hi)  # geometric mean
        bandwidth = hi - lo

        # Use wider detection bands (2x in log-frequency) for better coverage
        detect_lo = lo / np.sqrt(hi / lo)
        detect_hi = hi * np.sqrt(hi / lo)
        detect_bandwidth = detect_hi - detect_lo

        band_centers.append(float(center))

        # Build kernel and compute peaks
        kernel = _build_bandpass_kernel(sr, float(center), float(detect_bandwidth))
        peaks = _compute_band_peaks(audio, sr, kernel, step_samples)
        band_peaks_list.append(peaks)

        # Detect clicks in this band
        dets = _detect_clicks_in_band(
            peaks,
            params['sensitivity_db'],
            params['max_click_length_steps'],
            params['min_separation_steps'],
            params['dense_threshold_db'],
        )

        for d in dets:
            d['band_idx'] = i
        all_band_detections.append(dets)

    # Merge detections across bands at overlapping timesteps
    n_steps = len(band_peaks_list[0]) if band_peaks_list else 0
    clicks = _merge_detections(all_band_detections, n_steps, step_size_s,
                               params['max_click_length_steps'])

    # Convert band_peaks to lists for JSON serialization
    band_peaks_json = [p.tolist() for p in band_peaks_list]

    return {
        'clicks': clicks,
        'band_centers': band_centers,
        'band_peaks': band_peaks_json,
        'step_size_s': step_size_s,
        'num_steps': n_steps,
    }


def _merge_detections(all_band_detections, n_steps, step_size_s, max_click_steps):
    """
    Merge click detections from all bands. Detections at the same or overlapping
    timesteps are combined into a single click spanning all affected bands.
    """
    # Build a step->band map
    step_bands = {}  # step_idx -> {band_indices, max_ratio_db, max_steps}

    for band_dets in all_band_detections:
        for d in band_dets:
            s = d['step_idx']
            w = d['num_steps']
            for offset in range(w):
                key = s + offset
                if key not in step_bands:
                    step_bands[key] = {
                        'bands': set(),
                        'max_ratio_db': 0.0,
                        'start_step': key,
                        'end_step': key,
                    }
                step_bands[key]['bands'].add(d['band_idx'])
                step_bands[key]['max_ratio_db'] = max(
                    step_bands[key]['max_ratio_db'], d['ratio_db']
                )

    if not step_bands:
        return []

    # Group contiguous flagged steps into clicks
    sorted_steps = sorted(step_bands.keys())
    clicks = []
    current_start = sorted_steps[0]
    current_end = sorted_steps[0]
    current_bands = set(step_bands[sorted_steps[0]]['bands'])
    current_max_ratio = step_bands[sorted_steps[0]]['max_ratio_db']

    for s in sorted_steps[1:]:
        if s <= current_end + 1:
            # Contiguous — extend
            current_end = s
            current_bands |= step_bands[s]['bands']
            current_max_ratio = max(current_max_ratio, step_bands[s]['max_ratio_db'])
        else:
            # Gap — emit previous click
            clicks.append({
                'step_idx': current_start,
                'start_time': float(current_start * step_size_s),
                'end_time': float((current_end + 1) * step_size_s),
                'bands': sorted(current_bands),
                'max_ratio_db': float(current_max_ratio),
                'is_crackle': False,  # Could be refined
            })
            current_start = s
            current_end = s
            current_bands = set(step_bands[s]['bands'])
            current_max_ratio = step_bands[s]['max_ratio_db']

    # Emit last click
    clicks.append({
        'step_idx': current_start,
        'start_time': float(current_start * step_size_s),
        'end_time': float((current_end + 1) * step_size_s),
        'bands': sorted(current_bands),
        'max_ratio_db': float(current_max_ratio),
        'is_crackle': False,
    })

    return clicks


# ─── Peaking EQ biquad (Audio EQ Cookbook by Robert Bristow-Johnson) ──────────

def _peaking_eq_coeffs(sr, center_freq, gain_db, bw_octaves):
    """
    Design a peaking EQ biquad filter.

    With negative gain_db this directly attenuates the band — no subtraction
    tricks needed.  Returns (b, a) coefficient arrays for lfilter.
    """
    A = 10.0 ** (gain_db / 40.0)          # amplitude = sqrt(linear gain)
    w0 = 2.0 * np.pi * center_freq / sr
    # Q from bandwidth in octaves
    Q = 1.0 / (2.0 * np.sinh(np.log(2.0) / 2.0 * bw_octaves))
    Q = max(0.1, min(Q, 30.0))
    alpha = np.sin(w0) / (2.0 * Q)

    b0 = 1.0 + alpha * A
    b1 = -2.0 * np.cos(w0)
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * np.cos(w0)
    a2 = 1.0 - alpha / A

    return (np.array([b0 / a0, b1 / a0, b2 / a0]),
            np.array([1.0,     a1 / a0, a2 / a0]))


# ─── Click repair via parametric EQ attenuation ──────────────────────────────

def repair_clicks(audio, sr, detections, band_boundaries, params):
    """
    Repair detected clicks by applying parametric EQ attenuation.

    For each click, designs peaking EQ biquads with negative gain at each
    affected frequency band.  Uses crossfade envelopes for smooth transitions.
    """
    result = audio.copy()
    crossfade_samples = max(1, int(round(sr * params['crossfade_ms'] / 1000.0)))
    step_samples = max(1, int(round(sr * params['step_size_ms'] / 1000.0)))

    band_centers = []
    band_widths = []
    for i in range(len(band_boundaries) - 1):
        lo = band_boundaries[i]
        hi = band_boundaries[i + 1]
        band_centers.append(np.sqrt(lo * hi))
        band_widths.append(np.log2(hi / lo))  # width in octaves

    for click in detections:
        # Determine the sample range to process (with crossfade padding)
        start_sample = max(0, click['step_idx'] * step_samples - crossfade_samples)
        if 'end_time' in click and 'start_time' in click:
            dur_samples = int(round((click['end_time'] - click['start_time']) * sr))
        else:
            dur_samples = step_samples
        end_sample = min(len(audio),
                         click['step_idx'] * step_samples + dur_samples + crossfade_samples)

        if end_sample <= start_sample:
            continue

        segment_len = end_sample - start_sample
        original_segment = result[start_sample:end_sample].copy()
        filtered_segment = original_segment.copy()

        # Attenuation: bring the click down to the background level
        gain_db = -(click['max_ratio_db'] - params['sensitivity_db'])
        gain_db = min(gain_db, -0.5)  # always cut at least a little

        # Apply a peaking EQ cut at each affected band
        for band_idx in click['bands']:
            if band_idx >= len(band_centers):
                continue

            center_hz = band_centers[band_idx]
            if center_hz >= sr / 2.0:
                continue  # above Nyquist

            bw_oct = band_widths[band_idx]
            b, a = _peaking_eq_coeffs(sr, center_hz, gain_db, bw_oct)
            filtered_segment = lfilter(b, a, filtered_segment)

        # Build crossfade envelope (raised-cosine fade in/out)
        envelope = np.ones(segment_len, dtype=np.float64)
        fade_len = min(crossfade_samples, segment_len // 2)
        if fade_len > 1:
            fade_in = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_len) / fade_len))
            envelope[:fade_len] = fade_in
            envelope[-fade_len:] = fade_in[::-1]

        # Blend: envelope=0 → keep original, envelope=1 → use filtered
        result[start_sample:end_sample] = (
            original_segment * (1.0 - envelope) + filtered_segment * envelope
        )

    return result


# ─── Multi-pass orchestrator ──────────────────────────────────────────────────

def run_declicker(audio, sr, params=None):
    """
    Run the full de-clicker: detect → repair, repeated for num_passes.

    Returns (repaired_audio, list_of_detection_results_per_pass).
    """
    if params is None:
        params = get_default_declicker_params()

    current = audio.copy()
    all_pass_results = []

    boundaries = build_frequency_bands(
        params['freq_low'], params['freq_high'], params['num_bands']
    )

    for pass_num in range(params['num_passes']):
        result = detect_clicks(current, sr, params)
        all_pass_results.append(result)

        if not result['clicks']:
            break

        current = repair_clicks(
            current, sr, result['clicks'], boundaries, params
        )

    return current, all_pass_results


def isolate_clicks(original, repaired):
    """Return the difference (what was removed) — the isolated clicks."""
    return original - repaired


def repair_clicks_segment(audio, sr, clicks, band_boundaries, params,
                          padding_ms=100, crop_ms=50, crossfade_ms=10):
    """
    Repair one or more clicks by extracting a segment around them, repairing
    within that segment, cropping artifact edges, and splicing back with crossfade.

    Unlike repair_clicks() which modifies the full audio, this extracts only the
    relevant region so successive calls accumulate correctly.
    """
    if not clicks:
        return audio.copy()

    padding_s = padding_ms / 1000.0
    crop_s = crop_ms / 1000.0
    crossfade_s = crossfade_ms / 1000.0
    step_samples = max(1, int(round(sr * params['step_size_ms'] / 1000.0)))

    # Determine segment boundaries spanning all clicks
    seg_start_s = max(0.0, min(c['start_time'] for c in clicks) - padding_s)
    seg_end_s = min(len(audio) / sr, max(c['end_time'] for c in clicks) + padding_s)

    seg_start_sample = int(seg_start_s * sr)
    seg_end_sample = int(seg_end_s * sr)

    if seg_end_sample <= seg_start_sample:
        return audio.copy()

    segment = audio[seg_start_sample:seg_end_sample].copy()

    # Adjust clicks to be relative to the segment start
    seg_start_step = seg_start_sample // step_samples
    adjusted_clicks = []
    for c in clicks:
        adj = dict(c)
        adj['step_idx'] = max(0, c['step_idx'] - seg_start_step)
        adj['start_time'] = max(0.0, c['start_time'] - seg_start_s)
        adj['end_time'] = max(0.0, c['end_time'] - seg_start_s)
        adjusted_clicks.append(adj)

    repaired_seg = repair_clicks(segment, sr, adjusted_clicks, band_boundaries, params)

    # Crop artifact edges
    crop_samples = int(crop_s * sr)
    crop_samples = min(crop_samples, (seg_end_sample - seg_start_sample) // 4)

    # Splice boundaries after cropping
    splice_start = seg_start_sample + crop_samples
    splice_end = seg_end_sample - crop_samples
    seg_content = repaired_seg[crop_samples: len(repaired_seg) - crop_samples]

    if splice_end <= splice_start or len(seg_content) == 0:
        return audio.copy()

    result = audio.copy()
    content_len = len(seg_content)
    cf_samples = min(int(crossfade_s * sr), content_len // 2, splice_end - splice_start)

    if cf_samples < 1:
        result[splice_start:splice_end] = seg_content
        return result

    # Crossfade at start: old fades out, new fades in
    fade_in = np.linspace(0.0, 1.0, cf_samples)
    fade_out = np.linspace(1.0, 0.0, cf_samples)
    result[splice_start:splice_start + cf_samples] = (
        result[splice_start:splice_start + cf_samples] * fade_out
        + seg_content[:cf_samples] * fade_in
    )

    # Direct replace in middle
    result[splice_start + cf_samples:splice_end - cf_samples] = (
        seg_content[cf_samples:content_len - cf_samples]
    )

    # Crossfade at end: new fades out, old fades in
    result[splice_end - cf_samples:splice_end] = (
        seg_content[content_len - cf_samples:] * fade_out
        + result[splice_end - cf_samples:splice_end] * fade_in
    )

    return result
