/**
 * A readable pace profile for foot activities, computed from the GPS track.
 *
 * The raw pace stream is the speed between two consecutive GPS points, one per second, so it swings
 * between 0 and 20 min/km, and the chart plotted it on an axis that was spread evenly over the
 * samples rather than over distance. This profile instead:
 *
 * 1. measures real distance along the track and puts it on the x-axis,
 * 2. averages pace per distance bin (total time over total distance in the bin, not a mean of
 *    instantaneous paces),
 * 3. leaves stops out (known long stops, and bins far slower than the rest) so they show as a gap,
 * 4. returns the height per bin for a grey profile behind the line.
 *
 * Everything here is in SI units (seconds, metres, seconds per metre); the caller converts to the
 * user's units. The thresholds are tuned on synthetic tracks and one real hike, not on a range of
 * activities, so they are exported and easy to change.
 */

/** A GPS fix, seconds since the first fix. */
export interface TimedPoint {
  t: number
  lat: number
  lon: number
}

/** A sampled value (height), seconds since the first GPS fix. */
export interface TimedValue {
  t: number
  value: number
}

/** A long stop, in seconds since the first GPS fix (as the Google Health importer stores them). */
export interface StopWindow {
  startS: number
  durationS: number
}

/** A gap in the GPS stream longer than this is not walked time (seconds). */
export const GPS_GAP_S = 30
/** A bin slower than this many times the median bin pace is treated as a stop. */
export const SLOW_BIN_FACTOR = 3
/** A bin needs at least this share of its length covered by usable samples. */
export const MIN_BIN_COVERAGE = 0.5
/** About this many bins over the whole activity; the bin size is rounded up to a round number. */
export const TARGET_BIN_COUNT = 120
/** Bin sizes to choose from, metres. */
export const BIN_SIZES_M: readonly number[] = [25, 50, 100, 200, 500, 1000]
/**
 * The GPS path outside stops is scaled to the activity's distance only when the two agree within
 * these bounds; a larger difference means one of them is wrong and scaling would hide it.
 */
export const DISTANCE_SCALE_BOUNDS: readonly [number, number] = [0.9, 1.15]

const METRES_PER_DEGREE = 111_320

/** Why a bin has no pace: inside a known stop, far slower than the rest, or too little data. */
export type GapReason = 'stop' | 'slow' | 'sparse'

/** One distance bin of the profile. */
export interface PaceBin {
  startM: number
  endM: number
  /** Seconds per metre, or `null` where the bin is a gap. */
  paceSPerM: number | null
  /** Why `paceSPerM` is `null`. */
  gap: GapReason | null
  /** Average height in the bin, metres; `null` when the activity has no height samples. */
  elevationM: number | null
}

/** The binned profile of an activity. */
export interface PaceProfile {
  binSizeM: number
  /** Length of the profile: distance along the track outside stops, after scaling. */
  totalM: number
  /** The factor applied to the GPS path to match the activity's distance (1 = none). */
  scale: number
  bins: PaceBin[]
}

/** Options for {@link buildPaceProfile}. */
export interface PaceProfileOptions {
  /** Long stops to leave out. Their time and the GPS jitter inside them are ignored. */
  stops?: readonly StopWindow[]
  /** The activity's distance, metres, used to scale the GPS path. */
  activityDistanceM?: number | null
}

/** Distance in metres between two fixes (equirectangular; the same approximation the backend uses). */
function distanceM(a: TimedPoint, b: TimedPoint): number {
  const dy = (b.lat - a.lat) * METRES_PER_DEGREE
  const dx = (b.lon - a.lon) * METRES_PER_DEGREE * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180)
  return Math.hypot(dx, dy)
}

/**
 * @param totalM - Length of the profile in metres.
 * @returns The smallest listed bin size that gives at most about {@link TARGET_BIN_COUNT} bins.
 */
export function chooseBinSize(totalM: number): number {
  const wanted = totalM / TARGET_BIN_COUNT
  // The tolerance keeps 3000.0000001 m (floating-point noise) from tipping into the next size.
  return (
    BIN_SIZES_M.find((size) => size * (1 + 1e-9) >= wanted) ?? BIN_SIZES_M[BIN_SIZES_M.length - 1]!
  )
}

/** @returns The median of a non-empty list. */
function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 1 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2
}

