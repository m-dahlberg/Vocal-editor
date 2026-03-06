import type { Cluster } from '$lib/utils/types';

export const NOTE_FREQ_MAP: [string, number][] = [
  ['C2',65.41],['C#2',69.30],['D2',73.42],['D#2',77.78],
  ['E2',82.41],['F2',87.31],['F#2',92.50],['G2',98.00],
  ['G#2',103.83],['A2',110.00],['A#2',116.54],['B2',123.47],
  ['C3',130.81],['C#3',138.59],['D3',146.83],['D#3',155.56],
  ['E3',164.81],['F3',174.61],['F#3',185.00],['G3',196.00],
  ['G#3',207.65],['A3',220.00],['A#3',233.08],['B3',246.94],
  ['C4',261.63],['C#4',277.18],['D4',293.66],['D#4',311.13],
  ['E4',329.63],['F4',349.23],['F#4',369.99],['G4',392.00],
  ['G#4',415.30],['A4',440.00],['A#4',466.16],['B4',493.88],
  ['C5',523.25],['C#5',554.37],['D5',587.33],['D#5',622.25],
];

export function getYRange(frequencies: (number | null)[]): [number, number] {
  const valid = frequencies.filter((f): f is number => f != null && !isNaN(f));
  if (valid.length === 0) return [75, 600];
  return [Math.min(...valid) * 0.93, Math.max(...valid) * 1.07];
}

export function closestNote(freq: number): string {
  let bestNote = 'A4';
  let bestDev = Infinity;
  for (const [note, baseFreq] of NOTE_FREQ_MAP) {
    const cents = Math.abs(1200 * Math.log2(freq / baseFreq));
    if (cents < bestDev) {
      bestDev = cents;
      bestNote = note;
    }
  }
  return bestNote;
}

export function clusterDisplayFreq(c: Cluster): number {
  return c.mean_freq + (c.pitch_shift_semitones * c.mean_freq * (Math.pow(2, 1/12) - 1));
}

export function boxHeight(fullYRange: [number, number]): number {
  const spacing = (fullYRange[1] - fullYRange[0]) / 30;
  return spacing * 0.8;
}

// --- Ramp space helpers ---

function getRampSpace(cluster: Cluster, allClusters: Cluster[]): { spaceBefore: number; spaceAfter: number } {
  let spaceBefore = cluster.start_time;
  let spaceAfter = Infinity;
  for (const other of allClusters) {
    if (other === cluster) continue;
    if (other.end_time <= cluster.start_time) {
      const gap = cluster.start_time - other.end_time;
      if (gap < spaceBefore) spaceBefore = gap;
    }
    if (other.start_time >= cluster.end_time) {
      const gap = other.start_time - cluster.end_time;
      if (gap < spaceAfter) spaceAfter = gap;
    }
  }
  return { spaceBefore, spaceAfter };
}

function getIntrusionOutForCluster(clusterA: Cluster | null, clusterB: Cluster | null): number {
  if (!clusterA || !clusterB) return 0;
  const gap = clusterB.start_time - clusterA.end_time;
  if (gap <= 0) return 0;
  const rampOutA = (clusterA.ramp_out_ms || 50) / 1000.0;
  const rampInB = (clusterB.ramp_in_ms || 50) / 1000.0;
  const desired = rampOutA + rampInB;
  if (gap >= desired) return 0;
  const shortfall = desired - gap;
  const halfA = (clusterA.end_time - clusterA.start_time) / 2;
  return Math.min(shortfall / 2, halfA);
}

function getIntrusionInForCluster(clusterA: Cluster | null, clusterB: Cluster | null): number {
  if (!clusterA || !clusterB) return 0;
  const gap = clusterB.start_time - clusterA.end_time;
  if (gap <= 0) return 0;
  const rampOutA = (clusterA.ramp_out_ms || 50) / 1000.0;
  const rampInB = (clusterB.ramp_in_ms || 50) / 1000.0;
  const desired = rampOutA + rampInB;
  if (gap >= desired) return 0;
  const shortfall = desired - gap;
  const halfB = (clusterB.end_time - clusterB.start_time) / 2;
  return Math.min(shortfall / 2, halfB);
}

