import { describe, expect, it } from 'vitest'

import type { ActivityStream, StreamWaypoint } from '@/features/activities/types'

import { buildValueProfile } from '@/features/activities/utils/paceProfile'
import { buildDistanceValueChart, buildStreamCharts } from '@/features/activities/utils/streams'

import { makeActivity } from './fixtures/activity'

const M_PER_DEG = 111_320
const START = Date.UTC(2026, 9, 20, 8, 0, 0)

const iso = (seconds: number) => new Date(START + seconds * 1000).toISOString().slice(0, 19)

function stream(streamType: number, waypoints: StreamWaypoint[]): ActivityStream {
  return { id: streamType, streamType, waypoints, hrZones: null }
}

/**
 * A walk north at 1.25 m/s with a 600 s stand-still half way. Heart rate is 100 + distance / 10 while
 * walking and 60 while standing still; height is 100 + distance / 10. `dropFixes` removes GPS fixes
 * (the watch lost the signal) but keeps the heart-rate samples.
 */
function hike(options: { dropFixes?: [number, number]; withTimes?: boolean } = {}) {
  const withTimes = options.withTimes ?? true
  const map: StreamWaypoint[] = []
  const height: StreamWaypoint[] = []
  const hr: StreamWaypoint[] = []
  let y = 0
  let t = 0
  let resting = false
  const add = () => {
    const time = withTimes ? iso(t) : undefined
    const dropped = options.dropFixes && t >= options.dropFixes[0] && t < options.dropFixes[1]
    if (!dropped) {
      map.push({ time, lat: 60 + y / M_PER_DEG, lon: 5 })
    }
    height.push({ time, ele: 100 + 0.1 * y })
    hr.push({ time, hr: resting ? 60 : 100 + y / 10 })
  }
  add()
  for (let i = 0; i < 480; i += 1) {
    t += 1
    y += 1.25
    add()
  }
  const stopStart = t
  resting = true
  for (let i = 0; i < 600; i += 1) {
    t += 1
    y += i % 2 === 0 ? 0.15 : -0.15
    add()
  }
  resting = false
  for (let i = 0; i < 480; i += 1) {
    t += 1
    y += 1.25
    add()
  }
  return { streams: [stream(7, map), stream(4, height), stream(1, hr)], stopStart }
}

const activity = (overrides = {}) =>
  makeActivity({ activityType: 12, distance: 1200, pace: 0.8, ...overrides })

const withStop = (stopStart: number) => ({
  long_stops: { stops: [{ start_s: stopStart, duration_s: 600 }] },
})

describe('buildDistanceValueChart', () => {
  it('plots heart rate per distance bin on a real distance axis', () => {
    const { streams, stopStart } = hike()
    const chart = buildDistanceValueChart(
      'hr',
      streams,
      activity({ importInfo: withStop(stopStart) }),
      'metric',
    )!
    const [series] = chart.render.series

    expect(chart.metric).toBe('hr')
    expect(chart.render.xUnit).toBe('km')
    expect(chart.render.labels).toHaveLength(series!.data.length)
    // The axis ends where the walk does (1.2 km), not at the number of samples.
    expect(Number(chart.render.labels![chart.render.labels!.length - 1])).toBeCloseTo(1.19, 1)
    // Heart rate follows distance: low at the start, high at the end.
    const walked = series!.data.filter((v) => !Number.isNaN(v))
    expect(walked[0]).toBeLessThan(110)
    expect(walked[walked.length - 1]).toBeGreaterThan(210)
    for (let i = 1; i < walked.length; i += 1) {
      expect(walked[i]!).toBeGreaterThanOrEqual(walked[i - 1]!)
    }
    expect(chart.stats.map((s) => s.labelKey)).toContain('activities.metrics.avgHr')
  })

  it('leaves the resting heart rate out and breaks the line at the stop', () => {
    const { streams, stopStart } = hike()
    const chart = buildDistanceValueChart(
      'hr',
      streams,
      activity({ importInfo: withStop(stopStart) }),
      'metric',
    )!
    const data = chart.render.series[0]!.data

    expect(data.filter(Number.isNaN)).toHaveLength(1)
    // The 600 s at 60 bpm would drag the bin it sits in far below the walking heart rate.
    expect(Math.min(...data.filter((v) => !Number.isNaN(v)))).toBeGreaterThan(95)
  })

  it('keeps heart rate where the GPS dropped out, placed along the straight line', () => {
    const { streams, stopStart } = hike({ dropFixes: [100, 200] })
    const chart = buildDistanceValueChart(
      'hr',
      streams,
      activity({ importInfo: withStop(stopStart) }),
      'metric',
    )!
    // Only the stop is empty; the lost-signal stretch still has heart rate.
    expect(chart.render.series[0]!.data.filter(Number.isNaN)).toHaveLength(1)
  })

  it('plots height per bin without holes', () => {
    const { streams, stopStart } = hike()
    const chart = buildDistanceValueChart(
      'elevation',
      streams,
      activity({ importInfo: withStop(stopStart) }),
      'metric',
    )!
    const data = chart.render.series[0]!.data

    expect(chart.metric).toBe('elevation')
    // The stop bin is empty in the heart-rate chart, but height is filled from the neighbours' samples
    // and is also left out in the stop bin only; no other bin is missing.
    expect(data.filter(Number.isNaN).length).toBeLessThanOrEqual(1)
    expect(data[0]).toBeCloseTo(100 + 0.1 * 12.5, 0)
    expect(chart.stats.map((s) => s.labelKey)).toContain('activities.metrics.elevationGain')
  })

  it('shows heights in feet and distance in miles for imperial users', () => {
    const { streams } = hike()
    const chart = buildDistanceValueChart('elevation', streams, activity(), 'imperial')!

    expect(chart.render.xUnit).toBe('mi')
    expect(chart.render.series[0]!.data[0]).toBeCloseTo((100 + 1.25) * 3.28084, 0)
  })

  it.each([
    ['no timestamps on the fixes', () => hike({ withTimes: false }).streams, activity()],
    ['swimming', () => hike().streams, activity({ activityType: 8 })],
    ['no distance', () => hike().streams, activity({ distance: 0 })],
    ['no GPS', () => hike().streams.filter((s) => s.streamType !== 7), activity()],
  ])('returns null for %s, so the plain chart stays', (_name, streams, act) => {
    expect(buildDistanceValueChart('hr', streams(), act, 'metric')).toBeNull()
  })
})

