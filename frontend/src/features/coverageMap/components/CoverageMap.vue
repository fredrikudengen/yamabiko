<script setup lang="ts">
/**
 * The coverage map: one red square per cell the user's tours have passed
 * through, darker where more tours went.
 *
 * This talks to Leaflet directly instead of through the `useMapProvider` seam,
 * for the same reason the segment editor does: the seam draws one read-only
 * track, and this draws thousands of rectangles.
 *
 * The rectangles go on a canvas renderer rather than Leaflet's default SVG.
 * A few thousand SVG paths make panning stutter on a phone; on canvas they are
 * just shapes in one element.
 */
import {
  canvas as createCanvas,
  map as createMap,
  rectangle,
  tileLayer,
  type Canvas,
  type LayerGroup,
  type LatLngBoundsExpression,
  type Map as LeafletMap,
  layerGroup,
} from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { CoverageCell } from '@/features/coverageMap/types'

import { useAppConfig } from '@/features/config/composables/useAppConfig'
import { CELL_FILL_OPACITY, colorOf } from '@/features/coverageMap/utils/scale'
import { cellBounds } from '@/features/coverageMap/utils/tiles'

const props = defineProps<{
  cells: CoverageCell[]
  /** The grid the cells are counted at. */
  zoom: number
  /** Text for a cell's tooltip, given its count. */
  tooltip: (count: number) => string
}>()

const { config } = useAppConfig()
const container = ref<HTMLElement | null>(null)

let map: LeafletMap | null = null
let cellLayer: LayerGroup | null = null
// One canvas for every rectangle, made once. A renderer per redraw would leave
// the old canvases on the map: clearing the layer group drops the rectangles,
// not the renderer they were drawn on.
let renderer: Canvas | null = null
let resizeObserver: ResizeObserver | null = null
let fitted = false

/** The box around every cell, for the first fit. */
function boundsOfAll(): LatLngBoundsExpression | null {
  if (props.cells.length === 0) {
    return null
  }
  let south = 90
  let west = 180
  let north = -90
  let east = -180
  for (const cell of props.cells) {
    const box = cellBounds(cell.x, cell.y, props.zoom)
    south = Math.min(south, box.south)
    west = Math.min(west, box.west)
    north = Math.max(north, box.north)
    east = Math.max(east, box.east)
  }
  return [
    [south, west],
    [north, east],
  ]
}

function drawCells(): void {
  if (!map || !cellLayer || !renderer) {
    return
  }
  cellLayer.clearLayers()
  for (const cell of props.cells) {
    const box = cellBounds(cell.x, cell.y, props.zoom)
    const color = colorOf(cell.count)
    rectangle(
      [
        [box.south, box.west],
        [box.north, box.east],
      ],
      {
        renderer,
        color,
        // No outline: cells that touch should read as one walked area, not as
        // a grid drawn over the map.
        weight: 0,
        fillColor: color,
        fillOpacity: CELL_FILL_OPACITY,
        interactive: true,
      },
    )
      .bindTooltip(props.tooltip(cell.count), { sticky: true })
      .addTo(cellLayer)
  }
}

/** Fit to the cells the first time there are any; later changes keep the view. */
function fitOnce(): void {
  if (fitted || !map) {
    return
  }
  const bounds = boundsOfAll()
  if (bounds) {
    map.fitBounds(bounds, { padding: [24, 24] })
    fitted = true
  }
}

/** Re-fit on demand, for the "show everything" button. */
function fitAll(): void {
  const bounds = boundsOfAll()
  if (map && bounds) {
    map.fitBounds(bounds, { padding: [24, 24] })
  }
}

onMounted(() => {
  if (!container.value) {
    return
  }
  map = createMap(container.value, { attributionControl: true, preferCanvas: true }).setView(
    [62, 10],
    5,
  )
  tileLayer(config.value.map.tileUrl, {
    attribution: config.value.map.attribution,
    maxZoom: 19,
  }).addTo(map)
  renderer = createCanvas({ padding: 0.2 }).addTo(map)
  cellLayer = layerGroup().addTo(map)
  // The layout around the map changes, and Leaflet only learns its new size if
  // told; otherwise tiles stop loading and the map greys out.
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => map?.invalidateSize())
    resizeObserver.observe(container.value)
  }
  drawCells()
  fitOnce()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  // Drop the shapes before the map goes: a redraw already queued for the next
  // frame would otherwise run against a canvas that no longer exists.
  cellLayer?.clearLayers()
  renderer?.remove()
  map?.remove()
  map = null
  cellLayer = null
  renderer = null
})

watch(
  () => [props.cells, props.zoom],
  () => {
    drawCells()
    fitOnce()
  },
)

defineExpose({ fitAll })
</script>

<template>
  <div class="relative isolate size-full overflow-hidden rounded-lg bg-muted">
    <!-- Leaflet adds its own classes to this element, so Vue must not bind
         :class here: a re-render would wipe them and the map would lose its
         layout and tiles. -->
    <div
      ref="container"
      class="size-full"
      role="application"
      :aria-label="$t('activities.coverage.map.label')"
    />
  </div>
</template>
