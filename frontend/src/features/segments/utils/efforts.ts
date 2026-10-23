import type { SegmentEffort } from '@/features/segments/types'

/** One row of the comparison: the effort, and how it stands against the fastest. */
export interface EffortRow {
  effort: SegmentEffort
  /** Seconds slower than the fastest effort on the segment; 0 for the fastest. */
  behindBestS: number
  isBest: boolean
}

/**
 * Orders efforts newest first and marks each against the fastest moving time,
 * the comparable time (long stops and stream gaps are already taken out).
 *
 * @param efforts - Efforts of one segment, in any order.
 * @returns Rows newest first.
 */
export function compareEfforts(efforts: SegmentEffort[]): EffortRow[] {
  if (efforts.length === 0) {
    return []
  }
  const best = Math.min(...efforts.map((e) => e.movingS))
  return [...efforts]
    .sort((a, b) => b.startTime.localeCompare(a.startTime))
    .map((effort) => ({
      effort,
      behindBestS: effort.movingS - best,
      isBest: effort.movingS === best,
    }))
}
