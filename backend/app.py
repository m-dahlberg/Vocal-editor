"""
Vocal Editor GUI - Flask Server
"""

from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
import os
import uuid
import numpy as np
import soundfile as sf
from pathlib import Path
import tempfile
import json
import parselmouth
from parselmouth.praat import call

def save_as_wav(uploaded_file, wav_path):
    """Save an uploaded audio file as WAV, converting if necessary."""
    tmp_path = str(wav_path) + '.tmp'
    uploaded_file.save(tmp_path)
    try:
        data, samplerate = sf.read(tmp_path)
        sf.write(str(wav_path), data, samplerate)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


from audio_engine import (
    analyze_pitch, cluster_notes, parse_midi_file,
    autocorrect_midi, autocorrect_standard,
    process_full_audio, process_segment,
    clusters_to_json, get_audio_mono, hz_to_note,
    compute_avg_pitch_deviation, compute_cluster_pitch_variation,
    generate_pitch_map,
    DEFAULT_TIME_RESOLUTION_MS, DEFAULT_MIN_FREQUENCY, DEFAULT_MAX_FREQUENCY,
    DEFAULT_FREQUENCY_TOLERANCE_CENTS, DEFAULT_MIN_NOTE_DURATION_MS,
    DEFAULT_MAX_GAP_TO_BRIDGE_MS, DEFAULT_SILENCE_THRESHOLD_DB,
    DEFAULT_TRANSITION_RAMP_MS, DEFAULT_GAP_THRESHOLD_MS,
    DEFAULT_CORRECTION_STRENGTH, DEFAULT_MIDI_THRESHOLD_CENTS,
    DEFAULT_AUTOCORRECT_SMOOTHING, DEFAULT_SMOOTHING_THRESHOLD_CENTS, DEFAULT_SMOOTH_CURVE,
    DEFAULT_RUBBERBAND_COMMAND, DEFAULT_RUBBERBAND_CRISP,
    DEFAULT_RUBBERBAND_FORMANT, DEFAULT_RUBBERBAND_PITCH_HQ,
    DEFAULT_RUBBERBAND_WINDOW_LONG, DEFAULT_RUBBERBAND_SMOOTHING,
)

app = Flask(__name__)
CORS(app)
app.secret_key = 'vocal_editor_secret_key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Session storage (single user)
SESSION = {
    'audio_path': None,
    'midi_path': None,
    'audio': None,
    'sr': None,
    'times': None,
    'frequencies': None,
    'clusters': [],
    'midi_notes': [],
    'corrected_audio': None,
    'corrected_path': None,
    'params': {},
    'time_edits': [],
    'reference_path': None,
    'reference_clusters': [],
    'backing_path': None,
    'sms_analysis': None,
}

UPLOAD_DIR = Path(tempfile.gettempdir()) / 'vocal_editor'
UPLOAD_DIR.mkdir(exist_ok=True)


def get_default_params():
    return {
        'time_resolution_ms': DEFAULT_TIME_RESOLUTION_MS,
        'min_frequency': DEFAULT_MIN_FREQUENCY,
        'max_frequency': DEFAULT_MAX_FREQUENCY,
        'frequency_tolerance_cents': DEFAULT_FREQUENCY_TOLERANCE_CENTS,
        'min_note_duration_ms': DEFAULT_MIN_NOTE_DURATION_MS,
        'max_gap_to_bridge_ms': DEFAULT_MAX_GAP_TO_BRIDGE_MS,
        'silence_threshold_db': DEFAULT_SILENCE_THRESHOLD_DB,
        'transition_ramp_ms': DEFAULT_TRANSITION_RAMP_MS,
        'gap_threshold_ms': DEFAULT_GAP_THRESHOLD_MS,
        'correction_strength': DEFAULT_CORRECTION_STRENGTH,
        'midi_threshold_cents': DEFAULT_MIDI_THRESHOLD_CENTS,
        'autocorrect_smoothing': DEFAULT_AUTOCORRECT_SMOOTHING,
        'smoothing_threshold_cents': DEFAULT_SMOOTHING_THRESHOLD_CENTS,
        'smooth_curve': DEFAULT_SMOOTH_CURVE,
        'rb': {
            'command': DEFAULT_RUBBERBAND_COMMAND,
            'crisp': DEFAULT_RUBBERBAND_CRISP,
            'formant': DEFAULT_RUBBERBAND_FORMANT,
            'pitch_hq': DEFAULT_RUBBERBAND_PITCH_HQ,
            'window_long': DEFAULT_RUBBERBAND_WINDOW_LONG,
            'smoothing': DEFAULT_RUBBERBAND_SMOOTHING,
        },
        'pitch_engine': 'rubberband',
        'sms': {
            'max_harmonics': 40,
            'peak_threshold': -80,
            'stochastic_factor': 0.2,
            'timbre_preserve': True,
            'hop_size': 256,
            'synth_fft_size': 2048,
            'f0_error_threshold': 5.0,
            'harm_dev_slope': 0.01,
            'min_sine_dur': 0.02,
            'residual_level': 1.0,
        },
    }


