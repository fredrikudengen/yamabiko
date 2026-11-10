import type { SegmentEffort } from '@/features/segments/types'
import type { EffortBasis } from '@/features/segments/utils/efforts'

/** Where one pass stands among all passes of its segment, on one basis. */
export interface Milestone {
  /** 1 = fastest. Equal times (to the second) share a rank. */
  rank: number
  /** How many passes the segment has, from every source. */
  count: number
  /** The fastest pass: a personal record. */
  isPr: boolean
  /** The time may be off (see `SegmentEffort.doubts`), so a record is shown with a question mark. */
  doubtful: boolean
}

/**
 * The standing of a pass. The server ranks every pass of the segment whatever its source, because the
 * time between two nodes is computed from the GPS track in the same way for all of them; heart rate
 * and ascent are the numbers that differ. The rank is the current standing, not whether the pass was a
 * record on the day it was walked.
 *
 * @param effort - A pass, with the standings the server computed.
 * @param basis - Rank by moving time (without long stops) or by total time.
 * @returns The standing, or `null` when the segment has a single pass: there is nothing to rank against.
 */
export function milestoneOf(effort: SegmentEffort, basis: EffortBasis): Milestone | null {
  if (effort.segmentEffortCount < 2) {
    return null
  }
  const rank = basis === 'total' ? effort.rankTotal : effort.rankMoving
  return {
    rank,
    count: effort.segmentEffortCount,
    isPr: rank === 1,
    doubtful: effort.doubts.length > 0,
  }
}

/** The i18n key and values for a standing, such as "PR, of 8", "PR?, of 8" or "2 of 8". */
export function milestoneText(milestone: Milestone): {
  key: string
  values: Record<string, number>
} {
  if (milestone.isPr) {
    return {
      key: milestone.doubtful
        ? 'activities.segments.milestone.prDoubtful'
        : 'activities.segments.milestone.pr',
      values: { count: milestone.count },
    }
  }
  return {
    key: 'activities.segments.milestone.rank',
    values: { rank: milestone.rank, count: milestone.count },
  }
}
