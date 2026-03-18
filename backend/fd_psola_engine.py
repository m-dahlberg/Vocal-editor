"""
FD-PSOLA Engine -- Frequency-Domain PSOLA pitch shifting.

Pitch-synchronous analysis/synthesis with spectral envelope separation
for formant-preserving pitch modification.  Uses NumPy/SciPy only.

Algorithm outline:
  1. Place pitch marks at pitch-synchronous intervals using Parselmouth F0.
  2. Extract windowed frames (2×T0) centred on each mark; zero-pad to fft_size.
  3. FFT each frame; separate spectral envelope from fine structure.
  4. Shift the fine structure by the required frequency ratio.
  5. Optionally re-apply the *original* envelope (formant preservation).
  6. IFFT; overlap-add at output pitch marks spaced by target period.
"""

import numpy as np
import soundfile as sf
from scipy.signal import get_window, lfilter, lpc as _scipy_lpc


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _place_pitch_marks(audio_length, sr, original_times, original_frequencies,
                       min_pitch, max_pitch):
    """Return an array of sample-index pitch marks and per-mark local period."""
    orig_t = np.asarray(original_times, dtype=np.float64)
    orig_f = np.asarray(original_frequencies, dtype=np.float64)

    # Build a continuous F0 curve (0 for unvoiced)
    voiced = np.isfinite(orig_f) & (orig_f > 0)
    f0_cont = np.where(voiced, orig_f, 0.0)

    marks = []
    periods = []
    is_voiced_list = []

    default_period = sr / min_pitch  # fallback for unvoiced

    pos = 0.0
    while pos < audio_length:
        t = pos / sr
        # Interpolate F0 at this position
        f0 = float(np.interp(t, orig_t, f0_cont))
        if f0 > 0:
            period = sr / np.clip(f0, min_pitch, max_pitch)
            v = True
        else:
            period = default_period
            v = False

        marks.append(int(round(pos)))
        periods.append(period)
        is_voiced_list.append(v)
        pos += period

    return (np.array(marks, dtype=np.int64),
            np.array(periods, dtype=np.float64),
            np.array(is_voiced_list, dtype=bool))


def _make_window(window_type, length):
    """Create a window array of *length* samples."""
    if window_type == 'kaiser':
        return get_window(('kaiser', 8.0), length, fftbins=False)
    return get_window(window_type, length, fftbins=False)


def _extract_frame(audio, centre, half_len, fft_size, window):
    """Extract a single windowed frame, zero-padded to *fft_size*."""
    n = len(audio)
    start = centre - half_len
    end = centre + half_len

    # Gather samples (zero outside bounds)
    frame = np.zeros(end - start, dtype=np.float64)
    src_start = max(0, start)
    src_end = min(n, end)
    dst_start = src_start - start
    dst_end = dst_start + (src_end - src_start)
    frame[dst_start:dst_end] = audio[src_start:src_end]

    # Apply window (resize if lengths differ slightly)
    if len(window) != len(frame):
        w = _make_window('hanning', len(frame))
    else:
        w = window
    frame *= w

    # Zero-pad to fft_size
    padded = np.zeros(fft_size, dtype=np.float64)
    offset = (fft_size - len(frame)) // 2
    padded[offset:offset + len(frame)] = frame
    return padded


def _estimate_envelope_cepstral(log_mag, order):
    """Spectral envelope via cepstral liftering."""
    cepstrum = np.fft.irfft(log_mag)
    # Low-time lifter
    lifter = np.zeros_like(cepstrum)
    lifter[:order + 1] = 1.0
    if len(lifter) > order:
        lifter[-order:] = 1.0  # symmetric part
    envelope = np.fft.rfft(cepstrum * lifter).real
    return envelope


