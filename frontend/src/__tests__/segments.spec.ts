import { beforeEach, describe, expect, it, vi } from 'vitest'

import { mount } from '@vue/test-utils'

import type { NearMiss, PreviewMatch, SegmentEffort, SegmentNode } from '@/features/segments/types'

import i18n from '@/i18n'
import { apiFetch } from '@/services/http'
import EffortsTable from '@/features/segments/components/EffortsTable.vue'
import SegmentPreviewList from '@/features/segments/components/SegmentPreviewList.vue'
import {
  createSegment,
  fetchActivityEfforts,
  fetchActivityTrack,
  mapSegment,
  parseCoordinates,
  previewSegment,
  thinTrack,
} from '@/features/segments/services/segments'
import { compareEfforts } from '@/features/segments/utils/efforts'
import {
  clampRadius,
  distanceM,
  formatCoordinates,
  formatSeconds,
  nodeProblem,
  nodesOverlap,
  offsetEast,
} from '@/features/segments/utils/geo'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const node = (lat: number, lon: number, radiusM = 50): SegmentNode => ({ lat, lon, radiusM })

describe('segment geo helpers', () => {
  it('measures a degree of latitude as about 111 km', () => {
    expect(distanceM([60, 5], [61, 5])).toBeGreaterThan(111_000)
    expect(distanceM([60, 5], [61, 5])).toBeLessThan(111_400)
    expect(distanceM([60, 5], [60, 5])).toBe(0)
  })

  it('places the radius handle exactly one radius east of the centre', () => {
    const centre: [number, number] = [60.39, 5.32]
    expect(distanceM(centre, offsetEast(centre, 80))).toBeCloseTo(80, 1)
  })

  it('flags overlapping circles and small radii like the server does', () => {
    const a = node(60, 5, 60)
    const farAway = node(60.01, 5, 60)
    const touching = node(...offsetEast([60, 5], 100), 60)

    expect(nodesOverlap(a, touching)).toBe(true)
    expect(nodeProblem(a, touching)).toBe('overlap')
    expect(nodeProblem(a, farAway)).toBeNull()
    expect(nodeProblem(node(60, 5, 25), farAway)).toBe('radius_too_small')
    expect(nodeProblem(node(60, 5, 26), farAway)).toBeNull()
  })

  it('keeps a dragged radius inside what the server accepts', () => {
    expect(clampRadius(3)).toBe(26)
    expect(clampRadius(25)).toBe(26)
    expect(clampRadius(61.6)).toBe(62)
    expect(clampRadius(999_999)).toBe(2000)
    expect(clampRadius(Number.NaN)).toBe(26)
  })

  it('writes coordinates latitude first and durations as m:ss or h:mm:ss', () => {
    expect(formatCoordinates({ lat: 60.39, lon: 5.32 })).toBe('60.39000, 5.32000')
    expect(formatSeconds(31 * 60 + 6)).toBe('31:06')
    expect(formatSeconds(3725)).toBe('1:02:05')
    expect(formatSeconds(-4)).toBe('0:00')
  })
})

