"""
SMS Engine - Spectral Modeling Synthesis (Harmonic + Stochastic) pitch shifting.

Uses the sms-tools library's HPS model to decompose audio into harmonics and
stochastic residual, shift harmonic frequencies directly, and resynthesize
via additive synthesis. This avoids phase vocoder artifacts entirely.

The stochastic component (breath, noise, consonants) passes through unmodified.
"""

import numpy as np
import soundfile as sf
from dataclasses import dataclass, field
from typing import Optional

# sms-tools imports
from smstools.models import hpsModel as HPS
from smstools.models import sineModel as SM
from smstools.models import stochasticModel as STM
from smstools.models import harmonicModel as HM
from smstools.models import utilFunctions as UF
from smstools.models import dftModel as DFT
import math

# Default SMS parameters
DEFAULT_SMS_MAX_HARMONICS = 60
DEFAULT_SMS_PEAK_THRESHOLD = -80      # dB
DEFAULT_SMS_STOCHASTIC_FACTOR = 0.05  # residual spectral envelope resolution
DEFAULT_SMS_TIMBRE_PRESERVE = True
DEFAULT_SMS_HOP_SIZE = 128            # samples at 44100 Hz (~2.9ms)
DEFAULT_SMS_SYNTH_FFT_SIZE = 2048     # synthesis FFT size
DEFAULT_SMS_F0_ERROR_THRESHOLD = 5.0  # kept for frontend param compat
DEFAULT_SMS_HARM_DEV_SLOPE = 0.01     # harmonic deviation slope
DEFAULT_SMS_MIN_SINE_DUR = 0.02       # minimum sine track duration (seconds)
DEFAULT_SMS_RESIDUAL_LEVEL = 1.0      # stochastic component mix (0=harmonics only)
SMS_INTERNAL_SR = 44100               # sms-tools requires 44100 Hz


@dataclass
class SMSAnalysis:
    """Holds the result of SMS harmonic+stochastic analysis."""
    hfreq: np.ndarray       # harmonic frequencies per frame (nFrames x nHarmonics)
    hmag: np.ndarray        # harmonic magnitudes per frame
    hphase: np.ndarray      # harmonic phases per frame
    stocEnv: np.ndarray     # stochastic spectral envelope per frame
    residual: np.ndarray    # original residual signal (for direct mixing)
    original_sr: int        # original sample rate before resampling
    internal_sr: int        # sample rate used for analysis (44100)
    hop_size: int           # hop size in samples (at internal_sr)
    fft_size: int           # FFT size used
    window_type: str        # analysis window type
    min_frequency: float    # min f0 used for analysis


def _resample(audio, sr_in, sr_out):
    """Resample audio using scipy's resample_poly for quality."""
    if sr_in == sr_out:
        return audio
    from scipy.signal import resample_poly
    from math import gcd
    g = gcd(sr_in, sr_out)
    up = sr_out // g
    down = sr_in // g
    return resample_poly(audio, up, down).astype(np.float32)


def _next_power_of_2(n):
    """Round up to next power of 2."""
    p = 1
    while p < n:
        p *= 2
    return p


