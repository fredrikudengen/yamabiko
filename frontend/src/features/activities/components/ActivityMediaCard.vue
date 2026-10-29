<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ImagePlus, Trash2 } from '@lucide/vue'

import type { ActivityMedia } from '@/features/activities/types'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Image } from '@/components/ui/image'
import { Spinner } from '@/components/ui/spinner'
import { useToasts } from '@/composables/useToasts'
import PhotoLightbox from '@/features/activities/components/PhotoLightbox.vue'
import {
  useActivityMediaQuery,
  useDeleteActivityMediaMutation,
  useUploadActivityMediaMutation,
} from '@/features/activities/composables/useActivityDetail'

const props = withDefaults(
  defineProps<{
    /** The activity whose photos are shown. */
    activityId: number
    /** Whether the viewer owns the activity: gates the upload and delete buttons. */
    isOwner?: boolean
  }>(),
  { isOwner: false },
)

const { t } = useI18n()
const toasts = useToasts()

const { data: media } = useActivityMediaQuery(() => props.activityId)
const uploadMutation = useUploadActivityMediaMutation(() => props.activityId)
const deleteMutation = useDeleteActivityMediaMutation(() => props.activityId)

const photos = computed(() => media.value ?? [])
// The owner always sees the card, to be able to add the first photo; others only when there is one.
const visible = computed(() => props.isOwner || photos.value.length > 0)

// ── Upload ────────────────────────────────────────────────────────────────────
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

/** Opens the native file picker. */
function openFilePicker(): void {
  fileInput.value?.click()
}

/**
 * Uploads the chosen images one after the other and says how it went once, for the whole batch.
 * Files that are not images are skipped, and the input is cleared so the same file can be picked again.
 */
async function onFilesSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (files.length === 0) {
    return
  }
  const images = files.filter((file) => file.type.startsWith('image/'))
  if (images.length < files.length) {
    toasts.error(t('activities.media.invalidType'))
  }
  if (images.length === 0) {
    return
  }
  uploading.value = true
  let uploaded = 0
  for (const image of images) {
    try {
      await uploadMutation.mutateAsync(image)
      uploaded += 1
    } catch {
      // Counted below: one message for the whole batch, not one per failed file.
    }
  }
  uploading.value = false
  if (uploaded === images.length) {
    toasts.success(
      uploaded === 1
        ? t('activities.media.uploadSuccess')
        : t('activities.media.uploadSuccessMany', { count: uploaded }),
    )
  } else if (uploaded === 0) {
    toasts.error(t('activities.media.uploadError'))
  } else {
    toasts.error(t('activities.media.uploadPartial', { done: uploaded, total: images.length }))
  }
}

// ── Viewer ────────────────────────────────────────────────────────────────────
const lightboxOpen = ref(false)
const lightboxIndex = ref(0)

/** Opens the viewer at the photo at `index`. */
function openLightbox(index: number): void {
  lightboxIndex.value = index
  lightboxOpen.value = true
}

// ── Delete ────────────────────────────────────────────────────────────────────
const pendingDelete = ref<ActivityMedia | null>(null)
const isDeleteOpen = ref(false)

/** Opens the delete confirmation for a photo. */
function requestDelete(item: ActivityMedia): void {
  pendingDelete.value = item
  isDeleteOpen.value = true
}

/** Deletes the pending photo, then closes the dialog. */
async function confirmDelete(): Promise<void> {
  if (!pendingDelete.value) {
    return
  }
  try {
    await deleteMutation.mutateAsync(pendingDelete.value.id)
    isDeleteOpen.value = false
    toasts.success(t('activities.media.deleteSuccess'))
  } catch {
    toasts.error(t('activities.media.deleteError'))
  }
}
</script>

<template>
  <Card v-if="visible" class="flex flex-col gap-3">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-card-heading">{{ t('activities.media.title') }}</h2>
      <Button
        v-if="isOwner"
        type="button"
        variant="outline"
        size="sm"
        :disabled="uploading"
        @click="openFilePicker"
      >
        <Spinner v-if="uploading" size="sm" />
        <ImagePlus v-else class="size-4" />
        {{ t('activities.media.addMedia') }}
      </Button>
    </div>

    <input
      v-if="isOwner"
      ref="fileInput"
      type="file"
      accept="image/*"
      multiple
      class="hidden"
      data-testid="media-file-input"
      @change="onFilesSelected"
    />

    <p v-if="photos.length === 0" class="text-hint">{{ t('activities.media.empty') }}</p>

    <ul v-else class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      <li
        v-for="(photo, index) in photos"
        :key="photo.id"
        class="relative aspect-square overflow-hidden rounded-input bg-muted"
      >
        <button
          type="button"
          class="size-full cursor-zoom-in focus-visible:outline-none"
          :aria-label="t('activities.media.expand')"
          @click="openLightbox(index)"
        >
          <Image :src="photo.url" :alt="t('activities.media.alt')" class="size-full object-cover" />
        </button>
        <button
          v-if="isOwner"
          type="button"
          class="absolute right-1.5 bottom-1.5 z-10 flex size-8 items-center justify-center rounded-full bg-card/80 text-destructive backdrop-blur transition-colors hover:bg-destructive/10"
          :aria-label="t('activities.media.deleteTitle')"
          @click="requestDelete(photo)"
        >
          <Trash2 class="size-4" />
        </button>
      </li>
    </ul>
  </Card>

  <PhotoLightbox v-model:open="lightboxOpen" v-model:index="lightboxIndex" :photos="photos" />

  <ConfirmDialog
    v-model:open="isDeleteOpen"
    :title="t('activities.media.deleteTitle')"
    :description="t('activities.media.deleteBody')"
    :confirm-label="t('activities.media.delete')"
    :cancel-label="t('activities.media.cancel')"
    :close-label="t('activities.media.close')"
    :pending="deleteMutation.isPending.value"
    @confirm="confirmDelete"
  />
</template>
