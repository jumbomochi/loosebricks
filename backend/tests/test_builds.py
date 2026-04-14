import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Color, Part, Set, SetPart
from app.collections.models import Collection, CollectionPiece


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------


async def _seed_builds_data(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """
    Seed:
    - 3 parts (3001, 3003, 3010) and 2 colors (1=Red, 4=Blue)
    - Set A (10001-1): 10x 3001-red + 5x 3003-blue = 15 parts total
    - Set B (10002-1): 100x 3001-red + 50x 3010-red = 150 parts total
    - User collection: 10x 3001-red + 5x 3003-blue (100% of Set A, ~6.7% of Set B)
    """
    # Parts
    parts = [
        Part(part_num="3001", name="Brick 2x4", category_id=1),
        Part(part_num="3003", name="Brick 2x2", category_id=1),
        Part(part_num="3010", name="Brick 1x4", category_id=1),
    ]
    # Colors
    colors = [
        Color(id=1, name="Red", rgb="FF0000", is_trans=False),
        Color(id=4, name="Blue", rgb="0000FF", is_trans=False),
    ]
    for obj in parts + colors:
        db.add(obj)

    # Sets
    set_a = Set(set_num="10001-1", name="Set A", year=2020, num_parts=15, theme_id=1)
    set_b = Set(set_num="10002-1", name="Set B", year=2021, num_parts=150, theme_id=1)
    db.add(set_a)
    db.add(set_b)
    await db.flush()

    # Set A parts: 10x 3001-red + 5x 3003-blue
    db.add(SetPart(set_num="10001-1", part_num="3001", color_id=1, quantity=10))
    db.add(SetPart(set_num="10001-1", part_num="3003", color_id=4, quantity=5))

    # Set B parts: 100x 3001-red + 50x 3010-red
    db.add(SetPart(set_num="10002-1", part_num="3001", color_id=1, quantity=100))
    db.add(SetPart(set_num="10002-1", part_num="3010", color_id=1, quantity=50))

    # User collection
    collection_id = uuid.uuid4()
    collection = Collection(
        id=collection_id,
        user_id=user_id,
        name="My Bricks",
    )
    db.add(collection)
    await db.flush()

    # Collection pieces: 10x 3001-red + 5x 3003-blue
    db.add(CollectionPiece(
        id=uuid.uuid4(),
        collection_id=collection_id,
        part_num="3001",
        color_id=1,
        quantity=10,
    ))
    db.add(CollectionPiece(
        id=uuid.uuid4(),
        collection_id=collection_id,
        part_num="3003",
        color_id=4,
        quantity=5,
    ))

    await db.commit()

    return {"collection_id": collection_id}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_returns_matching_sets(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    auth_headers,
):
    """With min_completeness=70, only Set A (100%) should be returned."""
    user = await make_user()
    seeded = await _seed_builds_data(db_session, user.id)
    collection_id = seeded["collection_id"]
    headers = auth_headers(user.id)

    resp = await client.get(
        f"/builds/suggest?collection_ids={collection_id}&min_completeness=70",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    set_nums = [item["set_num"] for item in data["items"]]
    assert "10001-1" in set_nums
    assert "10002-1" not in set_nums


@pytest.mark.asyncio
async def test_suggest_low_threshold_returns_more(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    auth_headers,
):
    """With min_completeness=5, both sets should be returned."""
    user = await make_user()
    seeded = await _seed_builds_data(db_session, user.id)
    collection_id = seeded["collection_id"]
    headers = auth_headers(user.id)

    resp = await client.get(
        f"/builds/suggest?collection_ids={collection_id}&min_completeness=5",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    set_nums = [item["set_num"] for item in data["items"]]
    assert "10001-1" in set_nums
    assert "10002-1" in set_nums


@pytest.mark.asyncio
async def test_suggest_default_threshold_70(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    auth_headers,
):
    """Without min_completeness param, defaults to 70, only Set A returned."""
    user = await make_user()
    seeded = await _seed_builds_data(db_session, user.id)
    collection_id = seeded["collection_id"]
    headers = auth_headers(user.id)

    resp = await client.get(
        f"/builds/suggest?collection_ids={collection_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    set_nums = [item["set_num"] for item in data["items"]]
    assert "10001-1" in set_nums
    assert "10002-1" not in set_nums


@pytest.mark.asyncio
async def test_build_details(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    auth_headers,
):
    """Set A detail: 100% complete, 2 have items, 0 missing."""
    user = await make_user()
    seeded = await _seed_builds_data(db_session, user.id)
    collection_id = seeded["collection_id"]
    headers = auth_headers(user.id)

    resp = await client.get(
        f"/builds/10001-1/details?collection_ids={collection_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["set_num"] == "10001-1"
    assert data["completeness_pct"] == 100.0
    assert len(data["have"]) == 2
    assert len(data["missing"]) == 0


@pytest.mark.asyncio
async def test_build_details_with_missing_pieces(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    auth_headers,
):
    """Set B detail: shows missing pieces for 3001 (need 100, have 10) and 3010 (need 50, have 0)."""
    user = await make_user()
    seeded = await _seed_builds_data(db_session, user.id)
    collection_id = seeded["collection_id"]
    headers = auth_headers(user.id)

    resp = await client.get(
        f"/builds/10002-1/details?collection_ids={collection_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["set_num"] == "10002-1"

    # Both parts should be in missing (have 10 < need 100, have 0 < need 50)
    missing_parts = {p["part_num"]: p for p in data["missing"]}
    assert "3001" in missing_parts
    assert missing_parts["3001"]["needed"] == 100
    assert missing_parts["3001"]["have"] == 10

    assert "3010" in missing_parts
    assert missing_parts["3010"]["needed"] == 50
    assert missing_parts["3010"]["have"] == 0

    assert len(data["have"]) == 0


@pytest.mark.asyncio
async def test_suggest_rejects_other_users_collections(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    auth_headers,
):
    """A user cannot query builds using another user's collection — expect 404."""
    owner = await make_user(apple_sub="owner-sub", email="owner@example.com")
    attacker = await make_user(apple_sub="attacker-sub", email="attacker@example.com")

    seeded = await _seed_builds_data(db_session, owner.id)
    collection_id = seeded["collection_id"]

    # Attacker uses their own valid JWT but passes the owner's collection id
    headers = auth_headers(attacker.id)
    resp = await client.get(
        f"/builds/suggest?collection_ids={collection_id}&min_completeness=0",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_build_details_rejects_other_users_collections(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    auth_headers,
):
    """A user cannot fetch build details using another user's collection — expect 404."""
    owner = await make_user(apple_sub="owner2-sub", email="owner2@example.com")
    attacker = await make_user(apple_sub="attacker2-sub", email="attacker2@example.com")

    seeded = await _seed_builds_data(db_session, owner.id)
    collection_id = seeded["collection_id"]

    headers = auth_headers(attacker.id)
    resp = await client.get(
        f"/builds/10001-1/details?collection_ids={collection_id}",
        headers=headers,
    )
    assert resp.status_code == 404
