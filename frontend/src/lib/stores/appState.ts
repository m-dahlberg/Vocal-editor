import { writable, derived } from 'svelte/store';
import type { Cluster, MidiNote, LogMessage } from '$lib/utils/types';

// Audio/analysis state
export const clusters = writable<Cluster[]>([]);
export const times = writable<number[]>([]);
export const frequencies = writable<(number | null)[]>([]);
export const originalTimes = writable<number[]>([]);
export const originalFrequencies = writable<(number | null)[]>([]);
export const midiNotes = writable<MidiNote[]>([]);

// Selection
export const selectedIdx = writable<number | null>(null);
export const selectedIndices = writable<Set<number>>(new Set());

// Dirty tracking
export const dirtyClusters = writable<Set<number>>(new Set());

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
