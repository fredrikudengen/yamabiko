import { describe, expect, it } from 'vitest'

import {
  buildPaceProfile,
  chooseBinSize,
  GPS_GAP_S,
  longStopsOf,
  paceAxisRange,
  SLOW_BIN_FACTOR,
  type TimedPoint,
  type TimedValue,
} from '@/features/activities/utils/paceProfile'

const M_PER_DEG = 111_320

/** A track that walks north at piecewise-constant speeds, one fix per second; rests wobble in place. */
function walk(
  legs: ({ walk: number; speed: number } | { rest: number } | { pause: number })[],
): TimedPoint[] {
  const points: TimedPoint[] = [{ t: 0, lat: 60, lon: 5 }]
  let t = 0
  let y = 0
  for (const leg of legs) {
    if ('walk' in leg) {
      const seconds = Math.round(leg.walk / leg.speed)
      for (let i = 0; i < seconds; i += 1) {
        t += 1
        y += leg.speed
        points.push({ t, lat: 60 + y / M_PER_DEG, lon: 5 })
      }
    } else if ('rest' in leg) {
      // Wrist GPS jitter while standing still: ±0.15 m each second is 0.3 m/s of path.
      for (let i = 0; i < leg.rest; i += 1) {
        t += 1
        points.push({ t, lat: 60 + (y + (i % 2 === 0 ? 0.15 : -0.15)) / M_PER_DEG, lon: 5 })
      }
    } else {
      t += leg.pause // the device records nothing; the clock runs
    }
  }
  return points
}

const paceOf = (speed: number) => 1 / speed

