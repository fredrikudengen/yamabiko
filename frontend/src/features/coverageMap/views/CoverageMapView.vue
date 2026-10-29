<script setup lang="ts">
/**
 * Where the user has been: every cell their tours have passed through, red and
 * darker where more tours went.
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
import CoverageLegend from '@/features/coverageMap/components/CoverageLegend.vue'
import CoverageMap from '@/features/coverageMap/components/CoverageMap.vue'
import {
  useCoverageQuery,
  useRefreshCoverageMutation,
} from '@/features/coverageMap/composables/useCoverage'
import { CELL_ZOOMS, DEFAULT_CELL_ZOOM } from '@/features/coverageMap/types'
import { roundedCellSizeM } from '@/features/coverageMap/utils/tiles'

const { t, n } = useI18n()

const zoom = ref<number>(DEFAULT_CELL_ZOOM)
const query = useCoverageQuery(zoom)
const refresh = useRefreshCoverageMutation()
const mapRef = ref<InstanceType<typeof CoverageMap> | null>(null)

const cells = computed(() => query.data.value?.cells ?? [])
const maxCount = computed(() => query.data.value?.maxCount ?? 0)
const loading = computed(() => query.isPending.value)
const failed = computed(() => query.isError.value)
const empty = computed(() => !loading.value && !failed.value && cells.value.length === 0)

/**
 * Cell sizes are quoted at the middle of the drawn area. A cell is constant in
 * projected space, so its size on the ground depends on latitude; quoting it
 * from a fixed latitude would be wrong for anyone who travels.
 */
const middleLatitude = computed(() => {
  if (cells.value.length === 0) {
    return 60
  }
  const scale = 2 ** zoom.value
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

/**
 * @param count - How many tours passed through a cell.
 * @returns The tooltip for one cell.
 */
function cellTooltip(count: number): string {
  return t('activities.coverage.cellTooltip', count, { named: { count: n(count) } })
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
          v-model.number="zoom"
          class="w-auto"
          :aria-label="t('activities.coverage.cellSize.label')"
        >
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
      <Card class="h-96 overflow-hidden p-0 lg:h-150">
        <CoverageMap ref="mapRef" :cells="cells" :zoom="zoom" :tooltip="cellTooltip" />
      </Card>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <CoverageLegend :max-count="maxCount" />
        <Button variant="ghost" size="sm" @click="mapRef?.fitAll()">
          <Maximize2 aria-hidden="true" />
          {{ t('activities.coverage.fitAll') }}
        </Button>
      </div>
      <p class="text-caption">
        {{
          t('activities.coverage.summary', {
            cells: n(cells.length),
            metres: n(roundedCellSizeM(middleLatitude, zoom)),
          })
        }}
      </p>
    </template>
  </section>
</template>
