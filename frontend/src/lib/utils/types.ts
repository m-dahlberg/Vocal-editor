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
  note_name: string;
  note_number: number;
  frequency: number;
  start_time: number;
  end_time: number;
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
  timemap?: TimemapEntry[];
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
  segment_padding_ms: number;
  segment_crossfade_ms: number;
  segment_crop_ms: number;
  segment_neighbor_count: number;
  segment_auto_process: boolean;
  max_note_stretch: number;     // max stretch as % of original (e.g. 200 = 2x)
  max_note_compress: number;    // min size as % of original (e.g. 50 = can halve)
  max_gap_stretch: number;      // max stretch as % of original
  max_gap_compress: number;     // min size as % of original (0 = can fully remove)
  voicing_threshold: number;
  rb: RubberbandParams;
  pitch_engine: PitchEngine;
  sms: SMSParams;
  psola: PSOLAParams;
  fd_psola: FDPSOLAParams;
}

export interface RubberbandParams {
  command: string;
  crisp: number;
  formant: boolean;
  pitch_hq: boolean;
  window_long: boolean;
  smoothing: boolean;
  enable_pitchmap: boolean;
  enable_timemap: boolean;
}

export interface SMSParams {
  max_harmonics: number;
  peak_threshold: number;
  stochastic_factor: number;
  timbre_preserve: boolean;
  hop_size: number;
  synth_fft_size: number;
  f0_error_threshold: number;
  harm_dev_slope: number;
  min_sine_dur: number;
  residual_level: number;
}

export interface PSOLAParams {
  min_pitch: number;
  max_pitch: number;
  time_step: number;
  resynthesis_method: string;
  pitch_point_step: number;
  pitch_smooth_window_ms: number;
  max_shift_semitones: number;
}

export interface FDPSOLAParams {
  fft_size: number;
  window_type: string;
  formant_preservation: boolean;
  formant_method: string;
  envelope_order: number;
  overlap_factor: number;
  phase_mode: string;
  min_pitch: number;
  max_pitch: number;
  kaiser_beta: number;
}

export type PitchEngine = 'rubberband' | 'sms' | 'psola' | 'fd_psola';

export interface TimeEdit {
  clusterIdx: number;
  newStart: number;
  newEnd: number;
}

export interface TimemapEntry {
  source_s: number;
  target_s: number;
}

export interface TimeStretchResult {
  ok: boolean;
  error?: string;
  timemap?: TimemapEntry[];
}
