<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { SegmentNode } from '@/features/segments/types'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { useToasts } from '@/composables/useToasts'
import { useUserActivitiesQuery } from '@/features/activities/composables/useActivities'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import SegmentMapEditor from '@/features/segments/components/SegmentMapEditor.vue'
import SegmentPreviewList from '@/features/segments/components/SegmentPreviewList.vue'
import {
  useCreateSegmentMutation,
  useSegmentPreviewQuery,
  useSegmentQuery,
  useSegmentsQuery,
  useTrackLines,
  useUpdateSegmentMutation,
} from '@/features/segments/composables/useSegments'
import { parseCoordinates } from '@/features/segments/services/segments'
import { DEFAULT_NODE_RADIUS_M } from '@/features/segments/types'
import { clampRadius, formatCoordinates, nodeProblem } from '@/features/segments/utils/geo'
import { HttpError } from '@/services/http'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const toasts = useToasts()
const { data: currentUser } = useCurrentUser()

const editingId = computed(() => (route.params.id ? Number(route.params.id) : null))
const allSegmentsQuery = useSegmentsQuery()
const otherSegments = computed(() =>
  (allSegmentsQuery.data.value ?? []).filter((segment) => segment.id !== editingId.value),
)
const segmentQuery = useSegmentQuery(() => editingId.value ?? Number.NaN)

const name = ref('')
const start = ref<SegmentNode | null>(null)
const end = ref<SegmentNode | null>(null)
const placing = ref<'start' | 'end' | null>('start')
const startText = ref('')
const endText = ref('')
const startTextError = ref<string | undefined>()
const endTextError = ref<string | undefined>()

// Fill the form once when editing an existing segment.
watch(
  () => segmentQuery.data.value,
  (segment) => {
    if (segment && editingId.value !== null && start.value === null) {
      name.value = segment.name
      start.value = { ...segment.start }
      end.value = { ...segment.end }
      placing.value = null
    }
  },
  { immediate: true },
)

// Keep the coordinate fields in step with the map.
watch(start, (node) => (startText.value = node ? formatCoordinates(node) : ''), { immediate: true })
watch(end, (node) => (endText.value = node ? formatCoordinates(node) : ''), { immediate: true })

/** After the start is placed by a click, the next click places the end. */
watch(start, (node, previous) => {
  if (node && !previous && placing.value === 'start') {
    placing.value = end.value ? null : 'end'
  }
})
watch(end, (node, previous) => {
  if (node && !previous && placing.value === 'end') {
    placing.value = null
  }
})

function setText(which: 'start' | 'end', value: string): void {
  if (which === 'start') {
    startText.value = value
  } else {
    endText.value = value
  }
}

/**
 * Reads a typed or pasted coordinate pair through the server's parser, so the
 * field accepts exactly what the API accepts, and moves the node there.
 */
async function applyText(which: 'start' | 'end'): Promise<void> {
  const text = which === 'start' ? startText.value : endText.value
  const setError = (message: string | undefined) => {
    if (which === 'start') {
      startTextError.value = message
    } else {
      endTextError.value = message
    }
  }
  if (!text.trim()) {
    setError(undefined)
    return
  }
  try {
    const { lat, lon } = await parseCoordinates(text)
    const previous = which === 'start' ? start.value : end.value
    const node = { lat, lon, radiusM: previous?.radiusM ?? DEFAULT_NODE_RADIUS_M }
    if (which === 'start') {
      start.value = node
    } else {
      end.value = node
    }
    setError(undefined)
  } catch (error) {
    setError(
      error instanceof HttpError && typeof error.detail === 'string'
        ? error.detail
        : t('activities.segments.editor.coordinatesInvalid'),
    )
  }
}

/** Sets the radius from the number field, kept inside what the server accepts. */
function setRadius(which: 'start' | 'end', raw: string): void {
  const node = which === 'start' ? start.value : end.value
  if (!node) {
    return
  }
  const next = { ...node, radiusM: clampRadius(Number(raw)) }
  if (which === 'start') {
    start.value = next
  } else {
    end.value = next
  }
}

const problem = computed(() =>
  start.value && end.value ? nodeProblem(start.value, end.value) : null,
)
const blockedReason = computed<string | null>(() => {
  if (!start.value || !end.value) {
    return t('activities.segments.preview.needNodes')
  }
  if (problem.value === 'radius_too_small') {
    return t('activities.segments.preview.radiusTooSmall')
  }
  if (problem.value === 'overlap') {
    return t('activities.segments.preview.overlap')
  }
  return null
})

const previewQuery = useSegmentPreviewQuery(start, end)
const preview = computed(() => previewQuery.data.value)

// Draw the tours that matter; with nothing to preview yet, the latest few so
// there is something to place the circles on.
const userId = computed(() => currentUser.value?.id ?? null)
const recent = useUserActivitiesQuery(
  userId,
  1,
  8,
  { type: null, startDate: null, endDate: null, nameSearch: null },
  'start_time',
  'desc',
)
const trackIds = computed<number[]>(() => {
  const p = preview.value
  if (p && (p.matches.length > 0 || p.nearMisses.length > 0)) {
    return [...p.matches.map((m) => m.activityId), ...p.nearMisses.map((n) => n.activityId)]
  }
  return (recent.data.value?.records ?? []).map((a) => a.id)
})
const tracks = useTrackLines(trackIds)

const createMutation = useCreateSegmentMutation()
const updateMutation = useUpdateSegmentMutation()
const saving = computed(() => createMutation.isPending.value || updateMutation.isPending.value)
const nameError = ref<string | undefined>()
const canSave = computed(() => blockedReason.value === null && !saving.value)

