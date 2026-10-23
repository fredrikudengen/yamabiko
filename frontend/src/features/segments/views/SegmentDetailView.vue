<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { Pencil, RefreshCw, Trash2 } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import EffortsTable from '@/features/segments/components/EffortsTable.vue'
import {
  useDeleteSegmentMutation,
  useRefreshSegmentMutation,
  useSegmentEffortsQuery,
  useSegmentQuery,
} from '@/features/segments/composables/useSegments'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const toasts = useToasts()

const id = computed(() => Number(route.params.id))
const segmentQuery = useSegmentQuery(id)
const effortsQuery = useSegmentEffortsQuery(id)
const refreshMutation = useRefreshSegmentMutation()
const deleteMutation = useDeleteSegmentMutation()

const segment = computed(() => segmentQuery.data.value)
const efforts = computed(() => effortsQuery.data.value ?? [])
const confirmOpen = ref(false)

function refresh(): void {
  refreshMutation.mutate(id.value, {
    onSuccess: () => toasts.success(t('activities.segments.detail.refreshed')),
    onError: () => toasts.error(t('activities.segments.detail.refreshError')),
  })
}

function remove(): void {
  deleteMutation.mutate(id.value, {
    onSuccess: () => {
      confirmOpen.value = false
      toasts.success(t('activities.segments.detail.deleted'))
      void router.push({ name: 'segments' })
    },
    onError: () => toasts.error(t('activities.segments.detail.deleteError')),
  })
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <Skeleton v-if="segmentQuery.isPending.value" class="h-10 w-1/2" />
    <ErrorState
      v-else-if="segmentQuery.isError.value || !segment"
      :title="t('activities.segments.detail.loadError')"
      @retry="segmentQuery.refetch()"
    />
    <template v-else>
      <header class="flex flex-wrap items-end justify-between gap-2">
        <div class="flex flex-col gap-1">
          <h1 class="text-page-title">{{ segment.name }}</h1>
          <p class="text-body">
            {{
              t('activities.segments.radiusSummary', {
                start: segment.start.radiusM,
                end: segment.end.radiusM,
              })
            }}
          </p>
        </div>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" as-child>
            <router-link :to="{ name: 'segment-edit', params: { id: segment.id } }">
              <Pencil aria-hidden="true" />
              {{ t('activities.segments.detail.edit') }}
            </router-link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            :disabled="refreshMutation.isPending.value"
            @click="refresh"
          >
            <RefreshCw aria-hidden="true" />
            {{ t('activities.segments.detail.refresh') }}
          </Button>
          <Button variant="ghostDestructive" size="sm" @click="confirmOpen = true">
            <Trash2 aria-hidden="true" />
            {{ t('activities.segments.detail.delete') }}
          </Button>
        </div>
      </header>

      <Card class="p-3">
        <h2 class="mb-2 text-item-title">{{ t('activities.segments.detail.compare') }}</h2>
        <Skeleton v-if="effortsQuery.isPending.value" class="h-24 w-full" />
        <ErrorState
          v-else-if="effortsQuery.isError.value"
          :title="t('activities.segments.detail.loadError')"
          @retry="effortsQuery.refetch()"
        />
        <EmptyState
          v-else-if="efforts.length === 0"
          variant="filtered"
          :title="t('activities.segments.detail.noEfforts')"
        />
        <EffortsTable v-else :efforts="efforts" link-activities />
      </Card>

      <ConfirmDialog
        v-model:open="confirmOpen"
        :title="t('activities.segments.detail.deleteTitle')"
        :description="t('activities.segments.detail.deleteDescription', { name: segment.name })"
        :confirm-label="t('activities.segments.detail.delete')"
        :cancel-label="t('activities.segments.editor.cancel')"
        :close-label="t('activities.segments.detail.close')"
        :pending="deleteMutation.isPending.value"
        @confirm="remove"
      />
    </template>
  </section>
</template>
