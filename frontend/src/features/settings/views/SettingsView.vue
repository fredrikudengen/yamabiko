<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import SettingsNav from '@/features/settings/components/SettingsNav.vue'

/**
 * Settings shell. Renders the page heading and a two-column layout — the zone
 * sidebar beside the active zone (a nested child route) — mirroring the gears
 * list shell. Below `lg` the sidebar collapses to the top of the flow so the
 * same content appears at every breakpoint.
 */
const { t } = useI18n()
</script>

<template>
  <section class="flex flex-col gap-3">
    <div class="grid gap-3 lg:grid-cols-[16rem_minmax(0,1fr)] lg:items-start">
      <aside class="flex flex-col gap-3 lg:sticky lg:top-6">
        <header class="flex flex-col gap-1">
          <h1 class="text-page-title">{{ t('settings.title') }}</h1>
          <p class="text-body">{{ t('settings.subtitle') }}</p>
        </header>

        <SettingsNav />
      </aside>

      <RouterView />
    </div>
  </section>
</template>
