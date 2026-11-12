import { onBeforeUnmount, ref, toValue, type MaybeRefOrGetter } from 'vue'

import type { GeoPoint } from '@/composables/useMapProvider'

/** How long a playback of the whole route takes, whatever its length. */
export const PLAYBACK_DURATION_MS = 20_000

/** Metres between two points; an equirectangular estimate, plenty over a few hundred metres. */
function metresBetween(a: GeoPoint, b: GeoPoint): number {
  const toRad = Math.PI / 180
  const x = (b.lng - a.lng) * toRad * Math.cos(((a.lat + b.lat) / 2) * toRad)
  const y = (b.lat - a.lat) * toRad
  return Math.hypot(x, y) * 6_371_000
}

/**
 * The point a share of the way along a route, measured by distance so the marker moves at an even
 * pace over the map whatever the GPS sampling.
 *
 * @param points - The route.
 * @param share - 0 at the start, 1 at the end.
 * @returns The point, interpolated between the two nearest, or `null` for an empty route.
 */
export function pointAlong(points: readonly GeoPoint[], share: number): GeoPoint | null {
  if (points.length === 0) {
    return null
  }
  const cumulative = [0]
  for (let i = 1; i < points.length; i += 1) {
    cumulative.push(cumulative[i - 1]! + metresBetween(points[i - 1]!, points[i]!))
  }
  const total = cumulative[cumulative.length - 1]!
  if (total <= 0) {
    return points[0]!
  }
  const target = Math.min(Math.max(share, 0), 1) * total
  let i = 1
  while (i < cumulative.length - 1 && cumulative[i]! < target) {
    i += 1
  }
  const before = cumulative[i - 1]!
  const after = cumulative[i]!
  const t = after > before ? (target - before) / (after - before) : 0
  const a = points[i - 1]!
  const b = points[i]!
  return { lat: a.lat + t * (b.lat - a.lat), lng: a.lng + t * (b.lng - a.lng) }
}

/**
 * Walks a marker along the route from start to finish, so the charts follow it as if hovered.
 *
 * @param points - The route to play.
 * @param onPoint - Called with each position along the way, and with `null` when playback ends.
 * @returns Whether it is playing, and the controls.
 */
export function useRoutePlayback(
  points: MaybeRefOrGetter<readonly GeoPoint[]>,
  onPoint: (point: GeoPoint | null) => void,
) {
  const playing = ref(false)
  let frame: number | null = null
  let startedAt = 0

  function step(now: number): void {
    const share = (now - startedAt) / PLAYBACK_DURATION_MS
    onPoint(pointAlong(toValue(points), share))
    if (share >= 1) {
      stop()
      return
    }
    frame = requestAnimationFrame(step)
  }

  /** Starts from the beginning of the route. */
  function play(): void {
    stop()
    if (toValue(points).length < 2) {
      return
    }
    playing.value = true
    startedAt = performance.now()
    frame = requestAnimationFrame(step)
  }

  /** Stops where it is; the marker goes away. */
  function stop(): void {
    if (frame !== null) {
      cancelAnimationFrame(frame)
      frame = null
    }
    if (playing.value) {
      playing.value = false
      onPoint(null)
    }
  }

  function toggle(): void {
    if (playing.value) {
      stop()
    } else {
      play()
    }
  }

  onBeforeUnmount(stop)
  return { playing, play, stop, toggle }
}
