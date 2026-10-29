import { describe, expect, it } from 'vitest'

import { cellBounds, cellSizeM, roundedCellSizeM } from '@/features/coverageMap/utils/tiles'

// Fløyen, Bergen.
const BERGEN_LAT = 60.396

describe('cell boxes', () => {
  it('tile a row without a gap or an overlap', () => {
    const left = cellBounds(100, 200, 17)
    const right = cellBounds(101, 200, 17)

    expect(left.east).toBeCloseTo(right.west, 10)
  })

  it('tile a column without a gap or an overlap', () => {
    const above = cellBounds(100, 200, 17)
    const below = cellBounds(100, 201, 17)

    expect(above.south).toBeCloseTo(below.north, 10)
  })

  it('run north above south and east above west', () => {
    const box = cellBounds(68_000, 38_000, 17)

    expect(box.north).toBeGreaterThan(box.south)
    expect(box.east).toBeGreaterThan(box.west)
  })

  it('cover the whole world at zoom 0', () => {
    const box = cellBounds(0, 0, 0)

    expect(box.west).toBe(-180)
    expect(box.east).toBe(180)
    expect(box.north).toBeCloseTo(85.05, 1)
    expect(box.south).toBeCloseTo(-85.05, 1)
  })

  it('hold the four finer cells they contain', () => {
    const parent = cellBounds(50, 100, 16)

    for (const [x, y] of [
      [100, 200],
      [101, 200],
      [100, 201],
      [101, 201],
    ]) {
      const child = cellBounds(x as number, y as number, 17)
      expect(child.west).toBeGreaterThanOrEqual(parent.west - 1e-9)
      expect(child.east).toBeLessThanOrEqual(parent.east + 1e-9)
      expect(child.south).toBeGreaterThanOrEqual(parent.south - 1e-9)
      expect(child.north).toBeLessThanOrEqual(parent.north + 1e-9)
    }
  })
})

describe('cell size', () => {
  it('is about 150 m at zoom 17 in southern Norway, matching the backend grid', () => {
    expect(cellSizeM(BERGEN_LAT, 17)).toBeCloseTo(151, 0)
  })

  it('is about 300 m at the zoom the page opens at', () => {
    expect(cellSizeM(BERGEN_LAT, 16)).toBeCloseTo(302, 0)
  })

  it('halves with every zoom step', () => {
    expect(cellSizeM(BERGEN_LAT, 16)).toBeCloseTo(2 * cellSizeM(BERGEN_LAT, 17), 6)
  })

  it('shrinks towards the pole, so the caption cannot be quoted from one latitude', () => {
    expect(cellSizeM(60, 17)).toBeLessThan(cellSizeM(0, 17))
  })

  it('rounds to tens below a kilometre and to hundreds above', () => {
    expect(roundedCellSizeM(BERGEN_LAT, 17)).toBe(150)
    expect(roundedCellSizeM(BERGEN_LAT, 16)).toBe(300)
    expect(roundedCellSizeM(BERGEN_LAT, 13) % 100).toBe(0)
  })
})
