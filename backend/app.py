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
import hashlib
from datetime import datetime
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


from declicker_engine import (
    get_default_declicker_params, detect_clicks, run_declicker, isolate_clicks,
    repair_clicks, build_frequency_bands, repair_clicks_segment,
)

from denoise_engine import (
    get_default_denoise_params, apply_denoise, compute_spectrograms,
)

from volume_engine import (
    compute_rms_db, detect_breaths, create_breath_at_point,
    compute_effective_gains, generate_gain_envelope, apply_gain_envelope,
)

from audio_engine import (
    analyze_pitch, cluster_notes, parse_midi_file, piano_to_midi_notes, midi_notes_to_file,
    autocorrect_midi, autocorrect_standard,
    process_full_audio, process_segment, process_time_segment,
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
    'audio_hash': None,
    'original_filename': None,
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
    'stretch_markers': [],
    'reference_path': None,
    'reference_clusters': [],
    'backing_path': None,
    'sms_analysis': None,
    'declicker_params': {},
    'declicker_detections': None,
    'declicker_audio': None,
    'declicker_path': None,
    'declicker_processed_clicks': [],
    'denoiser_params': {},
    'denoiser_audio': None,
    'denoiser_path': None,
    'edit_audio': None,
    'edit_path': None,
    'edit_clips': None,
    'breaths': [],
    'volume_clusters': [],
    'breath_params': {
        'min_breath_length_ms': 80,
        'min_breath_volume_db': -50,
        'max_breath_volume_db': -15,
    },
    'volume_params': {
        'note_min_rms_db': -60.0,
        'note_max_rms_db': 0.0,
        'note_global_offset_db': 0.0,
        'breath_min_rms_db': -60.0,
        'breath_max_rms_db': 0.0,
        'breath_global_offset_db': 0.0,
    },
    'volume_audio': None,
    'volume_path': None,
    'volume_applied': False,
}

UPLOAD_DIR = Path(tempfile.gettempdir()) / 'vocal_editor'
UPLOAD_DIR.mkdir(exist_ok=True)

