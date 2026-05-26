import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.collections.models import Collection, CollectionPiece
from app.collections.schemas import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    MergeRequest,
    PieceCreate,
    PieceListResponse,
    PieceResponse,
    PieceUpdate,
)
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/collections", tags=["collections"])


async def _get_user_collection(
    collection_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Collection:
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.user_id == user.id,
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


def _collection_response(collection: Collection, piece_count: int) -> CollectionResponse:
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        piece_count=piece_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionResponse:
    collection = Collection(
        id=uuid.uuid4(),
        user_id=user.id,
        name=body.name,
        description=body.description,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return _collection_response(collection, 0)


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CollectionResponse]:
    result = await db.execute(
        select(
            Collection,
            func.coalesce(func.sum(CollectionPiece.quantity), 0).label("piece_count"),
        )
        .outerjoin(CollectionPiece, CollectionPiece.collection_id == Collection.id)
        .where(Collection.user_id == user.id)
        .group_by(Collection.id)
        .order_by(Collection.created_at)
    )
    rows = result.all()
    return [_collection_response(col, int(count)) for col, count in rows]


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionResponse:
    collection = await _get_user_collection(collection_id, user, db)
    result = await db.execute(
        select(func.coalesce(func.sum(CollectionPiece.quantity), 0)).where(
            CollectionPiece.collection_id == collection_id
        )
    )
    piece_count = int(result.scalar_one())
    return _collection_response(collection, piece_count)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionResponse:
    collection = await _get_user_collection(collection_id, user, db)
    if body.name is not None:
        collection.name = body.name
    if body.description is not None:
        collection.description = body.description
    await db.commit()
    await db.refresh(collection)
    result = await db.execute(
        select(func.coalesce(func.sum(CollectionPiece.quantity), 0)).where(
            CollectionPiece.collection_id == collection_id
        )
    )
    piece_count = int(result.scalar_one())
    return _collection_response(collection, piece_count)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    collection = await _get_user_collection(collection_id, user, db)
    await db.delete(collection)
    await db.commit()


@router.post("/{collection_id}/merge", response_model=CollectionResponse)
async def merge_collections(
    collection_id: uuid.UUID,
    body: MergeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionResponse:
    target = await _get_user_collection(collection_id, user, db)
    source = await _get_user_collection(body.source_collection_id, user, db)

    if source.id == target.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source and target must differ")

    # Load all source pieces
    src_result = await db.execute(
        select(CollectionPiece).where(CollectionPiece.collection_id == source.id)
    )
    source_pieces = src_result.scalars().all()

    # Load all target pieces indexed by (part_num, color_id)
    tgt_result = await db.execute(
        select(CollectionPiece).where(CollectionPiece.collection_id == target.id)
    )
    target_pieces = {(p.part_num, p.color_id): p for p in tgt_result.scalars().all()}

    for src_piece in source_pieces:
        key = (src_piece.part_num, src_piece.color_id)
        if key in target_pieces:
            target_pieces[key].quantity += src_piece.quantity
        else:
            new_piece = CollectionPiece(
                id=uuid.uuid4(),
                collection_id=target.id,
                part_num=src_piece.part_num,
                color_id=src_piece.color_id,
                quantity=src_piece.quantity,
            )
            db.add(new_piece)

    await db.delete(source)
    await db.commit()
    await db.refresh(target)

    result = await db.execute(
        select(func.coalesce(func.sum(CollectionPiece.quantity), 0)).where(
            CollectionPiece.collection_id == target.id
        )
    )
    piece_count = int(result.scalar_one())
    return _collection_response(target, piece_count)


# ---------------------------------------------------------------------------
# Piece endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{collection_id}/pieces",
    response_model=PieceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_piece(
    collection_id: uuid.UUID,
    body: PieceCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PieceResponse:
    await _get_user_collection(collection_id, user, db)

    result = await db.execute(
        select(CollectionPiece).where(
            CollectionPiece.collection_id == collection_id,
            CollectionPiece.part_num == body.part_num,
            CollectionPiece.color_id == body.color_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.quantity += body.quantity
        await db.commit()
        await db.refresh(existing)
        return PieceResponse.model_validate(existing)

    piece = CollectionPiece(
        id=uuid.uuid4(),
        collection_id=collection_id,
        part_num=body.part_num,
        color_id=body.color_id,
        quantity=body.quantity,
    )
    db.add(piece)
    await db.commit()
    await db.refresh(piece)
    return PieceResponse.model_validate(piece)


@router.get("/{collection_id}/pieces", response_model=PieceListResponse)
async def list_pieces(
    collection_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PieceListResponse:
    await _get_user_collection(collection_id, user, db)

    query = select(CollectionPiece).where(CollectionPiece.collection_id == collection_id)

    if cursor is not None:
        try:
            cursor_id = uuid.UUID(base64.b64decode(cursor).decode())
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor")
        query = query.where(CollectionPiece.id > cursor_id)

    query = query.order_by(CollectionPiece.id).limit(limit + 1)
    result = await db.execute(query)
    pieces = result.scalars().all()

    next_cursor: str | None = None
    if len(pieces) > limit:
        pieces = pieces[:limit]
        next_cursor = base64.b64encode(str(pieces[-1].id).encode()).decode()

    return PieceListResponse(
        items=[PieceResponse.model_validate(p) for p in pieces],
        next_cursor=next_cursor,
    )


@router.patch("/{collection_id}/pieces/{piece_id}", response_model=PieceResponse)
async def update_piece(
    collection_id: uuid.UUID,
    piece_id: uuid.UUID,
    body: PieceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PieceResponse:
    await _get_user_collection(collection_id, user, db)

    result = await db.execute(
        select(CollectionPiece).where(
            CollectionPiece.id == piece_id,
            CollectionPiece.collection_id == collection_id,
        )
    )
    piece = result.scalar_one_or_none()
    if piece is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Piece not found")

    piece.quantity = body.quantity
    await db.commit()
    await db.refresh(piece)
    return PieceResponse.model_validate(piece)


@router.delete("/{collection_id}/pieces/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_piece(
    collection_id: uuid.UUID,
    piece_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_user_collection(collection_id, user, db)

    result = await db.execute(
        select(CollectionPiece).where(
            CollectionPiece.id == piece_id,
            CollectionPiece.collection_id == collection_id,
        )
    )
    piece = result.scalar_one_or_none()
    if piece is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Piece not found")

    await db.delete(piece)
    await db.commit()
