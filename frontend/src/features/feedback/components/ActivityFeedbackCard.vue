<script setup lang="ts">
/**
 * The written feedback at the bottom of a tour's page. Hidden entirely when
 * the feature is off. Before a text exists, the owner can ask for one; after,
 * they can have it written again (the text describes the numbers as they were
 * the day it was written).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RefreshCw, Sparkles } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useActivityFeedbackQuery,
  useWriteActivityFeedbackMutation,
} from '@/features/feedback/feedback'

const props = defineProps<{ activityId: number }>()

const { t, locale } = useI18n()
const query = useActivityFeedbackQuery(() => props.activityId)
const write = useWriteActivityFeedbackMutation()

const feedback = computed(() => query.data.value ?? null)
const writing = computed(() => write.isPending.value || (feedback.value?.pending ?? false))
const writtenOn = computed(() =>
  feedback.value?.createdAt
    ? new Date(feedback.value.createdAt).toLocaleDateString(locale.value, { dateStyle: 'medium' })
    : null,
)
</script>

<template>
  <Card v-if="feedback?.enabled" class="flex flex-col gap-3" data-testid="activity-feedback">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="flex items-center gap-2 text-card-heading">
        <Sparkles class="size-4 text-brand" aria-hidden="true" />
        {{ t('activities.feedback.title') }}
      </h2>
      <Button
        v-if="feedback.text"
        variant="ghost"
        size="sm"
        :disabled="writing"
        data-testid="feedback-rewrite"
        @click="write.mutate(activityId)"
      >
        <RefreshCw aria-hidden="true" :class="{ 'animate-spin': writing }" />
        {{ t('activities.feedback.rewrite') }}
      </Button>
    </div>

    <div v-if="writing && !feedback.text" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-4/5" />
      <p class="text-meta">{{ t('activities.feedback.writing') }}</p>
    </div>
    <template v-else-if="feedback.text">
      <p class="text-body whitespace-pre-line" data-testid="feedback-text">{{ feedback.text }}</p>
      <p class="text-meta">{{ t('activities.feedback.caption', { date: writtenOn }) }}</p>
    </template>
    <div v-else class="flex flex-wrap items-center gap-3">
      <p class="text-body">{{ t('activities.feedback.none') }}</p>
      <Button size="sm" data-testid="feedback-write" @click="write.mutate(activityId)">
        {{ t('activities.feedback.write') }}
      </Button>
    </div>

    <p v-if="write.isError.value" class="text-meta text-destructive" role="alert">
      {{ t('activities.feedback.error') }}
    </p>
  </Card>
</template>
