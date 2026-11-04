<script setup lang="ts">
/**
 * The tours that passed through a picked cell: name and date, newest first,
 * each name a link to the tour.
 */
import { X } from '@lucide/vue'
import { onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CellRef } from '@/features/coverageMap/types'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { useCellToursQuery } from '@/features/coverageMap/composables/useCoverage'

const props = defineProps<{
  cell: CellRef
}>()

const emit = defineEmits<{
  close: []
}>()

const { t, n, locale } = useI18n()
const query = useCellToursQuery(() => props.cell)

/**
 * @param iso - A start time.
 * @returns The date in the user's locale, e.g. "14. okt. 2026".
 */
function dateOf(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, { dateStyle: 'medium' })
}

function closeOnEscape(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => window.addEventListener('keydown', closeOnEscape))
onBeforeUnmount(() => window.removeEventListener('keydown', closeOnEscape))
</script>

<template>
  <div
    class="flex max-h-[min(20rem,calc(100%-1.5rem))] w-72 max-w-[calc(100%-1.5rem)] flex-col rounded-lg border bg-card shadow-md"
    role="dialog"
    :aria-label="t('activities.coverage.cell.title', query.data.value?.length ?? 0)"
    data-testid="coverage-cell-tours"
  >
    <div class="flex items-center justify-between gap-2 border-b py-1 pr-1 pl-3">
      <p class="text-sm font-medium">
        <template v-if="query.data.value">
          {{
            t('activities.coverage.cell.title', query.data.value.length, {
              named: { count: n(query.data.value.length) },
            })
          }}
        </template>
      </p>
      <Button
        variant="ghost"
        size="icon-sm"
        :aria-label="t('activities.coverage.cell.close')"
        @click="emit('close')"
      >
        <X aria-hidden="true" />
      </Button>
    </div>

    <div v-if="query.isPending.value" class="flex justify-center p-4">
      <Spinner />
    </div>
    <p v-else-if="query.isError.value" class="p-3 text-sm text-destructive">
      {{ t('activities.coverage.cell.loadError') }}
    </p>
    <ul v-else class="overflow-y-auto py-1">
      <li v-for="tour in query.data.value" :key="tour.id" data-testid="coverage-cell-tour">
        <router-link
          :to="{ name: 'activity', params: { id: tour.id } }"
          class="flex flex-col px-3 py-1.5 hover:bg-muted"
        >
          <span class="text-sm font-medium hover:underline">
            {{ tour.name || t('activities.coverage.cell.unnamed') }}
          </span>
          <span class="text-caption">{{ dateOf(tour.startTime) }}</span>
        </router-link>
      </li>
    </ul>
  </div>
</template>
