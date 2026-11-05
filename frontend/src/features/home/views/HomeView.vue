<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Activity as ActivityIcon, Plus } from '@lucide/vue'

import HomeProfileCard from '@/features/home/components/HomeProfileCard.vue'
import UserDistanceStats from '@/features/home/components/UserDistanceStats.vue'
import HomeActivityCard from '@/features/home/components/HomeActivityCard.vue'
import HomeActivityCardSkeleton from '@/features/home/components/HomeActivityCardSkeleton.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useDisplayUnits } from '@/features/activities/composables/useActivityDetail'
import { ACTIVITY_FILE_EXTENSIONS } from '@/features/upload/types'
import { useUploadActivityFileMutation } from '@/features/upload/composables/useUpload'
import {
  useActivityStatsQuery,
  useUserActivitiesFeed,
} from '@/features/home/composables/useHome'

const { t } = useI18n()
const toasts = useToasts()

const { data: currentUser } = useCurrentUser()
const units = useDisplayUnits()
const currentUserId = computed(() => currentUser.value?.id ?? null)

// --- Distance stats (left) ---
const weekStats = useActivityStatsQuery(currentUserId, 'week')
const monthStats = useActivityStatsQuery(currentUserId, 'month')

// --- Feed (center) ---
const feed = useUserActivitiesFeed(currentUserId)

const activities = computed(() => feed.data.value?.pages.flat() ?? [])
const isPending = computed(() => feed.isPending.value)
const isError = computed(() => feed.isError.value)
const hasNextPage = computed(() => feed.hasNextPage.value)
const isFetchingNextPage = computed(() => feed.isFetchingNextPage.value)
const isEmpty = computed(() => !isPending.value && !isError.value && activities.value.length === 0)

/** Fetches the next page of the feed. */
function fetchNextPage(): void {
  void feed.fetchNextPage()
}

/** Refetches the feed after an error. */
function refetchFeed(): void {
  void feed.refetch()
}

const sentinel = ref<HTMLElement | null>(null)
useInfiniteScroll(sentinel, () => fetchNextPage(), {
  enabled: () => hasNextPage.value && !isFetchingNextPage.value,
})

// --- Add activity (file upload) ---
const fileInput = ref<HTMLInputElement | null>(null)
const uploadMutation = useUploadActivityFileMutation()
const acceptedFileTypes = ACTIVITY_FILE_EXTENSIONS.map((ext) => `.${ext}`).join(',')

/**
 * Whether to show a placeholder card at the top of the feed while an upload is
 * in flight; the new activity lands there once the upload resolves.
 */
const showUploadPlaceholder = computed(() => uploadMutation.isPending.value)

/** Opens the hidden file picker. */
function pickFile(): void {
  fileInput.value?.click()
}

/** Uploads the chosen file, surfacing the outcome as a toast. */
function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  uploadMutation.mutate(file, {
    onSuccess: () => toasts.success(t('home.upload.success')),
    onError: () => toasts.error(t('home.upload.error')),
  })
}
</script>

<template>
  <div class="grid grid-cols-1 gap-3 lg:grid-cols-12">
    <!-- Left sidebar -->
    <aside class="flex flex-col gap-3 lg:col-span-3">
      <!-- Profile (photo + username) — hidden on small screens. -->
      <div class="hidden lg:block">
        <HomeProfileCard
          v-if="currentUser"
          :name="currentUser.name"
          :username="currentUser.username"
          :avatar-url="currentUser.avatarUrl"
        />
        <Card v-else class="flex flex-col items-center gap-3">
          <Skeleton class="size-20 rounded-full" />
          <Skeleton class="h-5 w-32" />
          <Skeleton class="h-4 w-24" />
        </Card>
      </div>

      <!-- Actions -->
      <Card class="flex flex-col gap-2">
        <Button :disabled="uploadMutation.isPending.value" @click="pickFile">
          <Plus class="size-4" aria-hidden="true" />
          {{ uploadMutation.isPending.value ? t('home.upload.uploading') : t('home.addActivity') }}
        </Button>
        <input
          ref="fileInput"
          type="file"
          class="hidden"
          :accept="acceptedFileTypes"
          @change="onFileChange"
        />
      </Card>

      <!-- Distance stats — hidden on small screens. -->
      <div class="hidden lg:block">
        <UserDistanceStats
          :week-stats="weekStats.data.value"
          :month-stats="monthStats.data.value"
          :units="units"
          :is-loading="weekStats.isLoading.value || monthStats.isLoading.value"
        />
      </div>
    </aside>

    <!-- Center feed -->
    <section class="flex flex-col gap-3 lg:col-span-9">
      <!-- Loading -->
      <div v-if="isPending" class="flex flex-col gap-3" aria-busy="true">
        <HomeActivityCardSkeleton v-for="n in 3" :key="n" />
      </div>

      <!-- Error -->
      <ErrorState
        v-else-if="isError"
        :title="t('home.feed.error.title')"
        :description="t('home.feed.error.description')"
        @retry="refetchFeed"
      >
        <template #action="{ retry }">
          <Button variant="outline" @click="retry">{{ t('home.feed.error.retry') }}</Button>
        </template>
      </ErrorState>

      <!-- Empty -->
      <EmptyState
        v-else-if="isEmpty && !showUploadPlaceholder"
        :title="t('home.feed.empty.mine.title')"
        :description="t('home.feed.empty.mine.description')"
      >
        <template #icon>
          <ActivityIcon class="size-8" aria-hidden="true" />
        </template>
      </EmptyState>

      <!-- Feed -->
      <template v-else>
        <!-- Placeholder for an activity currently being uploaded. -->
        <HomeActivityCardSkeleton v-if="showUploadPlaceholder" />

        <HomeActivityCard
          v-for="activity in activities"
          :key="activity.id"
          :activity="activity"
          :units="units"
          :current-user-id="currentUserId"
        />

        <!-- Infinite-scroll sentinel + accessible manual fallback. -->
        <div v-if="hasNextPage" ref="sentinel" class="flex justify-center">
          <Button variant="ghost" :disabled="isFetchingNextPage" @click="fetchNextPage">
            {{ isFetchingNextPage ? t('home.feed.loading') : t('home.feed.loadMore') }}
          </Button>
        </div>
      </template>
    </section>
  </div>
</template>