describe('buildPaceProfile', () => {
  it('gives the pace of a steady walk in every bin, on a real distance axis', () => {
    const profile = buildPaceProfile(walk([{ walk: 3000, speed: 1.25 }]))!

    expect(profile.totalM).toBeCloseTo(3000, 0)
    expect(profile.binSizeM).toBe(25)
    expect(profile.bins).toHaveLength(120)
    for (const bin of profile.bins) {
      expect(bin.gap).toBeNull()
      expect(bin.paceSPerM).toBeCloseTo(paceOf(1.25), 3)
    }
    expect(profile.bins[0]!.startM).toBe(0)
    expect(profile.bins[119]!.endM).toBeCloseTo(3000, 0)
  })

  it('averages pace as time over distance, not as a mean of speeds', () => {
    // 1 km at 1 m/s then 1 km at 2 m/s: each half keeps its own pace.
    const profile = buildPaceProfile(
      walk([
        { walk: 1000, speed: 1 },
        { walk: 1000, speed: 2 },
      ]),
    )!
    const first = profile.bins[2]!
    const last = profile.bins[profile.bins.length - 3]!

    expect(first.paceSPerM).toBeCloseTo(1, 2)
    expect(last.paceSPerM).toBeCloseTo(0.5, 2)
  })

  it('leaves a known stop out: no time, no jitter distance, and a break in the line', () => {
    const track = walk([{ walk: 600, speed: 1.2 }, { rest: 600 }, { walk: 600, speed: 1.2 }])
    const stopStart = 500
    const withStop = buildPaceProfile(track, [], {
      stops: [{ startS: stopStart, durationS: 600 }],
    })!

    // 1200 m of walking; the 180 m of jitter inside the stop is not progress.
    expect(withStop.totalM).toBeCloseTo(1200, -1)
    expect(withStop.bins.filter((b) => b.gap === 'stop')).toHaveLength(1)
    const paced = withStop.bins.filter((b) => b.paceSPerM !== null)
    expect(paced.length).toBeGreaterThan(withStop.bins.length - 3)
    for (const bin of paced) {
      expect(bin.paceSPerM).toBeCloseTo(paceOf(1.2), 2)
    }
  })

  it('treats bins far slower than the rest as stops when no stops are known', () => {
    const track = walk([{ walk: 600, speed: 1.2 }, { rest: 600 }, { walk: 600, speed: 1.2 }])
    const profile = buildPaceProfile(track)!

    // Standing still with jitter covers 0.3 m/s of path: far slower than SLOW_BIN_FACTOR x the walking pace.
    expect(1 / 0.3).toBeGreaterThan(SLOW_BIN_FACTOR * paceOf(1.2))
    expect(profile.bins.filter((b) => b.gap === 'slow').length).toBeGreaterThan(0)
    // Away from the stop every bin is the walking pace.
    for (const bin of [...profile.bins.slice(0, 10), ...profile.bins.slice(-10)]) {
      expect(bin.gap).toBeNull()
      expect(bin.paceSPerM).toBeCloseTo(paceOf(1.2), 2)
    }
    // The bin where walking turns into standing mixes both, so it can show a blip that is not the stop.
    // That is the cost of not knowing the stop; with known stops (the Google Health import) it cannot happen.
    const paces = profile.bins.flatMap((bin) => (bin.paceSPerM === null ? [] : [bin.paceSPerM]))
    expect(paces.length).toBeGreaterThan(0)
    expect(Math.max(...paces)).toBeLessThanOrEqual(SLOW_BIN_FACTOR * paceOf(1.2))
  })

  it('keeps steep slow climbing: a slow section is not a stop unless it is far slower', () => {
    const profile = buildPaceProfile(
      walk([
        { walk: 1000, speed: 1.2 },
        { walk: 500, speed: 0.6 }, // twice as slow
        { walk: 1000, speed: 1.2 },
      ]),
    )!

    expect(profile.bins.filter((b) => b.gap !== null)).toHaveLength(0)
    expect(Math.max(...profile.bins.map((b) => b.paceSPerM!))).toBeCloseTo(paceOf(0.6), 1)
  })

  it('counts the distance across a device gap but gives it no pace', () => {
    const track = walk([
      { walk: 500, speed: 1.25 },
      { pause: GPS_GAP_S + 30 },
      { walk: 500, speed: 1.25 },
    ])
    const profile = buildPaceProfile(track)!

    // The straight line across the gap (one step of 1.25 m) still counts as distance.
    expect(profile.totalM).toBeCloseTo(1000, 0)
    expect(profile.bins.every((b) => b.gap === null)).toBe(true)
    for (const bin of profile.bins) {
      expect(bin.paceSPerM).toBeCloseTo(paceOf(1.25), 2)
    }
  })

  it('marks a bin with too little data as sparse', () => {
    // A long gap that jumps 300 m in one step: those bins have distance but no usable fixes.
    const first = walk([{ walk: 500, speed: 1.25 }])
    const last = first[first.length - 1]!
    const jump: TimedPoint = { t: last.t + 200, lat: last.lat + 300 / M_PER_DEG, lon: 5 }
    const after: TimedPoint[] = Array.from({ length: 400 }, (_, i) => ({
      t: jump.t + i + 1,
      lat: jump.lat + ((i + 1) * 1.25) / M_PER_DEG,
      lon: 5,
    }))
    const profile = buildPaceProfile([...first, jump, ...after])!

    const sparse = profile.bins.filter((b) => b.gap === 'sparse')
    expect(sparse.length).toBeGreaterThan(0)
    expect(sparse.every((b) => b.paceSPerM === null)).toBe(true)
  })

  it('scales the track to the reported distance so the profile ends where the headline does', () => {
    const track = walk([{ walk: 3000, speed: 1.25 }])
    const profile = buildPaceProfile(track, [], { activityDistanceM: 3150 })!

    expect(profile.scale).toBeCloseTo(1.05, 3)
    expect(profile.totalM).toBeCloseTo(3150, 0)
    // Same time over more distance: faster pace, matching the headline average.
    expect(profile.bins[10]!.paceSPerM).toBeCloseTo(paceOf(1.25) / 1.05, 3)
  })

  it.each([6000, 1500, 0, null])(
    'does not scale when the reported distance (%s) is far from the track',
    (reported) => {
      const profile = buildPaceProfile(walk([{ walk: 3000, speed: 1.25 }]), [], {
        activityDistanceM: reported,
      })!
      expect(profile.scale).toBe(1)
      expect(profile.totalM).toBeCloseTo(3000, 0)
    },
  )

  it('gives the height per bin along the distance axis and fills bins without samples', () => {
    const track = walk([{ walk: 2000, speed: 1.25 }])
    // Height 100 m + 0.1 m per metre walked, sampled every 20 s (every 25 m): a bin of 25 m can miss one.
    const elevation: TimedValue[] = track
      .filter((p) => p.t % 40 === 0)
      .map((p) => ({ t: p.t, value: 100 + 0.1 * (p.t * 1.25) }))
    const profile = buildPaceProfile(track, elevation)!

    const heights = profile.bins.map((b) => b.elevationM)
    expect(heights.every((h) => h !== null)).toBe(true)
    expect(heights[0]!).toBeCloseTo(100, 0)
    expect(heights[heights.length - 1]!).toBeGreaterThan(heights[0]! + 150)
    for (let i = 1; i < heights.length; i += 1) {
      expect(heights[i]!).toBeGreaterThanOrEqual(heights[i - 1]! - 0.5)
    }
  })

  it('has no heights without height samples', () => {
    const profile = buildPaceProfile(walk([{ walk: 500, speed: 1.25 }]))!
    expect(profile.bins.every((b) => b.elevationM === null)).toBe(true)
  })

  it('returns null for a track too short or that never moves', () => {
    expect(buildPaceProfile([])).toBeNull()
    expect(buildPaceProfile([{ t: 0, lat: 60, lon: 5 }])).toBeNull()
    expect(buildPaceProfile(walk([{ rest: 0 }]))).toBeNull()
    expect(
      buildPaceProfile([
        { t: 0, lat: 60, lon: 5 },
        { t: 1, lat: 60, lon: 5 },
      ]),
    ).toBeNull()
  })

  it('ignores fixes whose time does not advance', () => {
    const track = walk([{ walk: 500, speed: 1.25 }])
    const duplicated = track.flatMap((p) => [p, { ...p }])
    expect(buildPaceProfile(duplicated)!.totalM).toBeCloseTo(buildPaceProfile(track)!.totalM, 0)
  })
})

