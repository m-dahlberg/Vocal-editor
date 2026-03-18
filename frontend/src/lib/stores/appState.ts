import { writable, derived } from 'svelte/store';
import type { Cluster, MidiNote, LogMessage, TimeEdit, TimemapEntry } from '$lib/utils/types';

// Audio/analysis state
export const clusters = writable<Cluster[]>([]);
export const times = writable<number[]>([]);
export const frequencies = writable<(number | null)[]>([]);
export const originalTimes = writable<number[]>([]);
export const originalFrequencies = writable<(number | null)[]>([]);
export const midiNotes = writable<MidiNote[]>([]);

// Reference audio
export const referenceClusters = writable<Cluster[]>([]);
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
export const activeTab = writable<'pitch' | 'time'>('pitch');

// Time alignment edits
export const timeEdits = writable<TimeEdit[]>([]);
export const dirtyTimeEdits = writable<Set<number>>(new Set());

// Actual backend timemap (from last sync_time_edits response)
export const backendTimemap = writable<TimemapEntry[]>([]);

// Shared view range (synced between pitch and time tabs)
export const viewXRange = writable<[number, number]>([0, 10]);

// Signal to force waveform redraw (incremented on new file upload)
export const waveformReset = writable(0);

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

// Derived: selected cluster object
export const selectedCluster = derived(
  [clusters, selectedIdx],
  ([$clusters, $selectedIdx]) => {
    if ($selectedIdx === null || $selectedIdx >= $clusters.length) return null;
    return $clusters[$selectedIdx];
  }
);