def _harmonic_model_anal_fast(x, fs, w, N, H, t, nH, minf0, maxf0, harmDevSlope, minSineDur,
                               external_f0=None):
    """
    Harmonic analysis using external f0 guide from Parselmouth.

    The f0 contour (from Parselmouth's autocorrelation pitch tracker) is used
    directly for harmonic detection. This is more robust than TWM for singing
    voice, especially with overtone-rich voices and pitch drift.
    """
    if external_f0 is None or len(external_f0) == 0:
        raise ValueError("Parselmouth f0 data is required for SMS analysis. "
                         "Run pitch analysis before using the SMS engine.")

    hM1 = int(math.floor((w.size + 1) / 2))
    hM2 = int(math.floor(w.size / 2))
    x = np.append(np.zeros(hM2), x)
    x = np.append(x, np.zeros(hM2))
    pin = hM1
    pend = x.size - hM1
    w = w / sum(w)

    # Pre-calculate number of frames
    n_frames = 0
    p = pin
    while p <= pend:
        n_frames += 1
        p += H

    # Resample Parselmouth f0 to match SMS frame count
    if len(external_f0) == n_frames:
        f0_contour = external_f0.copy()
    else:
        ext_indices = np.linspace(0, n_frames - 1, len(external_f0))
        sms_indices = np.arange(n_frames)
        f0_contour = np.interp(sms_indices, ext_indices, external_f0)
    f0_contour[f0_contour < minf0] = 0
    n_voiced = np.sum(f0_contour > 0)
    print(f"[SMS] Using Parselmouth f0 guide: {n_voiced}/{n_frames} voiced frames")

    # ---- Spectral analysis + harmonic detection using f0 contour ----
    xhfreq = np.zeros((n_frames, nH))
    xhmag = np.zeros((n_frames, nH)) - 100.0
    xhphase = np.zeros((n_frames, nH))

    hfreqp = []
    frame_idx = 0
    pin_anal = hM1

    while pin_anal <= pend:
        x1 = x[pin_anal - hM1: pin_anal + hM2]
        mX, pX = DFT.dftAnal(x1, w, N)
        ploc = UF.peakDetection(mX, t)
        iploc, ipmag, ipphase = UF.peakInterp(mX, pX, ploc)
        ipfreq = fs * iploc / N

        hfreq, hmag, hphase = HM.harmonicDetection(
            ipfreq, ipmag, ipphase, f0_contour[frame_idx], nH, hfreqp, fs, harmDevSlope
        )
        hfreqp = hfreq
        xhfreq[frame_idx] = hfreq
        xhmag[frame_idx] = hmag
        xhphase[frame_idx] = hphase
        frame_idx += 1
        pin_anal += H

    xhfreq = SM.cleaningSineTracks(xhfreq, round(fs * minSineDur / H))
    return xhfreq, xhmag, xhphase


def _stochastic_model_anal_fast(x, H, N, stocf, fs=44100):
    """
    Optimized version of stochasticModelAnal that pre-allocates arrays.
    """
    from scipy.signal import resample
    from scipy.interpolate import splrep, splev
    from scipy.fft import fft
    from scipy.signal.windows import hann

    def hertz_to_mel(f):
        return 2595 * np.log10(1 + f / 700)

    hN = N // 2 + 1
    No2 = N // 2

    if hN * stocf < 3:
        raise ValueError("Stochastic decimation factor too small")
    if stocf > 1:
        raise ValueError("Stochastic decimation factor above 1")
    if not UF.isPower2(N):
        raise ValueError("FFT size (N) is not a power of 2")

    w = hann(N, sym=False)
    x = np.append(np.zeros(No2), x)
    x = np.append(x, np.zeros(No2))
    pin = No2
    pend = x.size - No2

    # Pre-calculate number of frames
    n_frames = 0
    p = pin
    while p <= pend:
        n_frames += 1
        p += H

    stoc_bins = int(stocf * hN)
    stocEnv = np.zeros((n_frames, stoc_bins))

    binFreqsMel = hertz_to_mel(np.arange(hN) * fs / float(N))
    uniformMelFreq = np.linspace(binFreqsMel[0], binFreqsMel[-1], hN)

    frame_idx = 0
    while pin <= pend:
        xw = x[pin - No2: pin + No2] * w
        X = fft(xw)
        mX = 20 * np.log10(np.abs(X[:hN]) + 1e-14)
        spl = splrep(binFreqsMel, np.maximum(-200, mX))
        mY = resample(splev(uniformMelFreq, spl), stoc_bins)
        stocEnv[frame_idx] = mY
        frame_idx += 1
        pin += H

    return stocEnv


