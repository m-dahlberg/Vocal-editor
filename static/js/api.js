/* api.js - Flask API calls */

const API = {

  async uploadAudio(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/upload_audio', { method: 'POST', body: fd });
    return r.json();
  },

  async uploadMidi(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/upload_midi', { method: 'POST', body: fd });
    return r.json();
  },

  async analyze(params) {
    const r = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return r.json();
  },

  async correct(params) {
    const r = await fetch('/api/correct', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return r.json();
  },

  async correctCluster(clusterIdx, updates) {
    const r = await fetch('/api/correct_cluster', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cluster_idx: clusterIdx, ...updates }),
    });
    return r.json();
  },

  async analyzeSegment(startTime, endTime) {
    const r = await fetch('/api/analyze_segment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start_time: startTime, end_time: endTime }),
    });
    return r.json();
  },

  async deleteCluster(clusterIdx) {
    const r = await fetch('/api/delete_cluster', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cluster_idx: clusterIdx }),
    });
    return r.json();
  },

  async syncClusters(clusters, originalTimes, originalFreqs, correctedFreqs) {
    const r = await fetch('/api/sync_clusters', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clusters, original_times: originalTimes, original_freqs: originalFreqs, corrected_freqs: correctedFreqs }),
    });
    return r.json();
  },

  async resetEdits() {
    const r = await fetch('/api/reset_edits', { method: 'POST' });
    return r.json();
  },

  async updateCluster(clusterIdx, updates) {
    const r = await fetch('/api/update_cluster', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cluster_idx: clusterIdx, ...updates }),
    });
    return r.json();
  },

  audioUrl() {
    return `/api/audio?t=${Date.now()}`;
  },

  exportUrl() {
    return '/api/export';
  },
};
