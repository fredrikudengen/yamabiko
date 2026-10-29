import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { CoverageCell } from '@/features/coverageMap/types'

import i18n from '@/i18n'
import CoverageMap from '@/features/coverageMap/components/CoverageMap.vue'
import { CELL_FILL_OPACITY, colorOf } from '@/features/coverageMap/utils/scale'
import { cellBounds } from '@/features/coverageMap/utils/tiles'

/**
 * jsdom has no canvas, and the cells are drawn on one. This has to run before
 * Leaflet is imported: Leaflet reads `requestAnimationFrame` off the window
 * once, at module load, so patching it later has no effect. Every 2D context
 * method becomes a no-op, which is enough — the test checks what was handed to
 * Leaflet, not what the pixels came out like — and frames run straight away so
 * a redraw cannot land after the map is torn down.
 */
vi.hoisted(() => {
  const context = new Proxy(
    {},
    {
      get: (target: Record<string, unknown>, property: string) =>
        property in target ? target[property] : () => undefined,
      set: (target: Record<string, unknown>, property: string, value: unknown) => {
        target[property] = value
        return true
      },
    },
  )
  HTMLCanvasElement.prototype.getContext = (() => context) as never
  window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
    callback(0)
    return 0
  }) as never
  window.cancelAnimationFrame = (() => undefined) as never
})

vi.mock('@/features/config/composables/useAppConfig', () => ({
  useAppConfig: () => ({
    config: ref({ map: { tileUrl: 'http://tiles.invalid/{z}/{x}/{y}.png', attribution: 'test' } }),
  }),
}))

const drawn: { bounds: unknown; options: Record<string, unknown> }[] = []

vi.mock('leaflet', async (importOriginal) => {
  const leaflet = await importOriginal<typeof import('leaflet')>()
  return {
    ...leaflet,
    rectangle: (bounds: unknown, options: Record<string, unknown>) => {
      drawn.push({ bounds, options })
      return leaflet.rectangle(bounds as never, options as never)
    },
  }
})

const CELLS: CoverageCell[] = [
  { x: 34_000, y: 19_000, count: 1 },
  { x: 34_001, y: 19_000, count: 3 },
  { x: 34_002, y: 19_000, count: 20 },
]

function mountMap(cells: CoverageCell[] = CELLS, zoom = 16) {
  drawn.length = 0
  return mount(CoverageMap, {
    props: { cells, zoom, tooltip: (count: number) => `${count}` },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
}

describe('CoverageMap', () => {
  it('draws one rectangle per cell', () => {
    const wrapper = mountMap()

    expect(drawn).toHaveLength(CELLS.length)
    wrapper.unmount()
  })

  it('puts each rectangle on the box its cell covers', () => {
    const wrapper = mountMap()

    const box = cellBounds(34_000, 19_000, 16)
    expect(drawn[0]?.bounds).toEqual([
      [box.south, box.west],
      [box.north, box.east],
    ])
    wrapper.unmount()
  })

  it('colours each rectangle by how many tours went through it', () => {
    const wrapper = mountMap()

    expect(drawn.map((shape) => shape.options.fillColor)).toEqual([
      colorOf(1),
      colorOf(3),
      colorOf(20),
    ])
    wrapper.unmount()
  })

  it('leaves the cells without an outline, so neighbours read as one area', () => {
    const wrapper = mountMap()

    expect(drawn.every((shape) => shape.options.weight === 0)).toBe(true)
    expect(drawn.every((shape) => shape.options.fillOpacity === CELL_FILL_OPACITY)).toBe(true)
    wrapper.unmount()
  })

  it('shares one canvas renderer between the cells instead of one each', () => {
    const wrapper = mountMap()

    expect(new Set(drawn.map((shape) => shape.options.renderer)).size).toBe(1)
    wrapper.unmount()
  })

  it('redraws from scratch when the cell size changes', async () => {
    const wrapper = mountMap()

    drawn.length = 0
    await wrapper.setProps({ zoom: 15 })

    expect(drawn).toHaveLength(CELLS.length)
    const box = cellBounds(34_000, 19_000, 15)
    expect(drawn[0]?.bounds).toEqual([
      [box.south, box.west],
      [box.north, box.east],
    ])
    wrapper.unmount()
  })

  it("keeps Leaflet's own classes on its container", () => {
    const wrapper = mountMap()

    expect(wrapper.find('[role="application"]').classes()).toContain('leaflet-container')
    wrapper.unmount()
  })

  it('draws nothing on an empty map without falling over', () => {
    const wrapper = mountMap([])

    expect(drawn).toHaveLength(0)
    wrapper.unmount()
  })
})