function onSaved(saved: { id: number; similarSegments: { name: string }[] }): void {
  toasts.success(t('activities.segments.editor.saved'))
  if (saved.similarSegments.length > 0) {
    toasts.info(
      t('activities.segments.preview.similar', {
        names: saved.similarSegments.map((s) => s.name).join(', '),
      }),
    )
  }
  void router.push({ name: 'segment', params: { id: saved.id } })
}

function onSaveError(error: Error): void {
  const detail =
    error instanceof HttpError && typeof error.detail === 'string' ? error.detail : null
  toasts.error(detail ?? t('activities.segments.editor.saveError'))
}

function save(): void {
  nameError.value = undefined
  if (!name.value.trim()) {
    nameError.value = t('activities.segments.editor.nameRequired')
    return
  }
  if (!start.value || !end.value || !canSave.value) {
    return
  }
  const input = { name: name.value.trim(), start: start.value, end: end.value }
  if (editingId.value !== null) {
    updateMutation.mutate(
      { id: editingId.value, input },
      { onSuccess: onSaved, onError: onSaveError },
    )
  } else {
    createMutation.mutate(input, { onSuccess: onSaved, onError: onSaveError })
  }
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">
        {{
          editingId === null
            ? t('activities.segments.editor.titleNew')
            : t('activities.segments.editor.titleEdit')
        }}
      </h1>
      <p class="text-body">{{ t('activities.segments.editor.subtitle') }}</p>
    </header>

    <Alert v-if="editingId !== null && segmentQuery.isError.value" kind="error">
      {{ t('activities.segments.detail.loadError') }}
    </Alert>

    <div class="grid gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Card class="flex flex-col gap-3 p-3">
        <div
          class="flex flex-wrap items-center gap-2"
          role="group"
          :aria-label="t('activities.segments.editor.placing')"
        >
          <Button
            type="button"
            size="sm"
            :variant="placing === 'start' ? 'default' : 'outline'"
            @click="placing = placing === 'start' ? null : 'start'"
          >
            {{ t('activities.segments.editor.placeStart') }}
          </Button>
          <Button
            type="button"
            size="sm"
            :variant="placing === 'end' ? 'default' : 'outline'"
            @click="placing = placing === 'end' ? null : 'end'"
          >
            {{ t('activities.segments.editor.placeEnd') }}
          </Button>
          <p class="text-hint">{{ t('activities.segments.editor.mapHint') }}</p>
        </div>
        <div class="h-[55vh] min-h-72">
          <SegmentMapEditor
            v-model:start="start"
            v-model:end="end"
            :placing="placing"
            :tracks="tracks"
            :others="otherSegments"
          />
        </div>
      </Card>

      <div class="flex flex-col gap-3">
        <Card class="flex flex-col gap-3 p-3">
          <FormField :label="t('activities.segments.editor.name')" :error="nameError" required>
            <template #default="{ fieldId, describedBy, invalid }">
              <Input
                :id="fieldId"
                v-model="name"
                maxlength="250"
                :aria-describedby="describedBy"
                :aria-invalid="invalid"
              />
            </template>
          </FormField>

          <div v-for="which in ['start', 'end'] as const" :key="which" class="flex flex-col gap-2">
            <h2 class="text-item-title">
              {{
                which === 'start'
                  ? t('activities.segments.editor.start')
                  : t('activities.segments.editor.end')
              }}
            </h2>
            <div class="grid grid-cols-[minmax(0,1fr)_6.5rem] gap-2">
              <FormField
                :label="t('activities.segments.editor.coordinates')"
                :error="which === 'start' ? startTextError : endTextError"
                :hint="t('activities.segments.editor.coordinatesHint')"
              >
                <template #default="{ fieldId, describedBy, invalid }">
                  <Input
                    :id="fieldId"
                    :model-value="which === 'start' ? startText : endText"
                    @update:model-value="setText(which, $event)"
                    inputmode="decimal"
                    autocomplete="off"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                    @change="applyText(which)"
                    @keydown.enter.prevent="applyText(which)"
                  />
                </template>
              </FormField>
              <FormField :label="t('activities.segments.editor.radius')">
                <template #default="{ fieldId }">
                  <Input
                    :id="fieldId"
                    type="number"
                    inputmode="numeric"
                    min="26"
                    step="5"
                    :model-value="
                      String((which === 'start' ? start : end)?.radiusM ?? DEFAULT_NODE_RADIUS_M)
                    "
                    :disabled="(which === 'start' ? start : end) === null"
                    @change="setRadius(which, ($event.target as HTMLInputElement).value)"
                  />
                </template>
              </FormField>
            </div>
          </div>

          <div class="flex gap-2">
            <Button type="button" :disabled="!canSave" @click="save">
              {{ t('activities.segments.editor.save') }}
            </Button>
            <Button type="button" variant="ghost" @click="router.back()">
              {{ t('activities.segments.editor.cancel') }}
            </Button>
          </div>
        </Card>

        <Card class="p-3">
          <h2 class="mb-2 text-item-title">{{ t('activities.segments.preview.title') }}</h2>
          <SegmentPreviewList
            :matches="preview?.matches ?? []"
            :near-misses="preview?.nearMisses ?? []"
            :similar="preview?.similarSegments ?? []"
            :loading="previewQuery.isFetching.value"
            :blocked="blockedReason"
          />
        </Card>
      </div>
    </div>
  </section>
</template>