/**
 * Mirror of audio_engine.py::generate_pitch_map.
 * Returns the semitone shift at time t.
 */
export function computeShiftAtTime(t: number, allClusters: Cluster[]): number {
  const corrected = allClusters.filter(c => c.pitch_shift_semitones !== 0 || (c.smoothing_percent || 0) !== 0);
  if (corrected.length === 0) return 0;

  for (let i = 0; i < corrected.length; i++) {
    const c = corrected[i];
    const rampInS = (c.ramp_in_ms || 50) / 1000.0;
    const rampOutS = (c.ramp_out_ms || 50) / 1000.0;

    const prev = i > 0 ? corrected[i - 1] : null;
    const nxt = i < corrected.length - 1 ? corrected[i + 1] : null;

    const { spaceBefore, spaceAfter } = getRampSpace(c, allClusters);
    let effRampInS = Math.min(rampInS, spaceBefore);
    let effRampOutS = Math.min(rampOutS, spaceAfter);

    const gapPrevS = prev ? (c.start_time - prev.end_time) : Infinity;
    const gapNextS = nxt ? (nxt.start_time - c.end_time) : Infinity;
    const clusterDuration = c.end_time - c.start_time;
    const clusterHalfS = clusterDuration / 2;

    let gapOverlapsPrev = false;
    let intrusionInS = 0;
    if (prev !== null) {
      const prevRampOutS = (prev.ramp_out_ms || 50) / 1000.0;
      const desiredTransition = prevRampOutS + rampInS;
      if (gapPrevS <= 0) {
        effRampInS = 0;
        gapOverlapsPrev = true;
      } else if (gapPrevS < desiredTransition) {
        gapOverlapsPrev = true;
        effRampInS = 0;
        const shortfall = desiredTransition - gapPrevS;
        intrusionInS = Math.min(shortfall / 2, clusterHalfS);
      }
    }

    let gapOverlapsNext = false;
    let intrusionOutS = 0;
    if (nxt !== null) {
      const nxtRampInS = (nxt.ramp_in_ms || 50) / 1000.0;
      const desiredTransition = rampOutS + nxtRampInS;
      if (gapNextS <= 0) {
        effRampOutS = 0;
        gapOverlapsNext = true;
      } else if (gapNextS < desiredTransition) {
        gapOverlapsNext = true;
        effRampOutS = 0;
        const shortfall = desiredTransition - gapNextS;
        intrusionOutS = Math.min(shortfall / 2, clusterHalfS);
      }
    }

    const adjustedStart = c.start_time + intrusionInS;
    const adjustedEnd = c.end_time - intrusionOutS;

    const rampInStart = gapOverlapsPrev
      ? (prev ? prev.end_time - getIntrusionOutForCluster(prev, c) : c.start_time)
      : c.start_time - effRampInS;
    const rampOutEnd = gapOverlapsNext
      ? (nxt ? nxt.start_time + getIntrusionInForCluster(c, nxt) : c.end_time)
      : c.end_time + effRampOutS;

    if (t < rampInStart || t > rampOutEnd) continue;

    if (t >= adjustedStart && t <= adjustedEnd) {
      return c.pitch_shift_semitones;
    }

    if (gapOverlapsPrev && intrusionInS > 0 && t >= c.start_time && t < adjustedStart) {
      const fromShift = prev ? prev.pitch_shift_semitones : 0;
      const totalTransition = gapPrevS + intrusionInS + getIntrusionOutForCluster(prev, c);
      const transitionStart = prev ? prev.end_time - getIntrusionOutForCluster(prev, c) : c.start_time;
      const progress = (t - transitionStart) / totalTransition;
      return fromShift + (c.pitch_shift_semitones - fromShift) * Math.max(0, Math.min(1, progress));
    }

    if (gapOverlapsNext && intrusionOutS > 0 && t > adjustedEnd && t <= c.end_time) {
      const toShift = nxt ? nxt.pitch_shift_semitones : 0;
      const totalTransition = intrusionOutS + gapNextS + getIntrusionInForCluster(c, nxt);
      const progress = (t - adjustedEnd) / totalTransition;
      return c.pitch_shift_semitones + (toShift - c.pitch_shift_semitones) * Math.max(0, Math.min(1, progress));
    }

    if (t >= rampInStart && t < c.start_time) {
      const fromShift = (prev && gapOverlapsPrev) ? prev.pitch_shift_semitones : 0;
      const totalRamp = gapOverlapsPrev
        ? gapPrevS + intrusionInS + getIntrusionOutForCluster(prev, c)
        : effRampInS;
      if (totalRamp <= 0) return c.pitch_shift_semitones;
      const transitionStart = gapOverlapsPrev && prev
        ? prev.end_time - getIntrusionOutForCluster(prev, c)
        : rampInStart;
      const progress = (t - transitionStart) / totalRamp;
      return fromShift + (c.pitch_shift_semitones - fromShift) * Math.max(0, Math.min(1, progress));
    }

    if (t > c.end_time && t <= rampOutEnd) {
      const toShift = (nxt && gapOverlapsNext) ? nxt.pitch_shift_semitones : 0;
      const totalRamp = gapOverlapsNext
        ? intrusionOutS + gapNextS + getIntrusionInForCluster(c, nxt)
        : effRampOutS;
      if (totalRamp <= 0) return c.pitch_shift_semitones;
      const progress = (t - adjustedEnd) / totalRamp;
      return c.pitch_shift_semitones + (toShift - c.pitch_shift_semitones) * Math.max(0, Math.min(1, progress));
    }
  }

  return 0;
}