@app.route('/api/upload_audio', methods=['POST'])
def upload_audio():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    path = UPLOAD_DIR / f"audio_{uuid.uuid4().hex}.wav"
    save_as_wav(file, path)

    # Full SESSION reset to prevent stale state from previous uploads
    SESSION['audio_path'] = str(path)
    SESSION['corrected_path'] = str(UPLOAD_DIR / f"corrected_{uuid.uuid4().hex}.wav")
    SESSION['params'] = get_default_params()
    SESSION['time_edits'] = []
    SESSION['audio'] = None
    SESSION['sr'] = None
    SESSION['times'] = None
    SESSION['frequencies'] = None
    SESSION['clusters'] = []
    SESSION['midi_notes'] = []
    SESSION['corrected_audio'] = None
    SESSION['sms_analysis'] = None

    return jsonify({'ok': True, 'filename': file.filename})


@app.route('/api/upload_reference', methods=['POST'])
def upload_reference():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    path = UPLOAD_DIR / f"reference_{uuid.uuid4().hex}.wav"
    save_as_wav(file, path)

    SESSION['reference_path'] = str(path)

    # Auto-analyze using current params (or defaults if no main audio yet)
    params = SESSION['params'] if SESSION['params'] else get_default_params()

    try:
        times, frequencies, notes, sr, audio = analyze_pitch(str(path), params)
        ref_clusters = cluster_notes(times, frequencies, notes, audio, sr, params)
        SESSION['reference_clusters'] = ref_clusters

        return jsonify({
            'ok': True,
            'filename': file.filename,
            'cluster_count': len(ref_clusters),
            'clusters': clusters_to_json(ref_clusters),
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/upload_backing', methods=['POST'])
def upload_backing():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    path = UPLOAD_DIR / f"backing_{uuid.uuid4().hex}.wav"
    save_as_wav(file, path)

    SESSION['backing_path'] = str(path)

    return jsonify({'ok': True, 'filename': file.filename})


@app.route('/api/reference_audio')
def serve_reference_audio():
    if not SESSION['reference_path'] or not os.path.exists(SESSION['reference_path']):
        return jsonify({'error': 'No reference audio available'}), 404
    return send_file(SESSION['reference_path'], mimetype='audio/wav', as_attachment=False)


@app.route('/api/backing_audio')
def serve_backing_audio():
    if not SESSION['backing_path'] or not os.path.exists(SESSION['backing_path']):
        return jsonify({'error': 'No backing audio available'}), 404
    return send_file(SESSION['backing_path'], mimetype='audio/wav', as_attachment=False)


@app.route('/api/upload_midi', methods=['POST'])
def upload_midi():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    path = UPLOAD_DIR / f"midi_{uuid.uuid4().hex}.mid"
    file.save(str(path))

    SESSION['midi_path'] = str(path)
    midi_notes, msg = parse_midi_file(str(path))
    SESSION['midi_notes'] = midi_notes

    return jsonify({'ok': True, 'message': msg, 'note_count': len(midi_notes)})


@app.route('/api/analyze', methods=['POST'])
def analyze():
    if not SESSION['audio_path']:
        return jsonify({'error': 'No audio file uploaded'}), 400

    params = request.json or {}
    # Merge with current params
    for k, v in params.items():
        if k == 'rb':
            SESSION['params']['rb'].update(v)
        elif k == 'sms':
            SESSION['params']['sms'].update(v)
        else:
            SESSION['params'][k] = v

    # Invalidate SMS analysis cache on re-analyze
    SESSION['sms_analysis'] = None

    try:
        times, frequencies, notes, sr, audio = analyze_pitch(
            SESSION['audio_path'], SESSION['params']
        )

        SESSION['times'] = times
        SESSION['frequencies'] = frequencies
        SESSION['sr'] = sr
        SESSION['audio'] = audio

        clusters = cluster_notes(times, frequencies, notes, audio, sr, SESSION['params'])
        SESSION['clusters'] = clusters
        SESSION['time_edits'] = []

        # Copy original to corrected path
        audio_mono = get_audio_mono(audio)
        sf.write(SESSION['corrected_path'], audio_mono, int(sr))
        SESSION['corrected_audio'] = audio_mono.copy()

        # Compute average pitch deviation vs MIDI if available
        avg_deviation = None
        if SESSION['midi_notes']:
            avg_deviation = compute_avg_pitch_deviation(clusters, SESSION['midi_notes'], SESSION['params'])

        return jsonify({
            'ok': True,
            'duration': float(len(audio_mono) / sr),
            'sr': float(sr),
            'cluster_count': len(clusters),
            'clusters': clusters_to_json(clusters),
            'times': times.tolist(),
            'frequencies': [float(f) if not np.isnan(f) else None for f in frequencies],
            'midi_notes': SESSION['midi_notes'],
            'avg_pitch_deviation_cents': avg_deviation,
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/correct', methods=['POST'])
def correct():
    if not SESSION['clusters']:
        return jsonify({'error': 'No clusters - run analyze first'}), 400

    params = request.json or {}
    for k, v in params.items():
        if k == 'rb':
            SESSION['params']['rb'].update(v)
        elif k == 'sms':
            SESSION['params']['sms'].update(v)
        else:
            SESSION['params'][k] = v

    try:
        if SESSION['midi_notes']:
            SESSION['clusters'] = autocorrect_midi(
                SESSION['clusters'], SESSION['midi_notes'], SESSION['params']
            )
        else:
            SESSION['clusters'] = autocorrect_standard(SESSION['clusters'], SESSION['params'])

        return jsonify({
            'ok': True,
            'clusters': clusters_to_json(SESSION['clusters']),
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/sync_clusters', methods=['POST'])
def sync_clusters():
    """
    Replace server-side clusters entirely with the client's cluster list, enrich
    each cluster with pitch frame data sliced from the original analysis, then
    run a single full-audio rubberband pass.
    """
    if SESSION['times'] is None or SESSION['frequencies'] is None:
        return jsonify({'error': 'No analysis data - run analyze first'}), 400

    data = request.json or {}
    incoming = data.get('clusters', [])

    # Merge params if provided (engine selection, SMS params, etc.)
    incoming_params = data.get('params', {})
    if incoming_params:
        old_sms = SESSION['params'].get('sms', {}).copy()
        old_engine = SESSION['params'].get('pitch_engine', 'rubberband')
        for k, v in incoming_params.items():
            if k == 'rb':
                SESSION['params']['rb'].update(v)
            elif k == 'sms':
                SESSION['params']['sms'].update(v)
            else:
                SESSION['params'][k] = v
        # Invalidate SMS cache only if analysis-affecting params changed
        # Synthesis-only params (synth_fft_size, residual_level, timbre_preserve) don't need re-analysis
        _SMS_SYNTH_ONLY_KEYS = {'synth_fft_size', 'residual_level', 'timbre_preserve'}
        new_sms = SESSION['params'].get('sms', {})
        new_engine = SESSION['params'].get('pitch_engine', 'rubberband')
        if old_engine != new_engine:
            SESSION['sms_analysis'] = None
            print("[SMS] Cache invalidated due to engine change")
        elif old_sms != new_sms:
            analysis_changed = any(
                old_sms.get(k) != new_sms.get(k)
                for k in set(old_sms) | set(new_sms)
                if k not in _SMS_SYNTH_ONLY_KEYS
            )
            if analysis_changed:
                SESSION['sms_analysis'] = None
                print("[SMS] Cache invalidated due to analysis param change")

    # Always overwrite time_edits — default to empty to clear stale edits
    incoming_time_edits = data.get('time_edits', [])
    SESSION['time_edits'] = [
        {'cluster_idx': int(e['clusterIdx']), 'new_start': float(e['newStart']), 'new_end': float(e['newEnd'])}
        for e in incoming_time_edits
    ]
    print(f"[DEBUG] sync_clusters: received {len(incoming_time_edits)} time_edits from client")

    print(f"[DEBUG] sync_clusters: {len(incoming)} clusters incoming, {len(SESSION['time_edits'])} time_edits active")
    if incoming:
        print(f"[DEBUG] incoming[0] keys: {list(incoming[0].keys())}")
        print(f"[DEBUG] incoming[0]: {incoming[0]}")

    times = SESSION['times']
    frequencies = SESSION['frequencies']
    params = SESSION['params']
    transition_ramp = params.get('transition_ramp_ms', 160)
    correction_strength = params.get('correction_strength', 90)

    new_clusters = []
    for c in incoming:
        start_time = float(c['start_time'])
        end_time   = float(c['end_time'])

        # Slice pitch frames from original analysis that fall within this cluster
        # Use binary search since times is sorted
        i_start = np.searchsorted(times, start_time, side='left')
        i_end = np.searchsorted(times, end_time, side='right')
        cluster_times = []
        cluster_freqs = []
        for j in range(i_start, i_end):
            f = frequencies[j]
            if not np.isnan(f) and f > 0:
                cluster_times.append(float(times[j]))
                cluster_freqs.append(float(f))

        # Use client-sent mean_freq — this is what the user sees as the note center.
        # Recalculating from pitch frames can give a slightly different value which
        # would cause smoothing to pull toward the wrong target.
        mean_freq = float(c.get('mean_freq', 0))
        if mean_freq == 0 and cluster_freqs:
            mean_freq = float(np.mean(cluster_freqs))
        print(f"[DEBUG] mean_freq assignment: client sent {float(c.get('mean_freq', 0)):.2f}Hz, using {mean_freq:.2f}Hz")

        # Recalculate note from mean_freq
        note = hz_to_note(mean_freq) or c.get('note', 'A4')

        new_cluster = {
            'note':                  note,
            'start_time':            start_time,
            'end_time':              end_time,
            'mean_freq':             mean_freq,
            'duration_ms':           (end_time - start_time) * 1000,
            'pitch_shift_semitones': float(c.get('pitch_shift_semitones', 0)),
            'ramp_in_ms':            float(c.get('ramp_in_ms', c.get('transition_ramp_ms', transition_ramp))),
            'ramp_out_ms':           float(c.get('ramp_out_ms', c.get('transition_ramp_ms', transition_ramp))),
            'correction_strength':   float(c.get('correction_strength', correction_strength)),
            'smoothing_percent':     float(c.get('smoothing_percent', 0)),
            'manually_edited':       bool(c.get('manually_edited', False)),
            'times':                 cluster_times,
            'frequencies':           cluster_freqs,
        }
        new_cluster['pitch_variation_cents'] = compute_cluster_pitch_variation(new_cluster)
        new_clusters.append(new_cluster)

        print(f"[DEBUG] cluster {note} {start_time:.2f}-{end_time:.2f}s | "
              f"smoothing_percent={float(c.get('smoothing_percent', 0)):.1f} | "
              f"pitch_shift_semitones={float(c.get('pitch_shift_semitones', 0)):.3f} | "
              f"times={len(cluster_times)} frames | "
              f"freqs={len(cluster_freqs)} frames")

    SESSION['clusters'] = new_clusters

    # Use process_combined to apply both pitch and time edits in a single pass
    try:
        from time_engine import process_combined
        # Pass SMS cache and Parselmouth f0 data through params for the engine to use
        if SESSION['params'].get('pitch_engine') == 'sms':
            SESSION['params']['_sms_cache'] = SESSION.get('sms_analysis')
            SESSION['params']['_sms_cache_ref'] = [SESSION.get('sms_analysis')]
            if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                SESSION['params']['sms']['_parselmouth_f0'] = {
                    'times': SESSION['times'],
                    'frequencies': SESSION['frequencies'],
                }

        success, msg = process_combined(
            SESSION['audio'], SESSION['sr'],
            SESSION['clusters'], SESSION['params'],
            SESSION['time_edits'], SESSION['corrected_path'],
        )

        # Store updated SMS cache
        if SESSION['params'].get('pitch_engine') == 'sms':
            cache_ref = SESSION['params'].pop('_sms_cache_ref', [None])
            SESSION['params'].pop('_sms_cache', None)
            if cache_ref[0] is not None:
                SESSION['sms_analysis'] = cache_ref[0]

        if not success:
            return jsonify({'error': msg}), 500

        corrected, _ = sf.read(SESSION['corrected_path'])
        SESSION['corrected_audio'] = get_audio_mono(corrected) if len(corrected.shape) > 1 else corrected

        # Analyze corrected audio pitch in one pass (avoids N separate analyzeSegment calls)
        corrected_times = None
        corrected_freqs = None
        try:
            time_step = SESSION['params'].get('time_resolution_ms', 20) / 1000.0
            min_freq = SESSION['params'].get('min_frequency', 75)
            max_freq = SESSION['params'].get('max_frequency', 600)
            snd = parselmouth.Sound(SESSION['corrected_audio'], sampling_frequency=SESSION['sr'])
            pitch = call(snd, "To Pitch", time_step, min_freq, max_freq)
            time_values = pitch.xs()
            freqs = []
            for t in time_values:
                f0 = call(pitch, "Get value at time", t, "Hertz", "Linear")
                freqs.append(float(f0) if (f0 is not None and not np.isnan(f0) and f0 > 0) else None)
            corrected_times = time_values.tolist()
            corrected_freqs = freqs
        except Exception as e:
            print(f"[WARN] corrected audio analysis failed: {e}")

        resp = {'ok': True, 'clusters': clusters_to_json(SESSION['clusters'])}
        if corrected_times is not None:
            resp['corrected_times'] = corrected_times
            resp['corrected_freqs'] = corrected_freqs

        # Return timemap if time edits are active
        if SESSION['time_edits']:
            from time_engine import generate_time_map
            audio_mono = get_audio_mono(SESSION['audio'])
            actual_timemap = generate_time_map(SESSION['clusters'], SESSION['time_edits'], SESSION['sr'], len(audio_mono))
            resp['timemap'] = [
                {'source_s': src / SESSION['sr'], 'target_s': tgt / SESSION['sr']}
                for src, tgt in actual_timemap
            ]

        return jsonify(resp)

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/correct_cluster', methods=['POST'])
def correct_cluster():
    """Correct a single cluster and splice back into audio.

    Accepts an optional 'clusters' array to sync the full cluster list
    before processing, ensuring the backend state matches the frontend.
    """
    data = request.json or {}
    cluster_idx = data.get('cluster_idx')

    # If a full cluster list is provided, sync it first (without processing)
    incoming = data.get('clusters', [])
    if incoming:
        times = SESSION['times']
        frequencies = SESSION['frequencies']
        params = SESSION['params']
        transition_ramp = params.get('transition_ramp_ms', 160)
        correction_strength = params.get('correction_strength', 90)

        new_clusters = []
        for c in incoming:
            start_time = float(c['start_time'])
            end_time   = float(c['end_time'])

            i_start = np.searchsorted(times, start_time, side='left')
            i_end = np.searchsorted(times, end_time, side='right')
            cluster_times = []
            cluster_freqs = []
            for j in range(i_start, i_end):
                f = frequencies[j]
                if not np.isnan(f) and f > 0:
                    cluster_times.append(float(times[j]))
                    cluster_freqs.append(float(f))

            mean_freq = float(c.get('mean_freq', 0))
            if mean_freq == 0 and cluster_freqs:
                mean_freq = float(np.mean(cluster_freqs))

            note = hz_to_note(mean_freq) or c.get('note', 'A4')

            new_clusters.append({
                'note': note,
                'start_time': start_time,
                'end_time': end_time,
                'mean_freq': mean_freq,
                'duration_ms': (end_time - start_time) * 1000,
                'pitch_shift_semitones': float(c.get('pitch_shift_semitones', 0)),
                'ramp_in_ms': float(c.get('ramp_in_ms', transition_ramp)),
                'ramp_out_ms': float(c.get('ramp_out_ms', transition_ramp)),
                'correction_strength': float(c.get('correction_strength', correction_strength)),
                'smoothing_percent': float(c.get('smoothing_percent', 0)),
                'manually_edited': bool(c.get('manually_edited', False)),
                'times': cluster_times,
                'frequencies': cluster_freqs,
            })
            new_clusters[-1]['pitch_variation_cents'] = compute_cluster_pitch_variation(new_clusters[-1])

        SESSION['clusters'] = new_clusters

    if cluster_idx is None or cluster_idx >= len(SESSION['clusters']):
        return jsonify({'error': 'Invalid cluster index'}), 400

    # Update cluster parameters from top-level fields (backwards compat)
    cluster = SESSION['clusters'][cluster_idx]
    if 'pitch_shift_semitones' in data and not incoming:
        cluster['pitch_shift_semitones'] = float(data['pitch_shift_semitones'])
    if 'ramp_in_ms' in data and not incoming:
        cluster['ramp_in_ms'] = float(data['ramp_in_ms'])
    if 'ramp_out_ms' in data and not incoming:
        cluster['ramp_out_ms'] = float(data['ramp_out_ms'])
    if 'correction_strength' in data and not incoming:
        cluster['correction_strength'] = float(data['correction_strength'])
    if 'smoothing_percent' in data and not incoming:
        cluster['smoothing_percent'] = float(data['smoothing_percent'])
    cluster['manually_edited'] = True

    # Sync time edits if provided
    incoming_time_edits = data.get('time_edits', None)
    if incoming_time_edits is not None:
        SESSION['time_edits'] = [
            {'cluster_idx': int(e['clusterIdx']), 'new_start': float(e['newStart']), 'new_end': float(e['newEnd'])}
            for e in incoming_time_edits
        ]

    padding_ms = float(data.get('padding_ms', 300))
    crossfade_ms = float(data.get('crossfade_ms', 10))
    crop_ms = float(data.get('crop_ms', 5))
    neighbor_count = int(data.get('neighbor_count', 0))

    # Pass Parselmouth f0 data for SMS engine
    if SESSION['params'].get('pitch_engine') == 'sms':
        if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
            SESSION['params']['sms']['_parselmouth_f0'] = {
                'times': SESSION['times'],
                'frequencies': SESSION['frequencies'],
            }

    try:
        result_audio, msg = process_segment(
            SESSION['audio'], SESSION['sr'],
            SESSION['clusters'], cluster_idx,
            SESSION['params'], SESSION['corrected_path'],
            time_edits=SESSION.get('time_edits', []),
            padding_ms=padding_ms, crossfade_ms=crossfade_ms,
            crop_ms=crop_ms, neighbor_count=neighbor_count
        )

        if result_audio is None:
            return jsonify({'error': msg}), 500

        SESSION['corrected_audio'] = result_audio
        sf.write(SESSION['corrected_path'], result_audio, int(SESSION['sr']))

        # Re-analyze pitch in the processed region
        buffer_s = padding_ms / 1000.0
        seg_start_time = max(0, cluster['start_time'] - buffer_s)
        seg_end_time = min(len(result_audio) / SESSION['sr'], cluster['end_time'] + buffer_s)

        seg_times = []
        seg_freqs = []
        try:
            start_sample = int(seg_start_time * SESSION['sr'])
            end_sample = int(seg_end_time * SESSION['sr'])
            audio_segment = result_audio[start_sample:end_sample]
            sound_segment = parselmouth.Sound(audio_segment, sampling_frequency=SESSION['sr'])
            time_step = SESSION['params'].get('time_resolution_ms', 20) / 1000.0
            min_freq = SESSION['params'].get('min_frequency', 75)
            max_freq = SESSION['params'].get('max_frequency', 600)
            pitch_obj = call(sound_segment, "To Pitch", time_step, min_freq, max_freq)
            time_values = pitch_obj.xs()
            for t in time_values:
                f0 = call(pitch_obj, "Get value at time", t, "Hertz", "Linear")
                seg_freqs.append(float(f0) if (f0 is not None and not np.isnan(f0) and f0 > 0) else None)
            seg_times = (time_values + seg_start_time).tolist()
        except Exception:
            pass  # Non-critical: pitch re-analysis failure shouldn't block the response

        return jsonify({
            'ok': True,
            'cluster': clusters_to_json(SESSION['clusters'])[cluster_idx],
            'times': seg_times,
            'frequencies': seg_freqs,
            'start_time': seg_start_time,
            'end_time': seg_end_time,
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/analyze_segment', methods=['POST'])
def analyze_segment():
    """Re-analyze pitch for a segment of the corrected audio and return updated times/frequencies."""
    data = request.json or {}
    start_time = data.get('start_time', 0)
    end_time = data.get('end_time', 0)

    if not SESSION['corrected_audio'] is None and SESSION['sr']:
        # Use in-memory audio if available (faster)
        audio_full = SESSION['corrected_audio']
        sr = SESSION['sr']
    elif SESSION['corrected_path'] and os.path.exists(SESSION['corrected_path']):
        # Fall back to loading from file
        audio_full, sr = sf.read(SESSION['corrected_path'])
        if len(audio_full.shape) > 1:
            audio_full = audio_full.mean(axis=1) if audio_full.shape[0] > audio_full.shape[1] else audio_full.mean(axis=0)
    else:
        return jsonify({'error': 'No corrected audio available'}), 400

    try:
        # Calculate sample range for the segment
        start_sample = int(start_time * sr)
        end_sample = int(end_time * sr)
        
        # Clamp to bounds
        start_sample = max(0, start_sample)
        end_sample = min(len(audio_full), end_sample)
        
        # Extract segment directly from array
        audio_segment = audio_full[start_sample:end_sample]
        
        # Create Parselmouth Sound object directly from array (no file I/O!)
        sound_segment = parselmouth.Sound(audio_segment, sampling_frequency=sr)
        
        # Analyze pitch on this segment
        time_step = SESSION['params'].get('time_resolution_ms', 20) / 1000.0
        min_freq = SESSION['params'].get('min_frequency', 75)
        max_freq = SESSION['params'].get('max_frequency', 600)
        
        pitch = call(sound_segment, "To Pitch", time_step, min_freq, max_freq)
        time_values = pitch.xs()
        
        frequencies = []
        for t in time_values:
            f0 = call(pitch, "Get value at time", t, "Hertz", "Linear")
            frequencies.append(f0 if (f0 is not None and not np.isnan(f0) and f0 > 0) else np.nan)
        
        frequencies = np.array(frequencies)
        
        # Convert relative times to absolute times
        times_abs = time_values + start_time
        
        seg_times = times_abs.tolist()
        seg_freqs = [float(f) if not np.isnan(f) else None for f in frequencies]
        
        return jsonify({
            'ok': True,
            'times': seg_times,
            'frequencies': seg_freqs,
            'start_time': start_time,
            'end_time': end_time,
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/reset_edits', methods=['POST'])
def reset_edits():
    """Reset all manual edits (pitch and time)."""
    for cluster in SESSION['clusters']:
        cluster['manually_edited'] = False
        cluster['pitch_shift_semitones'] = 0.0
    SESSION['time_edits'] = []

    return jsonify({'ok': True, 'clusters': clusters_to_json(SESSION['clusters'])})


@app.route('/api/audio')
def serve_audio():
    """Serve the current corrected audio for playback."""
    if not SESSION['corrected_path'] or not os.path.exists(SESSION['corrected_path']):
        return jsonify({'error': 'No audio available'}), 404

    return send_file(
        SESSION['corrected_path'],
        mimetype='audio/wav',
        as_attachment=False
    )


@app.route('/api/export')
def export_audio():
    """Download the corrected audio file, re-processing to ensure all edits are included."""
    if not SESSION['corrected_path'] or not os.path.exists(SESSION['corrected_path']):
        return jsonify({'error': 'No audio to export'}), 404

    # Re-process with both pitch and time edits to ensure export is up-to-date
    if SESSION['audio'] is not None and SESSION['clusters']:
        try:
            from time_engine import process_combined
            if SESSION['params'].get('pitch_engine') == 'sms':
                SESSION['params']['_sms_cache'] = SESSION.get('sms_analysis')
                SESSION['params']['_sms_cache_ref'] = [SESSION.get('sms_analysis')]
                if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                    SESSION['params']['sms']['_parselmouth_f0'] = {
                        'times': SESSION['times'],
                        'frequencies': SESSION['frequencies'],
                    }
            success, msg = process_combined(
                SESSION['audio'], SESSION['sr'],
                SESSION['clusters'], SESSION['params'],
                SESSION['time_edits'], SESSION['corrected_path'],
            )
            if SESSION['params'].get('pitch_engine') == 'sms':
                cache_ref = SESSION['params'].pop('_sms_cache_ref', [None])
                SESSION['params'].pop('_sms_cache', None)
                if cache_ref[0] is not None:
                    SESSION['sms_analysis'] = cache_ref[0]
            if not success:
                return jsonify({'error': f'Export processing failed: {msg}'}), 500
        except Exception as e:
            return jsonify({'error': f'Export processing failed: {e}'}), 500

    original_name = Path(SESSION['audio_path']).stem if SESSION['audio_path'] else 'audio'
    download_name = f"{original_name}_corrected.wav"

    return send_file(
        SESSION['corrected_path'],
        mimetype='audio/wav',
        as_attachment=True,
        download_name=download_name
    )


@app.route('/api/params', methods=['GET'])
def get_params():
    p = SESSION['params'] if SESSION['params'] else get_default_params()
    # Filter out internal cache keys that aren't serializable
    return jsonify({k: v for k, v in p.items() if not k.startswith('_')})


@app.route('/api/delete_cluster', methods=['POST'])
def delete_cluster():
    """Delete a cluster and restore original audio for that segment."""
    data = request.json or {}
    cluster_idx = data.get('cluster_idx')

    if cluster_idx is None or cluster_idx >= len(SESSION['clusters']):
        return jsonify({'error': 'Invalid cluster index'}), 400

    cluster = SESSION['clusters'][cluster_idx]

    try:
        # Restore original audio for this segment by processing with zero shift
        cluster['pitch_shift_semitones'] = 0.0
        cluster['correction_strength'] = 0.0
        cluster['manually_edited'] = False

        # Pass Parselmouth f0 data for SMS engine
        if SESSION['params'].get('pitch_engine') == 'sms':
            if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                SESSION['params']['sms']['_parselmouth_f0'] = {
                    'times': SESSION['times'],
                    'frequencies': SESSION['frequencies'],
                }

        result_audio, msg = process_segment(
            SESSION['audio'], SESSION['sr'],
            SESSION['clusters'], cluster_idx,
            SESSION['params'], SESSION['corrected_path']
        )

        if result_audio is None:
            return jsonify({'error': f'Failed to restore segment: {msg}'}), 500

        SESSION['corrected_audio'] = result_audio
        sf.write(SESSION['corrected_path'], result_audio, int(SESSION['sr']))

        # Now remove from server-side clusters list
        SESSION['clusters'].pop(cluster_idx)

        return jsonify({'ok': True, 'clusters': clusters_to_json(SESSION['clusters'])})

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/update_cluster', methods=['POST'])
def update_cluster():
    """Update individual cluster parameters without reprocessing."""
    data = request.json or {}
    cluster_idx = data.get('cluster_idx')

    if cluster_idx is None or cluster_idx >= len(SESSION['clusters']):
        return jsonify({'error': 'Invalid cluster index'}), 400

    cluster = SESSION['clusters'][cluster_idx]
    for key in ['ramp_in_ms', 'ramp_out_ms', 'correction_strength', 'smoothing_percent']:
        if key in data:
            cluster[key] = float(data[key])

    return jsonify({'ok': True})


@app.route('/api/sync_time_edits', methods=['POST'])
def sync_time_edits():
    """
    Receive time stretch edits, generate tempo map,
    run Rubberband with time stretching (and pitch if present), return success/error.
    """
    if SESSION['audio'] is None or SESSION['sr'] is None:
        return jsonify({'error': 'No audio loaded'}), 400

    if not SESSION['clusters']:
        return jsonify({'error': 'No clusters - run analyze first'}), 400

    data = request.json or {}
    incoming_edits = data.get('time_edits', [])

    # Convert to internal format
    time_edits = []
    for edit in incoming_edits:
        time_edits.append({
            'cluster_idx': int(edit['clusterIdx']),
            'new_start': float(edit['newStart']),
            'new_end': float(edit['newEnd']),
        })

    SESSION['time_edits'] = time_edits
    print(f"[DEBUG] sync_time_edits: {len(time_edits)} time edits received")

    try:
        from time_engine import process_combined, process_time_stretch, generate_time_map

        # Check if there are also pitch edits
        has_pitch = any(
            c['pitch_shift_semitones'] != 0 or c.get('smoothing_percent', 0) != 0
            for c in SESSION['clusters']
        )

        if has_pitch:
            # Combined pitch + time processing
            if SESSION['params'].get('pitch_engine') == 'sms':
                SESSION['params']['_sms_cache'] = SESSION.get('sms_analysis')
                SESSION['params']['_sms_cache_ref'] = [SESSION.get('sms_analysis')]
                if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                    SESSION['params']['sms']['_parselmouth_f0'] = {
                        'times': SESSION['times'],
                        'frequencies': SESSION['frequencies'],
                    }
            success, msg = process_combined(
                SESSION['audio'], SESSION['sr'],
                SESSION['clusters'], SESSION['params'],
                time_edits, SESSION['corrected_path'],
            )
            if SESSION['params'].get('pitch_engine') == 'sms':
                cache_ref = SESSION['params'].pop('_sms_cache_ref', [None])
                SESSION['params'].pop('_sms_cache', None)
                if cache_ref[0] is not None:
                    SESSION['sms_analysis'] = cache_ref[0]
        else:
            # Time-only processing
            rb_params = SESSION['params'].get('rb', {})
            success, msg = process_time_stretch(
                SESSION['audio'], SESSION['sr'],
                SESSION['clusters'], time_edits,
                rb_params, SESSION['corrected_path'],
            )

        if not success:
            return jsonify({'ok': False, 'error': msg}), 500

        corrected, _ = sf.read(SESSION['corrected_path'])
        SESSION['corrected_audio'] = get_audio_mono(corrected) if len(corrected.shape) > 1 else corrected

        # Return the actual timemap for frontend debugging
        audio_mono = get_audio_mono(SESSION['audio'])
        audio_length = len(audio_mono)
        sr = SESSION['sr']
        actual_timemap = generate_time_map(SESSION['clusters'], time_edits, sr, audio_length)
        # Convert frame pairs to seconds for easy comparison
        timemap_seconds = [
            {'source_s': src / sr, 'target_s': tgt / sr}
            for src, tgt in actual_timemap
        ]

        return jsonify({'ok': True, 'timemap': timemap_seconds})

    except Exception as e:
        import traceback
        return jsonify({'ok': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    app.run(debug=True, host=host, port=5000)
