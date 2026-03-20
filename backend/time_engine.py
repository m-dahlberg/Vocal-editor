"""
Time Engine - Time map generation and Rubberband time stretching.

Rubberband's --timemap (-M) format:
  Each line: source_frame target_frame
  These are keyframe pairs that pin a source audio frame to a target
  output frame. Rubberband stretches/compresses between them.
  Requires an overall duration flag (-D) to set total output length.
"""

import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from audio_engine import (
    get_audio_mono, _build_rubberband_cmd,
    generate_pitch_map, DEFAULT_GAP_THRESHOLD_MS, DEFAULT_SMOOTH_CURVE,
)


def generate_time_map(clusters, time_edits, sr, audio_length):
    """
    Build Rubberband --timemap from time edits.

    Format: list of (source_frame, target_frame) pairs.
    Source frames reference the original audio.
    Target frames reference where that audio should land in the output.

    Anchor strategy ensures gaps absorb time changes before notes:
      - For each edited cluster, add keyframes at its start/end
      - For each UNEDITED neighbor, add identity anchors at BOTH its
        start and end, so Rubberband keeps it unchanged
      - The gap between the edited cluster and the unedited neighbor
        will absorb all the time change
    """
    if not time_edits:
        return []

    # Build a lookup: cluster_idx -> edit
    edit_map = {}
    for edit in time_edits:
        edit_map[edit['cluster_idx']] = edit

    # Collect all keyframe pairs
    keyframes = set()
    keyframes.add((0, 0))

    for idx in sorted(edit_map.keys()):
        if idx >= len(clusters):
            continue

        edit = edit_map[idx]
        cluster = clusters[idx]

        src_start = int(cluster['start_time'] * sr)
        src_end = int(cluster['end_time'] * sr)
        tgt_start = int(edit['new_start'] * sr)
        tgt_end = int(edit['new_end'] * sr)

        # Edited cluster keyframes
        keyframes.add((src_start, tgt_start))
        keyframes.add((src_end, tgt_end))

        # Previous neighbor: pin both start AND end so it stays unchanged.
        # The gap between prev.end and this cluster.start absorbs the change.
        if idx > 0 and idx - 1 not in edit_map:
            prev = clusters[idx - 1]
            prev_start = int(prev['start_time'] * sr)
            prev_end = int(prev['end_time'] * sr)
            keyframes.add((prev_start, prev_start))
            keyframes.add((prev_end, prev_end))
        elif idx == 0:
            pass  # start of file already anchored

        # Next neighbor: pin both start AND end so it stays unchanged.
        # The gap between this cluster.end and next.start absorbs the change.
        if idx < len(clusters) - 1 and idx + 1 not in edit_map:
            nxt = clusters[idx + 1]
            nxt_start = int(nxt['start_time'] * sr)
            nxt_end = int(nxt['end_time'] * sr)
            keyframes.add((nxt_start, nxt_start))
            keyframes.add((nxt_end, nxt_end))

    # End of file
    keyframes.add((audio_length - 1, audio_length - 1))

    # Sort by source frame
    result = sorted(keyframes, key=lambda x: x[0])

    return result


def run_rubberband_with_timemap(input_path, output_path, time_map_entries, duration_s, rb_params=None):
    """Run Rubberband with --timemap flag."""
    if rb_params is None:
        rb_params = {}

    work_dir = os.path.join(tempfile.gettempdir(), 'vocal_editor')
    os.makedirs(work_dir, exist_ok=True)
    time_map_file = os.path.join(work_dir, 'last_time_map.txt')

    with open(time_map_file, 'w') as f:
        for src_frame, tgt_frame in time_map_entries:
            f.write(f"{src_frame} {tgt_frame}\n")

    print(f"[DEBUG] time_map saved to: {time_map_file}")
    print(f"[DEBUG] time_map ({len(time_map_entries)} entries):")
    for src, tgt in time_map_entries[:20]:
        print(f"  {src} {tgt}")
    if len(time_map_entries) > 20:
        print(f"  ... ({len(time_map_entries) - 20} more entries)")

    cmd = _build_rubberband_cmd(rb_params)
    # --timemap requires an overall duration/time flag
    cmd.extend(['-D', str(duration_s)])
    cmd.extend(['--timemap', time_map_file, input_path, str(output_path)])

    print(f"[DEBUG] rubberband cmd: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] rubberband stderr: {result.stderr}")
        return False, result.stderr

    return True, "OK"


