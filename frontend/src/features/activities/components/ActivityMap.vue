<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { LocateFixed, Pause, Play } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { GeoPoint, MapHighlight, MapInstance } from '@/composables/useMapProvider'

import { useMapProvider } from '@/composables/useMapProvider'
import { useRenderProvidersReady } from '@/providers'

const props = withDefaults(
  defineProps<{
    /** Ordered GPS coordinates forming the route polyline. */
    points: GeoPoint[]
    /** Whether the map responds to pan/zoom. */
    interactive?: boolean
    /** Stretches drawn over the route, such as the segments the tour passed. */
    highlights?: MapHighlight[]
    /** A point on the route to mark: where the charts point, or where playback has got to. */
    marker?: GeoPoint | null
    /** Whether the route is being played back; shows the play button when not undefined. */
    playing?: boolean
  }>(),
  { interactive: true, highlights: () => [], marker: null, playing: undefined },
)

const emit = defineEmits<{
  /** The point on the route under the pointer, or `null` when it leaves the route. */
  hover: [point: GeoPoint | null]
  /** The play button was pressed (to start or to stop). */
  togglePlay: []
}>()

const { t } = useI18n()

function onHoverPoint(point: GeoPoint | null): void {
  emit('hover', point)
}

const ready = useRenderProvidersReady()
const container = ref<HTMLElement | null>(null)
let instance: MapInstance | null = null

/** Resolves the start/finish emphasis points from the track ends. */
function endpoints(points: GeoPoint[]): { start?: GeoPoint; finish?: GeoPoint } {
  const first = points[0]
  const last = points[points.length - 1]
  return first && last ? { start: first, finish: last } : {}
}

/** Mounts the map once the provider is ready and the container exists. */
function mountMap(): void {
  if (instance || !container.value || !ready.value || props.points.length === 0) {
    return
  }
  const { provider } = useMapProvider()
  instance = provider.mount(container.value, {
    track: { points: props.points, ...endpoints(props.points), highlights: props.highlights },
    interactive: props.interactive,
    onHoverPoint: props.interactive ? onHoverPoint : undefined,
  })
  instance.setMarker?.(props.marker)
}

/** Re-fits the map to the whole track after the user has panned or zoomed. */
function recenter(): void {
  instance?.recenter()
}

onMounted(mountMap)
watch(ready, mountMap)
watch(
  () => [props.points, props.highlights] as const,
  ([points, highlights]) => {
    if (!instance) {
      mountMap()
      return
    }
    instance.update({
      track: { points, ...endpoints(points), highlights },
      interactive: props.interactive,
    })
  },
)

watch(
  () => props.marker,
  (point) => instance?.setMarker?.(point),
)

onBeforeUnmount(() => {
  instance?.destroy()
  instance = null
})
</script>

<template>
  <!-- Fills its parent, which controls the height (e.g. a gallery slide).
       `isolate` creates a stacking context so Leaflet's internal panes and
       controls (z-index up to 1000) stay contained and never paint over the
       sticky navbar (z-40) or bottom nav while scrolling. -->
  <div class="relative isolate size-full overflow-hidden bg-muted">
    <div ref="container" class="size-full" role="img" :aria-label="$t('activities.map.label')" />
    <!-- z above Leaflet's controls (z-1000) so it stays clickable. -->
    <button
      v-if="interactive && points.length > 0"
      type="button"
      class="absolute top-3 right-3 z-[1100] flex size-9 items-center justify-center rounded-full bg-card/80 text-foreground backdrop-blur transition-colors hover:bg-card"
      :aria-label="$t('activities.map.recenter')"
      :title="$t('activities.map.recenter')"
      @click="recenter"
    >
      <LocateFixed class="size-4" />
    </button>
    <button
      v-if="interactive && playing !== undefined && points.length > 1"
      type="button"
      class="absolute bottom-3 left-3 z-[1100] flex h-9 items-center gap-1.5 rounded-full bg-card/80 px-3 text-sm text-foreground backdrop-blur transition-colors hover:bg-card"
      :aria-pressed="playing"
      data-testid="route-play"
      @click="emit('togglePlay')"
    >
      <Pause v-if="playing" class="size-4" aria-hidden="true" />
      <Play v-else class="size-4" aria-hidden="true" />
      {{ playing ? t('activities.map.stop') : t('activities.map.play') }}
    </button>
  </div>
</template>
