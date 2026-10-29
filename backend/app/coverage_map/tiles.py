"""Web Mercator cells: the grid the coverage map counts tours in.

A cell is one Web Mercator tile at a fixed zoom — the same grid the map already
draws its background in, so a cell always lines up with the tiles under it and
never looks skewed. Cells are stored at :data:`STORE_ZOOM` and rolled up to a
coarser zoom by dropping low bits, which is exact: four cells of zoom ``z + 1``
tile one cell of zoom ``z``.

A cell is constant in *projected* space, so its size on the ground shrinks
towards the poles: at zoom 17 a cell is about 305 m at the equator and about
151 m at 60 N. :func:`cell_size_m` gives the size at a latitude, for captions.
"""

from __future__ import annotations

import math

# The zoom cells are stored at. About 151 m on the ground in southern Norway.
STORE_ZOOM = 17

# The zooms the API will roll up to. Zoom 8 cells are tens of kilometres across,
# which is as coarse as a country view needs; zoom 17 is the stored grid.
MIN_ZOOM = 8
MAX_ZOOM = STORE_ZOOM

# Web Mercator cannot represent the poles; this is where the projection is cut.
_MAX_LATITUDE = 85.05112878

# Circumference of the sphere Web Mercator wraps (m).
_EQUATOR_M = 40_075_016.686


def _clamp_latitude(lat: float) -> float:
    return max(-_MAX_LATITUDE, min(_MAX_LATITUDE, lat))


def tile_xy_float(lat: float, lon: float, zoom: int = STORE_ZOOM) -> tuple[float, float]:
    """Fractional tile coordinates of a position.

    The fraction is what tells how far into the cell the point sits, which is
    what walking a line between two points needs.

    Args:
        lat: Latitude in degrees. Clamped to the Mercator limit.
        lon: Longitude in degrees. Wrapped into [-180, 180).
        zoom: Zoom level of the grid.

    Returns:
        ``(x, y)`` in tile units, where the whole world is ``2 ** zoom`` wide.
    """
    scale = 2**zoom
    wrapped = (lon + 180.0) % 360.0
    x = wrapped / 360.0 * scale
    radians = math.radians(_clamp_latitude(lat))
    y = (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * scale
    return x, y


def tile_xy(lat: float, lon: float, zoom: int = STORE_ZOOM) -> tuple[int, int]:
    """The cell a position falls in.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        zoom: Zoom level of the grid.

    Returns:
        ``(x, y)`` cell indices, both within ``0 .. 2 ** zoom - 1``.
    """
    scale = 2**zoom
    x, y = tile_xy_float(lat, lon, zoom)
    return (
        min(scale - 1, max(0, math.floor(x))),
        min(scale - 1, max(0, math.floor(y))),
    )


def roll_up(x: int, y: int, from_zoom: int = STORE_ZOOM, to_zoom: int = STORE_ZOOM) -> tuple[int, int]:
    """The coarser cell that contains a cell.

    Args:
        x: Cell x at ``from_zoom``.
        y: Cell y at ``from_zoom``.
        from_zoom: Zoom the cell is given at.
        to_zoom: Zoom to roll up to. Must not be finer than ``from_zoom``.

    Returns:
        ``(x, y)`` at ``to_zoom``.

    Raises:
        ValueError: When ``to_zoom`` is finer than ``from_zoom``.
    """
    if to_zoom > from_zoom:
        raise ValueError(f"cannot roll up from zoom {from_zoom} to finer zoom {to_zoom}")
    shift = from_zoom - to_zoom
    return x >> shift, y >> shift


def cell_size_m(lat: float, zoom: int = STORE_ZOOM) -> float:
    """How wide a cell is on the ground at a latitude.

    Args:
        lat: Latitude in degrees.
        zoom: Zoom level of the grid.

    Returns:
        Cell width in metres.
    """
    return _EQUATOR_M * math.cos(math.radians(_clamp_latitude(lat))) / 2**zoom


def cell_bounds(x: int, y: int, zoom: int = STORE_ZOOM) -> tuple[float, float, float, float]:
    """The geographic box of a cell.

    Args:
        x: Cell x.
        y: Cell y.
        zoom: Zoom level of the grid.

    Returns:
        ``(south, west, north, east)`` in degrees.
    """
    scale = 2**zoom

    def latitude_of(row: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * row / scale))))

    west = x / scale * 360.0 - 180.0
    east = (x + 1) / scale * 360.0 - 180.0
    return latitude_of(y + 1), west, latitude_of(y), east