PROJECT_DIR = Path(os.environ.get('VOCAL_EDITOR_PROJECTS', str(Path.home() / '.vocal_editor' / 'projects')))
PROJECT_DIR.mkdir(parents=True, exist_ok=True)


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
        'pitch_engine': 'psola',
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
        'psola': {
            'min_pitch': 75,
            'max_pitch': 600,
            'time_step': 0.01,
            'resynthesis_method': 'overlap_add',
            'pitch_point_step': 1,
            'pitch_smooth_window_ms': 0,
            'max_shift_semitones': 12,
        },
        'voicing_threshold': 0.75,
        'fd_psola': {
            'fft_size': 2048,
            'window_type': 'kaiser',
            'formant_preservation': True,
            'formant_method': 'cepstral',
            'envelope_order': 30,
            'overlap_factor': 4,
            'phase_mode': 'pitch_sync',
            'min_pitch': 75,
            'max_pitch': 600,
            'kaiser_beta': 8.0,
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
    SESSION['stretch_markers'] = []
    SESSION['audio'] = None
    SESSION['sr'] = None
    SESSION['times'] = None
    SESSION['frequencies'] = None
    SESSION['clusters'] = []
    SESSION['midi_notes'] = []
    SESSION['corrected_audio'] = None
    SESSION['sms_analysis'] = None
    SESSION['declicker_params'] = {}
    SESSION['declicker_detections'] = None
    SESSION['declicker_audio'] = None
    SESSION['declicker_path'] = None
    SESSION['edit_audio'] = None
    SESSION['edit_path'] = None
    SESSION['edit_clips'] = None

    # Compute content hash for project save/load
    audio_data, sr = sf.read(str(path))
    audio_hash = hashlib.sha256(audio_data.tobytes()).hexdigest()
    SESSION['audio_hash'] = audio_hash
    SESSION['original_filename'] = file.filename

    # Check if a saved project exists for this audio
    project_path = PROJECT_DIR / f"{audio_hash}.json"
    has_project = project_path.exists()

    return jsonify({'ok': True, 'filename': file.filename, 'has_project': has_project})


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

    return jsonify({'ok': True, 'message': msg, 'note_count': len(midi_notes), 'midi_notes': midi_notes})


@app.route('/api/upload_piano_guide', methods=['POST'])
def upload_piano_guide():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    path = UPLOAD_DIR / f"piano_{uuid.uuid4().hex}.wav"
    file.save(str(path))

    try:
        midi_notes, msg = piano_to_midi_notes(str(path), SESSION['params'])
    except Exception as e:
        return jsonify({'error': f'Piano analysis failed: {str(e)}'}), 500

    SESSION['midi_notes'] = midi_notes

    return jsonify({'ok': True, 'message': msg, 'note_count': len(midi_notes), 'midi_notes': midi_notes})


@app.route('/api/export_midi', methods=['GET'])
def export_midi():
    if not SESSION.get('midi_notes'):
        return jsonify({'error': 'No MIDI notes available'}), 400

    path = UPLOAD_DIR / f"export_{uuid.uuid4().hex}.mid"
    midi_notes_to_file(SESSION['midi_notes'], str(path))
    return send_file(str(path), mimetype='audio/midi', as_attachment=True, download_name='piano_guide.mid')


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
        elif k == 'psola':
            SESSION['params']['psola'].update(v)
        else:
            SESSION['params'][k] = v

    # Invalidate SMS analysis cache on re-analyze
    SESSION['sms_analysis'] = None

    try:
        audio_path = _get_pipeline_audio_path()
        times, frequencies, notes, sr, audio = analyze_pitch(
            audio_path, SESSION['params']
        )

        SESSION['times'] = times
        SESSION['frequencies'] = frequencies
        SESSION['sr'] = sr
        SESSION['audio'] = audio

        clusters = cluster_notes(times, frequencies, notes, audio, sr, SESSION['params'])
        SESSION['clusters'] = clusters
        SESSION['time_edits'] = []
        SESSION['stretch_markers'] = []

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
        elif k == 'psola':
            SESSION['params']['psola'].update(v)
        else:
            SESSION['params'][k] = v

    try:
        warnings = []
        if SESSION['midi_notes']:
            SESSION['clusters'], warnings = autocorrect_midi(
                SESSION['clusters'], SESSION['midi_notes'], SESSION['params']
            )
        else:
            SESSION['clusters'] = autocorrect_standard(SESSION['clusters'], SESSION['params'])

        return jsonify({
            'ok': True,
            'clusters': clusters_to_json(SESSION['clusters']),
            'warnings': warnings,
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

    # Accept stretch_markers (new) or time_edits (legacy)
    incoming_stretch_markers = data.get('stretch_markers', [])
    SESSION['stretch_markers'] = [
        {
            'id': str(m['id']),
            'originalTime': float(m['originalTime']),
            'currentTime': float(m['currentTime']),
            'leftClusterIdx': int(m['leftClusterIdx']),
            'rightClusterIdx': int(m['rightClusterIdx']),
        }
        for m in incoming_stretch_markers
    ]

    incoming_time_edits = data.get('time_edits', [])
    SESSION['time_edits'] = [
        {'cluster_idx': int(e['clusterIdx']), 'new_start': float(e['newStart']), 'new_end': float(e['newEnd'])}
        for e in incoming_time_edits
    ]
    print(f"[DEBUG] sync_clusters: received {len(incoming_stretch_markers)} stretch_markers, {len(incoming_time_edits)} time_edits from client")

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
            'rms_db':                float(c.get('rms_db', -60.0)),
            'gain_db':               float(c.get('gain_db', 0.0)),
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
        elif SESSION['params'].get('pitch_engine') == 'psola':
            if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                SESSION['params']['psola']['_parselmouth_f0'] = {
                    'times': SESSION['times'],
                    'frequencies': SESSION['frequencies'],
                }
        elif SESSION['params'].get('pitch_engine') == 'fd_psola':
            if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                SESSION['params']['fd_psola']['_parselmouth_f0'] = {
                    'times': SESSION['times'],
                    'frequencies': SESSION['frequencies'],
                }

        success, msg = process_combined(
            SESSION['audio'], SESSION['sr'],
            SESSION['clusters'], SESSION['params'],
            SESSION['time_edits'], SESSION['corrected_path'],
            stretch_markers=SESSION.get('stretch_markers', []),
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

        # Return timemap if time edits or stretch markers are active
        if SESSION.get('stretch_markers') or SESSION['time_edits']:
            from time_engine import generate_time_map, generate_time_map_from_markers
            audio_mono = get_audio_mono(SESSION['audio'])
            if SESSION.get('stretch_markers'):
                actual_timemap = generate_time_map_from_markers(
                    SESSION['clusters'], SESSION['stretch_markers'], SESSION['sr'], len(audio_mono))
            else:
                actual_timemap = generate_time_map(
                    SESSION['clusters'], SESSION['time_edits'], SESSION['sr'], len(audio_mono))
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

    # Pass Parselmouth f0 data for SMS / PSOLA engines
    if SESSION['params'].get('pitch_engine') == 'sms':
        if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
            SESSION['params']['sms']['_parselmouth_f0'] = {
                'times': SESSION['times'],
                'frequencies': SESSION['frequencies'],
            }
    elif SESSION['params'].get('pitch_engine') == 'psola':
        if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
            SESSION['params']['psola']['_parselmouth_f0'] = {
                'times': SESSION['times'],
                'frequencies': SESSION['frequencies'],
            }
    elif SESSION['params'].get('pitch_engine') == 'fd_psola':
        if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
            SESSION['params']['fd_psola']['_parselmouth_f0'] = {
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


@app.route('/api/process_time_segment', methods=['POST'])
def api_process_time_segment():
    """Process a segment around a moved stretch marker and splice into corrected audio.

    The dirty region spans from the previous marker to the next marker
    (plus padding), ensuring boundaries match unchanged audio for seamless splicing.
    """
    data = request.json or {}
    marker_idx = data.get('marker_idx')

    if marker_idx is None:
        return jsonify({'error': 'marker_idx is required'}), 400

    # Sync clusters if provided
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

    # Sync stretch markers
    incoming_markers = data.get('stretch_markers', [])
    if incoming_markers:
        SESSION['stretch_markers'] = [
            {
                'id': m['id'],
                'originalTime': float(m['originalTime']),
                'currentTime': float(m['currentTime']),
                'leftClusterIdx': int(m['leftClusterIdx']),
                'rightClusterIdx': int(m['rightClusterIdx']),
            }
            for m in incoming_markers
        ]

    markers = SESSION.get('stretch_markers', [])
    if marker_idx >= len(markers):
        return jsonify({'error': f'Invalid marker_idx {marker_idx}, have {len(markers)} markers'}), 400

    padding_ms = float(data.get('padding_ms', 100))
    crossfade_ms = float(data.get('crossfade_ms', 10))
    crop_ms = float(data.get('crop_ms', 50))

    # Pass Parselmouth f0 data for engines that need it
    engine = SESSION['params'].get('pitch_engine', 'rubberband')
    if engine in ('psola', 'fd_psola', 'sms'):
        engine_key = engine if engine != 'sms' else 'sms'
        if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
            if engine_key in SESSION['params']:
                SESSION['params'][engine_key]['_parselmouth_f0'] = {
                    'times': SESSION['times'],
                    'frequencies': SESSION['frequencies'],
                }

    try:
        result_audio, msg = process_time_segment(
            SESSION['audio'], SESSION['sr'],
            SESSION['clusters'], markers, marker_idx,
            SESSION['params'], SESSION['corrected_path'],
            stretch_markers_raw=markers,
            padding_ms=padding_ms, crossfade_ms=crossfade_ms,
            crop_ms=crop_ms
        )

        if result_audio is None:
            return jsonify({'error': msg}), 500

        SESSION['corrected_audio'] = result_audio
        sf.write(SESSION['corrected_path'], result_audio, int(SESSION['sr']))

        return jsonify({
            'ok': True,
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
    SESSION['stretch_markers'] = []

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
            elif SESSION['params'].get('pitch_engine') in ('psola', 'fd_psola'):
                eng = SESSION['params']['pitch_engine']
                if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                    SESSION['params'][eng]['_parselmouth_f0'] = {
                        'times': SESSION['times'],
                        'frequencies': SESSION['frequencies'],
                    }
            success, msg = process_combined(
                SESSION['audio'], SESSION['sr'],
                SESSION['clusters'], SESSION['params'],
                SESSION['time_edits'], SESSION['corrected_path'],
                stretch_markers=SESSION.get('stretch_markers', []),
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

    # Apply volume automation if active
    export_path = SESSION['corrected_path']
    if SESSION.get('volume_applied') and SESSION.get('clusters'):
        try:
            corrected_audio, corr_sr = sf.read(SESSION['corrected_path'])
            if corr_sr == SESSION['sr']:
                audio_mono = get_audio_mono(corrected_audio)
                clusters = SESSION['clusters']
                breaths = SESSION.get('breaths', [])
                volume_params = SESSION.get('volume_params', {})
                for c in clusters:
                    if 'rms_db' not in c:
                        c['rms_db'] = compute_rms_db(audio_mono, SESSION['sr'], c['start_time'], c['end_time'])
                effective_gains = compute_effective_gains(clusters, breaths, volume_params)
                gain_env = generate_gain_envelope(clusters, breaths, effective_gains, SESSION['sr'], len(audio_mono))
                processed = apply_gain_envelope(audio_mono, gain_env)
                processed = np.clip(processed, -1.0, 1.0)
                vol_export_path = str(UPLOAD_DIR / 'volume_export.wav')
                sf.write(vol_export_path, processed, SESSION['sr'])
                export_path = vol_export_path
        except Exception as e:
            pass  # Fall back to corrected audio

    original_name = Path(SESSION['audio_path']).stem if SESSION['audio_path'] else 'audio'
    download_name = f"{original_name}_corrected.wav"

    return send_file(
        export_path,
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

        # Pass Parselmouth f0 data for SMS / PSOLA / FD-PSOLA engines
        if SESSION['params'].get('pitch_engine') == 'sms':
            if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                SESSION['params']['sms']['_parselmouth_f0'] = {
                    'times': SESSION['times'],
                    'frequencies': SESSION['frequencies'],
                }
        elif SESSION['params'].get('pitch_engine') in ('psola', 'fd_psola'):
            eng = SESSION['params']['pitch_engine']
            if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                SESSION['params'][eng]['_parselmouth_f0'] = {
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

    # Accept stretch_markers (new) or time_edits (legacy)
    incoming_stretch_markers = data.get('stretch_markers', [])
    SESSION['stretch_markers'] = [
        {
            'id': str(m['id']),
            'originalTime': float(m['originalTime']),
            'currentTime': float(m['currentTime']),
            'leftClusterIdx': int(m['leftClusterIdx']),
            'rightClusterIdx': int(m['rightClusterIdx']),
        }
        for m in incoming_stretch_markers
    ]

    incoming_edits = data.get('time_edits', [])
    time_edits = []
    for edit in incoming_edits:
        time_edits.append({
            'cluster_idx': int(edit['clusterIdx']),
            'new_start': float(edit['newStart']),
            'new_end': float(edit['newEnd']),
        })

    SESSION['time_edits'] = time_edits
    print(f"[DEBUG] sync_time_edits: {len(incoming_stretch_markers)} stretch_markers, {len(time_edits)} time edits received")

    try:
        from time_engine import process_combined, process_time_stretch, generate_time_map, generate_time_map_from_markers

        stretch_markers = SESSION.get('stretch_markers', [])

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
            elif SESSION['params'].get('pitch_engine') in ('psola', 'fd_psola'):
                eng = SESSION['params']['pitch_engine']
                if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                    SESSION['params'][eng]['_parselmouth_f0'] = {
                        'times': SESSION['times'],
                        'frequencies': SESSION['frequencies'],
                    }
            success, msg = process_combined(
                SESSION['audio'], SESSION['sr'],
                SESSION['clusters'], SESSION['params'],
                time_edits, SESSION['corrected_path'],
                stretch_markers=stretch_markers,
            )
            if SESSION['params'].get('pitch_engine') == 'sms':
                cache_ref = SESSION['params'].pop('_sms_cache_ref', [None])
                SESSION['params'].pop('_sms_cache', None)
                if cache_ref[0] is not None:
                    SESSION['sms_analysis'] = cache_ref[0]
        else:
            # Time-only processing — use process_combined for stretch markers support
            if SESSION['params'].get('pitch_engine') == 'psola':
                if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                    SESSION['params']['psola']['_parselmouth_f0'] = {
                        'times': SESSION['times'],
                        'frequencies': SESSION['frequencies'],
                    }
            elif SESSION['params'].get('pitch_engine') == 'fd_psola':
                if SESSION.get('times') is not None and SESSION.get('frequencies') is not None:
                    SESSION['params']['fd_psola']['_parselmouth_f0'] = {
                        'times': SESSION['times'],
                        'frequencies': SESSION['frequencies'],
                    }
            success, msg = process_combined(
                SESSION['audio'], SESSION['sr'],
                SESSION['clusters'], SESSION['params'],
                time_edits, SESSION['corrected_path'],
                stretch_markers=stretch_markers,
            )

        if not success:
            return jsonify({'ok': False, 'error': msg}), 500

        corrected, _ = sf.read(SESSION['corrected_path'])
        SESSION['corrected_audio'] = get_audio_mono(corrected) if len(corrected.shape) > 1 else corrected

        # Return the actual timemap for frontend debugging
        audio_mono = get_audio_mono(SESSION['audio'])
        audio_length = len(audio_mono)
        sr = SESSION['sr']
        if stretch_markers:
            actual_timemap = generate_time_map_from_markers(SESSION['clusters'], stretch_markers, sr, audio_length)
        else:
            actual_timemap = generate_time_map(SESSION['clusters'], time_edits, sr, audio_length)
        timemap_seconds = [
            {'source_s': src / sr, 'target_s': tgt / sr}
            for src, tgt in actual_timemap
        ]

        return jsonify({'ok': True, 'timemap': timemap_seconds})

    except Exception as e:
        import traceback
        return jsonify({'ok': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


##############################################################################
# De-Clicker endpoints
##############################################################################

def _get_declicker_source_audio():
    """Get the audio to run the declicker on (original upload)."""
    if SESSION['audio'] is None:
        return None, None
    audio = SESSION['audio']
    if len(audio.shape) > 1:
        audio = get_audio_mono(audio)
    return audio, SESSION['sr']


@app.route('/api/declicker/detect', methods=['POST'])
def declicker_detect():
    """Run click detection only (no repair), return results for visualization."""
    audio, sr = _get_declicker_source_audio()
    if audio is None:
        return jsonify({'error': 'No audio loaded'}), 400

    data = request.get_json(silent=True) or {}
    params = get_default_declicker_params()
    params.update(data)
    SESSION['declicker_params'] = params

    try:
        result = detect_clicks(audio, sr, params)
        SESSION['declicker_detections'] = result
        return jsonify({
            'ok': True,
            'click_count': len(result['clicks']),
            'clicks': result['clicks'],
            'band_centers': result['band_centers'],
            'band_peaks': result['band_peaks'],
            'step_size_s': result['step_size_s'],
            'num_steps': result['num_steps'],
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/declicker/apply', methods=['POST'])
def declicker_apply():
    """Run full de-clicker (multi-pass detect + repair), save repaired audio."""
    audio, sr = _get_declicker_source_audio()
    if audio is None:
        return jsonify({'error': 'No audio loaded'}), 400

    data = request.get_json(silent=True) or {}
    params = get_default_declicker_params()
    params.update(data)
    SESSION['declicker_params'] = params

    try:
        print(f"[declicker/apply] Running declicker on audio shape={audio.shape}, sr={sr}, params={params}")
        repaired, all_passes = run_declicker(audio, sr, params)
        print(f"[declicker/apply] Done: {len(all_passes)} passes, repaired shape={repaired.shape}")

        # Save repaired audio
        path = UPLOAD_DIR / f"declicked_{uuid.uuid4().hex}.wav"
        sf.write(str(path), repaired, int(sr))
        SESSION['declicker_audio'] = repaired
        SESSION['declicker_path'] = str(path)
        print(f"[declicker/apply] Saved to {path}")

        # Collect all detections from all passes
        all_clicks = []
        for p in all_passes:
            all_clicks.extend(p['clicks'])
        SESSION['declicker_detections'] = all_passes[-1] if all_passes else None

        return jsonify({
            'ok': True,
            'click_count': len(all_clicks),
            'clicks': all_clicks,
            'band_centers': all_passes[0]['band_centers'] if all_passes else [],
            'step_size_s': all_passes[0]['step_size_s'] if all_passes else 0,
            'num_passes_run': len(all_passes),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/declicker/apply_selected', methods=['POST'])
def declicker_apply_selected():
    """Repair only specific clicks (by index) without re-detecting."""
    data = request.get_json(silent=True) or {}
    click_indices = data.get('click_indices', [])

    detections = SESSION.get('declicker_detections')
    if not detections or not detections.get('clicks'):
        return jsonify({'error': 'No detections available. Run detect first.'}), 400

    all_clicks = detections['clicks']
    selected = [all_clicks[i] for i in click_indices if i < len(all_clicks)]
    if not selected:
        return jsonify({'error': 'No valid clicks selected'}), 400

    # Always apply from original audio so un-checking clicks takes effect
    base, sr = _get_declicker_source_audio()
    if base is None:
        return jsonify({'error': 'No audio loaded'}), 400

    params = SESSION.get('declicker_params', get_default_declicker_params())
    boundaries = build_frequency_bands(params['freq_low'], params['freq_high'], params['num_bands'])

    try:
        repaired = repair_clicks(base.copy(), sr, selected, boundaries, params)

        path = UPLOAD_DIR / f"declicked_{uuid.uuid4().hex}.wav"
        sf.write(str(path), repaired, int(sr))
        SESSION['declicker_audio'] = repaired
        SESSION['declicker_path'] = str(path)

        # Replace processed clicks with current selection (not additive)
        SESSION['declicker_processed_clicks'] = selected

        return jsonify({
            'ok': True,
            'repaired_count': len(selected),
            'processed_clicks': selected,
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/declicker/process_segment', methods=['POST'])
def declicker_process_segment():
    """Repair specific clicks as a single segment splice into current active audio."""
    data = request.get_json(silent=True) or {}
    click_indices = data.get('click_indices', [])
    padding_ms = float(data.get('padding_ms', 100))
    crop_ms = float(data.get('crop_ms', 50))
    crossfade_ms = float(data.get('crossfade_ms', 10))

    detections = SESSION.get('declicker_detections')
    if not detections or not detections.get('clicks'):
        return jsonify({'error': 'No detections available. Run detect first.'}), 400

    all_clicks = detections['clicks']
    selected = [all_clicks[i] for i in click_indices if i < len(all_clicks)]
    if not selected:
        return jsonify({'error': 'No valid clicks selected'}), 400

    # Use current active audio so successive segment repairs accumulate
    if SESSION.get('declicker_audio') is not None:
        base = SESSION['declicker_audio']
        sr = SESSION.get('declicker_sr')
        if sr is None:
            base, sr = _get_declicker_source_audio()
    else:
        base, sr = _get_declicker_source_audio()

    if base is None:
        return jsonify({'error': 'No audio loaded'}), 400

    params = SESSION.get('declicker_params', get_default_declicker_params())
    boundaries = build_frequency_bands(params['freq_low'], params['freq_high'], params['num_bands'])

    try:
        repaired = repair_clicks_segment(
            base.copy(), sr, selected, boundaries, params,
            padding_ms=padding_ms, crop_ms=crop_ms, crossfade_ms=crossfade_ms
        )

        path = UPLOAD_DIR / f"declicked_{uuid.uuid4().hex}.wav"
        sf.write(str(path), repaired, int(sr))
        SESSION['declicker_audio'] = repaired
        SESSION['declicker_sr'] = sr
        SESSION['declicker_path'] = str(path)

        # Append (accumulate) processed clicks
        existing = SESSION.get('declicker_processed_clicks', [])
        SESSION['declicker_processed_clicks'] = existing + selected

        return jsonify({
            'ok': True,
            'repaired_count': len(selected),
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/declicker/preview', methods=['POST'])
def declicker_preview():
    """Generate isolated clicks audio (original - repaired) for preview."""
    audio, sr = _get_declicker_source_audio()
    if audio is None or SESSION['declicker_audio'] is None:
        return jsonify({'error': 'Run apply first'}), 400

    try:
        diff = isolate_clicks(audio, SESSION['declicker_audio'])
        path = UPLOAD_DIR / f"declicker_preview_{uuid.uuid4().hex}.wav"
        sf.write(str(path), diff, sr)
        return jsonify({'ok': True, 'url': f'/api/declicker/preview_audio?t={uuid.uuid4().hex}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/declicker/preview_audio')
def declicker_preview_audio():
    """Serve the isolated clicks audio for playback."""
    # Find the most recent preview file
    preview_files = sorted(UPLOAD_DIR.glob('declicker_preview_*.wav'))
    if not preview_files:
        return jsonify({'error': 'No preview available'}), 404
    return send_file(str(preview_files[-1]), mimetype='audio/wav')


@app.route('/api/declicker/audio')
def declicker_audio():
    """Serve the declicked audio for playback."""
    if not SESSION['declicker_path'] or not os.path.exists(SESSION['declicker_path']):
        return jsonify({'error': 'No declicked audio available'}), 404
    return send_file(SESSION['declicker_path'], mimetype='audio/wav')


@app.route('/api/declicker/export')
def declicker_export():
    """Download the declicked audio file."""
    if not SESSION['declicker_path'] or not os.path.exists(SESSION['declicker_path']):
        return jsonify({'error': 'No declicked audio to export'}), 404

    original_name = Path(SESSION['audio_path']).stem if SESSION['audio_path'] else 'audio'
    return send_file(
        SESSION['declicker_path'],
        mimetype='audio/wav',
        as_attachment=True,
        download_name=f"{original_name}_declicked.wav"
    )


@app.route('/api/declicker/reset', methods=['POST'])
def declicker_reset():
    """Clear all declicker state."""
    SESSION['declicker_params'] = {}
    SESSION['declicker_detections'] = None
    SESSION['declicker_audio'] = None
    SESSION['declicker_path'] = None
    SESSION['declicker_processed_clicks'] = []
    return jsonify({'ok': True})


##############################################################################
# Denoiser endpoints
##############################################################################

def _get_denoiser_source_audio():
    """Get audio to run denoiser on. Use declicked audio if available, else original."""
    if SESSION.get('declicker_audio') is not None:
        audio = SESSION['declicker_audio']
    elif SESSION['audio'] is not None:
        audio = SESSION['audio']
    else:
        return None, None
    if len(audio.shape) > 1:
        audio = get_audio_mono(audio)
    return audio, SESSION['sr']


def _extract_noise_clip(audio, sr, data):
    """Extract noise clip from audio if noise_start/noise_end are provided."""
    noise_start = data.get('noise_start')
    noise_end = data.get('noise_end')
    if noise_start is not None and noise_end is not None:
        start_sample = int(float(noise_start) * sr)
        end_sample = int(float(noise_end) * sr)
        start_sample = max(0, min(start_sample, len(audio)))
        end_sample = max(start_sample, min(end_sample, len(audio)))
        if end_sample > start_sample:
            return audio[start_sample:end_sample]
    return None


@app.route('/api/denoiser/analyze', methods=['POST'])
def denoiser_analyze():
    """Run denoise + compute spectrograms for visualization (doesn't save)."""
    audio, sr = _get_denoiser_source_audio()
    if audio is None:
        return jsonify({'error': 'No audio loaded'}), 400

    data = request.get_json(silent=True) or {}
    params = get_default_denoise_params()
    params.update({k: v for k, v in data.items() if k in params})
    SESSION['denoiser_params'] = params

    try:
        noise_clip = _extract_noise_clip(audio, sr, data)
        denoised = apply_denoise(audio, sr, params, noise_clip=noise_clip)
        spec_data = compute_spectrograms(audio, denoised, sr, params.get('n_fft', 1024))
        return jsonify({'ok': True, **spec_data})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/denoiser/apply', methods=['POST'])
def denoiser_apply():
    """Run denoise, save to disk, update SESSION."""
    audio, sr = _get_denoiser_source_audio()
    if audio is None:
        return jsonify({'error': 'No audio loaded'}), 400

    data = request.get_json(silent=True) or {}
    params = get_default_denoise_params()
    params.update({k: v for k, v in data.items() if k in params})
    SESSION['denoiser_params'] = params

    try:
        noise_clip = _extract_noise_clip(audio, sr, data)
        print(f"[denoiser/apply] Running denoise on audio shape={audio.shape}, sr={sr}")
        denoised = apply_denoise(audio, sr, params, noise_clip=noise_clip)
        print(f"[denoiser/apply] Done, denoised shape={denoised.shape}")

        path = UPLOAD_DIR / f"denoised_{uuid.uuid4().hex}.wav"
        sf.write(str(path), denoised, int(sr))
        SESSION['denoiser_audio'] = denoised
        SESSION['denoiser_path'] = str(path)
        print(f"[denoiser/apply] Saved to {path}")

        spec_data = compute_spectrograms(audio, denoised, sr, params.get('n_fft', 1024))
        return jsonify({'ok': True, **spec_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/denoiser/audio')
def denoiser_audio():
    """Serve the denoised audio for playback."""
    if not SESSION['denoiser_path'] or not os.path.exists(SESSION['denoiser_path']):
        return jsonify({'error': 'No denoised audio available'}), 404
    return send_file(SESSION['denoiser_path'], mimetype='audio/wav')


@app.route('/api/denoiser/export')
def denoiser_export():
    """Download the denoised audio file."""
    if not SESSION['denoiser_path'] or not os.path.exists(SESSION['denoiser_path']):
        return jsonify({'error': 'No denoised audio to export'}), 404

    original_name = Path(SESSION['audio_path']).stem if SESSION['audio_path'] else 'audio'
    return send_file(
        SESSION['denoiser_path'],
        mimetype='audio/wav',
        as_attachment=True,
        download_name=f"{original_name}_denoised.wav"
    )


@app.route('/api/denoiser/reset', methods=['POST'])
def denoiser_reset():
    """Clear all denoiser state."""
    SESSION['denoiser_params'] = {}
    SESSION['denoiser_audio'] = None
    SESSION['denoiser_path'] = None
    return jsonify({'ok': True})


##############################################################################
# Audio source resolution helpers
##############################################################################

def _get_edit_source_audio_path():
    """Get audio path for the edit tab input: denoiser -> declicker -> raw."""
    if SESSION.get('denoiser_path') and os.path.exists(SESSION['denoiser_path']):
        return SESSION['denoiser_path']
    if SESSION.get('declicker_path') and os.path.exists(SESSION['declicker_path']):
        return SESSION['declicker_path']
    return SESSION.get('audio_path')


def _get_pipeline_audio_path():
    """Get best available audio for pitch/time processing: edit -> denoiser -> declicker -> raw."""
    if SESSION.get('edit_path') and os.path.exists(SESSION['edit_path']):
        return SESSION['edit_path']
    return _get_edit_source_audio_path()


##############################################################################
# Fine Edit endpoints
##############################################################################

@app.route('/api/edit/upload_render', methods=['POST'])
def edit_upload_render():
    """Receive rendered edit audio and clip list from frontend."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    path = UPLOAD_DIR / f"edit_{uuid.uuid4().hex}.wav"
    save_as_wav(file, path)
    data, sr = sf.read(str(path))
    SESSION['edit_audio'] = data
    SESSION['edit_path'] = str(path)
    # Save clip list if provided
    clips_json = request.form.get('clips')
    if clips_json:
        SESSION['edit_clips'] = json.loads(clips_json)
    return jsonify({'ok': True})


@app.route('/api/edit/clips')
def edit_get_clips():
    """Return saved clip list for restoring edits."""
    return jsonify({'ok': True, 'clips': SESSION.get('edit_clips')})


@app.route('/api/edit/reset', methods=['POST'])
def edit_reset():
    """Clear all edit state."""
    SESSION['edit_audio'] = None
    SESSION['edit_path'] = None
    SESSION['edit_clips'] = None
    return jsonify({'ok': True})


@app.route('/api/edit/audio')
def edit_audio():
    """Serve the committed edit output audio."""
    if not SESSION.get('edit_path') or not os.path.exists(SESSION['edit_path']):
        return jsonify({'error': 'No edit audio'}), 404
    return send_file(SESSION['edit_path'], mimetype='audio/wav')


@app.route('/api/edit/source_audio')
def edit_source_audio():
    """Serve the input audio for the edit tab (denoiser -> declicker -> raw)."""
    path = _get_edit_source_audio_path()
    if not path or not os.path.exists(path):
        return jsonify({'error': 'No audio'}), 404
    return send_file(path, mimetype='audio/wav')


##############################################################################
# Project save/load endpoints
##############################################################################

def _serialize_clusters(clusters):
    """Convert clusters to JSON-safe format."""
    result = []
    for c in clusters:
        if isinstance(c, dict):
            result.append(c)
        else:
            result.append({
                'start_time': c.start_time,
                'end_time': c.end_time,
                'note': c.note,
                'mean_freq': c.mean_freq,
                'pitch_shift_semitones': getattr(c, 'pitch_shift_semitones', 0),
                'ramp_in_ms': getattr(c, 'ramp_in_ms', 0),
                'ramp_out_ms': getattr(c, 'ramp_out_ms', 0),
                'correction_strength': getattr(c, 'correction_strength', 1.0),
                'smoothing_percent': getattr(c, 'smoothing_percent', 0),
                'manually_edited': getattr(c, 'manually_edited', False),
                'frequencies': getattr(c, 'frequencies', []),
                'times': getattr(c, 'times', []),
            })
    return result


@app.route('/api/volume/analyze_notes', methods=['POST'])
def volume_analyze_notes():
    """Compute RMS for each note cluster from the corrected audio."""
    if SESSION['audio'] is None:
        return jsonify({'error': 'No audio loaded'}), 400
    if not SESSION['clusters']:
        return jsonify({'error': 'No clusters found. Run analysis first.'}), 400

    audio = SESSION.get('corrected_audio')
    if audio is None:
        audio = SESSION['audio']
    sr = SESSION['sr']
    clusters = SESSION['clusters']

    volume_clusters = []
    for c in clusters:
        rms = compute_rms_db(audio, sr, c['start_time'], c['end_time'])
        c['rms_db'] = round(rms, 2)
        volume_clusters.append({
            'id': c.get('id', 0),
            'start_time': c['start_time'],
            'end_time': c['end_time'],
            'rms_db': c['rms_db'],
            'gain_db': c.get('gain_db', 0.0),
            'manual': False,
        })

    SESSION['volume_clusters'] = volume_clusters
    SESSION['volume_applied'] = False
    return jsonify({'ok': True, 'volume_clusters': volume_clusters})


@app.route('/api/volume/compute_rms', methods=['POST'])
def volume_compute_rms():
    """Compute RMS dB for an arbitrary time range in the corrected audio."""
    if SESSION['audio'] is None:
        return jsonify({'error': 'No audio loaded'}), 400
    data = request.get_json(silent=True) or {}
    start_time = data.get('start_time', 0.0)
    end_time = data.get('end_time', 0.0)
    audio = SESSION.get('corrected_audio')
    if audio is None:
        audio = SESSION['audio']
    sr = SESSION['sr']
    rms = compute_rms_db(audio, sr, start_time, end_time)
    return jsonify({'ok': True, 'rms_db': round(rms, 2)})


@app.route('/api/volume/detect_breaths', methods=['POST'])
def volume_detect_breaths():
    """Auto-detect breath regions in gaps between notes."""
    if SESSION['audio'] is None:
        return jsonify({'error': 'No audio loaded'}), 400
    if not SESSION['clusters']:
        return jsonify({'error': 'No clusters found. Run analysis first.'}), 400

    data = request.get_json(silent=True) or {}
    bp = SESSION['breath_params'].copy()
    bp.update({k: v for k, v in data.items() if k in bp})
    # Include silence threshold from analysis params
    bp['silence_threshold_db'] = SESSION.get('params', {}).get('silence_threshold_db', -55.0)
    SESSION['breath_params'] = bp

    audio = SESSION.get('corrected_audio')
    if audio is None:
        audio = SESSION['audio']
    sr = SESSION['sr']
    clusters = SESSION['clusters']
    frequencies = SESSION.get('frequencies')
    times = SESSION.get('times')

    if frequencies is not None:
        frequencies = np.array(frequencies, dtype=np.float64)
    if times is not None:
        times = np.array(times, dtype=np.float64)

    # Compute per-cluster RMS while we have the audio
    cluster_rms = []
    for c in clusters:
        rms = compute_rms_db(audio, sr, c['start_time'], c['end_time'])
        c['rms_db'] = round(rms, 2)
        cluster_rms.append({'id': c.get('id', 0), 'rms_db': c['rms_db']})

    breaths = detect_breaths(audio, sr, clusters, frequencies, times, bp)
    SESSION['breaths'] = breaths
    SESSION['volume_applied'] = False

    return jsonify({'ok': True, 'breaths': breaths, 'cluster_rms': cluster_rms})


@app.route('/api/volume/create_breath', methods=['POST'])
def volume_create_breath():
    """Manually create a breath at a given click time."""
    if SESSION['audio'] is None:
        return jsonify({'error': 'No audio loaded'}), 400

    data = request.get_json(silent=True) or {}
    click_time = data.get('click_time')
    if click_time is None:
        return jsonify({'error': 'click_time required'}), 400

    audio = SESSION['audio']
    sr = SESSION['sr']
    clusters = SESSION.get('clusters', [])
    frequencies = SESSION.get('frequencies')
    times = SESSION.get('times')

    if frequencies is not None:
        frequencies = np.array(frequencies, dtype=np.float64)
    if times is not None:
        times = np.array(times, dtype=np.float64)

    bp = SESSION['breath_params'].copy()
    bp['silence_threshold_db'] = SESSION.get('params', {}).get('silence_threshold_db', -55.0)

    breath = create_breath_at_point(audio, sr, click_time, clusters, frequencies, times, bp)
    if breath is None:
        return jsonify({'ok': False, 'error': 'Could not detect a valid breath at that location'})

    # Assign a unique id
    existing_ids = {b['id'] for b in SESSION['breaths']}
    new_id = max(existing_ids, default=-1) + 1
    breath['id'] = new_id
    SESSION['breaths'].append(breath)
    SESSION['volume_applied'] = False

    return jsonify({'ok': True, 'breath': breath, 'breaths': SESSION['breaths']})


@app.route('/api/volume/remove_breath', methods=['POST'])
def volume_remove_breath():
    """Remove a breath by id."""
    data = request.get_json(silent=True) or {}
    breath_id = data.get('breath_id')
    if breath_id is None:
        return jsonify({'error': 'breath_id required'}), 400

    SESSION['breaths'] = [b for b in SESSION['breaths'] if b['id'] != breath_id]
    SESSION['volume_applied'] = False

    return jsonify({'ok': True, 'breaths': SESSION['breaths']})


@app.route('/api/volume/sync_volume', methods=['POST'])
def volume_sync_volume():
    """Apply all volume automation: compute gain envelope and process audio."""
    if SESSION['audio'] is None:
        return jsonify({'error': 'No audio loaded'}), 400

    data = request.get_json(silent=True) or {}

    # Update session state from client
    client_breaths = data.get('breaths', SESSION['breaths'])
    SESSION['breaths'] = client_breaths

    client_volume_params = data.get('volume_params', {})
    if client_volume_params:
        SESSION['volume_params'].update(client_volume_params)

    # Sync volume clusters (includes custom boundaries, manual flag, gain_db)
    client_volume_clusters = data.get('volume_clusters', [])
    if client_volume_clusters:
        SESSION['volume_clusters'] = client_volume_clusters

    # Determine source audio (use corrected if available, else raw)
    source_audio = SESSION.get('corrected_audio')
    if source_audio is None:
        source_audio = SESSION['audio']

    sr = SESSION['sr']
    volume_clusters = SESSION.get('volume_clusters') or []
    breaths = SESSION['breaths']
    volume_params = SESSION['volume_params']

    # Recompute rms_db from source audio for all volume clusters
    for vc in volume_clusters:
        vc['rms_db'] = round(compute_rms_db(source_audio, sr, vc['start_time'], vc['end_time']), 2)

    # Check if any gain changes are needed
    effective_gains = compute_effective_gains(volume_clusters, breaths, volume_params)
    all_zero = all(abs(g) < 0.001 for g in effective_gains.values())

    if all_zero:
        SESSION['volume_applied'] = False
        cluster_rms = [{'id': vc.get('id', 0), 'rms_db': vc['rms_db']} for vc in volume_clusters]
        return jsonify({'ok': True, 'message': 'No gain changes needed', 'cluster_rms': cluster_rms})

    audio_length = len(source_audio)
    gain_env = generate_gain_envelope(volume_clusters, breaths, effective_gains, sr, audio_length)
    processed = apply_gain_envelope(source_audio, gain_env)

    # Clamp to [-1, 1]
    processed = np.clip(processed, -1.0, 1.0)

    # Save to temp file
    volume_path = str(UPLOAD_DIR / 'volume_output.wav')
    sf.write(volume_path, processed, int(sr))

    SESSION['volume_audio'] = processed
    SESSION['volume_path'] = volume_path
    SESSION['volume_applied'] = True

    cluster_rms = [{'id': vc.get('id', 0), 'rms_db': vc['rms_db']} for vc in volume_clusters]
    return jsonify({'ok': True, 'cluster_rms': cluster_rms})


@app.route('/api/volume/audio')
def volume_audio():
    """Serve the volume-processed audio."""
    path = SESSION.get('volume_path')
    if not path or not os.path.exists(path):
        # Fall back to corrected audio
        path = SESSION.get('corrected_path')
    if not path or not os.path.exists(path):
        return jsonify({'error': 'No audio available'}), 404
    return send_file(path, mimetype='audio/wav')


@app.route('/api/volume/reset', methods=['POST'])
def volume_reset():
    """Reset all volume automation."""
    SESSION['breaths'] = []
    SESSION['volume_clusters'] = []
    SESSION['volume_audio'] = None
    SESSION['volume_path'] = None
    SESSION['volume_applied'] = False
    SESSION['volume_params'] = {
        'note_min_rms_db': -60.0,
        'note_max_rms_db': 0.0,
        'note_global_offset_db': 0.0,
        'breath_min_rms_db': -60.0,
        'breath_max_rms_db': 0.0,
        'breath_global_offset_db': 0.0,
    }
    for c in SESSION.get('clusters', []):
        c['gain_db'] = 0.0
    return jsonify({'ok': True})


@app.route('/api/save_project', methods=['POST'])
def save_project():
    """Save current project state to a JSON file keyed by audio content hash."""
    audio_hash = SESSION.get('audio_hash')
    if not audio_hash:
        return jsonify({'error': 'No audio loaded'}), 400

    data = request.get_json(silent=True) or {}
    pipeline_status = data.get('pipeline_status', {})

    # Accept volume data from frontend (it owns the canonical state)
    if 'volume_clusters' in data:
        SESSION['volume_clusters'] = data['volume_clusters']
    if 'breaths' in data:
        SESSION['breaths'] = data['breaths']
    if 'volume_params' in data:
        SESSION['volume_params'].update(data['volume_params'])

    project = {
        'audio_hash': audio_hash,
        'original_filename': SESSION.get('original_filename', ''),
        'saved_at': datetime.utcnow().isoformat(),
        'pipeline_status': pipeline_status,
        'declicker_params': SESSION.get('declicker_params', {}),
        'declicker_processed_clicks': SESSION.get('declicker_processed_clicks', []),
        'denoiser_params': SESSION.get('denoiser_params', {}),
        'analysis_params': SESSION.get('params', {}),
        'clusters': _serialize_clusters(SESSION.get('clusters', [])),
        'stretch_markers': SESSION.get('stretch_markers', []),
        'time_edits': SESSION.get('time_edits', []),
        'edit_clips': SESSION.get('edit_clips'),
        'breaths': SESSION.get('breaths', []),
        'volume_clusters': SESSION.get('volume_clusters', []),
        'volume_params': SESSION.get('volume_params', {}),
        'midi_notes': [
            n if isinstance(n, dict) else {
                'start': n.start, 'end': n.end,
                'note': n.note, 'freq': n.freq, 'name': n.name,
            }
            for n in SESSION.get('midi_notes', [])
        ] if SESSION.get('midi_notes') else [],
    }

    project_path = PROJECT_DIR / f"{audio_hash}.json"
    with open(project_path, 'w') as f:
        json.dump(project, f, indent=2)

    return jsonify({'ok': True})


@app.route('/api/check_project')
def check_project():
    """Check if a saved project exists for the currently loaded audio."""
    audio_hash = SESSION.get('audio_hash')
    if not audio_hash:
        return jsonify({'found': False})

    project_path = PROJECT_DIR / f"{audio_hash}.json"
    if not project_path.exists():
        return jsonify({'found': False})

    try:
        with open(project_path) as f:
            project = json.load(f)
        return jsonify({'found': True, 'project': project})
    except Exception:
        return jsonify({'found': False})


if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    app.run(debug=True, host=host, port=5000)
