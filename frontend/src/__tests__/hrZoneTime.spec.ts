import { beforeEach, describe, expect, it } from 'vitest'

import type { ActivityStream, StreamWaypoint } from '@/features/activities/types'

import { useHrZoneLimits } from '@/features/activities/composables/useHrZoneLimits'
import {
  computeZoneSeconds,
  DEFAULT_HR_ZONE_LIMITS,
  isValidZoneLimits,
  parseZoneLimitInputs,
  toZoneBuckets,
  zoneBands,
  zoneOf,
  zoneRangeLabel,
  type HrZoneLimits,
} from '@/features/activities/utils/hrZoneTime'
import { hrZoneColor } from '@/features/activities/utils/hrZones'
import { buildMovingHrZones } from '@/features/activities/utils/streams'
import { clearUserScopedStorage, getStorageItem } from '@/lib/storage'

import { makeActivity } from './fixtures/activity'

const LIMITS: HrZoneLimits = [100, 120, 140, 160]

/** One sample per second from `from` (inclusive) to `to` (exclusive) at a constant heart rate. */
function steady(from: number, to: number, value: number) {
  return Array.from({ length: to - from }, (_, i) => ({ t: from + i, value }))
}

describe('zoneOf', () => {
  it('puts a limit in the zone above it', () => {
    const [a, b, c, d] = DEFAULT_HR_ZONE_LIMITS
    expect(zoneOf(a - 1, DEFAULT_HR_ZONE_LIMITS)).toBe(1)
    expect(zoneOf(a, DEFAULT_HR_ZONE_LIMITS)).toBe(2)
    expect(zoneOf(b - 1, DEFAULT_HR_ZONE_LIMITS)).toBe(2)
    expect(zoneOf(b, DEFAULT_HR_ZONE_LIMITS)).toBe(3)
    expect(zoneOf(c, DEFAULT_HR_ZONE_LIMITS)).toBe(4)
    expect(zoneOf(d - 1, DEFAULT_HR_ZONE_LIMITS)).toBe(4)
    expect(zoneOf(d, DEFAULT_HR_ZONE_LIMITS)).toBe(5)
    expect(zoneOf(220, DEFAULT_HR_ZONE_LIMITS)).toBe(5)
  })
})

describe('zoneRangeLabel', () => {
  it('writes ranges that do not overlap or leave a gap', () => {
    expect([1, 2, 3, 4, 5].map((z) => zoneRangeLabel(z, DEFAULT_HR_ZONE_LIMITS))).toEqual([
      '< 103',
      '103 - 112',
      '113 - 125',
      '126 - 153',
      '≥ 154',
    ])
  })
})

describe('zoneBands', () => {
  it('starts each zone at its limit, with zone 1 open downwards', () => {
    const bands = zoneBands(LIMITS)

    expect(bands.map((b) => b.from)).toEqual([Number.NEGATIVE_INFINITY, 100, 120, 140, 160])
    // The same colours as the bars on the zone card.
    expect(bands.map((b) => b.color)).toEqual([1, 2, 3, 4, 5].map((z) => hrZoneColor(z)))
  })
})

describe('zone limits validation', () => {
  it('has Google Health limits as the default, and they are valid', () => {
    expect(DEFAULT_HR_ZONE_LIMITS).toEqual([103, 113, 126, 154])
    expect(isValidZoneLimits(DEFAULT_HR_ZONE_LIMITS)).toBe(true)
  })

  it('rejects the wrong length, non-integers, out-of-range and non-increasing values', () => {
    expect(isValidZoneLimits([100, 120, 140])).toBe(false)
    expect(isValidZoneLimits([100, 120, 140, 160, 180])).toBe(false)
    expect(isValidZoneLimits([100, 120.5, 140, 160])).toBe(false)
    expect(isValidZoneLimits([100, '120', 140, 160])).toBe(false)
    expect(isValidZoneLimits([29, 120, 140, 160])).toBe(false)
    expect(isValidZoneLimits([100, 120, 140, 251])).toBe(false)
    expect(isValidZoneLimits([100, 120, 120, 160])).toBe(false)
    expect(isValidZoneLimits([100, 120, 110, 160])).toBe(false)
    expect(isValidZoneLimits(null)).toBe(false)
    expect(isValidZoneLimits('103,113,126,154')).toBe(false)
  })

  it('accepts the bounds themselves', () => {
    expect(isValidZoneLimits([30, 31, 249, 250])).toBe(true)
  })

  it('parses typed limits and says what is wrong with bad ones', () => {
    expect(parseZoneLimitInputs([' 100', '120', '140 ', '160'])).toEqual({ limits: LIMITS })
    expect(parseZoneLimitInputs(['100', '', '140', '160'])).toEqual({ error: 'incomplete' })
    expect(parseZoneLimitInputs(['100', 'abc', '140', '160'])).toEqual({ error: 'incomplete' })
    expect(parseZoneLimitInputs(['100', '120.5', '140', '160'])).toEqual({ error: 'incomplete' })
    expect(parseZoneLimitInputs(['100', '120', '140'])).toEqual({ error: 'incomplete' })
    expect(parseZoneLimitInputs(['10', '120', '140', '160'])).toEqual({ error: 'range' })
    expect(parseZoneLimitInputs(['100', '120', '140', '300'])).toEqual({ error: 'range' })
    expect(parseZoneLimitInputs(['100', '140', '120', '160'])).toEqual({ error: 'order' })
    expect(parseZoneLimitInputs(['100', '100', '140', '160'])).toEqual({ error: 'order' })
  })
})

