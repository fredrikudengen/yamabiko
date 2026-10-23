<script setup lang="ts">
/**
 * Map for placing a segment's two nodes. Click the map to place the node being
 * edited, drag a marker to move it, drag the small handle on a circle's edge to
 * change its radius. Tracks of the user's tours are drawn underneath so the
 * circles can be placed on the path actually walked.
 *
 * This talks to Leaflet directly instead of through the `useMapProvider` seam:
 * the seam only draws read-only tracks, and the editor needs draggable markers
 * and circles in metres.
 */
import {
  circle as createCircle,
  divIcon,
  map as createMap,
  marker as createMarker,
  polyline,
  tileLayer,
  type Circle,
  type LayerGroup,
  type LeafletMouseEvent,
  type Map as LeafletMap,
  type Marker,
  type LatLngBoundsExpression,
  layerGroup,
} from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { Segment, SegmentNode, TrackLine } from '@/features/segments/types'

import { useAppConfig } from '@/features/config/composables/useAppConfig'
import { DEFAULT_NODE_RADIUS_M } from '@/features/segments/types'
import { clampRadius, distanceM, offsetEast } from '@/features/segments/utils/geo'
import { themeColor } from '@/lib/themeColor'

type Which = 'start' | 'end'

const props = defineProps<{
  start: SegmentNode | null
  end: SegmentNode | null
  /** Which node a click on the map places. `null` leaves clicks alone. */
  placing: Which | null
  tracks: TrackLine[]
  /** The user's other segments, drawn faintly so new ones can be placed relative to them. */
  others?: Segment[]
}>()

const emit = defineEmits<{
  'update:start': [node: SegmentNode]
  'update:end': [node: SegmentNode]
}>()

const { config } = useAppConfig()
const container = ref<HTMLElement | null>(null)

let map: LeafletMap | null = null
let trackLayer: LayerGroup | null = null
let othersLayer: LayerGroup | null = null
let resizeObserver: ResizeObserver | null = null
let fitted = false

const markers: Partial<Record<Which, Marker>> = {}
const handles: Partial<Record<Which, Marker>> = {}
const circles: Partial<Record<Which, Circle>> = {}

/** Colours come from the design tokens at draw time so they follow the theme. */
function colorOf(which: Which): string {
  return themeColor(which === 'start' ? '--color-goal' : '--color-hr')
}

function pinIcon(which: Which) {
  const color = colorOf(which)
  return divIcon({
    className: '',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html: `<div style="width:22px;height:22px;border-radius:9999px;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45)"></div>`,
  })
}

function handleIcon(which: Which) {
  const color = colorOf(which)
  return divIcon({
    className: '',
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    html: `<div style="width:16px;height:16px;border-radius:3px;background:#fff;border:3px solid ${color};cursor:ew-resize;box-shadow:0 1px 3px rgba(0,0,0,.4)"></div>`,
  })
}

function emitNode(which: Which, node: SegmentNode): void {
  if (which === 'start') {
    emit('update:start', node)
  } else {
    emit('update:end', node)
  }
}

function currentNode(which: Which): SegmentNode | null {
  return which === 'start' ? props.start : props.end
}

/** Creates or updates the marker, circle and radius handle for one node. */
function syncNode(which: Which): void {
  if (!map) {
    return
  }
  const node = currentNode(which)
  if (!node) {
    markers[which]?.remove()
    handles[which]?.remove()
    circles[which]?.remove()
    delete markers[which]
    delete handles[which]
    delete circles[which]
    return
  }
  const center: [number, number] = [node.lat, node.lon]
  const edge = offsetEast(center, node.radiusM)
  const color = colorOf(which)

  const existingCircle = circles[which]
  if (existingCircle) {
    existingCircle.setLatLng(center)
    existingCircle.setRadius(node.radiusM)
  } else {
    circles[which] = createCircle(center, {
      radius: node.radiusM,
      color,
      weight: 2,
      fillColor: color,
      fillOpacity: 0.18,
      interactive: false,
    }).addTo(map)
  }

  const existingMarker = markers[which]
  if (existingMarker) {
    existingMarker.setLatLng(center)
  } else {
    const pin = createMarker(center, { icon: pinIcon(which), draggable: true, zIndexOffset: 500 })
    pin.on('drag', () => {
      const at = pin.getLatLng()
      circles[which]?.setLatLng(at)
      const radius = currentNode(which)?.radiusM ?? DEFAULT_NODE_RADIUS_M
      handles[which]?.setLatLng(offsetEast([at.lat, at.lng], radius))
    })
    pin.on('dragend', () => {
      const at = pin.getLatLng()
      const radius = currentNode(which)?.radiusM ?? DEFAULT_NODE_RADIUS_M
      emitNode(which, { lat: at.lat, lon: at.lng, radiusM: radius })
    })
    markers[which] = pin.addTo(map)
  }

  const existingHandle = handles[which]
  if (existingHandle) {
    existingHandle.setLatLng(edge)
  } else {
    const handle = createMarker(edge, {
      icon: handleIcon(which),
      draggable: true,
      zIndexOffset: 400,
    })
    const radiusAt = (): number => {
      const centerNow = currentNode(which)
      const at = handle.getLatLng()
      return centerNow
        ? clampRadius(distanceM([centerNow.lat, centerNow.lon], [at.lat, at.lng]))
        : 0
    }
    handle.on('drag', () => {
      circles[which]?.setRadius(radiusAt())
    })
    handle.on('dragend', () => {
      const centerNow = currentNode(which)
      if (centerNow) {
        emitNode(which, { ...centerNow, radiusM: radiusAt() })
      }
    })
    handles[which] = handle.addTo(map)
  }
}

