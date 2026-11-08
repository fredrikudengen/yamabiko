import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount, RouterLinkStub } from '@vue/test-utils'

import type { ActivityCells } from '@/features/coverageMap/types'

import i18n from '@/i18n'
import ActivityNewCells from '@/features/coverageMap/components/ActivityNewCells.vue'

const data = ref<ActivityCells | undefined>(undefined)

vi.mock('@/features/coverageMap/composables/useCoverage', () => ({
  useActivityCellsQuery: () => ({ data }),
}))

function mountIt() {
  return mount(ActivityNewCells, {
    props: { activityId: 4, latitude: 60.4 },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

describe('ActivityNewCells', () => {
  it('says in how many of the cells the tour was the first, and links to the map', () => {
    data.value = { zoom: 16, cells: 85, newCells: 12 }
    const wrapper = mountIt()

    expect(wrapper.text()).toContain('First time in 12 of 85 cells')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toEqual({ name: 'coverage' })
  })

  it('says so when the tour found no new ground', () => {
    data.value = { zoom: 16, cells: 85, newCells: 0 }

    expect(mountIt().text()).toContain('No new ground: you had been in all 85 cells before.')
  })

  it('shows nothing for a tour without cells, or before the counts arrive', () => {
    data.value = { zoom: 16, cells: 0, newCells: 0 }
    expect(mountIt().find('[data-testid="activity-new-cells"]').exists()).toBe(false)

    data.value = undefined
    expect(mountIt().find('[data-testid="activity-new-cells"]').exists()).toBe(false)
  })
})
