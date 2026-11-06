import { useRoute, useRouter } from 'vue-router'
import { getQueryString } from '@/composables/useRouteQuery'

export { getQueryString } from '@/composables/useRouteQuery'

/**
 * Resolves redirect query values while blocking external redirects, to
 * prevent open-redirect attacks. Only internal paths are allowed; anything
 * else falls back to the app root.
 *
 * @param value - Raw redirect query value.
 * @returns A safe internal path, or `/` when unsafe.
 */
export function getSafeRedirect(value: unknown): string {
  const candidate = getQueryString(value)
  if (candidate.startsWith('/') && !candidate.startsWith('//') && !candidate.includes('://')) {
    return candidate
  }
  return '/'
}

/**
 * Redirect helpers bound to the active route/router. Centralises the
 * open-redirect protection used by every authentication entry point.
 *
 * @returns Safe redirect resolvers plus post-login navigation helpers.
 */
export function useSafeRedirect() {
  const route = useRoute()
  const router = useRouter()

  /**
   * Navigates to the post-login destination, honouring a safe `redirect`
   * query.
   */
  async function navigateAfterLogin(): Promise<void> {
    await router.replace(getSafeRedirect(route.query.redirect))
  }

  return {
    getSafeRedirect,
    getQueryString,
    navigateAfterLogin,
  }
}
