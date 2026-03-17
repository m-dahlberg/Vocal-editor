import { writable, get } from 'svelte/store';
import type { Params } from '$lib/utils/types';

export const params = writable<Params>({
  min_frequency: 75,
  max_frequency: 600,
  time_resolution_ms: 20,
  frequency_tolerance_cents: 100,
  min_note_duration_ms: 100,
  max_gap_to_bridge_ms: 500,
  silence_threshold_db: -30,
  transition_ramp_ms: 50,
  gap_threshold_ms: 150,
  correction_strength: 90,
  midi_threshold_cents: 80,
  autocorrect_smoothing: 0,
  smoothing_threshold_cents: 0,
  smoothing_threshold_ms: 0,
  smooth_curve: 1.0,
  segment_padding_ms: 300,
  segment_crossfade_ms: 10,
  segment_crop_ms: 50,
  segment_neighbor_count: 0,
  segment_auto_process: true,
  max_note_stretch: 200,
  max_note_compress: 50,
  max_gap_stretch: 300,
  max_gap_compress: 50,
  rb: {
    command: 'rubberband-r3',
    crisp: 3,
    formant: true,
    pitch_hq: true,
    window_long: true,
    smoothing: true,
    enable_pitchmap: true,
    enable_timemap: true,
  },
});

export function getAllParams(): Params {
  return get(params);
}