def sms_analyze(audio_mono, sr, sms_params=None):
    """
    Analyze audio using the HPS (Harmonic + Stochastic) model.

    Returns an SMSAnalysis dataclass with all data needed for resynthesis.
    """
    if sms_params is None:
        sms_params = {}

    max_harmonics = sms_params.get('max_harmonics', DEFAULT_SMS_MAX_HARMONICS)
    peak_threshold = sms_params.get('peak_threshold', DEFAULT_SMS_PEAK_THRESHOLD)
    stoc_factor = sms_params.get('stochastic_factor', DEFAULT_SMS_STOCHASTIC_FACTOR)
    harm_dev_slope = sms_params.get('harm_dev_slope', DEFAULT_SMS_HARM_DEV_SLOPE)
    min_sine_dur = sms_params.get('min_sine_dur', DEFAULT_SMS_MIN_SINE_DUR)

    # Resample to 44100 Hz if needed
    audio_44k = _resample(audio_mono, int(sr), SMS_INTERNAL_SR)
    audio_44k = audio_44k.astype(np.float64)

    # Analysis parameters
    min_f0 = sms_params.get('min_frequency', 75.0)
    max_f0 = sms_params.get('max_frequency', 600.0)

    # Window size: needs >= 3 periods of the lowest frequency
    window_type = 'blackmanharris'
    min_window_size = int(3 * SMS_INTERNAL_SR / min_f0)
    if min_window_size % 2 == 0:
        min_window_size += 1

    # FFT size: next power of 2 above window size, minimum 2048
    fft_size = max(_next_power_of_2(min_window_size), 2048)

    # Hop size: user-configurable, must be power of 2
    hop_size = sms_params.get('hop_size', DEFAULT_SMS_HOP_SIZE)
    hop_size = max(64, min(hop_size, 1024))
    hop_size = _next_power_of_2(hop_size)

    # Stochastic FFT size (Ns parameter) — must be power of 2 and >= 2*H
    stoc_fft_size = max(fft_size, hop_size * 2)

    print(f"[SMS] Analyzing: {len(audio_44k)} samples @ {SMS_INTERNAL_SR}Hz")
    print(f"[SMS] window={min_window_size}, fft={fft_size}, hop={hop_size}, "
          f"maxH={max_harmonics}, f0=[{min_f0},{max_f0}]Hz, "
          f"harmDev={harm_dev_slope}, minSineDur={min_sine_dur}")

    # Optimized HPS analysis with pre-allocated arrays (avoids O(n²) vstack)
    window = UF.blackmanharris(min_window_size)
    window = window / window.sum()  # normalize

    # Build f0 guide from Parselmouth data (required)
    parselmouth_data = sms_params.pop('_parselmouth_f0', None)
    if parselmouth_data is None:
        raise ValueError("Parselmouth f0 data is required for SMS analysis. "
                         "Run pitch analysis before using the SMS engine.")

    pm_times = np.array(parselmouth_data['times'])
    pm_freqs = np.array(parselmouth_data['frequencies'])
    # Replace None/NaN with 0 (unvoiced)
    pm_freqs = np.array([f if f is not None and not np.isnan(f) else 0.0 for f in pm_freqs])

    # Interpolate Parselmouth f0 onto SMS frame grid
    n_sms_frames = len(range(0, len(audio_44k), hop_size))  # approximate
    sms_times = np.array([i * hop_size / SMS_INTERNAL_SR for i in range(n_sms_frames)])
    external_f0 = np.interp(sms_times, pm_times, pm_freqs)
    # Re-zero frames that fall in unvoiced gaps
    for i in range(len(external_f0)):
        t = sms_times[i]
        idx = np.searchsorted(pm_times, t)
        idx = min(idx, len(pm_freqs) - 1)
        if pm_freqs[idx] == 0:
            external_f0[i] = 0
        elif idx > 0 and pm_freqs[idx - 1] == 0 and abs(pm_times[idx - 1] - t) < abs(pm_times[idx] - t):
            external_f0[i] = 0

    hfreq, hmag, hphase = _harmonic_model_anal_fast(
        audio_44k, SMS_INTERNAL_SR, window, fft_size, hop_size,
        peak_threshold, max_harmonics, min_f0, max_f0,
        harm_dev_slope, min_sine_dur,
        external_f0=external_f0,
    )

    # Subtract harmonics to get residual, then analyze stochastic component
    stoc_anal_fft = max(512, hop_size * 2)
    xr = UF.sineSubtraction(audio_44k, stoc_fft_size, hop_size, hfreq, hmag, hphase, SMS_INTERNAL_SR)

    stocEnv = _stochastic_model_anal_fast(xr, hop_size, stoc_anal_fft, stoc_factor, SMS_INTERNAL_SR)


    print(f"[SMS] Analysis complete: {hfreq.shape[0]} frames, "
          f"{hfreq.shape[1]} harmonics tracked, "
          f"stocEnv shape={stocEnv.shape}")

    return SMSAnalysis(
        hfreq=hfreq,
        hmag=hmag,
        hphase=hphase,
        stocEnv=stocEnv,
        residual=xr.astype(np.float32),
        original_sr=int(sr),
        internal_sr=SMS_INTERNAL_SR,
        hop_size=hop_size,
        fft_size=fft_size,
        window_type=window_type,
        min_frequency=min_f0,
    )


