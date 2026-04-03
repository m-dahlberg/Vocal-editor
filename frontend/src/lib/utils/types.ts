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

export interface MidiWarning {
  type: 'mismatch' | 'missing';
  cluster_idx?: number;
  cluster_note?: string;
  midi_note: string;
  midi_freq: number;
  start_time: number;
  end_time: number;
  cents_off?: number;
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
  warnings?: MidiWarning[];
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
  // Time auto-correct params
  time_match_max_distance_ms: number;  // max distance (ms) between MIDI note change and marker to consider a match
  time_match_strength: number;         // 0-100% how far to move marker toward reference
  time_match_max_change_ms: number;    // max allowed change per marker (ms)
  cluster_padding_ms: number;          // padding (ms) from cluster edges for stretch markers
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

export interface DeclickerDetection {
  step_idx: number;
  start_time: number;
  end_time: number;
  bands: number[];
  max_ratio_db: number;
  is_crackle: boolean;
}

export interface DeclickerResult {
  ok: boolean;
  error?: string;
  click_count: number;
  clicks: DeclickerDetection[];
  band_centers: number[];
  band_peaks?: number[][];
  step_size_s: number;
  num_steps?: number;
  num_passes_run?: number;
}

export interface DeclickerParams {
  num_passes: number;
  sensitivity_db: number;
  step_size_ms: number;
  max_click_length_steps: number;
  min_separation_steps: number;
  dense_threshold_db: number;
  freq_low: number;
  freq_high: number;
  num_bands: number;
  crossfade_ms: number;
}

export interface TimeEdit {
  clusterIdx: number;
  newStart: number;
  newEnd: number;
}

export interface StretchMarker {
  id: string;
  originalTime: number;
  currentTime: number;
  leftClusterIdx: number;
  rightClusterIdx: number;
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

export interface DenoiserParams {
  stationary: boolean;
  prop_decrease: number;
  time_constant_s: number;
  freq_mask_smooth_hz: number;
  time_mask_smooth_ms: number;
  n_fft: number;
  noise_start?: number | null;
  noise_end?: number | null;
}

export interface DenoiserResult {
  ok: boolean;
  error?: string;
  spectrogram_before?: number[][];
  spectrogram_after?: number[][];
  freq_axis?: number[];
  time_axis?: number[];
}
