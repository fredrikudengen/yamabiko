import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { mount } from '@vue/test-utils'

import type { SegmentEffort, SegmentEffortDto } from '@/features/segments/types'

import i18n from '@/i18n'
import ActivitySegments from '@/features/segments/components/ActivitySegments.vue'
import EffortsTable from '@/features/segments/components/EffortsTable.vue'
import { mapEffort } from '@/features/segments/services/segments'
import { compareEfforts } from '@/features/segments/utils/efforts'
import { milestoneOf, milestoneText } from '@/features/segments/utils/milestone'

const cardEfforts = ref<SegmentEffort[]>([])
vi.mock('@/features/segments/composables/useSegments', () => ({
  useActivityEffortsQuery: () => ({ data: cardEfforts }),
}))

const effort = (id: number, extra: Partial<SegmentEffort> = {}): SegmentEffort => ({
  id,
  segmentId: 1,
  segmentName: 'To the top',
  activityId: id + 100,
  activityName: 'Hike',
  source: 'google_health',
  startTime: `2026-10-${String(id).padStart(2, '0')}T08:00:00`,
  endTime: `2026-10-${String(id).padStart(2, '0')}T08:30:00`,
  elapsedS: 1800,
  movingS: 1700,
  stoppedS: 0,
  gapS: 0,
  distanceM: 2000,
  elevationGainM: 250,
  elevationLossM: 0,
  netElevationM: 250,
  averageHr: 110,
  maxHr: 140,
  rankMoving: 1,
  rankTotal: 1,
  segmentEffortCount: 1,
  doubts: [],
  ...extra,
})

describe('milestoneOf', () => {
  const ranked = effort(1, { rankMoving: 1, rankTotal: 3, segmentEffortCount: 8 })

  it('reads the rank for the chosen basis', () => {
    expect(milestoneOf(ranked, 'moving')).toEqual({
      rank: 1,
      count: 8,
      isPr: true,
      doubtful: false,
    })
    expect(milestoneOf(ranked, 'total')).toEqual({
      rank: 3,
      count: 8,
      isPr: false,
      doubtful: false,
    })
  })

  it('marks the standing of a pass whose time may be off', () => {
    const doubted = effort(1, { rankMoving: 1, segmentEffortCount: 8, doubts: ['start_edge'] })

    expect(milestoneOf(doubted, 'moving')?.doubtful).toBe(true)
  })

  it('says nothing when the segment has a single pass', () => {
    expect(milestoneOf(effort(1), 'moving')).toBeNull()
    expect(milestoneOf(effort(1), 'total')).toBeNull()
  })

  it('words a record as "PR, of 8" and the rest as "2 of 8"', () => {
    expect(milestoneText({ rank: 1, count: 8, isPr: true, doubtful: false })).toEqual({
      key: 'activities.segments.milestone.pr',
      values: { count: 8 },
    })
    expect(milestoneText({ rank: 2, count: 8, isPr: false, doubtful: true })).toEqual({
      key: 'activities.segments.milestone.rank',
      values: { rank: 2, count: 8 },
    })
    expect(milestoneText({ rank: 1, count: 8, isPr: true, doubtful: true })).toEqual({
      key: 'activities.segments.milestone.prDoubtful',
      values: { count: 8 },
    })
    expect(i18n.global.t('activities.segments.milestone.pr', { count: 8 })).toBe('PR, of 8')
    expect(i18n.global.t('activities.segments.milestone.prDoubtful', { count: 8 })).toBe(
      'PR?, of 8',
    )
    expect(i18n.global.t('activities.segments.milestone.rank', { rank: 2, count: 8 })).toBe(
      '2 of 8',
    )
  })
})

function dtoOf(): SegmentEffortDto {
  return {
    id: 1,
    segment_id: 2,
    segment_name: 'Top',
    activity_id: 3,
    activity_name: 'Hike',
    source: 'strava',
    start_time: '2026-10-01T08:00:00',
    end_time: '2026-10-01T08:30:00',
    elapsed_s: 1800,
    moving_s: 1700,
    stopped_s: 0,
    gap_s: 0,
    distance_m: 2000,
    elevation_gain_m: 250,
    elevation_loss_m: 0,
    net_elevation_m: 250,
    average_hr: 170,
    max_hr: 190,
    rank_moving: 2,
    rank_total: 4,
    segment_effort_count: 8,
    doubts: [],
    matcher_version: 2,
    details: null,
  }
}

describe('mapEffort', () => {
  it('carries the server ranks', () => {
    const mapped = mapEffort({
      id: 1,
      segment_id: 2,
      segment_name: 'Top',
      activity_id: 3,
      activity_name: 'Hike',
      source: 'strava',
      start_time: '2026-10-01T08:00:00',
      end_time: '2026-10-01T08:30:00',
      elapsed_s: 1800,
      moving_s: 1700,
      stopped_s: 0,
      gap_s: 0,
      distance_m: 2000,
      elevation_gain_m: 250,
      elevation_loss_m: 0,
      net_elevation_m: 250,
      average_hr: 170,
      max_hr: 190,
      rank_moving: 2,
      rank_total: 4,
      segment_effort_count: 8,
      doubts: [],
      matcher_version: 1,
      details: null,
    })
    expect([mapped.rankMoving, mapped.rankTotal, mapped.segmentEffortCount]).toEqual([2, 4, 8])
    expect(mapped.doubts).toEqual([])
  })

  it('carries the reasons to doubt a time, leaving out any it does not know', () => {
    const mapped = mapEffort({ ...dtoOf(), doubts: ['gps_gap', 'from_the_future', 'end_edge'] })

    expect(mapped.doubts).toEqual(['gps_gap', 'end_edge'])
  })
})

