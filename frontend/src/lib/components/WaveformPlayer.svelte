<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { audioUrl } from '$lib/stores/appState';
  import type { PeaksInstance, SegmentAddOptions } from 'peaks.js';

  interface Props {
    onTimeUpdate: (time: number) => void;
    syncToRange?: (xRange: [number, number], totalDuration: number) => void;
  }

  let { onTimeUpdate }: Props = $props();

  let peaks: PeaksInstance | null = null;
  let PeaksModule: typeof import('peaks.js').default | null = null;
  let duration = $state(0);
  let playTime = $state('0:00');
  let totalTimeStr = $state('0:00');
  let isPlayingState = $state(false);
  let audioEl: HTMLAudioElement;
  let zoomviewEl: HTMLDivElement;
  let mounted = false;
  let initializing = false;
  let currentUrl = '';
  let rafId: number | null = null;

  function formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  }

  function startPlayheadLoop() {
    if (rafId !== null) return;
    const tick = () => {
      if (!peaks) return;
      const t = peaks.player.getCurrentTime();
      playTime = formatTime(t);
      onTimeUpdate(t);
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
  }

  function stopPlayheadLoop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  function setupEvents(instance: PeaksInstance) {
    instance.on('player.playing', () => {
      isPlayingState = true;
      startPlayheadLoop();
    });

    instance.on('player.pause', () => {
      isPlayingState = false;
      stopPlayheadLoop();
    });

    instance.on('player.ended', () => {
      isPlayingState = false;
      stopPlayheadLoop();
    });

    // Update pitch plot playhead after seek completes (user click on waveform)
    instance.on('player.seeked', (time: number) => {
      playTime = formatTime(time);
      onTimeUpdate(time);
    });
  }

  function onReady(instance: PeaksInstance) {
    const view = instance.views.getView('zoomview');
    if (view) {
      view.enableSeek(true);
      view.setWheelMode('none');
      view.enableAutoScroll(false);
      view.setZoom({ seconds: 'auto' });
    }

    duration = instance.player.getDuration();
    totalTimeStr = formatTime(duration);
    playTime = '0:00';
  }

  async function loadAudio(url: string): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const onCanPlay = () => { cleanup(); resolve(); };
      const onError = () => { cleanup(); reject(new Error('Audio load failed')); };
      const cleanup = () => {
        audioEl.removeEventListener('canplaythrough', onCanPlay);
        audioEl.removeEventListener('error', onError);
      };
      audioEl.addEventListener('canplaythrough', onCanPlay, { once: true });
      audioEl.addEventListener('error', onError, { once: true });
      audioEl.src = url;
      audioEl.load();
    });
  }

  async function initPeaks(url: string): Promise<PeaksInstance> {
    if (!PeaksModule) {
      PeaksModule = (await import('peaks.js')).default;
    }

    await loadAudio(url);

    const ctx = new AudioContext();

    return new Promise<PeaksInstance>((resolve, reject) => {
      PeaksModule!.init({
        zoomview: {
          container: zoomviewEl,
          waveformColor: '#2E86AB',
          playedWaveformColor: '#e94560',
          showAxisLabels: false,
        },
        mediaElement: audioEl,
        webAudio: {
          audioContext: ctx,
        },
        playheadColor: '#e94560',
        axisGridlineColor: 'transparent',
        axisLabelColor: 'transparent',
        zoomLevels: [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768],
      }, (err, instance) => {
        if (err || !instance) { reject(err); return; }
        resolve(instance);
      });
    });
  }

  onMount(() => {
    mounted = true;
    return () => {
      mounted = false;
      stopPlayheadLoop();
      peaks?.destroy();
    };
  });

  $effect(() => {
    const url = $audioUrl;

    untrack(() => {
      if (!url || !mounted || !audioEl || !zoomviewEl) return;
      if (url === currentUrl) return;
      currentUrl = url;

      if (isPlayingState && peaks) peaks.player.pause();
      isPlayingState = false;

      if (peaks) {
        // Destroy old instance and reinitialize to reliably load new audio
        stopPlayheadLoop();
        peaks.destroy();
        peaks = null;
        initializing = true;
        initPeaks(url).then((instance) => {
          initializing = false;
          if (!mounted) { instance.destroy(); return; }
          peaks = instance;
          setupEvents(peaks);
          onReady(peaks);
        }).catch((err) => {
          initializing = false;
          console.error('peaks.js reinit error:', err);
        });
      } else if (!initializing) {
        initializing = true;
        initPeaks(url).then((instance) => {
          initializing = false;
          if (!mounted) { instance.destroy(); return; }
          peaks = instance;
          setupEvents(peaks);
          onReady(peaks);
        }).catch((err) => {
          initializing = false;
          console.error('peaks.js init error:', err);
        });
      }
    });
  });

  export function togglePlay() {
    if (!peaks) return;
    if (isPlayingState) {
      peaks.player.pause();
    } else {
      peaks.player.play();
    }
  }

  export function stop() {
    if (!peaks) return;
    peaks.player.pause();
    peaks.player.seek(0);
    isPlayingState = false;
    playTime = '0:00';
    onTimeUpdate(0);
  }

  export function seek(time: number) {
    if (!peaks) return;
    peaks.player.seek(time);
    playTime = formatTime(time);
    onTimeUpdate(time);
  }

  export function syncToRange(xRange: [number, number], totalDuration: number) {
    if (!peaks || !totalDuration) return;

    const visibleDuration = xRange[1] - xRange[0];

    const view = peaks.views.getView('zoomview');
    if (view) {
      view.setZoom({ seconds: visibleDuration });
      view.setStartTime(xRange[0]);
    }
  }

  export function isPlaying(): boolean {
    return isPlayingState;
  }

  export function addSegment(startTime: number, endTime: number, opts?: {
    color?: string;
    labelText?: string;
    editable?: boolean;
    id?: string;
  }) {
    if (!peaks) return;
    peaks.segments.add({
      startTime,
      endTime,
      color: opts?.color ?? 'rgba(233, 69, 96, 0.3)',
      labelText: opts?.labelText ?? '',
      editable: opts?.editable ?? true,
      id: opts?.id,
    } as SegmentAddOptions);
  }

  export function removeSegment(id: string) {
    peaks?.segments.removeById(id);
  }

  export function getSegments() {
    return peaks?.segments.getSegments() ?? [];
  }

  export function removeAllSegments() {
    peaks?.segments.removeAll();
  }
</script>

<style>
  .play-btn {
    width: 38px;
    height: 32px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
</style>

<div class="waveform-container">
  <audio bind:this={audioEl} style="display:none;"></audio>
  <div bind:this={zoomviewEl} style="width:100%;height:60px;cursor:pointer;"></div>
  <div class="transport">
    <button class="btn btn-icon play-btn" onclick={togglePlay}>{isPlayingState ? '⏸' : '▶'}</button>
    <button class="btn btn-icon" onclick={stop}>■</button>
    <span id="playTime" style="font-size:0.82rem;font-family:monospace;color:var(--text-dim);">{playTime}</span>
    <span class="sep">/</span>
    <span id="totalTime" style="font-size:0.82rem;font-family:monospace;color:var(--text-dim);">{totalTimeStr}</span>
  </div>
</div>
