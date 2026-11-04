import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { CellRef, CellTour } from '@/features/coverageMap/types'

import i18n from '@/i18n'
import CoverageCellTours from '@/features/coverageMap/components/CoverageCellTours.vue'

const tours = ref<CellTour[] | undefined>(undefined)
const pending = ref(false)
const failed = ref(false)
let askedFor: unknown = null

vi.mock('@/features/coverageMap/composables/useCoverage', () => ({
  useCellToursQuery: (cell: () => CellRef) => {
    askedFor = cell()
    return { data: tours, isPending: pending, isError: failed }
  },
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/activity/:id', name: 'activity', component: { template: '<div />' } },
  ],
})

const CELL: CellRef = { x: 34_000, y: 19_000, zoom: 16 }

function mountList(list: CellTour[] = []) {
  tours.value = list
  pending.value = false
  failed.value = false
  return mount(CoverageCellTours, {
    props: { cell: CELL },
    attachTo: document.body,
    global: { plugins: [i18n, router] },
  })
}

describe('CoverageCellTours', () => {
  it('asks for the tours of the cell it was given', () => {
    const wrapper = mountList()

    expect(askedFor).toEqual(CELL)
    wrapper.unmount()
  })

  it('lists each tour by name and date, in the order the API gives', () => {
    const wrapper = mountList([
      { id: 12, name: 'Ulriken', startTime: '2026-10-20T07:00:00Z' },
      { id: 5, name: 'Fløyen', startTime: '2026-09-30T15:00:00Z' },
    ])

    const rows = wrapper.findAll('[data-testid="coverage-cell-tour"]')
    expect(rows.map((row) => row.text())).toEqual([
      expect.stringContaining('Ulriken'),
      expect.stringContaining('Fløyen'),
    ])
    expect(rows[0]?.text()).toContain('2026')
    wrapper.unmount()
  })

  it("links each tour's name to the tour's own page", () => {
    const wrapper = mountList([{ id: 12, name: 'Ulriken', startTime: '2026-10-20T07:00:00Z' }])

    expect(wrapper.find('a').attributes('href')).toBe('/activity/12')
    expect(wrapper.find('a').text()).toContain('Ulriken')
    wrapper.unmount()
  })

  it('names a tour without a name rather than leaving the link empty', () => {
    const wrapper = mountList([{ id: 3, name: null, startTime: '2026-10-20T07:00:00Z' }])

    expect(wrapper.find('a').text()).toContain('Untitled tour')
    wrapper.unmount()
  })

  it('says how many tours went through', () => {
    const wrapper = mountList([
      { id: 1, name: 'A', startTime: '2026-10-20T07:00:00Z' },
      { id: 2, name: 'B', startTime: '2026-10-21T07:00:00Z' },
    ])

    expect(wrapper.text()).toContain('2 tours here')
    wrapper.unmount()
  })

  it('shows an error instead of an empty list when the tours could not be loaded', () => {
    const wrapper = mountList()
    failed.value = true
    tours.value = undefined

    return wrapper.vm.$nextTick().then(() => {
      expect(wrapper.text()).toContain('Could not load the tours here.')
      wrapper.unmount()
    })
  })

  it('closes from its button and from Escape', async () => {
    const wrapper = mountList()

    await wrapper.find('button').trigger('click')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(wrapper.emitted('close')).toHaveLength(2)
    wrapper.unmount()
  })

  it('stops listening for Escape once it is gone', () => {
    const wrapper = mountList()
    wrapper.unmount()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
