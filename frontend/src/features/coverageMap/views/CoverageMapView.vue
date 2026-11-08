<script setup lang="ts">
/**
 * Where the user has been: every cell their tours have passed through, red and
 * darker where more tours went. The map can instead show one year's new
 * ground: the cells first visited that year, with the rest greyed out.
 *
 * The grid is counted on the server, so the page fetches one small list of
 * cells rather than every tour's GPS track.
 */
import { Map as MapIcon, Maximize2, RefreshCw } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import CoverageCellTours from '@/features/coverageMap/components/CoverageCellTours.vue'
import CoverageLegend from '@/features/coverageMap/components/CoverageLegend.vue'
import CoverageMap from '@/features/coverageMap/components/CoverageMap.vue'
import {
  useCoverageQuery,
  useRefreshCoverageMutation,
} from '@/features/coverageMap/composables/useCoverage'
import {
  CELL_ZOOMS,
  DEFAULT_CELL_ZOOM,
  type CellRef,
  type CellSizeChoice,
  type CoverageCell,
  type CoverageMode,
} from '@/features/coverageMap/types'
import {
  NEW_CELL_COLOR,
  OLD_CELL_COLOR,
  colorOf,
  firstVisitYears,
  yearOf,
} from '@/features/coverageMap/utils/scale'
import { autoCellZoom, roundedCellSizeM } from '@/features/coverageMap/utils/tiles'

const { t, n, locale } = useI18n()

/**
 * "Auto" follows the map: zoomed out, the cells get coarser so they stay
 * visible instead of shrinking below a pixel. A fixed size overrides it.
 */
const sizeChoice = ref<CellSizeChoice>('auto')
/** The map's zoom, once the map has reported it. */
const mapZoom = ref<number | null>(null)

/** The grid "auto" picks for the map as it is now. */
const autoZoom = computed(() =>
  mapZoom.value === null ? DEFAULT_CELL_ZOOM : autoCellZoom(mapZoom.value),
)
/** The grid to fetch. */
const zoom = computed(() => (sizeChoice.value === 'auto' ? autoZoom.value : sizeChoice.value))
const query = useCoverageQuery(zoom)
const refresh = useRefreshCoverageMutation()
const mapRef = ref<InstanceType<typeof CoverageMap> | null>(null)
/** The cell whose tours are listed, or `null` when the list is closed. */
const selectedCell = ref<CellRef | null>(null)

/**
 * The grid the cells on screen belong to. While a new size loads the previous
 * cells stay up, and they must be drawn at their own zoom, not the one asked for.
 */
const shownZoom = computed(() => query.data.value?.zoom ?? zoom.value)
const cells = computed(() => query.data.value?.cells ?? [])
const maxCount = computed(() => query.data.value?.maxCount ?? 0)
const loading = computed(() => query.isPending.value)
const failed = computed(() => query.isError.value)
const empty = computed(() => !loading.value && !failed.value && cells.value.length === 0)

/** Tour counts, or the year whose new cells stand out. */
const mode = ref<CoverageMode>('tours')
/** The years the map can show new cells for, newest first. */
const years = computed(() => firstVisitYears(cells.value.map((cell) => cell.firstVisit)))
/** The year shown, or `null` when the map shows tour counts. */
const shownYear = computed(() => (typeof mode.value === 'number' ? mode.value : null))
/** How many cells were first visited in the shown year. */
const newInYear = computed(() =>
  shownYear.value === null
    ? 0
    : cells.value.filter((cell) => yearOf(cell.firstVisit) === shownYear.value).length,
)

/**
 * A new function only when the mode changes, so the map redraws on a switch
 * and not on every render.
 */
const cellColor = computed(() => {
  const year = shownYear.value
  if (year === null) {
    return (cell: CoverageCell) => colorOf(cell.count)
  }
  return (cell: CoverageCell) =>
    yearOf(cell.firstVisit) === year ? NEW_CELL_COLOR : OLD_CELL_COLOR
})

/**
 * Cell sizes are quoted at the middle of the drawn area. A cell is constant in
 * projected space, so its size on the ground depends on latitude; quoting it
 * from a fixed latitude would be wrong for anyone who travels.
 */
