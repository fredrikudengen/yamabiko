/** Types for the coverage map: which cells the user's tours have passed through. */

/** One cell as the API sends it. */
export interface CoverageCellDto {
  x: number
  y: number
  count: number
}

/** The coverage grid as the API sends it. */
export interface CoverageDto {
  zoom: number
  cells: CoverageCellDto[]
  max_count: number
}

/** One cell and how many tours passed through it. */
export interface CoverageCell {
  /** Cell x at the grid's zoom. */
  x: number
  /** Cell y at the grid's zoom. */
  y: number
  /** How many separate tours passed through. */
  count: number
}

/** The user's coverage at one zoom. */
export interface Coverage {
  /** The grid the cells are given at; needed to turn x and y back into a box. */
  zoom: number
  cells: CoverageCell[]
  /** The highest count in `cells`, or 0 when there are none. */
  maxCount: number
}

/** The result of rebuilding the grid. */
export interface CoverageRefresh {
  activities: number
  cells: number
}

/** The cell sizes the page offers, as zoom levels of the Web Mercator grid. */
export const CELL_ZOOMS = [15, 16, 17] as const

/**
 * The grid used until the map has reported its zoom: cells of about 300 m in
 * southern Norway. Only the first fetch uses it; "auto" takes over once the map
 * has fitted the cells.
 */
export const DEFAULT_CELL_ZOOM = 16

/** The coarsest and finest grids the API counts at (`coverage_map/tiles.py`). */
export const MIN_CELL_ZOOM = 8
export const MAX_CELL_ZOOM = 17

/** The cell size picked by the user: one of `CELL_ZOOMS`, or follow the map. */
export type CellSizeChoice = 'auto' | number
