"""Add segments and segment efforts

Revision ID: c3e8a5f1b6d4
Revises: 8b1d4e6a2c97
Create Date: 2026-10-20 23:30:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3e8a5f1b6d4"
down_revision: str | None = "8b1d4e6a2c97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User ID that the segment belongs to"),
        sa.Column("name", sa.String(length=250), nullable=False, comment="Segment name"),
        sa.Column("start_latitude", sa.Double(), nullable=False, comment="Start node latitude"),
        sa.Column("start_longitude", sa.Double(), nullable=False, comment="Start node longitude"),
        sa.Column("start_radius_m", sa.Double(), nullable=False, comment="Start node radius (m)"),
        sa.Column("end_latitude", sa.Double(), nullable=False, comment="End node latitude"),
        sa.Column("end_longitude", sa.Double(), nullable=False, comment="End node longitude"),
        sa.Column("end_radius_m", sa.Double(), nullable=False, comment="End node radius (m)"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_radius_m > 25", name="ck_segments_start_radius"),
        sa.CheckConstraint("end_radius_m > 25", name="ck_segments_end_radius"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_segments_user_id"), "segments", ["user_id"], unique=False)

    op.create_table(
        "segment_efforts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False, comment="Segment that was passed"),
        sa.Column("activity_id", sa.Integer(), nullable=False, comment="Activity that passed the segment"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("elapsed_s", sa.Double(), nullable=False, comment="Clock time between the nodes (s)"),
        sa.Column("moving_s", sa.Double(), nullable=False, comment="Time without long stops and gaps (s)"),
        sa.Column("stopped_s", sa.Double(), nullable=False, comment="Time in long stops (s)"),
        sa.Column("gap_s", sa.Double(), nullable=False, comment="Time in GPS stream gaps (s)"),
        sa.Column("distance_m", sa.Double(), nullable=False, comment="GPS path between the nodes (m)"),
        sa.Column("elevation_gain_m", sa.Double(), nullable=True, comment="Ascent (m)"),
        sa.Column("elevation_loss_m", sa.Double(), nullable=True, comment="Descent (m)"),
        sa.Column("net_elevation_m", sa.Double(), nullable=True, comment="End height - start height (m)"),
        sa.Column("average_hr", sa.Double(), nullable=True, comment="Mean heart rate while moving"),
        sa.Column("max_hr", sa.Integer(), nullable=True, comment="Highest heart rate while moving"),
        sa.Column("matcher_version", sa.Integer(), nullable=False, comment="How the effort was derived"),
        sa.Column("details", sa.JSON(), nullable=True, comment="Node parameters, stops and visit counts"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("segment_id", "activity_id", name="uq_segment_efforts_segment_activity"),
    )
    op.create_index(op.f("ix_segment_efforts_segment_id"), "segment_efforts", ["segment_id"], unique=False)
    op.create_index(op.f("ix_segment_efforts_activity_id"), "segment_efforts", ["activity_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_segment_efforts_activity_id"), table_name="segment_efforts")
    op.drop_index(op.f("ix_segment_efforts_segment_id"), table_name="segment_efforts")
    op.drop_table("segment_efforts")
    op.drop_index(op.f("ix_segments_user_id"), table_name="segments")
    op.drop_table("segments")
