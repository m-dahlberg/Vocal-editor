import type { AnalysisResult, CorrectResult, SyncResult, SegmentResult, UploadResult, Params, Cluster, TimeEdit, TimeStretchResult, StretchMarker, DeclickerResult, DeclickerParams, DenoiserParams, DenoiserResult, EditClip } from '$lib/utils/types';

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

export async function uploadReference(file: File): Promise<any> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch('/api/upload_reference', { method: 'POST', body: fd });
  return r.json();
}

export async function uploadMidi(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch('/api/upload_midi', { method: 'POST', body: fd });
  return r.json();
}

export async function uploadPianoGuide(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch('/api/upload_piano_guide', { method: 'POST', body: fd });
  return r.json();
}

export function exportMidiUrl(): string {
  return '/api/export_midi';
}

export async function analyze(params: Params): Promise<AnalysisResult> {
  return post('/api/analyze', params);
}

export async function correct(params: Params): Promise<CorrectResult> {
  return post('/api/correct', params);
}

export async function correctCluster(clusterIdx: number, allClusters: Partial<Cluster>[], timeEdits?: TimeEdit[], paddingMs?: number, crossfadeMs?: number, cropMs?: number, neighborCount?: number): Promise<any> {
  return post('/api/correct_cluster', { cluster_idx: clusterIdx, clusters: allClusters, time_edits: timeEdits, padding_ms: paddingMs, crossfade_ms: crossfadeMs, crop_ms: cropMs, neighbor_count: neighborCount });
}

export async function analyzeSegment(startTime: number, endTime: number): Promise<SegmentResult> {
  return post('/api/analyze_segment', { start_time: startTime, end_time: endTime });
}

export async function deleteCluster(clusterIdx: number): Promise<any> {
  return post('/api/delete_cluster', { cluster_idx: clusterIdx });
}

export async function syncClusters(clusterList: Partial<Cluster>[], timeEdits?: TimeEdit[], params?: Partial<Params>, stretchMarkers?: StretchMarker[]): Promise<SyncResult> {
  const body: Record<string, unknown> = { clusters: clusterList };
  body.time_edits = timeEdits ?? [];
  body.stretch_markers = stretchMarkers ?? [];
  if (params) body.params = params;
  return post('/api/sync_clusters', body);
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

export async function uploadBacking(file: File): Promise<any> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch('/api/upload_backing', { method: 'POST', body: fd });
  return r.json();
}

export function referenceAudioUrl(): string {
  return `/api/reference_audio?t=${Date.now()}`;
}

export function backingAudioUrl(): string {
  return `/api/backing_audio?t=${Date.now()}`;
}

export function exportUrl(): string {
  return '/api/export';
}

export async function processTimeSegment(markerIdx: number, allClusters: Partial<Cluster>[], stretchMarkers: StretchMarker[], paddingMs?: number, crossfadeMs?: number, cropMs?: number): Promise<any> {
  return post('/api/process_time_segment', { marker_idx: markerIdx, clusters: allClusters, stretch_markers: stretchMarkers, padding_ms: paddingMs, crossfade_ms: crossfadeMs, crop_ms: cropMs });
}

export async function syncTimeEdits(edits: TimeEdit[], stretchMarkers?: StretchMarker[]): Promise<TimeStretchResult> {
  return post('/api/sync_time_edits', { time_edits: edits, stretch_markers: stretchMarkers ?? [] });
}

// De-Clicker API
export async function declickerDetect(params: DeclickerParams): Promise<DeclickerResult> {
  return post('/api/declicker/detect', params);
}

export async function declickerApply(params: DeclickerParams): Promise<DeclickerResult> {
  return post('/api/declicker/apply', params);
}

export async function declickerPreview(): Promise<{ ok: boolean; error?: string; url?: string }> {
  return post('/api/declicker/preview');
}

export async function declickerReset(): Promise<{ ok: boolean }> {
  return post('/api/declicker/reset');
}

export function declickerAudioUrl(): string {
  return `/api/declicker/audio?t=${Date.now()}`;
}

export function declickerExportUrl(): string {
  return '/api/declicker/export';
}

// Denoiser API
export async function denoiserAnalyze(params: DenoiserParams): Promise<DenoiserResult> {
  return post('/api/denoiser/analyze', params);
}

export async function denoiserApply(params: DenoiserParams): Promise<DenoiserResult> {
  return post('/api/denoiser/apply', params);
}

export async function denoiserReset(): Promise<{ ok: boolean }> {
  return post('/api/denoiser/reset');
}

export function denoiserAudioUrl(): string {
  return `/api/denoiser/audio?t=${Date.now()}`;
}

export function denoiserExportUrl(): string {
  return '/api/denoiser/export';
}

// Fine Edit API
export async function editUploadRender(wavBlob: Blob, clips: EditClip[]): Promise<{ ok: boolean; error?: string }> {
  const fd = new FormData();
  fd.append('file', wavBlob, 'edit_render.wav');
  fd.append('clips', JSON.stringify(clips));
  const r = await fetch('/api/edit/upload_render', { method: 'POST', body: fd });
  return r.json();
}

export async function editGetClips(): Promise<{ ok: boolean; clips: EditClip[] | null }> {
  const r = await fetch('/api/edit/clips');
  return r.json();
}

export async function editReset(): Promise<{ ok: boolean }> {
  return post('/api/edit/reset');
}

export function editAudioUrl(): string {
  return `/api/edit/audio?t=${Date.now()}`;
}

export function editSourceAudioUrl(): string {
  return `/api/edit/source_audio?t=${Date.now()}`;
}

// Project save/load
export async function saveProject(pipelineStatus: Record<string, string>): Promise<{ ok: boolean; error?: string }> {
  return post('/api/save_project', { pipeline_status: pipelineStatus });
}

export async function checkProject(): Promise<{ found: boolean; project?: any }> {
  const r = await fetch('/api/check_project');
  return r.json();
}
