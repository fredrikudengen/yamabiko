<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SegmentEffort } from '@/features/segments/types'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { beatsPer100mOf, climbRateOf } from '@/features/segments/utils/climb'
import { compareEfforts, type EffortBasis } from '@/features/segments/utils/efforts'
import { formatSeconds } from '@/features/segments/utils/geo'
import { milestoneOf, milestoneText } from '@/features/segments/utils/milestone'
import { hasMixedSources, sourceLabelKey } from '@/features/segments/utils/source'

const props = defineProps<{
  efforts: SegmentEffort[]
  /** Show the activity name as a link; off when the table sits on that activity. */
  linkActivities?: boolean
}>()

const { t, locale } = useI18n()
const basis = ref<EffortBasis>('moving')
const rows = computed(() =>
  compareEfforts(props.efforts, basis.value).map((row) => ({
    ...row,
    // Where the pass stands among all passes of the segment, on the chosen basis.
    milestone: milestoneOf(row.effort, basis.value),
    // Metres climbed per hour on the chosen time, and heart beats per 100 m climbed (moving time).
    climbRate: climbRateOf(row.effort, basis.value),
    beatsPer100m: beatsPer100mOf(row.effort),
  })),
)
// Times come from the GPS track for every source; heart rate and ascent do not.
const mixedSources = computed(() => hasMixedSources(props.efforts))

function dateOf(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, { dateStyle: 'medium' })
}

function signed(seconds: number): string {
  return `+${formatSeconds(seconds)}`
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div
      class="flex flex-wrap items-center gap-2 text-meta"
      role="group"
      :aria-label="t('activities.segments.fields.compareBy')"
    >
      <span>{{ t('activities.segments.fields.compareBy') }}</span>
      <Button
        v-for="option in ['moving', 'total'] as const"
        :key="option"
        type="button"
        size="sm"
        :variant="basis === option ? 'default' : 'outline'"
        :aria-pressed="basis === option"
        :data-testid="`basis-${option}`"
        @click="basis = option"
      >
        {{
          option === 'moving'
            ? t('activities.segments.fields.moving')
            : t('activities.segments.fields.total')
        }}
      </Button>
    </div>

    <p v-if="mixedSources" class="text-meta" role="note" data-testid="mixed-sources-notice">
      {{ t('activities.segments.source.mixedNotice') }}
    </p>

    <div class="overflow-x-auto">
      <table class="w-full text-left text-body" data-testid="efforts-table">
        <thead class="text-meta">
          <tr>
            <th scope="col" class="py-1 pr-3 font-medium">
              {{ t('activities.segments.fields.date') }}
            </th>
            <th scope="col" class="py-1 pr-3 font-medium">
              {{ t('activities.segments.source.label') }}
            </th>
            <th scope="col" class="py-1 pr-3 font-medium">
              {{ t('activities.segments.fields.rank') }}
            </th>
            <th scope="col" class="py-1 pr-3 font-medium">
              {{ t('activities.segments.fields.moving') }}
            </th>
            <th scope="col" class="py-1 pr-3 font-medium">
              {{ t('activities.segments.fields.total') }}
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
            <th scope="col" class="py-1 pr-3 font-medium">
              {{ t('activities.segments.fields.gain') }}
            </th>
            <th
              scope="col"
              class="py-1 pr-3 font-medium"
              :title="t('activities.segments.fields.climbRateTooltip')"
            >
              {{ t('activities.segments.fields.climbRate') }}
            </th>
            <th
              scope="col"
              class="py-1 font-medium"
              :title="t('activities.segments.fields.beatsTooltip')"
            >
              {{ t('activities.segments.fields.beats') }}
            </th>
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
            <td class="py-1.5 pr-3">
              <Badge
                variant="outline"
                :title="t('activities.segments.source.tooltip')"
                data-testid="effort-source"
              >
                {{ t(sourceLabelKey(row.effort.source)) }}
              </Badge>
            </td>
            <td class="py-1.5 pr-3 whitespace-nowrap" data-testid="effort-rank">
              <span
                v-if="row.milestone"
                :class="row.milestone.isPr ? 'font-medium text-goal' : ''"
                :title="t('activities.segments.milestone.tooltip')"
              >
                {{ t(milestoneText(row.milestone).key, milestoneText(row.milestone).values) }}
              </span>
              <span v-else>–</span>
            </td>
            <td class="py-1.5 pr-3 tabular-nums" :class="{ 'font-medium': basis === 'moving' }">
              {{ formatSeconds(row.effort.movingS) }}
            </td>
            <td class="py-1.5 pr-3 tabular-nums" :class="{ 'font-medium': basis === 'total' }">
              {{ formatSeconds(row.effort.elapsedS) }}
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
            <td class="py-1.5 pr-3 tabular-nums">
              {{
                row.effort.elevationGainM !== null
                  ? `+${Math.round(row.effort.elevationGainM)} m`
                  : '–'
              }}
            </td>
            <td class="py-1.5 pr-3 tabular-nums whitespace-nowrap" data-testid="effort-climb-rate">
              {{
                row.climbRate !== null
                  ? `${Math.round(row.climbRate)} ${t('activities.segments.fields.climbRateUnit')}`
                  : '–'
              }}
            </td>
            <td class="py-1.5 tabular-nums" data-testid="effort-beats">
              {{ row.beatsPer100m !== null ? Math.round(row.beatsPer100m) : '–' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
