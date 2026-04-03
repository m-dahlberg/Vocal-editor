"""
Denoise engine — spectral gating noise reduction using noisereduce.
"""

import numpy as np
import noisereduce as nr
from scipy.signal import stft

DEFAULT_DENOISE_PARAMS = {
    'stationary': True,
    'prop_decrease': 1.0,
    'time_constant_s': 2.0,
    'freq_mask_smooth_hz': 500,
    'time_mask_smooth_ms': 50,
    'n_fft': 1024,
}


def get_default_denoise_params():
    return dict(DEFAULT_DENOISE_PARAMS)


def apply_denoise(audio, sr, params, noise_clip=None):
    """Apply noise reduction using noisereduce library.

    Args:
        audio: 1D numpy array of audio samples
        sr: sample rate
        params: dict of denoise parameters
        noise_clip: optional 1D numpy array of noise-only audio for profile

    Returns:
        denoised audio as 1D numpy array
    """
    kwargs = {
        'y': audio,
        'sr': sr,
        'stationary': params.get('stationary', True),
        'prop_decrease': params.get('prop_decrease', 1.0),
        'freq_mask_smooth_hz': params.get('freq_mask_smooth_hz', 500),
        'time_mask_smooth_ms': params.get('time_mask_smooth_ms', 50),
        'n_fft': params.get('n_fft', 1024),
    }

    if not params.get('stationary', True):
        kwargs['time_constant_s'] = params.get('time_constant_s', 2.0)

    if noise_clip is not None and len(noise_clip) > 0:
        kwargs['y_noise'] = noise_clip

    return nr.reduce_noise(**kwargs)


def compute_spectrograms(audio_before, audio_after, sr, n_fft=1024):
    """Compute magnitude spectrograms for before/after comparison.

    Returns decimated spectrograms suitable for JSON serialization.
    """
    # Use a larger FFT for visualization to get better frequency resolution.
    # The denoiser's n_fft is for processing; visualization benefits from 4096+.
    vis_nfft = max(n_fft, 4096)
    nperseg = vis_nfft
    noverlap = nperseg * 3 // 4

    # Use STFT for proper dBFS values matching Audacity's spectrogram.
    # boundary=None avoids zero-padding that suppresses the start/end of the file.
    f_b, t_b, Zxx_b = stft(audio_before, fs=sr, nperseg=nperseg,
                            noverlap=noverlap, window='hann', boundary=None)
    f_a, t_a, Zxx_a = stft(audio_after, fs=sr, nperseg=nperseg,
                            noverlap=noverlap, window='hann', boundary=None)

    # Magnitude, x2 to compensate for one-sided spectrum → 0 dBFS for full-scale sine
    mag_b = np.abs(Zxx_b) * 2
    mag_a = np.abs(Zxx_a) * 2

    # Convert to dBFS — clamp floor at -160 dB
    Sxx_b_db = 20 * np.log10(np.maximum(mag_b, 1e-8))
    Sxx_a_db = 20 * np.log10(np.maximum(mag_a, 1e-8))

    # Decimate to reasonable size for JSON transfer
    max_time_bins = 4000
    max_freq_bins = 2050

    # Decimate time axis — use max pooling to preserve peaks
    if Sxx_b_db.shape[1] > max_time_bins:
        step = Sxx_b_db.shape[1] // max_time_bins
        n_out = Sxx_b_db.shape[1] // step
        Sxx_b_db = Sxx_b_db[:, :n_out * step].reshape(Sxx_b_db.shape[0], n_out, step).max(axis=2)
        Sxx_a_db = Sxx_a_db[:, :n_out * step].reshape(Sxx_a_db.shape[0], n_out, step).max(axis=2)
        # Use center time of each bin
        t_b = t_b[:n_out * step].reshape(n_out, step).mean(axis=1)

    # Decimate frequency axis — use max pooling to preserve peaks
    if Sxx_b_db.shape[0] > max_freq_bins:
        step = Sxx_b_db.shape[0] // max_freq_bins
        n_out = Sxx_b_db.shape[0] // step
        Sxx_b_db = Sxx_b_db[:n_out * step, :].reshape(n_out, step, Sxx_b_db.shape[1]).max(axis=1)
        Sxx_a_db = Sxx_a_db[:n_out * step, :].reshape(n_out, step, Sxx_a_db.shape[1]).max(axis=1)
        f_b = f_b[:n_out * step].reshape(n_out, step).mean(axis=1)

    # Round to 1 decimal to reduce JSON size
    Sxx_b_db = np.round(Sxx_b_db, 1)
    Sxx_a_db = np.round(Sxx_a_db, 1)

    return {
        'spectrogram_before': Sxx_b_db.tolist(),
        'spectrogram_after': Sxx_a_db.tolist(),
        'freq_axis': np.round(f_b, 1).tolist(),
        'time_axis': np.round(t_b, 4).tolist(),
    }
