# Vocal Pitch Editor — User Guide

## Getting Started

1. **Upload audio** — Click the **Audio** button to load a vocal file (WAV, MP3, FLAC, or AIFF). Pitch analysis runs automatically after upload.
2. **Upload MIDI (optional)** — Click the **MIDI** button to load a reference MIDI file. This provides target pitches for correction and shows green reference lines on the plot.
3. **Review the pitch plot** — The blue line shows detected pitch over time. Orange boxes represent detected note clusters.
4. **Auto-correct** — Click **Correct** to calculate pitch corrections for all clusters. This does not process audio yet — it only calculates the shifts.
5. **Manual editing** — Fine-tune individual notes by dragging boxes, adjusting ramps, and smoothing (see Pitch Plot Controls below).
6. **Update Audio** — Click **Update Audio** to apply all edits. The backend processes the audio with Rubberband and the waveform updates.
7. **Preview** — Use the play/pause controls or press **Space** to listen.
8. **Export** — Click **Export** to download the corrected audio as a WAV file.

---

## Pitch Plot Display

- **Blue line** — Detected pitch. Updates in real-time as you edit to preview corrections.
- **Orange boxes** — Note clusters, labeled with cluster number and note name (e.g. `1:A4`). Selected clusters turn red/pink.
- **Green lines** — MIDI reference notes (toggle with the MIDI checkbox in the header).
- **Orange curve** — Correction amount in cents (toggle with the Correction checkbox in the header). Uses a secondary Y-axis on the right.
- **Red dotted line** — Playhead position during playback.

---

## Pitch Plot Controls

### Selecting Notes
- **Click a box** — Select that cluster (deselects others). Details appear in the right panel.
- **Shift + Click a box** — Add/remove from multi-selection.
- **Drag on empty space** — Draw a selection rectangle to select multiple clusters.
- **Click empty space** — Clear selection.

### Adjusting Pitch
- **Drag a box up/down** — Shift the pitch of that cluster. If multiple clusters are selected, all move together. A sine tone preview plays after a short hold to give pitch feedback.

### Adjusting Timing
- **Drag the left/right edge of a box** — Resize the cluster's start or end time. The cursor changes to a resize icon when near an edge.

### Adjusting Ramps
- **Ctrl + Drag the left edge** — Adjust ramp-in duration (how gradually the correction fades in).
- **Ctrl + Drag the right edge** — Adjust ramp-out duration (how gradually the correction fades out).
- Applies to all selected clusters when multiple are selected.

### Adjusting Smoothing
- **Ctrl + Drag the body of a box vertically** — Adjust smoothing for that cluster. Drag up to increase, down to decrease. Applies to all selected clusters.

### Drawing New Clusters
- **Alt + Drag on empty space** — Draw a new note cluster. A dashed preview rectangle appears while dragging. The new cluster cannot overlap existing ones.

### Deleting Clusters
- **Select a cluster, then press Delete or Backspace** — Removes the cluster and restores the original audio for that segment.

### Navigation
- **Scroll** — Zoom the time axis (centered on cursor).
- **Shift + Scroll** — Zoom the frequency axis.
- **Ctrl + Shift + Drag on empty space** — Pan the view.
- **Reset View button (⟲)** — Reset zoom to show the full audio.

---

## Right Panel — Selected Note Details

When a cluster is selected, the right panel shows:

- **Note name**, start/end time, duration, mean frequency, pitch variation, and current correction in cents.
- **Edited flag** — Whether the cluster has been manually modified. Auto-correct skips manually edited clusters, preserving your adjustments.

### Per-Note Sliders

| Control | Range | Description |
|---|---|---|
| **Ramp In (ms)** | 0–1000 | How gradually the pitch correction fades in at the start of the note. Higher values create smoother transitions. |
| **Ramp Out (ms)** | 0–1000 | How gradually the pitch correction fades out at the end of the note. |
| **Smoothing (%)** | 0–100 | Reduces pitch variation (vibrato/wobble) within the note. 0% preserves the original variation, 100% flattens pitch to the cluster mean. |

