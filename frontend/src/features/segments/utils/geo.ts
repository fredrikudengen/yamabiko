import { MIN_NODE_RADIUS_M, type SegmentNode } from '@/features/segments/types'

const EARTH_RADIUS_M = 6_371_000

/**
 * Great-circle distance between two positions (haversine).
 *
 * @param a - First position as `[lat, lon]`.
 * @param b - Second position as `[lat, lon]`.
 * @returns Distance in metres.
 */
export function distanceM(a: [number, number], b: [number, number]): number {
  const toRad = Math.PI / 180
  const dLat = (b[0] - a[0]) * toRad
  const dLon = (b[1] - a[1]) * toRad
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[0] * toRad) * Math.cos(b[0] * toRad) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))
}

/**
 * The point `distance` metres east of `origin` (good for the small distances of a node radius).
 *
 * @param origin - Position as `[lat, lon]`.
 * @param distance - Metres towards east.
 * @returns The new position.
 */
export function offsetEast(origin: [number, number], distance: number): [number, number] {
  const dLon = distance / (EARTH_RADIUS_M * Math.cos((origin[0] * Math.PI) / 180))
  return [origin[0], origin[1] + (dLon * 180) / Math.PI]
}

/**
 * Whether two circles overlap, which the server rejects.
 *
 * @param start - Start node.
 * @param end - End node.
 * @returns True when the distance between centres is less than the radii added.
 */
export function nodesOverlap(start: SegmentNode, end: SegmentNode): boolean {
  return distanceM([start.lat, start.lon], [end.lat, end.lon]) < start.radiusM + end.radiusM
}

/** Why a pair of nodes cannot be previewed or saved, or `null` when it can. */
export type NodeProblem = 'radius_too_small' | 'overlap' | null

/**
 * Mirrors the server's checks so the editor can say what is wrong before asking.
 *
 * @param start - Start node.
 * @param end - End node.
 * @returns The first problem found.
 */
export function nodeProblem(start: SegmentNode, end: SegmentNode): NodeProblem {
  if (!(start.radiusM > MIN_NODE_RADIUS_M) || !(end.radiusM > MIN_NODE_RADIUS_M)) {
    return 'radius_too_small'
  }
  return nodesOverlap(start, end) ? 'overlap' : null
}

/**
 * Rounds a radius to a whole metre inside the allowed range.
 *
 * @param value - Raw radius in metres.
 * @param max - Upper limit, so a stray drag cannot make a continent-sized circle.
 * @returns A radius that passes the server check.
 */
export function clampRadius(value: number, max = 2000): number {
  if (!Number.isFinite(value)) {
    return MIN_NODE_RADIUS_M + 1
  }
  return Math.min(max, Math.max(MIN_NODE_RADIUS_M + 1, Math.round(value)))
}

/**
 * Formats a position for the coordinate field, latitude first.
 *
 * @param node - A node.
 * @returns Text such as `60.39000, 5.32000`.
 */
export function formatCoordinates(node: Pick<SegmentNode, 'lat' | 'lon'>): string {
  return `${node.lat.toFixed(5)}, ${node.lon.toFixed(5)}`
}

/**
 * A node from the address, as a suggested segment passes it: `?start=60.39, 5.32`. Plain decimal
 * degrees only; anything else gives `null`, and the node is placed by hand as usual.
 *
 * @param value - The query value.
 * @param radiusM - The radius to give the node.
 * @returns The node, or `null`.
 */
export function nodeFromQuery(value: unknown, radiusM: number): SegmentNode | null {
  if (typeof value !== 'string') {
    return null
  }
  const parts = value.split(',').map((part) => part.trim())
  if (parts.length !== 2 || parts.some((part) => part === '')) {
    return null
  }
  const [lat, lon] = parts.map(Number) as [number, number]
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    return null
  }
  return { lat, lon, radiusM }
}

/**
 * Formats seconds as `m:ss` or `h:mm:ss`.
 *
 * @param seconds - Duration in seconds.
 * @returns The formatted duration.
 */
export function formatSeconds(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}
