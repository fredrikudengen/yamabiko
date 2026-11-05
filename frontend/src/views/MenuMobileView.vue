<script setup lang="ts">
import { RouterLink, useRouter, type RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Activity, Calendar, LogOut, Settings, User } from '@lucide/vue'

import LocaleSwitcher from '@/components/LocaleSwitcher.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useAuthStore } from '@/features/auth/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

/** The profile entry opens profile settings: there are no public profile pages. */
const profileRoute: RouteLocationRaw = { name: 'settings-profile' }

/** Logs out and returns to the home screen. */
async function signOut(): Promise<void> {
  await auth.logout()
  await router.push({ name: 'login', query: { logoutSuccess: 'true' } })
}
</script>

<template>
  <!--
    Mobile-only "Menu" destination reached from the bottom navigation. Mirrors
    the v1 MenuMobileView: stacked, full-width, touch-friendly groups
    (Activities/Summary; Settings/Profile; Logout) plus the footer (which is
    hidden in the main shell on small screens).
  -->
  <section class="flex flex-col gap-3">
    <h1 class="text-page-title">
      {{ t('nav.menu') }}
    </h1>

    <template v-if="auth.isAuthenticated">
      <!-- Activities / Summary -->
      <Card padding="none" class="overflow-hidden">
        <RouterLink
          :to="{ name: 'activities' }"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Activity class="size-4" />
          <span>{{ t('nav.activities') }}</span>
        </RouterLink>
        <hr class="border-border" />
        <RouterLink
          :to="{ name: 'summary' }"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Calendar class="size-4" />
          <span>{{ t('nav.summary') }}</span>
        </RouterLink>
      </Card>

      <!-- Settings / Profile -->
      <Card padding="none" class="overflow-hidden">
        <RouterLink
          :to="{ name: 'settings' }"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Settings class="size-4" />
          <span>{{ t('nav.settings') }}</span>
        </RouterLink>
        <hr class="border-border" />
        <RouterLink
          :to="profileRoute"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <User class="size-4" />
          <span>{{ t('nav.profile') }}</span>
        </RouterLink>
      </Card>

      <!-- Preferences -->
      <div class="flex flex-col">
        <p class="mb-1 px-1 text-caption">
          {{ t('nav.preferences') }}
        </p>
        <Card padding="none" class="flex items-center justify-between gap-3 px-4 py-3">
          <LocaleSwitcher />
          <ThemeToggle />
        </Card>
      </div>

      <!-- Session -->
      <Button variant="destructive" class="w-full" @click="signOut">
        <LogOut class="size-4" />
        <span>{{ t('nav.logout') }}</span>
      </Button>
    </template>

    <AppFooter />
  </section>
</template>
