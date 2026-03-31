#!/usr/bin/env python3
"""
A/B test for FD-PSOLA: isolate the source of dullness.

Processes the same synthetic signal with different settings and compares
the spectral energy in frequency bands to pinpoint what's causing the loss.

Tests:
  A. Full pipeline (baseline - the current code)
  B. No formant preservation (is envelope separation the problem?)
  C. Formant preservation but ratio=1.0001 (near-identity roundtrip)
  D. Full pipeline with overlap_factor=2 (less overlap = less interference?)
  E. Full pipeline with overlap_factor=1 (minimal overlap)

Usage:
    python test_fd_psola_ab.py [shift_semitones]
"""

import sys
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import soundfile as sf

from fd_psola_engine import (
    _place_pitch_marks, _make_window, _extract_frame,
    _estimate_envelope_cepstral, _shift_fine_structure,
    run_fd_psola_pitch_shift,
)

DIAG_DIR = '/tmp/vocal_editor'
os.makedirs(DIAG_DIR, exist_ok=True)


def make_synthetic_voice(sr=44100, duration=1.0, f0=200.0):
    t = np.arange(int(sr * duration)) / sr
    n_samples = len(t)
    formants = [(800, 80), (1200, 100), (2500, 150)]
    signal = np.zeros(n_samples)
    n_harmonics = int(sr / 2 / f0)
    for k in range(1, n_harmonics + 1):
        freq = k * f0
        amp = 0.0
        for f_center, f_bw in formants:
            amp += 1.0 / (1.0 + ((freq - f_center) / f_bw) ** 2)
        amp = max(amp, 0.01)
        signal += amp * np.sin(2 * np.pi * freq * t + np.random.uniform(0, 2*np.pi))
    noise = np.random.randn(n_samples) * 0.02
    signal += noise
    signal /= np.max(np.abs(signal)) + 1e-12
    f0_times = np.linspace(0, duration, int(duration * 100))
    f0_freqs = np.full_like(f0_times, f0)
    return signal, sr, f0_times, f0_freqs


def band_energy(audio, sr, bands):
    """Compute energy in frequency bands."""
    spec = np.abs(np.fft.rfft(audio))
    freqs = np.arange(len(spec)) * sr / (2 * (len(spec) - 1))
    result = {}
    for name, (lo, hi) in bands.items():
        mask = (freqs >= lo) & (freqs < hi)
        result[name] = 20 * np.log10(np.sqrt(np.mean(spec[mask]**2)) + 1e-12)
    return result