/** Whether the instant `t` lies inside one of the stops. */
function insideStop(t: number, stops: readonly StopWindow[]): boolean {
  return stops.some((stop) => t >= stop.startS && t <= stop.startS + stop.durationS)
}

/**
 * Cumulative distance along the track (outside stops) at time `t`, interpolated between fixes.
 *
 * @param times - Fix times, ascending.
 * @param cumulative - Cumulative distance at each fix.
 */
function distanceAt(t: number, times: number[], cumulative: number[]): number {
  if (t <= times[0]!) {
    return cumulative[0]!
  }
  const last = times.length - 1
  if (t >= times[last]!) {
    return cumulative[last]!
  }
  let lo = 0
  let hi = last
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (times[mid]! <= t) {
      lo = mid
    } else {
      hi = mid
    }
  }
  const span = times[hi]! - times[lo]!
  const share = span > 0 ? (t - times[lo]!) / span : 0
  return cumulative[lo]! + share * (cumulative[hi]! - cumulative[lo]!)
}

/** Fills missing heights from the nearest known bins, linearly in between. */
function fillHeights(heights: (number | null)[]): (number | null)[] {
  const known = heights.map((h, i) => (h === null ? -1 : i)).filter((i) => i >= 0)
  if (known.length === 0) {
    return heights
  }
  return heights.map((h, i) => {
    if (h !== null) {
      return h
    }
    const before = [...known].reverse().find((k) => k < i)
    const after = known.find((k) => k > i)
    if (before === undefined) {
      return heights[after!]!
    }
    if (after === undefined) {
      return heights[before]!
    }
    const share = (i - before) / (after - before)
    return heights[before]! + share * (heights[after]! - heights[before]!)
  })
}

/** One step between two GPS fixes. */
interface Step {
  from: number
  to: number
  dt: number
  length: number
  kind: 'moving' | 'gap' | 'stop'
}

/** The track as a distance axis: shared by the pace profile and the per-distance value profiles. */
interface Track {
  times: number[]
  cumulative: number[]
  steps: Step[]
  /** Factor applied to the GPS path to match the activity's distance (1 = none). */
  scale: number
  totalM: number
  binSizeM: number
  binCount: number
  /** The bin a distance in metres (after scaling) falls in. */
  binOf: (metres: number) => number
}

/**
 * Walks the GPS track and classifies each step (moving, gap, inside a known stop), scales the path
 * to the activity's distance when the two agree, and chooses the bins.
 *
 * @returns The track, or `null` when it has fewer than two fixes or no length.
 */
function buildTrack(points: readonly TimedPoint[], options: PaceProfileOptions): Track | null {
  const stops = options.stops ?? []
  const fixes = points.filter((p, i) => i === 0 || p.t > points[i - 1]!.t)
  if (fixes.length < 2) {
    return null
  }
  const times: number[] = [fixes[0]!.t]
  const cumulative: number[] = [0]
  const steps: Step[] = []
  let along = 0
  for (let i = 1; i < fixes.length; i += 1) {
    const prev = fixes[i - 1]!
    const cur = fixes[i]!
    const dt = cur.t - prev.t
    const length = distanceM(prev, cur)
    const kind = insideStop((prev.t + cur.t) / 2, stops)
      ? 'stop'
      : dt > GPS_GAP_S
        ? 'gap'
        : 'moving'
    const from = along
    if (kind !== 'stop') {
      along += length
    }
    steps.push({ from, to: along, dt, length, kind })
    times.push(cur.t)
    cumulative.push(along)
  }
  if (along <= 0) {
    return null
  }

  // The GPS path is a little longer or shorter than the distance the activity reports. Scale it so the
  // profile ends where the headline distance does, and so its average pace matches the headline pace.
  const reported = options.activityDistanceM
  const ratio = reported && reported > 0 ? reported / along : 1
  const scale = ratio >= DISTANCE_SCALE_BOUNDS[0] && ratio <= DISTANCE_SCALE_BOUNDS[1] ? ratio : 1
  const totalM = along * scale
  const binSizeM = chooseBinSize(totalM)
  // A length that is a whole number of bins plus floating-point noise must not get a bin of its own.
  const binCount = Math.max(1, Math.ceil(totalM / binSizeM - 1e-9))
  const binOf = (metres: number): number =>
    Math.min(Math.max(Math.floor(metres / binSizeM), 0), binCount - 1)
  return { times, cumulative, steps, scale, totalM, binSizeM, binCount, binOf }
}