describe('segments service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  const segmentDto = {
    id: 3,
    name: 'To the top',
    start: { lat: 1, lon: 2, radius_m: 50 },
    end: { lat: 3, lon: 4, radius_m: 40 },
    effort_count: 2,
    created_at: '2026-10-23T10:00:00',
    updated_at: '2026-10-23T10:00:00',
  }

  it('maps the wire shape to the UI shape', () => {
    expect(mapSegment(segmentDto)).toEqual({
      id: 3,
      name: 'To the top',
      start: { lat: 1, lon: 2, radiusM: 50 },
      end: { lat: 3, lon: 4, radiusM: 40 },
      effortCount: 2,
      createdAt: '2026-10-23T10:00:00',
      updatedAt: '2026-10-23T10:00:00',
    })
  })

  it('creates with snake_case nodes and returns the similar-segment hint', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      ...segmentDto,
      similar_segments: [{ id: 9, name: 'Almost the same' }],
    })

    const saved = await createSegment({
      name: 'To the top',
      start: node(1, 2, 50),
      end: node(3, 4, 40),
    })

    const [url, options] = vi.mocked(apiFetch).mock.calls[0] ?? []
    expect(url).toBe('/segments')
    expect(options?.method).toBe('POST')
    expect(JSON.parse(options?.body as string)).toEqual({
      name: 'To the top',
      start: { lat: 1, lon: 2, radius_m: 50 },
      end: { lat: 3, lon: 4, radius_m: 40 },
    })
    expect(saved.similarSegments).toEqual([{ id: 9, name: 'Almost the same' }])
  })

  it('maps a preview with matches, near misses and closest approach', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      matches: [
        {
          activity_id: 7,
          activity_name: 'Hike',
          start_time: '2026-10-20T08:12:00',
          end_time: '2026-10-20T08:43:06',
          elapsed_s: 1866,
          moving_s: 1866,
          stopped_s: 0,
          gap_s: 0,
          distance_m: 2400,
          elevation_gain_m: 255,
          elevation_loss_m: 4,
          net_elevation_m: 251,
          average_hr: 105,
          max_hr: 140,
          start_visits: 1,
          end_visits: 2,
          closest_start_m: 12.2,
          closest_end_m: 8.7,
          start_visit_times: ['2026-10-20T08:12:00'],
          end_visit_times: ['2026-10-20T08:43:00', '2026-10-20T08:50:00'],
        },
      ],
      near_misses: [
        {
          activity_id: 8,
          activity_name: null,
          start_time: '2026-10-01T08:00:00',
          reason: 'end_not_reached',
          closest_start_m: 5,
          closest_end_m: 83.4,
        },
      ],
      similar_segments: [],
    })

    const preview = await previewSegment(node(1, 2), node(3, 4))

    const [url, options] = vi.mocked(apiFetch).mock.calls[0] ?? []
    expect(url).toBe('/segments/preview')
    expect(JSON.parse(options?.body as string).start).toEqual({ lat: 1, lon: 2, radius_m: 50 })
    expect(preview.matches[0]).toMatchObject({
      activityId: 7,
      movingS: 1866,
      endVisits: 2,
      closestEndM: 8.7,
    })
    expect(preview.nearMisses[0]).toMatchObject({ reason: 'end_not_reached', closestEndM: 83.4 })
  })

  it('reads a coordinate pair through the server parser', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ lat: 60.39, lon: 5.32 })

    await expect(parseCoordinates('60,39; 5,32')).resolves.toEqual({ lat: 60.39, lon: 5.32 })
    const [url, options] = vi.mocked(apiFetch).mock.calls[0] ?? []
    expect(url).toBe('/segments/parse-coordinates')
    expect(JSON.parse(options?.body as string)).toEqual({ text: '60,39; 5,32' })
  })

  it('asks for the efforts of one activity', async () => {
    vi.mocked(apiFetch).mockResolvedValue([])
    await fetchActivityEfforts(12)
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe('/segments/activities/12/efforts')
  })

  it('thins a long track but keeps both ends', () => {
    const track: [number, number][] = Array.from({ length: 2000 }, (_, i) => [i, i])
    const thin = thinTrack(track, 400)

    expect(thin).toHaveLength(400)
    expect(thin[0]).toEqual([0, 0])
    expect(thin[399]).toEqual([1999, 1999])
    expect(thinTrack(track.slice(0, 10), 400)).toHaveLength(10)
  })

  it('builds a track from GPS waypoints and tolerates an activity without GPS', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      stream_waypoints: [
        { lat: 1, lon: 2 },
        { lat: null, lon: 3 },
        { lat: 4, lon: 5 },
      ],
    })
    await expect(fetchActivityTrack(5)).resolves.toEqual({
      activityId: 5,
      points: [
        [1, 2],
        [4, 5],
      ],
    })

    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    await expect(fetchActivityTrack(6)).resolves.toEqual({ activityId: 6, points: [] })
  })
})

const effort = (id: number, startTime: string, movingS: number, extra = {}): SegmentEffort => ({
  id,
  segmentId: 1,
  segmentName: 'To the top',
  activityId: id + 100,
  activityName: 'Hike',
  startTime,
  endTime: startTime,
  elapsedS: movingS,
  movingS,
  stoppedS: 0,
  gapS: 0,
  distanceM: 2000,
  elevationGainM: 250,
  elevationLossM: 0,
  netElevationM: 250,
  averageHr: 110,
  maxHr: 140,
  ...extra,
})

