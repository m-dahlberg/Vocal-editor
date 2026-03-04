# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vocal pitch correction web application. Users upload vocal audio, analyze pitch, and apply corrections (auto or manual) with optional MIDI reference. Uses Rubberband for pitch shifting.

## Running the App

```bash
pip install -r requirements.txt
python app.py
# Opens at http://localhost:5000
```

**System dependency:** `rubberband-r3` CLI tool must be installed (`sudo apt-get install rubberband-cli`).

## Architecture

**Backend:** Flask (app.py) → Audio Engine (audio_engine.py) → Rubberband CLI subprocess

**Frontend:** Vanilla JS modules (no framework), Plotly.js for pitch visualization, WaveSurfer.js for waveform playback.

### Backend

- `app.py` — Flask routes, session management, file handling. Single-user in-memory `SESSION` dict holds all state.
- `audio_engine.py` — Pitch analysis (Parselmouth/Praat), note clustering by semitone, pitch correction algorithms (MIDI-aware, standard, smoothing), pitch map generation, Rubberband wrapper.

### Frontend Modules

- `main.js` — App state coordination, user interaction handling, cluster management
- `pitch_plot.js` — Plotly-based pitch visualization with draggable note boxes, MIDI overlay, correction curves
- `waveform.js` — WaveSurfer.js integration for audio playback with synchronized playhead
- `sine_player.js` — Web Audio API sine tone preview
- `api.js` — Fetch-based HTTP client for all backend calls

### Data Flow

1. Upload audio → backend analyzes pitch (Parselmouth) → returns time/frequency data
2. Backend clusters frequencies into musical notes (semitone buckets)
3. Frontend renders clusters as draggable boxes on pitch plot
4. User adjusts corrections (pitch shift, smoothing, ramps) per cluster
5. Client syncs edits via `/api/sync_clusters` → backend generates pitch map → Rubberband processes audio
6. Client fetches/plays corrected audio via `/api/audio`

### Key API Endpoints

- `POST /api/upload_audio`, `/api/upload_midi` — File uploads
- `POST /api/analyze` — Run pitch analysis
- `POST /api/correct` — Auto-correct all clusters
- `POST /api/correct_cluster` — Correct single note
- `POST /api/sync_clusters` — Sync all client edits to server and process
- `POST /api/analyze_segment` — Re-analyze specific time range
- `GET /api/audio` — Serve corrected audio
- `GET /api/export` — Download final audio

## Key Technical Details

- Single-user session model (not suitable for concurrent users)
- Temp files stored in `/tmp/vocal_editor/`
- Max upload: 100MB
- Pitch range: 75-600 Hz
- Output format: WAV
- Rubberband pitch map upsampled to 5ms grid for accuracy
- Clustering uses wobble detection (vibrato tolerance) and silence bridging
