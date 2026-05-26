import base64
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Color, Part


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def catalog(db_session: AsyncSession):
    """Seed one Part and one Color for FK references."""
    part = Part(part_num="3001", name="Brick 2x4", category_id=1)
    color = Color(id=1, name="Red", rgb="FF0000", is_trans=False)
    db_session.add(part)
    db_session.add(color)
    await db_session.commit()
    return part, color


@pytest.fixture
async def collection_id(client: AsyncClient, make_user, auth_headers):
    """Create a user + collection, return (collection_id_str, headers)."""
    user = await make_user()
    headers = auth_headers(user.id)
    resp = await client.post("/collections", json={"name": "Pieces Col"}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"], headers


# ---------------------------------------------------------------------------
# Add piece
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_piece(client: AsyncClient, catalog, collection_id):
    col_id, headers = collection_id

    resp = await client.post(
        f"/collections/{col_id}/pieces",
        json={"part_num": "3001", "color_id": 1, "quantity": 4},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["part_num"] == "3001"
    assert data["color_id"] == 1
    assert data["quantity"] == 4
    assert "id" in data


@pytest.mark.asyncio
async def test_add_piece_duplicate_increments(client: AsyncClient, catalog, collection_id):
    col_id, headers = collection_id

    await client.post(
        f"/collections/{col_id}/pieces",
        json={"part_num": "3001", "color_id": 1, "quantity": 4},
        headers=headers,
    )
    resp = await client.post(
        f"/collections/{col_id}/pieces",
        json={"part_num": "3001", "color_id": 1, "quantity": 6},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["quantity"] == 10


@pytest.mark.asyncio
async def test_add_piece_wrong_collection(client: AsyncClient, catalog, make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.post(
        f"/collections/{uuid.uuid4()}/pieces",
        json={"part_num": "3001", "color_id": 1, "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List pieces (pagination)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pieces_empty(client: AsyncClient, catalog, collection_id):
    col_id, headers = collection_id

    resp = await client.get(f"/collections/{col_id}/pieces", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_pieces_pagination(
    client: AsyncClient, catalog, db_session: AsyncSession, make_user, auth_headers
):
    from app.catalog.models import Color, Part
    from app.collections.models import CollectionPiece

    user = await make_user(apple_sub="paguser", email="pag@x.com")
    headers = auth_headers(user.id)

    col_resp = await client.post("/collections", json={"name": "Paginated"}, headers=headers)
    col_id = col_resp.json()["id"]

    # Seed extra parts/colors and add 5 pieces
    for i in range(2, 7):
        part = Part(part_num=f"300{i}", name=f"Brick {i}", category_id=1)
        color = Color(id=i, name=f"Color{i}", rgb="AABBCC", is_trans=False)
        db_session.add(part)
        db_session.add(color)
    await db_session.commit()

    piece_ids = []
    for i in range(1, 6):
        # Use part_num that exists: 3001 for i=1, 3002..3006 for i=2..5
        pn = "3001" if i == 1 else f"300{i}"
        ci = 1 if i == 1 else i
        resp = await client.post(
            f"/collections/{col_id}/pieces",
            json={"part_num": pn, "color_id": ci, "quantity": i},
            headers=headers,
        )
        piece_ids.append(resp.json()["id"])

    # Fetch first page (limit=3)
    resp1 = await client.get(f"/collections/{col_id}/pieces?limit=3", headers=headers)
    assert resp1.status_code == 200
    page1 = resp1.json()
    assert len(page1["items"]) == 3
    assert page1["next_cursor"] is not None

    # Fetch second page using cursor
    cursor = page1["next_cursor"]
    resp2 = await client.get(
        f"/collections/{col_id}/pieces?limit=3&cursor={cursor}", headers=headers
    )
    assert resp2.status_code == 200
    page2 = resp2.json()
    assert len(page2["items"]) == 2
    assert page2["next_cursor"] is None

    # No duplicates across pages
    ids1 = {i["id"] for i in page1["items"]}
    ids2 = {i["id"] for i in page2["items"]}
    assert ids1.isdisjoint(ids2)


# ---------------------------------------------------------------------------
# Update piece
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_piece(client: AsyncClient, catalog, collection_id):
    col_id, headers = collection_id

    created = (
        await client.post(
            f"/collections/{col_id}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 2},
            headers=headers,
        )
    ).json()

    resp = await client.patch(
        f"/collections/{col_id}/pieces/{created['id']}",
        json={"quantity": 99},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 99


@pytest.mark.asyncio
async def test_update_piece_not_found(client: AsyncClient, catalog, collection_id):
    col_id, headers = collection_id

    resp = await client.patch(
        f"/collections/{col_id}/pieces/{uuid.uuid4()}",
        json={"quantity": 1},
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete piece
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_piece(client: AsyncClient, catalog, collection_id):
    col_id, headers = collection_id

    created = (
        await client.post(
            f"/collections/{col_id}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 7},
            headers=headers,
        )
    ).json()

    resp = await client.delete(
        f"/collections/{col_id}/pieces/{created['id']}", headers=headers
    )
    assert resp.status_code == 204

    # Confirm gone
    list_resp = await client.get(f"/collections/{col_id}/pieces", headers=headers)
    assert list_resp.json()["items"] == []


@pytest.mark.asyncio
async def test_delete_piece_not_found(client: AsyncClient, catalog, collection_id):
    col_id, headers = collection_id

    resp = await client.delete(
        f"/collections/{col_id}/pieces/{uuid.uuid4()}", headers=headers
    )
    assert resp.status_code == 404
