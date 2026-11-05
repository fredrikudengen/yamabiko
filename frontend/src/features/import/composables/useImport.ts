import { useMutation } from '@tanstack/vue-query'

import { bulkImportActivities, importStravaActivities } from '@/features/import/services/import'

/** Bulk-imports activity files from the server's bulk-import folder (background). */
export function useBulkImportMutation() {
  return useMutation<void, Error, void>({ mutationFn: () => bulkImportActivities() })
}

/** Queues activities from a Strava bulk export for import (background). */
export function useImportStravaActivitiesMutation() {
  return useMutation<void, Error, void>({ mutationFn: () => importStravaActivities() })
}