/**
 * Generate correction curve data for the Plotly overlay.
 * Returns { times, cents } arrays.
 */
export function generateCorrectionCurve(allClusters: Cluster[]): { times: (number | null)[]; cents: (number | null)[] } {
  const corrected = allClusters.filter(c =>
    c.pitch_shift_semitones !== 0 || (c.smoothing_percent || 0) !== 0
  );

  if (corrected.length === 0) return { times: [], cents: [] };

  const outTimes: (number | null)[] = [];
  const outCents: (number | null)[] = [];

  for (let i = 0; i < corrected.length; i++) {
    const c = corrected[i];
    const corrCents = c.pitch_shift_semitones * 100;
    const rampInS = (c.ramp_in_ms || 50) / 1000.0;
    const rampOutS = (c.ramp_out_ms || 50) / 1000.0;

    const prev = i > 0 ? corrected[i - 1] : null;
    const nxt = i < corrected.length - 1 ? corrected[i + 1] : null;

    const { spaceBefore, spaceAfter } = getRampSpace(c, allClusters);
    const clampedRampInS = Math.min(rampInS, spaceBefore);
    const clampedRampOutS = Math.min(rampOutS, spaceAfter);

    const gapPrevS = prev ? (c.start_time - prev.end_time) : Infinity;
    const gapNextS = nxt ? (nxt.start_time - c.end_time) : Infinity;
    const clusterHalfS = (c.end_time - c.start_time) / 2;

    let gapOverlapsPrev = false;
    let intrusionInS = 0;
    if (prev !== null) {
      const prevRampOutS = (prev.ramp_out_ms || 50) / 1000.0;
      const desiredTransition = prevRampOutS + rampInS;
      if (gapPrevS <= 0) {
        gapOverlapsPrev = true;
      } else if (gapPrevS < desiredTransition) {
        gapOverlapsPrev = true;
        const shortfall = desiredTransition - gapPrevS;
        intrusionInS = Math.min(shortfall / 2, clusterHalfS);
      }
    }

    let gapOverlapsNext = false;
    let intrusionOutS = 0;
    if (nxt !== null) {
      const nxtRampInS = (nxt.ramp_in_ms || 50) / 1000.0;
      const desiredTransition = rampOutS + nxtRampInS;
      if (gapNextS <= 0) {
        gapOverlapsNext = true;
      } else if (gapNextS < desiredTransition) {
        gapOverlapsNext = true;
        const shortfall = desiredTransition - gapNextS;
        intrusionOutS = Math.min(shortfall / 2, clusterHalfS);
      }
    }

    const adjustedStart = c.start_time + intrusionInS;
    const adjustedEnd = c.end_time - intrusionOutS;

    // Ramp in
    if (!gapOverlapsPrev) {
      const rampInStart = c.start_time - clampedRampInS;
      outTimes.push(rampInStart);
      outCents.push(0);
      outTimes.push(c.start_time);
      outCents.push(corrCents);
    } else {
      outTimes.push(adjustedStart);
      outCents.push(corrCents);
    }

    // Interior
    outTimes.push(adjustedEnd);
    outCents.push(corrCents);

    // Ramp out
    if (!gapOverlapsNext) {
      const rampOutEnd = c.end_time + clampedRampOutS;
      outTimes.push(rampOutEnd);
      outCents.push(0);

      if (nxt) {
        outTimes.push(null);
        outCents.push(null);
      }
    }
  }

  return { times: outTimes, cents: outCents };
}

