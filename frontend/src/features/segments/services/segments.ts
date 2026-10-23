import type {
  NearMiss,
  NearMissDto,
  PreviewMatch,
  PreviewMatchDto,
  Segment,
  SegmentDto,
  SegmentEffort,
  SegmentEffortDto,
  SegmentInput,
  SegmentNode,
  SegmentNodeDto,
  SegmentNodeInputDto,
  SegmentPreview,
  SegmentPreviewDto,
  SegmentSaved,
  SegmentSavedDto,
  TrackLine,
} from '@/features/segments/types'

import { toActivitySource } from '@/features/segments/utils/source'
import { apiFetch } from '@/services/http'

/**
 * @param dto - A node from the API.
 * @returns The node in UI shape.
 */
export function mapNode(dto: SegmentNodeDto): SegmentNode {
  return { lat: dto.lat, lon: dto.lon, radiusM: dto.radius_m }
}

/**
 * @param node - A node from the editor.
 * @returns The request body for the node.
 */
export function nodeToInput(node: SegmentNode): SegmentNodeInputDto {
  return { lat: node.lat, lon: node.lon, radius_m: node.radiusM }
}

/**
 * @param dto - A segment from the API.
 * @returns The segment in UI shape.
 */
export function mapSegment(dto: SegmentDto): Segment {
  return {
    id: dto.id,
    name: dto.name,
    start: mapNode(dto.start),
    end: mapNode(dto.end),
    effortCount: dto.effort_count,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

/**
 * @param dto - A saved segment from the API.
 * @returns The segment with its similar-segment hint.
 */
export function mapSegmentSaved(dto: SegmentSavedDto): SegmentSaved {
  return { ...mapSegment(dto), similarSegments: dto.similar_segments }
}

/**
 * @param dto - An effort from the API.
 * @returns The effort in UI shape.
 */
export function mapEffort(dto: SegmentEffortDto): SegmentEffort {
  return {
    id: dto.id,
    segmentId: dto.segment_id,
    segmentName: dto.segment_name,
    activityId: dto.activity_id,
    activityName: dto.activity_name,
    source: toActivitySource(dto.source),
    startTime: dto.start_time,
    endTime: dto.end_time,
    elapsedS: dto.elapsed_s,
    movingS: dto.moving_s,
    stoppedS: dto.stopped_s,
    gapS: dto.gap_s,
    distanceM: dto.distance_m,
    elevationGainM: dto.elevation_gain_m,
    elevationLossM: dto.elevation_loss_m,
    netElevationM: dto.net_elevation_m,
    averageHr: dto.average_hr,
    maxHr: dto.max_hr,
  }
}

function mapPreviewMatch(dto: PreviewMatchDto): PreviewMatch {
  return {
    activityId: dto.activity_id,
    activityName: dto.activity_name,
    source: toActivitySource(dto.source),
    startTime: dto.start_time,
    endTime: dto.end_time,
    elapsedS: dto.elapsed_s,
    movingS: dto.moving_s,
    stoppedS: dto.stopped_s,
    gapS: dto.gap_s,
    distanceM: dto.distance_m,
    elevationGainM: dto.elevation_gain_m,
    netElevationM: dto.net_elevation_m,
    averageHr: dto.average_hr,
    maxHr: dto.max_hr,
    startVisits: dto.start_visits,
    endVisits: dto.end_visits,
    closestStartM: dto.closest_start_m,
    closestEndM: dto.closest_end_m,
    endVisitTimes: dto.end_visit_times,
  }
}

function mapNearMiss(dto: NearMissDto): NearMiss {
  return {
    activityId: dto.activity_id,
    activityName: dto.activity_name,
    startTime: dto.start_time,
    reason: dto.reason,
    closestStartM: dto.closest_start_m,
    closestEndM: dto.closest_end_m,
  }
}

/**
 * @param dto - A preview from the API.
 * @returns The preview in UI shape.
 */
export function mapPreview(dto: SegmentPreviewDto): SegmentPreview {
  return {
    matches: dto.matches.map(mapPreviewMatch),
    nearMisses: dto.near_misses.map(mapNearMiss),
    similarSegments: dto.similar_segments,
  }
}

function toBody(input: SegmentInput) {
  return {
    name: input.name,
    start: nodeToInput(input.start),
    end: nodeToInput(input.end),
  }
}

/**
 * @param signal - Optional abort signal from the query.
 * @returns The user's segments, by name.
 * @throws {HttpError} When the request fails.
 */
export async function fetchSegments(signal?: AbortSignal): Promise<Segment[]> {
  const dtos = await apiFetch<SegmentDto[]>('/segments', { signal })
  return dtos.map(mapSegment)
}

/**
 * @param id - Segment identifier.
 * @param signal - Optional abort signal from the query.
 * @returns The segment.
 * @throws {HttpError} When the request fails (404 when it is not the user's).
 */
export async function fetchSegment(id: number, signal?: AbortSignal): Promise<Segment> {
  return mapSegment(await apiFetch<SegmentDto>(`/segments/${id}`, { signal }))
}

/**
 * Creates a segment; the server finds the activities that pass it before answering.
 *
 * @param input - Name and nodes.
 * @returns The new segment and any similar existing ones.
 * @throws {HttpError} 422 when the name or nodes are not acceptable.
 */
export async function createSegment(input: SegmentInput): Promise<SegmentSaved> {
  const dto = await apiFetch<SegmentSavedDto>('/segments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toBody(input)),
  })
  return mapSegmentSaved(dto)
}

/**
 * Changes a segment; its efforts are recomputed from the new nodes.
 *
 * @param id - Segment identifier.
 * @param input - Name and nodes.
 * @returns The changed segment and any similar existing ones.
 * @throws {HttpError} 422 when the name or nodes are not acceptable.
 */
export async function updateSegment(id: number, input: SegmentInput): Promise<SegmentSaved> {
  const dto = await apiFetch<SegmentSavedDto>(`/segments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toBody(input)),
  })
  return mapSegmentSaved(dto)
}

/**
 * @param id - Segment identifier.
 * @throws {HttpError} When the request fails.
 */
export async function deleteSegment(id: number): Promise<void> {
  await apiFetch(`/segments/${id}`, { method: 'DELETE', responseType: 'void' })
}

/**
 * Recomputes a segment's efforts from the user's activities.
 *
 * @param id - Segment identifier.
 * @returns The segment with its new effort count.
 */
export async function refreshSegment(id: number): Promise<Segment> {
  return mapSegment(await apiFetch<SegmentDto>(`/segments/${id}/refresh`, { method: 'POST' }))
}

/**
 * @param id - Segment identifier.
 * @param signal - Optional abort signal from the query.
 * @returns All passes of the segment, oldest first.
 */
export async function fetchSegmentEfforts(
  id: number,
  signal?: AbortSignal,
): Promise<SegmentEffort[]> {
  const dtos = await apiFetch<SegmentEffortDto[]>(`/segments/${id}/efforts`, { signal })
  return dtos.map(mapEffort)
}

/**
 * @param activityId - Activity identifier.
 * @param signal - Optional abort signal from the query.
 * @returns The segments the activity has passed.
 */
export async function fetchActivityEfforts(
  activityId: number,
  signal?: AbortSignal,
): Promise<SegmentEffort[]> {
  const dtos = await apiFetch<SegmentEffortDto[]>(`/segments/activities/${activityId}/efforts`, {
    signal,
  })
  return dtos.map(mapEffort)
}

/**
 * Which of the user's activities would pass two nodes, and which nearly do. Nothing is saved.
 *
 * @param start - The start node.
 * @param end - The end node.
 * @param signal - Optional abort signal.
 * @returns Matches with times, near misses with the radius that would catch them.
 * @throws {HttpError} 422 when the nodes are not acceptable.
 */
export async function previewSegment(
  start: SegmentNode,
  end: SegmentNode,
  signal?: AbortSignal,
): Promise<SegmentPreview> {
  const dto = await apiFetch<SegmentPreviewDto>('/segments/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start: nodeToInput(start), end: nodeToInput(end) }),
    signal,
  })
  return mapPreview(dto)
}

/**
 * Reads a pasted pair such as `60.39, 5.32` (latitude first).
 *
 * @param text - What the user typed or pasted.
 * @returns The position.
 * @throws {HttpError} 422 with a readable `detail` when the text is not a pair of decimal degrees.
 */
export async function parseCoordinates(text: string): Promise<{ lat: number; lon: number }> {
  return apiFetch<{ lat: number; lon: number }>('/segments/parse-coordinates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

/** Most points drawn per track; more only slows the map down. */
const MAX_TRACK_POINTS = 400

/**
 * Picks at most ``maxPoints`` evenly spaced points, always keeping the first and last.
 *
 * @param points - The full track.
 * @param maxPoints - Upper bound on the result length.
 * @returns The thinned track.
 */
export function thinTrack(
  points: [number, number][],
  maxPoints = MAX_TRACK_POINTS,
): [number, number][] {
  if (points.length <= maxPoints || maxPoints < 2) {
    return points
  }
  const step = (points.length - 1) / (maxPoints - 1)
  const thinned: [number, number][] = []
  for (let i = 0; i < maxPoints; i += 1) {
    const point = points[Math.round(i * step)]
    if (point) {
      thinned.push(point)
    }
  }
  return thinned
}

interface MapStreamDto {
  stream_waypoints: { lat?: number | null; lon?: number | null }[] | null
}

/**
 * The GPS track of one of the user's activities, thinned for drawing.
 *
 * @param activityId - Activity identifier.
 * @param signal - Optional abort signal.
 * @returns The track, empty when the activity has no GPS stream.
 */
export async function fetchActivityTrack(
  activityId: number,
  signal?: AbortSignal,
): Promise<TrackLine> {
  const dto = await apiFetch<MapStreamDto | null>(
    `/activities_streams/activity_id/${activityId}/stream_type/7`,
    { signal },
  )
  const points: [number, number][] = []
  for (const waypoint of dto?.stream_waypoints ?? []) {
    if (typeof waypoint.lat === 'number' && typeof waypoint.lon === 'number') {
      points.push([waypoint.lat, waypoint.lon])
    }
  }
  return { activityId, points: thinTrack(points) }
}
