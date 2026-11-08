<script setup lang="ts">
/**
 * On a tour's page: in how many cells this was the user's first tour. Says how
 * much new ground the tour covered, which a distance or a time does not.
 *
 * Counted at the coverage map's default cell size, so the number matches what
 * the map shows before it is zoomed.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useActivityCellsQuery } from '@/features/coverageMap/composables/useCoverage'
import { DEFAULT_CELL_ZOOM } from '@/features/coverageMap/types'
import { roundedCellSizeM } from '@/features/coverageMap/utils/tiles'

const props = defineProps<{
  activityId: number
  /** Where the tour is, to give the cell size on the ground there. */
  latitude: number
}>()

const { t, n } = useI18n()
const query = useActivityCellsQuery(
  () => props.activityId,
  DEFAULT_CELL_ZOOM,
  () => true,
)

const counts = computed(() => query.data.value ?? null)
const metres = computed(() =>
  n(roundedCellSizeM(props.latitude, counts.value?.zoom ?? DEFAULT_CELL_ZOOM)),
)
</script>

<template>
  <p v-if="counts && counts.cells > 0" class="text-caption" data-testid="activity-new-cells">
    <template v-if="counts.newCells > 0">
      {{
        t('activities.coverage.activity.new', counts.newCells, {
          named: { count: n(counts.newCells), cells: n(counts.cells), metres },
        })
      }}
    </template>
    <template v-else>
      {{
        t('activities.coverage.activity.none', counts.cells, {
          named: { cells: n(counts.cells), metres },
        })
      }}
    </template>
    <RouterLink :to="{ name: 'coverage' }" class="underline underline-offset-2">
      {{ t('activities.coverage.activity.link') }}
    </RouterLink>
  </p>
</template>
