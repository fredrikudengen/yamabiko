<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useToasts } from '@/composables/useToasts'
import { useImportStravaActivitiesMutation } from '@/features/import/composables/useImport'

const { t } = useI18n()
const toasts = useToasts()

const activitiesMutation = useImportStravaActivitiesMutation()

function importActivities(): void {
  activitiesMutation.mutate(undefined, {
    onSuccess: () => toasts.info(t('settings.import.strava.activitiesQueued')),
    onError: () => toasts.error(t('settings.import.strava.activitiesError')),
  })
}
</script>

<template>
  <Card class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex min-w-0 items-center gap-3">
      <img
        :src="INTEGRATION_LOGOS.stravaMark"
        :alt="t('settings.import.strava.title')"
        class="size-10 shrink-0 object-contain rounded"
      />
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <h2 class="text-card-heading">{{ t('settings.import.strava.title') }}</h2>
          <Badge variant="secondary">{{ t('settings.import.beta') }}</Badge>
        </div>
        <p class="text-hint">{{ t('settings.import.strava.subtitle') }}</p>
      </div>
    </div>

    <Button
      variant="outline"
      size="sm"
      :disabled="activitiesMutation.isPending.value"
      @click="importActivities"
    >
      {{ t('settings.import.strava.activities') }}
    </Button>
  </Card>
</template>
