import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import type { CoverageDto } from '@/features/coverageMap/types'

import i18n from '@/i18n'
import enActivities from '@/i18n/locales/en/activities.json'
import nbActivities from '@/i18n/locales/nb/activities.json'
import { apiFetch } from '@/services/http'
import CoverageLegend from '@/features/coverageMap/components/CoverageLegend.vue'
import {
  fetchCoverage,
  mapCoverage,
  refreshCoverage,
} from '@/features/coverageMap/services/coverage'
import { COVERAGE_BUCKETS } from '@/features/coverageMap/utils/scale'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const mocked = vi.mocked(apiFetch)

const DTO: CoverageDto = {
  zoom: 16,
  cells: [
    { x: 34_000, y: 19_000, count: 1 },
    { x: 34_001, y: 19_000, count: 7 },
  ],
  max_count: 7,
}

describe('the coverage service', () => {
  beforeEach(() => {
    mocked.mockReset()
  })

  it('asks for the cell size the page is showing', async () => {
    mocked.mockResolvedValue(DTO)

    await fetchCoverage(15)

    expect(mocked.mock.calls[0]?.[0]).toBe('/coverage?zoom=15')
  })

  it('turns the API shape into the UI shape without losing a cell', () => {
    const coverage = mapCoverage(DTO)

    expect(coverage.zoom).toBe(16)
    expect(coverage.maxCount).toBe(7)
    expect(coverage.cells).toEqual([
      { x: 34_000, y: 19_000, count: 1 },
      { x: 34_001, y: 19_000, count: 7 },
    ])
  })

  it('reads an empty map without inventing a highest count', () => {
    expect(mapCoverage({ zoom: 16, cells: [], max_count: 0 })).toEqual({
      zoom: 16,
      cells: [],
      maxCount: 0,
    })
  })

  it('rebuilds with a POST, since it writes', async () => {
    mocked.mockResolvedValue({ activities: 31, cells: 2400 })

    const result = await refreshCoverage()

    expect(mocked).toHaveBeenCalledWith('/coverage/refresh', { method: 'POST' })
    expect(result).toEqual({ activities: 31, cells: 2400 })
  })
})

describe('the coverage query keys', () => {
  it('cache each cell size on its own, so switching back does not refetch', () => {
    expect(queryKeys.coverage.grid(16)).not.toEqual(queryKeys.coverage.grid(17))
  })

  it('share a prefix the rebuild can invalidate in one go', () => {
    for (const zoom of [15, 16, 17]) {
      expect(queryKeys.coverage.grid(zoom).slice(0, 1)).toEqual([...queryKeys.coverage.all()])
    }
  })
})

/**
 * @param hex - A `#rrggbb` colour.
 * @returns The same colour as jsdom writes it back out of a style attribute.
 */
function rgbOf(hex: string): string {
  const value = Number.parseInt(hex.slice(1), 16)
  return `rgb(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255})`
}

describe('the legend', () => {
  const mountLegend = (maxCount: number) =>
    mount(CoverageLegend, { props: { maxCount }, global: { plugins: [i18n] } })

  it('names the range of each colour it shows', () => {
    const text = mountLegend(12).text()

    expect(text).toContain('1')
    expect(text).toContain('2–3')
    expect(text).toContain('4–9')
    expect(text).toContain('10+')
  })

  it('draws one swatch per colour in the scale', () => {
    const swatches = mountLegend(12).findAll('span[aria-hidden="true"]')

    expect(swatches).toHaveLength(COVERAGE_BUCKETS.length)
    // jsdom rewrites the hex colour as rgb(), so compare it that way.
    expect(swatches[0]?.attributes('style')).toContain(rgbOf(COVERAGE_BUCKETS[0]?.color ?? ''))
    expect(swatches[swatches.length - 1]?.attributes('style')).toContain(
      rgbOf(COVERAGE_BUCKETS[COVERAGE_BUCKETS.length - 1]?.color ?? ''),
    )
  })

  it('does not promise colours the map has no cells for', () => {
    expect(mountLegend(2).text()).not.toContain('10+')
  })

  it('disappears entirely on an empty map', () => {
    expect(mountLegend(0).text()).toBe('')
  })
})

describe('the Norwegian texts', () => {
  it('cover every key the page uses', () => {
    expect(Object.keys(nbActivities.coverage).sort()).toEqual(
      Object.keys(enActivities.coverage).sort(),
    )
  })
})

describe('the cell tooltip', () => {
  it('says one tour in the singular and counts in the plural', () => {
    const t = i18n.global.t.bind(i18n.global)

    expect(t('activities.coverage.cellTooltip', 1, { named: { count: '1' } })).toContain('1 tour')
    expect(t('activities.coverage.cellTooltip', 7, { named: { count: '7' } })).toContain('7 tours')
  })
})
