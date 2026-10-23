<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Mountain, Plus } from '@lucide/vue'

import type { Segment } from '@/features/segments/types'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useSegmentsQuery } from '@/features/segments/composables/useSegments'

const { t } = useI18n()
const query = useSegmentsQuery()
const segments = computed<Segment[]>(() => query.data.value ?? [])
const failed = computed(() => query.isError.value)
const loading = computed(() => query.isPending.value)
const empty = computed(() => !loading.value && !failed.value && segments.value.length === 0)
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-wrap items-end justify-between gap-2">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('activities.segments.title') }}</h1>
        <p class="text-body">{{ t('activities.segments.subtitle') }}</p>
      </div>
      <Button as-child>
        <router-link :to="{ name: 'segment-new' }">
          <Plus aria-hidden="true" />
          {{ t('activities.segments.new') }}
        </router-link>
      </Button>
    </header>

    <div v-if="loading" class="flex flex-col gap-2" data-testid="segments-loading">
      <Skeleton v-for="n in 3" :key="n" class="h-16 w-full" />
    </div>

    <ErrorState
      v-else-if="failed"
      :title="t('activities.segments.loadError')"
      @retry="query.refetch()"
    />

    <EmptyState
      v-else-if="empty"
      :title="t('activities.segments.empty.title')"
      :description="t('activities.segments.empty.description')"
    >
      <template #icon><Mountain class="size-8" aria-hidden="true" /></template>
    </EmptyState>

    <ul v-else class="flex flex-col gap-2">
      <li v-for="segment in segments" :key="segment.id">
        <Card class="p-0">
          <router-link
            :to="{ name: 'segment', params: { id: segment.id } }"
            class="flex items-center justify-between gap-3 rounded-card px-4 py-3 hover:bg-accent/40"
          >
            <span class="text-item-title">{{ segment.name }}</span>
            <span class="text-meta">
              {{
                t(
                  'activities.segments.efforts',
                  { count: segment.effortCount },
                  segment.effortCount,
                )
              }}
            </span>
          </router-link>
        </Card>
      </li>
    </ul>
  </section>
</template>
