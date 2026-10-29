import { describe, expect, it } from 'vitest'

import {
  COVERAGE_BUCKETS,
  bucketOf,
  colorOf,
  legendBuckets,
} from '@/features/coverageMap/utils/scale'

describe('the red scale', () => {
  it('puts a cell walked once in the lightest bucket', () => {
    expect(bucketOf(1)).toBe(COVERAGE_BUCKETS[0])
  })

  it('puts a cell walked many times in the darkest bucket', () => {
    expect(bucketOf(500)).toBe(COVERAGE_BUCKETS[COVERAGE_BUCKETS.length - 1])
  })

  it('never jumps a bucket: each count sits in the one whose range holds it', () => {
    // The open-ended bucket has no `to`; its highest count is checked above.
    const edges = COVERAGE_BUCKETS.flatMap((bucket) =>
      bucket.to === null
        ? [[bucket.from, bucket]]
        : [
            [bucket.from, bucket],
            [bucket.to, bucket],
          ],
    ) as [number, (typeof COVERAGE_BUCKETS)[number]][]

    expect(edges.map(([count]) => bucketOf(count))).toEqual(edges.map(([, bucket]) => bucket))
  })

  it('never goes lighter as the count grows', () => {
    let previous = -1
    for (let count = 1; count <= 50; count += 1) {
      const index = COVERAGE_BUCKETS.indexOf(bucketOf(count))
      expect(index).toBeGreaterThanOrEqual(previous)
      previous = index
    }
  })

  it('falls back to the lightest colour for a count below the scale', () => {
    // Should not occur — a stored cell was walked at least once — but a colour
    // is better than undefined on a map.
    expect(colorOf(0)).toBe(COVERAGE_BUCKETS[0]?.color)
  })

  it('gives every bucket its own colour', () => {
    const colors = new Set(COVERAGE_BUCKETS.map((bucket) => bucket.color))

    expect(colors.size).toBe(COVERAGE_BUCKETS.length)
  })
})

describe('the legend', () => {
  it('stops at the bucket the highest count falls in', () => {
    expect(legendBuckets(2)).toEqual(COVERAGE_BUCKETS.slice(0, 2))
  })

  it('shows every bucket once something has been walked often', () => {
    expect(legendBuckets(40)).toEqual([...COVERAGE_BUCKETS])
  })

  it('shows nothing on an empty map', () => {
    expect(legendBuckets(0)).toEqual([])
  })

  it('always covers the colour the highest count is drawn in', () => {
    for (const maxCount of [1, 3, 4, 9, 10, 99]) {
      const shown = legendBuckets(maxCount)
      expect(shown[shown.length - 1]?.color).toBe(colorOf(maxCount))
    }
  })
})
