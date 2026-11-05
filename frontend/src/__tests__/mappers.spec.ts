import { describe, expect, it, vi } from 'vitest'

import type { UserProfileDto } from '@/features/auth/types'

import { mapUserProfile } from '@/features/auth/services/mappers'

vi.mock('@/services/runtime', () => ({
  getBackendAssetUrl: (path: string) => `https://cdn.test/${path.replace(/^\/+/, '')}`,
}))

const baseDto: UserProfileDto = {
  id: 7,
  name: 'Ada Lovelace',
  username: 'ada',
  email: 'ada@example.com',
  preferred_language: 'en',
  access_type: 'admin',
  active: true,
  mfa_enabled: true,
  photo_path: 'user_images/7.png',
  has_local_password: true,
  units: 'metric',
  currency: 'euro',
  first_day_of_week: 'sunday',
}

describe('mapUserProfile', () => {
  it('maps snake_case fields to the clean camelCase model', () => {
    const user = mapUserProfile(baseDto)

    expect(user).toEqual({
      id: 7,
      name: 'Ada Lovelace',
      username: 'ada',
      email: 'ada@example.com',
      preferredLanguage: 'en',
      accessType: 'admin',
      active: true,
      mfaEnabled: true,
      avatarUrl: 'https://cdn.test/user_images/7.png',
      hasLocalPassword: true,
      units: 'metric',
      currency: 'euro',
      firstDayOfWeek: 'sunday',
    })
  })

  it('resolves avatarUrl to null when no photo_path is set', () => {
    expect(mapUserProfile({ ...baseDto, photo_path: null }).avatarUrl).toBeNull()
    expect(mapUserProfile({ ...baseDto, photo_path: undefined }).avatarUrl).toBeNull()
  })

  it('strips the absolute filesystem prefix from photo_path', () => {
    expect(
      mapUserProfile({ ...baseDto, photo_path: '/app/backend/data/user_images/7.png' }).avatarUrl,
    ).toBe('https://cdn.test/user_images/7.png')
    expect(mapUserProfile({ ...baseDto, photo_path: 'data/user_images/7.png' }).avatarUrl).toBe(
      'https://cdn.test/user_images/7.png',
    )
  })

  it('defaults hasLocalPassword to false when absent', () => {
    expect(mapUserProfile({ ...baseDto, has_local_password: null }).hasLocalPassword).toBe(false)
    expect(mapUserProfile({ ...baseDto, has_local_password: undefined }).hasLocalPassword).toBe(
      false,
    )
  })
})
