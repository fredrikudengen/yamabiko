<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import GoogleHealthCard from '@/features/integrations/components/GoogleHealthCard.vue'

const { t } = useI18n()
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('settings.integrations.title') }}</h1>
      <p class="text-body">{{ t('settings.integrations.subtitle') }}</p>
    </div>

    <GoogleHealthCard />
  </div>
</template>
