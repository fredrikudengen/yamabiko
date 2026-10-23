<script setup lang="ts">
/** Segments one activity has passed, on its detail page. Hidden when there are none. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { useActivityEffortsQuery } from '@/features/segments/composables/useSegments'
import { formatSeconds } from '@/features/segments/utils/geo'
import { sourceLabelKey } from '@/features/segments/utils/source'

const props = defineProps<{ activityId: number }>()
const { t } = useI18n()
const query = useActivityEffortsQuery(() => props.activityId)
const efforts = computed(() => query.data.value ?? [])
// All efforts of one tour share its source.
const source = computed(() => efforts.value[0]?.source ?? 'other')
</script>

<template>
  <Card v-if="efforts.length > 0" class="p-3" data-testid="activity-segments">
    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-item-title">{{ t('activities.segments.onActivity') }}</h2>
      <Badge
        variant="outline"
        :title="t('activities.segments.source.tooltip')"
        data-testid="activity-segments-source"
      >
        {{ t(sourceLabelKey(source)) }}
      </Badge>
    </div>
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
