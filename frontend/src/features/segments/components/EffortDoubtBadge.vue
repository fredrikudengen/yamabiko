<script setup lang="ts">
/**
 * A small mark on a pass whose time may be off, with the reasons on hover. The
 * pass keeps its rank; the mark says to read the time with care.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { EffortDoubt } from '@/features/segments/types'

import { Badge } from '@/components/ui/badge'

const props = defineProps<{ doubts: EffortDoubt[] }>()

const { t } = useI18n()

const reasons = computed(() =>
  props.doubts.map((doubt) => t(`activities.segments.doubt.reason.${doubt}`)).join(' '),
)
</script>

<template>
  <Badge
    v-if="doubts.length > 0"
    variant="warning"
    :title="reasons"
    :aria-label="`${t('activities.segments.doubt.label')}: ${reasons}`"
    data-testid="effort-doubt"
  >
    {{ t('activities.segments.doubt.label') }}
  </Badge>
</template>
