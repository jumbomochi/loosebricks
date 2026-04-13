from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.catalog.models import Color, Part
from app.catalog.schemas import ColorResponse, PartResponse, PartSearchResponse
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/parts", response_model=PartSearchResponse)
async def search_parts(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartSearchResponse:
    query = select(Part)
    if q:
        search_term = f"%{q}%"
        query = query.where(
            Part.name.ilike(search_term) | Part.part_num.ilike(search_term)
        )
    query = query.order_by(Part.part_num).limit(limit)
    result = await db.execute(query)
    parts = result.scalars().all()
    return PartSearchResponse(items=[PartResponse.model_validate(p) for p in parts])


@router.get("/colors", response_model=list[ColorResponse])
async def list_colors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ColorResponse]:
    result = await db.execute(select(Color).order_by(Color.name))
    colors = result.scalars().all()
    return [ColorResponse.model_validate(c) for c in colors]


@router.get("/parts/{part_num}", response_model=PartResponse)
async def get_part(
    part_num: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartResponse:
    result = await db.execute(select(Part).where(Part.part_num == part_num))
    part = result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Part not found")
    return PartResponse.model_validate(part)
