#!/usr/bin/env python3
"""
Diagnostic script for FD-PSOLA pitch shifting.

Generates a synthetic vocal-like signal with known harmonics and formants,
runs it through the FD-PSOLA engine step-by-step, and saves diagnostic
plots showing what happens to the spectrum at each stage.

Usage:
    python test_fd_psola_diag.py [shift_semitones]

    Default shift: +2 semitones
    Output: /tmp/vocal_editor/diag_*.png
"""

import sys
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Import engine internals
from fd_psola_engine import (
    _place_pitch_marks, _make_window, _extract_frame,
    _estimate_envelope_cepstral, _estimate_envelope_lpc,
    _shift_fine_structure, _phase_lock,
    run_fd_psola_pitch_shift,
)

DIAG_DIR = '/tmp/vocal_editor'
os.makedirs(DIAG_DIR, exist_ok=True)


def make_synthetic_voice(sr=44100, duration=1.0, f0=200.0):
    """
    Create a synthetic vocal signal with known F0 and formant-like envelope.
    Harmonics at f0, 2*f0, 3*f0, ... shaped by 3 formant peaks.
    Also adds a bit of noise.
    """
    t = np.arange(int(sr * duration)) / sr
    n_samples = len(t)

    # Formant frequencies and bandwidths (typical male vowel /a/)
    formants = [(800, 80), (1200, 100), (2500, 150)]

    signal = np.zeros(n_samples)
    n_harmonics = int(sr / 2 / f0)  # up to Nyquist

    for k in range(1, n_harmonics + 1):
        freq = k * f0
        # Amplitude shaped by formant resonances
        amp = 0.0
        for f_center, f_bw in formants:
            amp += 1.0 / (1.0 + ((freq - f_center) / f_bw) ** 2)
        amp = max(amp, 0.01)  # noise floor
        # Add harmonic with some phase variation
        signal += amp * np.sin(2 * np.pi * freq * t + np.random.uniform(0, 2*np.pi))

    # Add noise (breath/aspiration)
    noise = np.random.randn(n_samples) * 0.02
    signal += noise

    # Normalize
    signal /= np.max(np.abs(signal)) + 1e-12

    # Create F0 data (Parselmouth-like)
    f0_times = np.linspace(0, duration, int(duration * 100))  # 100 Hz rate
    f0_freqs = np.full_like(f0_times, f0)

    return signal, sr, f0_times, f0_freqs


