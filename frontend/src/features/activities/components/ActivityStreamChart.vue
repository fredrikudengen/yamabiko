<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartInstance, ChartRenderOptions } from '@/composables/useChartProvider'
import type { GeoPoint } from '@/composables/useMapProvider'
import type { StreamStat } from '@/features/activities/utils/streams'

import { Card } from '@/components/ui/card'
import { useChartProvider } from '@/composables/useChartProvider'
import { useRenderProvidersReady } from '@/providers'

const props = withDefaults(
  defineProps<{
    /** Localized chart title. */
    title: string
    /** Render options for the chart provider. */
    render: ChartRenderOptions
    /** Summary stats shown beneath the chart. */
    stats?: StreamStat[]
    /** Where on the route each point of the chart lies; without it the chart does not follow the map. */
    positions?: GeoPoint[]
    /** The point on the route to mark with a vertical line, or `null` for none. */
    cursor?: GeoPoint | null
  }>(),
  { stats: () => [], positions: undefined, cursor: null },
)

const emit = defineEmits<{
  /** The point on the route under the pointer, or `null` when it leaves the chart. */
  hover: [point: GeoPoint | null]
}>()

/**
 * The chart index nearest a point on the route. Compared in degrees with longitude scaled by
 * latitude, which is close enough over the few kilometres a tour covers.
 */
function nearestIndex(positions: readonly GeoPoint[], point: GeoPoint): number | null {
  const scale = Math.cos((point.lat * Math.PI) / 180)
  let best: number | null = null
  let bestDistance = Number.POSITIVE_INFINITY
  positions.forEach((p, index) => {
    const distance = (p.lat - point.lat) ** 2 + ((p.lng - point.lng) * scale) ** 2
    if (distance < bestDistance) {
      bestDistance = distance
      best = index
    }
  })
  return best
}

/** Reports the route point under the pointer; set once, at mount, since the provider keeps it. */
function onHoverIndex(index: number | null): void {
  emit('hover', index === null ? null : (props.positions?.[index] ?? null))
}

const { t } = useI18n()

const ready = useRenderProvidersReady()
const container = ref<HTMLElement | null>(null)
let instance: ChartInstance | null = null

/** Legend swatch colour, taken from the (single) series. */
const swatchColor = computed(() => props.render.series[0]?.color ?? 'var(--color-brand)')

/**
 * Render options with series labels resolved through i18n. `buildStreamChart`
 * stores each metric's i18n *key* as the series label, so the tooltip would
 * otherwise read e.g. `activities.streams.heartRate`. Translating here keeps the
 * stream util pure; `t()` returns non-key strings unchanged, so an
 * already-localized label passes through.
 */
const chartRender = computed<ChartRenderOptions>(() => ({
  ...props.render,
  series: props.render.series.map((series) => ({ ...series, label: t(series.label) })),
  onHoverIndex: props.positions ? onHoverIndex : undefined,
}))

/** Moves the vertical line to where the map (or the playback, or another chart) points. */
function drawCursor(): void {
  if (!instance || !props.positions) {
    return
  }
  instance.setCursor?.(props.cursor ? nearestIndex(props.positions, props.cursor) : null)
}

/** Mounts the chart once the provider is ready and the container exists. */
function mountChart(): void {
  if (instance || !container.value || !ready.value) {
    return
  }
  const { provider } = useChartProvider()
  instance = provider.mount(container.value, chartRender.value)
  drawCursor()
}

onMounted(mountChart)
watch(ready, mountChart)
watch(chartRender, (render) => {
  if (!instance) {
    mountChart()
    return
  }
  instance.update(render)
})

watch(() => props.cursor, drawCursor)

onBeforeUnmount(() => {
  instance?.destroy()
  instance = null
})
</script>

<template>
  <!-- min-w-0 lets the chart shrink inside the grid; without it the canvas
       forces the column wider than the viewport on mobile. -->
  <Card class="flex min-w-0 flex-col gap-3">
    <div class="flex items-center gap-2">
      <span
        class="size-2.5 rounded-full"
        :style="{ backgroundColor: swatchColor }"
        aria-hidden="true"
      />
      <h3 class="text-card-heading">{{ title }}</h3>
    </div>
    <div ref="container" class="relative h-56 w-full min-w-0" />
    <dl v-if="props.stats.length > 0" class="flex flex-wrap gap-x-6 gap-y-2">
      <div v-for="stat in props.stats" :key="stat.labelKey">
        <dt class="text-caption">{{ t(stat.labelKey) }}</dt>
        <dd class="text-item-title">
          {{ stat.value
          }}<span v-if="stat.unit" class="ms-1 text-hint font-normal">{{ stat.unit }}</span>
        </dd>
      </div>
    </dl>
  </Card>
</template>
