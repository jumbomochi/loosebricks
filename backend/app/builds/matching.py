import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.builds.schemas import BuildDetailResponse, BuildPieceDetail, BuildSuggestion
from app.catalog.models import Moc, MocPart, Set, SetPart
from app.collections.models import Collection, CollectionPiece


def _user_pieces_subquery(collection_ids: list[uuid.UUID]):
    """Build a subquery aggregating user pieces across given collections."""
    return (
        select(
            CollectionPiece.part_num.label("part_num"),
            CollectionPiece.color_id.label("color_id"),
            func.sum(CollectionPiece.quantity).label("user_qty"),
        )
        .join(Collection, CollectionPiece.collection_id == Collection.id)
        .where(Collection.id.in_(collection_ids))
        .group_by(CollectionPiece.part_num, CollectionPiece.color_id)
        .subquery()
    )


async def find_matching_builds(
    db: AsyncSession,
    collection_ids: list[uuid.UUID],
    min_completeness: float = 70.0,
    min_parts: int | None = None,
    max_parts: int | None = None,
    theme_id: int | None = None,
    build_type: Literal["set", "moc", "all"] = "all",
    limit: int = 20,
) -> list[BuildSuggestion]:
    user_pieces = _user_pieces_subquery(collection_ids)

    results: list[BuildSuggestion] = []

    if build_type in ("set", "all"):
        set_query = (
            select(
                Set.set_num,
                Set.name,
                Set.year,
                Set.num_parts,
                func.sum(
                    func.least(
                        func.coalesce(user_pieces.c.user_qty, 0),
                        SetPart.quantity,
                    )
                ).label("matched_parts"),
                func.sum(SetPart.quantity).label("total_parts"),
            )
            .join(Set, SetPart.set_num == Set.set_num)
            .outerjoin(
                user_pieces,
                (SetPart.part_num == user_pieces.c.part_num)
                & (SetPart.color_id == user_pieces.c.color_id),
            )
            .group_by(Set.set_num, Set.name, Set.year, Set.num_parts)
            .having(
                (
                    100.0
                    * func.sum(
                        func.least(
                            func.coalesce(user_pieces.c.user_qty, 0),
                            SetPart.quantity,
                        )
                    )
                    / func.sum(SetPart.quantity)
                )
                >= min_completeness
            )
        )

        if min_parts is not None:
            set_query = set_query.where(Set.num_parts >= min_parts)
        if max_parts is not None:
            set_query = set_query.where(Set.num_parts <= max_parts)
        if theme_id is not None:
            set_query = set_query.where(Set.theme_id == theme_id)

        set_result = await db.execute(set_query)
        for row in set_result.all():
            matched = int(row.matched_parts)
            total = int(row.total_parts) or 1
            pct = round(100.0 * matched / total, 2)
            results.append(
                BuildSuggestion(
                    set_num=row.set_num,
                    name=row.name,
                    year=row.year,
                    num_parts=row.num_parts,
                    matched_parts=matched,
                    total_parts=int(row.total_parts),
                    completeness_pct=pct,
                )
            )

    if build_type in ("moc", "all"):
        moc_query = (
            select(
                Moc.set_num,
                Moc.name,
                Moc.num_parts,
                func.sum(
                    func.least(
                        func.coalesce(user_pieces.c.user_qty, 0),
                        MocPart.quantity,
                    )
                ).label("matched_parts"),
                func.sum(MocPart.quantity).label("total_parts"),
            )
            .join(Moc, MocPart.set_num == Moc.set_num)
            .outerjoin(
                user_pieces,
                (MocPart.part_num == user_pieces.c.part_num)
                & (MocPart.color_id == user_pieces.c.color_id),
            )
            .group_by(Moc.set_num, Moc.name, Moc.num_parts)
            .having(
                (
                    100.0
                    * func.sum(
                        func.least(
                            func.coalesce(user_pieces.c.user_qty, 0),
                            MocPart.quantity,
                        )
                    )
                    / func.sum(MocPart.quantity)
                )
                >= min_completeness
            )
        )

        if min_parts is not None:
            moc_query = moc_query.where(Moc.num_parts >= min_parts)
        if max_parts is not None:
            moc_query = moc_query.where(Moc.num_parts <= max_parts)

        moc_result = await db.execute(moc_query)
        for row in moc_result.all():
            matched = int(row.matched_parts)
            total = int(row.total_parts) or 1
            pct = round(100.0 * matched / total, 2)
            results.append(
                BuildSuggestion(
                    set_num=row.set_num,
                    name=row.name,
                    year=0,  # MOCs don't have a year field
                    num_parts=row.num_parts,
                    matched_parts=matched,
                    total_parts=int(row.total_parts),
                    completeness_pct=pct,
                )
            )

    results.sort(key=lambda x: x.completeness_pct, reverse=True)
    return results[:limit]


