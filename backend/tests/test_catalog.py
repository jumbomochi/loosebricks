import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Color, Part


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_catalog(db: AsyncSession) -> None:
    parts = [
        Part(part_num="3001", name="Brick 2x4", category_id=1),
        Part(part_num="3003", name="Brick 2x2", category_id=1),
        Part(part_num="3004", name="Brick 1x2", category_id=1),
        Part(part_num="3005", name="Plate 1x1", category_id=2),
    ]
    colors = [
        Color(id=1, name="Red", rgb="FF0000", is_trans=False),
        Color(id=4, name="Blue", rgb="0000FF", is_trans=False),
        Color(id=15, name="White", rgb="FFFFFF", is_trans=False),
    ]
    for p in parts:
        db.add(p)
    for c in colors:
        db.add(c)
    await db.commit()


# ---------------------------------------------------------------------------
# Search by name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_parts_by_name(client: AsyncClient, db_session: AsyncSession, make_user, auth_headers):
    await _seed_catalog(db_session)
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.get("/catalog/parts?q=Brick", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    # Brick 2x4, Brick 2x2, Brick 1x2 all match "Brick"
    assert len(data["items"]) == 3
    names = {item["name"] for item in data["items"]}
    assert "Brick 2x4" in names
    assert "Brick 2x2" in names
    assert "Brick 1x2" in names


# ---------------------------------------------------------------------------
# Search by part number
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_parts_by_number(client: AsyncClient, db_session: AsyncSession, make_user, auth_headers):
    await _seed_catalog(db_session)
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.get("/catalog/parts?q=3001", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["part_num"] == "3001"
    assert data["items"][0]["name"] == "Brick 2x4"


# ---------------------------------------------------------------------------
# Partial search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_parts_partial(client: AsyncClient, db_session: AsyncSession, make_user, auth_headers):
    await _seed_catalog(db_session)
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.get("/catalog/parts?q=Plate", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["part_num"] == "3005"


# ---------------------------------------------------------------------------
# No query returns all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_parts_no_query(client: AsyncClient, db_session: AsyncSession, make_user, auth_headers):
    await _seed_catalog(db_session)
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.get("/catalog/parts", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 4


# ---------------------------------------------------------------------------
# List colors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_colors(client: AsyncClient, db_session: AsyncSession, make_user, auth_headers):
    await _seed_catalog(db_session)
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.get("/catalog/colors", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    # Should be ordered by name: Blue, Red, White
    assert data[0]["name"] == "Blue"
    assert data[1]["name"] == "Red"
    assert data[2]["name"] == "White"


# ---------------------------------------------------------------------------
# Get part detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_part_detail(client: AsyncClient, db_session: AsyncSession, make_user, auth_headers):
    await _seed_catalog(db_session)
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.get("/catalog/parts/3001", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["part_num"] == "3001"
    assert data["name"] == "Brick 2x4"
    assert data["category_id"] == 1


# ---------------------------------------------------------------------------
# Part not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_part_not_found(client: AsyncClient, db_session: AsyncSession, make_user, auth_headers):
    await _seed_catalog(db_session)
    user = await make_user()
    headers = auth_headers(user.id)

    resp = await client.get("/catalog/parts/NOTEXIST", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Part not found"


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catalog_requires_auth(client: AsyncClient):
    resp = await client.get("/catalog/parts")
    assert resp.status_code == 401

    resp = await client.get("/catalog/colors")
    assert resp.status_code == 401

    resp = await client.get("/catalog/parts/3001")
    assert resp.status_code == 401
