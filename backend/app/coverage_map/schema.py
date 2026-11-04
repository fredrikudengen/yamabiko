"""Response models for the coverage map API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CellOut(BaseModel):
    """One cell and how many of the user's tours passed through it."""

    x: int
    y: int
    count: int


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


class RefreshOut(BaseModel):
    """The result of rebuilding the coverage grid."""

    activities: int
    cells: int
