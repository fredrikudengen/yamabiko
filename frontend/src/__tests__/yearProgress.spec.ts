import { describe, expect, it } from 'vitest'

import type { ProgressDay } from '@/features/summary/types'

import {
  DAYS_IN_CHART,
  buildYearLines,
  chartDayDate,
  chartDayIndex,
  totalBy,
} from '@/features/summary/utils/yearProgress'

function day(iso: string, climb: number): ProgressDay {
  return { day: iso, distance: 0, duration: 0, elevationGain: climb, activityCount: 1, newCells: 0 }
}

describe('the shared calendar', () => {
  it('puts 1 March at the same place in a leap year and a common year', () => {
    expect(chartDayIndex(1, 1)).toBe(0)
    expect(chartDayIndex(2, 29)).toBe(59)
    expect(chartDayIndex(3, 1)).toBe(60)
    expect(chartDayIndex(12, 31)).toBe(DAYS_IN_CHART - 1)
  })

  it('turns a place back into its date', () => {
    expect(chartDayDate(60)).toEqual({ month: 3, day: 1 })
    expect(chartDayDate(DAYS_IN_CHART - 1)).toEqual({ month: 12, day: 31 })
  })
})

describe('buildYearLines', () => {
  const days = [
    day('2025-01-10', 100),
    day('2025-03-01', 200),
    day('2026-01-05', 50),
    day('2026-01-05', 25),
    day('2026-02-01', 300),
  ]

  it('adds up through each year, newest year first', () => {
    const [y2026, y2025] = buildYearLines(days, 'elevationGain', '2026-11-08')

    expect(y2026?.year).toBe(2026)
    expect(y2025?.year).toBe(2025)
    expect(y2025?.values[chartDayIndex(1, 9)]).toBe(0)
    expect(y2025?.values[chartDayIndex(1, 10)]).toBe(100)
    expect(y2025?.values[chartDayIndex(3, 1)]).toBe(300)
    expect(y2025?.total).toBe(300)
    expect(y2026?.values[chartDayIndex(1, 5)]).toBe(75)
  })

  it('stops the current year at today and runs a past year to 31 December', () => {
    const [y2026, y2025] = buildYearLines(days, 'elevationGain', '2026-11-08')

    expect(y2026?.values[chartDayIndex(11, 8)]).toBe(375)
    expect(y2026?.values[chartDayIndex(11, 9)]).toBeNaN()
    expect(y2026?.total).toBe(375)
    expect(y2025?.values[DAYS_IN_CHART - 1]).toBe(300)
  })

  it('adds up whichever metric it is asked for', () => {
    const [y2026] = buildYearLines(days, 'activityCount', '2026-12-31')

    expect(y2026?.total).toBe(3)
  })

  it('reads a total by a day, or nothing past where the line stops', () => {
    const [y2026] = buildYearLines(days, 'elevationGain', '2026-11-08')

    expect(totalBy(y2026!, chartDayIndex(2, 1))).toBe(375)
    expect(totalBy(y2026!, chartDayIndex(12, 1))).toBeNull()
  })

  it('has no lines without days', () => {
    expect(buildYearLines([], 'distance', '2026-11-08')).toEqual([])
  })
})
