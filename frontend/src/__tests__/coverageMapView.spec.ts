import { describe, expect, it, vi } from 'vitest'
import { defineComponent, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { mount } from '@vue/test-utils'

import type { Coverage } from '@/features/coverageMap/types'

import i18n from '@/i18n'
import CoverageMapView from '@/features/coverageMap/views/CoverageMapView.vue'
import { AUTO_ZOOM_OFFSET } from '@/features/coverageMap/utils/tiles'

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
}))

/** Stands in for the Leaflet map: records what it is given and can report a zoom. */
const MapStub = defineComponent({
  name: 'CoverageMap',
  props: { cells: Array, zoom: Number, tooltip: Function },
  emits: ['zoom'],
  setup: () => ({ fitAll: () => undefined }),
  template: '<div />',
})

function grid(zoom: number): Coverage {
  return { zoom, cells: [{ x: 1, y: 1, count: 1 }], maxCount: 1 }
}

function mountView() {
  return mount(CoverageMapView, {
    global: { plugins: [i18n], stubs: { CoverageMap: MapStub } },
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

    await wrapper.find('select').setValue('17')
    wrapper.findComponent(MapStub).vm.$emit('zoom', 9)
    await wrapper.vm.$nextTick()

    expect(toValue(askedZoom)).toBe(17)
    wrapper.unmount()
  })

  it('offers "auto" first and starts on it', () => {
    data.value = grid(16)
    const wrapper = mountView()

    const select = wrapper.find('select').element as HTMLSelectElement
    expect(select.options[0]?.value).toBe('auto')
    expect(select.value).toBe('auto')
    wrapper.unmount()
  })
})
