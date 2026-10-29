"""ORM model for the cells an activity's GPS track passed through."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ActivityCell(Base):
    """
    One Web Mercator cell an activity's track passed through.

    The rows are derived data: they can be rebuilt from the activity's GPS
    stream at any time (``POST /coverage/refresh``), which is what happens when
    the grid or the filling rules change. An activity contributes at most one
    row per cell, so counting rows per cell counts *tours*, not GPS points — an
    hour standing still at a summit adds the same single row as walking past.

    Attributes:
        activity_id: Activity the cell belongs to.
        cell_x: Cell x at ``grid_zoom``.
        cell_y: Cell y at ``grid_zoom``.
        grid_zoom: Zoom the cell indices are given at.
    """

    __tablename__ = "activity_cells"
    __table_args__ = (Index("ix_activity_cells_cell", "cell_x", "cell_y"),)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Activity that passed through the cell",
    )
    cell_x: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Web Mercator cell x at grid_zoom")
    cell_y: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Web Mercator cell y at grid_zoom")
    grid_zoom: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="Zoom the cell indices are given at")
