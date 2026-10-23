import { keepPreviousData, useQueries, useQuery } from '@tanstack/vue-query'
import { computed, onBeforeUnmount, ref, type MaybeRefOrGetter, toValue, watch } from 'vue'

import type { SegmentInput, SegmentNode, TrackLine } from '@/features/segments/types'

import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import {
  createSegment,
  deleteSegment,
  fetchActivityEfforts,
  fetchActivityTrack,
  fetchSegment,
  fetchSegmentEfforts,
  fetchSegments,
  previewSegment,
  refreshSegment,
  updateSegment,
} from '@/features/segments/services/segments'
import { nodeProblem } from '@/features/segments/utils/geo'
import { queryKeys } from '@/services/queryKeys'

/** The user's segments. */
export function useSegmentsQuery() {
  return useQuery({
    queryKey: queryKeys.segments.list(),
    queryFn: ({ signal }) => fetchSegments(signal),
  })
}

/**
 * One segment.
 *
 * @param id - Segment identifier (a ref, getter or plain number).
 */
export function useSegmentQuery(id: MaybeRefOrGetter<number>) {
  return useQuery({
    queryKey: computed(() => queryKeys.segments.detail(toValue(id))),
    queryFn: ({ signal }) => fetchSegment(toValue(id), signal),
    enabled: computed(() => Number.isFinite(toValue(id))),
  })
}

/**
 * All passes of one segment, oldest first.
 *
 * @param id - Segment identifier.
 */
export function useSegmentEffortsQuery(id: MaybeRefOrGetter<number>) {
  return useQuery({
    queryKey: computed(() => queryKeys.segments.efforts(toValue(id))),
    queryFn: ({ signal }) => fetchSegmentEfforts(toValue(id), signal),
    enabled: computed(() => Number.isFinite(toValue(id))),
  })
}

/**
 * The segments one activity has passed.
 *
 * @param activityId - Activity identifier.
 */
export function useActivityEffortsQuery(activityId: MaybeRefOrGetter<number>) {
  return useQuery({
    queryKey: computed(() => queryKeys.segments.activityEfforts(toValue(activityId))),
    queryFn: ({ signal }) => fetchActivityEfforts(toValue(activityId), signal),
    enabled: computed(() => Number.isFinite(toValue(activityId))),
  })
}

/** Creates a segment; efforts for existing activities are computed server-side. */
export function useCreateSegmentMutation() {
  return useInvalidatingMutation({
    mutationKey: ['segments', 'create'],
    mutationFn: (input: SegmentInput) => createSegment(input),
    invalidateKey: queryKeys.segments.all(),
  })
}

/** Changes a segment; its efforts are recomputed. */
export function useUpdateSegmentMutation() {
  return useInvalidatingMutation({
    mutationKey: ['segments', 'update'],
    mutationFn: (variables: { id: number; input: SegmentInput }) =>
      updateSegment(variables.id, variables.input),
    invalidateKey: queryKeys.segments.all(),
  })
}

/** Deletes a segment and its efforts. */
export function useDeleteSegmentMutation() {
  return useInvalidatingMutation({
    mutationKey: ['segments', 'delete'],
    mutationFn: (id: number) => deleteSegment(id),
    invalidateKey: queryKeys.segments.all(),
  })
}

/** Recomputes a segment's efforts. */
export function useRefreshSegmentMutation() {
  return useInvalidatingMutation({
    mutationKey: ['segments', 'refresh'],
    mutationFn: (id: number) => refreshSegment(id),
    invalidateKey: queryKeys.segments.all(),
  })
}

/** How long the nodes must rest before the preview asks the server (ms). */
const PREVIEW_DEBOUNCE_MS = 450

/**
 * Which of the user's activities would pass two nodes, asked again whenever the
 * nodes settle. Stays idle until both nodes exist and pass the same checks the
 * server makes, so half-placed or overlapping circles never cause a 422.
 *
 * @param start - The start node, or `null` while unplaced.
 * @param end - The end node, or `null` while unplaced.
 */
export function useSegmentPreviewQuery(
  start: MaybeRefOrGetter<SegmentNode | null>,
  end: MaybeRefOrGetter<SegmentNode | null>,
) {
  const settled = ref<{ start: SegmentNode; end: SegmentNode } | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined

  watch(
    () => [toValue(start), toValue(end)] as const,
    ([s, e]) => {
      clearTimeout(timer)
      if (!s || !e || nodeProblem(s, e) !== null) {
        settled.value = null
        return
      }
      const next = { start: { ...s }, end: { ...e } }
      timer = setTimeout(() => {
        settled.value = next
      }, PREVIEW_DEBOUNCE_MS)
    },
    { immediate: true, deep: true },
  )
  onBeforeUnmount(() => clearTimeout(timer))

  return useQuery({
    queryKey: computed(() => ['segments', 'preview', settled.value] as const),
    queryFn: ({ signal }) => {
      const nodes = settled.value
      if (!nodes) {
        throw new Error('preview without nodes')
      }
      return previewSegment(nodes.start, nodes.end, signal)
    },
    enabled: computed(() => settled.value !== null),
    placeholderData: keepPreviousData,
    retry: false,
  })
}

/**
 * GPS tracks for several activities at once, for drawing under the circles.
 * Activities without a GPS stream come back with no points and are skipped.
 *
 * @param activityIds - The activities to draw.
 * @returns The tracks that have loaded so far.
 */
export function useTrackLines(activityIds: MaybeRefOrGetter<number[]>) {
  const results = useQueries({
    queries: computed(() =>
      toValue(activityIds).map((id) => ({
        queryKey: queryKeys.segments.track(id),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchActivityTrack(id, signal),
        staleTime: 10 * 60 * 1000,
        retry: false,
      })),
    ),
  })
  return computed<TrackLine[]>(() =>
    results.value.flatMap((r) => (r.data && r.data.points.length > 1 ? [r.data] : [])),
  )
}
