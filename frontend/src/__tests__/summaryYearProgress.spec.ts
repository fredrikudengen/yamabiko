import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { ChartRenderOptions, ChartSeries } from '@/composables/useChartProvider'
import type { ProgressDay } from '@/features/summary/types'

import i18n from '@/i18n'
import SummaryYearProgress from '@/features/summary/components/SummaryYearProgress.vue'

const rendered: ChartRenderOptions[] = []
const data = ref<ProgressDay[] | undefined>(undefined)

vi.mock('@/features/summary/composables/useSummary', () => ({
  useDailyProgressQuery: () => ({ data, isPending: ref(false) }),
}))
vi.mock('@/providers', () => ({ useRenderProvidersReady: () => ref(true) }))
vi.mock('@/composables/useChartProvider', () => ({
  useChartProvider: () => ({
    provider: {
      mount: (_target: HTMLElement, options: ChartRenderOptions) => {
        rendered.push(options)
        return {
          update: (next: ChartRenderOptions) => rendered.push(next),
          destroy: () => undefined,
        }
      },
    },
  }),
}))

function day(iso: string, climb: number): ProgressDay {
  return { day: iso, distance: 0, duration: 0, elevationGain: climb, activityCount: 1, newCells: 0 }
}

function mountIt(year = 2025) {
  rendered.length = 0
  return mount(SummaryYearProgress, {
    props: { year, typeCode: null, units: 'metric' },
    global: { plugins: [i18n] },
  })
}

describe('SummaryYearProgress', () => {
  it('draws the year strong on top of the earlier years, at most four of them', () => {
    data.value = ['2019', '2020', '2021', '2022', '2023', '2024', '2025'].map((year) =>
      day(`${year}-05-01`, 100),
    )
    mountIt(2025)

    const last = rendered[rendered.length - 1]
    expect(last?.series.map((series: ChartSeries) => series.label)).toEqual([
      '2021',
      '2022',
      '2023',
      '2024',
      '2025',
    ])
    expect(last?.series[last.series.length - 1]?.width).toBe(3)
    expect(last?.series.every((series: ChartSeries) => series.fill === false)).toBe(true)
    expect(last?.hoverAll).toBe(true)
  })

  it('compares a past year with the year before it at year end', () => {
    data.value = [day('2024-05-01', 900), day('2025-05-01', 1200)]
    const wrapper = mountIt(2025)

    const text = wrapper.find('[data-testid="summary-progress-comparison"]').text()
    expect(text).toContain('1,200 m')
    expect(text).toContain('900 m')
    expect(text).toContain('2024')
  })

  it('switches what it adds up', async () => {
    data.value = [day('2024-05-01', 900), day('2025-05-01', 1200)]
    const wrapper = mountIt(2025)

    await wrapper.find('[data-testid="summary-progress-metric"]').setValue('activityCount')

    expect(rendered[rendered.length - 1]?.valueFormat?.(2)).toBe('2')
    expect(wrapper.find('[data-testid="summary-progress-comparison"]').text()).toContain('1')
  })

  it('says so when the year has no activities', () => {
    data.value = [day('2024-05-01', 900)]

    expect(mountIt(2025).text()).toContain('No activities in 2025.')
  })
})
