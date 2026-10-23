"""Tests for segments.coordinates: one string in, latitude and longitude out."""

import pytest

from segments.coordinates import CoordinateError, parse_coordinates


@pytest.mark.parametrize(
    "text",
    [
        "60.39, 5.32",
        "60.39,5.32",
        "60.39 5.32",
        "  60.39 ,  5.32  ",
        "60.39; 5.32",
        "60,39; 5,32",
        "60,39 5,32",
        "(60.39, 5.32)",
        "60.39° N, 5.32° E",
        "[60.39, 5.32]",
    ],
)
def test_common_ways_of_writing_a_pair(text):
    assert parse_coordinates(text) == (60.39, 5.32)


def test_negative_and_whole_numbers():
    assert parse_coordinates("-33.9, 151.2") == (-33.9, 151.2)
    assert parse_coordinates("60, 5") == (60.0, 5.0)
    assert parse_coordinates("+60.5 -5.5") == (60.5, -5.5)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "60.39",
        "60.39, 5.32, 10",
        "60,39,5,32",
        "abc, def",
        "32V 301234 6700000",
        "60°23'24\"N 5°19'12\"E",
        "nan, 5",
        "inf, 5",
        "1e3, 5",
    ],
)
def test_text_that_is_not_a_pair_is_rejected(text):
    with pytest.raises(CoordinateError):
        parse_coordinates(text)


def test_out_of_range_values_are_rejected_with_a_hint_about_the_order():
    with pytest.raises(CoordinateError, match=r"latitude.*first"):
        parse_coordinates("120.0, 5.0")
    with pytest.raises(CoordinateError, match="longitude"):
        parse_coordinates("60.0, 200.0")
    # Swapped order cannot be told apart in general, but a value past 90 gives it away.
    with pytest.raises(CoordinateError, match="latitude"):
        parse_coordinates("151.2, -33.9")


def test_it_is_a_value_error():
    # The API maps ValueError to a 422 response.
    assert issubclass(CoordinateError, ValueError)
