# Vocal Pitch Editor

A web-based vocal pitch correction application. Upload vocal audio, analyze pitch, and apply corrections — automatic or manual — with optional MIDI reference. Powered by Rubberband for high-quality pitch shifting.

![Screenshot placeholder](docs/screenshot.png)

## Features!

- **Automatic pitch analysis** using Parselmouth/Praat (75–600 Hz range)
- **Note clustering** — detected pitches grouped into musical notes with vibrato tolerance
- **Interactive pitch plot** — drag note boxes to adjust pitch, resize for timing, Ctrl+drag for ramps/smoothing
- **MIDI reference** — upload a MIDI file for guided correction with configurable matching threshold
- **Auto-correct** — one-click correction to nearest semitone or MIDI target
- **Manual fine-tuning** — per-note ramp in/out, smoothing, and correction strength
- **Real-time preview** — pitch curve updates instantly as you edit, before processing
- **High-quality processing** — Rubberband with formant preservation, configurable crisp/window/quality settings
- **Export** — download corrected audio as WAV

## Quick Start with Docker

```bash
docker compose up --build
```

Open http://localhost:5000 in your browser.

To stop:

```bash
docker compose down
```

## Manual Setup

### Prerequisites

- Python 3.9+
- `rubberband-cli` (Rubberband R3)

Install system dependencies (Ubuntu/Debian):

```bash
sudo apt-get install rubberband-cli libsndfile1
```

### Install and Run

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 in your browser.

## Usage

1. **Upload audio** — Click **Audio** to load a vocal file (WAV, MP3, FLAC, or AIFF). Pitch analysis runs automatically.
2. **Upload MIDI (optional)** — Click **MIDI** to load a reference MIDI file for guided correction.
3. **Auto-correct** — Click **Correct** to calculate pitch corrections for all clusters.
4. **Manual editing** — Drag note boxes to adjust pitch, resize edges for timing, Ctrl+drag for ramps and smoothing.
5. **Update Audio** — Click **Update Audio** to process corrections with Rubberband.
6. **Preview** — Press **Space** to play/pause.
7. **Export** — Click **Export** to download the corrected WAV.

### Keyboard Shortcuts

| Key | Action |
|---|---|
| **Space** | Play / Pause |
| **Delete / Backspace** | Delete selected cluster |
| **Shift + Click** | Multi-select clusters |
| **Alt + Drag** | Draw new cluster |
| **Ctrl + Drag edge** | Adjust ramp in/out |
| **Ctrl + Drag body** | Adjust smoothing |
| **Scroll** | Zoom time axis |
| **Shift + Scroll** | Zoom frequency axis |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/upload_audio` | Upload vocal audio file |
| POST | `/api/upload_midi` | Upload MIDI reference file |
| POST | `/api/analyze` | Run pitch analysis |
| POST | `/api/correct` | Auto-correct all clusters |
| POST | `/api/correct_cluster` | Correct a single cluster |
| POST | `/api/sync_clusters` | Sync client edits and process audio |
| POST | `/api/analyze_segment` | Re-analyze a specific time range |
| GET | `/api/audio` | Serve corrected audio |
| GET | `/api/export` | Download final WAV |

## Architecture

**Backend:** Flask → Audio Engine (Parselmouth + Rubberband CLI)

**Frontend:** Vanilla JS modules, Plotly.js (pitch plot), WaveSurfer.js (waveform playback)

```
app.py              — Flask routes and session management
audio_engine.py     — Pitch analysis, clustering, correction algorithms, Rubberband wrapper
static/js/main.js   — App state and interaction handling
static/js/pitch_plot.js — Interactive Plotly pitch visualization
static/js/waveform.js   — WaveSurfer.js audio playback
static/js/sine_player.js — Web Audio sine tone preview
static/js/api.js         — HTTP client for backend calls
templates/index.html     — Single-page UI
```

## Technical Details

- **Pitch range:** 75–600 Hz
- **Max upload size:** 100 MB
- **Output format:** WAV
- **Pitch map resolution:** 5 ms grid (upsampled for Rubberband accuracy)
- **Clustering:** Semitone-based with wobble detection (vibrato tolerance) and silence bridging
- **Single-user session model** — not designed for concurrent users
- **Temp files:** stored in `/tmp/vocal_editor/`
