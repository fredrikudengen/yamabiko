import { computed, ref } from 'vue'

import { getStorageItem, removeStorageItem, setStorageItem } from '@/lib/storage'

import { DEFAULT_HR_ZONE_LIMITS, isValidZoneLimits, type HrZoneLimits } from '../utils/hrZoneTime'

/** Storage key (unprefixed); listed as device-scoped in `lib/storage.ts` so logout keeps it. */
const STORAGE_KEY = 'hrZoneLimits'

/** Limits stored on this device, or the defaults when none are stored or the stored ones are invalid. */
function loadLimits(): HrZoneLimits {
  const stored = getStorageItem<unknown>(STORAGE_KEY)
  return isValidZoneLimits(stored) ? stored : DEFAULT_HR_ZONE_LIMITS
}

// Module-level so every card on the page, and the next activity opened, sees the same limits.
const limits = ref<HrZoneLimits>(loadLimits())

/**
 * The heart-rate zone limits, kept on this device. They start as Google Health's limits and can be
 * changed or reset; changing them recomputes the zone card at once.
 *
 * @returns The current limits, whether they are the defaults, and the setters.
 */
export function useHrZoneLimits() {
  const isDefault = computed(() => limits.value.every((l, i) => l === DEFAULT_HR_ZONE_LIMITS[i]))

  /**
   * Stores new limits.
   *
   * @param next - Four whole numbers, strictly increasing (validated by the caller).
   */
  function setLimits(next: HrZoneLimits): void {
    limits.value = next
    setStorageItem(STORAGE_KEY, next)
  }

  /** Goes back to the defaults and forgets the stored limits. */
  function resetLimits(): void {
    limits.value = DEFAULT_HR_ZONE_LIMITS
    removeStorageItem(STORAGE_KEY)
  }

  return { limits, isDefault, setLimits, resetLimits }
}
