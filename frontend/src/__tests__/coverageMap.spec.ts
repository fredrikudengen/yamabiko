import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { CellRef, CoverageCell } from '@/features/coverageMap/types'

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

const drawn: {
  bounds: unknown
  options: Record<string, unknown>
  shape: import('leaflet').Rectangle
}[] = []

vi.mock('leaflet', async (importOriginal) => {
  const leaflet = await importOriginal<typeof import('leaflet')>()
  return {
    ...leaflet,
    rectangle: (bounds: unknown, options: Record<string, unknown>) => {
      const shape = leaflet.rectangle(bounds as never, options as never)
      drawn.push({ bounds, options, shape })
      return shape
    },
  }
})

const CELLS: CoverageCell[] = [
  { x: 34_000, y: 19_000, count: 1 },
  { x: 34_001, y: 19_000, count: 3 },
  { x: 34_002, y: 19_000, count: 20 },
]

function mountMap(cells: CoverageCell[] = CELLS, zoom = 16, selected: CellRef | null = null) {
  drawn.length = 0
  return mount(CoverageMap, {
    props: { cells, zoom, tooltip: (count: number) => `${count}`, selected },
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

  it('reports a clicked cell with the grid it was drawn at', () => {
    const wrapper = mountMap()

    drawn[1]?.shape.fire('click')

    expect(wrapper.emitted('select')).toEqual([[{ x: 34_001, y: 19_000, zoom: 16 }]])
    wrapper.unmount()
  })

  it('outlines the picked cell on top of the cells, and lets clicks through', () => {
    const wrapper = mountMap(CELLS, 16, { x: 34_002, y: 19_000, zoom: 16 })

    const outline = drawn[drawn.length - 1]
    const box = cellBounds(34_002, 19_000, 16)
    expect(drawn).toHaveLength(CELLS.length + 1)
    expect(outline?.bounds).toEqual([
      [box.south, box.west],
      [box.north, box.east],
    ])
    expect(outline?.options).toMatchObject({ fill: false, interactive: false, weight: 2 })
    wrapper.unmount()
  })

  it('keeps the outline on top when the cells are redrawn at another size', async () => {
    const picked = { x: 34_002, y: 19_000, zoom: 16 }
    const wrapper = mountMap(CELLS, 16, picked)

    drawn.length = 0
    await wrapper.setProps({ zoom: 15 })

    // Same canvas: what is added last is painted last.
    expect(drawn).toHaveLength(CELLS.length + 1)
    expect(drawn[drawn.length - 1]?.options.interactive).toBe(false)
    const box = cellBounds(picked.x, picked.y, picked.zoom)
    expect(drawn[drawn.length - 1]?.bounds).toEqual([
      [box.south, box.west],
      [box.north, box.east],
    ])
    wrapper.unmount()
  })

  it('drops the outline when nothing is picked', async () => {
    const wrapper = mountMap(CELLS, 16, { x: 34_002, y: 19_000, zoom: 16 })

    drawn.length = 0
    await wrapper.setProps({ selected: null })

    expect(drawn).toHaveLength(0)
    wrapper.unmount()
  })

  it('reports the zoom once the map has settled, not before', () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountMap()

      expect(wrapper.emitted('zoom')).toBeUndefined()
      vi.advanceTimersByTime(300)
      const reported = wrapper.emitted<[number]>('zoom')
      expect(reported).toHaveLength(1)
      expect(typeof reported?.[0]?.[0]).toBe('number')
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports nothing after it is gone', () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountMap()
      wrapper.unmount()

      vi.advanceTimersByTime(300)
      expect(wrapper.emitted('zoom')).toBeUndefined()
    } finally {
      vi.useRealTimers()
    }
  })
})