def run_rubberband_combined(input_path, output_path, pitch_map_entries, time_map_entries, duration_s, rb_params=None):
    """Run Rubberband with both --pitchmap and --timemap in a single invocation."""
    if rb_params is None:
        rb_params = {}

    work_dir = os.path.join(tempfile.gettempdir(), 'vocal_editor')
    os.makedirs(work_dir, exist_ok=True)

    pitch_map_file = os.path.join(work_dir, 'combined_pitch_map.txt')
    time_map_file = os.path.join(work_dir, 'combined_time_map.txt')

    with open(pitch_map_file, 'w') as f:
        for frame, semitones in pitch_map_entries:
            f.write(f"{frame} {semitones}\n")

    with open(time_map_file, 'w') as f:
        for src_frame, tgt_frame in time_map_entries:
            f.write(f"{src_frame} {tgt_frame}\n")

    print(f"[DEBUG] combined pitch_map ({len(pitch_map_entries)} entries), "
          f"time_map ({len(time_map_entries)} entries)")

    cmd = _build_rubberband_cmd(rb_params)
    cmd.extend(['-D', str(duration_s)])
    cmd.extend([
        '--pitchmap', pitch_map_file,
        '--timemap', time_map_file,
        input_path, str(output_path),
    ])

    print(f"[DEBUG] rubberband cmd: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] rubberband stderr: {result.stderr}")
        return False, result.stderr

    return True, "OK"


def process_time_stretch(audio, sr, clusters, time_edits, rb_params, output_path):
    """Full pipeline: generate time map -> run Rubberband -> write output."""
    audio_mono = get_audio_mono(audio)
    audio_length = len(audio_mono)
    duration_s = audio_length / sr

    time_map = generate_time_map(clusters, time_edits, sr, audio_length)

    if not time_map:
        # No edits, just copy original
        sf.write(output_path, audio_mono, int(sr))
        return True, "OK"

    # Write input to temp file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        temp_input = f.name
    sf.write(temp_input, audio_mono, int(sr))

    try:
        success, msg = run_rubberband_with_timemap(
            temp_input, output_path, time_map, duration_s, rb_params
        )
        return success, msg
    finally:
        if os.path.exists(temp_input):
            os.remove(temp_input)


