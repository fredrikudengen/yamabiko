import type { SegmentEffort } from '@/features/segments/types'

import { timeOf, type EffortBasis } from '@/features/segments/utils/efforts'

/**
 * A pass must climb at least this far (net, metres) for a climb rate or a heart cost to be shown.
 * The net height is the median height around the end node minus the one around the start node, which
 * is good to a metre or two; on a smaller climb that error is a large share of the number.
 */
export const MIN_NET_CLIMB_M = 20

/** Seconds in an hour: the climb rate is metres per hour. */
const SECONDS_PER_HOUR = 3600

/** The net climb of a pass in metres, or `null` when it is missing or too small to measure with. */
function usableClimbM(effort: SegmentEffort): number | null {
  const net = effort.netElevationM
  return net !== null && Number.isFinite(net) && net >= MIN_NET_CLIMB_M ? net : null
}

/**
 * Climb rate (VAM): metres climbed per hour. Uses the net height difference between the nodes, not
 * the summed ascent, because the summed ascent of a smoothed height track overstates small climbs.
 *
 * @param effort - One pass of a segment.
 * @param basis - Which time to divide by: moving time (long stops and GPS gaps out) or clock time.
 * @returns Metres per hour, or `null` when the pass did not climb enough or has no time.
 */
export function climbRateOf(effort: SegmentEffort, basis: EffortBasis): number | null {
  const climb = usableClimbM(effort)
  const seconds = timeOf(effort, basis)
  return climb !== null && seconds > 0 ? (climb / seconds) * SECONDS_PER_HOUR : null
}

/**
 * Heart beats spent per 100 m climbed: average heart rate times moving time, over the net climb.
 * Lower is better for the same climb. Always moving time, because the average heart rate is taken over
 * the moving part of the pass only.
 *
 * @param effort - One pass of a segment.
 * @returns Beats per 100 m, or `null` without heart rate, time or enough climb.
 */
export function beatsPer100mOf(effort: SegmentEffort): number | null {
  const climb = usableClimbM(effort)
  const hr = effort.averageHr
  if (climb === null || hr === null || !(hr > 0) || !(effort.movingS > 0)) {
    return null
  }
  return ((hr * effort.movingS) / 60 / climb) * 100
}
