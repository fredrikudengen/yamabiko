/**
 * The segments a tour passed, cut out of its own GPS track so they can be drawn
 * on its map, each with its standing at the end.
 */

import type { ActivityStream } from '@/features/activities/types'
import type { GeoPoint, MapHighlight } from '@/composables/useMapProvider'
import type { SegmentEffort } from '@/features/segments/types'

/** A track point with its time, milliseconds since the epoch. */
export interface TimedPoint extends GeoPoint {
  t: number
}

/** Marker colours for the first three places; the rest use the line's own colour. */
const PODIUM_COLORS: Record<number, string> = { 1: '#eab308', 2: '#94a3b8', 3: '#b45309' }

/**
 * Milliseconds since the epoch for a stored time. Stream times are UTC written
 * without an offset; read as they are, a browser would take them as local time.
 *
 * @param iso - An ISO time, with or without an offset.
 * @returns The time, or `NaN` when it cannot be read.
 */
export function utcMillis(iso: string): number {
  const hasOffset = /(Z|[+-]\d{2}:?\d{2})$/i.test(iso)
  return Date.parse(hasOffset ? iso : `${iso}Z`)
}

/**
 * @param streams - The tour's streams.
 * @returns The GPS points that carry a time, in time order.
 */
export function timedTrackPoints(streams: readonly ActivityStream[]): TimedPoint[] {
  for (const stream of streams) {
    const points: TimedPoint[] = []
    for (const waypoint of stream.waypoints) {
      const lat = Number(waypoint.lat)
      const lng = Number(waypoint.lon)
      const t = typeof waypoint.time === 'string' ? utcMillis(waypoint.time) : Number.NaN
      if (Number.isFinite(lat) && Number.isFinite(lng) && Number.isFinite(t)) {
        points.push({ lat, lng, t })
      }
    }
    if (points.length > 0) {
      return points.sort((a, b) => a.t - b.t)
    }
  }
  return []
}

/**
 * The part of the track between two moments, both ends included.
 *
 * @param points - The track, in time order.
 * @param startIso - When the stretch begins.
 * @param endIso - When it ends.
 * @returns The points of the stretch.
 */
export function stretchOf(
  points: readonly TimedPoint[],
  startIso: string,
  endIso: string,
): GeoPoint[] {
  const start = utcMillis(startIso)
  const end = utcMillis(endIso)
  return points
    .filter((point) => point.t >= start && point.t <= end)
    .map((point) => ({ lat: point.lat, lng: point.lng }))
}

/**
 * The tour's segments as highlights on its map.
 *
 * @param points - The tour's timed track.
 * @param efforts - Its passes of segments.
 * @param labelOf - The text for a pass, e.g. "Løvstakken · PR, of 8 · 34:06".
 * @returns One highlight per pass with at least two points on the track.
 */
export function segmentHighlights(
  points: readonly TimedPoint[],
  efforts: readonly SegmentEffort[],
  labelOf: (effort: SegmentEffort) => string,
): MapHighlight[] {
  return efforts
    .map((effort) => ({
      points: stretchOf(points, effort.startTime, effort.endTime),
      label: labelOf(effort),
      markerColor: effort.segmentEffortCount > 1 ? PODIUM_COLORS[effort.rankMoving] : undefined,
    }))
    .filter((highlight) => highlight.points.length >= 2)
}
