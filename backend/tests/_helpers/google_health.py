"""Builders for Google Health tests: synthetic Fitbit-like TCX files and data points."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

LAT0, LON0 = 60.0, 5.0


def make_track(segments: list[tuple[str, int]], seed: int = 5) -> list[dict]:
    """Per-second points for ``[("walk", seconds), ("rest", seconds), ...]``.

    ``walk`` moves ~1.2 m/s with 1 m GPS noise. ``rest`` stands still but the
    position wobbles like a wrist-worn receiver (slowly varying offset of a few
    metres plus noise). The cumulative distance is the GPS path, like the
    trackpoint distance in real Fitbit files.
    """
    rng = random.Random(seed)  # noqa: S311 - deterministic test data, not cryptography
    t0 = datetime(2026, 10, 14, 9, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    x = y = wob_x = wob_y = cum = 0.0
    prev: tuple[float, float] | None = None
    points: list[dict] = []
    i = 0
    for kind, seconds in segments:
        for _ in range(seconds):
            if kind == "walk":
                speed = 1.2 + rng.uniform(-0.2, 0.2)
                heading = 0.6 + 0.3 * math.sin(i / 90)
                x += speed * math.sin(heading)
                y += speed * math.cos(heading)
                wobble = 1.0
            else:
                wobble = 2.5
            wob_x = 0.9 * wob_x + rng.gauss(0, wobble * 0.45)
            wob_y = 0.9 * wob_y + rng.gauss(0, wobble * 0.45)
            gx = x + wob_x + rng.gauss(0, 1.0)
            gy = y + wob_y + rng.gauss(0, 1.0)
            if prev is not None:
                cum += math.hypot(gx - prev[0], gy - prev[1])
            prev = (gx, gy)
            points.append(
                {
                    "time": t0 + timedelta(seconds=i),
                    "lat": LAT0 + gy / 111_320,
                    "lon": LON0 + gx / (111_320 * math.cos(math.radians(LAT0))),
                    "ele": 50 + 0.02 * i,
                    "distance": cum,
                }
            )
            i += 1
    return points


def write_tcx(path: Path, points: list[dict], summary_distance: float | None = None) -> Path:
    """Write ``points`` as a single-lap Fitbit-like TCX file."""

    def stamp(value: datetime) -> str:
        return value.isoformat(timespec="milliseconds")

    trackpoints = "\n".join(
        f"<Trackpoint><Time>{stamp(p['time'])}</Time><Position><LatitudeDegrees>{p['lat']:.6f}</LatitudeDegrees>"
        f"<LongitudeDegrees>{p['lon']:.6f}</LongitudeDegrees></Position><AltitudeMeters>{p['ele']:.2f}</AltitudeMeters>"
        f"<DistanceMeters>{p['distance']:.2f}</DistanceMeters><HeartRateBpm><Value>110</Value></HeartRateBpm></Trackpoint>"
        for p in points
    )
    total = (points[-1]["time"] - points[0]["time"]).total_seconds()
    lap_distance = summary_distance if summary_distance is not None else points[-1]["distance"]
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Activities>
<Activity Sport="Other"><Id>{stamp(points[0]["time"])}</Id><Lap StartTime="{stamp(points[0]["time"])}">
<TotalTimeSeconds>{total:.0f}</TotalTimeSeconds><DistanceMeters>{lap_distance:.1f}</DistanceMeters>
<Calories>100</Calories><Intensity>Active</Intensity><TriggerMethod>Manual</TriggerMethod>
<Track>{trackpoints}</Track></Lap></Activity></Activities></TrainingCenterDatabase>"""
    )
    return path


def data_point(
    exercise_id: str = "1111111111111111111",
    recording_method: str = "ACTIVELY_MEASURED",
    has_gps: bool | None = True,
    events: tuple[str, ...] = ("START", "STOP"),
    exercise_type: str = "WALKING",
    distance_mm: int | None = None,
    elevation_gain_mm: int | None = None,
) -> dict:
    """A Google Health exercise data point shaped like the real API response."""
    metadata = {} if has_gps is None else {"hasGps": has_gps}
    summary: dict = {}
    if distance_mm is not None:
        summary["distanceMillimeters"] = distance_mm
    if elevation_gain_mm is not None:
        summary["elevationGainMillimeters"] = elevation_gain_mm
    return {
        "name": f"users/0000000000000000000/dataTypes/exercise/dataPoints/{exercise_id}",
        "dataSource": {"recordingMethod": recording_method, "platform": "FITBIT"},
        "exercise": {
            "interval": {"startTime": "2026-10-14T07:00:00Z", "endTime": "2026-10-14T08:00:00Z"},
            "exerciseType": exercise_type,
            "metricsSummary": summary,
            "exerciseMetadata": metadata,
            "displayName": "Gåing",
            "activeDuration": "3600s",
            "exerciseEvents": [{"exerciseEventType": event} for event in events],
        },
    }
