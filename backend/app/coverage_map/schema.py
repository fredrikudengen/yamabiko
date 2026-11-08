"""Response models for the coverage map API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CellOut(BaseModel):
    """One cell, how many of the user's tours passed through it, and when the first did."""

    x: int
    y: int
    count: int
    first_visit: datetime


class CoverageOut(BaseModel):
    """The user's coverage at one zoom.

    ``zoom`` is the grid the cells are given at, which the client needs to turn
    ``x`` and ``y`` back into a box on the map. ``max_count`` saves the client a
    pass over the cells to scale a legend.
    """

    zoom: int
    cells: list[CellOut]
    max_count: int


class CellTourOut(BaseModel):
    """One tour that passed through a cell: enough to name it and link to it."""

    id: int
    name: str | None
    start_time: datetime


class ActivityCellsOut(BaseModel):
    """How many cells one tour passed through, and in how many it was the user's first."""

    zoom: int
    cells: int
    new_cells: int


class RefreshOut(BaseModel):
    """The result of rebuilding the coverage grid."""

    activities: int
    cells: int
