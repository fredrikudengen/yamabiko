import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'

import type { GeoPoint } from '@/composables/useMapProvider'

import {
  PLAYBACK_DURATION_MS,
  pointAlong,
  useRoutePlayback,
} from '@/features/activities/composables/useRoutePlayback'

const ROUTE: GeoPoint[] = [
  { lat: 60, lng: 5 },
  { lat: 60.001, lng: 5 },
  { lat: 60.003, lng: 5 },
]

describe('pointAlong', () => {
  it('measures the share by distance, not by point count', () => {
    // The second stretch is twice the first, so halfway is past the middle point.
    const half = pointAlong(ROUTE, 0.5)!

    expect(half.lat).toBeCloseTo(60.0015, 6)
  })

  it('starts at the first point, ends at the last, and keeps within them', () => {
    expect(pointAlong(ROUTE, 0)).toEqual(ROUTE[0])
    expect(pointAlong(ROUTE, 1)!.lat).toBeCloseTo(60.003, 9)
    expect(pointAlong(ROUTE, 2)!.lat).toBeCloseTo(60.003, 9)
    expect(pointAlong([], 0.5)).toBeNull()
  })
})

describe('useRoutePlayback', () => {
  let now = 0
  let frames: FrameRequestCallback[] = []

  beforeEach(() => {
    now = 0
    frames = []
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      frames.push(callback)
      return frames.length
    })
    vi.stubGlobal('cancelAnimationFrame', () => {
      frames = []
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  /** Advances the clock and runs the frame the playback asked for. */
  function tick(ms: number) {
    now += ms
    const pending = frames
    frames = []
    pending.forEach((callback) => callback(now))
  }

  function mountPlayback(route: GeoPoint[] = ROUTE) {
    const seen: (GeoPoint | null)[] = []
    let controls!: ReturnType<typeof useRoutePlayback>
    const wrapper = mount(
      defineComponent({
        setup() {
          controls = useRoutePlayback(route, (point) => seen.push(point))
          return () => h('div')
        },
      }),
    )
    return { seen, controls, wrapper }
  }

  it('walks from the start to the end in the playback time, then lets go of the point', () => {
    const { seen, controls } = mountPlayback()

    controls.play()
    tick(0)
    tick(PLAYBACK_DURATION_MS / 2)
    expect(controls.playing.value).toBe(true)
    tick(PLAYBACK_DURATION_MS / 2)

    expect(seen[0]).toEqual(ROUTE[0])
    expect(seen[1]!.lat).toBeCloseTo(60.0015, 6)
    expect(seen[seen.length - 2]!.lat).toBeCloseTo(60.003, 9)
    expect(seen[seen.length - 1]).toBeNull()
    expect(controls.playing.value).toBe(false)
  })

  it('stops where it is when asked, and toggles', () => {
    const { seen, controls } = mountPlayback()

    controls.toggle()
    tick(1000)
    controls.toggle()

    expect(controls.playing.value).toBe(false)
    expect(seen[seen.length - 1]).toBeNull()
    expect(frames).toHaveLength(0)
  })

  it('does not play a route of one point', () => {
    const { controls } = mountPlayback([ROUTE[0]!])

    controls.play()

    expect(controls.playing.value).toBe(false)
  })

  it('stops when the page goes away', () => {
    const { controls, wrapper } = mountPlayback()
    controls.play()

    wrapper.unmount()

    expect(controls.playing.value).toBe(false)
  })
})
