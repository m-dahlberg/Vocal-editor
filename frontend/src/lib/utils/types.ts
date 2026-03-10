export interface Cluster {
  id?: number;
  note: string;
  start_time: number;
  end_time: number;
  mean_freq: number;
  duration_ms: number;
  pitch_shift_semitones: number;
  ramp_in_ms: number;
  ramp_out_ms: number;
  correction_strength: number;
  smoothing_percent: number;
  manually_edited: boolean;
  pitch_variation_cents?: number;
  times?: number[];
  frequencies?: number[];
}

export interface MidiNote {
  note: string;
  frequency: number;
  start_time: number;
  end_time: number;
  duration: number;
}

export interface AnalysisResult {
  ok: boolean;
  error?: string;
  traceback?: string;
  duration: number;
  sr: number;
  cluster_count: number;
  clusters: Cluster[];
  times: number[];
  frequencies: (number | null)[];
  midi_notes: MidiNote[];
  avg_pitch_deviation_cents: number | null;
}

export interface CorrectResult {
  ok: boolean;
  error?: string;
  clusters: Cluster[];
}

export interface SyncResult {
  ok: boolean;
  error?: string;
  clusters: Cluster[];
  corrected_times?: number[];
  corrected_freqs?: (number | null)[];
}

export interface SegmentResult {
  ok: boolean;
  error?: string;
  times: number[];
  frequencies: (number | null)[];
  start_time: number;
  end_time: number;
}

export interface UploadResult {
  ok: boolean;
  error?: string;
  filename?: string;
  message?: string;
  note_count?: number;
}

export type LogType = 'info' | 'warn' | 'error';

export interface LogMessage {
  text: string;
  type: LogType;
  timestamp: string;
}

export interface Params {
  min_frequency: number;
  max_frequency: number;
  time_resolution_ms: number;
  frequency_tolerance_cents: number;
  min_note_duration_ms: number;
  max_gap_to_bridge_ms: number;
  silence_threshold_db: number;
  transition_ramp_ms: number;
  gap_threshold_ms: number;
  correction_strength: number;
  midi_threshold_cents: number;
  autocorrect_smoothing: number;
  smoothing_threshold_cents: number;
  smoothing_threshold_ms: number;
  smooth_curve: number;
  rb: RubberbandParams;
}

export interface RubberbandParams {
  command: string;
  crisp: number;
  formant: boolean;
  pitch_hq: boolean;
  window_long: boolean;
  smoothing: boolean;
}

export interface TimeEdit {
  clusterIdx: number;
  newStart: number;
  newEnd: number;
}

export interface TimeStretchResult {
  ok: boolean;
  error?: string;
}
