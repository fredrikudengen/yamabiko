<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { House, Map as MapIcon, Menu, Mountain, type LucideIcon } from '@lucide/vue'

import { useAuthStore } from '@/features/auth/stores/auth'

interface BottomNavLink {
  name: string
  label: string
  icon: LucideIcon
}

const { t } = useI18n()
const auth = useAuthStore()

/**
 * Leading destinations of the mobile bottom bar. Menu renders separately
 * because it has a fixed destination.
 */
const links = computed<BottomNavLink[]>(() => [
  { name: 'home', label: t('nav.home'), icon: House },
  { name: 'segments', label: t('nav.segments'), icon: Mountain },
  { name: 'coverage', label: t('nav.coverage'), icon: MapIcon },
])
</script>

<template>
  <!--
    Mobile primary navigation. Mirrors the v1 bottom navbar: a sticky bar
    pinned to the bottom on small screens (Home, Segments, Map, Menu),
    hidden from `lg` up where the top navbar takes over. Authenticated only.
  -->
  <nav
    v-if="auth.isAuthenticated"
    class="sticky bottom-0 z-40 flex items-stretch justify-around border-t border-border bg-card pb-safe lg:hidden"
    :aria-label="t('nav.primary')"
  >
    <RouterLink
      v-for="link in links"
      :key="link.name"
      :to="{ name: link.name }"
      class="flex flex-1 flex-col items-center gap-1 px-1 py-2 text-micro text-muted-foreground hover:text-foreground"
      active-class="text-foreground"
    >
      <component :is="link.icon" class="size-5" />
      <span class="truncate">{{ link.label }}</span>
    </RouterLink>

    <RouterLink
      :to="{ name: 'menu' }"
      class="flex flex-1 flex-col items-center gap-1 px-1 py-2 text-micro text-muted-foreground hover:text-foreground"
      active-class="text-foreground"
    >
      <Menu class="size-5" />
      <span class="truncate">{{ t('nav.menu') }}</span>
    </RouterLink>
  </nav>
</template>