def process_combined(audio, sr, clusters, params, time_edits, output_path):
    """
    Process audio with both pitch corrections and time stretching.

    Rubberband's --pitchmap implies realtime mode (-R), which conflicts with
    --timemap (time stretching is unreliable in realtime mode).  Therefore,
    when both are needed we run two separate passes:
      1. Pitch correction (--pitchmap)
      2. Time stretching on the pitch-corrected result (--timemap)
    """
    from audio_engine import run_rubberband

    audio_mono = get_audio_mono(audio)
    audio_length = len(audio_mono)
    duration_s = audio_length / sr

    # Generate pitch map from clusters
    gap_threshold = params.get('gap_threshold_ms', DEFAULT_GAP_THRESHOLD_MS)
    smooth_curve = params.get('smooth_curve', DEFAULT_SMOOTH_CURVE)
    pitch_map = generate_pitch_map(clusters, sr, audio_length, gap_threshold, smooth_curve)

    # Generate time map from time edits
    time_map = generate_time_map(clusters, time_edits, sr, audio_length)

    rb_params = params.get('rb', {})

    has_pitch = any(
        c['pitch_shift_semitones'] != 0 or c.get('smoothing_percent', 0) != 0
        for c in clusters
    )
    has_time = len(time_map) > 0

    # Respect enable_pitchmap / enable_timemap flags from rubberband params
    if not rb_params.get('enable_pitchmap', True):
        has_pitch = False
    if not rb_params.get('enable_timemap', True):
        has_time = False

    # Write input to temp file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        temp_input = f.name
    sf.write(temp_input, audio_mono, int(sr))

    try:
        if has_pitch and has_time:
            # Two-pass: pitch first, then time stretch on the result.
            # This avoids the conflict between --pitchmap (realtime mode)
            # and --timemap in a single Rubberband invocation.
            # Exception: FD-PSOLA handles both in a single pass.
            engine = params.get("pitch_engine", "rubberband")

            if engine == "fd_psola":
                # Single-pass FD-PSOLA: pitch + time simultaneously
                from fd_psola_engine import run_fd_psola_time_stretch
                fd_psola_params = params.get("fd_psola", {}).copy()
                f0_data = fd_psola_params.pop("_parselmouth_f0", None)
                success, msg = run_fd_psola_time_stretch(
                    audio_mono, sr, time_map, output_path,
                    pitch_map=pitch_map,
                    fd_psola_params=fd_psola_params,
                    original_times=f0_data["times"] if f0_data else None,
                    original_frequencies=f0_data["frequencies"] if f0_data else None,
                )
                return success, msg

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_pitched = f.name
            try:
                if engine == "sms":
                    from sms_engine import run_sms_pitch_shift
                    sms_params = params.get("sms", {})
                    sms_cache = params.get("_sms_cache", None)
                    success, msg, analysis = run_sms_pitch_shift(
                        audio_mono, sr, pitch_map, temp_pitched, sms_params,
                        cached_analysis=sms_cache,
                    )
                    if analysis and "_sms_cache_ref" in params:
                        params["_sms_cache_ref"][0] = analysis
                elif engine == "psola":
                    from psola_engine import run_psola_pitch_shift
                    psola_params = params.get("psola", {})
                    f0_data = psola_params.pop("_parselmouth_f0", None)
                    success, msg = run_psola_pitch_shift(
                        audio_mono, sr, pitch_map, temp_pitched, psola_params,
                        original_times=f0_data["times"] if f0_data else None,
                        original_frequencies=f0_data["frequencies"] if f0_data else None,
                    )
                else:
                    success, msg = run_rubberband(
                        audio_mono, sr, pitch_map, temp_pitched, rb_params
                    )
                if not success:
                    return success, msg

                success, msg = run_rubberband_with_timemap(
                    temp_pitched, output_path, time_map, duration_s, rb_params
                )
                return success, msg
            finally:
                if os.path.exists(temp_pitched):
                    os.remove(temp_pitched)
        elif has_time:
            engine = params.get("pitch_engine", "rubberband")
            if engine == "fd_psola":
                # FD-PSOLA time-only stretching
                from fd_psola_engine import run_fd_psola_time_stretch
                fd_psola_params = params.get("fd_psola", {}).copy()
                f0_data = fd_psola_params.pop("_parselmouth_f0", None)
                success, msg = run_fd_psola_time_stretch(
                    audio_mono, sr, time_map, output_path,
                    pitch_map=None,
                    fd_psola_params=fd_psola_params,
                    original_times=f0_data["times"] if f0_data else None,
                    original_frequencies=f0_data["frequencies"] if f0_data else None,
                )
            else:
                success, msg = run_rubberband_with_timemap(
                    temp_input, output_path, time_map, duration_s, rb_params
                )
        elif has_pitch:
            engine = params.get("pitch_engine", "rubberband")
            if engine == "sms":
                from sms_engine import run_sms_pitch_shift
                sms_params = params.get("sms", {})
                sms_cache = params.get("_sms_cache", None)
                success, msg, analysis = run_sms_pitch_shift(
                    audio_mono, sr, pitch_map, output_path, sms_params,
                    cached_analysis=sms_cache,
                )
                if analysis and "_sms_cache_ref" in params:
                    params["_sms_cache_ref"][0] = analysis
            elif engine == "psola":
                from psola_engine import run_psola_pitch_shift
                psola_params = params.get("psola", {})
                f0_data = psola_params.pop("_parselmouth_f0", None)
                success, msg = run_psola_pitch_shift(
                    audio_mono, sr, pitch_map, output_path, psola_params,
                    original_times=f0_data["times"] if f0_data else None,
                    original_frequencies=f0_data["frequencies"] if f0_data else None,
                )
            elif engine == "fd_psola":
                from fd_psola_engine import run_fd_psola_pitch_shift
                fd_psola_params = params.get("fd_psola", {}).copy()
                f0_data = fd_psola_params.pop("_parselmouth_f0", None)
                success, msg = run_fd_psola_pitch_shift(
                    audio_mono, sr, pitch_map, output_path, fd_psola_params,
                    original_times=f0_data["times"] if f0_data else None,
                    original_frequencies=f0_data["frequencies"] if f0_data else None,
                )
            else:
                success, msg = run_rubberband(
                    audio_mono, sr, pitch_map, output_path, rb_params
                )
        else:
            sf.write(output_path, audio_mono, int(sr))
            success, msg = True, "OK"

        return success, msg
    finally:
        if os.path.exists(temp_input):
            os.remove(temp_input)