def diagnose_single_frame(audio, sr, mark, period, f0, shift_semitones,
                           fft_size=2048, envelope_order=30, frame_idx=0):
    """
    Process a single frame and save diagnostic plots.
    """
    ratio = 2.0 ** (shift_semitones / 12.0)
    overlap_factor = 4

    half_len = int(round(period * overlap_factor / 2))
    half_len = max(half_len, 64)
    half_len = min(half_len, fft_size // 2)
    frame_len = 2 * half_len

    analysis_window = _make_window('kaiser', frame_len)
    frame = _extract_frame(audio, mark, half_len, fft_size, analysis_window)

    # FFT
    spectrum = np.fft.rfft(frame)
    mag = np.abs(spectrum)
    phase = np.angle(spectrum)
    log_mag = 20.0 * np.log10(mag + 1e-12)

    freqs = np.arange(len(log_mag)) * sr / fft_size

    # Envelope estimation (cepstral)
    envelope_cep = _estimate_envelope_cepstral(log_mag, envelope_order)
    fine_structure_cep = log_mag - envelope_cep

    # Envelope estimation (LPC)
    envelope_lpc = _estimate_envelope_lpc(frame, sr, envelope_order, fft_size)
    fine_structure_lpc = log_mag - envelope_lpc

    # Shift fine structure
    shifted_fine_cep = _shift_fine_structure(fine_structure_cep, ratio)
    shifted_fine_lpc = _shift_fine_structure(fine_structure_lpc, ratio)

    # Reconstructed magnitude
    reconstructed_cep = envelope_cep + shifted_fine_cep
    reconstructed_lpc = envelope_lpc + shifted_fine_lpc

    # --- Plot 1: Spectrum vs Envelopes ---
    fig, axes = plt.subplots(3, 1, figsize=(14, 12))

    ax = axes[0]
    ax.plot(freqs, log_mag, 'b-', alpha=0.7, label='Original spectrum')
    ax.plot(freqs, envelope_cep, 'r-', linewidth=2, label=f'Cepstral envelope (order={envelope_order})')
    ax.plot(freqs, envelope_lpc, 'g-', linewidth=2, label=f'LPC envelope (order={envelope_order})')
    # Mark expected harmonics
    for k in range(1, int(sr/2/f0) + 1):
        ax.axvline(k * f0, color='gray', alpha=0.2, linewidth=0.5)
    ax.set_xlim(0, 5000)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Magnitude (dB)')
    ax.set_title(f'Frame {frame_idx}: Spectrum vs Envelopes (F0={f0:.0f} Hz)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # --- Plot 2: Fine structure before/after shift ---
    ax = axes[1]
    ax.plot(freqs, fine_structure_cep, 'b-', alpha=0.7, label='Fine structure (cepstral)')
    ax.plot(freqs, shifted_fine_cep, 'r-', alpha=0.7, label=f'Shifted fine structure (ratio={ratio:.3f})')
    ax.axhline(0, color='k', linewidth=0.5)
    # Mark original and target harmonics
    for k in range(1, int(sr/2/f0) + 1):
        ax.axvline(k * f0, color='blue', alpha=0.15, linewidth=0.5)
        ax.axvline(k * f0 * ratio, color='red', alpha=0.15, linewidth=0.5)
    ax.set_xlim(0, 3000)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Magnitude (dB)')
    ax.set_title(f'Fine Structure: Original (blue lines=orig harmonics) vs Shifted (red lines=target harmonics)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # --- Plot 3: Reconstructed spectrum ---
    ax = axes[2]
    ax.plot(freqs, log_mag, 'b-', alpha=0.5, label='Original spectrum')
    ax.plot(freqs, reconstructed_cep, 'r-', alpha=0.7, label='Reconstructed (cepstral)')
    ax.plot(freqs, envelope_cep, 'k--', alpha=0.5, label='Envelope (unchanged)')
    for k in range(1, int(sr/2/f0) + 1):
        ax.axvline(k * f0, color='blue', alpha=0.15, linewidth=0.5)
        ax.axvline(k * f0 * ratio, color='red', alpha=0.15, linewidth=0.5)
    ax.set_xlim(0, 5000)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Magnitude (dB)')
    ax.set_title(f'Reconstructed Spectrum: shift={shift_semitones:+.1f} st')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(DIAG_DIR, f'diag_frame{frame_idx}_shift{shift_semitones:+.1f}.png')
    plt.savefig(path, dpi=100)
    plt.close()
    print(f'  Saved: {path}')

    # --- Plot 4: Phase analysis ---
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))

    ax = axes[0]
    ax.plot(freqs, phase, 'b.', markersize=1, alpha=0.5, label='Original phase')
    ax.plot(freqs, phase * ratio, 'r.', markersize=1, alpha=0.5, label=f'Phase × ratio ({ratio:.3f})')
    ax.set_xlim(0, 3000)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Phase (rad)')
    ax.set_title('Phase: Original vs Scaled')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Phase coherence: difference between consecutive bins
    ax = axes[1]
    phase_diff = np.diff(phase)
    ax.plot(freqs[:-1], phase_diff, 'b.', markersize=1, alpha=0.5, label='Original phase diff')
    ax.set_xlim(0, 3000)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Phase diff (rad)')
    ax.set_title('Inter-bin Phase Difference (coherence indicator)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(DIAG_DIR, f'diag_phase_frame{frame_idx}_shift{shift_semitones:+.1f}.png')
    plt.savefig(path, dpi=100)
    plt.close()
    print(f'  Saved: {path}')

    # --- Print numeric diagnostics ---
    print(f'\n  Frame {frame_idx} diagnostics:')
    print(f'    Mark: {mark}, Period: {period:.1f} samples ({sr/period:.1f} Hz)')
    print(f'    Frame length: {frame_len}, FFT size: {fft_size}')
    print(f'    Shift: {shift_semitones:+.1f} st, Ratio: {ratio:.4f}')
    print(f'    Cepstral envelope range: {envelope_cep.min():.1f} to {envelope_cep.max():.1f} dB')
    print(f'    Fine structure range: {fine_structure_cep.min():.1f} to {fine_structure_cep.max():.1f} dB')
    print(f'    Fine structure peak-to-valley: {fine_structure_cep.max() - fine_structure_cep.min():.1f} dB')

    # Check if harmonics leak into envelope
    harmonic_bins = [int(round(k * f0 * fft_size / sr)) for k in range(1, 15)]
    mid_bins = [int(round((k + 0.5) * f0 * fft_size / sr)) for k in range(1, 14)]
    env_at_harmonics = np.mean([envelope_cep[b] for b in harmonic_bins if b < len(envelope_cep)])
    env_at_midpoints = np.mean([envelope_cep[b] for b in mid_bins if b < len(envelope_cep)])
    harmonic_leak = env_at_harmonics - env_at_midpoints
    print(f'    Envelope at harmonics vs midpoints: {harmonic_leak:+.1f} dB (>3 dB = leaking)')

    return {
        'envelope_cep': envelope_cep,
        'fine_structure_cep': fine_structure_cep,
        'harmonic_leak': harmonic_leak,
    }


def diagnose_full_pipeline(shift_semitones=2.0):
    """Run full pipeline diagnostics."""
    print(f'=== FD-PSOLA Diagnostic: shift={shift_semitones:+.1f} semitones ===\n')

    f0 = 200.0
    sr = 44100
    audio, sr, f0_times, f0_freqs = make_synthetic_voice(sr=sr, f0=f0)

    print(f'Synthetic signal: {len(audio)} samples, sr={sr}, F0={f0} Hz')
    print(f'Duration: {len(audio)/sr:.2f} s\n')

    # Place pitch marks
    marks, periods, is_voiced = _place_pitch_marks(
        len(audio), sr, f0_times, f0_freqs, 75, 600
    )
    print(f'Pitch marks: {len(marks)}, mean period: {np.mean(periods):.1f} samples')
    print(f'Expected period: {sr/f0:.1f} samples\n')

    # Diagnose individual frames at different envelope orders
    print('--- Single frame analysis (mid-signal) ---')
    mid_idx = len(marks) // 2
    mid_mark = marks[mid_idx]
    mid_period = periods[mid_idx]

    for order in [20, 30, 40, 50]:
        print(f'\n  Envelope order = {order}:')
        diag = diagnose_single_frame(
            audio, sr, mid_mark, mid_period, f0, shift_semitones,
            envelope_order=order, frame_idx=mid_idx,
        )
        # Re-save with order in filename
        # (already saved by diagnose_single_frame, just rename)

    # Run full pipeline and check output
    print('\n--- Full pipeline test ---')
    import soundfile as sf

    pitch_map = [(i, shift_semitones) for i in range(0, len(audio), sr // 200)]
    output_path = os.path.join(DIAG_DIR, f'diag_output_shift{shift_semitones:+.1f}.wav')

    success, msg = run_fd_psola_pitch_shift(
        audio, sr, pitch_map, output_path,
        fd_psola_params={
            'fft_size': 2048,
            'envelope_order': 30,
            'formant_preservation': True,
            'formant_method': 'cepstral',
            'phase_mode': 'pitch_sync',
            'overlap_factor': 4,
        },
        original_times=f0_times,
        original_frequencies=f0_freqs,
    )
    print(f'  Result: {success}, {msg}')

    if success and os.path.exists(output_path):
        out_audio, out_sr = sf.read(output_path)
        print(f'  Input length:  {len(audio)} samples')
        print(f'  Output length: {len(out_audio)} samples')
        print(f'  Length match: {len(audio) == len(out_audio)}')

        # Compare spectra of a chunk
        chunk = 4096
        start = len(audio) // 2
        orig_spec = np.abs(np.fft.rfft(audio[start:start+chunk]))
        out_spec = np.abs(np.fft.rfft(out_audio[start:start+chunk]))
        freqs = np.arange(len(orig_spec)) * sr / chunk

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(freqs, 20*np.log10(orig_spec + 1e-12), 'b-', alpha=0.7, label='Original')
        ax.plot(freqs, 20*np.log10(out_spec + 1e-12), 'r-', alpha=0.7, label='Processed')
        for k in range(1, 20):
            ax.axvline(k * f0, color='blue', alpha=0.15, linewidth=1)
            ax.axvline(k * f0 * 2**(shift_semitones/12), color='red', alpha=0.15, linewidth=1)
        ax.set_xlim(0, 5000)
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Magnitude (dB)')
        ax.set_title(f'Full Pipeline: Original vs Processed ({shift_semitones:+.1f} st)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = os.path.join(DIAG_DIR, f'diag_pipeline_shift{shift_semitones:+.1f}.png')
        plt.savefig(path, dpi=100)
        plt.close()
        print(f'  Saved: {path}')

    print(f'\nAll diagnostics saved to {DIAG_DIR}/')


if __name__ == '__main__':
    shift = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    diagnose_full_pipeline(shift)
    # Also run with a large shift
    if len(sys.argv) <= 1:
        diagnose_full_pipeline(7.0)