/**
 * Existing segments: faint dashed circles in the node colours, named on hover.
 * Clicks bubble through to the map (Leaflet paths do by default), so placing a
 * node on top of an old circle still works.
 */
function drawOthers(): void {
  if (!othersLayer) {
    return
  }
  othersLayer.clearLayers()
  for (const segment of props.others ?? []) {
    for (const which of ['start', 'end'] as const) {
      const node = segment[which]
      const color = colorOf(which)
      createCircle([node.lat, node.lon], {
        radius: node.radiusM,
        color,
        weight: 1.5,
        dashArray: '4 4',
        fillColor: color,
        fillOpacity: 0.06,
        bubblingMouseEvents: true,
      })
        .bindTooltip(segment.name, { sticky: true })
        .addTo(othersLayer)
    }
  }
}

function drawTracks(): void {
  if (!map || !trackLayer) {
    return
  }
  trackLayer.clearLayers()
  const color = themeColor('--color-brand')
  for (const track of props.tracks) {
    if (track.points.length > 1) {
      polyline(track.points, { color, weight: 3, opacity: 0.55, interactive: false }).addTo(
        trackLayer,
      )
    }
  }
}

/** Fits the viewport once: to the nodes if there are any, else to the tracks. */
function fitOnce(): void {
  if (!map || fitted) {
    return
  }
  const points: [number, number][] = []
  for (const node of [props.start, props.end]) {
    if (node) {
      points.push([node.lat, node.lon])
    }
  }
  if (points.length === 0) {
    for (const track of props.tracks) {
      points.push(...track.points)
    }
  }
  if (points.length === 0) {
    return
  }
  fitted = true
  if (points.length === 1 && points[0]) {
    map.setView(points[0], 16)
  } else {
    map.fitBounds(points as LatLngBoundsExpression, { padding: [40, 40], maxZoom: 17 })
  }
}

/** Zooms to everything drawn, for the button on the map. */
function fitAll(): void {
  fitted = false
  fitOnce()
}

function onMapClick(event: LeafletMouseEvent): void {
  if (!props.placing) {
    return
  }
  const previous = currentNode(props.placing)
  emitNode(props.placing, {
    lat: event.latlng.lat,
    lon: event.latlng.lng,
    radiusM: previous?.radiusM ?? DEFAULT_NODE_RADIUS_M,
  })
}

onMounted(() => {
  if (!container.value) {
    return
  }
  map = createMap(container.value, { attributionControl: true }).setView([62, 10], 5)
  tileLayer(config.value.map.tileUrl, {
    attribution: config.value.map.attribution,
    maxZoom: 19,
  }).addTo(map)
  othersLayer = layerGroup().addTo(map)
  trackLayer = layerGroup().addTo(map)
  // The layout around the map changes (e.g. when the preview list grows), and Leaflet
  // only learns its new size if told; otherwise tiles stop loading and the map greys out.
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => map?.invalidateSize())
    resizeObserver.observe(container.value)
  }
  drawOthers()
  map.on('click', onMapClick)
  drawTracks()
  syncNode('start')
  syncNode('end')
  fitOnce()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  map?.remove()
  map = null
})

watch(
  () => props.start,
  () => syncNode('start'),
  { deep: true },
)
watch(
  () => props.end,
  () => syncNode('end'),
  { deep: true },
)
watch(() => props.others, drawOthers)
watch(
  () => props.tracks,
  () => {
    drawTracks()
    fitOnce()
  },
)
defineExpose({ fitAll })
</script>

<template>
  <div
    class="relative isolate size-full overflow-hidden rounded-lg bg-muted"
    :class="{ 'segment-placing': placing !== null }"
  >
    <!-- Leaflet adds its own classes to this element, so Vue must not bind :class here
         (a re-render would wipe them and the map would lose its layout and tiles).
         The crosshair cursor lives on the wrapper and is inherited. -->
    <div
      ref="container"
      class="size-full"
      role="application"
      :aria-label="$t('activities.segments.map.label')"
    />
  </div>
</template>

<style>
/* Leaflet sets its own cursor on the container, so override it from the wrapper. */
.segment-placing .leaflet-container,
.segment-placing .leaflet-grab {
  cursor: crosshair;
}
</style>
