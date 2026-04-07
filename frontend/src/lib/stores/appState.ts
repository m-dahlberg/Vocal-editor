import { writable, derived } from 'svelte/store';
import type { Cluster, Breath, VolumeCluster, MidiNote, MidiWarning, LogMessage, TimeEdit, TimemapEntry, StretchMarker, DeclickerDetection, EditClip } from '$lib/utils/types';

// Audio/analysis state
export const clusters = writable<Cluster[]>([]);
export const times = writable<number[]>([]);
export const frequencies = writable<(number | null)[]>([]);
export const originalTimes = writable<number[]>([]);
export const originalFrequencies = writable<(number | null)[]>([]);
export const midiNotes = writable<MidiNote[]>([]);
export const midiWarnings = writable<MidiWarning[]>([]);

// Reference audio
export const referenceClusters = writable<Cluster[]>([]);
export const referenceStretchMarkers = writable<StretchMarker[]>([]);
export const referenceLoaded = writable(false);

// Backing track
export const backingLoaded = writable(false);

// Mixer volumes
export const mainVolume = writable(1.0);
export const referenceVolume = writable(0.5);
export const backingVolume = writable(0.5);

// Selection
export const selectedIdx = writable<number | null>(null);
export const selectedIndices = writable<Set<number>>(new Set());

// Dirty tracking
export const dirtyClusters = writable<Set<number>>(new Set());

// Tab state
export const activeTab = writable<'declicker' | 'denoise' | 'edit' | 'pitch' | 'time' | 'volume'>('declicker');

// Pipeline state management
export type PipelineStep = 'declicker' | 'denoise' | 'edit' | 'pitchtime' | 'volume';
export type StepStatus = 'idle' | 'done' | 'stale';

export const pipelineStatus = writable<Record<PipelineStep, StepStatus>>({
  declicker: 'idle',
  denoise: 'idle',
  edit: 'idle',
  pitchtime: 'idle',
  volume: 'idle',
});

export const hasStaleSteps = derived(pipelineStatus, ($ps) =>
  Object.values($ps).some(s => s === 'stale')
);

const PIPELINE_ORDER: PipelineStep[] = ['declicker', 'denoise', 'edit', 'pitchtime', 'volume'];

export function markDownstreamStale(fromStep: PipelineStep) {
  pipelineStatus.update(ps => {
    const idx = PIPELINE_ORDER.indexOf(fromStep);
    const updated = { ...ps };
    for (let i = idx + 1; i < PIPELINE_ORDER.length; i++) {
      if (updated[PIPELINE_ORDER[i]] === 'done') {
        updated[PIPELINE_ORDER[i]] = 'stale';
      }
    }
    return updated;
  });
}

export function markStepDone(step: PipelineStep) {
  pipelineStatus.update(ps => ({ ...ps, [step]: 'done' }));
  markDownstreamStale(step);
}

export function markStepIdle(step: PipelineStep) {
  pipelineStatus.update(ps => ({ ...ps, [step]: 'idle' }));
  markDownstreamStale(step);
}

export function resetPipelineStatus() {
  pipelineStatus.set({ declicker: 'idle', denoise: 'idle', edit: 'idle', pitchtime: 'idle', volume: 'idle' });
}

// Declicker state
export const declickerDetections = writable<DeclickerDetection[]>([]);
export const declickerBandCenters = writable<number[]>([]);
export const declickerBandPeaks = writable<number[][]>([]);
export const declickerApplied = writable(false);
export const selectedClickIdx = writable<number | null>(null);
export const declickerCheckedIndices = writable<Set<number>>(new Set());
export const declickerProcessedClicks = writable<DeclickerDetection[]>([]);
export const declickerFilterState = writable({
  minRatioDb: 0,
  minLengthMs: 0,
  freqLowHz: 20,
  freqHighHz: 20000,
});
export const declickerVisibleIndices = derived(
  [declickerDetections, declickerFilterState, declickerBandCenters],
  ([$dets, $filter, $bands]) => {
    return $dets.reduce<number[]>((acc, click, i) => {
      if (click.max_ratio_db < $filter.minRatioDb) return acc;
      const ms = (click.end_time - click.start_time) * 1000;
      if (ms < $filter.minLengthMs) return acc;
      if ($bands.length > 0) {
        const hasVisibleBand = click.bands.some(b =>
          b < $bands.length && $bands[b] >= $filter.freqLowHz && $bands[b] <= $filter.freqHighHz
        );
        if (!hasVisibleBand) return acc;
      }
      acc.push(i);
      return acc;
    }, []);
  }
);

// Denoiser state
export const denoiserApplied = writable(false);
export const denoiserHeatmapRange = writable(0);  // dB offset: 0 = full range, positive = compress range (boost quiet)
export const denoiserSpectrogramBefore = writable<number[][] | null>(null);
export const denoiserSpectrogramAfter = writable<number[][] | null>(null);
export const denoiserFreqAxis = writable<number[] | null>(null);
export const denoiserTimeAxis = writable<number[] | null>(null);

// Fine Edit state
export const editClips = writable<EditClip[]>([]);
export const editSelectedClipIds = writable<Set<string>>(new Set());
export const editAudioBuffer = writable<AudioBuffer | null>(null);
export const editApplied = writable(false);
export const editCursorTime = writable(0);
export const editTimeSelection = writable<{ start: number; end: number } | null>(null);

// Time alignment edits (legacy)
export const timeEdits = writable<TimeEdit[]>([]);
export const dirtyTimeEdits = writable<Set<number>>(new Set());

// Stretch markers (new time alignment model)
export const stretchMarkers = writable<StretchMarker[]>([]);
export const dirtyStretchMarkers = writable(false);
export const selectedMarkerIdx = writable<number | null>(null);

// Actual backend timemap (from last sync_time_edits response)
export const backendTimemap = writable<TimemapEntry[]>([]);

// Shared view range (synced between pitch and time tabs)
export const viewXRange = writable<[number, number]>([0, 10]);

// Signal to force waveform redraw (incremented on new file upload)
export const waveformReset = writable(0);

// View mode
export const advancedView = writable(false);

// UI state
export const audioLoaded = writable(false);
export const midiLoaded = writable(false);
export const audioUrl = writable<string | null>(null);
export const processing = writable(false);
export const showHelp = writable(false);
export const showMidi = writable(true);
export const showCorrectionCurve = writable(false);
export const fileStatus = writable('');
export const avgPitchDeviation = writable<number | null>(null);

// Log
export const logMessages = writable<LogMessage[]>([]);

export function log(msg: string, type: LogMessage['type'] = 'info') {
  const ts = new Date().toLocaleTimeString('en', { hour12: false });
  logMessages.update(msgs => [...msgs, { text: msg, type, timestamp: ts }]);
}

// Volume automation state
export const breaths = writable<Breath[]>([]);
export const volumeClusters = writable<VolumeCluster[]>([]);
export const selectedBreathIdx = writable<number | null>(null);
export const dirtyVolume = writable(false);
export const volumeApplied = writable(false);
export const volumeMacroParams = writable({
  note_min_rms_db: -60,
  note_max_rms_db: 0,
  note_global_offset_db: 0,
  breath_min_rms_db: -60,
  breath_max_rms_db: 0,
  breath_global_offset_db: 0,
});

// Derived: selected cluster object
export const selectedCluster = derived(
  [clusters, selectedIdx],
  ([$clusters, $selectedIdx]) => {
    if ($selectedIdx === null || $selectedIdx >= $clusters.length) return null;
    return $clusters[$selectedIdx];
  }
);