/** One distance bin of a value profile (heart rate, height). */
export interface ValueBin {
  startM: number
  endM: number
  /** Mean of the samples in the bin, or `null` where there is none (or the bin holds a known stop). */
  value: number | null
  /** The bin where a known stop happened: left empty so the chart breaks there. */
  stop: boolean
}

/** A sampled value averaged per distance bin, on the same axis as {@link buildPaceProfile}. */
export interface ValueProfile {
  binSizeM: number
  totalM: number
  bins: ValueBin[]
}

/**
 * Averages a sampled value (heart rate, height) per distance bin on the track's own distance axis,
 * so it lines up with the pace profile above it. A sample is placed by the distance at its time,
 * interpolated between GPS fixes, so a stretch where the GPS dropped out is still placed (on the
 * straight line across it). Samples before the first or after the last fix are dropped. The bin where a
 * known stop happened is left empty, with the samples taken during the stop, so the line breaks there.
 *
 * @param points - GPS fixes in time order.
 * @param samples - The values and their times, seconds since the first fix.
 * @param options - Known stops and the activity's distance (as for the pace profile).
 * @param fill - Interpolate bins without samples from their neighbours (height), instead of leaving
 *   them empty (heart rate: no samples means no measurement).
 * @returns The profile, or `null` when the track is too short to bin.
 */
export function buildValueProfile(
  points: readonly TimedPoint[],
  samples: readonly TimedValue[],
  options: PaceProfileOptions = {},
  fill = false,
): ValueProfile | null {
  const track = buildTrack(points, options)
  if (!track) {
    return null
  }
  const { times, cumulative, steps, scale, totalM, binSizeM, binCount, binOf } = track
  const sums = Array.from({ length: binCount }, () => 0)
  const counts = Array.from({ length: binCount }, () => 0)
  const first = times[0]!
  const last = times[times.length - 1]!
  for (const sample of samples) {
    if (!Number.isFinite(sample.value) || sample.t < first || sample.t > last) {
      continue
    }
    const bin = binOf(distanceAt(sample.t, times, cumulative) * scale)
    sums[bin]! += sample.value
    counts[bin]! += 1
  }
  const stopBins = new Set<number>()
  for (const step of steps) {
    if (step.kind === 'stop') {
      stopBins.add(binOf(step.from * scale))
    }
  }
  const means = sums.map((sum, i) => (counts[i]! > 0 ? sum / counts[i]! : null))
  const values = fill ? fillHeights(means) : means
  const bins: ValueBin[] = values.map((value, i) => ({
    startM: i * binSizeM,
    endM: Math.min((i + 1) * binSizeM, totalM),
    value: stopBins.has(i) ? null : value,
    stop: stopBins.has(i),
  }))
  return { binSizeM, totalM, bins }
}

/**
 * Builds the binned pace profile.
 *
 * A stretch of track is `moving` (counts towards pace and distance), `gap` (the device stopped
 * recording for more than {@link GPS_GAP_S}: the distance still counts, there is no pace) or inside
 * a known `stop` (neither the time nor the jitter counts, and the bin where the stop happened is
 * left empty so the chart shows a break there).
 *
 * @param points - GPS fixes in time order.
 * @param elevation - Height samples, optional.
 * @param options - Known stops and the activity's distance.
 * @returns The profile, or `null` when the track is too short to bin.
 */
