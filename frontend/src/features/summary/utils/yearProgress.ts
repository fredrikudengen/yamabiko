/**
 * Running totals through each year, laid on a shared calendar so one year can
 * be read against another: how far into the year the user had walked as far as
 * by the same date last year.
 *
 * Every year is placed on a leap-year calendar of 366 days, so 1 March is the
 * same x in every year; in a common year 29 February repeats the 28th's total.
 */

import type { ProgressDay, ProgressMetric } from '@/features/summary/types'

/** Days on the shared calendar. */
export const DAYS_IN_CHART = 366

/** A leap year, to name the days of the shared calendar. */
const CALENDAR_YEAR = 2024

const MS_PER_DAY = 86_400_000

/**
 * @param month - 1–12.
 * @param day - 1–31.
 * @returns The day's place on the shared calendar, 0 for 1 January.
 */
export function chartDayIndex(month: number, day: number): number {
  return Math.round(
    (Date.UTC(CALENDAR_YEAR, month - 1, day) - Date.UTC(CALENDAR_YEAR, 0, 1)) / MS_PER_DAY,
  )
}

/**
 * @param index - A place on the shared calendar.
 * @returns Its month (1–12) and day.
 */
export function chartDayDate(index: number): { month: number; day: number } {
  const date = new Date(Date.UTC(CALENDAR_YEAR, 0, 1) + index * MS_PER_DAY)
  return { month: date.getUTCMonth() + 1, day: date.getUTCDate() }
}

/** One year's running total, one value per day of the shared calendar. */
export interface YearLine {
  year: number
  /** The running total; `NaN` after `today` in the current year, so the line stops. */
  values: number[]
  /** The total at the last day drawn: the year's total, or so far this year. */
  total: number
}

/**
 * Running totals per year.
 *
 * @param days - Totals per day, in any order.
 * @param metric - What to add up.
 * @param today - Today as `YYYY-MM-DD`; the current year's line stops here.
 * @returns One line per year with at least one day, newest first.
 */
export function buildYearLines(
  days: readonly ProgressDay[],
  metric: ProgressMetric,
  today: string,
): YearLine[] {
  const perYear = new Map<number, number[]>()
  for (const day of days) {
    const [year, month, dayOfMonth] = day.day.split('-').map(Number)
    if (!year || !month || !dayOfMonth) {
      continue
    }
    const daily = perYear.get(year) ?? Array.from({ length: DAYS_IN_CHART }, () => 0)
    const index = chartDayIndex(month, dayOfMonth)
    daily[index] = (daily[index] ?? 0) + day[metric]
    perYear.set(year, daily)
  }

  const [thisYear, thisMonth, thisDay] = today.split('-').map(Number)
  const lastIndexThisYear = chartDayIndex(thisMonth ?? 12, thisDay ?? 31)

  return [...perYear.entries()]
    .sort(([a], [b]) => b - a)
    .map(([year, daily]) => {
      const last = year === thisYear ? lastIndexThisYear : DAYS_IN_CHART - 1
      let running = 0
      const values = daily.map((value, index) => {
        if (index > last) {
          return Number.NaN
        }
        running += value
        return running
      })
      return { year, values, total: running }
    })
}

/**
 * @param line - A year's running total.
 * @param index - A place on the shared calendar.
 * @returns The total by that day, or `null` when the line has not got there.
 */
export function totalBy(line: YearLine, index: number): number | null {
  const value = line.values[index]
  return value === undefined || Number.isNaN(value) ? null : value
}
