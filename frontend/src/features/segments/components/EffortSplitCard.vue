<script setup lang="ts">
/**
 * Where on the segment a pass gained or lost against the best one: the gap
 * between their clocks at each hundredth of the way. A line that climbs is
 * time lost; one that falls is time won back.
 *
 * The best pass is the fastest on the chosen basis, as in the table above. A
 * pass marked uncertain can still be the best; its record then reads "PR?".
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartInstance, ChartRenderOptions } from '@/composables/useChartProvider'
import type { SegmentEffort } from '@/features/segments/types'
import type { EffortBasis } from '@/features/segments/utils/efforts'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useChartProvider } from '@/composables/useChartProvider'
import { useRenderProvidersReady } from '@/providers'
import { useEffortProfileQuery } from '@/features/segments/composables/useSegments'
import { timeOf } from '@/features/segments/utils/efforts'
import { formatSeconds } from '@/features/segments/utils/geo'
import { behindAlongTheWay, biggestStretches } from '@/features/segments/utils/splits'

const props = defineProps<{
  segmentId: number
  efforts: SegmentEffort[]
}>()

const { t, locale } = useI18n()

/** The line: red where behind reads as time lost. */
const LINE_COLOR = '#dc2626'

const basis = ref<EffortBasis>('moving')

/** The fastest pass on the basis; the first stored wins a tie, as the table's ranks share it. */
const best = computed(() => {
  const ranked = [...props.efforts].sort(
    (a, b) => timeOf(a, basis.value) - timeOf(b, basis.value) || a.id - b.id,
  )
  return ranked[0] ?? null
})

/** The passes that can be compared with the best, newest first. */
const others = computed(() =>
  props.efforts
    .filter((effort) => effort.id !== best.value?.id)
    .sort((a, b) => b.startTime.localeCompare(a.startTime)),
)

/** The pass picked in the select; the newest by default. */
const picked = ref<number | null>(null)
const pickedId = computed(() => {
  const ids = others.value.map((effort) => effort.id)
  return picked.value !== null && ids.includes(picked.value) ? picked.value : (ids[0] ?? null)
})
/** The select's model: always one of the passes on offer. */
const pickModel = computed<number>({
  get: () => pickedId.value ?? 0,
  set: (value) => {
    picked.value = Number(value)
  },
})
const pickedEffort = computed(
  () => others.value.find((effort) => effort.id === pickedId.value) ?? null,
)

const mineQuery = useEffortProfileQuery(() => props.segmentId, pickedId)
const bestQuery = useEffortProfileQuery(
  () => props.segmentId,
  () => (pickedId.value === null ? null : (best.value?.id ?? null)),
)

const behind = computed(() => {
  const mine = mineQuery.data.value
  const reference = bestQuery.data.value
  return mine && reference ? behindAlongTheWay(mine, reference, basis.value) : null
})
const stretches = computed(() => (behind.value ? biggestStretches(behind.value) : null))
const loading = computed(() => mineQuery.isPending.value || bestQuery.isPending.value)
const failed = computed(() => mineQuery.isError.value || bestQuery.isError.value)

/**
 * @param seconds - Seconds behind; negative when ahead.
 * @returns E.g. "+1:20" or "−0:31".
 */
function signed(seconds: number): string {
  const rounded = Math.round(seconds)
  if (rounded === 0) {
    return '0:00'
  }
  return `${rounded > 0 ? '+' : '−'}${formatSeconds(Math.abs(rounded))}`
}

/**
 * @param effort - A pass.
 * @returns Its date and time on the basis, for the select.
 */
function effortLabel(effort: SegmentEffort): string {
  const date = new Date(effort.startTime).toLocaleDateString(locale.value, { dateStyle: 'medium' })
  return `${date} · ${formatSeconds(timeOf(effort, basis.value))}`
}

const bestLabel = computed(() => (best.value ? effortLabel(best.value) : ''))

const render = computed<ChartRenderOptions>(() => ({
  kind: 'line',
  labels: Array.from({ length: behind.value?.length ?? 0 }, (_, index) => `${index} %`),
  series: [
    {
      label: t('activities.segments.split.behind'),
      data: behind.value ?? [],
      color: LINE_COLOR,
      fill: false,
    },
  ],
  valueFormat: signed,
}))

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
// The container goes away while a new pass loads; the next one needs a fresh chart.
watch(container, (element) => {
  if (!element) {
    instance?.destroy()
    instance = null
  }
})
onBeforeUnmount(() => {
  instance?.destroy()
  instance = null
})
</script>

<template>
  <Card v-if="others.length > 0 && best" class="flex flex-col gap-3 p-3" data-testid="effort-split">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-item-title">{{ t('activities.segments.split.title') }}</h2>
      <div class="flex flex-wrap items-center gap-2">
        <Button
          v-for="option in ['moving', 'total'] as const"
          :key="option"
          type="button"
          size="sm"
          :variant="basis === option ? 'default' : 'outline'"
          :aria-pressed="basis === option"
          :data-testid="`split-basis-${option}`"
          @click="basis = option"
        >
          {{
            option === 'moving'
              ? t('activities.segments.fields.moving')
              : t('activities.segments.fields.total')
          }}
        </Button>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2 text-meta">
      <Select
        v-model.number="pickModel"
        class="w-auto"
        :aria-label="t('activities.segments.split.pick')"
        data-testid="split-pick"
      >
        <option v-for="effort in others" :key="effort.id" :value="effort.id">
          {{ effortLabel(effort) }}
        </option>
      </Select>
      <span>{{ t('activities.segments.split.against', { best: bestLabel }) }}</span>
    </div>

    <Skeleton v-if="loading" class="h-56 w-full" />
    <ErrorState
      v-else-if="failed"
      :title="t('activities.segments.split.loadError')"
      @retry="
        () => {
          mineQuery.refetch()
          bestQuery.refetch()
        }
      "
    />
    <template v-else-if="behind && pickedEffort">
      <p class="text-body" data-testid="split-summary">
        {{
          t('activities.segments.split.atFinish', { time: signed(behind[behind.length - 1] ?? 0) })
        }}
        <template v-if="stretches?.lost">
          {{
            t('activities.segments.split.mostLost', {
              time: formatSeconds(stretches.lost.seconds),
              from: stretches.lost.fromPct,
              to: stretches.lost.toPct,
            })
          }}
        </template>
        <template v-if="stretches?.won">
          {{
            t('activities.segments.split.mostWon', {
              time: formatSeconds(-stretches.won.seconds),
              from: stretches.won.fromPct,
              to: stretches.won.toPct,
            })
          }}
        </template>
      </p>
      <!-- min-w-0 lets the canvas shrink with the card on a phone. -->
      <div ref="container" class="relative h-56 w-full min-w-0" />
      <p class="text-meta">{{ t('activities.segments.split.hint') }}</p>
    </template>
  </Card>
</template>
