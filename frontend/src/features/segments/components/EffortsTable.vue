<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SegmentEffort } from '@/features/segments/types'

import { compareEfforts } from '@/features/segments/utils/efforts'
import { formatSeconds } from '@/features/segments/utils/geo'

const props = defineProps<{
  efforts: SegmentEffort[]
  /** Show the activity name as a link; off when the table sits on that activity. */
  linkActivities?: boolean
}>()

const { t, locale } = useI18n()
const rows = computed(() => compareEfforts(props.efforts))

function dateOf(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, { dateStyle: 'medium' })
}

function signed(seconds: number): string {
  return `+${formatSeconds(seconds)}`
}
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full text-left text-body" data-testid="efforts-table">
      <thead class="text-meta">
        <tr>
          <th scope="col" class="py-1 pr-3 font-medium">
            {{ t('activities.segments.fields.date') }}
          </th>
          <th scope="col" class="py-1 pr-3 font-medium">
            {{ t('activities.segments.fields.moving') }}
          </th>
          <th scope="col" class="py-1 pr-3 font-medium">
            {{ t('activities.segments.fields.behind') }}
          </th>
          <th scope="col" class="py-1 pr-3 font-medium">
            {{ t('activities.segments.fields.stopped') }}
          </th>
          <th scope="col" class="py-1 pr-3 font-medium">
            {{ t('activities.segments.fields.hr') }}
          </th>
          <th scope="col" class="py-1 font-medium">{{ t('activities.segments.fields.gain') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.effort.id" class="border-t" data-testid="effort-row">
          <td class="py-1.5 pr-3">
            <router-link
              v-if="linkActivities"
              :to="{ name: 'activity', params: { id: row.effort.activityId } }"
              class="hover:underline"
            >
              {{ dateOf(row.effort.startTime) }}
            </router-link>
            <span v-else>{{ dateOf(row.effort.startTime) }}</span>
          </td>
          <td class="py-1.5 pr-3 font-medium tabular-nums">
            {{ formatSeconds(row.effort.movingS) }}
            <span
              v-if="row.isBest && rows.length > 1"
              class="ml-1 text-goal"
              data-testid="best-badge"
            >
              {{ t('activities.segments.fields.best') }}
            </span>
          </td>
          <td class="py-1.5 pr-3 tabular-nums">
            {{ row.isBest ? '–' : signed(row.behindBestS) }}
          </td>
          <td class="py-1.5 pr-3 tabular-nums">
            {{
              row.effort.stoppedS + row.effort.gapS > 0
                ? formatSeconds(row.effort.stoppedS + row.effort.gapS)
                : '–'
            }}
          </td>
          <td class="py-1.5 pr-3 tabular-nums">
            {{ row.effort.averageHr !== null ? Math.round(row.effort.averageHr) : '–' }}
          </td>
          <td class="py-1.5 tabular-nums">
            {{
              row.effort.elevationGainM !== null
                ? `+${Math.round(row.effort.elevationGainM)} m`
                : '–'
            }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