describe('best time and the server ranking agree', () => {
  it('treats times that show the same to the second as tied for best', () => {
    const rows = compareEfforts([
      effort(1, { movingS: 1800.2 }),
      effort(2, { movingS: 1799.8 }),
      effort(3, { movingS: 1801.6 }),
    ])
    expect(rows.map((r) => r.isBest)).toEqual([false, true, true])
  })
})

describe('EffortsTable ranks', () => {
  it('ranks by moving time until the toggle is switched', async () => {
    const wrapper = mount(EffortsTable, {
      props: {
        efforts: [
          effort(1, { rankMoving: 1, rankTotal: 2, segmentEffortCount: 3 }),
          effort(2, { rankMoving: 3, rankTotal: 3, segmentEffortCount: 3 }),
          effort(3, { rankMoving: 2, rankTotal: 1, segmentEffortCount: 3 }),
        ],
      },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })
    const ranks = () => wrapper.findAll('[data-testid="effort-rank"]').map((c) => c.text())

    // Newest first: efforts 3, 2, 1.
    expect(ranks()).toEqual(['2 of 3', '3 of 3', 'PR, of 3'])

    await wrapper.find('[data-testid="basis-total"]').trigger('click')
    expect(ranks()).toEqual(['PR, of 3', '3 of 3', '2 of 3'])
  })

  it('marks a doubtful pass in its rank cell, and only that one', () => {
    const wrapper = mount(EffortsTable, {
      props: {
        efforts: [
          effort(1, { rankMoving: 1, segmentEffortCount: 2, doubts: ['gps_gap'] }),
          effort(2, { rankMoving: 2, segmentEffortCount: 2 }),
        ],
      },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })
    const cells = wrapper.findAll('[data-testid="effort-rank"]')

    // Newest first: effort 2, then effort 1.
    expect(cells[0]?.find('[data-testid="effort-doubt"]').exists()).toBe(false)
    expect(cells[1]?.text()).toContain('PR?, of 2')
    expect(cells[1]?.find('[data-testid="effort-doubt"]').attributes('title')).toContain(
      'GPS signal dropped out',
    )
  })
})

describe('ActivitySegments card', () => {
  const mountCard = () =>
    mount(ActivitySegments, {
      props: { activityId: 7 },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })

  it('shows the standing by moving time next to each segment', () => {
    cardEfforts.value = [
      effort(1, { segmentName: 'To the top', rankMoving: 1, rankTotal: 4, segmentEffortCount: 8 }),
      effort(2, { segmentName: 'Halfway', rankMoving: 3, rankTotal: 1, segmentEffortCount: 5 }),
    ]

    const texts = mountCard()
      .findAll('[data-testid="activity-milestone"]')
      .map((m) => m.text())

    expect(texts).toEqual(['PR, of 8', '3 of 5'])
  })

  it('marks a doubtful pass and asks whether its record holds', () => {
    cardEfforts.value = [
      effort(1, { rankMoving: 1, segmentEffortCount: 8, doubts: ['start_edge'] }),
      effort(2, { segmentName: 'Halfway', rankMoving: 3, segmentEffortCount: 5 }),
    ]

    const wrapper = mountCard()
    const badges = wrapper.findAll('[data-testid="effort-doubt"]')

    expect(wrapper.find('[data-testid="activity-milestone"]').text()).toBe('PR?, of 8')
    expect(badges).toHaveLength(1)
    expect(badges[0]?.text()).toBe('Uncertain')
    expect(badges[0]?.attributes('title')).toContain('edge of the start circle')
  })

  it('shows no standing for a segment with a single pass', () => {
    cardEfforts.value = [effort(1)]

    const wrapper = mountCard()

    expect(wrapper.find('[data-testid="activity-segments"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="activity-milestone"]').exists()).toBe(false)
  })
})

describe('notes beside the times', () => {
  it('shows the tour note under its date in the table, and nothing for a tour without one', () => {
    const wrapper = mount(EffortsTable, {
      props: {
        efforts: [
          effort(1, { activityNotes: 'Snø over 400 m, tung sekk' }),
          effort(2, { activityNotes: null }),
        ],
      },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })

    const notes = wrapper.findAll('[data-testid="effort-notes"]')
    expect(notes).toHaveLength(1)
    expect(notes[0]?.text()).toBe('Snø over 400 m, tung sekk')
    expect(notes[0]?.attributes('title')).toBe('Snø over 400 m, tung sekk')
  })

  it('reads the note from the API, and no note when the field is missing', () => {
    expect(mapEffort({ ...dtoOf(), activity_notes: 'Med Clara' }).activityNotes).toBe('Med Clara')
    expect(mapEffort(dtoOf()).activityNotes).toBeNull()
  })
})
