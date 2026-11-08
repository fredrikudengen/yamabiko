<script setup lang="ts">
/**
 * One year laid over the years before it: a running total from 1 January, so
 * the chart answers "am I ahead of last year?" for distance, climb, time,
 * tours or new ground.
 *
 * The selected year is drawn strong; up to four earlier years with tours are
 * drawn behind it. The line for the current year stops at today.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Units } from '@/features/activities/utils/format'
import type { ChartInstance, ChartRenderOptions } from '@/composables/useChartProvider'
import type { ProgressMetric } from '@/features/summary/types'

import { Card } from '@/components/ui/card'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useChartProvider } from '@/composables/useChartProvider'
import { useRenderProvidersReady } from '@/providers'
import { useDailyProgressQuery } from '@/features/summary/composables/useSummary'
import {
  DAYS_IN_CHART,
  buildYearLines,
  chartDayDate,
  chartDayIndex,
  totalBy,
} from '@/features/summary/utils/yearProgress'
import { kmToMiles } from '@/utils/units'

const props = defineProps<{
  /** The year the summary shows; drawn strong. */
  year: number
  /** Activity type code to filter by, or `null` for every type. */
  typeCode: number | null
  units: Units
}>()

const { t, locale } = useI18n()

/** Earlier years drawn behind the selected one, at most. */
const EARLIER_YEARS = 4
const SELECTED_COLOR = '#2f5d8c'
/** Last year stands out from the older ones, which recede. */
const EARLIER_COLORS = ['#f59e0b', '#94a3b8', '#64748b', '#cbd5e1'] as const

const METRICS: readonly ProgressMetric[] = [
  'distance',
  'elevationGain',
  'duration',
  'activityCount',
  'newCells',
]

const metric = ref<ProgressMetric>('elevationGain')
const query = useDailyProgressQuery(
  () => props.typeCode,
  () => true,
)

/** Today in the browser's time zone, `YYYY-MM-DD`. */
function todayIso(): string {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
const today = todayIso()
const [thisYear, thisMonth, thisDay] = today.split('-').map(Number)

const allLines = computed(() => buildYearLines(query.data.value ?? [], metric.value, today))
const selectedLine = computed(() => allLines.value.find((line) => line.year === props.year) ?? null)
const earlierLines = computed(() =>
  allLines.value.filter((line) => line.year < props.year).slice(0, EARLIER_YEARS),
)

/**
 * The day the years are compared on: today in the current year, otherwise the
 * last day of the year.
 */
const compareIndex = computed(() =>
  props.year === thisYear ? chartDayIndex(thisMonth ?? 12, thisDay ?? 31) : DAYS_IN_CHART - 1,
)

/**
 * @param value - A running total in the metric's own unit (metres, seconds, a count).
 * @returns It formatted for the axis and the tooltip.
 */
function formatValue(value: number): string {
  const number = (amount: number, digits = 0) =>
    amount.toLocaleString(locale.value, { maximumFractionDigits: digits })
  switch (metric.value) {
    case 'distance': {
      const km = value / 1000
      return props.units === 'imperial' ? `${number(kmToMiles(km), 1)} mi` : `${number(km, 1)} km`
    }
    case 'elevationGain':
      return props.units === 'imperial' ? `${number(value * 3.28084)} ft` : `${number(value)} m`
    case 'duration':
      return t('summary.progress.hours', { value: number(value / 3600, 1) })
    default:
      return number(value)
  }
}

/** The x-axis: each day of the shared calendar by its date, e.g. "14. mar.". */
const labels = computed(() =>
  Array.from({ length: DAYS_IN_CHART }, (_, index) => {
    const { month, day } = chartDayDate(index)
    return new Date(Date.UTC(2024, month - 1, day)).toLocaleDateString(locale.value, {
      day: 'numeric',
      month: 'short',
      timeZone: 'UTC',
    })
  }),
)

const render = computed<ChartRenderOptions>(() => {
  // Drawn oldest first, so the selected year ends up on top.
  const earlier = [...earlierLines.value].reverse().map((line) => ({
    label: String(line.year),
    data: line.values,
    color: EARLIER_COLORS[earlierLines.value.indexOf(line)] ?? '#cbd5e1',
    fill: false,
    width: 1.5,
  }))
  const selected = selectedLine.value
    ? [
        {
          label: String(props.year),
          data: selectedLine.value.values,
          color: SELECTED_COLOR,
          fill: false,
          width: 3,
        },
      ]
    : []
  return {
    kind: 'line',
    labels: labels.value,
    series: [...earlier, ...selected],
    valueFormat: formatValue,
    hoverAll: true,
  }
})

/** The selected year against last year with tours, on the compare day. */
const comparison = computed(() => {
  const mine = selectedLine.value ? totalBy(selectedLine.value, compareIndex.value) : null
  const before = earlierLines.value[0]
  if (mine === null || !before) {
    return null
  }
  const theirs = totalBy(before, compareIndex.value) ?? before.total
  const { month, day } = chartDayDate(compareIndex.value)
  const date = new Date(Date.UTC(2024, month - 1, day)).toLocaleDateString(locale.value, {
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  })
  return {
    date,
    mine: formatValue(mine),
    year: before.year,
    theirs: formatValue(theirs),
  }
})

const isEmpty = computed(() => !query.isPending.value && selectedLine.value === null)

const ready = useRenderProvidersReady()
const container = ref<HTMLElement | null>(null)
let instance: ChartInstance | null = null

function mountChart(): void {
  if (instance || !container.value || !ready.value) {
    return
  }
  instance = useChartProvider().provider.mount(container.value, render.value)
}

onMounted(mountChart)
watch([ready, container], mountChart)
watch(render, (next) => {
  if (!instance) {
    mountChart()
    return
  }
  instance.update(next)
})
onBeforeUnmount(() => {
  instance?.destroy()
  instance = null
})
</script>

<template>
  <Card class="flex min-w-0 flex-col gap-3" data-testid="summary-year-progress">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-card-heading">{{ t('summary.progress.title') }}</h2>
      <Select
        v-model="metric"
        class="w-auto"
        :aria-label="t('summary.progress.metricLabel')"
        data-testid="summary-progress-metric"
      >
        <option v-for="option in METRICS" :key="option" :value="option">
          {{ t(`summary.progress.metric.${option}`) }}
        </option>
      </Select>
    </div>

    <Skeleton v-if="query.isPending.value" class="h-64 w-full" />
    <p v-else-if="isEmpty" class="text-hint">{{ t('summary.progress.empty', { year }) }}</p>
    <template v-else>
      <p v-if="comparison" class="text-body" data-testid="summary-progress-comparison">
        {{ t('summary.progress.comparison', { ...comparison, selected: year }) }}
      </p>
      <!-- min-w-0 lets the canvas shrink with the card on a phone. -->
      <div ref="container" class="relative h-64 w-full min-w-0" />
    </template>
  </Card>
</template>
