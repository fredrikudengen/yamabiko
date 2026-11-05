import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { storeToRefs } from 'pinia'

import { useAuthStore } from '@/features/auth/stores/auth'
import { queryKeys } from '@/services/queryKeys'
import {
  fetchGoogleHealthStatus,
  startGoogleHealthLink,
  syncGoogleHealth,
  unlinkGoogleHealth,
} from '@/features/integrations/services/googleHealth'

/** The Google Health link status for the current user. */
export function useGoogleHealthStatusQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  return useQuery({
    queryKey: queryKeys.googleHealth.status(),
    queryFn: ({ signal }) => fetchGoogleHealthStatus(signal),
    enabled: isAuthenticated,
  })
}

/** Gets Google's consent URL; the caller redirects the browser to it. */
export function useStartGoogleHealthLinkMutation() {
  return useMutation<string, Error, void>({ mutationFn: () => startGoogleHealthLink() })
}

/** Imports the last N days of Google Health exercises (background task). */
export function useSyncGoogleHealthMutation() {
  return useMutation<void, Error, number>({ mutationFn: (days) => syncGoogleHealth(days) })
}

/** Disconnects Google Health and refreshes its status. */
export function useUnlinkGoogleHealthMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, void>({
    mutationFn: () => unlinkGoogleHealth(),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.googleHealth.status() })
    },
  })
}
