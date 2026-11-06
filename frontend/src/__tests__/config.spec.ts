import { describe, expect, it, vi } from 'vitest'

import type { PublicServerSettings } from '@/features/config/types'

import {
  DEFAULT_APP_CONFIG,
  fetchAppConfig,
  mapServerSettingsToAppConfig,
} from '@/features/config/services/config'
import { fetchPublicServerSettings } from '@/features/config/services/serverSettings'

vi.mock('@/features/config/services/serverSettings', () => ({
  fetchPublicServerSettings: vi.fn<typeof fetchPublicServerSettings>(),
}))

const publicSettings: PublicServerSettings = {
  login_photo_set: false,
  signup_enabled: true,
  units: 'metric',
  currency: 'euro',
  password_type: 'strict',
  password_length_regular_users: 8,
  password_length_admin_users: 12,
  num_records_per_page: 25,
  tileserver_url: 'https://tiles.test/{z}/{x}/{y}.png',
  tileserver_attribution: '&copy; Test tiles',
}

describe('mapServerSettingsToAppConfig', () => {
  it('keeps self-hosted defaults for fields the public settings do not carry', () => {
    const config = mapServerSettingsToAppConfig(publicSettings)

    expect(config.features.federation).toBe(DEFAULT_APP_CONFIG.features.federation)
    expect(config.branding).toEqual(DEFAULT_APP_CONFIG.branding)
    expect(config.map).toEqual({
      tileUrl: publicSettings.tileserver_url,
      attribution: publicSettings.tileserver_attribution,
    })
    expect(config.enabledLocales).toBe(DEFAULT_APP_CONFIG.enabledLocales)
  })
})

describe('fetchAppConfig', () => {
  it('derives the app config from the public server settings', async () => {
    vi.mocked(fetchPublicServerSettings).mockResolvedValue(publicSettings)

    const config = await fetchAppConfig()

    expect(fetchPublicServerSettings).toHaveBeenCalledOnce()
    expect(config.map.tileUrl).toBe(publicSettings.tileserver_url)
  })
})