describe('computeZoneSeconds', () => {
  it('lets every sample hold its heart rate until the next, and ignores the last', () => {
    // 90 for 10 s (t 0..9), 130 for 5 s (t 10..14); the sample at t = 15 has no successor.
    const samples = [...steady(0, 10, 90), ...steady(10, 15, 130), { t: 15, value: 190 }]
    const result = computeZoneSeconds(samples, LIMITS)

    expect(result.seconds).toEqual([10, 0, 5, 0, 0])
    expect(result.countedS).toBe(15)
    expect(result.stoppedS).toBe(0)
    expect(result.gapS).toBe(0)
  })

  it('weighs by time, not by number of samples', () => {
    // Two samples in zone 1 that are 1 s apart, then one in zone 3 that holds for 20 s.
    const samples = [
      { t: 0, value: 90 },
      { t: 1, value: 90 },
      { t: 2, value: 130 },
      { t: 22, value: 130 },
    ]
    expect(computeZoneSeconds(samples, LIMITS).seconds).toEqual([2, 0, 20, 0, 0])
  })

  it('leaves out the time inside a stop, including a stop that cuts a step in two', () => {
    // 60 s in zone 3, with a stop from 20 to 40 s.
    const samples = steady(0, 61, 130)
    const result = computeZoneSeconds(samples, LIMITS, [{ startS: 20, durationS: 20 }])

    expect(result.seconds).toEqual([0, 0, 40, 0, 0])
    expect(result.stoppedS).toBe(20)

    // A stop that starts and ends between two samples removes only its own overlap.
    const sparse = computeZoneSeconds(
      [
        { t: 0, value: 130 },
        { t: 20, value: 130 },
      ],
      LIMITS,
      [{ startS: 5.5, durationS: 4 }],
    )
    expect(sparse.seconds[2]).toBeCloseTo(16)
    expect(sparse.stoppedS).toBeCloseTo(4)
  })

  it('counts overlapping stops once', () => {
    const result = computeZoneSeconds(steady(0, 61, 130), LIMITS, [
      { startS: 10, durationS: 20 },
      { startS: 20, durationS: 20 }, // overlaps the first: together 10..40
      { startS: 100, durationS: 50 }, // outside the samples
    ])
    expect(result.stoppedS).toBe(30)
    expect(result.seconds[2]).toBe(30)
  })

  it('does not count a step longer than the limit, and reports it as a gap', () => {
    const samples = [
      ...steady(0, 10, 130), // 9 s counted (10th sample runs into the gap)
      { t: 100, value: 130 },
      { t: 110, value: 130 },
    ]
    const result = computeZoneSeconds(samples, LIMITS, [], 30)

    // t 0..8 hold 1 s each = 9 s, then 9 -> 100 is a 91 s gap, then 100 -> 110 counts 10 s.
    expect(result.seconds[2]).toBe(19)
    expect(result.gapS).toBe(91)
  })

  it('treats a step of exactly the limit as counted', () => {
    const result = computeZoneSeconds(
      [
        { t: 0, value: 130 },
        { t: 30, value: 130 },
      ],
      LIMITS,
      [],
      30,
    )
    expect(result.seconds[2]).toBe(30)
    expect(result.gapS).toBe(0)
  })

  it('does not count stop time as gap time when a stop sits inside a gap', () => {
    const result = computeZoneSeconds(
      [
        { t: 0, value: 130 },
        { t: 200, value: 130 },
      ],
      LIMITS,
      [{ startS: 20, durationS: 150 }],
    )
    expect(result.countedS).toBe(0)
    expect(result.stoppedS).toBe(150)
    expect(result.gapS).toBe(50)
  })

  describe('with a recording span', () => {
    it('reports the time before the first and after the last sample as a gap', () => {
      // Heart rate from t = 30 to 99 (69 s counted) in a recording that ran from 0 to 200.
      const result = computeZoneSeconds(steady(30, 100, 130), LIMITS, [], 30, {
        startS: 0,
        endS: 200,
      })

      expect(result.seconds[2]).toBe(69)
      // 30 s before the first sample + 101 s after the last (t = 99).
      expect(result.gapS).toBe(131)
    })

    it('leaves a stop at the edge out of the gap', () => {
      const result = computeZoneSeconds(
        steady(30, 100, 130),
        LIMITS,
        [
          { startS: 0, durationS: 20 }, // 20 of the 30 s before the first sample
          { startS: 150, durationS: 40 }, // 40 of the 101 s after the last
        ],
        30,
        { startS: 0, endS: 200 },
      )

      expect(result.gapS).toBe(10 + 61)
    })

    it('finds no gap when the samples cover the span', () => {
      const result = computeZoneSeconds(steady(0, 101, 130), LIMITS, [], 30, {
        startS: 0,
        endS: 100,
      })
      expect(result.gapS).toBe(0)
    })

    it('does not count samples that start before or end after the span as negative gap', () => {
      const result = computeZoneSeconds(steady(0, 100, 130), LIMITS, [], 30, {
        startS: 10,
        endS: 50,
      })
      expect(result.gapS).toBe(0)
    })

    it('finds nothing to compare against when there are no samples', () => {
      const result = computeZoneSeconds([], LIMITS, [], 30, { startS: 0, endS: 200 })
      expect(result.gapS).toBe(0)
    })

    it('finds no edge gap without a span, only gaps between samples', () => {
      expect(computeZoneSeconds(steady(30, 100, 130), LIMITS).gapS).toBe(0)
    })

    it('adds an edge gap to a gap between samples', () => {
      const samples = [...steady(10, 20, 130), ...steady(100, 110, 130)]
      const result = computeZoneSeconds(samples, LIMITS, [], 30, { startS: 0, endS: 120 })

      // 10 s before, 81 s between t = 19 and 100, 11 s after t = 109.
      expect(result.gapS).toBe(10 + 81 + 11)
    })
  })

  it('accepts samples in any order', () => {
    // Sorted: 0:130, 5:130, 10:90, 20:90 -> 10 s in zone 3, then 10 s in zone 1.
    const result = computeZoneSeconds(
      [
        { t: 10, value: 90 },
        { t: 0, value: 130 },
        { t: 20, value: 90 },
        { t: 5, value: 130 },
      ],
      LIMITS,
    )
    expect(result.seconds).toEqual([10, 0, 10, 0, 0])
  })

  it('skips non-finite samples and repeated times', () => {
    const result = computeZoneSeconds(
      [
        { t: 0, value: 130 },
        { t: 1, value: Number.NaN },
        { t: Number.NaN, value: 130 },
        { t: 2, value: 130 },
        { t: 2, value: 90 },
        { t: 3, value: 130 },
      ],
      LIMITS,
    )
    // Cleaned: 0:130, 2:130, 2:90, 3:130 -> 0..2 in zone 3, 2..2 skipped, 2..3 in zone 1.
    expect(result.seconds).toEqual([1, 0, 2, 0, 0])
  })

  it('returns zeros for fewer than two samples', () => {
    expect(computeZoneSeconds([], LIMITS).countedS).toBe(0)
    expect(computeZoneSeconds([{ t: 0, value: 130 }], LIMITS).countedS).toBe(0)
  })

  it('moves a sample to another zone when the limits change', () => {
    const samples = steady(0, 11, 110)
    expect(computeZoneSeconds(samples, [100, 120, 140, 160]).seconds).toEqual([0, 10, 0, 0, 0])
    expect(computeZoneSeconds(samples, [111, 120, 140, 160]).seconds).toEqual([10, 0, 0, 0, 0])
    expect(computeZoneSeconds(samples, [110, 120, 140, 160]).seconds).toEqual([0, 10, 0, 0, 0])
  })
})

