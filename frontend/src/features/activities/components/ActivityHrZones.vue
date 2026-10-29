<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { HrZoneBucket } from '@/features/activities/types'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useHrZoneLimits } from '@/features/activities/composables/useHrZoneLimits'
import { formatHmsDuration } from '@/features/activities/utils/format'
import { MIN_SHOWN_GAP_S, parseZoneLimitInputs } from '@/features/activities/utils/hrZoneTime'
import { hrZoneColor } from '@/features/activities/utils/hrZones'

const props = defineProps<{
  /** Ordered HR zone buckets (zones 1–5). */
  zones: HrZoneBucket[]
  /**
   * What the zone times cover. `moving`: time without the long stops; `recorded`: the whole
   * recording because no stops are known. Omit for zones the server computed, which the user's
   * limits do not apply to (no editor, no caption).
   */
  basis?: 'moving' | 'recorded'
  /** Seconds counted, shown as the sum under the bars. */
  countedS?: number
  /** Seconds without heart-rate data; shown only when it is more than a few seconds. */
  gapS?: number
}>()

const { t } = useI18n()
const { limits, isDefault, setLimits, resetLimits } = useHrZoneLimits()

const editable = computed(() => props.basis !== undefined)
const showGap = computed(() => (props.gapS ?? 0) >= MIN_SHOWN_GAP_S)
const editing = ref(false)
const fields = ref<string[]>([])
const error = ref<'incomplete' | 'range' | 'order' | null>(null)

/** Clamps a percentage to the 0–100 range for the bar width. */
function barWidth(percent: number): string {
  return `${Math.min(100, Math.max(0, percent))}%`
}

/** Opens the editor with the current limits in the fields. */
function startEditing(): void {
  fields.value = limits.value.map(String)
  error.value = null
  editing.value = true
}

/** Stores the typed limits when they are valid, otherwise says what is wrong. */
function save(): void {
  const parsed = parseZoneLimitInputs(fields.value)
  if ('error' in parsed) {
    error.value = parsed.error
    return
  }
  setLimits(parsed.limits)
  editing.value = false
}

/** Goes back to the default limits. */
function reset(): void {
  resetLimits()
  fields.value = limits.value.map(String)
  error.value = null
}
</script>

<template>
  <div class="flex flex-col gap-2.5">
    <div v-for="zone in zones" :key="zone.zone" class="flex items-center gap-3">
      <div class="w-24 shrink-0">
        <p class="text-meta font-medium text-foreground">
          {{ t('activities.hrZones.zone') }} {{ zone.zone }}
        </p>
        <p v-if="zone.hrRange" class="text-caption">{{ zone.hrRange }}</p>
      </div>
      <div
        class="h-2.5 flex-1 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        :aria-valuenow="Math.round(zone.percent)"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div
          class="h-full rounded-full"
          :style="{ width: barWidth(zone.percent), backgroundColor: hrZoneColor(zone.zone) }"
        />
      </div>
      <div class="w-20 shrink-0 text-right">
        <p v-if="basis" class="text-meta font-medium text-foreground tabular-nums">
          {{ formatHmsDuration(zone.timeSeconds) }}
        </p>
        <p :class="basis ? 'text-caption tabular-nums' : 'text-meta font-medium text-foreground'">
          {{ Math.round(zone.percent) }}%
        </p>
      </div>
    </div>

    <template v-if="editable">
      <p class="text-caption">
        {{
          t(
            basis === 'moving'
              ? 'activities.hrZones.basisMoving'
              : 'activities.hrZones.basisRecorded',
          )
        }}
        <template v-if="countedS">
          · {{ t('activities.hrZones.sum', { time: formatHmsDuration(countedS) }) }}
        </template>
      </p>
      <p v-if="showGap" class="text-caption">
        {{
          t('activities.hrZones.noHeartRate', { time: formatHmsDuration(Math.round(gapS ?? 0)) })
        }}
      </p>

      <div v-if="!editing" class="flex items-center gap-2">
        <Button variant="ghost" size="sm" class="-ml-3" @click="startEditing">
          {{ t('activities.hrZones.editLimits') }}
        </Button>
        <span v-if="!isDefault" class="text-caption">{{
          t('activities.hrZones.customLimits')
        }}</span>
      </div>

      <form v-else class="flex flex-col gap-2" @submit.prevent="save">
        <p class="text-caption">{{ t('activities.hrZones.limitsHint') }}</p>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <label v-for="(_, index) in fields" :key="index" class="flex flex-col gap-1">
            <span class="text-caption">{{
              t('activities.hrZones.zoneStartsAt', { zone: index + 2 })
            }}</span>
            <Input
              v-model="fields[index]"
              inputmode="numeric"
              class="w-full tabular-nums"
              :aria-invalid="error !== null"
            />
          </label>
        </div>
        <p v-if="error" class="text-caption text-destructive" role="alert">
          {{ t(`activities.hrZones.error.${error}`) }}
        </p>
        <div class="flex flex-wrap gap-2">
          <Button type="submit" size="sm">{{ t('activities.hrZones.save') }}</Button>
          <Button type="button" variant="outline" size="sm" @click="reset">
            {{ t('activities.hrZones.reset') }}
          </Button>
          <Button type="button" variant="ghost" size="sm" @click="editing = false">
            {{ t('activities.hrZones.cancel') }}
          </Button>
        </div>
      </form>
    </template>
  </div>
</template>
