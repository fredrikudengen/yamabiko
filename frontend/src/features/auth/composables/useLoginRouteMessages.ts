import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import type { Severity } from '@/types'

/** An inline alert shown on the login screen. */
export interface AlertState {
  kind: Severity
  message: string
}

/** Maps a boolean status query flag to a translation key and severity. */
const STATUS_FLAG_ALERTS: ReadonlyArray<{ query: string; kind: Severity; key: string }> = [
  { query: 'logoutSuccess', kind: 'success', key: 'login.loggedOut' },
  { query: 'sessionExpired', kind: 'warning', key: 'login.sessionExpired' },
  { query: 'passwordResetSuccess', kind: 'success', key: 'login.passwordResetSuccess' },
  { query: 'passwordResetInvalidLink', kind: 'error', key: 'login.passwordResetInvalidLink' },
  { query: 'emailVerificationSent', kind: 'info', key: 'login.emailVerificationSent' },
  { query: 'adminApprovalRequired', kind: 'info', key: 'login.adminApprovalRequired' },
  { query: 'verifyEmailInvalidLink', kind: 'error', key: 'login.verifyEmailInvalidLink' },
]

/**
 * Translates the login screen's status query parameters into a single alert.
 * Keeping this mapping out of the view makes the redirect states
 * independently testable.
 *
 * @returns A helper to resolve the initial alert.
 */
export function useLoginRouteMessages() {
  const route = useRoute()
  const { t } = useI18n()

  /**
   * Resolves the alert to show on first render from status query parameters.
   *
   * @returns The alert to display, or `null` when there is nothing to show.
   */
  function resolveInitialAlert(): AlertState | null {
    const statusMatch = STATUS_FLAG_ALERTS.find((entry) => route.query[entry.query] === 'true')
    if (statusMatch) {
      return { kind: statusMatch.kind, message: t(statusMatch.key) }
    }

    return null
  }

  return { resolveInitialAlert }
}