/**
 * Update pitch curve for a segment or all, applying shift + smoothing.
 */
export function computePitchCurve(
  origTimes: number[],
  origFreqs: (number | null)[],
  allClusters: Cluster[],
  smoothCurve: number,
  segmentStart = -Infinity,
  segmentEnd = Infinity
): { times: number[]; freqs: (number | null)[] } {
  const newTimes: number[] = [];
  const newFreqs: (number | null)[] = [];

  // Precompute max deviation per cluster for power curve smoothing
  const clusterMaxDevCache = new Map<Cluster, number>();
  if (smoothCurve > 1.0) {
    for (const c of allClusters) {
      if (!c.smoothing_percent) continue;
      let maxDev = 0;
      for (let j = 0; j < origTimes.length; j++) {
        const tj = origTimes[j];
        const fj = origFreqs[j];
        if (tj >= c.start_time && tj <= c.end_time && fj && !isNaN(fj)) {
          const dev = Math.abs(12 * Math.log2(fj / c.mean_freq));
          if (dev > maxDev) maxDev = dev;
        }
      }
      clusterMaxDevCache.set(c, maxDev || 1);
    }
  }

  // Build sorted cluster lookup for binary search
  const sortedClusters = [...allClusters].sort((a, b) => a.start_time - b.start_time);

  for (let i = 0; i < origTimes.length; i++) {
    const t = origTimes[i];
    const origF = origFreqs[i];

    if (t < segmentStart || t > segmentEnd) continue;

    newTimes.push(t);

    if (origF === null || isNaN(origF)) {
      newFreqs.push(null);
      continue;
    }

    const shiftedF = origF * Math.pow(2, computeShiftAtTime(t, allClusters) / 12);

    // Binary search for owning cluster
    let owningCluster: Cluster | null = null;
    let lo = 0, hi = sortedClusters.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const sc = sortedClusters[mid];
      if (t < sc.start_time) { hi = mid - 1; }
      else if (t > sc.end_time) { lo = mid + 1; }
      else { owningCluster = sc; break; }
    }

    if (owningCluster && owningCluster.smoothing_percent > 0) {
      const smoothing = owningCluster.smoothing_percent / 100;
      const deviationSemitones = 12 * Math.log2(origF / owningCluster.mean_freq);
      const correctionShift = owningCluster.pitch_shift_semitones;

      let smoothedDeviation: number;
      if (smoothCurve <= 1.0) {
        smoothedDeviation = deviationSemitones * (1 - smoothing);
      } else {
        const maxDev = clusterMaxDevCache.get(owningCluster) || 1;
        const absDev = Math.abs(deviationSemitones);
        const norm = absDev / maxDev;
        const curvedNorm = Math.pow(norm, 1.0 / smoothCurve);
        smoothedDeviation = Math.sign(deviationSemitones) * curvedNorm * maxDev * (1 - smoothing);
      }

      newFreqs.push(owningCluster.mean_freq * Math.pow(2, (smoothedDeviation + correctionShift) / 12));
    } else {
      newFreqs.push(shiftedF);
    }
  }

  return { times: newTimes, freqs: newFreqs };
}
