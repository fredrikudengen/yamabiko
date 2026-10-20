import type { GoogleHealthStatus, GoogleHealthStatusDto } from '@/features/integrations/types'

import { apiFetch } from '@/services/http'

/**
 * Reads whether the server is configured for Google Health and whether the
 * current user has linked an account.
 *
 * @param signal - Optional abort signal from the query.
 * @returns The link status.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGoogleHealthStatus(signal?: AbortSignal): Promise<GoogleHealthStatus> {
  const dto = await apiFetch<GoogleHealthStatusDto>('/googlehealth/status', { signal })
  return {
    configured: dto.configured,
    linked: dto.linked,
    redirectUri: dto.redirect_uri,
  }
}

/**
 * Starts linking: the server stores a one-time state and returns Google's
 * consent URL, which the caller sends the browser to (full page). Google then
 * redirects to the server's callback, which returns here with
 * `?googlehealth=linked|denied|scopes|error`.
 *
 * @returns The absolute Google consent URL.
 * @throws {HttpError} When the request fails (503 when the server has no OAuth client).
 */
export async function startGoogleHealthLink(): Promise<string> {
  const { url } = await apiFetch<{ url: string }>('/googlehealth/auth-url', { method: 'POST' })
  return url
}

/**
 * Starts a background import of the last `days` days of Google Health exercises.
 *
 * @param days - How many days back to look (the server caps it at 60).
 * @throws {HttpError} When the request fails (409 when not linked).
 */
export async function syncGoogleHealth(days: number): Promise<void> {
  await apiFetch(`/googlehealth/sync?days=${encodeURIComponent(String(days))}`, {
    method: 'POST',
    responseType: 'void',
  })
}

/**
 * Forgets the stored Google Health tokens.
 *
 * @throws {HttpError} When the request fails.
 */
export async function unlinkGoogleHealth(): Promise<void> {
  await apiFetch('/googlehealth/link', { method: 'DELETE', responseType: 'void' })
}
