import type { Coverage, CoverageDto, CoverageRefresh } from '@/features/coverageMap/types'

import { apiFetch } from '@/services/http'

/**
 * @param dto - The grid from the API.
 * @returns The grid in UI shape.
 */
export function mapCoverage(dto: CoverageDto): Coverage {
  return {
    zoom: dto.zoom,
    cells: dto.cells.map((cell) => ({ x: cell.x, y: cell.y, count: cell.count })),
    maxCount: dto.max_count,
  }
}

/**
 * Where the user has been, counted per cell.
 *
 * @param zoom - The grid to count at; coarser zooms gather more tours per cell.
 * @param signal - Optional abort signal.
 * @returns The cells with at least one tour through them.
 */
export async function fetchCoverage(zoom: number, signal?: AbortSignal): Promise<Coverage> {
  return mapCoverage(await apiFetch<CoverageDto>(`/coverage?zoom=${zoom}`, { signal }))
}

/**
 * Rebuild the grid from every activity the user owns. Needed after an import
 * that did not go through the hook, such as a Strava file.
 *
 * @returns How many activities were recomputed and how many cells they cover.
 */
export async function refreshCoverage(): Promise<CoverageRefresh> {
  return apiFetch<CoverageRefresh>('/coverage/refresh', { method: 'POST' })
}
