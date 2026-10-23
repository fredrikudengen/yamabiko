"""HTTP endpoints for segments (``/api/v1/segments``).

A segment belongs to one user; other users' segments and activities answer 404.
Creating a segment, or changing its nodes, recomputes its efforts from the owner's
activities before the response is sent. The handlers are plain ``def`` so FastAPI runs
them in its thread pool: matching reads the streams of every activity.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
import segments.coordinates as segments_coordinates
import segments.crud as segments_crud
import segments.models as segments_models
import segments.schema as segments_schema
import segments.service as segments_service

router = APIRouter()

_Validated = Annotated[Callable, Depends(auth_dependencies.validate_access_token)]
_CanRead = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])]
_CanWrite = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])]
_UserId = Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)]
_Db = Annotated[Session, Depends(core_database.get_db)]


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _own_segment(segment_id: int, user_id: int, db: Session) -> segments_models.Segment:
    segment = segments_crud.get_segment(segment_id, user_id, db)
    if segment is None:
        raise _not_found("Segment")
    return segment


def _unprocessable(err: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err))


def _segment_out(segment: segments_models.Segment, effort_count: int) -> segments_schema.SegmentOut:
    return segments_schema.SegmentOut(
        id=segment.id,
        name=segment.name,
        start=segments_schema.NodeOut(
            lat=segment.start_latitude, lon=segment.start_longitude, radius_m=segment.start_radius_m
        ),
        end=segments_schema.NodeOut(lat=segment.end_latitude, lon=segment.end_longitude, radius_m=segment.end_radius_m),
        effort_count=effort_count,
        created_at=segment.created_at,
        updated_at=segment.updated_at,
    )


def _similar_out(segments: list[segments_models.Segment]) -> list[segments_schema.SimilarSegmentOut]:
    return [segments_schema.SimilarSegmentOut(id=s.id, name=s.name) for s in segments]


def _effort_out(
    effort: segments_models.SegmentEffort, segment_name: str, activity_name: str | None
) -> segments_schema.EffortOut:
    return segments_schema.EffortOut(
        id=effort.id,
        segment_id=effort.segment_id,
        segment_name=segment_name,
        activity_id=effort.activity_id,
        activity_name=activity_name,
        start_time=effort.start_time,
        end_time=effort.end_time,
        elapsed_s=effort.elapsed_s,
        moving_s=effort.moving_s,
        stopped_s=effort.stopped_s,
        gap_s=effort.gap_s,
        distance_m=effort.distance_m,
        elevation_gain_m=effort.elevation_gain_m,
        elevation_loss_m=effort.elevation_loss_m,
        net_elevation_m=effort.net_elevation_m,
        average_hr=effort.average_hr,
        max_hr=effort.max_hr,
        matcher_version=effort.matcher_version,
        details=effort.details,
    )


@router.get("", response_model=list[segments_schema.SegmentOut])
def list_segments(
    _validate_access_token: _Validated, _check_scopes: _CanRead, token_user_id: _UserId, db: _Db
) -> list[segments_schema.SegmentOut]:
    """The user's segments, by name, each with how many activities have passed it."""
    return [
        _segment_out(segment, len(segments_crud.get_efforts_for_segment(segment.id, db)))
        for segment in segments_crud.get_user_segments(token_user_id, db)
    ]


@router.post("", response_model=segments_schema.SegmentSavedOut, status_code=status.HTTP_201_CREATED)
def create_segment(
    body: segments_schema.SegmentIn,
    _validate_access_token: _Validated,
    _check_scopes: _CanWrite,
    token_user_id: _UserId,
    db: _Db,
) -> segments_schema.SegmentSavedOut:
    """Create a segment and find the activities that pass it."""
    start, end = body.start.to_node(), body.end.to_node()
    try:
        segment = segments_crud.create_segment(token_user_id, body.name, start, end, db)
    except ValueError as err:
        raise _unprocessable(err) from err
    efforts = segments_service.refresh_segment_efforts(segment, db)
    similar = segments_service.find_similar_segments(token_user_id, start, end, db, exclude_id=segment.id)
    return segments_schema.SegmentSavedOut(
        **_segment_out(segment, len(efforts)).model_dump(), similar_segments=_similar_out(similar)
    )


@router.post("/preview", response_model=segments_schema.PreviewOut)
def preview_segment(
    body: segments_schema.PreviewIn,
    _validate_access_token: _Validated,
    _check_scopes: _CanRead,
    token_user_id: _UserId,
    db: _Db,
) -> segments_schema.PreviewOut:
    """Which of the user's activities would pass these nodes, with times. Nothing is saved."""
    start, end = body.start.to_node(), body.end.to_node()
    try:
        result = segments_service.preview(token_user_id, start, end, db)
    except ValueError as err:
        raise _unprocessable(err) from err
    similar = segments_service.find_similar_segments(token_user_id, start, end, db)
    return segments_schema.PreviewOut(
        matches=[
            segments_schema.PreviewMatchOut(
                activity_id=hit.activity_id,
                activity_name=hit.activity_name,
                start_time=hit.start_time,
                end_time=hit.end_time,
                elapsed_s=hit.match.elapsed_s,
                moving_s=hit.match.moving_s,
                stopped_s=hit.match.stopped_s,
                gap_s=hit.match.gap_s,
                distance_m=hit.match.distance_m,
                elevation_gain_m=hit.match.elevation_gain_m,
                elevation_loss_m=hit.match.elevation_loss_m,
                net_elevation_m=hit.match.net_elevation_m,
                average_hr=hit.match.average_hr,
                max_hr=hit.match.max_hr,
                start_visits=hit.match.start_visits,
                end_visits=hit.match.end_visits,
                closest_start_m=hit.closest_start_m,
                closest_end_m=hit.closest_end_m,
                start_visit_times=list(hit.start_visit_times),
                end_visit_times=list(hit.end_visit_times),
            )
            for hit in result.matches
        ],
        near_misses=[
            segments_schema.NearMissOut(
                activity_id=miss.activity_id,
                activity_name=miss.activity_name,
                start_time=miss.start_time,
                reason=miss.reason,
                closest_start_m=miss.closest_start_m,
                closest_end_m=miss.closest_end_m,
            )
            for miss in result.near_misses
        ],
        similar_segments=_similar_out(similar),
    )