describe('toZoneBuckets', () => {
  it('gives five buckets whose shares add up to 100 %', () => {
    const result = computeZoneSeconds(
      [...steady(0, 30, 90), ...steady(30, 40, 130), { t: 40, value: 130 }],
      LIMITS,
    )
    const buckets = toZoneBuckets(result, LIMITS)

    expect(buckets.map((b) => b.zone)).toEqual([1, 2, 3, 4, 5])
    expect(buckets.map((b) => b.timeSeconds)).toEqual([30, 0, 10, 0, 0])
    expect(buckets[0]!.percent).toBeCloseTo(75)
    expect(buckets[2]!.percent).toBeCloseTo(25)
    expect(buckets.reduce((sum, b) => sum + b.percent, 0)).toBeCloseTo(100)
    expect(buckets.map((b) => b.hrRange)).toEqual([
      '< 100',
      '100 - 119',
      '120 - 139',
      '140 - 159',
      '≥ 160',
    ])
  })

  it('gives zero shares when nothing was counted', () => {
    const buckets = toZoneBuckets(computeZoneSeconds([], LIMITS), LIMITS)
    expect(buckets.map((b) => b.percent)).toEqual([0, 0, 0, 0, 0])
  })
})

describe('buildMovingHrZones', () => {
  const START = Date.UTC(2026, 9, 20, 8, 0, 0)
  const iso = (seconds: number) => new Date(START + seconds * 1000).toISOString().slice(0, 19)
  const stream = (streamType: number, waypoints: StreamWaypoint[]): ActivityStream => ({
    id: streamType,
    streamType,
    waypoints,
    hrZones: null,
  })

  /** GPS starts at `gpsStart` s; heart rate every second from 0 to `end`: 90 until 100, 130 after. */
  function recording(gpsStart: number, end: number) {
    const gps: StreamWaypoint[] = []
    for (let t = gpsStart; t <= end; t += 1) {
      gps.push({ time: iso(t), lat: 60 + t * 1e-5, lon: 5 })
    }
    const hr: StreamWaypoint[] = []
    for (let t = 0; t <= end; t += 1) {
      hr.push({ time: iso(t), hr: t < 100 ? 90 : 130 })
    }
    return [stream(7, gps), stream(1, hr)]
  }

  it('leaves out the stop, measuring it from the first GPS fix', () => {
    // GPS starts 10 s after the first HR sample. A stop 80 s after the first fix, lasting 40 s, is
    // 90..130 s on the HR clock: it straddles the change from zone 1 to zone 3 at 100 s, so a stop
    // measured from the wrong origin would take a different share from each zone.
    const streams = recording(10, 200)
    const activity = makeActivity({
      importInfo: { long_stops: { stops: [{ start_s: 80, duration_s: 40 }] } },
    })
    const result = buildMovingHrZones(streams, activity, LIMITS)!

    expect(result.stopsKnown).toBe(true)
    // 0..99 s in zone 1 (100 s) minus 10 s of stop; 100..199 s in zone 3 (100 s) minus 30 s.
    expect(result.buckets.map((b) => b.timeSeconds)).toEqual([90, 0, 70, 0, 0])
    expect(result.countedS).toBe(160)
  })

  it('counts the whole recording and says so when no stops are recorded', () => {
    const result = buildMovingHrZones(
      recording(0, 200),
      makeActivity({ importInfo: null }),
      LIMITS,
    )!

    expect(result.stopsKnown).toBe(false)
    expect(result.countedS).toBe(200)
    expect(result.gapS).toBe(0)
  })

  it('reports heart rate that starts after and stops before the GPS track', () => {
    const gps: StreamWaypoint[] = []
    for (let t = 0; t <= 300; t += 1) {
      gps.push({ time: iso(t), lat: 60 + t * 1e-5, lon: 5 })
    }
    const hr: StreamWaypoint[] = []
    for (let t = 40; t <= 270; t += 1) {
      hr.push({ time: iso(t), hr: 130 })
    }
    const result = buildMovingHrZones(
      [stream(7, gps), stream(1, hr)],
      makeActivity({ importInfo: null }),
      LIMITS,
    )!

    expect(result.countedS).toBe(230)
    // 40 s before the first heart-rate sample, 30 s after the last, measured against the GPS track.
    expect(result.gapS).toBe(70)
  })

  it('leaves a stop inside a heart-rate dropout out of the gap', () => {
    const gps: StreamWaypoint[] = []
    for (let t = 0; t <= 300; t += 1) {
      gps.push({ time: iso(t), lat: 60 + t * 1e-5, lon: 5 })
    }
    // No heart rate between 100 and 200 s, but the first 60 s of that is a recorded stop.
    const hr: StreamWaypoint[] = []
    for (let t = 0; t <= 300; t += 1) {
      if (t <= 100 || t >= 200) {
        hr.push({ time: iso(t), hr: 130 })
      }
    }
    const result = buildMovingHrZones(
      [stream(7, gps), stream(1, hr)],
      makeActivity({
        importInfo: { long_stops: { stops: [{ start_s: 100, duration_s: 60 }] } },
      }),
      LIMITS,
    )!

    expect(result.gapS).toBe(40)
  })

  it('without GPS finds only the hole between samples', () => {
    const hr: StreamWaypoint[] = []
    for (let t = 0; t <= 120; t += 1) {
      if (t < 10 || t >= 110) {
        hr.push({ time: iso(t), hr: 130 })
      }
    }
    const result = buildMovingHrZones([stream(1, hr)], makeActivity({ importInfo: null }), LIMITS)!

    expect(result.gapS).toBe(101)
  })

  it('treats an importer record with an empty stop list as known', () => {
    const activity = makeActivity({ importInfo: { long_stops: { stops: [] } } })
    expect(buildMovingHrZones(recording(0, 200), activity, LIMITS)!.stopsKnown).toBe(true)
  })

  it('works without a GPS stream, measuring from the first heart-rate sample', () => {
    const [, hr] = recording(0, 200)
    const activity = makeActivity({
      importInfo: { long_stops: { stops: [{ start_s: 20, duration_s: 30 }] } },
    })
    const result = buildMovingHrZones([hr!], activity, LIMITS)!

    expect(result.countedS).toBe(170)
    expect(result.buckets.map((b) => b.timeSeconds)).toEqual([70, 0, 100, 0, 0])
  })

  it('returns null without a heart-rate stream or without times', () => {
    const [gps, hr] = recording(0, 50)
    expect(buildMovingHrZones([gps!], makeActivity(), LIMITS)).toBeNull()
    const untimed = stream(
      1,
      hr!.waypoints.map((w) => ({ hr: w.hr })),
    )
    expect(buildMovingHrZones([untimed], makeActivity(), LIMITS)).toBeNull()
  })

  it('uses the limits it is given', () => {
    const streams = recording(0, 200)
    const a = buildMovingHrZones(streams, makeActivity(), [100, 120, 140, 160])!
    const b = buildMovingHrZones(streams, makeActivity(), [80, 100, 120, 140])!

    expect(a.buckets.map((x) => x.timeSeconds)).toEqual([100, 0, 100, 0, 0])
    expect(b.buckets.map((x) => x.timeSeconds)).toEqual([0, 100, 0, 100, 0])
  })
})

describe('useHrZoneLimits', () => {
  beforeEach(() => {
    localStorage.clear()
    useHrZoneLimits().resetLimits()
  })

  it('starts at the defaults', () => {
    const { limits, isDefault } = useHrZoneLimits()
    expect(limits.value).toEqual(DEFAULT_HR_ZONE_LIMITS)
    expect(isDefault.value).toBe(true)
  })

  it('stores changed limits, shares them between callers, and survives logout', () => {
    const first = useHrZoneLimits()
    first.setLimits(LIMITS)

    expect(useHrZoneLimits().limits.value).toEqual(LIMITS)
    expect(first.isDefault.value).toBe(false)
    expect(getStorageItem('hrZoneLimits')).toEqual(LIMITS)

    clearUserScopedStorage()
    expect(getStorageItem('hrZoneLimits')).toEqual(LIMITS)
  })

  it('forgets the stored limits on reset', () => {
    const { setLimits, resetLimits, limits } = useHrZoneLimits()
    setLimits(LIMITS)
    resetLimits()

    expect(limits.value).toEqual(DEFAULT_HR_ZONE_LIMITS)
    expect(getStorageItem('hrZoneLimits')).toBeNull()
  })
})
