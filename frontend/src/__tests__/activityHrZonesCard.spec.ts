import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { HrZoneBucket } from '@/features/activities/types'

import enActivities from '@/i18n/locales/en/activities.json'
import nbActivities from '@/i18n/locales/nb/activities.json'
import i18n from '@/i18n'
import ActivityHrZones from '@/features/activities/components/ActivityHrZones.vue'
import { useHrZoneLimits } from '@/features/activities/composables/useHrZoneLimits'
import { DEFAULT_HR_ZONE_LIMITS, toZoneBuckets } from '@/features/activities/utils/hrZoneTime'

const BUCKETS: HrZoneBucket[] = toZoneBuckets(
  { seconds: [3600, 1200, 600, 300, 60], countedS: 5760, stoppedS: 0, gapS: 0 },
  DEFAULT_HR_ZONE_LIMITS,
)

function mountCard(props: { basis?: 'moving' | 'recorded'; countedS?: number } = {}) {
  return mount(ActivityHrZones, {
    props: { zones: BUCKETS, ...props },
    global: { plugins: [i18n] },
  })
}

const button = (wrapper: ReturnType<typeof mountCard>, label: string) =>
  wrapper.findAll('button').find((b) => b.text() === label)!

describe('ActivityHrZones with computed zones', () => {
  beforeEach(() => {
    useHrZoneLimits().resetLimits()
  })

  it('shows the time and share in each zone, what they cover and the total', () => {
    const wrapper = mountCard({ basis: 'moving', countedS: 5760 })
    const text = wrapper.text()

    expect(text).toContain('1:00:00') // zone 1
    expect(text).toContain('20:00') // zone 2
    expect(text).toContain('63%') // 3600 / 5760 = 62.5 %, rounded
    expect(text).toContain('< 103')
    expect(text).toContain('≥ 154')
    expect(text).toContain('Moving time, long stops left out')
    expect(text).toContain('Total 1:36:00')
  })

  it('says it is the whole recording when no stops are recorded', () => {
    const text = mountCard({ basis: 'recorded', countedS: 5760 }).text()

    expect(text).toContain('Whole recording')
    expect(text).not.toContain('long stops left out')
  })

  it('edits the limits: shows the current ones, rejects bad ones, stores good ones', async () => {
    const wrapper = mountCard({ basis: 'moving', countedS: 5760 })
    await button(wrapper, 'Edit limits').trigger('click')

    const inputs = wrapper.findAll('input')
    expect(inputs.map((i) => i.element.value)).toEqual(['103', '113', '126', '154'])

    // Out of order: nothing is stored and the reason is shown.
    await inputs[1]!.setValue('100')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.text()).toContain('Each limit must be higher than the one before.')
    expect(useHrZoneLimits().limits.value).toEqual(DEFAULT_HR_ZONE_LIMITS)

    // Valid: stored, shared, and the editor closes.
    await inputs[1]!.setValue('115')
    await wrapper.find('form').trigger('submit')
    expect(useHrZoneLimits().limits.value).toEqual([103, 115, 126, 154])
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('Custom limits')
  })

  it('resets to the defaults', async () => {
    useHrZoneLimits().setLimits([100, 120, 140, 160])
    const wrapper = mountCard({ basis: 'moving', countedS: 5760 })
    await button(wrapper, 'Edit limits').trigger('click')
    await button(wrapper, 'Reset to default').trigger('click')

    expect(useHrZoneLimits().limits.value).toEqual(DEFAULT_HR_ZONE_LIMITS)
    expect(wrapper.findAll('input').map((i) => i.element.value)).toEqual([
      '103',
      '113',
      '126',
      '154',
    ])
  })
})

describe('ActivityHrZones with the server zones', () => {
  it('shows shares only, with no caption and no limit editor, as before', () => {
    const wrapper = mountCard()
    const text = wrapper.text()

    expect(text).not.toContain('Edit limits')
    expect(text).not.toContain('Moving time')
    expect(text).not.toContain('1:00:00')
    expect(text).toContain('63%')
  })
})

describe('hrZones texts', () => {
  it('has every English key in Norwegian too', () => {
    const keys = (o: Record<string, unknown>, prefix = ''): string[] =>
      Object.entries(o).flatMap(([k, v]) =>
        v && typeof v === 'object'
          ? keys(v as Record<string, unknown>, `${prefix}${k}.`)
          : [`${prefix}${k}`],
      )
    expect(keys(nbActivities.hrZones).sort()).toEqual(keys(enActivities.hrZones).sort())
  })
})
