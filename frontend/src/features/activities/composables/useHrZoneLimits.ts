import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'

import { useAuthStore } from '@/features/auth/stores/auth'
import { getStorageItem, removeStorageItem } from '@/lib/storage'
import { apiFetch } from '@/services/http'

import { DEFAULT_HR_ZONE_LIMITS, isValidZoneLimits, type HrZoneLimits } from '../utils/hrZoneTime'

/**
 * Where the limits used to be kept, one copy per browser. Read once to move them
 * to the server, then removed.
 */
const STORAGE_KEY = 'hrZoneLimits'

/** The limits as the server sends them. */
interface ZoneLimitsDto {
  limits: number[]
  is_default: boolean
}

/** The limits this browser had, if any, before they moved to the server. */
function localLimits(): HrZoneLimits | null {
  const stored = getStorageItem<unknown>(STORAGE_KEY)
  return isValidZoneLimits(stored) ? stored : null
}

// Module-level so every card on the page, and the next activity opened, sees the same limits.
// Until the server has answered, this browser's old limits stand in, so the page does not jump.
const limits = ref<HrZoneLimits>(localLimits() ?? DEFAULT_HR_ZONE_LIMITS)
let loading: Promise<void> | null = null

function apply(dto: ZoneLimitsDto): void {
  if (isValidZoneLimits(dto.limits)) {
    limits.value = dto.limits
  }
}

async function save(next: HrZoneLimits | null): Promise<void> {
  apply(
    await apiFetch<ZoneLimitsDto>('/profile/hr_zones', {
      method: 'PUT',
      body: JSON.stringify({ limits: next }),
    }),
  )
}

/**
 * Loads the limits from the server once per page load. Limits set in this
 * browser before they were kept on the server are moved there the first time,
 * unless the server already has limits of its own.
 */
async function load(): Promise<void> {
  try {
    const dto = await apiFetch<ZoneLimitsDto>('/profile/hr_zones')
    const local = localLimits()
    if (dto.is_default && local) {
      await save(local)
    } else {
      apply(dto)
    }
    removeStorageItem(STORAGE_KEY)
  } catch {
    // Keep what is shown; the next page load tries again.
    loading = null
  }
}

/** Forgets the loaded limits, so the next user to log in on this browser gets their own. */
export function forgetHrZoneLimits(): void {
  loading = null
  limits.value = localLimits() ?? DEFAULT_HR_ZONE_LIMITS
}

/**
 * The heart-rate zone limits, kept on the server so every device shows the same
 * zones and the written feedback can use them. They start as Google Health's
 * limits and can be changed or reset; changing them recomputes the zone card at once.
 *
 * Anyone not logged in (a shared tour) sees the defaults and changes nothing.
 *
 * @returns The current limits, whether they are the defaults, and the setters.
 */
export function useHrZoneLimits() {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  watch(
    isAuthenticated,
    (authenticated) => {
      if (authenticated && !loading) {
        loading = load()
      } else if (!authenticated && loading) {
        forgetHrZoneLimits()
      }
    },
    { immediate: true },
  )

  const isDefault = computed(() => limits.value.every((l, i) => l === DEFAULT_HR_ZONE_LIMITS[i]))

  /**
   * Stores new limits. The page shows them at once; the server is told after.
   *
   * @param next - Four whole numbers, strictly increasing (validated by the caller).
   */
  function setLimits(next: HrZoneLimits): void {
    limits.value = next
    void save(next).catch(() => undefined)
  }

  /** Goes back to the defaults. */
  function resetLimits(): void {
    limits.value = DEFAULT_HR_ZONE_LIMITS
    void save(null).catch(() => undefined)
  }

  return { limits, isDefault, setLimits, resetLimits }
}
