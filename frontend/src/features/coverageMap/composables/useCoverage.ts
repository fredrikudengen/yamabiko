import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { fetchCoverage, refreshCoverage } from '@/features/coverageMap/services/coverage'
import { queryKeys } from '@/services/queryKeys'

/**
 * The user's coverage at one cell size. Each zoom is cached on its own, so
 * switching cell size back and forth does not refetch.
 *
 * @param zoom - The grid to count at (a ref, getter or plain number).
 */
export function useCoverageQuery(zoom: MaybeRefOrGetter<number>) {
  return useQuery({
    queryKey: computed(() => queryKeys.coverage.grid(toValue(zoom))),
    queryFn: ({ signal }) => fetchCoverage(toValue(zoom), signal),
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
