import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import type { SegmentEffort } from '@/features/segments/types'

import i18n from '@/i18n'
import enActivities from '@/i18n/locales/en/activities.json'
import nbActivities from '@/i18n/locales/nb/activities.json'
import EffortsTable from '@/features/segments/components/EffortsTable.vue'
import { beatsPer100mOf, climbRateOf, MIN_NET_CLIMB_M } from '@/features/segments/utils/climb'

const effort = (id: number, extra: Partial<SegmentEffort> = {}): SegmentEffort => ({
  id,
  segmentId: 1,
  segmentName: 'To the top',
  activityId: id + 100,
  activityName: 'Hike',
  source: 'google_health',
  startTime: `2026-10-${String(id).padStart(2, '0')}T08:00:00`,
  endTime: `2026-10-${String(id).padStart(2, '0')}T08:30:00`,
  elapsedS: 4000,
  movingS: 3600,
  stoppedS: 400,
  gapS: 0,
  distanceM: 2000,
  elevationGainM: 520,
  elevationLossM: 0,
  netElevationM: 500,
  averageHr: 120,
  maxHr: 140,
  rankMoving: 1,
  rankTotal: 1,
  segmentEffortCount: 1,
  ...extra,
})

describe('climbRateOf', () => {
  it('is the net climb per hour of the chosen time', () => {
    // 500 m in an hour of moving time; the same climb over 4000 s of clock time is slower.
    expect(climbRateOf(effort(1), 'moving')).toBeCloseTo(500, 6)
    expect(climbRateOf(effort(1), 'total')).toBeCloseTo(450, 6)
  })

  it('uses the net climb, not the summed ascent', () => {
    // 520 m of summed ascent on a 500 m net climb: a smoothed height track overstates the ascent.
    expect(climbRateOf(effort(1, { elevationGainM: 900 }), 'moving')).toBeCloseTo(500, 6)
  })

  it('says nothing for a descent, a tiny climb, missing height or no time', () => {
    expect(climbRateOf(effort(1, { netElevationM: -300 }), 'moving')).toBeNull()
    expect(climbRateOf(effort(1, { netElevationM: MIN_NET_CLIMB_M - 0.1 }), 'moving')).toBeNull()
    expect(climbRateOf(effort(1, { netElevationM: MIN_NET_CLIMB_M }), 'moving')).not.toBeNull()
    expect(climbRateOf(effort(1, { netElevationM: null }), 'moving')).toBeNull()
    expect(climbRateOf(effort(1, { movingS: 0 }), 'moving')).toBeNull()
  })
})

describe('beatsPer100mOf', () => {
  it('is heart rate times moving minutes over the net climb', () => {
    // 120 bpm for 60 min = 7200 beats over 500 m = 1440 per 100 m.
    expect(beatsPer100mOf(effort(1))).toBeCloseTo(1440, 6)
  })

  it('uses moving time whatever the clock time is', () => {
    expect(beatsPer100mOf(effort(1, { elapsedS: 9000, stoppedS: 5400 }))).toBeCloseTo(1440, 6)
  })

  it('is lower for the same climb on a lower heart rate and in less time', () => {
    const fitter = effort(2, { averageHr: 110, movingS: 3300 })
    expect(beatsPer100mOf(fitter)!).toBeLessThan(beatsPer100mOf(effort(1))!)
  })

  it('says nothing without heart rate, time or enough climb', () => {
    expect(beatsPer100mOf(effort(1, { averageHr: null }))).toBeNull()
    expect(beatsPer100mOf(effort(1, { averageHr: 0 }))).toBeNull()
    expect(beatsPer100mOf(effort(1, { movingS: 0 }))).toBeNull()
    expect(beatsPer100mOf(effort(1, { netElevationM: 10 }))).toBeNull()
    expect(beatsPer100mOf(effort(1, { netElevationM: null }))).toBeNull()
  })
})

describe('EffortsTable climb columns', () => {
  const mountTable = (efforts: SegmentEffort[]) =>
    mount(EffortsTable, {
      props: { efforts },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })
  const texts = (wrapper: ReturnType<typeof mountTable>, id: string) =>
    wrapper.findAll(`[data-testid="${id}"]`).map((cell) => cell.text())

  it('shows both numbers per pass, newest first, with dashes where they do not apply', () => {
    const wrapper = mountTable([
      effort(1),
      effort(2, { netElevationM: 10, averageHr: null }),
      effort(3, { averageHr: null }),
    ])

    expect(texts(wrapper, 'effort-climb-rate')).toEqual(['500 m/h', '–', '500 m/h'])
    expect(texts(wrapper, 'effort-beats')).toEqual(['–', '–', '1440'])
  })

  it('follows the Moving/Total toggle for the climb rate but not for the beats', async () => {
    const wrapper = mountTable([effort(1)])

    expect(texts(wrapper, 'effort-climb-rate')).toEqual(['500 m/h'])
    await wrapper.find('[data-testid="basis-total"]').trigger('click')
    expect(texts(wrapper, 'effort-climb-rate')).toEqual(['450 m/h'])
    expect(texts(wrapper, 'effort-beats')).toEqual(['1440'])
  })

  it('has a header and a tooltip for each column in both languages', () => {
    // nb is loaded lazily and `t` would fall back to English, so read the files themselves.
    const files = { en: enActivities, nb: nbActivities }
    for (const [locale, file] of Object.entries(files)) {
      const fields = file.segments.fields as Record<string, string>
      for (const key of [
        'climbRate',
        'climbRateUnit',
        'climbRateTooltip',
        'beats',
        'beatsTooltip',
      ]) {
        expect(fields[key], `${locale}.${key}`).toBeTruthy()
      }
    }
  })
})