@router.post("/parse-coordinates", response_model=segments_schema.ParsedCoordinatesOut)
def parse_coordinates(
    body: segments_schema.ParseCoordinatesIn,
    _validate_access_token: _Validated,
    _check_scopes: _CanRead,
) -> segments_schema.ParsedCoordinatesOut:
    """Turn a pasted ``60.39, 5.32`` into latitude and longitude, for the editor's coordinate field."""
    try:
        lat, lon = segments_coordinates.parse_coordinates(body.text)
    except segments_coordinates.CoordinateError as err:
        raise _unprocessable(err) from err
    return segments_schema.ParsedCoordinatesOut(lat=lat, lon=lon)


@router.get("/activities/{activity_id}/efforts", response_model=list[segments_schema.EffortOut])
def get_activity_efforts(
    activity_id: int, _validate_access_token: _Validated, _check_scopes: _CanRead, token_user_id: _UserId, db: _Db
) -> list[segments_schema.EffortOut]:
    """The segments one of the user's activities has passed."""
    if segments_service.activity_owner(activity_id, db) != token_user_id:
        raise _not_found("Activity")
    names = segments_service.activity_names([activity_id], db)
    segment_names = {s.id: s.name for s in segments_crud.get_user_segments(token_user_id, db)}
    return [
        _effort_out(effort, segment_names[effort.segment_id], names.get(activity_id))
        for effort in segments_crud.get_efforts_for_activity(activity_id, db)
        if effort.segment_id in segment_names
    ]


@router.get("/{segment_id}", response_model=segments_schema.SegmentOut)
def get_segment(
    segment_id: int, _validate_access_token: _Validated, _check_scopes: _CanRead, token_user_id: _UserId, db: _Db
) -> segments_schema.SegmentOut:
    segment = _own_segment(segment_id, token_user_id, db)
    return _segment_out(segment, len(segments_crud.get_efforts_for_segment(segment.id, db)))


@router.put("/{segment_id}", response_model=segments_schema.SegmentSavedOut)
def update_segment(
    segment_id: int,
    body: segments_schema.SegmentIn,
    _validate_access_token: _Validated,
    _check_scopes: _CanWrite,
    token_user_id: _UserId,
    db: _Db,
) -> segments_schema.SegmentSavedOut:
    """Change the name and nodes, then recompute the efforts (old ones from the earlier nodes are dropped)."""
    segment = _own_segment(segment_id, token_user_id, db)
    start, end = body.start.to_node(), body.end.to_node()
    try:
        segments_crud.update_segment(segment, body.name, start, end, db)
    except ValueError as err:
        raise _unprocessable(err) from err
    efforts = segments_service.refresh_segment_efforts(segment, db)
    similar = segments_service.find_similar_segments(token_user_id, start, end, db, exclude_id=segment.id)
    return segments_schema.SegmentSavedOut(
        **_segment_out(segment, len(efforts)).model_dump(), similar_segments=_similar_out(similar)
    )


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment(
    segment_id: int, _validate_access_token: _Validated, _check_scopes: _CanWrite, token_user_id: _UserId, db: _Db
) -> None:
    """Delete the segment and its efforts."""
    segments_crud.delete_segment(_own_segment(segment_id, token_user_id, db), db)


@router.get("/{segment_id}/efforts", response_model=list[segments_schema.EffortOut])
def get_segment_efforts(
    segment_id: int, _validate_access_token: _Validated, _check_scopes: _CanRead, token_user_id: _UserId, db: _Db
) -> list[segments_schema.EffortOut]:
    """All passes of the segment, oldest first, for comparing tours."""
    segment = _own_segment(segment_id, token_user_id, db)
    efforts = segments_crud.get_efforts_for_segment(segment.id, db)
    names = segments_service.activity_names([e.activity_id for e in efforts], db)
    return [_effort_out(effort, segment.name, names.get(effort.activity_id)) for effort in efforts]


@router.post("/{segment_id}/refresh", response_model=segments_schema.SegmentOut)
def refresh_segment(
    segment_id: int, _validate_access_token: _Validated, _check_scopes: _CanWrite, token_user_id: _UserId, db: _Db
) -> segments_schema.SegmentOut:
    """Recompute the segment's efforts from the user's activities (for example after the matcher changed)."""
    segment = _own_segment(segment_id, token_user_id, db)
    return _segment_out(segment, len(segments_service.refresh_segment_efforts(segment, db)))
