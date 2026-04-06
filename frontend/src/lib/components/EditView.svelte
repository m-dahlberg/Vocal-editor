<script lang="ts">
  import { onMount } from 'svelte';
  import {
    editClips, editSelectedClipIds, editCursorTime, editAudioBuffer, editApplied,
    activeTab, viewXRange, waveformReset, audioLoaded, editTimeSelection
  } from '$lib/stores/appState';
  import * as api from '$lib/api';
  import type { EditClip } from '$lib/utils/types';

  interface Props {
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
  }

  let { syncWaveform, onSeek }: Props = $props();

  let canvasEl: HTMLCanvasElement;
  let containerEl: HTMLDivElement;
  let ctx: CanvasRenderingContext2D;
  let _rafPending = false;

  // View state
  let _xRange: [number, number] = [0, 10];
  let _fullXRange: [number, number] = [0, 10];
  let _pendingZoomReset = false;
  let _playheadTime = 0;
  let _mounted = false;

  // Audio data
  let _waveformData: Float32Array | null = null;
  let _waveformSr = 0;
  let _audioDuration = 0;

  // Drag / interaction state
  let _dragState: { clipId: string; startX: number; originalPositions: Map<string, number> } | null = null;
  let _resizeState: {
    clipId: string;
    edge: 'left' | 'right';
    startX: number;
    originalPosition: number;
    originalSourceOffset: number;
    originalDuration: number;
  } | null = null;
  let _timeSelectState: { startTime: number } | null = null;

  function setXRange(range: [number, number]) {
    _xRange = range;
    $viewXRange = range;
  }

  const COLORS = {
    bg: '#16213e',
    clipBg: 'rgba(40, 60, 100, 0.8)',
    clipBgSelected: 'rgba(80, 100, 160, 0.9)',
    clipBorder: '#4a6fa5',
    clipBorderSelected: '#8ab4f8',
    gap: 'rgba(10, 15, 30, 0.6)',
    gridLine: '#2a2a4a',
    text: '#ccc',
    textDim: '#888',
    playhead: '#e94560',
    cursor: '#2dd4bf',
    waveform: 'rgba(100, 180, 255, 0.7)',
    waveformSelected: 'rgba(140, 200, 255, 0.85)',
    fade: 'rgba(255, 200, 50, 0.85)',
    crossfadeFill: 'rgba(255, 140, 50, 0.18)',
    crossfadeLine: 'rgba(255, 165, 50, 0.65)',
    timeSelFill: 'rgba(45, 212, 191, 0.12)',
    timeSelLine: 'rgba(45, 212, 191, 0.5)',
  };

  const MARGIN = { l: 60, r: 20, t: 30, b: 40 };
  const EDGE_HIT_PX = 6; // pixels for edge hit detection

  // --- Audio loading ---
  async function loadAudio() {
    try {
      const resp = await fetch(api.editSourceAudioUrl());
      if (!resp.ok) return;
      const buf = await resp.arrayBuffer();
      const audioCtx = new AudioContext();
      const decoded = await audioCtx.decodeAudioData(buf);
      _waveformData = decoded.getChannelData(0);
      _waveformSr = decoded.sampleRate;
      _audioDuration = decoded.duration;
      $editAudioBuffer = decoded;
      audioCtx.close();
      buildPeakCache();

      if (_audioDuration > 0) {
        _fullXRange = [0, _audioDuration];
        if (_pendingZoomReset) {
          setXRange([..._fullXRange] as [number, number]);
          _pendingZoomReset = false;
        }
      }

      // Restore clips from backend or initialize
      const result = await api.editGetClips();
      if (result.ok && result.clips && result.clips.length > 0) {
        $editClips = result.clips;
      } else if ($editClips.length === 0) {
        $editClips = [{
          id: crypto.randomUUID(),
          sourceOffset: 0,
          duration: _audioDuration,
          position: 0,
        }];
      }

      requestDraw();
    } catch {
      // ignore
    }
  }

  // --- Drawing ---
  function requestDraw() {
    if (_rafPending || !_mounted) return;
    _rafPending = true;
    requestAnimationFrame(() => {
      _rafPending = false;
      draw();
    });
  }

  // Reusable time-to-canvas-x conversion (uses current _xRange and canvas size)
  function timeToX(t: number): number {
    if (!canvasEl) return 0;
    const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
    const [xMin, xMax] = _xRange;
    const span = xMax - xMin;
    if (span <= 0) return MARGIN.l;
    return MARGIN.l + ((t - xMin) / span) * plotW;
  }

  function draw() {
    if (!ctx || !canvasEl) return;
    const W = canvasEl.width;
    const H = canvasEl.height;
    const plotW = W - MARGIN.l - MARGIN.r;
    const plotH = H - MARGIN.t - MARGIN.b;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    if (plotW <= 0 || plotH <= 0) return;

    const [xMin, xMax] = _xRange;
    const xSpan = xMax - xMin;
    if (xSpan <= 0) return;

    const toX = (t: number) => MARGIN.l + ((t - xMin) / xSpan) * plotW;

    // Draw time grid
    drawTimeGrid(ctx, xMin, xMax, plotW, plotH, toX);

    // Draw gaps (darker background between clips)
    drawGaps(ctx, plotH, toX, xMin, xMax);

    // Draw clips
    const clips = $editClips;
    const selected = $editSelectedClipIds;
    for (const clip of clips) {
      const isSelected = selected.has(clip.id);
      drawClip(ctx, clip, isSelected, plotW, plotH, toX, xMin, xMax);
    }

    // Draw crossfade regions on top of clips
    const crossfades = findCrossfades(clips);
    for (const xf of crossfades) {
      drawCrossfade(ctx, xf.startTime, xf.endTime, plotW, plotH, toX);
    }

    // Draw time selection
    const sel = $editTimeSelection;
    if (sel) {
      const sx1 = Math.max(MARGIN.l, toX(sel.start));
      const sx2 = Math.min(MARGIN.l + plotW, toX(sel.end));
      if (sx2 > sx1) {
        ctx.fillStyle = COLORS.timeSelFill;
        ctx.fillRect(sx1, MARGIN.t, sx2 - sx1, plotH);
        ctx.strokeStyle = COLORS.timeSelLine;
        ctx.lineWidth = 1;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(sx1, MARGIN.t); ctx.lineTo(sx1, MARGIN.t + plotH);
        ctx.moveTo(sx2, MARGIN.t); ctx.lineTo(sx2, MARGIN.t + plotH);
        ctx.stroke();
      }
    }

    // Draw cursor
    const cx = toX($editCursorTime);
    if (cx >= MARGIN.l && cx <= MARGIN.l + plotW) {
      ctx.strokeStyle = COLORS.cursor;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(cx, MARGIN.t);
      ctx.lineTo(cx, MARGIN.t + plotH);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw playhead
    const px = toX(_playheadTime);
    if (px >= MARGIN.l && px <= MARGIN.l + plotW) {
      ctx.strokeStyle = COLORS.playhead;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px, MARGIN.t);
      ctx.lineTo(px, MARGIN.t + plotH);
      ctx.stroke();
    }
  }

  function drawTimeGrid(ctx: CanvasRenderingContext2D, xMin: number, xMax: number, plotW: number, plotH: number, toX: (t: number) => number) {
    const span = xMax - xMin;
    const rawStep = span / 8;
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    const steps = [1, 2, 5, 10];
    const step = mag * (steps.find(s => s * mag >= rawStep) || 10);

    ctx.fillStyle = COLORS.textDim;
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';

    const start = Math.ceil(xMin / step) * step;
    for (let t = start; t <= xMax; t += step) {
      const x = toX(t);
      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(x, MARGIN.t);
      ctx.lineTo(x, MARGIN.t + plotH);
      ctx.stroke();
      ctx.fillText(t.toFixed(2) + 's', x, MARGIN.t + plotH + 14);
    }
  }

  function drawGaps(ctx: CanvasRenderingContext2D, plotH: number, toX: (t: number) => number, xMin: number, xMax: number) {
    const clips = [...$editClips].sort((a, b) => a.position - b.position);
    ctx.fillStyle = COLORS.gap;

    let prevEnd = 0;
    for (const clip of clips) {
      if (clip.position > prevEnd) {
        const gx1 = Math.max(MARGIN.l, toX(prevEnd));
        const gx2 = Math.min(MARGIN.l + (canvasEl.width - MARGIN.l - MARGIN.r), toX(clip.position));
        if (gx2 > gx1) ctx.fillRect(gx1, MARGIN.t, gx2 - gx1, plotH);
      }
      prevEnd = Math.max(prevEnd, clip.position + clip.duration);
    }
    if (prevEnd < xMax) {
      const gx1 = Math.max(MARGIN.l, toX(prevEnd));
      const gx2 = MARGIN.l + (canvasEl.width - MARGIN.l - MARGIN.r);
      if (gx2 > gx1) ctx.fillRect(gx1, MARGIN.t, gx2 - gx1, plotH);
    }
  }

  function drawClip(ctx: CanvasRenderingContext2D, clip: EditClip, isSelected: boolean, plotW: number, plotH: number, toX: (t: number) => number, xMin: number, xMax: number) {
    const x1 = toX(clip.position);
    const x2 = toX(clip.position + clip.duration);
    const clipLeft = Math.max(MARGIN.l, x1);
    const clipRight = Math.min(MARGIN.l + plotW, x2);

    if (clipRight <= clipLeft) return;

    // Clip background
    ctx.fillStyle = isSelected ? COLORS.clipBgSelected : COLORS.clipBg;
    ctx.fillRect(clipLeft, MARGIN.t, clipRight - clipLeft, plotH);

    // Waveform within clip
    if (_waveformData && _waveformSr) {
      drawClipWaveform(ctx, clip, isSelected, plotH, toX, xMin, xMax);
    }

    // Fade in indicator
    if (clip.fadeIn && clip.fadeIn > 0) {
      const fadeEndX = toX(clip.position + clip.fadeIn);
      const startX = Math.max(MARGIN.l, x1);
      const endX = Math.min(MARGIN.l + plotW, fadeEndX);
      if (endX > startX) {
        ctx.strokeStyle = COLORS.fade;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(startX, MARGIN.t + plotH);
        ctx.lineTo(endX, MARGIN.t);
        ctx.stroke();
      }
    }

    // Fade out indicator
    if (clip.fadeOut && clip.fadeOut > 0) {
      const fadeStartX = toX(clip.position + clip.duration - clip.fadeOut);
      const startX = Math.max(MARGIN.l, fadeStartX);
      const endX = Math.min(MARGIN.l + plotW, x2);
      if (endX > startX) {
        ctx.strokeStyle = COLORS.fade;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(startX, MARGIN.t);
        ctx.lineTo(endX, MARGIN.t + plotH);
        ctx.stroke();
      }
    }

    // Clip borders
    ctx.strokeStyle = isSelected ? COLORS.clipBorderSelected : COLORS.clipBorder;
    ctx.lineWidth = isSelected ? 2 : 1;
    if (x1 >= MARGIN.l && x1 <= MARGIN.l + plotW) {
      ctx.beginPath();
      ctx.moveTo(x1, MARGIN.t);
      ctx.lineTo(x1, MARGIN.t + plotH);
      ctx.stroke();
    }
    if (x2 >= MARGIN.l && x2 <= MARGIN.l + plotW) {
      ctx.beginPath();
      ctx.moveTo(x2, MARGIN.t);
      ctx.lineTo(x2, MARGIN.t + plotH);
      ctx.stroke();
    }
  }

  interface CrossfadeRegion {
    startTime: number;
    endTime: number;
    clipA: EditClip;
    clipB: EditClip;
  }

  function findCrossfades(clips: EditClip[]): CrossfadeRegion[] {
    const sorted = [...clips].sort((a, b) => a.position - b.position);
    const regions: CrossfadeRegion[] = [];
    for (let i = 0; i < sorted.length; i++) {
      for (let j = i + 1; j < sorted.length; j++) {
        const a = sorted[i], b = sorted[j];
        const aEnd = a.position + a.duration;
        if (aEnd > b.position + 0.001) {
          const overlapEnd = Math.min(aEnd, b.position + b.duration);
          regions.push({ startTime: b.position, endTime: overlapEnd, clipA: a, clipB: b });
        }
      }
    }
    return regions;
  }

  // When clips overlap forming a crossfade, strip any explicit fade that covers the same edge.
  function clearFadesOnCrossfade(clips: EditClip[]): EditClip[] {
    const xfades = findCrossfades(clips);
    if (xfades.length === 0) return clips;
    return clips.map(clip => {
      let changed = false;
      let fadeIn = clip.fadeIn;
      let fadeOut = clip.fadeOut;
      for (const xf of xfades) {
        // clipA ends into the crossfade — clear its fadeOut
        if (xf.clipA.id === clip.id && fadeOut !== undefined) {
          fadeOut = undefined;
          changed = true;
        }
        // clipB starts into the crossfade — clear its fadeIn
        if (xf.clipB.id === clip.id && fadeIn !== undefined) {
          fadeIn = undefined;
          changed = true;
        }
      }
      return changed ? { ...clip, fadeIn, fadeOut } : clip;
    });
  }

  function drawCrossfade(ctx: CanvasRenderingContext2D, startTime: number, endTime: number, plotW: number, plotH: number, toX: (t: number) => number) {
    const x1 = Math.max(MARGIN.l, toX(startTime));
    const x2 = Math.min(MARGIN.l + plotW, toX(endTime));
    if (x2 <= x1) return;

    // Semi-transparent overlay
    ctx.fillStyle = COLORS.crossfadeFill;
    ctx.fillRect(x1, MARGIN.t, x2 - x1, plotH);

    // X pattern
    ctx.strokeStyle = COLORS.crossfadeLine;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(x1, MARGIN.t);
    ctx.lineTo(x2, MARGIN.t + plotH);
    ctx.moveTo(x1, MARGIN.t + plotH);
    ctx.lineTo(x2, MARGIN.t);
    ctx.stroke();
  }

  // Pre-computed peak cache for fast waveform drawing
  let _peakCache: { min: Float32Array; max: Float32Array } | null = null;
  let _peakCacheSamplesPerPeak = 0;

  function buildPeakCache() {
    if (!_waveformData || !_waveformSr) return;
    const samplesPerPeak = 64;
    const numPeaks = Math.ceil(_waveformData.length / samplesPerPeak);
    const mins = new Float32Array(numPeaks);
    const maxs = new Float32Array(numPeaks);

    for (let i = 0; i < numPeaks; i++) {
      const start = i * samplesPerPeak;
      const end = Math.min(start + samplesPerPeak, _waveformData.length);
      let mn = 0, mx = 0;
      for (let s = start; s < end; s++) {
        const v = _waveformData[s];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      mins[i] = mn;
      maxs[i] = mx;
    }
    _peakCache = { min: mins, max: maxs };
    _peakCacheSamplesPerPeak = samplesPerPeak;
  }

  function drawClipWaveform(ctx: CanvasRenderingContext2D, clip: EditClip, isSelected: boolean, plotH: number, toX: (t: number) => number, xMin: number, xMax: number) {
    if (!_waveformData || !_waveformSr) return;

    const midY = MARGIN.t + plotH / 2;
    const halfH = plotH / 2 * 0.85;
    const plotW = canvasEl.width - MARGIN.l - MARGIN.r;

    const visStart = Math.max(clip.position, xMin);
    const visEnd = Math.min(clip.position + clip.duration, xMax);
    if (visEnd <= visStart) return;

    const pxStart = Math.max(0, Math.floor(toX(visStart) - MARGIN.l));
    const pxEnd = Math.min(plotW, Math.ceil(toX(visEnd) - MARGIN.l));

    ctx.fillStyle = isSelected ? COLORS.waveformSelected : COLORS.waveform;

    for (let px = pxStart; px < pxEnd; px++) {
      const t = xMin + (px / plotW) * (xMax - xMin);
      const sourceTime = clip.sourceOffset + (t - clip.position);
      const nextT = xMin + ((px + 1) / plotW) * (xMax - xMin);
      const nextSourceTime = clip.sourceOffset + (nextT - clip.position);

      let mn = 0, mx = 0;

      if (_peakCache && _peakCacheSamplesPerPeak > 0) {
        const p0 = Math.max(0, Math.floor(sourceTime * _waveformSr / _peakCacheSamplesPerPeak));
        const p1 = Math.min(_peakCache.min.length, Math.ceil(nextSourceTime * _waveformSr / _peakCacheSamplesPerPeak));
        for (let p = p0; p < p1; p++) {
          if (_peakCache.min[p] < mn) mn = _peakCache.min[p];
          if (_peakCache.max[p] > mx) mx = _peakCache.max[p];
        }
      } else {
        const s0 = Math.floor(sourceTime * _waveformSr);
        const s1 = Math.min(Math.ceil(nextSourceTime * _waveformSr), _waveformData!.length);
        for (let s = Math.max(0, s0); s < Math.min(s1, _waveformData!.length); s++) {
          const v = _waveformData![s];
          if (v < mn) mn = v;
          if (v > mx) mx = v;
        }
      }

      const x = MARGIN.l + px;
      const y1 = midY - mx * halfH;
      const y2 = midY - mn * halfH;
      ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
    }
  }

  // --- Interaction helpers ---
  function xToTime(e: MouseEvent): number {
    if (!canvasEl) return 0;
    const rect = canvasEl.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (canvasEl.width / rect.width);
    const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
    const [xMin, xMax] = _xRange;
    return xMin + ((x - MARGIN.l) / plotW) * (xMax - xMin);
  }

  function findClipAtTime(t: number): EditClip | null {
    for (const clip of $editClips) {
      if (t >= clip.position && t < clip.position + clip.duration) {
        return clip;
      }
    }
    return null;
  }

  function findEdgeAtMouse(e: MouseEvent): { clip: EditClip; edge: 'left' | 'right' } | null {
    if (!canvasEl) return null;
    const rect = canvasEl.getBoundingClientRect();
    const scale = canvasEl.width / rect.width;
    const mouseX = (e.clientX - rect.left) * scale;

    for (const clip of $editClips) {
      const leftX = timeToX(clip.position);
      const rightX = timeToX(clip.position + clip.duration);
      if (Math.abs(mouseX - leftX) <= EDGE_HIT_PX) return { clip, edge: 'left' };
      if (Math.abs(mouseX - rightX) <= EDGE_HIT_PX) return { clip, edge: 'right' };
    }
    return null;
  }

  function getClickZone(e: MouseEvent): 'upper' | 'lower' {
    if (!canvasEl) return 'lower';
    const rect = canvasEl.getBoundingClientRect();
    const scale = canvasEl.height / rect.height;
    const mouseY = (e.clientY - rect.top) * scale;
    const plotH = canvasEl.height - MARGIN.t - MARGIN.b;
    const midY = MARGIN.t + plotH / 2;
    return mouseY < midY ? 'upper' : 'lower';
  }

  function handleSelect(e: MouseEvent) {
    const t = xToTime(e);
    const clip = findClipAtTime(t);

    if (clip) {
      if (e.shiftKey) {
        const newSet = new Set($editSelectedClipIds);
        if (newSet.has(clip.id)) {
          newSet.delete(clip.id);
        } else {
          newSet.add(clip.id);
        }
        $editSelectedClipIds = newSet;
      } else {
        $editSelectedClipIds = new Set([clip.id]);
      }
    } else {
      $editSelectedClipIds = new Set();
    }

    $editCursorTime = Math.max(0, t);
    onSeek?.(Math.max(0, t));
    requestDraw();
  }

  // --- Mouse interaction ---
  let _didDrag = false;
  let _mouseDownPos = { x: 0, y: 0 };
  const DRAG_THRESHOLD = 4;

  function onMouseDown(e: MouseEvent) {
    _mouseDownPos = { x: e.clientX, y: e.clientY };
    _didDrag = false;

    // Pan mode (middle-click or Alt+click)
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      _isPanning = true;
      _panStartX = e.clientX;
      _panStartRange = [..._xRange] as [number, number];
      e.preventDefault();
      return;
    }

    if (e.button !== 0) return;

    // Edge resize (highest priority)
    const edgeHit = findEdgeAtMouse(e);
    if (edgeHit) {
      _resizeState = {
        clipId: edgeHit.clip.id,
        edge: edgeHit.edge,
        startX: e.clientX,
        originalPosition: edgeHit.clip.position,
        originalSourceOffset: edgeHit.clip.sourceOffset,
        originalDuration: edgeHit.clip.duration,
      };
      e.preventDefault();
      return;
    }

    const t = xToTime(e);
    const clip = findClipAtTime(t);
    const zone = getClickZone(e);

    if (clip) {
      if (zone === 'lower') {
        // Lower half: select immediately and prepare drag
        if (!e.shiftKey) {
          if (!$editSelectedClipIds.has(clip.id)) {
            $editSelectedClipIds = new Set([clip.id]);
          }
        } else {
          const newSet = new Set($editSelectedClipIds);
          newSet.add(clip.id);
          $editSelectedClipIds = newSet;
        }
        // Capture original positions of all selected clips (including the clicked one)
        const selectedNow = new Set([...$editSelectedClipIds, clip.id]);
        const origPositions = new Map<string, number>();
        for (const c of $editClips) {
          if (selectedNow.has(c.id)) origPositions.set(c.id, c.position);
        }
        _dragState = { clipId: clip.id, startX: e.clientX, originalPositions: origPositions };
        e.preventDefault();
      } else {
        // Upper half: deselect clips, set cursor, start time selection
        $editSelectedClipIds = new Set();
        $editCursorTime = Math.max(0, t);
        onSeek?.(Math.max(0, t));
        $editTimeSelection = null;
        _timeSelectState = { startTime: t };
        e.preventDefault();
      }
    } else {
      // Empty area: clear selection, start time selection
      $editSelectedClipIds = new Set();
      $editCursorTime = Math.max(0, t);
      onSeek?.(Math.max(0, t));
      $editTimeSelection = null;
      _timeSelectState = { startTime: t };
      e.preventDefault();
    }
    requestDraw();
  }

  function onMouseMove(e: MouseEvent) {
    const dx = e.clientX - _mouseDownPos.x;
    const dy = e.clientY - _mouseDownPos.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    // Update cursor style when not dragging
    if (!_dragState && !_resizeState && !_timeSelectState && !_isPanning && e.buttons === 0) {
      updateCursorStyle(e);
    }

    // Resize edge drag
    if (_resizeState && canvasEl && dist > DRAG_THRESHOLD) {
      _didDrag = true;
      const rect = canvasEl.getBoundingClientRect();
      const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
      const scale = rect.width > 0 ? (canvasEl.width / rect.width) : 1;
      const span = _xRange[1] - _xRange[0];
      const pxDx = (e.clientX - _resizeState.startX) * scale;
      const dt = (pxDx / plotW) * span;

      const clips = $editClips;
      const clipIdx = clips.findIndex(c => c.id === _resizeState!.clipId);
      if (clipIdx >= 0) {
        const s = _resizeState!;
        let updated = { ...clips[clipIdx] };

        if (s.edge === 'left') {
          // Left edge: right side stays fixed, left moves
          const newSourceOffset = Math.max(0, s.originalSourceOffset + dt);
          const actualDt = newSourceOffset - s.originalSourceOffset;
          const newDuration = Math.max(0.01, s.originalDuration - actualDt);
          const newPosition = s.originalPosition + actualDt;
          updated = { ...updated, position: newPosition, sourceOffset: newSourceOffset, duration: newDuration };
        } else {
          // Right edge: left side stays fixed, right moves
          const newDuration = Math.max(0.01, s.originalDuration + dt);
          const maxDuration = _audioDuration - s.originalSourceOffset;
          updated = { ...updated, duration: Math.min(newDuration, maxDuration) };
        }

        clips[clipIdx] = updated;
        $editClips = [...clips];
      }
      requestDraw();
      return;
    }

    // Clip move drag
    if (_dragState && canvasEl && dist > DRAG_THRESHOLD) {
      _didDrag = true;
      const rect = canvasEl.getBoundingClientRect();
      const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
      const scale = rect.width > 0 ? (canvasEl.width / rect.width) : 1;
      const span = _xRange[1] - _xRange[0];
      const pxDx = (e.clientX - _dragState.startX) * scale;
      const dt = (pxDx / plotW) * span;

      // Move all clips that were selected at drag start
      let clips = [...$editClips];
      const dragIds = _dragState.originalPositions;
      const nonDragClips = clips.filter(c => !dragIds.has(c.id));

      for (let i = 0; i < clips.length; i++) {
        const c = clips[i];
        const origPos = dragIds.get(c.id);
        if (origPos === undefined) continue;
        const rawPos = Math.max(0, origPos + dt);
        const constrainedPos = constrainPosition(c, rawPos, nonDragClips);
        clips[i] = { ...c, position: constrainedPos };
      }

      // Strip fades where crossfades now form
      clips = clearFadesOnCrossfade(clips);
      $editClips = clips;
      requestDraw();
      return;
    }

    // Time selection drag
    if (_timeSelectState && canvasEl && dist > DRAG_THRESHOLD) {
      _didDrag = true;
      const t = xToTime(e);
      const start = Math.min(_timeSelectState.startTime, t);
      const end = Math.max(_timeSelectState.startTime, t);
      $editTimeSelection = { start, end };
      requestDraw();
      return;
    }

    // Pan
    if (_isPanning && canvasEl) {
      _didDrag = true;
      const rect = canvasEl.getBoundingClientRect();
      const pxDx = e.clientX - _panStartX;
      const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
      const scale = rect.width > 0 ? (canvasEl.width / rect.width) : 1;
      const span = _panStartRange[1] - _panStartRange[0];
      const dt = -(pxDx * scale / plotW) * span;
      const newMin = Math.max(0, _panStartRange[0] + dt);
      const newMax = newMin + span;
      setXRange([newMin, Math.min(newMax, _fullXRange[1])]);
      requestDraw();
      syncWaveform(_xRange, _audioDuration);
    }
  }

  function updateCursorStyle(e: MouseEvent) {
    if (!canvasEl) return;
    const edgeHit = findEdgeAtMouse(e);
    if (edgeHit) {
      canvasEl.style.cursor = 'ew-resize';
      return;
    }
    const t = xToTime(e);
    const clip = findClipAtTime(t);
    if (clip) {
      const zone = getClickZone(e);
      canvasEl.style.cursor = zone === 'lower' ? 'grab' : 'crosshair';
    } else {
      canvasEl.style.cursor = 'crosshair';
    }
  }

  function onMouseUp(e: MouseEvent) {
    if (_isPanning) {
      _isPanning = false;
      _didDrag = false;
      return;
    }

    if (_resizeState) {
      _resizeState = null;
      _didDrag = false;
      canvasEl.style.cursor = 'crosshair';
      return;
    }

    if (_dragState) {
      const wasDrag = _didDrag;
      _dragState = null;
      _didDrag = false;
      if (!wasDrag) {
        $editCursorTime = Math.max(0, xToTime(e));
        onSeek?.($editCursorTime);
        requestDraw();
      }
      return;
    }

    if (_timeSelectState) {
      const wasDrag = _didDrag;
      _timeSelectState = null;
      _didDrag = false;
      if (!wasDrag) {
        // Just a click — clear selection
        $editTimeSelection = null;
        requestDraw();
      }
      return;
    }

    if (e.button === 0 && !_didDrag) {
      handleSelect(e);
    }
    _didDrag = false;
  }

  function constrainPosition(clip: EditClip, newPos: number, _allClips: EditClip[]): number {
    // Clips may fully overlap — no crossfade limit
    return Math.max(0, newPos);
  }

  // Pan state
  let _isPanning = false;
  let _panStartX = 0;
  let _panStartRange: [number, number] = [0, 10];

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    if (!canvasEl) return;

    if (e.shiftKey) {
      // Shift+scroll → horizontal pan
      const span = _xRange[1] - _xRange[0];
      const delta = (e.deltaY !== 0 ? e.deltaY : e.deltaX) / canvasEl.getBoundingClientRect().width * span * 2;
      const newMin = Math.max(0, _xRange[0] + delta);
      const newMax = Math.min(_fullXRange[1], newMin + span);
      setXRange([newMin, newMax]);
    } else {
      // Vertical scroll → zoom centred on mouse position
      const rect = canvasEl.getBoundingClientRect();
      const mx = (e.clientX - rect.left) / rect.width;
      const span = _xRange[1] - _xRange[0];
      const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
      const newSpan = Math.max(0.1, Math.min(span * factor, _fullXRange[1]));
      const center = _xRange[0] + mx * span;
      const newMin = Math.max(0, center - mx * newSpan);
      const newMax = Math.min(_fullXRange[1], newMin + newSpan);
      setXRange([newMin, newMax]);
    }

    requestDraw();
    syncWaveform(_xRange, _audioDuration);
  }

  // Apply zoom centred on the edit cursor. factor > 1 zooms out, factor < 1 zooms in.
  function applyZoom(factor: number) {
    const span = _xRange[1] - _xRange[0];
    const cursor = $editCursorTime;
    // Fraction of current view that the cursor sits at (0–1)
    const mx = Math.max(0, Math.min(1, (cursor - _xRange[0]) / span));
    const newSpan = Math.max(0.1, Math.min(span * factor, _fullXRange[1]));
    const newMin = Math.max(0, cursor - mx * newSpan);
    const newMax = Math.min(_fullXRange[1], newMin + newSpan);
    setXRange([newMin, newMax]);
    requestDraw();
    syncWaveform(_xRange, _audioDuration);
  }

  export function zoomIn(percent: number) {
    applyZoom(1 / (1 + percent / 100));
  }

  export function zoomOut(percent: number) {
    applyZoom(1 + percent / 100);
  }

  export function nudge(direction: -1 | 1, amountMs: number) {
    const dt = direction * amountMs / 1000;
    const selected = $editSelectedClipIds;

    if (selected.size === 0) {
      // Move cursor
      $editCursorTime = Math.max(0, $editCursorTime + dt);
      onSeek?.($editCursorTime);
      requestDraw();
      return;
    }

    // Move all selected clips
    let clips = [...$editClips];
    const selectedIds = new Set(selected);
    const nonSelectedClips = clips.filter(c => !selectedIds.has(c.id));

    for (let i = 0; i < clips.length; i++) {
      if (!selectedIds.has(clips[i].id)) continue;
      const newPos = Math.max(0, clips[i].position + dt);
      clips[i] = { ...clips[i], position: constrainPosition(clips[i], newPos, nonSelectedClips) };
    }

    clips = clearFadesOnCrossfade(clips);
    $editClips = clips;
    requestDraw();
  }

  // --- Clip operations ---

  const SPLIT_FADE_S = 0.003; // 3 ms fade applied at every split/cut edge

  // Split a single clip at time t. Returns false if not possible.
  function splitClipAt(clips: EditClip[], t: number): EditClip[] | null {
    const clip = clips.find(c => t > c.position + 0.001 && t < c.position + c.duration - 0.001);
    if (!clip) return null;

    const relativeTime = t - clip.position;
    const rightDuration = clip.duration - relativeTime;
    const left: EditClip = {
      id: crypto.randomUUID(),
      sourceOffset: clip.sourceOffset,
      duration: relativeTime,
      position: clip.position,
      fadeIn: clip.fadeIn ? Math.min(clip.fadeIn, relativeTime) : undefined,
      fadeOut: Math.min(SPLIT_FADE_S, relativeTime),
    };
    const right: EditClip = {
      id: crypto.randomUUID(),
      sourceOffset: clip.sourceOffset + relativeTime,
      duration: rightDuration,
      position: clip.position + relativeTime,
      fadeIn: Math.min(SPLIT_FADE_S, rightDuration),
      fadeOut: clip.fadeOut ? Math.min(clip.fadeOut, rightDuration) : undefined,
    };
    return [...clips.filter(c => c.id !== clip.id), left, right];
  }

  export function splitAtCursorOrSelection() {
    const sel = $editTimeSelection;
    if (sel && sel.end - sel.start > 0.001) {
      // Split at both selection boundaries
      let clips = $editClips;
      const result1 = splitClipAt(clips, sel.start);
      if (result1) clips = result1;
      const result2 = splitClipAt(clips, sel.end);
      if (result2) clips = result2;
      clips.sort((a, b) => a.position - b.position);
      $editClips = clips;
    } else {
      const t = $editCursorTime;
      const result = splitClipAt($editClips, t);
      if (!result) return;
      result.sort((a, b) => a.position - b.position);
      $editClips = result;
    }
    $editSelectedClipIds = new Set();
    requestDraw();
  }

  export function deleteAtCursorOrSelection() {
    const sel = $editTimeSelection;
    if (sel && sel.end - sel.start > 0.001) {
      // Split at both boundaries, then delete clips entirely within the selection
      let clips = $editClips;
      const r1 = splitClipAt(clips, sel.start);
      if (r1) clips = r1;
      const r2 = splitClipAt(clips, sel.end);
      if (r2) clips = r2;
      // Delete clips that are fully within [sel.start, sel.end]
      clips = clips.filter(c => !(c.position >= sel.start - 0.001 && c.position + c.duration <= sel.end + 0.001));
      clips.sort((a, b) => a.position - b.position);
      $editClips = clips;
      $editSelectedClipIds = new Set();
      $editTimeSelection = null;
    } else if ($editSelectedClipIds.size > 0) {
      $editClips = $editClips.filter(c => !$editSelectedClipIds.has(c.id));
      $editSelectedClipIds = new Set();
    }
    requestDraw();
  }

  // Auto-select the clip under cursor (if needed) and return it, or null
  function autoSelectClipAtCursor(): EditClip | null {
    const t = $editCursorTime;
    const clip = findClipAtTime(t);
    if (!clip) return null;
    if (!$editSelectedClipIds.has(clip.id)) {
      $editSelectedClipIds = new Set([clip.id]);
    }
    return clip;
  }

  export function trimStartToCursor() {
    const t = $editCursorTime;
    const clip = autoSelectClipAtCursor();
    if (!clip) return;
    if (t <= clip.position || t >= clip.position + clip.duration) return;

    const trimAmount = t - clip.position;
    const newDuration = clip.duration - trimAmount;
    const updated: EditClip = {
      ...clip,
      position: t,
      sourceOffset: clip.sourceOffset + trimAmount,
      duration: newDuration,
      fadeIn: clip.fadeIn ? Math.min(clip.fadeIn, newDuration) : undefined,
    };
    $editClips = $editClips.map(c => c.id === clip.id ? updated : c);
    requestDraw();
  }

  export function trimEndToCursor() {
    const t = $editCursorTime;
    const clip = autoSelectClipAtCursor();
    if (!clip) return;
    if (t <= clip.position || t >= clip.position + clip.duration) return;

    const newDuration = t - clip.position;
    const updated: EditClip = {
      ...clip,
      duration: newDuration,
      fadeOut: clip.fadeOut ? Math.min(clip.fadeOut, newDuration) : undefined,
    };
    $editClips = $editClips.map(c => c.id === clip.id ? updated : c);
    requestDraw();
  }

  export function setFadeInToCursor() {
    const t = $editCursorTime;
    const clip = autoSelectClipAtCursor();
    if (!clip) return;
    if (t <= clip.position || t >= clip.position + clip.duration) return;

    $editClips = $editClips.map(c => c.id === clip.id ? { ...c, fadeIn: t - clip.position } : c);
    requestDraw();
  }

  export function setFadeOutToCursor() {
    const t = $editCursorTime;
    const clip = autoSelectClipAtCursor();
    if (!clip) return;
    if (t <= clip.position || t >= clip.position + clip.duration) return;

    $editClips = $editClips.map(c => c.id === clip.id ? { ...c, fadeOut: (clip.position + clip.duration) - t } : c);
    requestDraw();
  }

  export function zoomToFull() {
    setXRange([..._fullXRange] as [number, number]);
    requestDraw();
    syncWaveform(_xRange, _audioDuration);
  }

  export function moveToStart() {
    $editCursorTime = 0;
    onSeek?.(0);
    requestDraw();
  }

  export function moveToEnd() {
    $editCursorTime = _audioDuration;
    onSeek?.(_audioDuration);
    requestDraw();
  }

  export function moveToNextClipBoundary() {
    const t = $editCursorTime;
    const boundaries: number[] = [];
    for (const c of $editClips) {
      boundaries.push(c.position, c.position + c.duration);
    }
    boundaries.sort((a, b) => a - b);
    const next = boundaries.find(b => b > t + 0.0001);
    if (next !== undefined) {
      $editCursorTime = next;
      onSeek?.(next);
      requestDraw();
    }
  }

  export function moveToPrevClipBoundary() {
    const t = $editCursorTime;
    const boundaries: number[] = [];
    for (const c of $editClips) {
      boundaries.push(c.position, c.position + c.duration);
    }
    boundaries.sort((a, b) => b - a); // descending
    const prev = boundaries.find(b => b < t - 0.0001);
    if (prev !== undefined) {
      $editCursorTime = prev;
      onSeek?.(prev);
      requestDraw();
    }
  }

  // --- Playback engine ---
  let _audioCtx: AudioContext | null = null;
  let _scheduledSources: AudioBufferSourceNode[] = [];
  let _scheduledGains: GainNode[] = [];
  let _isPlaying = false;
  let _playStartWallTime = 0;
  let _playStartCursorTime = 0;
  let _playheadRafId = 0;

  function getAudioCtx(): AudioContext {
    if (!_audioCtx) _audioCtx = new AudioContext();
    return _audioCtx;
  }

  export function togglePlay() {
    if (_isPlaying) {
      stopPlayback();
    } else {
      startPlayback($editCursorTime);
    }
  }

  function startPlayback(fromTime: number) {
    const buffer = $editAudioBuffer;
    const clips = $editClips;
    if (!buffer || clips.length === 0) return;

    stopPlayback();

    const actx = getAudioCtx();
    if (actx.state === 'suspended') actx.resume();

    _playStartCursorTime = fromTime;
    _playStartWallTime = actx.currentTime;
    _isPlaying = true;

    const arrangementEnd = Math.max(...clips.map(c => c.position + c.duration));
    const crossfades = findCrossfades(clips);

    for (const clip of clips) {
      const clipEnd = clip.position + clip.duration;
      if (clipEnd <= fromTime) continue;

      const source = actx.createBufferSource();
      source.buffer = buffer;

      const gainNode = actx.createGain();
      gainNode.connect(actx.destination);
      source.connect(gainNode);

      // Schedule audio
      let sourceStartWall: number;
      if (fromTime > clip.position) {
        const offset = clip.sourceOffset + (fromTime - clip.position);
        const remaining = clipEnd - fromTime;
        source.start(0, offset, remaining);
        sourceStartWall = actx.currentTime;
      } else {
        const delay = clip.position - fromTime;
        source.start(actx.currentTime + delay, clip.sourceOffset, clip.duration);
        sourceStartWall = actx.currentTime + delay;
      }

      // Apply explicit fade-in
      if (clip.fadeIn && clip.fadeIn > 0) {
        const fadeInStartWall = sourceStartWall;
        const fadeInEndWall = sourceStartWall + clip.fadeIn;
        if (fromTime > clip.position && fromTime < clip.position + clip.fadeIn) {
          // Playback starts mid fade-in
          const progress = (fromTime - clip.position) / clip.fadeIn;
          gainNode.gain.setValueAtTime(progress, actx.currentTime);
          gainNode.gain.linearRampToValueAtTime(1, fadeInEndWall);
        } else if (fromTime <= clip.position) {
          gainNode.gain.setValueAtTime(0, fadeInStartWall);
          gainNode.gain.linearRampToValueAtTime(1, fadeInEndWall);
        }
      }

      // Apply explicit fade-out
      if (clip.fadeOut && clip.fadeOut > 0) {
        const fadeOutStartTime = clip.position + clip.duration - clip.fadeOut;
        const fadeOutStartWall = actx.currentTime + Math.max(0, fadeOutStartTime - fromTime);
        const fadeOutEndWall = actx.currentTime + Math.max(0, clipEnd - fromTime);
        if (fromTime < clipEnd) {
          gainNode.gain.setValueAtTime(1, fadeOutStartWall);
          gainNode.gain.linearRampToValueAtTime(0, fadeOutEndWall);
        }
      }

      // Apply crossfades involving this clip
      for (const xf of crossfades) {
        const xfStartWall = actx.currentTime + Math.max(0, xf.startTime - fromTime);
        const xfEndWall = actx.currentTime + Math.max(0, xf.endTime - fromTime);

        if (xf.clipA.id === clip.id) {
          // This clip fades out over the crossfade
          gainNode.gain.setValueAtTime(1, xfStartWall);
          gainNode.gain.linearRampToValueAtTime(0, xfEndWall);
        } else if (xf.clipB.id === clip.id) {
          // This clip fades in over the crossfade
          if (fromTime <= xf.startTime) {
            gainNode.gain.setValueAtTime(0, xfStartWall);
          }
          gainNode.gain.linearRampToValueAtTime(1, xfEndWall);
        }
      }

      _scheduledSources.push(source);
      _scheduledGains.push(gainNode);
    }

    const totalRemaining = arrangementEnd - fromTime;
    if (totalRemaining > 0) {
      setTimeout(() => {
        if (_isPlaying) stopPlayback();
      }, totalRemaining * 1000 + 100);
    }

    updatePlayheadDuringPlayback();
  }

  function stopPlayback() {
    _isPlaying = false;
    for (const src of _scheduledSources) {
      try { src.stop(); } catch { /* already stopped */ }
    }
    _scheduledSources = [];
    _scheduledGains = [];
    if (_playheadRafId) {
      cancelAnimationFrame(_playheadRafId);
      _playheadRafId = 0;
    }
  }

  function updatePlayheadDuringPlayback() {
    if (!_isPlaying || !_audioCtx) return;
    const elapsed = _audioCtx.currentTime - _playStartWallTime;
    _playheadTime = _playStartCursorTime + elapsed;
    $editCursorTime = _playheadTime;
    requestDraw();
    _playheadRafId = requestAnimationFrame(updatePlayheadDuringPlayback);
  }

  // --- Resize ---
  function resizeCanvas() {
    if (!canvasEl || !containerEl) return;
    const rect = containerEl.getBoundingClientRect();
    canvasEl.width = rect.width;
    canvasEl.height = rect.height;
    ctx = canvasEl.getContext('2d')!;
    requestDraw();
  }

  // --- Public methods ---
  export function setPlayheadTime(t: number) {
    _playheadTime = t;
    requestDraw();
  }

  // Expose crossfade finder for offline rendering
  export function getCrossfades(): CrossfadeRegion[] {
    return findCrossfades($editClips);
  }

  // --- Lifecycle ---
  onMount(() => {
    _mounted = true;
    resizeCanvas();
    const ro = new ResizeObserver(() => resizeCanvas());
    ro.observe(containerEl);

    return () => {
      _mounted = false;
      ro.disconnect();
      stopPlayback();
      _audioCtx?.close();
      _audioCtx = null;
    };
  });

  $effect(() => {
    void $editClips;
    void $editSelectedClipIds;
    void $editCursorTime;
    requestDraw();
  });

  $effect(() => {
    void $viewXRange;
    if ($activeTab === 'edit') {
      _xRange = $viewXRange;
      requestDraw();
    }
  });

  $effect(() => {
    void $waveformReset;
    _pendingZoomReset = true;
    loadAudio();
  });

  $effect(() => {
    if ($audioLoaded && $activeTab === 'edit') {
      loadAudio();
    }
  });
</script>

<div class="edit-view" bind:this={containerEl}>
  <canvas
    bind:this={canvasEl}
    onmousedown={onMouseDown}
    onmousemove={onMouseMove}
    onmouseup={onMouseUp}
    onmouseleave={onMouseUp}
    onwheel={onWheel}
  ></canvas>
</div>

<style>
  .edit-view {
    flex: 1;
    min-height: 200px;
    position: relative;
    overflow: hidden;
  }
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    cursor: crosshair;
  }
</style>
