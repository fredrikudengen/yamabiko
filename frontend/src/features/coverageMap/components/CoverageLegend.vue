<script setup lang="ts">
/** What the reds mean: a swatch per bucket, from walked once to walked often. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { CELL_FILL_OPACITY, legendBuckets } from '@/features/coverageMap/utils/scale'

const props = defineProps<{ maxCount: number }>()

const { t } = useI18n()
const buckets = computed(() => legendBuckets(props.maxCount))

/**
 * @param from - Lowest count in the bucket.
 * @param to - Highest count, or `null` when the bucket is open-ended.
 * @returns The label for one swatch.
 */
function label(from: number, to: number | null): string {
  if (to === null) {
    return t('activities.coverage.legend.andUp', { from })
  }
  return from === to ? String(from) : `${from}–${to}`
}
</script>

<template>
  <div v-if="buckets.length" class="flex flex-wrap items-center gap-x-3 gap-y-1">
    <span class="text-caption">{{ t('activities.coverage.legend.title') }}</span>
    <ul class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <li v-for="bucket in buckets" :key="bucket.from" class="flex items-center gap-1.5">
        <span
          class="size-3 rounded-xs border border-border"
          :style="{ backgroundColor: bucket.color, opacity: CELL_FILL_OPACITY }"
          aria-hidden="true"
        />
        <span class="text-caption">{{ label(bucket.from, bucket.to) }}</span>
      </li>
    </ul>
  </div>
</template>
