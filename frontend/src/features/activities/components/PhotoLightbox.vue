<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, ChevronRight, X } from '@lucide/vue'

import type { ActivityMedia } from '@/features/activities/types'

import { Image } from '@/components/ui/image'

const props = defineProps<{
  /** The photos to step through. */
  photos: ActivityMedia[]
}>()

/** Whether the viewer is open. */
const open = defineModel<boolean>('open', { required: true })
/** Index of the photo shown. */
const index = defineModel<number>('index', { default: 0 })

const { t } = useI18n()

/** Shows the photo at `next`, kept within the list. */
function go(next: number): void {
  index.value = Math.min(Math.max(next, 0), props.photos.length - 1)
}

function close(): void {
  open.value = false
}

/** Escape closes the viewer, the arrow keys step through the photos. */
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    close()
  } else if (event.key === 'ArrowLeft') {
    go(index.value - 1)
  } else if (event.key === 'ArrowRight') {
    go(index.value + 1)
  }
}

// Listen only while the viewer is open, so a closed one never takes the arrow keys.
watch(
  open,
  (isOpen) => {
    if (isOpen) {
      document.addEventListener('keydown', onKeydown)
    } else {
      document.removeEventListener('keydown', onKeydown)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="lightbox">
      <div
        v-if="open"
        role="dialog"
        aria-modal="true"
        :aria-label="t('activities.gallery.lightbox')"
        class="fixed inset-0 z-[2000] flex items-center justify-center bg-black/90"
        @click.self="close"
      >
        <Image
          v-if="photos[index]"
          :src="photos[index]!.url"
          :alt="t('activities.media.alt')"
          class="max-h-screen max-w-full object-contain p-4"
        />

        <button
          type="button"
          class="absolute top-4 right-4 flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20"
          :aria-label="t('activities.gallery.close')"
          @click="close"
        >
          <X class="size-5" />
        </button>

        <template v-if="photos.length > 1">
          <button
            type="button"
            class="absolute left-4 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 disabled:opacity-30"
            :disabled="index === 0"
            :aria-label="t('activities.gallery.previous')"
            @click="go(index - 1)"
          >
            <ChevronLeft class="size-6" />
          </button>
          <button
            type="button"
            class="absolute right-4 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 disabled:opacity-30"
            :disabled="index === photos.length - 1"
            :aria-label="t('activities.gallery.next')"
            @click="go(index + 1)"
          >
            <ChevronRight class="size-6" />
          </button>

          <p class="absolute inset-x-0 bottom-5 text-center text-sm text-white/70">
            {{ index + 1 }} / {{ photos.length }}
          </p>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.lightbox-enter-active,
.lightbox-leave-active {
  transition: opacity 0.18s ease;
}
.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
}
</style>
