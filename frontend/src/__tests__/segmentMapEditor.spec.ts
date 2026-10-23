import { describe, expect, it, vi } from 'vitest'

import { ref } from 'vue'

import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import SegmentMapEditor from '@/features/segments/components/SegmentMapEditor.vue'

vi.mock('@/features/config/composables/useAppConfig', () => ({
  useAppConfig: () => ({
    config: ref({ map: { tileUrl: 'http://tiles.invalid/{z}/{x}/{y}.png', attribution: 'test' } }),
  }),
}))

function mountEditor(props: Record<string, unknown>) {
  return mount(SegmentMapEditor, {
    props: { start: null, end: null, placing: null, tracks: [], ...props },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
}

describe('SegmentMapEditor', () => {
  it('draws a pin and a radius handle for each placed node', async () => {
    const wrapper = mountEditor({
      start: { lat: 60.39, lon: 5.32, radiusM: 50 },
      end: { lat: 60.4, lon: 5.33, radiusM: 40 },
    })

    // Two pins and two radius handles are Leaflet markers.
    expect(wrapper.findAll('.leaflet-marker-icon')).toHaveLength(4)
    await wrapper.setProps({ end: null })
    expect(wrapper.findAll('.leaflet-marker-icon')).toHaveLength(2)
    wrapper.unmount()
  })

  it("keeps Leaflet's own classes on its container when placing mode changes", async () => {
    // Regression: a Vue :class binding on the Leaflet container wiped
    // `leaflet-container` on re-render, which greyed out the map after the end node was placed.
    const wrapper = mountEditor({ placing: 'end' })
    const container = wrapper.find('[role="application"]')
    expect(container.classes()).toContain('leaflet-container')

    await wrapper.setProps({ placing: null })
    expect(container.classes()).toContain('leaflet-container')
    expect(wrapper.classes()).not.toContain('segment-placing')

    await wrapper.setProps({ placing: 'start' })
    expect(container.classes()).toContain('leaflet-container')
    expect(wrapper.classes()).toContain('segment-placing')
    wrapper.unmount()
  })

  it('draws existing segments faintly and names them', async () => {
    const wrapper = mountEditor({
      others: [
        {
          id: 1,
          name: 'Old route',
          start: { lat: 60.39, lon: 5.32, radiusM: 50 },
          end: { lat: 60.4, lon: 5.33, radiusM: 50 },
          effortCount: 1,
          createdAt: '',
          updatedAt: '',
        },
      ],
    })

    // Two circles (start and end), each carrying the name as a hover tooltip; no permanent label.
    expect(wrapper.element.querySelectorAll('path.leaflet-interactive')).toHaveLength(2)
    expect(wrapper.element.querySelectorAll('.leaflet-tooltip')).toHaveLength(0)
    wrapper.unmount()
  })
})
