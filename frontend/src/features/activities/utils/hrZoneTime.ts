import type { ChartBand } from '@/composables/useChartProvider'

import type { HrZoneBucket } from '../types'
import type { StopWindow, TimedValue } from './paceProfile'

import { hrZoneColor } from './hrZones'
import { GPS_GAP_S } from './paceProfile'

/**
 * Time in heart-rate zones, counted in seconds and with the long stops left out.
 *
 * The zone card used to show the server's split, which counts samples (not time) over the whole
 * recording, stop included, and scales the share to the timer time. This module instead lets every
 * sample hold its heart rate until the next one, and drops the time inside known stops, so the sum
 * of the zones is the moving time.
 *
 * Everything is in seconds; times are relative to one origin (the first GPS fix when the activity has
 * one), the same origin the stored long stops use.
 */

/** The four upper bounds that split the heart rate into five zones, bpm, strictly increasing. */
export type HrZoneLimits = readonly [number, number, number, number]

/** Google Health's limits for the user's own zones (the lines in its zone graph). */
export const DEFAULT_HR_ZONE_LIMITS: HrZoneLimits = [103, 113, 126, 154]

/** Heart rates outside this range (bpm) are not accepted as a zone limit. */
export const HR_LIMIT_BOUNDS: { readonly min: number; readonly max: number } = { min: 30, max: 250 }

/** Number of zones. */
export const HR_ZONE_COUNT = 5

/**
 * @param value - Anything, typically parsed from storage.
 * @returns Whether it is four whole numbers within bounds, each larger than the one before.
 */
export function isValidZoneLimits(value: unknown): value is HrZoneLimits {
  if (!Array.isArray(value) || value.length !== HR_ZONE_COUNT - 1) {
    return false
  }
  return value.every(
    (limit, index) =>
      typeof limit === 'number' &&
      Number.isInteger(limit) &&
      limit >= HR_LIMIT_BOUNDS.min &&
      limit <= HR_LIMIT_BOUNDS.max &&
      (index === 0 || limit > (value[index - 1] as number)),
  )
}

/** Why a set of typed limits was rejected. */
export type ZoneLimitsError = 'incomplete' | 'range' | 'order'

/**
 * Reads limits typed into four text fields.
 *
 * @param inputs - The four field values, lowest zone first.
 * @returns The limits, or the reason they cannot be used.
 */
export function parseZoneLimitInputs(
  inputs: readonly string[],
): { limits: HrZoneLimits } | { error: ZoneLimitsError } {
  const numbers = inputs.map((text) => (text.trim() === '' ? Number.NaN : Number(text)))
  if (numbers.length !== HR_ZONE_COUNT - 1 || numbers.some((n) => !Number.isInteger(n))) {
    return { error: 'incomplete' }
  }
  if (numbers.some((n) => n < HR_LIMIT_BOUNDS.min || n > HR_LIMIT_BOUNDS.max)) {
    return { error: 'range' }
  }
  if (!isValidZoneLimits(numbers)) {
    return { error: 'order' }
  }
  return { limits: numbers }
}

/**
 * @param heartRate - Heart rate in bpm.
 * @param limits - The zone limits.
 * @returns The zone, 1–5. A limit belongs to the zone above it (103 is zone 2 when the first limit
 *   is 103), like the ranges `< 103`, `103 - 112`, … shown on the card.
 */
export function zoneOf(heartRate: number, limits: HrZoneLimits): number {
  let zone = 1
  for (const limit of limits) {
    if (heartRate >= limit) {
      zone += 1
    }
  }
  return zone
}

/**
 * @param zone - Zone number, 1–5.
 * @param limits - The zone limits.
 * @returns The bpm range of the zone as text (`< 103`, `103 - 112`, …, `≥ 154`).
 */
export function zoneRangeLabel(zone: number, limits: HrZoneLimits): string {
  const lower = limits[zone - 2]
  const upper = limits[zone - 1]
  if (lower === undefined) {
    return `< ${upper}`
  }
  if (upper === undefined) {
    return `≥ ${lower}`
  }
  return `${lower} - ${upper - 1}`
}

/**
 * The zones as colour bands for a chart, so a heart-rate line changes colour at each limit.
 *
 * @param limits - The zone limits.
 * @returns Five bands, zone 1 from `-Infinity`, each zone starting at its limit.
 */
export function zoneBands(limits: HrZoneLimits): ChartBand[] {
  return Array.from({ length: HR_ZONE_COUNT }, (_, index) => ({
    from: index === 0 ? Number.NEGATIVE_INFINITY : limits[index - 1]!,
    color: hrZoneColor(index + 1),
  }))
}