describe('buildStreamCharts with distance axes', () => {
  it('replaces the heart-rate and height charts but keeps their order and privacy', () => {
    const { streams } = hike()
    const charts = buildStreamCharts(streams, activity(), 'metric', () => true)

    const hr = charts.find((c) => c.metric === 'hr')!
    const elevation = charts.find((c) => c.metric === 'elevation')!
    expect(hr.render.labels).toHaveLength(hr.render.series[0]!.data.length)
    // ~100 bins, not one label per second (1 561 samples).
    expect(hr.render.labels!.length).toBeLessThan(200)
    expect(elevation.render.labels!.length).toBeLessThan(200)
    expect(charts.map((c) => c.metric).indexOf('hr')).toBeLessThan(
      charts.map((c) => c.metric).indexOf('elevation'),
    )
  })

  it('does not build a hidden metric', () => {
    const { streams } = hike()
    const charts = buildStreamCharts(streams, activity(), 'metric', (m) => m !== 'hr')

    expect(charts.some((c) => c.metric === 'hr')).toBe(false)
    expect(charts.some((c) => c.metric === 'elevation')).toBe(true)
  })

  it('falls back to the per-sample chart without a timed GPS track', () => {
    const { streams } = hike({ withTimes: false })
    const charts = buildStreamCharts(streams, activity(), 'metric', () => true)
    const hr = charts.find((c) => c.metric === 'hr')!

    expect(hr.render.series[0]!.data).toHaveLength(1561)
  })
})

describe('buildValueProfile', () => {
  const line = Array.from({ length: 11 }, (_, i) => ({
    t: i * 10,
    lat: 60 + (i * 12.5) / M_PER_DEG,
    lon: 5,
  }))

  it('drops samples outside the track and non-finite values', () => {
    const profile = buildValueProfile(line, [
      { t: -5, value: 999 },
      { t: 50, value: Number.NaN },
      { t: 50, value: 120 },
      { t: 500, value: 999 },
    ])!

    const values = profile.bins.map((b) => b.value).filter((v): v is number => v !== null)
    expect(values).toEqual([120])
  })

  it('averages the samples of a bin and returns null for the track too short to bin', () => {
    const profile = buildValueProfile(line, [
      { t: 50, value: 100 },
      { t: 51, value: 110 },
    ])!
    expect(profile.bins.find((b) => b.value !== null)!.value).toBe(105)
    expect(buildValueProfile([line[0]!], [{ t: 0, value: 1 }])).toBeNull()
  })

  it('fills empty bins from their neighbours only when asked', () => {
    const samples = [
      { t: 0, value: 100 },
      { t: 100, value: 200 },
    ]
    const empty = buildValueProfile(line, samples)!
    const filled = buildValueProfile(line, samples, {}, true)!

    expect(empty.bins.some((b) => b.value === null)).toBe(true)
    expect(filled.bins.every((b) => b.value !== null)).toBe(true)
  })
})
