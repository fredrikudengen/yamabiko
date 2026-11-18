import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { NO_COVERAGE_FILTER, type CellRef, type CoverageFilter } from '@/features/coverageMap/types'

import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import {
  fetchActivityCells,
  fetchCellTours,
  fetchCoverage,
  refreshCoverage,
} from '@/features/coverageMap/services/coverage'
import { queryKeys } from '@/services/queryKeys'

/**
 * The user's coverage at one cell size. Each zoom is cached on its own, so
 * switching cell size back and forth does not refetch.
 *
 * The previous grid stays in `data` while a new one loads, so zooming the map
 * does not swap it for a loading placeholder. Draw with `data.zoom`, not the
 * zoom asked for: until the new grid arrives they differ.
 *
 * @param zoom - The grid to count at (a ref, getter or plain number).
 */
export function useCoverageQuery(
  zoom: MaybeRefOrGetter<number>,
  filter: MaybeRefOrGetter<CoverageFilter> = NO_COVERAGE_FILTER,
) {
  return useQuery({
    queryKey: computed(() => {
      const { year, activityType } = toValue(filter)
      return queryKeys.coverage.grid(toValue(zoom), year, activityType)
    }),
    queryFn: ({ signal }) => fetchCoverage(toValue(zoom), signal, toValue(filter)),
    placeholderData: keepPreviousData,
    staleTime: 10 * 60 * 1000,
  })
}

/**
 * The tours that passed through a picked cell. Idle while nothing is picked.
 *
 * @param cell - The picked cell, or `null`.
 */
export function useCellToursQuery(
  cell: MaybeRefOrGetter<CellRef | null>,
  filter: MaybeRefOrGetter<CoverageFilter> = NO_COVERAGE_FILTER,
) {
  return useQuery({
    queryKey: computed(() => {
      const picked = toValue(cell)
      const { year, activityType } = toValue(filter)
      return picked
        ? queryKeys.coverage.cell(picked.zoom, picked.x, picked.y, year, activityType)
        : queryKeys.coverage.cell(0, 0, 0)
    }),
    queryFn: ({ signal }) => fetchCellTours(toValue(cell) as CellRef, signal, toValue(filter)),
    enabled: computed(() => toValue(cell) !== null),
    staleTime: 10 * 60 * 1000,
  })
}

/**
 * How many cells a tour passed through, and how many of them were new. Idle
 * until `enabled` holds, so it is not asked for tours the viewer does not own.
 *
 * @param activityId - The tour.
 * @param zoom - The grid to count at.
 * @param enabled - Whether to fetch.
 */
export function useActivityCellsQuery(
  activityId: MaybeRefOrGetter<number>,
  zoom: MaybeRefOrGetter<number>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.coverage.activity(toValue(activityId), toValue(zoom))),
    queryFn: ({ signal }) => fetchActivityCells(toValue(activityId), toValue(zoom), signal),
    enabled: computed(() => toValue(enabled)),
    staleTime: 10 * 60 * 1000,
  })
}

/** Rebuild the grid from every activity, then refetch every cell size. */
export function useRefreshCoverageMutation() {
  return useInvalidatingMutation({
    mutationKey: queryKeys.coverage.all(),
    mutationFn: () => refreshCoverage(),
  })
}
