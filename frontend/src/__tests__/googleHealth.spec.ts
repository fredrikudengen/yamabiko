import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { flushPromises, mount } from '@vue/test-utils'

import type { GoogleHealthStatus } from '@/features/integrations/types'

import i18n from '@/i18n'
import { apiFetch } from '@/services/http'
import GoogleHealthCard from '@/features/integrations/components/GoogleHealthCard.vue'
import {
  fetchGoogleHealthStatus,
  startGoogleHealthLink,
  syncGoogleHealth,
  unlinkGoogleHealth,
} from '@/features/integrations/services/googleHealth'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

describe('googleHealth service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('maps the status DTO and never exposes tokens', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      configured: true,
      linked: true,
      access_token_expires_at: '2026-10-20T20:00:00+00:00',
      redirect_uri: 'http://localhost:8080/api/v1/googlehealth/callback',
    })

    const status = await fetchGoogleHealthStatus()

    expect(apiFetch).toHaveBeenCalledWith('/googlehealth/status', { signal: undefined })
    expect(status).toEqual({
      configured: true,
      linked: true,
      redirectUri: 'http://localhost:8080/api/v1/googlehealth/callback',
    })
  })

  it('startGoogleHealthLink POSTs and returns the consent URL', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ url: 'https://accounts.google.com/x' })

    await expect(startGoogleHealthLink()).resolves.toBe('https://accounts.google.com/x')
    expect(apiFetch).toHaveBeenCalledWith('/googlehealth/auth-url', { method: 'POST' })
  })

  it('syncGoogleHealth POSTs the number of days (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await syncGoogleHealth(30)

    expect(apiFetch).toHaveBeenCalledWith('/googlehealth/sync?days=30', {
      method: 'POST',
      responseType: 'void',
    })
  })

  it('unlinkGoogleHealth DELETEs the link (void)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await unlinkGoogleHealth()

    expect(apiFetch).toHaveBeenCalledWith('/googlehealth/link', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})

// --- Card ---------------------------------------------------------------

const status = ref<GoogleHealthStatus | undefined>()
const refetch = vi.fn<() => Promise<void>>()
const startMutate = vi.fn<(...args: unknown[]) => void>()
const routeQuery = ref<Record<string, string>>({})
const replace = vi.fn<(...args: unknown[]) => void>()
const toasts = {
  success: vi.fn<(...args: unknown[]) => void>(),
  error: vi.fn<(...args: unknown[]) => void>(),
  info: vi.fn<(...args: unknown[]) => void>(),
}

vi.mock('@/features/integrations/composables/useIntegrations', () => ({
  useGoogleHealthStatusQuery: () => ({
    data: status,
    isPending: ref(false),
    isError: ref(false),
    refetch,
  }),
  useStartGoogleHealthLinkMutation: () => ({ mutate: startMutate, isPending: ref(false) }),
  useSyncGoogleHealthMutation: () => ({
    mutate: vi.fn<(...args: unknown[]) => void>(),
    isPending: ref(false),
  }),
  useUnlinkGoogleHealthMutation: () => ({
    mutate: vi.fn<(...args: unknown[]) => void>(),
    isPending: ref(false),
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    get query() {
      return routeQuery.value
    },
  }),
  useRouter: () => ({ replace }),
}))

vi.mock('@/composables/useToasts', () => ({ useToasts: () => toasts }))

function mountCard() {
  return mount(GoogleHealthCard, {
    global: {
      plugins: [i18n],
      stubs: { ConfirmDialog: true, DropdownMenu: true, DropdownMenuTrigger: true },
    },
  })
}

describe('GoogleHealthCard', () => {
  beforeEach(() => {
    status.value = undefined
    routeQuery.value = {}
    refetch.mockReset().mockResolvedValue(undefined)
    startMutate.mockReset()
    replace.mockReset()
    Object.values(toasts).forEach((toast) => toast.mockReset())
  })

  it('disables connect and explains why when the server has no OAuth client', () => {
    status.value = { configured: false, linked: false, redirectUri: 'http://x/cb' }

    const wrapper = mountCard()

    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('GOOGLE_HEALTH_CLIENT_ID')
  })

  it('shows the redirect URI to register and starts linking on connect', async () => {
    status.value = {
      configured: true,
      linked: false,
      redirectUri: 'http://localhost:8080/api/v1/googlehealth/callback',
    }

    const wrapper = mountCard()
    expect(wrapper.text()).toContain('http://localhost:8080/api/v1/googlehealth/callback')

    await wrapper.find('button').trigger('click')

    expect(startMutate).toHaveBeenCalledTimes(1)
  })

  it('shows the connected badge when linked', () => {
    status.value = { configured: true, linked: true, redirectUri: 'http://x/cb' }

    expect(mountCard().text()).toContain('Connected')
  })

  it.each([
    ['linked', 'success'],
    ['denied', 'error'],
    ['scopes', 'error'],
    ['error', 'error'],
  ] as const)('reports ?googlehealth=%s once and clears the parameter', async (result, toast) => {
    status.value = { configured: true, linked: true, redirectUri: 'http://x/cb' }
    routeQuery.value = { googlehealth: result, other: '1' }

    mountCard()
    await flushPromises()

    expect(toasts[toast]).toHaveBeenCalledTimes(1)
    expect(refetch).toHaveBeenCalledTimes(1)
    expect(replace).toHaveBeenCalledWith({ query: { other: '1' } })
  })

  it('does nothing special without the result parameter', async () => {
    status.value = { configured: true, linked: true, redirectUri: 'http://x/cb' }

    mountCard()
    await flushPromises()

    expect(toasts.success).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })
})