export function buildPaceProfile(
  points: readonly TimedPoint[],
  elevation: readonly TimedValue[] = [],
  options: PaceProfileOptions = {},
): PaceProfile | null {
  const track = buildTrack(points, options)
  if (!track) {
    return null
  }
  const { times, cumulative, steps, scale, totalM, binSizeM, binCount, binOf } = track

  // Pass 2: time and distance per bin, and where the known stops happened.
  const seconds = Array.from({ length: binCount }, () => 0)
  const metres = Array.from({ length: binCount }, () => 0)
  const stopBins = new Set<number>()
  for (const step of steps) {
    if (step.kind === 'stop') {
      stopBins.add(binOf(step.from * scale))
    } else if (step.kind === 'moving') {
      const bin = binOf(((step.from + step.to) / 2) * scale)
      seconds[bin]! += step.dt
      metres[bin]! += step.length * scale
    }
  }

  // Pace per bin, then the gaps.
  const paces = seconds.map((s, i) => {
    const length = Math.min(binSizeM, totalM - i * binSizeM)
    return metres[i]! >= MIN_BIN_COVERAGE * length && s > 0 ? s / metres[i]! : null
  })
  const valid = paces.filter((p): p is number => p !== null)
  const slowLimit = valid.length > 0 ? SLOW_BIN_FACTOR * median(valid) : Number.POSITIVE_INFINITY

  // Heights per bin.
  const heightSums = Array.from({ length: binCount }, () => 0)
  const heightCounts = Array.from({ length: binCount }, () => 0)
  for (const sample of elevation) {
    if (!Number.isFinite(sample.value)) {
      continue
    }
    const bin = binOf(distanceAt(sample.t, times, cumulative) * scale)
    heightSums[bin]! += sample.value
    heightCounts[bin]! += 1
  }
  const heights = fillHeights(
    heightSums.map((sum, i) => (heightCounts[i]! > 0 ? sum / heightCounts[i]! : null)),
  )

  const bins: PaceBin[] = paces.map((pace, i) => {
    let gap: GapReason | null = null
    if (stopBins.has(i)) {
      gap = 'stop'
    } else if (pace === null) {
      gap = 'sparse'
    } else if (pace > slowLimit) {
      gap = 'slow'
    }
    return {
      startM: i * binSizeM,
      endM: Math.min((i + 1) * binSizeM, totalM),
      paceSPerM: gap === null ? pace : null,
      gap,
      elevationM: heights[i] ?? null,
    }
  })
  return { binSizeM, totalM, scale, bins }
}

/** A value at a fraction of a sorted list (linear between neighbours). */
function quantile(sorted: number[], fraction: number): number {
  const position = (sorted.length - 1) * fraction
  const lo = Math.floor(position)
  const hi = Math.ceil(position)
  return sorted[lo]! + (sorted[hi]! - sorted[lo]!) * (position - lo)
}

/**
 * A y-axis range for pace that shows the typical spread rather than the extremes: from the 2nd to the
 * 98th percentile, padded, and rounded out to whole 15 s. Values outside are drawn clipped at the edge.
 *
 * @param values - Pace per bin in the display unit; non-finite values are ignored.
 * @returns The range, or `null` when there are no values.
 */
export function paceAxisRange(values: readonly number[]): { min: number; max: number } | null {
  const finite = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (finite.length === 0) {
    return null
  }
  const lo = quantile(finite, 0.02)
  const hi = quantile(finite, 0.98)
  const pad = Math.max((hi - lo) * 0.08, 15)
  return {
    min: Math.max(0, Math.floor((lo - pad) / 15) * 15),
    max: Math.ceil((hi + pad) / 15) * 15,
  }
}

/**
 * Whether the importer looked for long stops at all (the list can then still be empty). Activities
 * from other sources carry no such record, so for them "no stops" means "not known".
 *
 * @param importInfo - The activity's `import_info`.
 */
export function hasLongStopInfo(importInfo: Record<string, unknown> | null): boolean {
  const longStops = importInfo?.long_stops
  return Array.isArray((longStops as { stops?: unknown } | null | undefined)?.stops)
}

/**
 * Reads the long stops the Google Health importer stores in `import_info.long_stops.stops`.
 *
 * @param importInfo - The activity's `import_info`.
 * @returns The stops; empty for other sources or when the shape is not what the importer writes.
 */
export function longStopsOf(importInfo: Record<string, unknown> | null): StopWindow[] {
  const longStops = importInfo?.long_stops
  const list = (longStops as { stops?: unknown } | null | undefined)?.stops
  if (!Array.isArray(list)) {
    return []
  }
  return list.flatMap((entry: unknown) => {
    const start = (entry as { start_s?: unknown } | null)?.start_s
    const duration = (entry as { duration_s?: unknown } | null)?.duration_s
    return typeof start === 'number' &&
      typeof duration === 'number' &&
      Number.isFinite(start) &&
      Number.isFinite(duration) &&
      duration > 0
      ? [{ startS: start, durationS: duration }]
      : []
  })
}
