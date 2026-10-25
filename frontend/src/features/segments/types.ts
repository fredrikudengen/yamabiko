import type { ActivitySource } from '@/features/segments/utils/source'

/** A node as the API returns it: a circle on the map (snake_case wire shape). */
export interface SegmentNodeDto {
  lat: number
  lon: number
  radius_m: number
}

/** Node body sent to the API: either `lat` + `lon`, or one `coordinates` string, plus a radius. */
export interface SegmentNodeInputDto {
  lat?: number
  lon?: number
  coordinates?: string
  radius_m: number
}

export interface SegmentDto {
  id: number
  name: string
  start: SegmentNodeDto
  end: SegmentNodeDto
  effort_count: number
  created_at: string
  updated_at: string
}

export interface SimilarSegmentDto {
  id: number
  name: string
}

export interface SegmentSavedDto extends SegmentDto {
  similar_segments: SimilarSegmentDto[]
}

export interface SegmentEffortDto {
  id: number
  segment_id: number
  segment_name: string
  activity_id: number
  activity_name: string | null
  /** Where the tour was imported from; see `utils/source.ts`. */
  source: string
  start_time: string
  end_time: string
  elapsed_s: number
  moving_s: number
  stopped_s: number
  gap_s: number
  distance_m: number
  elevation_gain_m: number | null
  elevation_loss_m: number | null
  net_elevation_m: number | null
  average_hr: number | null
  max_hr: number | null
  /** Standing among all passes of the segment, whatever their source (1 = fastest). */
  rank_moving: number
  rank_total: number
  segment_effort_count: number
  matcher_version: number
  details: Record<string, unknown> | null
}

export interface PreviewMatchDto {
  activity_id: number
  activity_name: string | null
  /** Where the tour was imported from; see `utils/source.ts`. */
  source: string
  start_time: string
  end_time: string
  elapsed_s: number
  moving_s: number
  stopped_s: number
  gap_s: number
  distance_m: number
  elevation_gain_m: number | null
  elevation_loss_m: number | null
  net_elevation_m: number | null
  average_hr: number | null
  max_hr: number | null
  start_visits: number
  end_visits: number
  closest_start_m: number
  closest_end_m: number
  start_visit_times: string[]
  end_visit_times: string[]
}

export type NearMissReason =
  'start_not_reached' | 'end_not_reached' | 'both_not_reached' | 'wrong_order'

export interface NearMissDto {
  activity_id: number
  activity_name: string | null
  start_time: string
  reason: NearMissReason
  closest_start_m: number
  closest_end_m: number
}

export interface SegmentPreviewDto {
  matches: PreviewMatchDto[]
  near_misses: NearMissDto[]
  similar_segments: SimilarSegmentDto[]
}

/** A circle on the map, in the shape the UI works with. */
export interface SegmentNode {
  lat: number
  lon: number
  /** Radius in metres; the server requires more than {@link MIN_NODE_RADIUS_M}. */
  radiusM: number
}

/** The smallest radius the server accepts is anything above this (metres). */
export const MIN_NODE_RADIUS_M = 25
export const DEFAULT_NODE_RADIUS_M = 50

export interface Segment {
  id: number
  name: string
  start: SegmentNode
  end: SegmentNode
  effortCount: number
  createdAt: string
  updatedAt: string
}

export interface SimilarSegment {
  id: number
  name: string
}

export interface SegmentSaved extends Segment {
  /** Existing segments with nearly the same start and end: a hint, never an error. */
  similarSegments: SimilarSegment[]
}

/** What the editor submits to create or change a segment. */
export interface SegmentInput {
  name: string
  start: SegmentNode
  end: SegmentNode
}

/** One pass of a segment by one activity. Times in seconds, distances in metres. */
export interface SegmentEffort {
  id: number
  segmentId: number
  segmentName: string
  activityId: number
  activityName: string | null
  source: ActivitySource
  startTime: string
  endTime: string
  elapsedS: number
  /** Time without long stops and gaps in the GPS stream: the comparable time. */
  movingS: number
  stoppedS: number
  gapS: number
  distanceM: number
  elevationGainM: number | null
  elevationLossM: number | null
  netElevationM: number | null
  averageHr: number | null
  maxHr: number | null
  /** Standing by moving time among all passes of the segment (1 = fastest); see `utils/milestone.ts`. */
  rankMoving: number
  rankTotal: number
  segmentEffortCount: number
}

export interface PreviewMatch {
  activityId: number
  activityName: string | null
  source: ActivitySource
  startTime: string
  endTime: string
  elapsedS: number
  movingS: number
  stoppedS: number
  gapS: number
  distanceM: number
  elevationGainM: number | null
  netElevationM: number | null
  averageHr: number | null
  maxHr: number | null
  startVisits: number
  endVisits: number
  /** How close the track came to the node centres: the radius that would just catch it. */
  closestStartM: number
  closestEndM: number
  /** When each visit to the end node began (ISO), so a second visit can be told from the arrival. */
  endVisitTimes: string[]
}

export interface NearMiss {
  activityId: number
  activityName: string | null
  startTime: string
  reason: NearMissReason
  closestStartM: number
  closestEndM: number
}

export interface SegmentPreview {
  matches: PreviewMatch[]
  nearMisses: NearMiss[]
  similarSegments: SimilarSegment[]
}

/** A track to draw under the circles, as `[lat, lon]` pairs. */
export interface TrackLine {
  activityId: number
  points: [number, number][]
}