def _build_spectral_envelope(freqs, mags, n_points=512, sr=44100):
    """Build a smooth spectral envelope from harmonic peaks using linear interpolation."""
    max_freq = sr / 2.0
    envelope = np.full(n_points, -120.0)  # dB floor
    freq_axis = np.linspace(0, max_freq, n_points)

    # Filter valid harmonics
    valid = [(f, m) for f, m in zip(freqs, mags) if f > 0]
    if not valid:
        return envelope

    valid_freqs, valid_mags = zip(*valid)
    valid_freqs = np.array(valid_freqs)
    valid_mags = np.array(valid_mags)

    # Sort by frequency
    order = np.argsort(valid_freqs)
    valid_freqs = valid_freqs[order]
    valid_mags = valid_mags[order]

    # Interpolate
    envelope = np.interp(freq_axis, valid_freqs, valid_mags,
                         left=valid_mags[0], right=-120.0)
    return envelope


def _smooth_harmonic_tracks(hfreq, hmag, max_gap=3, fade_frames=3):
    """
    Post-process harmonic tracks to reduce clicks and artifacts:
    1. Fill short gaps (up to max_gap frames) by interpolating freq/mag
    2. Apply multi-frame fade-in/fade-out at track boundaries
    """
    n_frames, n_harmonics = hfreq.shape

    for h in range(n_harmonics):
        freq_track = hfreq[:, h]
        mag_track = hmag[:, h]

        # --- Gap filling: interpolate short gaps ---
        i = 0
        while i < n_frames:
            if freq_track[i] > 0:
                i += 1
                continue
            # Found start of a gap
            gap_start = i
            while i < n_frames and freq_track[i] == 0:
                i += 1
            gap_end = i  # first frame after gap

            gap_len = gap_end - gap_start
            if gap_len <= max_gap and gap_start > 0 and gap_end < n_frames:
                # Both sides have active harmonics — interpolate
                f0 = freq_track[gap_start - 1]
                f1 = freq_track[gap_end]
                m0 = mag_track[gap_start - 1]
                m1 = mag_track[gap_end]
                for j in range(gap_len):
                    t = (j + 1) / (gap_len + 1)
                    freq_track[gap_start + j] = f0 + t * (f1 - f0)
                    mag_track[gap_start + j] = m0 + t * (m1 - m0)

        # --- Multi-frame fade at track boundaries ---
        i = 0
        while i < n_frames:
            if freq_track[i] == 0:
                i += 1
                continue
            # Found track start
            track_start = i
            while i < n_frames and freq_track[i] > 0:
                i += 1
            track_end = i  # first frame after track

            track_len = track_end - track_start
            if track_len < 2:
                continue

            # Fade in
            n_fade_in = min(fade_frames, track_len // 2)
            for j in range(n_fade_in):
                ramp = (j + 1) / (n_fade_in + 1)
                mag_track[track_start + j] += 20.0 * np.log10(ramp + 1e-10)

            # Fade out
            n_fade_out = min(fade_frames, track_len // 2)
            for j in range(n_fade_out):
                ramp = (j + 1) / (n_fade_out + 1)
                mag_track[track_end - 1 - j] += 20.0 * np.log10(ramp + 1e-10)

    return hfreq, hmag


def sms_pitch_shift(analysis, pitch_map, sr, audio_length, sms_params=None):
    """
    Apply pitch shifting to SMS analysis data and resynthesize.

    Args:
        analysis: SMSAnalysis from sms_analyze()
        pitch_map: List of (frame, semitones) pairs (same format as generate_pitch_map)
        sr: Original sample rate
        audio_length: Original audio length in samples
        sms_params: Optional SMS parameter dict for synthesis settings

    Returns:
        Pitch-shifted audio as numpy array at original sample rate.
    """
    if sms_params is None:
        sms_params = {}

    hfreq = analysis.hfreq.copy()
    hmag = analysis.hmag.copy()
    hphase = analysis.hphase.copy()
    stocEnv = analysis.stocEnv.copy()
    hop_size = analysis.hop_size
    n_frames = hfreq.shape[0]
    timbre_preserve = sms_params.get('timbre_preserve', DEFAULT_SMS_TIMBRE_PRESERVE)
    residual_level = sms_params.get('residual_level', DEFAULT_SMS_RESIDUAL_LEVEL)
    synth_fft_size = sms_params.get('synth_fft_size', DEFAULT_SMS_SYNTH_FFT_SIZE)
    synth_fft_size = _next_power_of_2(synth_fft_size)
    # sms-tools sineModelSynth allocates H*(L+3) output samples;
    # the overlap-add window of size N must fit: N <= 4*H
    synth_fft_size = max(hop_size * 2, min(synth_fft_size, hop_size * 4))

    # Convert pitch map from audio frames (at original sr) to SMS frame indices
    if not pitch_map:
        shift_per_frame = np.zeros(n_frames)
    else:
        pm = sorted(pitch_map, key=lambda x: x[0])
        pm_times = np.array([f / sr for f, _ in pm])
        pm_shifts = np.array([s for _, s in pm])

        sms_times = np.array([i * hop_size / analysis.internal_sr for i in range(n_frames)])
        shift_per_frame = np.interp(sms_times, pm_times, pm_shifts)

    non_zero = np.count_nonzero(np.abs(shift_per_frame) > 1e-6)
    print(f"[SMS] shift_per_frame: min={shift_per_frame.min():.4f}, max={shift_per_frame.max():.4f}, "
          f"non-zero={non_zero}/{n_frames}")

    # Log sample hfreq values before shifting
    mid = n_frames // 2
    sample_freqs_before = hfreq[mid][hfreq[mid] > 0][:5] if n_frames > 0 else []
    print(f"[SMS] hfreq before shift (frame {mid}): {sample_freqs_before}")

    # Apply pitch shift to each frame
    nyquist = analysis.internal_sr / 2.0
    for i in range(n_frames):
        shift_st = shift_per_frame[i]
        if abs(shift_st) < 1e-6:
            continue

        ratio = 2.0 ** (shift_st / 12.0)

        if timbre_preserve:
            orig_env = _build_spectral_envelope(
                hfreq[i], hmag[i], n_points=512, sr=analysis.internal_sr
            )
            freq_axis = np.linspace(0, analysis.internal_sr / 2.0, 512)

        # Shift harmonic frequencies
        new_freqs = hfreq[i] * ratio

        if timbre_preserve:
            new_mags = np.interp(new_freqs, freq_axis, orig_env,
                                 left=-120.0, right=-120.0)
            valid = hfreq[i] > 0
            hmag[i][valid] = new_mags[valid]

        # Clamp to Nyquist
        above_nyquist = new_freqs >= nyquist
        new_freqs[above_nyquist] = 0
        hmag[i][above_nyquist] = -120.0

        hfreq[i] = new_freqs

    # Log sample hfreq values after shifting
    sample_freqs_after = hfreq[mid][hfreq[mid] > 0][:5] if n_frames > 0 else []
    print(f"[SMS] hfreq after shift  (frame {mid}): {sample_freqs_after}")

    # Fill short harmonic gaps and apply multi-frame fades to reduce clicks
    hfreq, hmag = _smooth_harmonic_tracks(hfreq, hmag, max_gap=3, fade_frames=3)

    # Resynthesize harmonics and stochastic separately for mix control
    print(f"[SMS] Resynthesizing {n_frames} frames "
          f"(synth_fft={synth_fft_size}, hop={hop_size}, residual_level={residual_level})...")

    # Pass empty phases so sms-tools uses its internal phase propagation,
    # which correctly tracks the shifted frequencies instead of using
    # original analysis phases that cause destructive interference.
    yh = SM.sineModelSynth(hfreq, hmag, np.array([]), synth_fft_size, hop_size, SMS_INTERNAL_SR)

    # Use the original residual signal directly instead of resynthesizing
    # from the stochastic envelope. The envelope-based resynthesis shapes
    # white noise with a coarse spectral envelope, losing the natural
    # spectral correlation of the original residual (breath texture, etc.)
    yst = analysis.residual

    # Diagnostic logging for synthesis output
    yh_rms = np.sqrt(np.mean(yh**2)) if len(yh) > 0 else 0
    yst_rms = np.sqrt(np.mean(yst**2)) if len(yst) > 0 else 0
    print(f"[SMS] Synthesis RMS — harmonics: {yh_rms:.6f}, residual: {yst_rms:.6f}, "
          f"residual_level: {residual_level}")

    # Mix: apply residual level and combine
    min_len = min(len(yh), len(yst))
    y_out = yh[:min_len] + residual_level * yst[:min_len]

    print(f"[SMS] Resynthesis complete: {len(y_out)} samples @ {analysis.internal_sr}Hz")

    # Resample back to original sample rate
    y_out = _resample(y_out.astype(np.float32), analysis.internal_sr, analysis.original_sr)

    # Match original audio length
    if len(y_out) > audio_length:
        y_out = y_out[:audio_length]
    elif len(y_out) < audio_length:
        y_out = np.pad(y_out, (0, audio_length - len(y_out)))

    return y_out.astype(np.float32)


def run_sms_pitch_shift(audio_mono, sr, pitch_map, output_path, sms_params=None,
                        cached_analysis=None):
    """
    Drop-in replacement for run_rubberband() for pitch shifting.

    Args:
        audio_mono: Mono audio numpy array
        sr: Sample rate
        pitch_map: List of (frame, semitones) pairs
        output_path: Path to write output WAV
        sms_params: Optional SMS parameter dict
        cached_analysis: Optional pre-computed SMSAnalysis to skip analysis step

    Returns:
        (success: bool, message: str, analysis: SMSAnalysis)
        The analysis is returned for caching.
    """
    try:
        if cached_analysis is not None:
            analysis = cached_analysis
            print("[SMS] Using cached analysis")
        else:
            analysis = sms_analyze(audio_mono, sr, sms_params)

        y_out = sms_pitch_shift(analysis, pitch_map, sr, len(audio_mono), sms_params)

        sf.write(str(output_path), y_out, int(sr))
        return True, "OK", analysis

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"SMS processing failed: {e}", None