describe('comparing efforts', () => {
  it('orders newest first and measures each against the fastest moving time', () => {
    const rows = compareEfforts([
      effort(1, '2026-10-01T08:00:00', 2000),
      effort(2, '2026-10-20T08:00:00', 1866),
      effort(3, '2026-10-10T08:00:00', 1900),
    ])

    expect(rows.map((r) => r.effort.id)).toEqual([2, 3, 1])
    expect(rows.map((r) => r.behindBestS)).toEqual([0, 34, 134])
    expect(rows.map((r) => r.isBest)).toEqual([true, false, false])
    expect(compareEfforts([])).toEqual([])
  })

  it('can rank by total time, where stops count against an effort', () => {
    // The user's point: a tour with many rests has lower moving time but is not faster overall.
    const restful = effort(1, '2026-10-01T08:00:00', 2000, { elapsedS: 2900, stoppedS: 900 })
    const steady = effort(2, '2026-10-20T08:00:00', 2300, { elapsedS: 2300 })

    const byMoving = compareEfforts([restful, steady], 'moving')
    expect(byMoving.find((r) => r.isBest)?.effort.id).toBe(1)

    const byTotal = compareEfforts([restful, steady], 'total')
    expect(byTotal.find((r) => r.isBest)?.effort.id).toBe(2)
    expect(byTotal.find((r) => !r.isBest)?.behindBestS).toBe(600)
  })

  it('shows total time and switches the ranking with the toggle', async () => {
    const wrapper = mount(EffortsTable, {
      props: {
        efforts: [
          effort(1, '2026-10-01T08:00:00', 2000, { elapsedS: 2900, stoppedS: 900 }),
          effort(2, '2026-10-20T08:00:00', 2300, { elapsedS: 2300 }),
        ],
      },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })
    const badgeRow = () =>
      wrapper
        .findAll('[data-testid="effort-row"]')
        .findIndex((r) => r.find('[data-testid="best-badge"]').exists())

    expect(wrapper.text()).toContain('48:20') // 2900 s total
    // Rows are newest first: index 0 is the steady tour, index 1 the restful one.
    expect(badgeRow()).toBe(1)

    await wrapper.find('[data-testid="basis-total"]').trigger('click')
    expect(badgeRow()).toBe(0)
  })

  it('shows the best badge only when there is something to compare with', () => {
    const mountTable = (efforts: SegmentEffort[]) =>
      mount(EffortsTable, {
        props: { efforts },
        global: { plugins: [i18n], stubs: { 'router-link': true } },
      })

    expect(
      mountTable([effort(1, '2026-10-01T08:00:00', 2000)])
        .find('[data-testid="best-badge"]')
        .exists(),
    ).toBe(false)

    const wrapper = mountTable([
      effort(1, '2026-10-01T08:00:00', 2000),
      effort(2, '2026-10-20T08:00:00', 1866, { stoppedS: 90, averageHr: null }),
    ])
    expect(wrapper.findAll('[data-testid="effort-row"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-testid="best-badge"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('31:06')
    expect(wrapper.text()).toContain('+2:14')
    expect(wrapper.text()).toContain('1:30')
  })
})

describe('SegmentPreviewList', () => {
  const match: PreviewMatch = {
    activityId: 7,
    activityName: 'Hike',
    startTime: '2026-10-20T08:12:00',
    endTime: '2026-10-20T08:43:06',
    elapsedS: 1866,
    movingS: 1866,
    stoppedS: 0,
    gapS: 0,
    distanceM: 2400,
    elevationGainM: 255,
    netElevationM: 251,
    averageHr: 105,
    maxHr: 140,
    startVisits: 1,
    endVisits: 2,
    closestStartM: 12.2,
    closestEndM: 8.7,
    endVisitTimes: [],
  }
  const miss: NearMiss = {
    activityId: 8,
    activityName: null,
    startTime: '2026-10-01T08:00:00',
    reason: 'end_not_reached',
    closestStartM: 5,
    closestEndM: 83.4,
  }

  const mountList = (props: Record<string, unknown>) =>
    mount(SegmentPreviewList, {
      props: { matches: [], nearMisses: [], similar: [], loading: false, blocked: null, ...props },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })

  it('shows time, heart rate, ascent and the radius that would just catch the tour', () => {
    const wrapper = mountList({ matches: [match] })
    const text = wrapper.find('[data-testid="preview-match"]').text()

    expect(text).toContain('31:06')
    expect(text).toContain('105')
    expect(text).toContain('+255 m')
    expect(text).toContain('13 m') // 12.2 rounded up
    expect(text).toContain('9 m') // 8.7 rounded up
  })

  it('points out a second visit to the end, which is what made the earlier count 2', () => {
    expect(
      mountList({ matches: [match] })
        .find('[data-testid="preview-multi-visit"]')
        .exists(),
    ).toBe(true)
    expect(
      mountList({ matches: [{ ...match, endVisits: 1 }] })
        .find('[data-testid="preview-multi-visit"]')
        .exists(),
    ).toBe(false)
  })

  it('lists near misses with the reason and the distance that was missed by', () => {
    const wrapper = mountList({ nearMisses: [miss] })
    const text = wrapper.find('[data-testid="preview-near-miss"]').text()

    expect(text).toContain('Missed the end circle')
    expect(text).toContain('84 m')
  })

  it('shows only the blocking reason when the nodes cannot be previewed', () => {
    const wrapper = mountList({ blocked: 'Place both a start and an end', matches: [match] })

    expect(wrapper.text()).toContain('Place both a start and an end')
    expect(wrapper.find('[data-testid="preview-match"]').exists()).toBe(false)
  })

  it('warns about similar segments without blocking', () => {
    const wrapper = mountList({ similar: [{ id: 1, name: 'Old route' }] })
    expect(wrapper.text()).toContain('Old route')
  })
})
