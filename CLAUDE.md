# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vocal pitch correction web application. Users upload vocal audio, analyze pitch, and apply corrections (auto or manual) with optional MIDI reference.

## Running the App

```bash
docker compose up --build
# Frontend at http://localhost:3000
# Backend at http://localhost:5000
```

## After Making Changes

**Always rebuild and restart the affected service(s) before returning to the user**, so the latest changes are live:

```bash
# Rebuild and restart a specific service
docker compose up --build frontend
docker compose up --build backend

# Or rebuild both
docker compose up --build
```

## Architecture

**Backend:** `backend/` — Flask (app.py) → Audio Engine (audio_engine.py) → Rubberband CLI subprocess

**Frontend:** `frontend/` — SvelteKit + TypeScript, Plotly.js for pitch visualization, WaveSurfer.js for waveform playback. Proxies all `/api/*` requests to the backend via `hooks.server.ts`.

### Backend

- `backend/app.py` — Flask routes, session management, file handling. Single-user in-memory `SESSION` dict holds all state.
- `backend/audio_engine.py` — Pitch analysis (Parselmouth/Praat), note clustering by semitone, pitch correction algorithms (MIDI-aware, standard, smoothing), pitch map generation.

### Frontend Modules

- `src/hooks.server.ts` — Proxies `/api/*` requests to the Flask backend (`API_BACKEND` env var)
- `src/lib/api.ts` — Fetch-based HTTP client for all backend calls
- `src/lib/components/` — Svelte components (PitchPlot, WaveformPlayer, ClusterPanel, etc.)
- `src/lib/stores/` — App state (appState.ts, params.ts)

### Data Flow

1. Upload audio → backend analyzes pitch (Parselmouth) → returns time/frequency data
2. Backend clusters frequencies into musical notes (semitone buckets)
3. Frontend renders clusters as draggable boxes on pitch plot
4. User adjusts corrections (pitch shift, smoothing, ramps) per cluster
5. Client syncs edits via `/api/sync_clusters` → backend generates pitch map
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
- Max upload: 100MB (enforced by both Flask and the SvelteKit Node adapter via `BODY_SIZE_LIMIT`)
- Output format: WAV
- Clustering uses wobble detection (vibrato tolerance) and silence bridging
