<script setup lang="ts">
/**
 * Presentational split-card shell shared by the login and sign-up screens: a
 * brand image column on large screens and a centered content column that
 * renders the default slot. Screens own their own form/markup; this component
 * only owns the surrounding chrome.
 */
defineProps<{
  /** Source URL for the brand image shown in the left column. */
  imageUrl: string
  /** Accessible alt text for the brand image. */
  imageAlt: string
}>()
</script>

<template>
  <section class="mx-auto w-full max-w-7xl">
    <div
      class="grid overflow-hidden rounded-card border border-border bg-card p-3 lg:grid-cols-2 lg:gap-3"
    >
      <!-- Brand image, hidden on small screens. -->
      <div class="relative hidden overflow-hidden rounded-input lg:block">
        <img
          width="640"
          height="640"
          :src="imageUrl"
          :alt="imageAlt"
          class="h-full min-h-[520px] w-full object-cover"
        />
      </div>

      <div class="flex min-h-[520px] flex-col justify-center px-2 py-6 sm:px-6 lg:px-8">
        <slot />
      </div>
    </div>
  </section>
</template>
