import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Color, Part
from app.collections.models import Collection, CollectionPiece


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_catalog(db: AsyncSession) -> tuple[Part, Color]:
    part = Part(part_num="3001", name="Brick 2x4", category_id=1)
    color = Color(id=1, name="Red", rgb="FF0000", is_trans=False)
    db.add(part)
    db.add(color)
    await db.commit()
    return part, color


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_collection(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.post(
        "/collections",
        json={"name": "My First Collection", "description": "A test collection"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My First Collection"
    assert data["description"] == "A test collection"
    assert data["piece_count"] == 0
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_collection_no_description(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.post("/collections", json={"name": "Minimal"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["description"] is None


@pytest.mark.asyncio
async def test_create_collection_requires_auth(client: AsyncClient):
    resp = await client.post("/collections", json={"name": "No auth"})
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_collections_empty(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    resp = await client.get("/collections", headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_collections_returns_own(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    await client.post("/collections", json={"name": "A"}, headers=headers)
    await client.post("/collections", json={"name": "B"}, headers=headers)

    resp = await client.get("/collections", headers=headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "A" in names
    assert "B" in names
    assert len(names) == 2


@pytest.mark.asyncio
async def test_list_collections_isolates_users(client: AsyncClient, make_user, auth_headers):
    user1 = await make_user(apple_sub="u1", email="u1@x.com")
    user2 = await make_user(apple_sub="u2", email="u2@x.com")

    await client.post("/collections", json={"name": "User1 col"}, headers=auth_headers(user1.id))

    resp = await client.get("/collections", headers=auth_headers(user2.id))
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_collection(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    created = (await client.post("/collections", json={"name": "Solo"}, headers=headers)).json()
    resp = await client.get(f"/collections/{created['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Solo"


@pytest.mark.asyncio
async def test_get_collection_not_found(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    resp = await client.get(f"/collections/{uuid.uuid4()}", headers=auth_headers(user.id))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_collection_cross_user_denied(client: AsyncClient, make_user, auth_headers):
    user1 = await make_user(apple_sub="u1", email="u1@x.com")
    user2 = await make_user(apple_sub="u2", email="u2@x.com")

    created = (
        await client.post("/collections", json={"name": "Private"}, headers=auth_headers(user1.id))
    ).json()

    resp = await client.get(f"/collections/{created['id']}", headers=auth_headers(user2.id))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_collection(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    created = (await client.post("/collections", json={"name": "Old Name"}, headers=headers)).json()

    resp = await client.patch(
        f"/collections/{created['id']}",
        json={"name": "New Name", "description": "Updated"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["description"] == "Updated"


@pytest.mark.asyncio
async def test_update_collection_partial(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    created = (
        await client.post(
            "/collections", json={"name": "Original", "description": "Keep me"}, headers=headers
        )
    ).json()

    resp = await client.patch(
        f"/collections/{created['id']}", json={"name": "Changed"}, headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Changed"
    # description unchanged because update body didn't include it
    assert data["description"] == "Keep me"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_collection(client: AsyncClient, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    created = (await client.post("/collections", json={"name": "Bye"}, headers=headers)).json()

    resp = await client.delete(f"/collections/{created['id']}", headers=headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"/collections/{created['id']}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_collection_cross_user_denied(client: AsyncClient, make_user, auth_headers):
    user1 = await make_user(apple_sub="u1", email="u1@x.com")
    user2 = await make_user(apple_sub="u2", email="u2@x.com")

    created = (
        await client.post("/collections", json={"name": "Mine"}, headers=auth_headers(user1.id))
    ).json()

    resp = await client.delete(f"/collections/{created['id']}", headers=auth_headers(user2.id))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_collections(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    user = await make_user()
    headers = auth_headers(user.id)

    # Seed catalog
    await _seed_catalog(db_session)

    # Create target and source collections
    target = (await client.post("/collections", json={"name": "Target"}, headers=headers)).json()
    source = (await client.post("/collections", json={"name": "Source"}, headers=headers)).json()

    target_id = uuid.UUID(target["id"])
    source_id = uuid.UUID(source["id"])

    # Add pieces directly via DB to avoid needing Task 9 endpoints
    piece_target = CollectionPiece(
        id=uuid.uuid4(),
        collection_id=target_id,
        part_num="3001",
        color_id=1,
        quantity=5,
    )
    piece_source_same = CollectionPiece(
        id=uuid.uuid4(),
        collection_id=source_id,
        part_num="3001",
        color_id=1,
        quantity=3,
    )
    db_session.add(piece_target)
    db_session.add(piece_source_same)
    await db_session.commit()

    # Merge source into target
    resp = await client.post(
        f"/collections/{target_id}/merge",
        json={"source_collection_id": str(source_id)},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["piece_count"] == 8  # 5 + 3

    # Source should be gone
    get_resp = await client.get(f"/collections/{source_id}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_cross_user_denied(client: AsyncClient, make_user, auth_headers):
    user1 = await make_user(apple_sub="u1", email="u1@x.com")
    user2 = await make_user(apple_sub="u2", email="u2@x.com")

    target = (
        await client.post("/collections", json={"name": "Target"}, headers=auth_headers(user1.id))
    ).json()
    source = (
        await client.post("/collections", json={"name": "Source"}, headers=auth_headers(user2.id))
    ).json()

    resp = await client.post(
        f"/collections/{target['id']}/merge",
        json={"source_collection_id": source["id"]},
        headers=auth_headers(user1.id),
    )
    # source belongs to user2, so 404
    assert resp.status_code == 404
