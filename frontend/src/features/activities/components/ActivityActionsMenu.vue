<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { EllipsisVertical, Pencil, Trash2 } from '@lucide/vue'

import type { Activity } from '@/features/activities/types'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useToasts } from '@/composables/useToasts'
import { useDeleteActivityMutation } from '@/features/activities/composables/useActivityDetail'
import ActivityEditDialog from '@/features/activities/components/ActivityEditDialog.vue'

const props = defineProps<{
  /** The activity these owner-only actions apply to. */
  activity: Activity
}>()

const { t } = useI18n()
const router = useRouter()
const toasts = useToasts()

const deleteMutation = useDeleteActivityMutation()
const isDeleteOpen = ref(false)
const isEditOpen = ref(false)

/** Deletes the activity, then returns to the home feed. */
async function confirmDelete(): Promise<void> {
  try {
    await deleteMutation.mutateAsync(props.activity.id)
    isDeleteOpen.value = false
    toasts.success(t('activities.actions.deleteSuccess'))
    await router.push({ name: 'home' })
  } catch {
    toasts.error(t('activities.actions.deleteError'))
  }
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger
      class="flex cursor-pointer items-center rounded-input p-1 text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/30"
      :aria-label="t('activities.actions.menu')"
    >
      <EllipsisVertical class="size-5" />
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem @select="isEditOpen = true">
        <Pencil class="size-4" />
        <span>{{ t('activities.actions.edit') }}</span>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        class="text-destructive hover:bg-destructive/10 hover:text-destructive focus:bg-destructive/10 focus:text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive"
        @select="isDeleteOpen = true"
      >
        <Trash2 class="size-4" />
        <span>{{ t('activities.actions.delete') }}</span>
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>

  <ActivityEditDialog v-model:open="isEditOpen" :activity="activity" />

  <ConfirmDialog
    v-model:open="isDeleteOpen"
    :title="t('activities.actions.deleteTitle')"
    :description="t('activities.actions.deleteBody', { name: activity.name })"
    :confirm-label="t('activities.actions.delete')"
    :cancel-label="t('activities.actions.cancel')"
    :close-label="t('activities.actions.close')"
    :pending="deleteMutation.isPending.value"
    @confirm="confirmDelete"
  />
</template>
