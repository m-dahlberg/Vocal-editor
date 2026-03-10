import type { AnalysisResult, CorrectResult, SyncResult, SegmentResult, UploadResult, Params, Cluster, TimeEdit, TimeStretchResult } from '$lib/utils/types';

async function post(url: string, body?: object): Promise<any> {
  const opts: RequestInit = { method: 'POST' };
  if (body) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  return r.json();
}

export async function uploadAudio(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch('/api/upload_audio', { method: 'POST', body: fd });
  return r.json();
}

export async function uploadMidi(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch('/api/upload_midi', { method: 'POST', body: fd });
  return r.json();
}

export async function analyze(params: Params): Promise<AnalysisResult> {
  return post('/api/analyze', params);
}

export async function correct(params: Params): Promise<CorrectResult> {
  return post('/api/correct', params);
}

export async function correctCluster(clusterIdx: number, updates: Partial<Cluster>): Promise<any> {
  return post('/api/correct_cluster', { cluster_idx: clusterIdx, ...updates });
}

export async function analyzeSegment(startTime: number, endTime: number): Promise<SegmentResult> {
  return post('/api/analyze_segment', { start_time: startTime, end_time: endTime });
}

export async function deleteCluster(clusterIdx: number): Promise<any> {
  return post('/api/delete_cluster', { cluster_idx: clusterIdx });
}

export async function syncClusters(clusterList: Partial<Cluster>[]): Promise<SyncResult> {
  return post('/api/sync_clusters', { clusters: clusterList });
}

export async function resetEdits(): Promise<any> {
  return post('/api/reset_edits');
}

export async function updateCluster(clusterIdx: number, updates: Partial<Cluster>): Promise<any> {
  return post('/api/update_cluster', { cluster_idx: clusterIdx, ...updates });
}

export function audioUrl(): string {
  return `/api/audio?t=${Date.now()}`;
}

export function exportUrl(): string {
  return '/api/export';
}

export async function syncTimeEdits(edits: TimeEdit[]): Promise<TimeStretchResult> {
  return post('/api/sync_time_edits', { time_edits: edits });
}
