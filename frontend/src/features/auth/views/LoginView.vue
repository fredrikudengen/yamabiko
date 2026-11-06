<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import ForgotPasswordDialog from '@/features/auth/components/ForgotPasswordDialog.vue'
import AppLogo from '@/components/AppLogo.vue'
import AuthScreenLayout from '@/components/layout/AuthScreenLayout.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAppConfig } from '@/features/config/composables/useAppConfig'
import {
  type AlertState,
  useLoginRouteMessages,
} from '@/features/auth/composables/useLoginRouteMessages'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { useSafeRedirect } from '@/composables/useSafeRedirect'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { useAuthStore } from '@/features/auth/stores/auth'

const auth = useAuthStore()
const { t } = useI18n()
const { config } = useAppConfig()
const { loginImageUrl, load } = usePublicServerSettings()
const { navigateAfterLogin } = useSafeRedirect()
const { resolveInitialAlert } = useLoginRouteMessages()
const toasts = useToasts()

const username = ref('')
const password = ref('')
const mfaCode = ref('')
const pendingUsername = ref('')
const isLoading = ref(false)
const isForgotPasswordOpen = ref(false)
const alert = ref<AlertState | null>(null)

const isMfaStep = computed(() => pendingUsername.value.length > 0)
const canSubmit = computed(() =>
  isMfaStep.value
    ? mfaCode.value.trim().length > 0
    : username.value.trim().length > 0 && password.value.length > 0,
)
const statusText = computed(() =>
  isMfaStep.value ? t('login.verifyingMfa') : t('login.signingIn'),
)
const submitText = computed(() =>
  isMfaStep.value ? t('login.verifyMfaButton') : t('login.signInButton'),
)

/**
 * Maps a backend HTTP error to a non-enumerating user-facing message.
 *
 * @param error - Caught auth error.
 * @param duringMfa - Whether the failed request was MFA verification.
 * @returns Translated error message.
 */
function getAuthErrorMessage(error: unknown, duringMfa: boolean): string {
  if (!(error instanceof HttpError)) {
    return t('login.genericError')
  }

  if (duringMfa && [400, 401].includes(error.status)) {
    return t('login.invalidMfa')
  }

  switch (error.status) {
    case 401:
      return t('login.invalidCredentials')
    case 403:
      return t('login.forbidden')
    case 429:
      return t('login.tooManyAttempts')
    case 503:
      return t('login.unavailable')
    default:
      return t('login.genericError')
  }
}

/**
 * Submits either the password form or the MFA verification form.
 */
async function submitForm(): Promise<void> {
  if (!canSubmit.value || isLoading.value) {
    return
  }

  isLoading.value = true
  alert.value = null
  const duringMfa = isMfaStep.value

  try {
    const result = duringMfa
      ? await auth.verifyMfa(pendingUsername.value, mfaCode.value.trim().toUpperCase())
      : await auth.login(username.value.trim(), password.value)

    if (result.status === 'mfa-required') {
      pendingUsername.value = result.username
      password.value = ''
      alert.value = { kind: 'info', message: t('login.mfaRequired') }
      return
    }

    await navigateAfterLogin()
  } catch (error) {
    if (duringMfa) {
      mfaCode.value = ''
    } else {
      password.value = ''
    }
    alert.value = { kind: 'error', message: getAuthErrorMessage(error, duringMfa) }
  } finally {
    isLoading.value = false
  }
}

/**
 * Surfaces a successful password reset request as a toast.
 *
 * @param message - Localised success message.
 */
function onForgotPasswordSuccess(message: string): void {
  toasts.success(message)
}

/**
 * Surfaces a failed password reset request as a toast (visible above the
 * still-open dialog).
 *
 * @param message - Localised error message.
 */
function onForgotPasswordError(message: string): void {
  toasts.error(message)
}

onMounted(async () => {
  await load()

  // Navigation/status messages are shown as toasts (out of layout flow) so the
  // card never grows on load; credential errors stay inline (see submitForm).
  const initialAlert = resolveInitialAlert()
  if (initialAlert) {
    toasts.notify(initialAlert.kind, initialAlert.message)
  }
})
</script>

<template>
  <AuthScreenLayout :image-url="loginImageUrl" :image-alt="t('login.imageAlt')">
    <form class="mx-auto flex w-full max-w-sm flex-col" novalidate @submit.prevent="submitForm">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />
      <h1 class="text-center text-page-title">
        {{ config.branding.appName }}
      </h1>

      <!-- Subtitle on mobile, where the photo and its overlay are hidden. -->
      <p class="mt-2 text-center text-body">
        {{ t('login.subtitle') }}
      </p>

      <Alert v-if="alert" :kind="alert.kind" class="mt-5">
        {{ alert.message }}
      </Alert>

      <div class="mt-5 flex flex-col gap-3">
        <template v-if="!isMfaStep">
          <div class="flex flex-col gap-1.5">
            <Label for="login-username">
              {{ t('login.username') }}
            </Label>
            <Input
              id="login-username"
              v-model="username"
              name="username"
              type="text"
              autocomplete="username"
              required
              :placeholder="t('login.username')"
              :disabled="isLoading"
            />
          </div>

          <div class="flex flex-col gap-1.5">
            <Label for="login-password">
              {{ t('login.password') }}
            </Label>
            <PasswordInput
              id="login-password"
              v-model="password"
              name="password"
              autocomplete="current-password"
              :placeholder="t('login.password')"
              :disabled="isLoading"
            />
          </div>
        </template>

        <div v-else class="flex flex-col gap-1.5">
          <Label for="login-mfa-code">
            {{ t('login.mfaCode') }}
          </Label>
          <Input
            id="login-mfa-code"
            v-model="mfaCode"
            name="mfaCode"
            type="text"
            autocomplete="one-time-code"
            required
            :disabled="isLoading"
          />
          <p class="text-hint">{{ t('login.mfaCodeHelp') }}</p>
        </div>

        <Button class="w-full" type="submit" :disabled="!canSubmit || isLoading">
          <LoaderCircle v-if="isLoading" class="size-4 animate-spin" aria-hidden="true" />
          <span>{{ isLoading ? statusText : submitText }}</span>
        </Button>

        <button
          v-if="!isMfaStep"
          type="button"
          class="self-center text-meta text-muted-foreground hover:text-foreground"
          @click="isForgotPasswordOpen = true"
        >
          {{ t('login.forgotPassword') }}
        </button>
      </div>
    </form>
  </AuthScreenLayout>

  <ForgotPasswordDialog
    v-model:open="isForgotPasswordOpen"
    @success="onForgotPasswordSuccess"
    @error="onForgotPasswordError"
  />
</template>