Changes preview instantly on the blue pitch line. Click **Update Audio** to apply.

---

## Left Panel — Parameters

### Analysis Parameters

These control how pitch is detected and how note clusters are formed. Click **Re-analyze** after changing these.

| Parameter | Description |
|---|---|
| **Min Freq (Hz)** | Lowest pitch to detect. Raise if low-frequency noise causes false detections. |
| **Max Freq (Hz)** | Highest pitch to detect. |
| **Time Resolution (ms)** | Analysis hop size. Lower values give finer detail but slower analysis. |
| **Freq Tolerance (cents)** | How far a pitch frame can deviate from a semitone center and still be grouped into that note cluster. |
| **Min Note Duration (ms)** | Clusters shorter than this are discarded. Raise to filter out brief glitches. |
| **Max Gap to Bridge (ms)** | Maximum silence gap between same-note clusters to merge them into one. Useful for notes with brief interruptions. |
| **Silence Threshold (dB)** | RMS level below which audio is considered silence. Affects gap bridging — only true silence gaps are candidates for merging. |

### Correction Parameters

These affect auto-correction behavior when you click **Correct**.

| Parameter | Description |
|---|---|
| **Transition Ramp (ms)** | Default ramp in/out duration applied to each cluster during auto-correct and when drawing new clusters. |
| **Correction Strength (%)** | How far toward the target note the correction pulls. 100% = full correction to exact pitch. Lower values leave some natural variation. |
| **MIDI Threshold (cents)** | When MIDI is loaded: if a cluster is within this distance of a MIDI note, the MIDI note becomes the target. Otherwise, the nearest semitone is used. |
| **Auto Smooth (%)** | Smoothing percentage automatically applied during auto-correct. |
| **Smooth Threshold (cents)** | Auto-smooth only applies to clusters with pitch variation exceeding this value. 0 = apply to all. |
| **Smooth Threshold (ms)** | Auto-smooth only applies to clusters longer than this duration. 0 = apply to all. |
| **Smooth Curve** | Shape of the smoothing curve. 1.0 = linear (uniform reduction). Values above 1.0 correct large deviations more aggressively while leaving small ones mostly intact. |

### Rubberband Parameters

These control the Rubberband audio processing engine.

| Parameter | Description |
|---|---|
| **Crisp Level (0–6)** | Transient handling. Higher = sharper transients, lower = smoother. |
| **Formant** | Preserve vocal formants during pitch shifting. Keeps the voice sounding natural rather than "chipmunked." |
| **Pitch HQ** | High-quality pitch shifting mode. |
| **Window Long** | Use longer analysis windows. Better for sustained vocal notes. |
| **Smoothing** | Rubberband's internal time-domain smoothing. |

---

## MIDI Reference

Uploading a MIDI file provides a pitch reference for correction:

- **Green lines** on the pitch plot show MIDI note positions and timing.
- **Avg Pitch Deviation** (shown after analysis) reports how far the vocal is from the MIDI reference on average.
- **Auto-correct with MIDI** matches each vocal cluster to the closest overlapping MIDI note. If the cluster is within the MIDI Threshold, the MIDI note becomes the correction target. Otherwise, the nearest semitone is used.
- **Without MIDI**, auto-correct simply snaps each cluster to its nearest semitone.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| **Space** | Play / Pause |
| **Delete / Backspace** | Delete selected cluster |

---

## Tips

- **Auto-correct first, then fine-tune** — Use Correct to get a baseline, then manually drag individual notes that need adjustment.
- **Manual edits are preserved** — Re-running Correct will skip clusters you've manually edited.
- **Preview before processing** — The blue pitch line updates instantly as you edit, showing what the corrected pitch will look like before you click Update Audio.
- **Use smoothing sparingly** — A little smoothing (20–40%) can tighten a performance while keeping it natural. High smoothing removes vibrato entirely.
- **Ramps prevent artifacts** — Transition ramps smooth the boundary between corrected and uncorrected segments. If you hear clicks or jumps at note boundaries, try increasing ramp values.
