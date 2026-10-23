import type { SegmentEffort } from '@/features/segments/types'

/** Which time the comparison ranks by: without long stops, or the whole clock time between the nodes. */
export type EffortBasis = 'moving' | 'total'

/** The time of an effort on the given basis, in seconds. */
export function timeOf(effort: SegmentEffort, basis: EffortBasis): number {
  return basis === 'total' ? effort.elapsedS : effort.movingS
}

/** One row of the comparison: the effort, and how it stands against the fastest. */
export interface EffortRow {
  effort: SegmentEffort
  /** Seconds slower than the fastest effort on the segment; 0 for the fastest. */
  behindBestS: number
  isBest: boolean
}

/**
 * Orders efforts newest first and marks each against the fastest time on the chosen basis.
 * Moving time has long stops and stream gaps taken out; total time is the clock time
 * between the nodes. Neither is right for every comparison, so the caller chooses.
 *
 * @param efforts - Efforts of one segment, in any order.
 * @param basis - Which time to rank by; defaults to moving time.
 * @returns Rows newest first.
 */
export function compareEfforts(
  efforts: SegmentEffort[],
  basis: EffortBasis = 'moving',
): EffortRow[] {
  if (efforts.length === 0) {
    return []
  }
  const best = Math.min(...efforts.map((e) => timeOf(e, basis)))
  return [...efforts]
    .sort((a, b) => b.startTime.localeCompare(a.startTime))
    .map((effort) => ({
      effort,
      behindBestS: timeOf(effort, basis) - best,
      isBest: timeOf(effort, basis) === best,
    }))
}
