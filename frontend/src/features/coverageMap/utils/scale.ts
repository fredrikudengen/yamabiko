/**
 * The red scale: darker means a cell was walked more often.
 *
 * The buckets are fixed rather than stretched over the highest count, so the
 * same colour means the same thing between visits and between cell sizes. The
 * counts are very skewed — the cells near home are passed on nearly every tour
 * while a single trip to the mountains leaves ones passed once — and a linear
 * ramp over that range would leave everything but home looking identical.
 *
 * The reds are fixed rather than theme tokens: they are drawn over map tiles,
 * not over the page background, so they must hold up against the map in both
 * themes.
 */

/** One step of the scale. */
export interface CoverageBucket {
  /** Lowest count that falls in this bucket. */
  from: number
  /** Highest count in this bucket, or `null` when the bucket is open-ended. */
  to: number | null
  /** Fill colour. */
  color: string
}

/** The scale, from least to most often walked. */
export const COVERAGE_BUCKETS: readonly CoverageBucket[] = [
  { from: 1, to: 1, color: '#fecaca' },
  { from: 2, to: 3, color: '#f87171' },
  { from: 4, to: 9, color: '#dc2626' },
  { from: 10, to: null, color: '#7f1d1d' },
] as const

/** How solid a cell is drawn. Low enough to read the map through it. */
export const CELL_FILL_OPACITY = 0.55

/**
 * The bucket a count falls in.
 *
 * @param count - How many tours passed through the cell.
 * @returns The matching bucket; the first one for anything below the scale.
 */
export function bucketOf(count: number): CoverageBucket {
  for (let index = COVERAGE_BUCKETS.length - 1; index > 0; index -= 1) {
    const bucket = COVERAGE_BUCKETS[index]
    if (bucket && count >= bucket.from) {
      return bucket
    }
  }
  return COVERAGE_BUCKETS[0] as CoverageBucket
}

/**
 * The colour for a count.
 *
 * @param count - How many tours passed through the cell.
 * @returns A CSS colour.
 */
export function colorOf(count: number): string {
  return bucketOf(count).color
}

/**
 * The buckets worth showing in the legend: everything up to and including the
 * one the highest count falls in. Showing "10+" when nothing has been walked
 * more than twice would suggest the map is hiding something.
 *
 * @param maxCount - The highest count on the map.
 * @returns The buckets to draw, least walked first.
 */
export function legendBuckets(maxCount: number): CoverageBucket[] {
  if (maxCount < 1) {
    return []
  }
  const last = COVERAGE_BUCKETS.indexOf(bucketOf(maxCount))
  return COVERAGE_BUCKETS.slice(0, last + 1)
}
