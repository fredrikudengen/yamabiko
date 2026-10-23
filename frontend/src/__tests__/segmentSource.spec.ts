import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import type { SegmentEffort } from '@/features/segments/types'

import i18n from '@/i18n'
import en from '@/i18n/locales/en/activities.json'
import nb from '@/i18n/locales/nb/activities.json'
import EffortsTable from '@/features/segments/components/EffortsTable.vue'
import { mapEffort } from '@/features/segments/services/segments'
import {
  ACTIVITY_SOURCES,
  activitySourceOf,
  comparableSources,
  hasMixedSources,
  sourceLabelKey,
  toActivitySource,
  type ActivitySource,
} from '@/features/segments/utils/source'

describe('activitySourceOf', () => {
  const base = { stravaActivityId: null, garminActivityId: null, importInfo: null }

  it.each([
    [{ importInfo: { import_source: 'google_health' } }, 'google_health'],
    // The Strava bulk import leaves the Strava id empty on purpose, so import_info is the trace.
    [{ importInfo: { import_source: 'Strava bulk import' } }, 'strava'],
    [{ stravaActivityId: 123 }, 'strava'],
    [{ garminActivityId: 456 }, 'garmin'],
    [{ importInfo: { import_source: 'Basic bulk import' } }, 'other'],
    [{ importInfo: {} }, 'other'],
    [{}, 'other'],
  ] as [Partial<typeof base> & { importInfo?: Record<string, unknown> }, ActivitySource][])(
    'reads %j as %s',
    (fields, expected) => {
      expect(activitySourceOf({ ...base, ...fields })).toBe(expected)
    },
  )

  it('lets the Google Health import win over a Strava copy id', () => {
    expect(
      activitySourceOf({
        ...base,
        stravaActivityId: 9,
        importInfo: { import_source: 'google_health' },
      }),
    ).toBe('google_health')
  })
})

describe('source helpers', () => {
  it('treats a source this version does not know as other', () => {
    expect(toActivitySource('strava')).toBe('strava')
    expect(toActivitySource('polar')).toBe('other')
  })

  it('says heart rate is comparable only within the same known source', () => {
    expect(comparableSources('strava', 'strava')).toBe(true)
    expect(comparableSources('strava', 'google_health')).toBe(false)
    expect(comparableSources('other', 'other')).toBe(false)
  })

  it('detects mixed sources', () => {
    expect(hasMixedSources([])).toBe(false)
    expect(hasMixedSources([{ source: 'strava' }, { source: 'strava' }])).toBe(false)
    expect(hasMixedSources([{ source: 'strava' }, { source: 'google_health' }])).toBe(true)
  })

  it('has a label for every source in both languages', () => {
    // The `nb` bundle is loaded on demand, so read the locale files themselves.
    for (const locale of [en, nb] as { segments: { source: Record<string, string> } }[]) {
      for (const source of ACTIVITY_SOURCES) {
        expect(locale.segments.source[source]).toBeTruthy()
      }
    }
    expect(sourceLabelKey('strava')).toBe('activities.segments.source.strava')
  })
})

describe('mapEffort', () => {
  it('carries the source from the API', () => {
    const mapped = mapEffort({
      id: 1,
      segment_id: 2,
      segment_name: 'Top',
      activity_id: 3,
      activity_name: 'Hike',
      source: 'strava',
      start_time: '2026-10-01T08:00:00',
      end_time: '2026-10-01T08:30:00',
      elapsed_s: 1800,
      moving_s: 1700,
      stopped_s: 0,
      gap_s: 0,
      distance_m: 2000,
      elevation_gain_m: 250,
      elevation_loss_m: 0,
      net_elevation_m: 250,
      average_hr: 170,
      max_hr: 190,
      matcher_version: 1,
      details: null,
    })
    expect(mapped.source).toBe('strava')
  })
})

describe('EffortsTable and sources', () => {
  const effort = (id: number, source: ActivitySource): SegmentEffort => ({
    id,
    segmentId: 1,
    segmentName: 'Top',
    activityId: id + 100,
    activityName: 'Hike',
    source,
    startTime: `2026-10-0${id}T08:00:00`,
    endTime: `2026-10-0${id}T08:30:00`,
    elapsedS: 1800,
    movingS: 1700,
    stoppedS: 0,
    gapS: 0,
    distanceM: 2000,
    elevationGainM: 250,
    elevationLossM: 0,
    netElevationM: 250,
    averageHr: 110,
    maxHr: 140,
  })
  const mountTable = (efforts: SegmentEffort[]) =>
    mount(EffortsTable, {
      props: { efforts },
      global: { plugins: [i18n], stubs: { 'router-link': true } },
    })

  it('labels each row with its source', () => {
    const wrapper = mountTable([effort(1, 'strava'), effort(2, 'google_health')])
    const labels = wrapper.findAll('[data-testid="effort-source"]').map((b) => b.text())
    // Rows are newest first.
    expect(labels).toEqual(['Fitbit', 'Strava'])
  })

  it('warns that heart rate and ascent are not comparable only when sources are mixed', () => {
    expect(
      mountTable([effort(1, 'strava'), effort(2, 'google_health')])
        .find('[data-testid="mixed-sources-notice"]')
        .exists(),
    ).toBe(true)
    expect(
      mountTable([effort(1, 'strava'), effort(2, 'strava')])
        .find('[data-testid="mixed-sources-notice"]')
        .exists(),
    ).toBe(false)
  })
})