/** What {@link computeZoneSeconds} found. */
export interface ZoneSeconds {
  /** Seconds in each zone, lowest first. */
  seconds: number[]
  /** Sum of {@link ZoneSeconds.seconds}. */
  countedS: number
  /** Seconds inside known stops that were left out. */
  stoppedS: number
  /**
   * Seconds without heart-rate data that are not inside a known stop: steps between two samples
   * too far apart to say anything about (the sensor dropped out), and, when a recording span is
   * given, the time before the first and after the last sample.
   */
  gapS: number
}

/** The stretch of the recording the heart rate should cover, relative to the samples' origin. */
export interface RecordingSpan {
  startS: number
  endS: number
}

/**
 * A gap shorter than this is not worth showing: the last sample has no successor, so even a
 * complete recording ends about a second short.
 */
export const MIN_SHOWN_GAP_S = 5

/** Sorts stops by start and merges the ones that overlap, so no second is counted twice. */
function mergeStops(stops: readonly StopWindow[]): [number, number][] {
  const sorted = stops
    .filter((s) => Number.isFinite(s.startS) && Number.isFinite(s.durationS) && s.durationS > 0)
    .map((s): [number, number] => [s.startS, s.startS + s.durationS])
    .sort((a, b) => a[0] - b[0])
  const merged: [number, number][] = []
  for (const window of sorted) {
    const last = merged[merged.length - 1]
    if (last && window[0] <= last[1]) {
      last[1] = Math.max(last[1], window[1])
    } else {
      merged.push([window[0], window[1]])
    }
  }
  return merged
}

/** Seconds of `[from, to]` that lie inside the (merged, sorted) stops. */
function overlapWithStops(from: number, to: number, stops: readonly [number, number][]): number {
  let total = 0
  for (const [start, end] of stops) {
    if (start >= to) {
      break
    }
    total += Math.max(0, Math.min(to, end) - Math.max(from, start))
  }
  return total
}

/**
 * Adds up the time spent in each heart-rate zone.
 *
 * Every sample holds its heart rate until the next sample. A step longer than `maxStepS` is not
 * counted (a sensor dropout says nothing about the zone), and time inside a stop is left out.
 *
 * @param samples - Heart rate (bpm) over time, in any order; samples that are not finite are ignored.
 * @param limits - The zone limits.
 * @param stops - Long stops to leave out, relative to the same origin as the samples.
 * @param maxStepS - Longest step between two samples that still counts.
 * @param span - The stretch of the recording the heart rate should cover. When given, the time
 *   before the first sample and after the last one (outside known stops) is reported as a gap too.
 *   Without it only the steps between samples can be found missing.
 * @returns The seconds per zone and how much was left out.
 */
export function computeZoneSeconds(
  samples: readonly TimedValue[],
  limits: HrZoneLimits,
  stops: readonly StopWindow[] = [],
  maxStepS: number = GPS_GAP_S,
  span?: RecordingSpan,
): ZoneSeconds {
  const ordered = samples
    .filter((s) => Number.isFinite(s.t) && Number.isFinite(s.value))
    .sort((a, b) => a.t - b.t)
  const windows = mergeStops(stops)
  const seconds = Array.from({ length: HR_ZONE_COUNT }, () => 0)
  let stoppedS = 0
  let gapS = 0

  for (let i = 0; i + 1 < ordered.length; i += 1) {
    const from = ordered[i]!
    const to = ordered[i + 1]!
    const step = to.t - from.t
    if (step <= 0) {
      continue
    }
    const inStop = overlapWithStops(from.t, to.t, windows)
    stoppedS += inStop
    if (step > maxStepS) {
      gapS += step - inStop
      continue
    }
    seconds[zoneOf(from.value, limits) - 1]! += step - inStop
  }

  const firstSample = ordered[0]
  const lastSample = ordered[ordered.length - 1]
  if (span && firstSample && lastSample) {
    if (firstSample.t > span.startS) {
      gapS += firstSample.t - span.startS - overlapWithStops(span.startS, firstSample.t, windows)
    }
    if (span.endS > lastSample.t) {
      gapS += span.endS - lastSample.t - overlapWithStops(lastSample.t, span.endS, windows)
    }
  }

  const countedS = seconds.reduce((sum, s) => sum + s, 0)
  return { seconds, countedS, stoppedS, gapS }
}

/**
 * Turns zone seconds into the buckets the zone card draws.
 *
 * @param result - Output of {@link computeZoneSeconds}.
 * @param limits - The zone limits, for the bpm ranges.
 * @returns Five buckets; the shares add up to 100 % of the counted time (all 0 when nothing counted).
 */
export function toZoneBuckets(result: ZoneSeconds, limits: HrZoneLimits): HrZoneBucket[] {
  return result.seconds.map((s, index) => ({
    zone: index + 1,
    percent: result.countedS > 0 ? (s / result.countedS) * 100 : 0,
    hrRange: zoneRangeLabel(index + 1, limits),
    timeSeconds: Math.round(s),
  }))
}
