<script setup lang="ts">
/**
 * What the colours mean. Counting tours: a swatch per bucket, from walked once
 * to walked often. Showing one year: new that year, and everything else.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  CELL_FILL_OPACITY,
  NEW_CELL_COLOR,
  OLD_CELL_COLOR,
  legendBuckets,
} from '@/features/coverageMap/utils/scale'

const props = defineProps<{
  maxCount: number
  /** The year whose new cells stand out, or `null`/absent when counting tours. */
  year?: number | null
}>()

const { t } = useI18n()

interface Swatch {
  key: string
  color: string
  label: string
}

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

const swatches = computed<Swatch[]>(() => {
  if (props.maxCount < 1) {
    return []
  }
  if (props.year != null) {
    return [
      {
        key: 'new',
        color: NEW_CELL_COLOR,
        label: t('activities.coverage.legend.newIn', { year: props.year }),
      },
      { key: 'old', color: OLD_CELL_COLOR, label: t('activities.coverage.legend.otherYears') },
    ]
  }
  return legendBuckets(props.maxCount).map((bucket) => ({
    key: String(bucket.from),
    color: bucket.color,
    label: label(bucket.from, bucket.to),
  }))
})
</script>

<template>
  <div v-if="swatches.length" class="flex flex-wrap items-center gap-x-3 gap-y-1">
    <span v-if="year == null" class="text-caption">{{
      t('activities.coverage.legend.title')
    }}</span>
    <ul class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <li v-for="swatch in swatches" :key="swatch.key" class="flex items-center gap-1.5">
        <span
          class="size-3 rounded-xs border border-border"
          :style="{ backgroundColor: swatch.color, opacity: CELL_FILL_OPACITY }"
          aria-hidden="true"
        />
        <span class="text-caption">{{ swatch.label }}</span>
      </li>
    </ul>
  </div>
</template>
