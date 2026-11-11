/**
 * The written feedback on a tour: a few sentences from Claude about how the
 * tour stands, made from the numbers the app has computed. The feature is off
 * when the server has no API key, and only the tour's owner sees it.
 */
import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { apiFetch } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'

/** The feedback as the API sends it. */
export interface ActivityFeedbackDto {
  enabled: boolean
  pending: boolean
  text: string | null
  model: string | null
  created_at: string | null
}

/** The feedback on one tour, or why there is none. */
export interface ActivityFeedback {
  /** False when the server has no API key: show nothing at all. */
  enabled: boolean
  /** The tour was just imported and its text is being written. */
  pending: boolean
  text: string | null
  /** When the text was written (ISO); it describes the tour as it stood then. */
  createdAt: string | null
}

/** How often to look again while a new tour's text is being written. */
export const PENDING_POLL_MS = 4000

function mapFeedback(dto: ActivityFeedbackDto): ActivityFeedback {
  return { enabled: dto.enabled, pending: dto.pending, text: dto.text, createdAt: dto.created_at }
}

/**
 * @param activityId - One of the user's own tours.
 * @param signal - Optional abort signal.
 * @returns The stored feedback and whether the feature is on.
 */
export async function fetchActivityFeedback(
  activityId: number,
  signal?: AbortSignal,
): Promise<ActivityFeedback> {
  return mapFeedback(
    await apiFetch<ActivityFeedbackDto>(`/feedback/activities/${activityId}`, { signal }),
  )
}

/**
 * Write the feedback now, replacing any earlier text. Costs one API call.
 *
 * @param activityId - One of the user's own tours.
 * @returns The new feedback.
 */
export async function writeActivityFeedback(activityId: number): Promise<ActivityFeedback> {
  return mapFeedback(
    await apiFetch<ActivityFeedbackDto>(`/feedback/activities/${activityId}`, { method: 'POST' }),
  )
}

/**
 * The feedback on a tour. Looks again every few seconds while the server says
 * a text is on its way.
 *
 * @param activityId - The tour.
 */
export function useActivityFeedbackQuery(activityId: MaybeRefOrGetter<number>) {
  return useQuery({
    queryKey: computed(() => queryKeys.feedback.activity(toValue(activityId))),
    queryFn: ({ signal }) => fetchActivityFeedback(toValue(activityId), signal),
    refetchInterval: (query) => (query.state.data?.pending ? PENDING_POLL_MS : false),
    staleTime: 10 * 60 * 1000,
  })
}

/** Write (or rewrite) a tour's feedback, then show the new text. */
export function useWriteActivityFeedbackMutation() {
  return useInvalidatingMutation({
    mutationKey: ['feedback', 'write'],
    mutationFn: (activityId: number) => writeActivityFeedback(activityId),
    invalidateKey: queryKeys.feedback.all(),
  })
}
