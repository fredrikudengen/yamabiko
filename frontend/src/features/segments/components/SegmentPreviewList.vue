<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { NearMiss, PreviewMatch } from '@/features/segments/types'

import { Alert } from '@/components/ui/alert'
import { formatSeconds } from '@/features/segments/utils/geo'

defineProps<{
  matches: PreviewMatch[]
  nearMisses: NearMiss[]
  /** Existing segments with nearly the same ends: a hint, not an error. */
  similar: { id: number; name: string }[]
  loading: boolean
  /** The nodes cannot be previewed yet, with the reason in words. */
  blocked: string | null
}>()

const { t, locale } = useI18n()

/** Rounds a distance in metres up, so "radius needed" never under-promises. */
function needed(metres: number): number {
  return Math.ceil(metres)
}

function dateOf(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, { dateStyle: 'medium' })
}
</script>

<template>
  <div class="flex flex-col gap-3" data-testid="segment-preview">
    <Alert v-if="blocked" kind="info">{{ blocked }}</Alert>

    <template v-else>
      <Alert v-if="similar.length > 0" kind="warning">
        {{
          t('activities.segments.preview.similar', { names: similar.map((s) => s.name).join(', ') })
        }}
      </Alert>

      <p class="text-meta" aria-live="polite">
        {{
          loading
            ? t('activities.segments.preview.loading')
            : t('activities.segments.preview.summary', {
                matches: matches.length,
                misses: nearMisses.length,
              })
        }}
      </p>

      <ul v-if="matches.length > 0" class="flex flex-col gap-2">
        <li
          v-for="m in matches"
          :key="m.activityId"
          class="rounded-input border px-3 py-2"
          data-testid="preview-match"
        >
          <div class="flex flex-wrap items-baseline justify-between gap-x-3">
            <router-link
              :to="{ name: 'activity', params: { id: m.activityId } }"
              class="text-item-title hover:underline"
            >
              {{ m.activityName ?? t('activities.segments.untitled') }}
            </router-link>
            <span class="text-meta">{{ dateOf(m.startTime) }}</span>
          </div>
          <dl class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-meta">
            <div>
              <dt class="inline">{{ t('activities.segments.fields.moving') }}:</dt>
              <dd class="ml-1 inline font-medium">{{ formatSeconds(m.movingS) }}</dd>
            </div>
            <div v-if="m.stoppedS + m.gapS > 0">
              <dt class="inline">{{ t('activities.segments.fields.stopped') }}:</dt>
              <dd class="ml-1 inline">{{ formatSeconds(m.stoppedS + m.gapS) }}</dd>
            </div>
            <div v-if="m.averageHr !== null">
              <dt class="inline">{{ t('activities.segments.fields.hr') }}:</dt>
              <dd class="ml-1 inline">{{ Math.round(m.averageHr) }}</dd>
            </div>
            <div v-if="m.elevationGainM !== null">
              <dt class="inline">{{ t('activities.segments.fields.gain') }}:</dt>
              <dd class="ml-1 inline">+{{ Math.round(m.elevationGainM) }} m</dd>
            </div>
          </dl>
          <p class="mt-1 text-hint">
            {{
              t('activities.segments.preview.closest', {
                start: needed(m.closestStartM),
                end: needed(m.closestEndM),
              })
            }}
          </p>
          <p v-if="m.endVisits > 1" class="text-hint" data-testid="preview-multi-visit">
            {{ t('activities.segments.preview.endVisits', { count: m.endVisits }) }}
          </p>
        </li>
      </ul>

      <div v-if="nearMisses.length > 0" class="flex flex-col gap-2">
        <h3 class="text-item-title">{{ t('activities.segments.preview.nearMisses') }}</h3>
        <ul class="flex flex-col gap-2">
          <li
            v-for="n in nearMisses"
            :key="n.activityId"
            class="rounded-input border border-dashed px-3 py-2"
            data-testid="preview-near-miss"
          >
            <div class="flex flex-wrap items-baseline justify-between gap-x-3">
              <span class="text-item-title">{{
                n.activityName ?? t('activities.segments.untitled')
              }}</span>
              <span class="text-meta">{{ dateOf(n.startTime) }}</span>
            </div>
            <p class="text-meta">{{ t(`activities.segments.preview.reason.${n.reason}`) }}</p>
            <p class="text-hint">
              {{
                t('activities.segments.preview.closest', {
                  start: needed(n.closestStartM),
                  end: needed(n.closestEndM),
                })
              }}
            </p>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>
