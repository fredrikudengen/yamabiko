/**
 * Where a tour came from. Mirrors `backend/app/segments/source.py`: the backend decides the source of
 * every effort and preview match; `activitySourceOf` applies the same rules to an activity the page
 * already has (the detail header), so the two must change together.
 *
 * The source is how the tour got into Yamabiko, not which device measured it. It is still the best
 * available signal for what can be compared: GPS time between two nodes is computed the same way
 * for every source, while heart rate and ascent come from different sensors and corrections.
 */
export const ACTIVITY_SOURCES = ['google_health', 'strava', 'garmin', 'other'] as const

export type ActivitySource = (typeof ACTIVITY_SOURCES)[number]

/** The `import_info.import_source` values the importers write. */
const IMPORT_SOURCE_GOOGLE_HEALTH = 'google_health'
const IMPORT_SOURCE_STRAVA_BULK = 'Strava bulk import'

/**
 * @param value - A source string from the API.
 * @returns The source, or `other` for a value this version does not know.
 */
export function toActivitySource(value: string): ActivitySource {
  return (ACTIVITY_SOURCES as readonly string[]).includes(value)
    ? (value as ActivitySource)
    : 'other'
}

/** The fields of an activity that tell where it came from. */
export interface ActivitySourceFields {
  stravaActivityId: number | null
  garminActivityId: number | null
  importInfo: Record<string, unknown> | null
}

/**
 * The source of an activity. Google Health imports are recognised by `import_info` (the frontend
 * model has no Google Health id; the importer always sets `import_source`). The Strava bulk import
 * leaves `stravaActivityId` empty on purpose, so it too is recognised by `import_info`.
 *
 * @param activity - The activity's source-related fields.
 * @returns The source.
 */
export function activitySourceOf(activity: ActivitySourceFields): ActivitySource {
  const importSource = activity.importInfo?.import_source
  if (importSource === IMPORT_SOURCE_GOOGLE_HEALTH) {
    return 'google_health'
  }
  if (activity.stravaActivityId || importSource === IMPORT_SOURCE_STRAVA_BULK) {
    return 'strava'
  }
  if (activity.garminActivityId) {
    return 'garmin'
  }
  return 'other'
}

/**
 * Whether heart rate and ascent from two sources can be compared: only the same known source.
 * Two `other` tours may come from different devices.
 */
export function comparableSources(a: ActivitySource, b: ActivitySource): boolean {
  return a === b && a !== 'other'
}

/**
 * @param items - Anything with a source, such as efforts.
 * @returns True when the items come from more than one source, so heart rate and ascent are not
 *   directly comparable across all of them.
 */
export function hasMixedSources(items: readonly { source: ActivitySource }[]): boolean {
  return new Set(items.map((item) => item.source)).size > 1
}

/** The i18n key of a source's short label. */
export function sourceLabelKey(source: ActivitySource): string {
  return `activities.segments.source.${source}`
}
