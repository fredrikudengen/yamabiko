import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import { queryClient } from '@/plugins/vueQuery'
import { queryKeys } from '@/services/queryKeys'
import { getBackendAssetUrl } from '@/services/runtime'
import {
  DEFAULT_PUBLIC_SERVER_SETTINGS,
  fetchPublicServerSettings,
} from '@/features/config/services/serverSettings'
import defaultLoginImage from '@/assets/login.svg'

/** Shared cache lifetime so every auth screen reuses one fetch per window. */
const PUBLIC_SETTINGS_STALE_TIME = 5 * 60_000

/**
 * Loads the public server settings needed by the unauthenticated auth
 * screens (login, password reset). Failures fall back to safe defaults so the
 * auth screen always renders.
 *
 * @returns Reactive settings state, the resolved login image, and a `load`
 *   action that awaits the request.
 */
export function usePublicServerSettings() {
  // Use `placeholderData`, never `initialData`: `initialData` is written to the
  // query cache and, paired with a `staleTime`, is treated as a fresh fetch.
  // That suppresses the real request on mount and makes `ensureQueryData()` in
  // `load()` return the seeded defaults. `placeholderData` renders the same
  // safe defaults while the real settings are fetched.
  const settingsQuery = useQuery({
    queryKey: queryKeys.public.serverSettings(),
    queryFn: fetchPublicServerSettings,
    placeholderData: DEFAULT_PUBLIC_SERVER_SETTINGS,
    retry: 1,
    staleTime: PUBLIC_SETTINGS_STALE_TIME,
  })

  const serverSettings = computed(() => settingsQuery.data.value ?? DEFAULT_PUBLIC_SERVER_SETTINGS)

  /** Instance login photo when configured, else the bundled default image. */
  const loginImageUrl = computed(() =>
    serverSettings.value.login_photo_set
      ? getBackendAssetUrl('server_images/login.png')
      : defaultLoginImage,
  )

  /**
   * Ensures public server settings are cached. Backed by TanStack Query's
   * cache, so concurrent auth screens share one response, retries, and request
   * de-duplication.
   */
  async function load(): Promise<void> {
    await queryClient.ensureQueryData({
      queryKey: queryKeys.public.serverSettings(),
      queryFn: fetchPublicServerSettings,
      staleTime: PUBLIC_SETTINGS_STALE_TIME,
    })
  }

  return { serverSettings, loginImageUrl, load }
}