async def get_build_detail(
    db: AsyncSession,
    set_num: str,
    collection_ids: list[uuid.UUID],
) -> BuildDetailResponse | None:
    user_pieces = _user_pieces_subquery(collection_ids)

    # Try to find as a Set first
    set_result = await db.execute(select(Set).where(Set.set_num == set_num))
    build_set = set_result.scalar_one_or_none()

    if build_set is not None:
        parts_query = (
            select(
                SetPart.part_num,
                SetPart.color_id,
                SetPart.quantity.label("needed"),
                func.coalesce(user_pieces.c.user_qty, 0).label("have"),
            )
            .outerjoin(
                user_pieces,
                (SetPart.part_num == user_pieces.c.part_num)
                & (SetPart.color_id == user_pieces.c.color_id),
            )
            .where(SetPart.set_num == set_num)
        )
        parts_result = await db.execute(parts_query)
        rows = parts_result.all()

        have_list: list[BuildPieceDetail] = []
        missing_list: list[BuildPieceDetail] = []
        total_needed = 0
        total_matched = 0

        for row in rows:
            needed = row.needed
            have = int(row.have)
            total_needed += needed
            total_matched += min(have, needed)
            detail = BuildPieceDetail(
                part_num=row.part_num,
                color_id=row.color_id,
                needed=needed,
                have=have,
            )
            if have >= needed:
                have_list.append(detail)
            else:
                missing_list.append(detail)

        pct = round(100.0 * total_matched / total_needed, 2) if total_needed > 0 else 0.0
        return BuildDetailResponse(
            set_num=build_set.set_num,
            name=build_set.name,
            year=build_set.year,
            num_parts=build_set.num_parts,
            completeness_pct=pct,
            have=have_list,
            missing=missing_list,
        )

    # Try MOC
    moc_result = await db.execute(select(Moc).where(Moc.set_num == set_num))
    build_moc = moc_result.scalar_one_or_none()

    if build_moc is not None:
        parts_query = (
            select(
                MocPart.part_num,
                MocPart.color_id,
                MocPart.quantity.label("needed"),
                func.coalesce(user_pieces.c.user_qty, 0).label("have"),
            )
            .outerjoin(
                user_pieces,
                (MocPart.part_num == user_pieces.c.part_num)
                & (MocPart.color_id == user_pieces.c.color_id),
            )
            .where(MocPart.set_num == set_num)
        )
        parts_result = await db.execute(parts_query)
        rows = parts_result.all()

        have_list = []
        missing_list = []
        total_needed = 0
        total_matched = 0

        for row in rows:
            needed = row.needed
            have = int(row.have)
            total_needed += needed
            total_matched += min(have, needed)
            detail = BuildPieceDetail(
                part_num=row.part_num,
                color_id=row.color_id,
                needed=needed,
                have=have,
            )
            if have >= needed:
                have_list.append(detail)
            else:
                missing_list.append(detail)

        pct = round(100.0 * total_matched / total_needed, 2) if total_needed > 0 else 0.0
        return BuildDetailResponse(
            set_num=build_moc.set_num,
            name=build_moc.name,
            year=0,  # MOCs don't have a year field
            num_parts=build_moc.num_parts,
            completeness_pct=pct,
            have=have_list,
            missing=missing_list,
        )

    return None
