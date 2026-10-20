<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ChevronDown, HeartPulse } from '@lucide/vue'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import {
  useGoogleHealthStatusQuery,
  useStartGoogleHealthLinkMutation,
  useSyncGoogleHealthMutation,
  useUnlinkGoogleHealthMutation,
} from '@/features/integrations/composables/useIntegrations'

/** Days looked back by the two sync menu items. */
const SYNC_DAYS_RECENT = 7
const SYNC_DAYS_LONG = 30

const { t } = useI18n()
const toasts = useToasts()
const route = useRoute()
const router = useRouter()

const statusQuery = useGoogleHealthStatusQuery()
const startMutation = useStartGoogleHealthLinkMutation()
const syncMutation = useSyncGoogleHealthMutation()
const unlinkMutation = useUnlinkGoogleHealthMutation()

const isUnlinkOpen = ref(false)
// Held true through the full-page redirect so the button stays busy.
const isRedirecting = ref(false)

/** Sends the browser to Google's consent page; Google returns via the server callback. */
function connect(): void {
  startMutation.mutate(undefined, {
    onSuccess: (url) => {
      isRedirecting.value = true
      window.location.assign(url)
    },
    onError: () => toasts.error(t('settings.integrations.googleHealth.connectError')),
  })
}

function sync(days: number): void {
  syncMutation.mutate(days, {
    onSuccess: () => toasts.info(t('settings.integrations.googleHealth.syncing')),
    onError: () => toasts.error(t('settings.integrations.googleHealth.syncError')),
  })
}

function confirmUnlink(): void {
  unlinkMutation.mutate(undefined, {
    onSuccess: () => {
      isUnlinkOpen.value = false
      toasts.success(t('settings.integrations.googleHealth.unlinkSuccess'))
    },
    onError: () => toasts.error(t('settings.integrations.googleHealth.unlinkError')),
  })
}

/**
 * The server callback sends the browser back with `?googlehealth=<result>`.
 * Show the outcome once, refresh the status and drop the parameter.
 */
onMounted(() => {
  const result = route.query.googlehealth
  if (typeof result !== 'string') {
    return
  }
  if (result === 'linked') {
    toasts.success(t('settings.integrations.googleHealth.linkSuccess'))
  } else if (result === 'denied') {
    toasts.error(t('settings.integrations.googleHealth.linkDenied'))
  } else if (result === 'scopes') {
    toasts.error(t('settings.integrations.googleHealth.linkScopes'))
  } else {
    toasts.error(t('settings.integrations.googleHealth.connectError'))
  }
  void statusQuery.refetch()
  const rest = { ...route.query }
  delete rest.googlehealth
  void router.replace({ query: rest })
})
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <div
          class="flex size-10 shrink-0 items-center justify-center rounded bg-muted text-foreground"
          aria-hidden="true"
        >
          <HeartPulse class="size-6" />
        </div>
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="text-card-heading">{{ t('settings.integrations.googleHealth.title') }}</h2>
            <Badge v-if="statusQuery.data.value?.linked" variant="secondary">
              {{ t('settings.integrations.connected') }}
            </Badge>
          </div>
          <p class="text-hint">{{ t('settings.integrations.googleHealth.subtitle') }}</p>
        </div>
      </div>

      <Skeleton v-if="statusQuery.isPending.value" class="h-9 w-24" />

      <Button
        v-else-if="statusQuery.data.value && !statusQuery.data.value.linked"
        size="sm"
        :disabled="
          !statusQuery.data.value.configured || startMutation.isPending.value || isRedirecting
        "
        @click="connect"
      >
        {{ t('settings.integrations.connect') }}
      </Button>

      <DropdownMenu v-else-if="statusQuery.data.value?.linked">
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm">
            {{ t('settings.integrations.options') }}
            <ChevronDown class="size-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-56">
          <DropdownMenuItem
            :disabled="syncMutation.isPending.value"
            @select="sync(SYNC_DAYS_RECENT)"
          >
            {{ t('settings.integrations.googleHealth.syncRecent', { days: SYNC_DAYS_RECENT }) }}
          </DropdownMenuItem>
          <DropdownMenuItem :disabled="syncMutation.isPending.value" @select="sync(SYNC_DAYS_LONG)">
            {{ t('settings.integrations.googleHealth.syncLong', { days: SYNC_DAYS_LONG }) }}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem @select="connect">
            {{ t('settings.integrations.relink') }}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            class="text-destructive hover:bg-destructive/10 hover:text-destructive focus:bg-destructive/10 focus:text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive"
            @select="isUnlinkOpen = true"
          >
            {{ t('settings.integrations.unlink') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <p v-if="statusQuery.isError.value" class="text-hint text-destructive" role="alert">
      {{ t('settings.integrations.googleHealth.statusError') }}
    </p>
    <p
      v-else-if="statusQuery.data.value && !statusQuery.data.value.configured"
      class="text-hint"
      role="status"
    >
      {{ t('settings.integrations.googleHealth.notConfigured') }}
    </p>
    <p v-else-if="statusQuery.data.value && !statusQuery.data.value.linked" class="text-hint">
      {{
        t('settings.integrations.googleHealth.redirectHint', {
          uri: statusQuery.data.value.redirectUri,
        })
      }}
    </p>

    <ConfirmDialog
      v-model:open="isUnlinkOpen"
      :title="t('settings.integrations.googleHealth.unlinkTitle')"
      :description="t('settings.integrations.googleHealth.unlinkBody')"
      :confirm-label="t('settings.integrations.unlink')"
      :cancel-label="t('settings.integrations.cancel')"
      :close-label="t('settings.integrations.close')"
      :pending="unlinkMutation.isPending.value"
      @confirm="confirmUnlink"
    />
  </Card>
</template>
