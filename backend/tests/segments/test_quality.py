"""Tests for when a pass's time is to be doubted."""

from dataclasses import dataclass, field
from typing import Any

import pytest

import segments.quality as quality


@dataclass
class Effort:
    gap_s: float = 0.0
    details: dict[str, Any] | None = field(default_factory=lambda: {"start_depth_m": 40.0, "end_depth_m": 30.0})


def test_a_clean_pass_raises_no_doubt():
    assert quality.effort_doubts(Effort()) == []


def test_a_gps_gap_inside_the_segment_is_a_doubt():
    assert quality.effort_doubts(Effort(gap_s=95)) == [quality.DOUBT_GPS_GAP]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (4.9, 30.0, [quality.DOUBT_START_EDGE]),
        (40.0, 0.0, [quality.DOUBT_END_EDGE]),
        (1.0, 2.0, [quality.DOUBT_START_EDGE, quality.DOUBT_END_EDGE]),
        (5.0, 5.0, []),
    ],
)
def test_coming_less_than_the_edge_depth_into_a_circle_is_a_doubt(start, end, expected):
    assert quality.effort_doubts(Effort(details={"start_depth_m": start, "end_depth_m": end})) == expected


def test_all_reasons_are_given_in_a_fixed_order():
    effort = Effort(gap_s=40, details={"start_depth_m": 1.0, "end_depth_m": 1.0})

    assert quality.effort_doubts(effort) == [
        quality.DOUBT_GPS_GAP,
        quality.DOUBT_START_EDGE,
        quality.DOUBT_END_EDGE,
    ]


@pytest.mark.parametrize("details", [None, {}, {"start_depth_m": None, "end_depth_m": None}])
def test_a_pass_computed_before_depths_were_recorded_is_judged_on_gaps_only(details):
    assert quality.effort_doubts(Effort(details=details)) == []
    assert quality.effort_doubts(Effort(gap_s=60, details=details)) == [quality.DOUBT_GPS_GAP]