def run_test(audio, sr, f0_times, f0_freqs, shift_st, label, **param_overrides):
    """Run FD-PSOLA with given params and return output audio."""
    params = {
        'fft_size': 2048,
        'envelope_order': 30,
        'formant_preservation': True,
        'formant_method': 'cepstral',
        'phase_mode': 'pitch_sync',
        'overlap_factor': 4,
    }
    params.update(param_overrides)

    pitch_map = [(i, shift_st) for i in range(0, len(audio), sr // 200)]
    output_path = os.path.join(DIAG_DIR, f'ab_{label}.wav')

    success, msg = run_fd_psola_pitch_shift(
        audio, sr, pitch_map, output_path,
        fd_psola_params=params,
        original_times=f0_times,
        original_frequencies=f0_freqs,
    )

    if success:
        out, _ = sf.read(output_path)
        return out
    else:
        print(f'  FAILED: {msg}')
        return None


def main():
    shift_st = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    f0 = 200.0

    print(f'=== FD-PSOLA A/B Test: shift={shift_st:+.1f} st ===\n')

    audio, sr, f0_times, f0_freqs = make_synthetic_voice(sr=44100, f0=f0)

    bands = {
        'sub_200': (0, 200),
        '200_500': (200, 500),
        '500_1k': (500, 1000),
        '1k_2k': (1000, 2000),
        '2k_4k': (2000, 4000),
        '4k_8k': (4000, 8000),
        '8k_nyq': (8000, 22050),
    }

    tests = {
        'A_full': {'label': 'A: Full pipeline (baseline)', 'params': {}},
        'B_no_formant': {'label': 'B: No formant preservation', 'params': {'formant_preservation': False}},
        'C_identity': {'label': f'C: Near-identity (0.001 st)', 'params': {}, 'shift_override': 0.001},
        'D_overlap2': {'label': 'D: overlap_factor=2', 'params': {'overlap_factor': 2}},
        'E_overlap1': {'label': 'E: overlap_factor=1', 'params': {'overlap_factor': 1}},
        'F_lpc': {'label': 'F: LPC envelope', 'params': {'formant_method': 'lpc'}},
        'G_phase_lock': {'label': 'G: Phase lock mode', 'params': {'phase_mode': 'phase_lock'}},
    }

    orig_energy = band_energy(audio, sr, bands)

    results = {}
    for key, test in tests.items():
        shift = test.get('shift_override', shift_st)
        out = run_test(audio, sr, f0_times, f0_freqs, shift, key, **test['params'])
        if out is not None:
            results[key] = {
                'audio': out,
                'energy': band_energy(out, sr, bands),
                'label': test['label'],
            }

    # --- Print energy comparison table ---
    print(f'\n{"Band":<12}  {"Original":>10}', end='')
    for key in results:
        print(f'  {key:>12}', end='')
    print()

    print(f'{"":12}  {"(dB)":>10}', end='')
    for key in results:
        print(f'  {"Δ dB":>12}', end='')
    print()

    print('-' * (14 + 14 * (1 + len(results))))

    for band in bands:
        print(f'{band:<12}  {orig_energy[band]:>10.1f}', end='')
        for key in results:
            delta = results[key]['energy'][band] - orig_energy[band]
            marker = ' ⚠' if delta < -3 else ''
            print(f'  {delta:>+10.1f}{marker}', end='')
        print()

    # Total RMS
    orig_rms = 20 * np.log10(np.sqrt(np.mean(audio**2)) + 1e-12)
    print(f'\n{"Total RMS":<12}  {orig_rms:>10.1f}', end='')
    for key in results:
        out_rms = 20 * np.log10(np.sqrt(np.mean(results[key]['audio']**2)) + 1e-12)
        delta = out_rms - orig_rms
        print(f'  {delta:>+10.1f}', end='')
    print()

    # --- Plot spectral comparison ---
    chunk = 8192
    start = len(audio) // 2
    freqs_plot = np.arange(chunk // 2 + 1) * sr / chunk
    orig_spec = 20 * np.log10(np.abs(np.fft.rfft(audio[start:start+chunk])) + 1e-12)

    fig, axes = plt.subplots(len(results), 1, figsize=(14, 3 * len(results)), sharex=True)
    if len(results) == 1:
        axes = [axes]

    for ax, (key, res) in zip(axes, results.items()):
        out_spec = 20 * np.log10(np.abs(np.fft.rfft(res['audio'][start:start+chunk])) + 1e-12)
        ax.plot(freqs_plot, orig_spec, 'b-', alpha=0.5, linewidth=0.5, label='Original')
        ax.plot(freqs_plot, out_spec, 'r-', alpha=0.7, linewidth=0.5, label='Processed')
        # Spectral difference (smoothed)
        diff = out_spec - orig_spec
        win = 50
        if len(diff) > win:
            smooth_diff = np.convolve(diff, np.ones(win)/win, mode='same')
            ax2 = ax.twinx()
            ax2.plot(freqs_plot, smooth_diff, 'g-', alpha=0.8, linewidth=1.5, label='Δ (smoothed)')
            ax2.set_ylabel('Δ dB', color='g')
            ax2.set_ylim(-30, 10)
            ax2.axhline(0, color='g', alpha=0.3, linewidth=0.5)
        ax.set_xlim(0, 8000)
        ax.set_ylim(-40, 60)
        ax.set_ylabel('dB')
        ax.set_title(res['label'])
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel('Frequency (Hz)')
    plt.tight_layout()
    path = os.path.join(DIAG_DIR, f'ab_comparison_shift{shift_st:+.1f}.png')
    plt.savefig(path, dpi=100)
    plt.close()
    print(f'\nPlot saved: {path}')
    print(f'WAV files saved in {DIAG_DIR}/')


if __name__ == '__main__':
    main()
