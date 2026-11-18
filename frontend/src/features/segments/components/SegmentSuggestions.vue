<script setup lang="ts">
/**
 * Stretches walked often without a segment on them. Each one can open the segment editor with its
 * two ends already placed on the path; the user checks the matches there and saves.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Lightbulb } from '@lucide/vue'

import type { SegmentSuggestion } from '@/features/segments/types'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useSegmentSuggestionsQuery } from '@/features/segments/composables/useSegments'
import { formatCoordinates } from '@/features/segments/utils/geo'

/** How many of a stretch's tours are named; the rest are counted. */
const SHOWN_TOURS = 3

const { t, n, locale } = useI18n()
/** Also stretches walked only twice; off by default so the list stays short. */
const includeTwice = ref(false)
const query = useSegmentSuggestionsQuery(() => (includeTwice.value ? 2 : 3))
const suggestions = computed(() => query.data.value ?? [])

/**
 * @param iso - A start time.
 * @returns The date in the user's locale.
 */
function dateOf(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, { dateStyle: 'medium' })
}

/** The editor, opened with the suggestion's two ends placed. */
function editorFor(suggestion: SegmentSuggestion) {
  return {
    name: 'segment-new',
    query: { start: formatCoordinates(suggestion.start), end: formatCoordinates(suggestion.end) },
  }
}
</script>

<template>
  <Card class="flex flex-col gap-3 p-3" data-testid="segment-suggestions">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="flex items-center gap-2 text-item-title">
        <Lightbulb class="size-4 text-brand" aria-hidden="true" />
        {{ t('activities.segments.suggestions.title') }}
      </h2>
      <label class="flex items-center gap-2 text-meta">
        <input v-model="includeTwice" type="checkbox" data-testid="suggestions-twice" />
        {{ t('activities.segments.suggestions.includeTwice') }}
      </label>
    </div>

    <Skeleton v-if="query.isPending.value" class="h-12 w-full" />
    <p v-else-if="query.isError.value" class="text-meta">
      {{ t('activities.segments.suggestions.loadError') }}
    </p>
    <p v-else-if="suggestions.length === 0" class="text-meta" data-testid="suggestions-none">
      {{ t('activities.segments.suggestions.none') }}
    </p>
    <ul v-else class="flex flex-col divide-y">
      <li
        v-for="suggestion in suggestions"
        :key="suggestion.key"
        class="flex flex-wrap items-center justify-between gap-3 py-2"
        data-testid="suggestion"
      >
        <div class="flex min-w-0 flex-col gap-0.5">
          <p class="text-body">
            {{
              t('activities.segments.suggestions.walked', {
                count: suggestion.tours.length,
                km: n(suggestion.straightM / 1000, { maximumFractionDigits: 1 }),
              })
            }}
          </p>
          <p class="text-meta">
            <template
              v-for="(tour, index) in suggestion.tours.slice(0, SHOWN_TOURS)"
              :key="tour.id"
            >
              <template v-if="index > 0"> · </template>
              <router-link
                :to="{ name: 'activity', params: { id: tour.id } }"
                class="hover:underline"
              >
                {{ tour.name || t('activities.segments.suggestions.unnamed') }}
              </router-link>
              ({{ dateOf(tour.startTime) }})
            </template>
            <template v-if="suggestion.tours.length > SHOWN_TOURS">
              {{
                t('activities.segments.suggestions.more', {
                  count: suggestion.tours.length - SHOWN_TOURS,
                })
              }}
            </template>
          </p>
        </div>
        <Button size="sm" variant="outline" as-child>
          <router-link :to="editorFor(suggestion)" data-testid="suggestion-create">
            {{ t('activities.segments.suggestions.create') }}
          </router-link>
        </Button>
      </li>
    </ul>
  </Card>
</template>
