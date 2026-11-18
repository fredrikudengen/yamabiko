import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount, RouterLinkStub } from '@vue/test-utils'

import type { SegmentSuggestion } from '@/features/segments/types'

import i18n from '@/i18n'
import SegmentSuggestions from '@/features/segments/components/SegmentSuggestions.vue'
import { fetchSegmentSuggestions } from '@/features/segments/services/segments'
import { nodeFromQuery } from '@/features/segments/utils/geo'
import { apiFetch } from '@/services/http'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const data = ref<SegmentSuggestion[] | undefined>(undefined)
const asked: number[] = []

vi.mock('@/features/segments/composables/useSegments', async () => {
  const { computed, toValue } = await import('vue')
  return {
    useSegmentSuggestionsQuery: (minTours: () => number) => {
      const threshold = computed(() => toValue(minTours))
      return {
        data: computed(() => {
          asked.push(threshold.value)
          return data.value
        }),
        isPending: ref(false),
        isError: ref(false),
      }
    },
  }
})

function suggestion(tours: number): SegmentSuggestion {
  return {
    key: `s${tours}`,
    tours: Array.from({ length: tours }, (_, i) => ({
      id: 100 + i,
      name: i === 0 ? null : `Tur ${i}`,
      startTime: `2026-0${i + 1}-15T08:00:00Z`,
    })),
    start: { lat: 59.83216, lon: 10.17767, radiusM: 50 },
    end: { lat: 59.83804, lon: 10.22013, radiusM: 50 },
    straightM: 2463,
  }
}

function mountCard() {
  return mount(SegmentSuggestions, {
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

describe('fetchSegmentSuggestions', () => {
  it('asks with the threshold and reads the ends as nodes', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([
      {
        key: 'abc',
        zoom: 17,
        cells: [[1, 2]],
        tours: [{ id: 5, name: 'Hytta', start_time: '2026-07-21T08:00:00Z' }],
        start: { lat: 59.8, lon: 10.1, radius_m: 50 },
        end: { lat: 59.9, lon: 10.2, radius_m: 50 },
        straight_m: 2463,
      },
    ])

    const [result] = await fetchSegmentSuggestions(2)

    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe('/segments/suggestions?min_tours=2')
    expect(result).toEqual({
      key: 'abc',
      tours: [{ id: 5, name: 'Hytta', startTime: '2026-07-21T08:00:00Z' }],
      start: { lat: 59.8, lon: 10.1, radiusM: 50 },
      end: { lat: 59.9, lon: 10.2, radiusM: 50 },
      straightM: 2463,
    })
  })
})

describe('SegmentSuggestions', () => {
  beforeEach(() => {
    asked.length = 0
  })

  it('lists each stretch with how often and how far, naming its newest tours', () => {
    data.value = [suggestion(5)]
    const wrapper = mountCard()

    const row = wrapper.find('[data-testid="suggestion"]')
    expect(row.text()).toContain('Walked 5 times · about 2.5 km as the crow flies')
    expect(row.text()).toContain('Unnamed tour')
    expect(row.text()).toContain('Tur 2')
    expect(row.text()).not.toContain('Tur 3')
    expect(row.text()).toContain('and 2 more')
  })

  it('opens the editor with the two ends placed', () => {
    data.value = [suggestion(3)]
    const wrapper = mountCard()

    const links = wrapper.findAllComponents(RouterLinkStub)
    const create = links[links.length - 1]!
    expect(create.props('to')).toEqual({
      name: 'segment-new',
      query: { start: '59.83216, 10.17767', end: '59.83804, 10.22013' },
    })
  })

  it('asks for three tours, and two once the box is ticked', async () => {
    data.value = []
    const wrapper = mountCard()
    expect(asked).toContain(3)

    await wrapper.find('[data-testid="suggestions-twice"]').setValue(true)

    expect(asked).toContain(2)
  })

  it('says so when there is nothing to suggest', () => {
    data.value = []

    expect(mountCard().find('[data-testid="suggestions-none"]').exists()).toBe(true)
  })
})

describe('nodeFromQuery', () => {
  it('reads a node from decimal degrees in the address', () => {
    expect(nodeFromQuery('59.83216, 10.17767', 50)).toEqual({
      lat: 59.83216,
      lon: 10.17767,
      radiusM: 50,
    })
  })

  it.each([
    undefined,
    ['59.8, 10.1'],
    '',
    '59.8',
    '59.8,',
    'abc, 10',
    '91, 10',
    '59.8, 181',
    '1, 2, 3',
  ])('reads nothing from %j', (value) => {
    expect(nodeFromQuery(value, 50)).toBeNull()
  })
})
