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

import type { CellRef, CoverageCell } from '@/features/coverageMap/types'

import { useAppConfig } from '@/features/config/composables/useAppConfig'
import { CELL_FILL_OPACITY, colorOf } from '@/features/coverageMap/utils/scale'
import { cellBounds } from '@/features/coverageMap/utils/tiles'

const props = defineProps<{
  cells: CoverageCell[]
  /** The grid the cells are counted at. */
  zoom: number
  /** Text for a cell's tooltip. */
  tooltip: (cell: CoverageCell) => string
  /** Fill colour of a cell; by default the red scale over its tour count. */
  color?: (cell: CoverageCell) => string
  /** The picked cell, outlined; it may belong to another grid than `zoom`. */
  selected?: CellRef | null
}>()

const emit = defineEmits<{
  /** The map's zoom once it has settled, so the page can pick a cell size. */
  zoom: [mapZoom: number]
  /** A cell was clicked, given at the grid it was drawn with. */
  select: [cell: CellRef]
}>()

/**
 * How long the map must stay at a zoom before it is reported. Scrolling through
 * several levels fires `zoomend` at each; only the last should cost a fetch.
 */
const ZOOM_SETTLE_MS = 300

/** Outline of the picked cell: dark enough to stand out on every red bucket. */
const SELECTED_OUTLINE = '#1e293b'

const { config } = useAppConfig()
const container = ref<HTMLElement | null>(null)

let map: LeafletMap | null = null
let cellLayer: LayerGroup | null = null
// Its own layer above the cells, so picking a cell redraws one outline rather
// than every cell.
let selectionLayer: LayerGroup | null = null
// One canvas for every rectangle, made once. A renderer per redraw would leave
// the old canvases on the map: clearing the layer group drops the rectangles,
// not the renderer they were drawn on.
let renderer: Canvas | null = null
let resizeObserver: ResizeObserver | null = null
let fitted = false
let zoomTimer: ReturnType<typeof setTimeout> | undefined

/** Report the zoom once it has stopped changing. */
function reportZoomSoon(): void {
  clearTimeout(zoomTimer)
  zoomTimer = setTimeout(() => {
    if (map) {
      emit('zoom', map.getZoom())
    }
  }, ZOOM_SETTLE_MS)
}

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
    const color = props.color ? props.color(cell) : colorOf(cell.count)
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
      .bindTooltip(props.tooltip(cell), { sticky: true })
      .on('click', () => emit('select', { x: cell.x, y: cell.y, zoom: props.zoom }))
      .addTo(cellLayer)
  }
}

function drawSelection(): void {
  if (!map || !selectionLayer || !renderer) {
    return
  }
  selectionLayer.clearLayers()
  const cell = props.selected
  if (!cell) {
    return
  }
  const box = cellBounds(cell.x, cell.y, cell.zoom)
  rectangle(
    [
      [box.south, box.west],
      [box.north, box.east],
    ],
    // Not interactive: clicks go through to the cell underneath.
    { renderer, color: SELECTED_OUTLINE, weight: 2, fill: false, interactive: false },
  ).addTo(selectionLayer)
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
  selectionLayer = layerGroup().addTo(map)
  // The layout around the map changes, and Leaflet only learns its new size if
  // told; otherwise tiles stop loading and the map greys out.
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => map?.invalidateSize())
    resizeObserver.observe(container.value)
  }
  map.on('zoomend', reportZoomSoon)
  drawCells()
  drawSelection()
  fitOnce()
  // The first fit may land on the zoom the map started at, which fires no
  // `zoomend`; report it anyway so the page always learns the starting zoom.
  reportZoomSoon()
})

onBeforeUnmount(() => {
  clearTimeout(zoomTimer)
  resizeObserver?.disconnect()
  resizeObserver = null
  // Drop the shapes before the map goes: a redraw already queued for the next
  // frame would otherwise run against a canvas that no longer exists.
  cellLayer?.clearLayers()
  selectionLayer?.clearLayers()
  renderer?.remove()
  map?.remove()
  map = null
  cellLayer = null
  selectionLayer = null
  renderer = null
})

watch(
  () => [props.cells, props.zoom, props.color],
  () => {
    drawCells()
    // One canvas paints in the order shapes were added, so new cells would
    // cover the outline; put it back on top.
    drawSelection()
    fitOnce()
  },
)

watch(() => props.selected, drawSelection)

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
