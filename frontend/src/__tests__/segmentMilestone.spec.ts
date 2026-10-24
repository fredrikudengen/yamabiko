import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { mount } from '@vue/test-utils'

import type { SegmentEffort } from '@/features/segments/types'

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
  ...extra,
})

describe('milestoneOf', () => {
  const ranked = effort(1, { rankMoving: 1, rankTotal: 3, segmentEffortCount: 8 })

  it('reads the rank for the chosen basis', () => {
    expect(milestoneOf(ranked, 'moving')).toEqual({ rank: 1, count: 8, isPr: true })
    expect(milestoneOf(ranked, 'total')).toEqual({ rank: 3, count: 8, isPr: false })
  })

  it('says nothing when the segment has a single pass', () => {
    expect(milestoneOf(effort(1), 'moving')).toBeNull()
    expect(milestoneOf(effort(1), 'total')).toBeNull()
  })

  it('words a record as "PR, of 8" and the rest as "2 of 8"', () => {
    expect(milestoneText({ rank: 1, count: 8, isPr: true })).toEqual({
      key: 'activities.segments.milestone.pr',
      values: { count: 8 },
    })
    expect(milestoneText({ rank: 2, count: 8, isPr: false })).toEqual({
      key: 'activities.segments.milestone.rank',
      values: { rank: 2, count: 8 },
    })
    expect(i18n.global.t('activities.segments.milestone.pr', { count: 8 })).toBe('PR, of 8')
    expect(i18n.global.t('activities.segments.milestone.rank', { rank: 2, count: 8 })).toBe(
      '2 of 8',
    )
  })
})

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
      matcher_version: 1,
      details: null,
    })
    expect([mapped.rankMoving, mapped.rankTotal, mapped.segmentEffortCount]).toEqual([2, 4, 8])
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

  it('shows no standing for a segment with a single pass', () => {
    cardEfforts.value = [effort(1)]

    const wrapper = mountCard()

    expect(wrapper.find('[data-testid="activity-segments"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="activity-milestone"]').exists()).toBe(false)
  })
})
