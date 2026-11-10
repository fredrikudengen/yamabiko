import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { EffortProfile, SegmentEffort } from '@/features/segments/types'

import i18n from '@/i18n'
import EffortSplitCard from '@/features/segments/components/EffortSplitCard.vue'
import { apiFetch } from '@/services/http'
import { fetchEffortProfile } from '@/features/segments/services/segments'
import {
  STRETCH_STEPS,
  behindAlongTheWay,
  biggestStretches,
} from '@/features/segments/utils/splits'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

/** A clock at 101 shares, running at `perStep` seconds a hundredth, with `extra` added from `from` on. */
function clock(perStep: number, extra = 0, from = 101): number[] {
  return Array.from({ length: 101 }, (_, index) => index * perStep + (index >= from ? extra : 0))
}

function profile(effortId: number, moving: number[], elapsed = moving): EffortProfile {
  return { effortId, distanceM: 2000, movingS: moving, elapsedS: elapsed }
}

describe('fetchEffortProfile', () => {
  it('asks for one pass of a segment and reads the clocks', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      effort_id: 5,
      distance_m: 2033,
      elapsed_s: [0, 20],
      moving_s: [0, 18],
    })

    const result = await fetchEffortProfile(3, 5)

    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe('/segments/3/efforts/5/profile')
    expect(result).toEqual({ effortId: 5, distanceM: 2033, elapsedS: [0, 20], movingS: [0, 18] })
  })
})

describe('behindAlongTheWay', () => {
  it('is the gap between the clocks at each share, on the chosen basis', () => {
    const best = profile(1, clock(20), clock(25))
    const mine = profile(2, clock(21), clock(20))

    expect(behindAlongTheWay(mine, best, 'moving')[100]).toBe(100)
    expect(behindAlongTheWay(mine, best, 'total')[100]).toBe(-500)
    expect(behindAlongTheWay(mine, best, 'moving')[0]).toBe(0)
  })
})

describe('biggestStretches', () => {
  it('finds where the most time went, and where the most came back', () => {
    // Even until 30 %, 90 s lost between 30 % and 40 %, 40 s won back between 70 % and 80 %.
    const behind = Array.from({ length: 101 }, (_, index) => {
      const lost = Math.min(Math.max(index - 30, 0), STRETCH_STEPS) * 9
      const won = Math.min(Math.max(index - 70, 0), STRETCH_STEPS) * 4
      return lost - won
    })

    const { lost, won } = biggestStretches(behind)

    expect(lost).toEqual({ fromPct: 30, toPct: 40, seconds: 90 })
    expect(won).toEqual({ fromPct: 70, toPct: 80, seconds: -40 })
  })

  it('has nothing to say about a pass that kept level all the way', () => {
    expect(biggestStretches(Array.from({ length: 101 }, () => 0))).toEqual({
      lost: null,
      won: null,
    })
  })
})

const profiles = new Map<number, EffortProfile>()
const rendered: ChartRenderOptions[] = []

vi.mock('@/features/segments/composables/useSegments', async () => {
  const { computed, toValue } = await import('vue')
  return {
    useEffortProfileQuery: (_segment: unknown, effortId: () => number | null) => {
      const id = computed(() => toValue(effortId))
      return {
        data: computed(() => {
          return id.value === null ? undefined : profiles.get(id.value)
        }),
        isPending: ref(false),
        isError: ref(false),
        refetch: () => undefined,
      }
    },
  }
})
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

function effort(id: number, day: number, movingS: number, elapsedS = movingS): SegmentEffort {
  return {
    id,
    segmentId: 3,
    segmentName: 'Løvstakken',
    activityId: id + 100,
    activityName: 'Tur',
    source: 'google_health',
    startTime: `2026-10-${String(day).padStart(2, '0')}T08:00:00`,
    endTime: `2026-10-${String(day).padStart(2, '0')}T09:00:00`,
    elapsedS,
    movingS,
    stoppedS: 0,
    gapS: 0,
    distanceM: 2000,
    elevationGainM: null,
    elevationLossM: null,
    netElevationM: null,
    averageHr: null,
    maxHr: null,
    rankMoving: 1,
    rankTotal: 1,
    segmentEffortCount: 3,
    doubts: [],
  }
}

describe('EffortSplitCard', () => {
  const efforts = [effort(1, 1, 2100), effort(2, 5, 2000, 2600), effort(3, 9, 2200, 2200)]

  function mountCard() {
    rendered.length = 0
    profiles.clear()
    profiles.set(1, profile(1, clock(21), clock(21)))
    profiles.set(2, profile(2, clock(20), clock(26)))
    profiles.set(3, profile(3, clock(22, 0), clock(22)))
    return mount(EffortSplitCard, {
      props: { segmentId: 3, efforts },
      global: { plugins: [i18n] },
    })
  }

  it('compares the newest pass with the fastest one by default', () => {
    const wrapper = mountCard()

    const options = wrapper
      .findAll('[data-testid="split-pick"] option')
      .map((o) => (o.element as HTMLOptionElement).value)
    expect(options).toEqual(['3', '1'])
    expect(wrapper.find('[data-testid="split-summary"]').text()).toContain('At the finish: +3:20.')
    const last = rendered[rendered.length - 1]
    expect(last?.series[0]?.data[100]).toBe(200)
    expect(last?.labels?.[50]).toBe('50 %')
  })

  it('takes the fastest on total time as the best when the basis is switched', async () => {
    const wrapper = mountCard()

    await wrapper.find('[data-testid="split-basis-total"]').trigger('click')

    // On total time pass 1 (2100) is fastest, so the newest pass is compared with it.
    const options = wrapper
      .findAll('[data-testid="split-pick"] option')
      .map((o) => (o.element as HTMLOptionElement).value)
    expect(options).toEqual(['3', '2'])
    expect(wrapper.find('[data-testid="split-summary"]').text()).toContain('At the finish: +1:40.')
  })

  it('shows nothing for a segment with a single pass', () => {
    const wrapper = mount(EffortSplitCard, {
      props: { segmentId: 3, efforts: [effort(1, 1, 2000)] },
      global: { plugins: [i18n] },
    })

    expect(wrapper.find('[data-testid="effort-split"]').exists()).toBe(false)
  })
})