describe('chooseBinSize', () => {
  it.each([
    [400, 25],
    [3000, 25],
    [5000, 50],
    [16_330, 200],
    [40_000, 500],
    [500_000, 1000],
  ])('%s m gets bins of %s m', (total, expected) => {
    expect(chooseBinSize(total)).toBe(expected)
  })
})

describe('paceAxisRange', () => {
  it('shows the typical spread, not the extremes, rounded to 15 s', () => {
    const values = [...Array.from({ length: 98 }, () => 600), 300, 3000]
    const range = paceAxisRange(values)!

    expect(range.min % 15).toBe(0)
    expect(range.max % 15).toBe(0)
    expect(range.min).toBeGreaterThanOrEqual(300)
    expect(range.max).toBeLessThan(1000)
    expect(range.min).toBeLessThanOrEqual(600)
    expect(range.max).toBeGreaterThanOrEqual(600)
  })

  it('keeps a usable range for a constant pace and ignores NaN', () => {
    const range = paceAxisRange([600, Number.NaN, 600])!
    expect(range.max - range.min).toBeGreaterThanOrEqual(30)
    expect(paceAxisRange([])).toBeNull()
    expect(paceAxisRange([Number.NaN])).toBeNull()
  })
})

describe('longStopsOf', () => {
  it('reads the stops the Google Health importer writes', () => {
    expect(
      longStopsOf({
        long_stops: {
          stops: [
            { start_s: 6120, duration_s: 1137, untrimmed_duration_s: 1200 },
            { start_s: 9000, duration_s: 400 },
          ],
        },
      }),
    ).toEqual([
      { startS: 6120, durationS: 1137 },
      { startS: 9000, durationS: 400 },
    ])
  })

  it.each([
    null,
    {},
    { long_stops: null },
    { long_stops: { stops: 'no' } },
    {
      long_stops: { stops: [null, { start_s: 'x', duration_s: 5 }, { start_s: 1, duration_s: 0 }] },
    },
  ])('gives no stops for %j', (importInfo) => {
    expect(longStopsOf(importInfo as Record<string, unknown> | null)).toEqual([])
  })
})
