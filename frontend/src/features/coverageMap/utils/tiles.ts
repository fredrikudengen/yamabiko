/**
 * Web Mercator cell geometry, the drawing half of the backend's
 * `coverage_map/tiles.py`. The backend decides which cells a tour passed
 * through; this turns a cell back into the box to draw on the map.
 */

/** Circumference of the sphere Web Mercator wraps (m). */
const EQUATOR_M = 40_075_016.686

/** A cell's geographic box, in the order Leaflet's bounds want. */
export interface CellBounds {
  south: number
  west: number
  north: number
  east: number
}

/**
 * The geographic box of a cell.
 *
 * @param x - Cell x.
 * @param y - Cell y.
 * @param zoom - Zoom of the grid the cell belongs to.
 * @returns The box in degrees.
 */
export function cellBounds(x: number, y: number, zoom: number): CellBounds {
  const scale = 2 ** zoom
  const latitudeOf = (row: number): number =>
    (Math.atan(Math.sinh(Math.PI * (1 - (2 * row) / scale))) * 180) / Math.PI
  return {
    south: latitudeOf(y + 1),
    west: (x / scale) * 360 - 180,
    north: latitudeOf(y),
    east: ((x + 1) / scale) * 360 - 180,
  }
}

/**
 * How wide a cell is on the ground at a latitude. A cell is constant in
 * projected space, so it shrinks towards the poles: about 300 m at zoom 16 in
 * southern Norway, about 600 m at the equator.
 *
 * @param lat - Latitude in degrees.
 * @param zoom - Zoom of the grid.
 * @returns Cell width in metres.
 */
export function cellSizeM(lat: number, zoom: number): number {
  return (EQUATOR_M * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom
}

/**
 * A cell size for a caption, rounded to something readable.
 *
 * @param lat - Latitude to measure at.
 * @param zoom - Zoom of the grid.
 * @returns A rounded width in metres.
 */
export function roundedCellSizeM(lat: number, zoom: number): number {
  const metres = cellSizeM(lat, zoom)
  return metres >= 1000 ? Math.round(metres / 100) * 100 : Math.round(metres / 10) * 10
}
