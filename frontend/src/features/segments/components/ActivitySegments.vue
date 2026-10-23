<script setup lang="ts">
/** Segments one activity has passed, on its detail page. Hidden when there are none. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { Card } from '@/components/ui/card'
import { useActivityEffortsQuery } from '@/features/segments/composables/useSegments'
import { formatSeconds } from '@/features/segments/utils/geo'

const props = defineProps<{ activityId: number }>()
const { t } = useI18n()
const query = useActivityEffortsQuery(() => props.activityId)
const efforts = computed(() => query.data.value ?? [])
</script>

<template>
  <Card v-if="efforts.length > 0" class="p-3" data-testid="activity-segments">
    <h2 class="mb-2 text-item-title">{{ t('activities.segments.onActivity') }}</h2>
    <ul class="flex flex-col gap-1.5">
      <li
        v-for="effort in efforts"
        :key="effort.id"
        class="flex flex-wrap items-baseline justify-between gap-x-3"
      >
        <router-link
          :to="{ name: 'segment', params: { id: effort.segmentId } }"
          class="text-body font-medium hover:underline"
        >
          {{ effort.segmentName }}
        </router-link>
        <span class="text-meta tabular-nums">
          {{ formatSeconds(effort.movingS) }}
          <template v-if="effort.elapsedS - effort.movingS >= 1">
            ({{ t('activities.segments.fields.totalShort') }} {{ formatSeconds(effort.elapsedS) }})
          </template>
          <template v-if="effort.averageHr !== null">
            · {{ Math.round(effort.averageHr) }} {{ t('activities.segments.fields.bpm') }}</template
          >
          <template v-if="effort.elevationGainM !== null">
            · +{{ Math.round(effort.elevationGainM) }} m</template
          >
        </span>
      </li>
    </ul>
  </Card>
</template>
