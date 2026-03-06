<script lang="ts">
  import { onMount } from 'svelte';
  import { audioUrl } from '$lib/stores/appState';
  import type WaveSurfer from 'wavesurfer.js';

  interface Props {
    onTimeUpdate: (time: number) => void;
    syncToRange?: (xRange: [number, number], totalDuration: number) => void;
  }

  let { onTimeUpdate }: Props = $props();

  let ws: WaveSurfer | null = null;
  let duration = $state(0);
  let playTime = $state('0:00');
  let totalTimeStr = $state('0:00');
  let isPlayingState = $state(false);
  let waveformEl: HTMLDivElement;

  function formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  }

  onMount(() => {
    const init = async () => {
    const WaveSurferLib = (await import('wavesurfer.js')).default;

    ws = WaveSurferLib.create({
      container: waveformEl,
      waveColor: '#2E86AB',
      progressColor: '#e94560',
      cursorColor: '#e94560',
      cursorWidth: 2,
      height: 60,
      normalize: true,
      interact: true,
      fillParent: true,
      backend: 'WebAudio',
      autoCenter: false,
    });

    ws.on('ready', () => {
      duration = ws!.getDuration();
      totalTimeStr = formatTime(duration);
      playTime = '0:00';
    });

    ws.on('audioprocess', (t: number) => {
      playTime = formatTime(t);
      onTimeUpdate(t);
    });

    ws.on('seeking', (progress: number) => {
      const t = progress * duration;
      playTime = formatTime(t);
      onTimeUpdate(t);
    });

    ws.on('finish', () => {
      isPlayingState = false;
    });

    };
    init();

    return () => {
      ws?.destroy();
    };
  });

  $effect(() => {
    const url = $audioUrl;
    if (url && ws) {
      const wasPlaying = ws.isPlaying();
      if (wasPlaying) ws.pause();
      ws.load(url);
      isPlayingState = false;
    }
  });

  export function togglePlay() {
    if (!ws) return;
    if (ws.isPlaying()) {
      ws.pause();
      isPlayingState = false;
    } else {
      ws.play();
      isPlayingState = true;
    }
  }

  export function stop() {
    if (!ws) return;
    ws.stop();
    isPlayingState = false;
    playTime = '0:00';
    onTimeUpdate(0);
  }

  export function syncToRange(xRange: [number, number], totalDuration: number) {
    if (!ws || !totalDuration) return;
    const dur = totalDuration || duration;
    if (!dur) return;

    const visibleDuration = xRange[1] - xRange[0];
    const containerWidth = waveformEl.clientWidth;
    const pxPerSec = containerWidth / visibleDuration;

    ws.zoom(pxPerSec);

    const wrapper = (ws as any).getWrapper?.();
    if (wrapper?.parentElement) {
      wrapper.parentElement.scrollLeft = xRange[0] * pxPerSec;
    }
  }

  export function isPlaying(): boolean {
    return ws ? ws.isPlaying() : false;
  }
</script>

<div class="waveform-container">
  <div bind:this={waveformEl} style="width:100%;height:60px;cursor:pointer;"></div>
  <div class="transport">
    <button class="btn btn-icon" onclick={togglePlay}>{isPlayingState ? '⏸' : '▶'}</button>
    <button class="btn btn-icon" onclick={stop}>■</button>
    <span id="playTime" style="font-size:0.82rem;font-family:monospace;color:var(--text-dim);">{playTime}</span>
    <span class="sep">/</span>
    <span id="totalTime" style="font-size:0.82rem;font-family:monospace;color:var(--text-dim);">{totalTimeStr}</span>
  </div>
</div>
