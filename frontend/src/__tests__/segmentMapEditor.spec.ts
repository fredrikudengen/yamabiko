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

  it('marks the map as clickable only while a node is being placed', async () => {
    const wrapper = mountEditor({ placing: 'start' })
    expect(wrapper.find('[role="application"]').classes()).toContain('cursor-crosshair')
    await wrapper.setProps({ placing: null })
    expect(wrapper.find('[role="application"]').classes()).not.toContain('cursor-crosshair')
    wrapper.unmount()
  })
})
