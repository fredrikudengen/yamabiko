import { describe, expect, it } from 'vitest'
import { Bike, Footprints, Sailboat, Waves } from '@lucide/vue'

import {
  activityBadgeCategory,
  activityTypeIsCycling,
  activityTypeIsRunning,
  activityTypeIsSwimming,
  activityTypeIsVirtual,
  activityTypeUsesKnots,
  activityTypeUsesPace,
  presentActivityType,
} from '@/features/activities/utils/activityType'

describe('activity type predicates', () => {
  it('classifies running, cycling and swimming types', () => {
    expect(activityTypeIsRunning(1)).toBe(true)
    expect(activityTypeIsRunning(4)).toBe(false)
    expect(activityTypeIsCycling(4)).toBe(true)
    expect(activityTypeIsSwimming(8)).toBe(true)
    expect(activityTypeIsSwimming(9)).toBe(true)
  })

  it('flags virtual run/ride types', () => {
    expect(activityTypeIsVirtual(3)).toBe(true)
    expect(activityTypeIsVirtual(7)).toBe(true)
    expect(activityTypeIsVirtual(1)).toBe(false)
  })

  it('uses pace for foot/water sports and speed for cycling', () => {
    expect(activityTypeUsesPace(1)).toBe(true)
    expect(activityTypeUsesPace(8)).toBe(true)
    expect(activityTypeUsesPace(13)).toBe(true)
    expect(activityTypeUsesPace(4)).toBe(false)
  })

  it('uses knots for marine sports', () => {
    expect(activityTypeUsesKnots(43)).toBe(true)
    expect(activityTypeUsesKnots(30)).toBe(true)
    expect(activityTypeUsesKnots(4)).toBe(false)
  })
})

describe('activityBadgeCategory', () => {
  it('maps each discipline to a badge colour category', () => {
    expect(activityBadgeCategory(1)).toBe('running')
    expect(activityBadgeCategory(4)).toBe('cycling')
    expect(activityBadgeCategory(8)).toBe('swimming')
    expect(activityBadgeCategory(11)).toBe('hiking')
    expect(activityBadgeCategory(21)).toBe('other')
  })
})

describe('presentActivityType', () => {
  it('bundles label key, badge and icon for known types', () => {
    expect(presentActivityType(1)).toEqual({
      labelKey: 'activities.types.run',
      badge: 'running',
      icon: Footprints,
    })
    expect(presentActivityType(4).icon).toBe(Bike)
    expect(presentActivityType(8).icon).toBe(Waves)
    expect(presentActivityType(43).icon).toBe(Sailboat)
  })

  it('falls back to a generic workout label for unknown types', () => {
    expect(presentActivityType(999).labelKey).toBe('activities.types.workout')
  })
})