const middleLatitude = computed(() => {
  if (cells.value.length === 0) {
    return 60
  }
  const scale = 2 ** shownZoom.value
  const rows = cells.value.map((cell) => cell.y)
  const middleRow = (Math.min(...rows) + Math.max(...rows)) / 2
  return (Math.atan(Math.sinh(Math.PI * (1 - (2 * middleRow) / scale))) * 180) / Math.PI
})

/**
 * @param value - A grid zoom.
 * @returns The label for the cell-size choice, e.g. "about 300 m".
 */
function sizeLabel(value: number): string {
  return t('activities.coverage.cellSize.option', {
    metres: n(roundedCellSizeM(middleLatitude.value, value)),
  })
}

/** The label for "auto", with the size it picks at the current map zoom. */
const autoLabel = computed(() =>
  t('activities.coverage.cellSize.auto', {
    metres: n(roundedCellSizeM(middleLatitude.value, autoZoom.value)),
  }),
)

/**
 * @param cell - A cell on the map.
 * @returns The tooltip for it: how many tours, and when the first was.
 */
function cellTooltip(cell: CoverageCell): string {
  return t('activities.coverage.cellTooltip', cell.count, {
    named: {
      count: n(cell.count),
      first: new Date(cell.firstVisit).toLocaleDateString(locale.value, { dateStyle: 'medium' }),
    },
  })
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-wrap items-end justify-between gap-2">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('activities.coverage.title') }}</h1>
        <p class="text-body">{{ t('activities.coverage.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Select
          v-model.number="mode"
          class="w-auto"
          :aria-label="t('activities.coverage.mode.label')"
          data-testid="coverage-mode"
        >
          <option value="tours">{{ t('activities.coverage.mode.tours') }}</option>
          <option v-for="year in years" :key="year" :value="year">
            {{ t('activities.coverage.mode.newIn', { year }) }}
          </option>
        </Select>
        <Select
          v-model.number="sizeChoice"
          class="w-auto"
          data-testid="coverage-cell-size"
          :aria-label="t('activities.coverage.cellSize.label')"
        >
          <option value="auto">{{ autoLabel }}</option>
          <option v-for="value in CELL_ZOOMS" :key="value" :value="value">
            {{ sizeLabel(value) }}
          </option>
        </Select>
        <Button
          variant="outline"
          :disabled="refresh.isPending.value"
          @click="refresh.mutate(undefined)"
        >
          <RefreshCw aria-hidden="true" :class="{ 'animate-spin': refresh.isPending.value }" />
          {{ t('activities.coverage.refresh') }}
        </Button>
      </div>
    </header>

    <Skeleton v-if="loading" class="h-150 w-full" data-testid="coverage-loading" />

    <ErrorState
      v-else-if="failed"
      :title="t('activities.coverage.loadError')"
      @retry="query.refetch()"
    />

    <EmptyState
      v-else-if="empty"
      :title="t('activities.coverage.empty.title')"
      :description="t('activities.coverage.empty.description')"
    >
      <template #icon><MapIcon class="size-8" aria-hidden="true" /></template>
    </EmptyState>

    <template v-else>
      <Card class="relative h-96 overflow-hidden p-0 lg:h-150">
        <CoverageMap
          ref="mapRef"
          :cells="cells"
          :zoom="shownZoom"
          :tooltip="cellTooltip"
          :color="cellColor"
          :selected="selectedCell"
          @zoom="mapZoom = $event"
          @select="selectedCell = $event"
        />
        <CoverageCellTours
          v-if="selectedCell"
          :cell="selectedCell"
          class="absolute top-3 right-3 z-10"
          @close="selectedCell = null"
        />
      </Card>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <CoverageLegend :max-count="maxCount" :year="shownYear" />
        <Button variant="ghost" size="sm" @click="mapRef?.fitAll()">
          <Maximize2 aria-hidden="true" />
          {{ t('activities.coverage.fitAll') }}
        </Button>
      </div>
      <p class="text-caption">
        {{
          t('activities.coverage.summary', {
            cells: n(cells.length),
            metres: n(roundedCellSizeM(middleLatitude, shownZoom)),
          })
        }}
        <template v-if="shownYear !== null">
          {{
            t('activities.coverage.newSummary', newInYear, {
              named: { count: n(newInYear), year: shownYear },
            })
          }}
        </template>
      </p>
    </template>
  </section>
</template>
