import { describe, expect, it, vi } from 'vitest'
import { defineComponent, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { mount } from '@vue/test-utils'

import type { Coverage, CoverageCell } from '@/features/coverageMap/types'

import i18n from '@/i18n'
import CoverageMapView from '@/features/coverageMap/views/CoverageMapView.vue'
import { AUTO_ZOOM_OFFSET } from '@/features/coverageMap/utils/tiles'
import { NEW_CELL_COLOR, OLD_CELL_COLOR, colorOf } from '@/features/coverageMap/utils/scale'

/**
 * The query is replaced by a ref the test fills by hand, so it can hold the
 * previous grid while a new zoom is asked for, as `keepPreviousData` does.
 */
let askedZoom: MaybeRefOrGetter<number> = 0
const data = ref<Coverage | undefined>(undefined)

vi.mock('@/features/coverageMap/composables/useCoverage', () => ({
  useCoverageQuery: (zoom: MaybeRefOrGetter<number>) => {
    askedZoom = zoom
    return {
      data,
      isPending: ref(false),
      isError: ref(false),
      refetch: () => undefined,
    }
  },
  useRefreshCoverageMutation: () => ({ isPending: ref(false), mutate: () => undefined }),
  useCellToursQuery: () => ({ data: ref([]), isPending: ref(false), isError: ref(false) }),
}))

/** Stands in for the Leaflet map: records what it is given and can report a zoom. */
const MapStub = defineComponent({
  name: 'CoverageMap',
  props: { cells: Array, zoom: Number, tooltip: Function, color: Function, selected: Object },
  emits: ['zoom', 'select'],
  setup: () => ({ fitAll: () => undefined }),
  template: '<div />',
})

/** Stands in for the list of tours, so the test sees which cell it was given. */
const ToursStub = defineComponent({
  name: 'CoverageCellTours',
  props: { cell: Object },
  emits: ['close'],
  template: '<div data-testid="tours" />',
})

function grid(zoom: number): Coverage {
  return {
    zoom,
    cells: [
      { x: 1, y: 1, count: 1, firstVisit: '2025-06-01T08:00:00' },
      { x: 2, y: 1, count: 3, firstVisit: '2026-03-14T08:00:00' },
      { x: 3, y: 1, count: 2, firstVisit: '2026-07-01T08:00:00' },
    ],
    maxCount: 3,
  }
}

function mountView() {
  return mount(CoverageMapView, {
    global: { plugins: [i18n], stubs: { CoverageMap: MapStub, CoverageCellTours: ToursStub } },
  })
}

describe('CoverageMapView', () => {
  it('asks for the grid that follows the map once the map reports its zoom', async () => {
    data.value = grid(16)
    const wrapper = mountView()

    expect(toValue(askedZoom)).toBe(16)
    wrapper.findComponent(MapStub).vm.$emit('zoom', 9)
    await wrapper.vm.$nextTick()

    expect(toValue(askedZoom)).toBe(9 + AUTO_ZOOM_OFFSET)
    wrapper.unmount()
  })

  it('draws the cells on screen at their own zoom while a new size loads', async () => {
    data.value = grid(16)
    const wrapper = mountView()

    wrapper.findComponent(MapStub).vm.$emit('zoom', 9)
    await wrapper.vm.$nextTick()

    // The new grid has not arrived: the map must keep drawing the old one at 16.
    expect(wrapper.findComponent(MapStub).props('zoom')).toBe(16)
    data.value = grid(9 + AUTO_ZOOM_OFFSET)
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(MapStub).props('zoom')).toBe(9 + AUTO_ZOOM_OFFSET)
    wrapper.unmount()
  })

  it('keeps a fixed cell size however the map is zoomed', async () => {
    data.value = grid(16)
    const wrapper = mountView()

    await wrapper.find('[data-testid="coverage-cell-size"]').setValue('17')
    wrapper.findComponent(MapStub).vm.$emit('zoom', 9)
    await wrapper.vm.$nextTick()

    expect(toValue(askedZoom)).toBe(17)
    wrapper.unmount()
  })

  it('offers "auto" first and starts on it', () => {
    data.value = grid(16)
    const wrapper = mountView()

    const select = wrapper.find('[data-testid="coverage-cell-size"]').element as HTMLSelectElement
    expect(select.options[0]?.value).toBe('auto')
    expect(select.value).toBe('auto')
    wrapper.unmount()
  })

  it('lists the tours of a clicked cell and outlines it, until closed', async () => {
    data.value = grid(16)
    const wrapper = mountView()
    const picked = { x: 34_001, y: 19_000, zoom: 16 }

    expect(wrapper.findComponent(ToursStub).exists()).toBe(false)
    wrapper.findComponent(MapStub).vm.$emit('select', picked)
    await wrapper.vm.$nextTick()

    expect(wrapper.findComponent(ToursStub).props('cell')).toEqual(picked)
    expect(wrapper.findComponent(MapStub).props('selected')).toEqual(picked)

    wrapper.findComponent(ToursStub).vm.$emit('close')
    await wrapper.vm.$nextTick()

    expect(wrapper.findComponent(ToursStub).exists()).toBe(false)
    expect(wrapper.findComponent(MapStub).props('selected')).toBeNull()
    wrapper.unmount()
  })

  it('offers tour counts first, then each year cells were first visited in, newest first', () => {
    data.value = grid(16)
    const wrapper = mountView()

    const select = wrapper.find('[data-testid="coverage-mode"]').element as HTMLSelectElement
    expect([...select.options].map((option) => option.value)).toEqual(['tours', '2026', '2025'])
    expect(select.value).toBe('tours')
    wrapper.unmount()
  })

  it('colours by tour count until a year is picked, then by whether a cell was new that year', async () => {
    data.value = grid(16)
    const wrapper = mountView()
    const cells = data.value.cells
    const colors = () =>
      cells.map((cell) =>
        (wrapper.findComponent(MapStub).props('color') as (cell: CoverageCell) => string)(cell),
      )

    expect(colors()).toEqual([colorOf(1), colorOf(3), colorOf(2)])
    await wrapper.find('[data-testid="coverage-mode"]').setValue('2026')

    expect(colors()).toEqual([OLD_CELL_COLOR, NEW_CELL_COLOR, NEW_CELL_COLOR])
    expect(wrapper.text()).toContain('2026')
    expect(wrapper.text()).toMatch(/\b2\b.*2026/)
    wrapper.unmount()
  })
})
