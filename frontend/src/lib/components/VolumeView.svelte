<script lang="ts">
  import { onMount } from 'svelte';
  import {
    volumeClusters, breaths, selectedBreathIdx, activeTab,
    viewXRange, waveformReset, audioLoaded, volumeMacroParams, dirtyVolume,
  } from '$lib/stores/appState';
  import type { VolumeCluster, Breath } from '$lib/utils/types';

  interface Props {
    syncWaveform: (xRange: [number, number], totalDuration: number) => void;
    onSeek?: (time: number) => void;
    onBreathClick?: (time: number) => void;
    onBreathAltClick?: (breathId: number) => void;
    onNoteRemove?: (id: number) => void;
    onSegmentAdd?: (type: 'note' | 'breath', startTime: number, endTime: number) => void;
    onSegmentResize?: (type: 'note' | 'breath', id: number, startTime: number, endTime: number) => void;
  }

  let { syncWaveform, onSeek, onBreathClick, onBreathAltClick, onNoteRemove, onSegmentAdd, onSegmentResize }: Props = $props();

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

  // Waveform data
  let _waveformData: Float32Array | null = null;
  let _waveformSr = 0;
  let _audioDuration = 0;

  // Interaction state
  let _hoverSegment: { type: 'note' | 'breath'; id: number } | null = null;
  let _hoverEdge: { type: 'note' | 'breath'; id: number; edge: 'left' | 'right' } | null = null;
  let _dragSegment: { type: 'note' | 'breath'; id: number; startY: number; startGain: number } | null = null;
  let _drawPreview: { type: 'note' | 'breath'; startTime: number; endTime: number } | null = null;

  function setXRange(range: [number, number]) {
    _xRange = range;
    $viewXRange = range;
  }

  const COLORS = {
    bg: '#16213e',
    bg2: '#0f3460',
    gridLine: '#2a2a4a',
    text: '#ccc',
    textDim: '#888',
    playhead: '#e94560',
    waveform: 'rgba(100, 180, 255, 0.45)',
    noteSegment: '#ff8c42',
    noteSegmentFill: 'rgba(255, 140, 66, 0.18)',
    breathSegment: '#2dd4bf',
    breathSegmentFill: 'rgba(45, 212, 191, 0.18)',
    breathRegion: 'rgba(45, 212, 191, 0.12)',
    baseline: 'rgba(255,255,255,0.25)',
    ramp: '#aaaacc',
    zeroLine: 'rgba(255,255,255,0.15)',
    selectedBreath: 'rgba(45,212,191,0.3)',
  };

  const MARGIN = { l: 60, r: 20, t: 20, b: 30 };
  const GAIN_DB_RANGE = 20; // ±20 dB shown on gain panel

  // ─── Effective gain computation (mirrors backend logic, client-side) ─────────

  function computeEffectiveGain(
    rmsDb: number,
    manualGainDb: number,
    minRms: number,
    maxRms: number,
    globalOffset: number,
    isManual: boolean = false,
  ): number {
    if (isManual) return manualGainDb; // bypass all macro controls
    let gain = manualGainDb;
    if (rmsDb + gain < minRms) gain = minRms - rmsDb;
    if (rmsDb + gain > maxRms) gain = maxRms - rmsDb;
    gain += globalOffset;
    return gain;
  }

  function getEffectiveGains(): Map<string, number> {
    const mp = $volumeMacroParams;
    const result = new Map<string, number>();
    for (const c of $volumeClusters) {
      const g = computeEffectiveGain(
        c.rms_db,
        c.gain_db,
        mp.note_min_rms_db,
        mp.note_max_rms_db,
        mp.note_global_offset_db,
        c.manual ?? false,
      );
      result.set(`note-${c.id}`, g);
    }
    for (const b of $breaths) {
      const g = computeEffectiveGain(
        b.rms_db,
        b.gain_db,
        mp.breath_min_rms_db,
        mp.breath_max_rms_db,
        mp.breath_global_offset_db,
        b.manual ?? false,
      );
      result.set(`breath-${b.id}`, g);
    }
    return result;
  }

  // ─── Waveform loading ────────────────────────────────────────────────────────

  export async function loadWaveform() {
    try {
      const resp = await fetch(`/api/audio?t=${Date.now()}`);
      if (!resp.ok) return;
      const buf = await resp.arrayBuffer();
      const audioCtx = new AudioContext();
      const decoded = await audioCtx.decodeAudioData(buf);
      _waveformData = decoded.getChannelData(0);
      _waveformSr = decoded.sampleRate;
      _audioDuration = decoded.duration;
      audioCtx.close();
      if (_audioDuration > 0) {
        _fullXRange = [0, _audioDuration];
        if (_pendingZoomReset) {
          setXRange([..._fullXRange] as [number, number]);
          _pendingZoomReset = false;
        }
        syncWaveform(_xRange, _audioDuration);
      }
      requestDraw();
    } catch {
      // ignore
    }
  }

  export function onTimeUpdate(t: number) {
    _playheadTime = t;
    requestDraw();
  }

  export function resetView() {
    if (_audioDuration > 0) {
      setXRange([0, _audioDuration]);
    } else {
      _pendingZoomReset = true;
    }
    requestDraw();
  }

  // ─── Drawing ─────────────────────────────────────────────────────────────────

  function requestDraw() {
    if (_rafPending || !_mounted) return;
    _rafPending = true;
    requestAnimationFrame(() => {
      _rafPending = false;
      draw();
    });
  }

  function draw() {
    if (!ctx || !canvasEl) return;
    const W = canvasEl.width;
    const H = canvasEl.height;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    const [xMin, xMax] = _xRange;
    const xSpan = xMax - xMin;
    if (xSpan <= 0) return;

    const plotW = W - MARGIN.l - MARGIN.r;
    const topH = Math.floor((H - MARGIN.t - MARGIN.b) * 0.55);
    const bottomH = H - MARGIN.t - MARGIN.b - topH;

    const toX = (t: number) => MARGIN.l + ((t - xMin) / xSpan) * plotW;
    const topMidY = MARGIN.t + topH / 2;
    const gainAreaTop = MARGIN.t + topH + 10;
    const gainAreaH = bottomH - 10;
    const gainMidY = gainAreaTop + gainAreaH / 2;
    const gainToY = (db: number) => gainMidY - (db / GAIN_DB_RANGE) * (gainAreaH / 2);

    drawTimeGrid(W, H, plotW, topH, gainAreaH, gainAreaTop, xMin, xMax, toX);

    // ── Breath region overlays on waveform ─────────────────
    for (const b of $breaths) {
      const x1 = toX(b.start_time);
      const x2 = toX(b.end_time);
      const isSelected = $selectedBreathIdx !== null && $breaths[$selectedBreathIdx]?.id === b.id;
      ctx.fillStyle = isSelected ? COLORS.selectedBreath : COLORS.breathRegion;
      ctx.fillRect(x1, MARGIN.t, x2 - x1, topH);
    }

    // ── Note cluster region overlays ──────────────────────
    for (const c of $volumeClusters) {
      const x1 = toX(c.start_time);
      const x2 = toX(c.end_time);
      ctx.fillStyle = 'rgba(255, 140, 66, 0.07)';
      ctx.fillRect(x1, MARGIN.t, x2 - x1, topH);
    }

    // ── Draw preview overlay ──────────────────────────────
    if (_drawPreview) {
      const x1 = toX(_drawPreview.startTime);
      const x2 = toX(_drawPreview.endTime);
      const color = _drawPreview.type === 'note' ? 'rgba(255, 140, 66, 0.25)' : 'rgba(45, 212, 191, 0.25)';
      ctx.fillStyle = color;
      ctx.fillRect(x1, MARGIN.t, x2 - x1, topH);
    }

    // ── Waveform ──────────────────────────────────────────
    if (_waveformData && _waveformSr) {
      drawWaveform(plotW, topH, xMin, xMax, toX, topMidY);
    }

    // ── Divider line ──────────────────────────────────────
    ctx.strokeStyle = COLORS.gridLine;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(MARGIN.l, MARGIN.t + topH + 5);
    ctx.lineTo(W - MARGIN.r, MARGIN.t + topH + 5);
    ctx.stroke();

    // ── Gain panel ────────────────────────────────────────
    drawGainPanel(plotW, gainAreaH, gainAreaTop, gainMidY, gainToY, toX, W);

    // ── Playhead ──────────────────────────────────────────
    const px = toX(_playheadTime);
    if (px >= MARGIN.l && px <= MARGIN.l + plotW) {
      ctx.strokeStyle = COLORS.playhead;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px, MARGIN.t);
      ctx.lineTo(px, H - MARGIN.b);
      ctx.stroke();
    }
  }

  function drawTimeGrid(
    W: number, H: number, plotW: number, topH: number, gainAreaH: number,
    gainAreaTop: number, xMin: number, xMax: number, toX: (t: number) => number,
  ) {
    const span = xMax - xMin;
    const rawStep = span / 8;
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    const steps = [1, 2, 5, 10];
    const step = mag * (steps.find(s => s * mag >= rawStep) ?? 10);

    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    ctx.fillStyle = COLORS.textDim;

    const start = Math.ceil(xMin / step) * step;
    for (let t = start; t <= xMax; t += step) {
      const x = toX(t);
      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(x, MARGIN.t);
      ctx.lineTo(x, H - MARGIN.b);
      ctx.stroke();
      ctx.fillText(t.toFixed(1) + 's', x, H - MARGIN.b + 14);
    }

    // Y-axis labels for waveform
    ctx.fillStyle = COLORS.textDim;
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText('Audio', MARGIN.l - 6, MARGIN.t + topH / 2);

    // Y-axis labels for gain panel
    const gainMidY = gainAreaTop + gainAreaH / 2;
    ctx.fillText('0 dB', MARGIN.l - 4, gainMidY);
    ctx.fillText(`+${GAIN_DB_RANGE}`, MARGIN.l - 4, gainAreaTop + 8);
    ctx.fillText(`-${GAIN_DB_RANGE}`, MARGIN.l - 4, gainAreaTop + gainAreaH - 4);
  }

  function drawWaveform(
    plotW: number, topH: number, xMin: number, xMax: number,
    toX: (t: number) => number, midY: number,
  ) {
    if (!_waveformData || !_waveformSr) return;
    const halfH = topH * 0.45;
    const startSample = Math.max(0, Math.floor(xMin * _waveformSr));
    const endSample = Math.min(_waveformData.length, Math.ceil(xMax * _waveformSr));
    const samplesPerPixel = Math.max(1, Math.floor((endSample - startSample) / plotW));

    ctx.fillStyle = COLORS.waveform;
    ctx.beginPath();

    for (let px = 0; px < plotW; px++) {
      const s0 = startSample + Math.floor(px * (endSample - startSample) / plotW);
      const s1 = Math.min(s0 + samplesPerPixel, _waveformData.length);
      let minV = 0, maxV = 0;
      for (let s = s0; s < s1; s++) {
        const v = _waveformData[s];
        if (v < minV) minV = v;
        if (v > maxV) maxV = v;
      }
      const x = MARGIN.l + px;
      const y1 = midY - maxV * halfH;
      const y2 = midY - minV * halfH;
      ctx.rect(x, y1, 1, Math.max(1, y2 - y1));
    }
    ctx.fill();
  }

  function drawGainPanel(
    plotW: number, gainAreaH: number, gainAreaTop: number, gainMidY: number,
    gainToY: (db: number) => number, toX: (t: number) => number, W: number,
  ) {
    const [xMin, xMax] = _xRange;
    const effectiveGains = getEffectiveGains();

    // Background
    ctx.fillStyle = 'rgba(255,255,255,0.02)';
    ctx.fillRect(MARGIN.l, gainAreaTop, W - MARGIN.l - MARGIN.r, gainAreaH);

    // Zero dB line
    ctx.strokeStyle = COLORS.zeroLine;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(MARGIN.l, gainMidY);
    ctx.lineTo(W - MARGIN.r, gainMidY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Horizontal dB gridlines at ±5, ±10, ±15
    for (const db of [-15, -10, -5, 5, 10, 15]) {
      const y = gainToY(db);
      ctx.strokeStyle = COLORS.gridLine;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(MARGIN.l, y);
      ctx.lineTo(W - MARGIN.r, y);
      ctx.stroke();
    }

    // Build sorted list of all gain segments within view
    type GainSeg = { start: number; end: number; gain: number; type: 'note' | 'breath'; id: number };
    const segs: GainSeg[] = [];

    for (const c of $volumeClusters) {
      if (c.end_time < xMin || c.start_time > xMax) continue;
      const gain = effectiveGains.get(`note-${c.id}`) ?? 0;
      segs.push({ start: c.start_time, end: c.end_time, gain, type: 'note', id: c.id });
    }
    for (const b of $breaths) {
      if (b.end_time < xMin || b.start_time > xMax) continue;
      const gain = effectiveGains.get(`breath-${b.id}`) ?? 0;
      segs.push({ start: b.start_time, end: b.end_time, gain, type: 'breath', id: b.id });
    }
    segs.sort((a, b) => a.start - b.start);

    if (segs.length === 0) return;

    // Draw filled segment areas
    for (const seg of segs) {
      const x1 = Math.max(MARGIN.l, toX(seg.start));
      const x2 = Math.min(W - MARGIN.r, toX(seg.end));
      const y = gainToY(seg.gain);
      const isHovered = _hoverSegment?.type === seg.type && _hoverSegment?.id === seg.id;

      ctx.fillStyle = seg.type === 'note' ? COLORS.noteSegmentFill : COLORS.breathSegmentFill;
      if (isHovered) ctx.fillStyle = seg.type === 'note'
        ? 'rgba(255,140,66,0.35)'
        : 'rgba(45,212,191,0.35)';

      const rectTop = Math.min(y, gainMidY);
      const rectH = Math.abs(y - gainMidY);
      ctx.fillRect(x1, rectTop, x2 - x1, rectH);
    }

    // Draw ramps between adjacent segments
    ctx.strokeStyle = COLORS.ramp;
    ctx.lineWidth = 1;
    for (let i = 0; i < segs.length - 1; i++) {
      const curr = segs[i];
      const next = segs[i + 1];
      const x1 = toX(curr.end);
      const x2 = toX(next.start);
      const y1 = gainToY(curr.gain);
      const y2 = gainToY(next.gain);
      if (x2 > x1 + 1) {
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    }

    // Draw flat segment lines (on top)
    for (const seg of segs) {
      const x1 = Math.max(MARGIN.l, toX(seg.start));
      const x2 = Math.min(W - MARGIN.r, toX(seg.end));
      const y = gainToY(seg.gain);
      const isHovered = _hoverSegment?.type === seg.type && _hoverSegment?.id === seg.id;

      ctx.strokeStyle = seg.type === 'note' ? COLORS.noteSegment : COLORS.breathSegment;
      ctx.lineWidth = isHovered ? 2.5 : 1.5;
      ctx.beginPath();
      ctx.moveTo(x1, y);
      ctx.lineTo(x2, y);
      ctx.stroke();

      // Label
      const midX = (x1 + x2) / 2;
      if (x2 - x1 > 24) {
        ctx.fillStyle = seg.type === 'note' ? COLORS.noteSegment : COLORS.breathSegment;
        ctx.font = '9px sans-serif';
        ctx.textAlign = 'center';
        const label = seg.gain === 0 ? '0 dB' : `${seg.gain > 0 ? '+' : ''}${seg.gain.toFixed(1)} dB`;
        ctx.fillText(label, midX, y - 5);
      }
    }

    // Draw preview box in gain area
    if (_drawPreview) {
      const x1 = Math.max(MARGIN.l, toX(_drawPreview.startTime));
      const x2 = Math.min(W - MARGIN.r, toX(_drawPreview.endTime));
      const color = _drawPreview.type === 'note' ? COLORS.noteSegment : COLORS.breathSegment;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x1, gainMidY);
      ctx.lineTo(x2, gainMidY);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  // ─── Hit testing ────────────────────────────────────────────────────────────

  function getCanvasCoords(e: MouseEvent): { px: number; py: number } {
    const rect = canvasEl.getBoundingClientRect();
    return { px: e.clientX - rect.left, py: e.clientY - rect.top };
  }

  function pxToTime(px: number): number {
    const W = canvasEl.width;
    const plotW = W - MARGIN.l - MARGIN.r;
    const [xMin, xMax] = _xRange;
    return xMin + ((px - MARGIN.l) / plotW) * (xMax - xMin);
  }

  function timeToPx(t: number): number {
    const W = canvasEl.width;
    const plotW = W - MARGIN.l - MARGIN.r;
    const [xMin, xMax] = _xRange;
    return MARGIN.l + ((t - xMin) / (xMax - xMin)) * plotW;
  }

  function isInPlotArea(px: number, py: number): boolean {
    const W = canvasEl.width;
    const H = canvasEl.height;
    return px > MARGIN.l && px < W - MARGIN.r && py > MARGIN.t && py < H - MARGIN.b;
  }

  function getGainAreaBounds(): { top: number; bottom: number; midY: number } {
    const H = canvasEl.height;
    const totalH = H - MARGIN.t - MARGIN.b;
    const topH = Math.floor(totalH * 0.55);
    const gainTop = MARGIN.t + topH + 10;
    const gainH = totalH - topH - 10;
    return { top: gainTop, bottom: gainTop + gainH, midY: gainTop + gainH / 2 };
  }

  function getWaveformAreaBounds(): { top: number; bottom: number } {
    const H = canvasEl.height;
    const totalH = H - MARGIN.t - MARGIN.b;
    const topH = Math.floor(totalH * 0.55);
    return { top: MARGIN.t, bottom: MARGIN.t + topH };
  }

  function getSegmentAtGainArea(px: number, py: number): { type: 'note' | 'breath'; id: number } | null {
    const { top, bottom } = getGainAreaBounds();
    if (py < top || py > bottom) return null;
    const time = pxToTime(px);
    // Check clusters first, then breaths
    for (const c of $volumeClusters) {
      if (time >= c.start_time && time <= c.end_time) {
        return { type: 'note', id: c.id };
      }
    }
    for (const b of $breaths) {
      if (time >= b.start_time && time <= b.end_time) {
        return { type: 'breath', id: b.id };
      }
    }
    return null;
  }

  function getBreathAtWaveform(px: number, py: number): Breath | null {
    const { top, bottom } = getWaveformAreaBounds();
    if (py < top || py > bottom) return null;
    const time = pxToTime(px);
    for (const b of $breaths) {
      if (time >= b.start_time && time <= b.end_time) return b;
    }
    return null;
  }

  const EDGE_HIT_PX = 6; // pixels from edge that counts as an edge hit

  function getEdgeAtPosition(px: number, py: number): { type: 'note' | 'breath'; id: number; edge: 'left' | 'right' } | null {
    const { top: wTop, bottom: wBottom } = getWaveformAreaBounds();
    const { top: gTop, bottom: gBottom } = getGainAreaBounds();
    if ((py < wTop || py > wBottom) && (py < gTop || py > gBottom)) return null;

    for (const c of $volumeClusters) {
      const x1 = timeToPx(c.start_time);
      const x2 = timeToPx(c.end_time);
      if (Math.abs(px - x1) <= EDGE_HIT_PX) return { type: 'note', id: c.id, edge: 'left' };
      if (Math.abs(px - x2) <= EDGE_HIT_PX) return { type: 'note', id: c.id, edge: 'right' };
    }
    for (const b of $breaths) {
      const x1 = timeToPx(b.start_time);
      const x2 = timeToPx(b.end_time);
      if (Math.abs(px - x1) <= EDGE_HIT_PX) return { type: 'breath', id: b.id, edge: 'left' };
      if (Math.abs(px - x2) <= EDGE_HIT_PX) return { type: 'breath', id: b.id, edge: 'right' };
    }
    return null;
  }

  function isTimeEmpty(time: number): boolean {
    for (const c of $volumeClusters) {
      if (time >= c.start_time && time <= c.end_time) return false;
    }
    for (const b of $breaths) {
      if (time >= b.start_time && time <= b.end_time) return false;
    }
    return true;
  }

  /** Returns the valid [start, end] clamped so the box doesn't overlap others. */
  function clampToNonOverlapping(
    startTime: number, endTime: number,
    excludeType: 'note' | 'breath', excludeId: number
  ): [number, number] {
    const MIN_GAP = 0.005;
    let leftBound = 0;
    let rightBound = _audioDuration || 999;

    const boxes = [
      ...$volumeClusters.filter(c => !(excludeType === 'note' && c.id === excludeId))
        .map(c => ({ start: c.start_time, end: c.end_time })),
      ...$breaths.filter(b => !(excludeType === 'breath' && b.id === excludeId))
        .map(b => ({ start: b.start_time, end: b.end_time })),
    ];

    for (const box of boxes) {
      // Box entirely to the left
      if (box.end <= startTime + MIN_GAP) leftBound = Math.max(leftBound, box.end + MIN_GAP);
      // Box entirely to the right
      if (box.start >= endTime - MIN_GAP) rightBound = Math.min(rightBound, box.start - MIN_GAP);
    }

    return [Math.max(leftBound, startTime), Math.min(rightBound, endTime)];
  }

  /** Clamp a new box [start, end] against all existing boxes. */
  function clampNewBox(startTime: number, endTime: number): [number, number] {
    const MIN_GAP = 0.005;
    let left = Math.min(startTime, endTime);
    let right = Math.max(startTime, endTime);

    for (const c of $volumeClusters) {
      if (c.end_time <= left) left = Math.max(left, c.end_time + MIN_GAP);
      if (c.start_time >= right) right = Math.min(right, c.start_time - MIN_GAP);
      // If overlapping, shrink from the drag direction
      if (c.start_time < right && c.end_time > left) {
        // find which side has less overlap
        const overlapLeft = right - c.start_time;
        const overlapRight = c.end_time - left;
        if (overlapLeft < overlapRight) right = c.start_time - MIN_GAP;
        else left = c.end_time + MIN_GAP;
      }
    }
    for (const b of $breaths) {
      if (b.end_time <= left) left = Math.max(left, b.end_time + MIN_GAP);
      if (b.start_time >= right) right = Math.min(right, b.start_time - MIN_GAP);
      if (b.start_time < right && b.end_time > left) {
        const overlapLeft = right - b.start_time;
        const overlapRight = b.end_time - left;
        if (overlapLeft < overlapRight) right = b.start_time - MIN_GAP;
        else left = b.end_time + MIN_GAP;
      }
    }
    return [left, right];
  }

  // ─── Interactions ────────────────────────────────────────────────────────────

  function setupInteractions() {
    type Mode = 'gain-drag' | 'edge-resize' | 'draw' | 'pan' | 'seek' | null;
    let mode: Mode = null;
    let panStartXRange: [number, number] | null = null;
    let panStartX = 0;

    // Edge resize state
    let resizeSeg: { type: 'note' | 'breath'; id: number; edge: 'left' | 'right';
                     fixedTime: number } | null = null;

    // Draw state
    let drawType: 'note' | 'breath' = 'note';
    let drawAnchorTime = 0;

    function updateCursor(px: number, py: number) {
      const edge = getEdgeAtPosition(px, py);
      if (edge) {
        canvasEl.style.cursor = 'ew-resize';
        const changed = edge.type !== _hoverEdge?.type || edge.id !== _hoverEdge?.id || edge.edge !== _hoverEdge?.edge;
        _hoverEdge = edge;
        _hoverSegment = null;
        if (changed) requestDraw();
        return;
      }
      _hoverEdge = null;
      const seg = getSegmentAtGainArea(px, py);
      const changed = seg?.type !== _hoverSegment?.type || seg?.id !== _hoverSegment?.id;
      _hoverSegment = seg;
      canvasEl.style.cursor = seg ? 'ns-resize' : 'crosshair';
      if (changed) requestDraw();
    }

    canvasEl.addEventListener('mousemove', (e: MouseEvent) => {
      const { px, py } = getCanvasCoords(e);

      if (mode === 'gain-drag' && _dragSegment) {
        const dyPx = _dragSegment.startY - py;
        const gainAreaH = getGainAreaBounds().bottom - getGainAreaBounds().top;
        const dbPerPx = (GAIN_DB_RANGE * 2) / gainAreaH;
        const newGain = Math.round((_dragSegment.startGain + dyPx * dbPerPx) * 2) / 2;

        if (_dragSegment.type === 'note') {
          const idx = $volumeClusters.findIndex(c => c.id === _dragSegment!.id);
          if (idx >= 0) {
            const updated = [...$volumeClusters];
            updated[idx] = { ...updated[idx], gain_db: newGain, manual: true };
            $volumeClusters = updated;
          }
        } else {
          const idx = $breaths.findIndex(b => b.id === _dragSegment!.id);
          if (idx >= 0) {
            const updated = [...$breaths];
            updated[idx] = { ...updated[idx], gain_db: newGain, manual: true };
            $breaths = updated;
          }
        }
        $dirtyVolume = true;
        requestDraw();
        return;
      }

      if (mode === 'edge-resize' && resizeSeg) {
        let newTime = pxToTime(px);
        const seg = resizeSeg;
        // Get the existing box boundaries
        let curStart: number, curEnd: number;
        if (seg.type === 'note') {
          const c = $volumeClusters.find(c => c.id === seg.id);
          curStart = c?.start_time ?? 0; curEnd = c?.end_time ?? 0;
        } else {
          const b = $breaths.find(b => b.id === seg.id);
          curStart = b?.start_time ?? 0; curEnd = b?.end_time ?? 0;
        }
        const MIN_DUR = 0.02; // 20ms minimum segment duration
        let newStart = curStart, newEnd = curEnd;
        if (seg.edge === 'left') {
          newStart = Math.min(newTime, curEnd - MIN_DUR);
          [newStart, newEnd] = clampToNonOverlapping(newStart, curEnd, seg.type, seg.id);
        } else {
          newEnd = Math.max(newTime, curStart + MIN_DUR);
          [newStart, newEnd] = clampToNonOverlapping(curStart, newEnd, seg.type, seg.id);
        }
        // Update store for live preview
        if (seg.type === 'note') {
          $volumeClusters = $volumeClusters.map(c =>
            c.id === seg.id ? { ...c, start_time: newStart, end_time: newEnd } : c
          );
        } else {
          $breaths = $breaths.map(b =>
            b.id === seg.id ? { ...b, start_time: newStart, end_time: newEnd } : b
          );
        }
        requestDraw();
        return;
      }

      if (mode === 'draw') {
        let newTime = pxToTime(px);
        newTime = Math.max(0, Math.min(_audioDuration || 999, newTime));
        const [s, e] = newTime >= drawAnchorTime
          ? [drawAnchorTime, newTime]
          : [newTime, drawAnchorTime];
        const [cs, ce] = clampNewBox(s, e);
        _drawPreview = { type: drawType, startTime: cs, endTime: ce };
        requestDraw();
        return;
      }

      if (mode === 'pan' && panStartXRange) {
        const dxPx = e.clientX - panStartX;
        const plotW = canvasEl.width - MARGIN.l - MARGIN.r;
        const [xMin0, xMax0] = panStartXRange;
        const dxTime = -(dxPx / plotW) * (xMax0 - xMin0);
        let newMin = xMin0 + dxTime;
        let newMax = xMax0 + dxTime;
        const dur = _audioDuration || 30;
        if (newMin < 0) { newMax -= newMin; newMin = 0; }
        if (newMax > dur) { newMin -= newMax - dur; newMax = dur; }
        setXRange([Math.max(0, newMin), Math.min(dur, newMax)]);
        syncWaveform(_xRange, _audioDuration);
        requestDraw();
        return;
      }

      updateCursor(px, py);
    });

    canvasEl.addEventListener('mousedown', (e: MouseEvent) => {
      if (e.button !== 0) return;
      const { px, py } = getCanvasCoords(e);
      if (!isInPlotArea(px, py)) return;

      // Shift+drag → pan
      if (e.shiftKey) {
        mode = 'pan';
        panStartX = e.clientX;
        panStartXRange = [..._xRange] as [number, number];
        canvasEl.style.cursor = 'grabbing';
        e.preventDefault();
        return;
      }

      // Alt+click → delete
      if (e.altKey) {
        // Check if a drag will follow (alt+drag in empty = add note)
        // We'll handle this in mousemove/mouseup
        const time = pxToTime(px);

        // Alt-click on breath in waveform or gain area → remove breath
        const breathWave = getBreathAtWaveform(px, py);
        if (breathWave) { onBreathAltClick?.(breathWave.id); e.preventDefault(); return; }
        const seg = getSegmentAtGainArea(px, py);
        if (seg?.type === 'breath') { onBreathAltClick?.(seg.id); e.preventDefault(); return; }
        if (seg?.type === 'note') { onNoteRemove?.(seg.id); e.preventDefault(); return; }

        // Also check waveform area for note overlays
        const { top: wTop, bottom: wBottom } = getWaveformAreaBounds();
        if (py >= wTop && py <= wBottom) {
          for (const c of $volumeClusters) {
            if (time >= c.start_time && time <= c.end_time) {
              onNoteRemove?.(c.id); e.preventDefault(); return;
            }
          }
        }

        // Alt+drag in empty area → add note
        if (isTimeEmpty(time)) {
          drawType = 'note';
          drawAnchorTime = time;
          _drawPreview = { type: 'note', startTime: time, endTime: time };
          mode = 'draw';
          e.preventDefault();
          return;
        }
        return;
      }

      // Ctrl+drag in empty area → add breath
      if (e.ctrlKey) {
        const time = pxToTime(px);
        if (isTimeEmpty(time)) {
          drawType = 'breath';
          drawAnchorTime = time;
          _drawPreview = { type: 'breath', startTime: time, endTime: time };
          mode = 'draw';
          e.preventDefault();
          return;
        }
        return;
      }

      // Edge resize
      const edge = getEdgeAtPosition(px, py);
      if (edge) {
        resizeSeg = edge;
        mode = 'edge-resize';
        canvasEl.style.cursor = 'ew-resize';
        e.preventDefault();
        return;
      }

      // Gain drag
      const seg = getSegmentAtGainArea(px, py);
      if (seg) {
        let startGain = 0;
        if (seg.type === 'note') {
          const c = $volumeClusters.find(c => c.id === seg.id);
          startGain = c?.gain_db ?? 0;
        } else {
          const b = $breaths.find(b => b.id === seg.id);
          startGain = b?.gain_db ?? 0;
        }
        _dragSegment = { ...seg, startY: py, startGain };
        mode = 'gain-drag';
        canvasEl.style.cursor = 'ns-resize';
        e.preventDefault();
        return;
      }

      // Click in waveform (not on any segment) → seek or old breath-create
      const { top: wTop, bottom: wBottom } = getWaveformAreaBounds();
      if (py >= wTop && py <= wBottom) {
        const t = pxToTime(px);
        onSeek?.(t);
        e.preventDefault();
        return;
      }

      // Seek (gain area, not on segment)
      const { top: gTop, bottom: gBottom } = getGainAreaBounds();
      if (py >= gTop && py <= gBottom) {
        mode = 'seek';
        onSeek?.(pxToTime(px));
        e.preventDefault();
      }
    });

    canvasEl.addEventListener('mouseup', (e: MouseEvent) => {
      if (mode === 'gain-drag') {
        _dragSegment = null;
      }

      if (mode === 'edge-resize' && resizeSeg) {
        // Fire resize callback with final boundaries
        const seg = resizeSeg;
        if (seg.type === 'note') {
          const c = $volumeClusters.find(c => c.id === seg.id);
          if (c) onSegmentResize?.(seg.type, seg.id, c.start_time, c.end_time);
        } else {
          const b = $breaths.find(b => b.id === seg.id);
          if (b) onSegmentResize?.(seg.type, seg.id, b.start_time, b.end_time);
        }
        resizeSeg = null;
      }

      if (mode === 'draw' && _drawPreview) {
        const MIN_DUR = 0.02;
        if (_drawPreview.endTime - _drawPreview.startTime >= MIN_DUR) {
          onSegmentAdd?.(_drawPreview.type, _drawPreview.startTime, _drawPreview.endTime);
        }
        _drawPreview = null;
        requestDraw();
      }

      mode = null;
      panStartXRange = null;
      const { px, py } = getCanvasCoords(e);
      updateCursor(px, py);
    });

    canvasEl.addEventListener('mouseleave', () => {
      if (mode === 'gain-drag' || mode === 'edge-resize') return; // keep dragging
      mode = null;
      _hoverSegment = null;
      _hoverEdge = null;
      _drawPreview = null;
      _dragSegment = null;
      canvasEl.style.cursor = 'crosshair';
      requestDraw();
    });

    canvasEl.addEventListener('wheel', (e: WheelEvent) => {
      e.preventDefault();
      const { px } = getCanvasCoords(e);
      const t = pxToTime(px);
      const factor = e.deltaY > 0 ? 1.15 : 0.87;
      const [xMin, xMax] = _xRange;
      const dur = _audioDuration || 30;
      let newMin = t - (t - xMin) * factor;
      let newMax = t + (xMax - t) * factor;
      newMin = Math.max(0, newMin);
      newMax = Math.min(dur, newMax);
      if (newMax - newMin < 0.5) return;
      setXRange([newMin, newMax]);
      syncWaveform(_xRange, _audioDuration);
      requestDraw();
    }, { passive: false });
  }

  // ─── Resize handling ─────────────────────────────────────────────────────────

  function resizeCanvas() {
    if (!containerEl || !canvasEl) return;
    const rect = containerEl.getBoundingClientRect();
    canvasEl.width = rect.width;
    canvasEl.height = rect.height;
    requestDraw();
  }

  // ─── Reactive effects ────────────────────────────────────────────────────────

  $effect(() => {
    void $volumeClusters; void $breaths; void $volumeMacroParams; void $selectedBreathIdx;
    void _drawPreview; void _hoverEdge;
    requestDraw();
  });

  $effect(() => {
    void $viewXRange;
    if ($activeTab === 'volume') {
      _xRange = $viewXRange;
      requestDraw();
      if (_audioDuration > 0) syncWaveform(_xRange, _audioDuration);
    }
  });

  $effect(() => {
    void $waveformReset;
    _pendingZoomReset = true;
    loadWaveform();
  });

  $effect(() => {
    if ($audioLoaded && $activeTab === 'volume') {
      loadWaveform();
    }
  });

  onMount(() => {
    ctx = canvasEl.getContext('2d')!;
    _mounted = true;
    resizeCanvas();
    setupInteractions();

    const ro = new ResizeObserver(resizeCanvas);
    ro.observe(containerEl);

    return () => {
      ro.disconnect();
      _mounted = false;
    };
  });
</script>

<div class="volume-view" bind:this={containerEl}>
  <canvas bind:this={canvasEl} style="cursor: crosshair;"></canvas>
  {#if !$audioLoaded}
    <div class="empty-overlay">Load audio to begin</div>
  {/if}
</div>

<style>
  .volume-view {
    flex: 1;
    position: relative;
    overflow: hidden;
    background: var(--bg2);
    min-height: 0;
  }

  canvas {
    display: block;
    width: 100%;
    height: 100%;
  }

  .empty-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-dim);
    font-size: 0.85rem;
    pointer-events: none;
  }
</style>
