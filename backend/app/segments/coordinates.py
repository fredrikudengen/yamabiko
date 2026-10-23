"""Parse a pair of coordinates typed or pasted as one string, such as ``60.39, 5.32``.

Latitude comes first (the order of ut.no and the map apps). Only decimal degrees
are accepted; UTM and degrees/minutes/seconds are rejected with a message, not guessed at.

Accepted separators between the two numbers: a comma, a semicolon, or whitespace.
A decimal comma is accepted when the numbers are separated by a semicolon or
whitespace (``60,39 5,32`` or ``60,39; 5,32``); with a comma as the separator the
numbers must use decimal points (``60.39, 5.32``), because ``60,39,5,32`` could
be read two ways.
"""

from __future__ import annotations

import math
import re

_NUMBER = r"[+-]?\d+(?:\.\d+)?"
_DECORATION = re.compile(r"[()\[\]°]|\b[NnEe]\b")
_ONE_NUMBER = re.compile(_NUMBER)


class CoordinateError(ValueError):
    """The text is not a pair of decimal-degree coordinates."""


def _number(text: str) -> float:
    text = text.strip().replace(",", ".")
    if not _ONE_NUMBER.fullmatch(text):
        raise CoordinateError(f"'{text}' is not a decimal number; use decimal degrees such as 60.39, 5.32")
    return float(text)


def parse_coordinates(text: str) -> tuple[float, float]:
    """Latitude and longitude in decimal degrees from a string like ``60.39, 5.32``.

    Raises:
        CoordinateError: When the text is not two decimal numbers, or they are outside
            -90..90 (latitude) and -180..180 (longitude).
    """
    cleaned = _DECORATION.sub(" ", text).strip()
    if not cleaned:
        raise CoordinateError("the coordinates are empty")

    if ";" in cleaned:
        parts = cleaned.split(";")
    elif "." in cleaned or "," not in cleaned or re.search(r",\s", cleaned):
        # Decimal points (or whole numbers, or a comma followed by a space): a comma,
        # if present, is the separator.
        parts = cleaned.split(",") if "," in cleaned else cleaned.split()
    else:
        # Commas but no points: "60,39 5,32" (decimal commas, whitespace between).
        parts = cleaned.split()
    parts = [part for part in parts if part.strip()]
    if len(parts) != 2:
        raise CoordinateError(
            "give two decimal numbers, latitude then longitude, for example 60.39, 5.32 (UTM is not supported)"
        )

    lat, lon = _number(parts[0]), _number(parts[1])
    if not (math.isfinite(lat) and -90.0 <= lat <= 90.0):
        raise CoordinateError(f"latitude {lat:g} must be between -90 and 90 (latitude comes first)")
    if not (math.isfinite(lon) and -180.0 <= lon <= 180.0):
        raise CoordinateError(f"longitude {lon:g} must be between -180 and 180")
    return lat, lon
