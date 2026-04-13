import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.builds.matching import find_matching_builds, get_build_detail
from app.builds.schemas import BuildDetailResponse, BuildSuggestResponse
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/builds", tags=["builds"])


def _parse_collection_ids(collection_ids: str) -> list[uuid.UUID]:
    """Parse a comma-separated string of UUIDs into a list."""
    try:
        return [uuid.UUID(cid.strip()) for cid in collection_ids.split(",") if cid.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid collection_id format",
        )


@router.get("/suggest", response_model=BuildSuggestResponse)
async def suggest_builds(
    collection_ids: str = Query(..., description="Comma-separated collection UUIDs"),
    min_completeness: float = Query(default=70.0, ge=0.0, le=100.0),
    min_parts: int | None = Query(default=None, ge=1),
    max_parts: int | None = Query(default=None, ge=1),
    theme_id: int | None = Query(default=None),
    type: Literal["set", "moc", "all"] = Query(default="all"),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BuildSuggestResponse:
    cids = _parse_collection_ids(collection_ids)
    suggestions = await find_matching_builds(
        db=db,
        collection_ids=cids,
        min_completeness=min_completeness,
        min_parts=min_parts,
        max_parts=max_parts,
        theme_id=theme_id,
        build_type=type,
        limit=limit,
    )
    return BuildSuggestResponse(items=suggestions)


@router.get("/{set_num}/details", response_model=BuildDetailResponse)
async def build_details(
    set_num: str,
    collection_ids: str = Query(..., description="Comma-separated collection UUIDs"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BuildDetailResponse:
    cids = _parse_collection_ids(collection_ids)
    detail = await get_build_detail(db=db, set_num=set_num, collection_ids=cids)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Build not found",
        )
    return detail
