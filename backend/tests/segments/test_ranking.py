"""Where each pass stands among all passes of a segment."""

from dataclasses import dataclass

import pytest

import segments.ranking as ranking


@dataclass
class Pass:
    id: int
    moving_s: float
    elapsed_s: float


def ranks(*passes: Pass) -> dict[int, tuple[int, int]]:
    return {i: (s.rank_moving, s.rank_total) for i, s in ranking.rank_efforts(passes).items()}


def test_the_fastest_is_first_and_the_count_is_every_pass():
    standings = ranking.rank_efforts([Pass(1, 2000, 2000), Pass(2, 1800, 1800), Pass(3, 1900, 1900)])

    assert {i: s.rank_moving for i, s in standings.items()} == {1: 3, 2: 1, 3: 2}
    assert {s.count for s in standings.values()} == {3}


def test_a_single_pass_is_first_of_one():
    (standing,) = ranking.rank_efforts([Pass(1, 1800, 1800)]).values()

    assert (standing.rank_moving, standing.rank_total, standing.count) == (1, 1, 1)


def test_no_passes_gives_no_standings():
    assert ranking.rank_efforts([]) == {}


def test_moving_time_and_total_time_rank_separately():
    # Pass 1 rested a long time: fastest on the move, slowest by the clock.
    assert ranks(Pass(1, 1500, 2900), Pass(2, 1800, 1800)) == {1: (1, 2), 2: (2, 1)}


def test_equal_times_share_a_rank_and_the_next_rank_is_skipped():
    assert ranks(Pass(1, 1800, 1800), Pass(2, 1800, 1800), Pass(3, 1900, 1900)) == {1: (1, 1), 2: (1, 1), 3: (3, 3)}


@pytest.mark.parametrize(
    ("a", "b", "tied"),
    [
        (1800.2, 1799.8, True),  # both show as 30:00
        (1800.4, 1800.0, True),
        (1800.6, 1800.4, False),  # 30:01 against 30:00
        (1800.5, 1800.49, False),  # half rounds up, as the interface rounds
    ],
)
def test_times_that_show_the_same_to_the_second_tie(a, b, tied):
    result = ranks(Pass(1, a, a), Pass(2, b, b))

    assert (result[1][0] == result[2][0]) is tied
