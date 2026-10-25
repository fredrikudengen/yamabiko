import { describe, expect, it } from 'vitest'

import type { ActivityStream, StreamWaypoint } from '@/features/activities/types'

import { buildPaceProfileChart, buildStreamCharts } from '@/features/activities/utils/streams'

import { makeActivity } from './fixtures/activity'

const M_PER_DEG = 111_320
const START = Date.UTC(2026, 9, 20, 8, 0, 0)

const iso = (seconds: number) => new Date(START + seconds * 1000).toISOString().slice(0, 19)

function stream(streamType: number, waypoints: StreamWaypoint[]): ActivityStream {
  return { id: streamType, streamType, waypoints, hrZones: null }
}

/**
 * A hike north at 1.25 m/s with a 600 s stand-still half way, as the three streams the importer stores:
 * GPS (type 7), height (type 4) and the noisy per-second pace (type 6).
 */
function hike(options: { withTimes?: boolean } = {}) {
  const withTimes = options.withTimes ?? true
  const map: StreamWaypoint[] = []
  const height: StreamWaypoint[] = []
  const pace: StreamWaypoint[] = []
  let y = 0
  let t = 0
  const add = () => {
    const time = withTimes ? iso(t) : undefined
    map.push({ time, lat: 60 + y / M_PER_DEG, lon: 5 })
    height.push({ time, ele: 100 + 0.1 * y })
    pace.push({ time, pace: t % 2 === 0 ? 0.8 : 2 })
  }
  add()
  for (let i = 0; i < 480; i += 1) {
    t += 1
    y += 1.25
    add()
  }
  const stopStart = t
  for (let i = 0; i < 600; i += 1) {
    t += 1
    y += i % 2 === 0 ? 0.15 : -0.15
    add()
  }
  for (let i = 0; i < 480; i += 1) {
    t += 1
    y += 1.25
    add()
  }
  return { streams: [stream(7, map), stream(4, height), stream(6, pace)], stopStart }
}

const activity = (overrides = {}) =>
  makeActivity({ activityType: 12, distance: 1200, pace: 0.8, ...overrides })

const withStop = (stopStart: number) => ({
  long_stops: { stops: [{ start_s: stopStart, duration_s: 600 }] },
})

describe('buildPaceProfileChart', () => {
  it('plots pace per distance bin with the height behind and the stop left as a break', () => {
    const { streams, stopStart } = hike()
    const chart = buildPaceProfileChart(
      streams,
      activity({ importInfo: withStop(stopStart) }),
      'metric',
      true,
    )!
    const [pace, height] = chart.render.series

    expect(chart.metric).toBe('pace')
    // Faster (fewer seconds) is higher, as in the plain pace chart.
    expect(chart.render.invertY).toBe(true)
    expect(chart.render.xUnit).toBe('km')
    expect(chart.render.labels).toHaveLength(pace!.data.length)
    // 1200 m on a real distance axis: the last label is the end of the walk, not the end of the clock.
    expect(Number(chart.render.labels![chart.render.labels!.length - 1])).toBeCloseTo(1.19, 1)
    // Bins are smooth: the pace stream alternated between 0.8 and 2 s/m, the bins do not.
    const walked = pace!.data.filter((v) => !Number.isNaN(v))
    for (const value of walked) {
      expect(value).toBeCloseTo(800, -1) // 0.8 s/m shown as s/km
    }
    expect(pace!.data.filter(Number.isNaN)).toHaveLength(1)
    expect(chart.render.yMin).toBeLessThan(800)
    expect(chart.render.yMax).toBeGreaterThan(800)
    expect(height).toMatchObject({ backdrop: true, color: '#94a3b8' })
    expect(height!.format!(123.4)).toBe('123 m')
    expect(chart.render.valueFormat!(750)).toBe('12:30')
    expect(chart.stats.length).toBeGreaterThan(0)
  })

  it('converts to miles and feet for imperial users', () => {
    const { streams, stopStart } = hike()
    const chart = buildPaceProfileChart(
      streams,
      activity({ importInfo: withStop(stopStart) }),
      'imperial',
      true,
    )!

    expect(chart.render.xUnit).toBe('mi')
    expect(Number(chart.render.labels![chart.render.labels!.length - 1])).toBeCloseTo(0.74, 1)
    expect(chart.render.series[1]!.format!(100)).toBe('100 ft')
    expect(chart.render.series[0]!.data.find((v) => !Number.isNaN(v))).toBeCloseTo(1287, -1)
  })

  it('leaves the height out when the viewer may not see it', () => {
    const { streams } = hike()
    const chart = buildPaceProfileChart(streams, activity(), 'metric', false)!

    expect(chart.render.series).toHaveLength(1)
  })

  it('has no profile when the GPS fixes carry no time', () => {
    expect(
      buildPaceProfileChart(hike({ withTimes: false }).streams, activity(), 'metric', true),
    ).toBeNull()
  })

  it.each([8, 9, 13])('has no profile for pace per 100 m or 500 m (type %s)', (type) => {
    expect(
      buildPaceProfileChart(hike().streams, activity({ activityType: type }), 'metric', true),
    ).toBeNull()
  })

  it('has no profile for cycling (speed, not pace)', () => {
    expect(
      buildPaceProfileChart(hike().streams, activity({ activityType: 4 }), 'metric', true),
    ).toBeNull()
  })
})

describe('buildStreamCharts with the pace profile', () => {
  const visible = () => true

  it('replaces the noisy pace chart when the track supports it', () => {
    const { streams, stopStart } = hike()
    const charts = buildStreamCharts(
      streams,
      activity({ importInfo: withStop(stopStart) }),
      'metric',
      visible,
    )
    const pace = charts.find((chart) => chart.metric === 'pace')!

    expect(pace.render.series).toHaveLength(2)
    expect(pace.render.yMin).toBeDefined()
    // The height still gets its own chart below.
    expect(charts.map((chart) => chart.metric)).toEqual(['pace', 'elevation'])
  })

  it('keeps the plain pace chart when the fixes have no time', () => {
    const { streams } = hike({ withTimes: false })
    const pace = buildStreamCharts(streams, activity(), 'metric', visible).find(
      (chart) => chart.metric === 'pace',
    )!

    expect(pace.render.series).toHaveLength(1)
    expect(pace.render.yMin).toBeUndefined()
  })

  it('shows no pace chart when pace is hidden, even if the track could draw one', () => {
    const charts = buildStreamCharts(
      hike().streams,
      activity(),
      'metric',
      (metric) => metric !== 'pace',
    )

    expect(charts.some((chart) => chart.metric === 'pace')).toBe(false)
  })

  it('leaves out the height profile when height is hidden', () => {
    const charts = buildStreamCharts(
      hike().streams,
      activity(),
      'metric',
      (metric) => metric !== 'elevation',
    )
    const pace = charts.find((chart) => chart.metric === 'pace')!

    expect(pace.render.series).toHaveLength(1)
  })

  it('does not draw a pace chart from the track alone', () => {
    const { streams } = hike()
    const withoutPaceStream = streams.filter((s) => s.streamType !== 6)

    expect(
      buildStreamCharts(withoutPaceStream, activity(), 'metric', visible).some(
        (c) => c.metric === 'pace',
      ),
    ).toBe(false)
  })
})