def _estimate_envelope_lpc(frame_td, sr, order, n_fft):
    """Spectral envelope via LPC."""
    # Ensure frame has enough energy for LPC
    energy = np.sum(frame_td ** 2)
    if energy < 1e-12 or len(frame_td) <= order:
        return np.zeros(n_fft // 2 + 1)

    try:
        a = _scipy_lpc(frame_td, order)
    except Exception:
        return np.zeros(n_fft // 2 + 1)

    # Frequency response of the all-pole model
    w = np.linspace(0, np.pi, n_fft // 2 + 1)
    # H(z) = 1 / A(z)
    z = np.exp(-1j * w[np.newaxis, :] * np.arange(len(a))[:, np.newaxis])
    A = np.sum(a[:, np.newaxis] * z, axis=0)
    mag = np.abs(1.0 / (A + 1e-12))
    return 20.0 * np.log10(mag + 1e-12)


def _shift_fine_structure(mag_spectrum, ratio):
    """Resample magnitude spectrum along frequency axis by 1/ratio."""
    n = len(mag_spectrum)
    old_bins = np.arange(n, dtype=np.float64)
    new_bins = old_bins / ratio  # stretch/compress
    shifted = np.interp(new_bins, old_bins, mag_spectrum, left=0.0, right=0.0)
    return shifted


def _phase_lock(phase, magnitude):
    """Phase-locking: propagate peak phases to neighbouring bins."""
    n = len(magnitude)
    locked = phase.copy()
    # Find local peaks
    peaks = np.zeros(n, dtype=bool)
    peaks[1:-1] = (magnitude[1:-1] > magnitude[:-2]) & (magnitude[1:-1] > magnitude[2:])
    peaks[0] = magnitude[0] > magnitude[1] if n > 1 else True

    # For each bin, find closest peak and inherit its phase offset
    peak_idx = np.where(peaks)[0]
    if len(peak_idx) == 0:
        return locked

    for i in range(n):
        closest = peak_idx[np.argmin(np.abs(peak_idx - i))]
        locked[i] = phase[closest] + (i - closest) * phase[closest] / (closest + 1e-6)
    return locked


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def run_fd_psola_pitch_shift(audio_mono, sr, pitch_map, output_path,
                              fd_psola_params=None,
                              original_times=None, original_frequencies=None):
    """
    FD-PSOLA pitch shifting.

    Args:
        audio_mono: Mono audio numpy array
        sr: Sample rate
        pitch_map: List of (frame, semitones) pairs — piecewise-linear shift
        output_path: Path to write output WAV
        fd_psola_params: Dict of engine parameters
        original_times: Parselmouth F0 time points
        original_frequencies: Parselmouth F0 values (Hz, NaN for unvoiced)

    Returns:
        (success: bool, message: str)
    """
    try:
        if original_times is None or original_frequencies is None:
            return False, "FD-PSOLA engine requires original Parselmouth F0 data"

        params = fd_psola_params or {}
        fft_size = int(params.get('fft_size', 2048))
        window_type = str(params.get('window_type', 'hanning'))
        formant_preservation = bool(params.get('formant_preservation', True))
        formant_method = str(params.get('formant_method', 'cepstral'))
        envelope_order = int(params.get('envelope_order', 30))
        overlap_factor = int(params.get('overlap_factor', 4))
        phase_mode = str(params.get('phase_mode', 'pitch_sync'))
        min_pitch = float(params.get('min_pitch', 75))
        max_pitch = float(params.get('max_pitch', 600))

        audio = np.asarray(audio_mono, dtype=np.float64)
        audio_length = len(audio)

        # ---- 1. Build semitone-shift envelope from pitch_map ----
        pm_frames = np.array([p[0] for p in pitch_map], dtype=np.float64)
        pm_shifts = np.array([p[1] for p in pitch_map], dtype=np.float64)
        pm_times = pm_frames / sr

        # ---- 2. Place pitch marks ----
        marks, periods, is_voiced = _place_pitch_marks(
            audio_length, sr, original_times, original_frequencies,
            min_pitch, max_pitch,
        )
        n_frames = len(marks)
        if n_frames == 0:
            sf.write(str(output_path), audio_mono.astype(np.float32), int(sr))
            return True, "OK (no pitch marks)"

        # ---- 3. Process each frame ----
        output = np.zeros(audio_length + fft_size, dtype=np.float64)
        win_sum = np.zeros(audio_length + fft_size, dtype=np.float64)

        n_rfft = fft_size // 2 + 1
        synthesis_window = _make_window(window_type, fft_size)

        out_pos = 0.0  # running output position in samples

        for i in range(n_frames):
            mark = marks[i]
            period = periods[i]
            voiced = is_voiced[i]

            # Frame time for pitch_map interpolation
            frame_time = mark / sr
            shift_semitones = float(np.interp(frame_time, pm_times, pm_shifts))
            ratio = 2.0 ** (shift_semitones / 12.0)

            # Half-length: use overlap_factor periods for wider frames
            half_len = int(round(period * overlap_factor / 2))
            half_len = max(half_len, 64)  # minimum frame size

            # Create analysis window for this frame size
            frame_len = 2 * half_len
            analysis_window = _make_window(window_type, frame_len)

            # Extract and window the frame
            frame = _extract_frame(audio, mark, half_len, fft_size, analysis_window)

            if not voiced or abs(shift_semitones) < 0.001:
                # Unvoiced or no shift: pass through (just OLA)
                out_mark = int(round(out_pos))
                if out_mark + fft_size <= len(output):
                    output[out_mark:out_mark + fft_size] += frame * synthesis_window
                    win_sum[out_mark:out_mark + fft_size] += synthesis_window ** 2
                if voiced:
                    out_pos += period / ratio
                else:
                    out_pos += period
                continue

            # ---- FFT ----
            spectrum = np.fft.rfft(frame)
            magnitude = np.abs(spectrum)
            phase = np.angle(spectrum)
            log_mag = 20.0 * np.log10(magnitude + 1e-12)

            # ---- Spectral envelope ----
            if formant_preservation:
                if formant_method == 'lpc':
                    envelope = _estimate_envelope_lpc(frame, sr, envelope_order, fft_size)
                else:
                    envelope = _estimate_envelope_cepstral(log_mag, envelope_order)

                # Fine structure = full spectrum minus envelope
                fine_structure = log_mag - envelope
            else:
                fine_structure = log_mag
                envelope = None

            # ---- Shift fine structure ----
            shifted_fine = _shift_fine_structure(fine_structure, ratio)

            # ---- Reconstruct magnitude ----
            if formant_preservation and envelope is not None:
                new_log_mag = envelope + shifted_fine
            else:
                new_log_mag = shifted_fine

            new_mag = 10.0 ** (new_log_mag / 20.0)

            # ---- Phase handling ----
            if phase_mode == 'phase_lock':
                new_phase = _phase_lock(phase * ratio, new_mag)
            else:
                # pitch_sync: scale phase by ratio
                new_phase = phase * ratio

            # ---- IFFT ----
            new_spectrum = new_mag * np.exp(1j * new_phase)
            new_frame = np.fft.irfft(new_spectrum, n=fft_size)

            # ---- Place at output position ----
            out_mark = int(round(out_pos))
            if out_mark + fft_size <= len(output):
                output[out_mark:out_mark + fft_size] += new_frame * synthesis_window
                win_sum[out_mark:out_mark + fft_size] += synthesis_window ** 2

            # Advance output by target period
            out_pos += period / ratio

        # ---- 4. Normalise by overlap-add window sum ----
        nonzero = win_sum > 1e-8
        output[nonzero] /= win_sum[nonzero]

        # Trim to original length
        y_out = output[:audio_length]

        # Fade edges to avoid clicks
        fade_len = min(256, audio_length // 4)
        if fade_len > 0:
            fade_in = np.linspace(0.0, 1.0, fade_len)
            fade_out = np.linspace(1.0, 0.0, fade_len)
            y_out[:fade_len] *= fade_in
            y_out[-fade_len:] *= fade_out

        sf.write(str(output_path), y_out.astype(np.float32), int(sr))
        print(f"[FD-PSOLA] Processed {n_frames} frames, output {audio_length} samples")
        return True, "OK"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"FD-PSOLA processing failed: {e}"
