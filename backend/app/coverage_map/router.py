"""HTTP endpoints for the coverage map (``/api/v1/coverage``).

Coverage is per user: the cells answered are the ones the caller's own
activities passed through. The handlers are plain ``def`` so FastAPI runs them
in its thread pool — the rebuild reads the GPS stream of every activity.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
import coverage_map.crud as coverage_crud
import coverage_map.schema as coverage_schema
import coverage_map.service as coverage_service
import coverage_map.tiles as coverage_tiles

router = APIRouter()

_Validated = Annotated[Callable, Depends(auth_dependencies.validate_access_token)]
_CanRead = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])]
_CanWrite = Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])]
_UserId = Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)]
_Db = Annotated[Session, Depends(core_database.get_db)]

# The zoom the map shows by default: about 300 m cells in southern Norway.
DEFAULT_ZOOM = coverage_tiles.STORE_ZOOM - 1


@router.get("", response_model=coverage_schema.CoverageOut)
def get_coverage(
    _validate_access_token: _Validated,
    _check_scopes: _CanRead,
    token_user_id: _UserId,
    db: _Db,
    zoom: Annotated[int, Query(ge=coverage_tiles.MIN_ZOOM, le=coverage_tiles.MAX_ZOOM)] = DEFAULT_ZOOM,
) -> coverage_schema.CoverageOut:
    """Where the user has been, counted in cells, with how many tours passed through each."""
    try:
        counts = coverage_crud.cell_counts(token_user_id, zoom, db)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    return coverage_schema.CoverageOut(
        zoom=zoom,
        cells=[coverage_schema.CellOut(x=cell.x, y=cell.y, count=cell.count) for cell in counts],
        max_count=max((cell.count for cell in counts), default=0),
    )


@router.post("/refresh", response_model=coverage_schema.RefreshOut)
def refresh_coverage(
    _validate_access_token: _Validated, _check_scopes: _CanWrite, token_user_id: _UserId, db: _Db
) -> coverage_schema.RefreshOut:
    """Rebuild the grid from every activity the user owns.

    Needed after an import that does not go through the hook (a Strava file),
    and after the cells or the filling rules change.
    """
    activities = coverage_service.refresh_user_cells(token_user_id, db)
    counts = coverage_crud.cell_counts(token_user_id, coverage_tiles.STORE_ZOOM, db)
    return coverage_schema.RefreshOut(activities=activities, cells=len(counts))
