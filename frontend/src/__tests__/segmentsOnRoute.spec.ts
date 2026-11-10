import { describe, expect, it, vi } from 'vitest'

import type { ActivityStream } from '@/features/activities/types'
import type { SegmentEffort } from '@/features/segments/types'

import { createLeafletMapProvider } from '@/providers/leafletMapProvider'
import {
  segmentHighlights,
  stretchOf,
  timedTrackPoints,
  utcMillis,
} from '@/features/segments/utils/onRoute'

const drawn: { kind: string; options: Record<string, unknown>; tooltip?: string }[] = []

vi.mock('leaflet', async (importOriginal) => {
  const leaflet = await importOriginal<typeof import('leaflet')>()
  const record =
    (kind: 'polyline' | 'circleMarker') =>
    (where: unknown, options: Record<string, unknown> = {}) => {
      const layer = (
        leaflet[kind] as (a: unknown, b: unknown) => ReturnType<typeof leaflet.polyline>
      )(where, options)
      const entry: (typeof drawn)[number] = { kind, options }
      drawn.push(entry)
      const bind = layer.bindTooltip.bind(layer)
      layer.bindTooltip = ((content: string, tooltipOptions?: unknown) => {
        entry.tooltip = content
        return bind(content, tooltipOptions as never)
      }) as typeof layer.bindTooltip
      return layer
    }
  return { ...leaflet, polyline: record('polyline'), circleMarker: record('circleMarker') }
})

function stream(times: string[]): ActivityStream {
  return {
    id: 1,
    streamType: 7,
    hrZones: null,
    waypoints: times.map((time, index) => ({
      time,
      lat: 60 + index / 1000,
      lon: 5 + index / 1000,
    })),
  }
}

function effort(extra: Partial<SegmentEffort>): SegmentEffort {
  return {
    id: 1,
    segmentId: 2,
    segmentName: 'Løvstakken',
    activityId: 3,
    activityName: 'Tur',
    source: 'google_health',
    startTime: '2026-09-30T16:00:01+02:00',
    endTime: '2026-09-30T16:00:03+02:00',
    elapsedS: 2,
    movingS: 2,
    stoppedS: 0,
    gapS: 0,
    distanceM: 10,
    elevationGainM: null,
    elevationLossM: null,
    netElevationM: null,
    averageHr: null,
    maxHr: null,
    rankMoving: 1,
    rankTotal: 1,
    segmentEffortCount: 8,
    doubts: [],
    ...extra,
  }
}

const TIMES = [
  '2026-09-30T14:00:00',
  '2026-09-30T14:00:01',
  '2026-09-30T14:00:02',
  '2026-09-30T14:00:03',
  '2026-09-30T14:00:04',
]

describe('utcMillis', () => {
  it('reads a stream time without an offset as UTC, not as local time', () => {
    expect(utcMillis('2026-09-30T14:00:00')).toBe(Date.UTC(2026, 8, 30, 14))
  })

  it('keeps an offset that is there', () => {
    expect(utcMillis('2026-09-30T16:00:00+02:00')).toBe(Date.UTC(2026, 8, 30, 14))
    expect(utcMillis('2026-09-30T14:00:00Z')).toBe(Date.UTC(2026, 8, 30, 14))
  })
})

describe('timedTrackPoints', () => {
  it('keeps the points that have a time and a position, in time order', () => {
    const track = stream([TIMES[2]!, TIMES[0]!, TIMES[1]!])
    track.waypoints.push({ time: null, lat: 61, lon: 6 })

    const points = timedTrackPoints([track])

    expect(points.map((point) => point.t)).toEqual(
      [0, 1, 2].map((s) => Date.UTC(2026, 8, 30, 14, 0, s)),
    )
  })
})

describe('stretchOf', () => {
  it('cuts the part between a pass given in local time out of a track stored in UTC', () => {
    const points = timedTrackPoints([stream(TIMES)])

    const stretch = stretchOf(points, '2026-09-30T16:00:01+02:00', '2026-09-30T16:00:03+02:00')

    expect(stretch).toEqual([
      { lat: 60.001, lng: 5.001 },
      { lat: 60.002, lng: 5.002 },
      { lat: 60.003, lng: 5.003 },
    ])
  })
})

describe('segmentHighlights', () => {
  const points = timedTrackPoints([stream(TIMES)])
  const label = (pass: SegmentEffort) => pass.segmentName

  it('gives the record a gold marker, the podium silver and bronze, and the rest none', () => {
    const colors = [1, 2, 3, 4].map(
      (rank) => segmentHighlights(points, [effort({ rankMoving: rank })], label)[0]?.markerColor,
    )

    expect(colors).toEqual(['#eab308', '#94a3b8', '#b45309', undefined])
  })

  it('gives no podium colour to the only pass of a segment', () => {
    const [highlight] = segmentHighlights(points, [effort({ segmentEffortCount: 1 })], label)

    expect(highlight?.markerColor).toBeUndefined()
    expect(highlight?.label).toBe('Løvstakken')
  })

  it('leaves out a pass that is not on this track', () => {
    const elsewhere = effort({
      startTime: '2026-10-01T10:00:00+02:00',
      endTime: '2026-10-01T10:30:00+02:00',
    })

    expect(segmentHighlights(points, [elsewhere], label)).toEqual([])
  })
})

describe('the Leaflet provider', () => {
  it('draws each highlight over the track with a labelled marker at its end', () => {
    drawn.length = 0
    const target = document.createElement('div')
    document.body.append(target)
    const track = [
      { lat: 60, lng: 5 },
      { lat: 60.01, lng: 5.01 },
      { lat: 60.02, lng: 5.02 },
    ]

    const map = createLeafletMapProvider().mount(target, {
      track: {
        points: track,
        highlights: [
          { points: track.slice(1), label: 'Løvstakken · PR, of 8', markerColor: '#eab308' },
        ],
      },
    })

    const lines = drawn.filter((layer) => layer.kind === 'polyline')
    const markers = drawn.filter((layer) => layer.kind === 'circleMarker')
    expect(lines).toHaveLength(2)
    expect(lines[1]?.tooltip).toBe('Løvstakken · PR, of 8')
    expect(markers.some((marker) => marker.options.fillColor === '#eab308')).toBe(true)
    map.destroy()
  })
})
