import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { storeToRefs } from 'pinia'

import type { DateRange, GarminLoginInput } from '@/features/integrations/types'

import { useAuthStore } from '@/features/auth/stores/auth'
import { queryKeys } from '@/services/queryKeys'
import {
  linkGarmin,
  retrieveGarminActivities,
  retrieveGarminGear,
  retrieveGarminHealth,
  submitGarminMfa,
  unlinkGarmin,
} from '@/features/integrations/services/garmin'
import {
  fetchGoogleHealthStatus,
  startGoogleHealthLink,
  syncGoogleHealth,
  unlinkGoogleHealth,
} from '@/features/integrations/services/googleHealth'
import {
  retrieveStravaActivities,
  retrieveStravaGear,
  unlinkStrava,
} from '@/features/integrations/services/strava'

/**
 * Returns a callback that invalidates the self-profile so the integration link
 * status (read from `useProfileQuery`) refreshes after a link/unlink.
 */
function useProfileInvalidation(): () => void {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: queryKeys.profile.all() })
  }
}

/** Imports Strava activities for a date window (background task on the server). */
export function useRetrieveStravaActivitiesMutation() {
  return useMutation<void, Error, DateRange>({
    mutationFn: (range) => retrieveStravaActivities(range),
  })
}

/** Imports the user's Strava gear (background task on the server). */
export function useRetrieveStravaGearMutation() {
  return useMutation<void, Error, void>({ mutationFn: () => retrieveStravaGear() })
}

/** Disconnects Strava and refreshes the profile link status. */
export function useUnlinkStravaMutation() {
  const invalidateProfile = useProfileInvalidation()
  return useMutation<void, Error, void>({
    mutationFn: () => unlinkStrava(),
    onSuccess: invalidateProfile,
  })
}

/**
 * Links a Garmin Connect account. The request may stay pending until an MFA
 * code is supplied (see {@link useSubmitGarminMfaMutation}); on success it
 * refreshes the profile link status.
 */
export function useLinkGarminMutation() {
  const invalidateProfile = useProfileInvalidation()
  return useMutation<void, Error, GarminLoginInput>({
    mutationFn: (input) => linkGarmin(input),
    onSuccess: invalidateProfile,
  })
}

/** Submits a Garmin Connect MFA code, unblocking a pending link request. */
export function useSubmitGarminMfaMutation() {
  return useMutation<void, Error, string>({ mutationFn: (code) => submitGarminMfa(code) })
}

/** Imports Garmin Connect activities for a date window (background task). */
export function useRetrieveGarminActivitiesMutation() {
  return useMutation<void, Error, DateRange>({
    mutationFn: (range) => retrieveGarminActivities(range),
  })
}

/** Imports the user's Garmin Connect gear (background task). */
export function useRetrieveGarminGearMutation() {
  return useMutation<void, Error, void>({ mutationFn: () => retrieveGarminGear() })
}

/** Imports Garmin Connect health data for a date window (background task). */
export function useRetrieveGarminHealthMutation() {
  return useMutation<void, Error, DateRange>({
    mutationFn: (range) => retrieveGarminHealth(range),
  })
}

/** Disconnects Garmin Connect and refreshes the profile link status. */
export function useUnlinkGarminMutation() {
  const invalidateProfile = useProfileInvalidation()
  return useMutation<void, Error, void>({
    mutationFn: () => unlinkGarmin(),
    onSuccess: invalidateProfile,
  })
}

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
