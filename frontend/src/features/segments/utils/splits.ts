/**
 * Where on the way one pass gained or lost against another: the difference of
 * their clocks at each hundredth of the way.
 */

import type { EffortProfile } from '@/features/segments/types'
import type { EffortBasis } from '@/features/segments/utils/efforts'

/** How many hundredths a stretch is when looking for where the most time went. */
export const STRETCH_STEPS = 10

/**
 * @param profile - The clock along a pass.
 * @param basis - Moving or total time.
 * @returns The clock on that basis.
 */
function clockOf(profile: EffortProfile, basis: EffortBasis): number[] {
  return basis === 'total' ? profile.elapsedS : profile.movingS
}

/**
 * How far behind the reference a pass was at each hundredth of the way.
 *
 * @param mine - The pass to look at.
 * @param reference - The pass to compare with, usually the best.
 * @param basis - Moving or total time.
 * @returns Seconds behind at each share; negative where the pass was ahead.
 */
export function behindAlongTheWay(
  mine: EffortProfile,
  reference: EffortProfile,
  basis: EffortBasis,
): number[] {
  const theirs = clockOf(reference, basis)
  return clockOf(mine, basis).map((value, index) => value - (theirs[index] ?? value))
}

/** A stretch of the way and the time won or lost on it. */
export interface Stretch {
  /** Start of the stretch, in percent of the way. */
  fromPct: number
  /** End of the stretch, in percent of the way. */
  toPct: number
  /** Seconds lost on the stretch; negative when time was won. */
  seconds: number
}

/**
 * The stretches of `STRETCH_STEPS` hundredths where the most time was lost and won.
 *
 * @param behind - Seconds behind at each hundredth (`behindAlongTheWay`).
 * @returns The worst and the best stretch, or `null` for a stretch that did not lose (or win) any time.
 */
export function biggestStretches(behind: readonly number[]): {
  lost: Stretch | null
  won: Stretch | null
} {
  let lost: Stretch | null = null
  let won: Stretch | null = null
  for (let from = 0; from + STRETCH_STEPS < behind.length; from += 1) {
    const to = from + STRETCH_STEPS
    const seconds = (behind[to] ?? 0) - (behind[from] ?? 0)
    if (seconds > 0 && (!lost || seconds > lost.seconds)) {
      lost = { fromPct: from, toPct: to, seconds }
    }
    if (seconds < 0 && (!won || seconds < won.seconds)) {
      won = { fromPct: from, toPct: to, seconds }
    }
  }
  return { lost, won }
}
