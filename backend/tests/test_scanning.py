"""Tests for the scanning module: ML client and scanning router."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Color, Part
from app.collections.models import Collection, CollectionPiece
from app.scanning.ml_client import BrickognizeAdapter, Prediction
from app.scanning.models import Scan, ScanResult, ScanStatus


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


async def _seed_catalog_multi(db: AsyncSession) -> None:
    """Seed two parts and two colors."""
    part1 = Part(part_num="3001", name="Brick 2x4", category_id=1)
    part2 = Part(part_num="3002", name="Brick 1x2", category_id=1)
    color1 = Color(id=1, name="Red", rgb="FF0000", is_trans=False)
    color2 = Color(id=2, name="Blue", rgb="0000FF", is_trans=False)
    for obj in (part1, part2, color1, color2):
        db.add(obj)
    await db.commit()


# ---------------------------------------------------------------------------
# ML Client Tests
# ---------------------------------------------------------------------------


class TestBrickognizeAdapter:
    """Unit tests for BrickognizeAdapter using mocked HTTP clients."""

    @pytest.mark.asyncio
    async def test_predict_maps_response_correctly(self):
        """BrickognizeAdapter correctly maps Brickognize API items to Predictions."""
        fake_image_bytes = b"fake-image-data"
        fake_api_response = {
            "items": [
                {
                    "id": "3001",
                    "color": {"id": 1},
                    "score": 0.92,
                    "bounding_box": {"x": 10, "y": 20, "width": 50, "height": 60},
                },
                {
                    "id": "3002",
                    "color": {"id": 2},
                    "score": 0.55,
                },
            ]
        }

        # Mock the download response
        mock_download_resp = MagicMock()
        mock_download_resp.content = fake_image_bytes
        mock_download_resp.raise_for_status = MagicMock()

        # Mock the predict response
        mock_predict_resp = MagicMock()
        mock_predict_resp.json.return_value = fake_api_response
        mock_predict_resp.raise_for_status = MagicMock()

        adapter = BrickognizeAdapter()

        mock_download_client = AsyncMock()
        mock_download_client.__aenter__ = AsyncMock(return_value=mock_download_client)
        mock_download_client.__aexit__ = AsyncMock(return_value=False)
        mock_download_client.get = AsyncMock(return_value=mock_download_resp)

        with (
            patch("app.scanning.ml_client.httpx.AsyncClient", return_value=mock_download_client),
            patch.object(adapter._http_client, "post", AsyncMock(return_value=mock_predict_resp)),
        ):
            predictions = await adapter.predict("https://example.com/photo.jpg", "req-123")

        assert len(predictions) == 2

        p0 = predictions[0]
        assert p0.part_num == "3001"
        assert p0.color_id == 1
        assert p0.confidence == 0.92
        assert p0.bbox == {"x": 10, "y": 20, "w": 50, "h": 60}

        p1 = predictions[1]
        assert p1.part_num == "3002"
        assert p1.color_id == 2
        assert p1.confidence == 0.55
        assert p1.bbox is None

    @pytest.mark.asyncio
    async def test_predict_empty_items(self):
        """BrickognizeAdapter returns empty list when API returns no items."""
        fake_api_response = {"items": []}

        mock_download_resp = MagicMock()
        mock_download_resp.content = b"img"
        mock_download_resp.raise_for_status = MagicMock()

        mock_predict_resp = MagicMock()
        mock_predict_resp.json.return_value = fake_api_response
        mock_predict_resp.raise_for_status = MagicMock()

        adapter = BrickognizeAdapter()

        mock_download_client = AsyncMock()
        mock_download_client.__aenter__ = AsyncMock(return_value=mock_download_client)
        mock_download_client.__aexit__ = AsyncMock(return_value=False)
        mock_download_client.get = AsyncMock(return_value=mock_download_resp)

        with (
            patch("app.scanning.ml_client.httpx.AsyncClient", return_value=mock_download_client),
            patch.object(adapter._http_client, "post", AsyncMock(return_value=mock_predict_resp)),
        ):
            predictions = await adapter.predict("https://example.com/photo.jpg", "req-456")

        assert predictions == []

    @pytest.mark.asyncio
    async def test_predict_missing_items_key(self):
        """BrickognizeAdapter handles response without 'items' key gracefully."""
        fake_api_response = {}

        mock_download_resp = MagicMock()
        mock_download_resp.content = b"img"
        mock_download_resp.raise_for_status = MagicMock()

        mock_predict_resp = MagicMock()
        mock_predict_resp.json.return_value = fake_api_response
        mock_predict_resp.raise_for_status = MagicMock()

        adapter = BrickognizeAdapter()

        mock_download_client = AsyncMock()
        mock_download_client.__aenter__ = AsyncMock(return_value=mock_download_client)
        mock_download_client.__aexit__ = AsyncMock(return_value=False)
        mock_download_client.get = AsyncMock(return_value=mock_download_resp)

        with (
            patch("app.scanning.ml_client.httpx.AsyncClient", return_value=mock_download_client),
            patch.object(adapter._http_client, "post", AsyncMock(return_value=mock_predict_resp)),
        ):
            predictions = await adapter.predict("https://example.com/photo.jpg", "req-789")

        assert predictions == []

    def test_prediction_dataclass(self):
        """Prediction dataclass stores all fields correctly."""
        pred = Prediction(
            part_num="3003",
            color_id=5,
            confidence=0.88,
            bbox={"x": 0, "y": 0, "w": 100, "h": 100},
        )
        assert pred.part_num == "3003"
        assert pred.color_id == 5
        assert pred.confidence == 0.88
        assert pred.bbox == {"x": 0, "y": 0, "w": 100, "h": 100}

    def test_prediction_dataclass_no_bbox(self):
        """Prediction dataclass accepts None bbox."""
        pred = Prediction(part_num="3001", color_id=1, confidence=0.5, bbox=None)
        assert pred.bbox is None


# ---------------------------------------------------------------------------
# Scanning Router Tests
# ---------------------------------------------------------------------------


FAKE_UPLOAD_URL = "https://s3.example.com/upload?presigned=abc"
FAKE_DOWNLOAD_URL = "https://s3.example.com/download?presigned=xyz"


@pytest.mark.asyncio
async def test_create_scan_returns_upload_url(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """POST /scans returns 201 with a presigned upload URL and scan ID."""
    user = await make_user()
    headers = auth_headers(user.id)

    # Create a collection first
    resp = await client.post("/collections", json={"name": "My Bricks"}, headers=headers)
    assert resp.status_code == 201
    collection_id = resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        resp = await client.post(
            "/scans",
            json={"collection_id": collection_id, "photo_consent": True},
            headers=headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["upload_url"] == FAKE_UPLOAD_URL
    assert "s3_key" in data
    assert data["s3_key"].startswith("scans/")
    assert data["s3_key"].endswith(".jpg")


@pytest.mark.asyncio
async def test_create_scan_collection_not_found(
    client: AsyncClient, make_user, auth_headers
):
    """POST /scans returns 404 when the collection does not belong to the user."""
    user = await make_user()
    headers = auth_headers(user.id)

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        resp = await client.post(
            "/scans",
            json={"collection_id": str(uuid.uuid4())},
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_scan_requires_auth(client: AsyncClient):
    """POST /scans returns 401/403 without auth."""
    resp = await client.post(
        "/scans",
        json={"collection_id": str(uuid.uuid4())},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_process_scan_calls_ml_and_stores_results(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """POST /scans/{id}/process calls ML, stores results, returns COMPLETED scan."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog(db_session)

    # Create collection and scan
    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    fake_predictions = [
        Prediction(part_num="3001", color_id=1, confidence=0.95, bbox=None),
    ]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=fake_predictions)),
    ):
        resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["part_num"] == "3001"
    assert result["color_id"] == 1
    assert result["confidence"] == 0.95
    assert result["user_verified"] is False
    # confidence 0.95 >= 0.7 threshold → needs_review = False
    assert result["needs_review"] is False


@pytest.mark.asyncio
async def test_process_scan_sets_needs_review_for_low_confidence(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """Results with confidence below threshold have needs_review=True."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog(db_session)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    # Low confidence prediction
    fake_predictions = [
        Prediction(part_num="3001", color_id=1, confidence=0.4, bbox=None),
    ]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=fake_predictions)),
    ):
        resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["needs_review"] is True


@pytest.mark.asyncio
async def test_process_scan_sets_failed_on_ml_error(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """POST /scans/{id}/process returns 502 and sets status to FAILED on ML error."""
    user = await make_user()
    headers = auth_headers(user.id)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch(
            "app.scanning.router.ml_client.predict",
            AsyncMock(side_effect=Exception("ML service down")),
        ),
    ):
        resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    assert resp.status_code == 502

    # Verify the scan status is FAILED
    with patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL):
        get_resp = await client.get(f"/scans/{scan_id}", headers=headers)
    assert get_resp.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_get_scan_returns_results_with_needs_review(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """GET /scans/{id} returns scan with results including needs_review flag."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog_multi(db_session)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    fake_predictions = [
        Prediction(part_num="3001", color_id=1, confidence=0.9, bbox=None),
        Prediction(part_num="3002", color_id=2, confidence=0.3, bbox={"x": 1, "y": 2, "w": 3, "h": 4}),
    ]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=fake_predictions)),
    ):
        await client.post(f"/scans/{scan_id}/process", headers=headers)

    resp = await client.get(f"/scans/{scan_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == scan_id
    assert data["status"] == "completed"
    assert len(data["results"]) == 2

    high_conf = next(r for r in data["results"] if r["part_num"] == "3001")
    low_conf = next(r for r in data["results"] if r["part_num"] == "3002")

    assert high_conf["needs_review"] is False
    assert low_conf["needs_review"] is True
    assert low_conf["bbox"] == {"x": 1, "y": 2, "w": 3, "h": 4}


@pytest.mark.asyncio
async def test_get_scan_not_found(client: AsyncClient, make_user, auth_headers):
    """GET /scans/{id} returns 404 for unknown scan."""
    user = await make_user()
    resp = await client.get(f"/scans/{uuid.uuid4()}", headers=auth_headers(user.id))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_scan_cross_user_denied(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """GET /scans/{id} returns 404 when accessed by a different user."""
    user1 = await make_user(apple_sub="u1", email="u1@x.com")
    user2 = await make_user(apple_sub="u2", email="u2@x.com")

    col_resp = await client.post(
        "/collections", json={"name": "Col"}, headers=auth_headers(user1.id)
    )
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=auth_headers(user1.id),
        )
    scan_id = scan_resp.json()["id"]

    # User2 tries to access user1's scan
    resp = await client.get(f"/scans/{scan_id}", headers=auth_headers(user2.id))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_scan_adds_pieces_to_collection(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """POST /scans/{id}/confirm adds accepted pieces to the collection."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog(db_session)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    fake_predictions = [
        Prediction(part_num="3001", color_id=1, confidence=0.95, bbox=None),
    ]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=fake_predictions)),
    ):
        process_resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    assert process_resp.status_code == 200
    result_id = process_resp.json()["results"][0]["id"]

    confirm_resp = await client.post(
        f"/scans/{scan_id}/confirm",
        json={"items": [{"scan_result_id": result_id, "accepted": True}]},
        headers=headers,
    )
    assert confirm_resp.status_code == 200

    # Verify piece was added to the collection
    pieces_resp = await client.get(f"/collections/{collection_id}/pieces", headers=headers)
    assert pieces_resp.status_code == 200
    pieces = pieces_resp.json()["items"]
    assert len(pieces) == 1
    assert pieces[0]["part_num"] == "3001"
    assert pieces[0]["color_id"] == 1
    assert pieces[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_confirm_scan_increments_existing_piece(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """Confirming a scan result increments quantity if the piece already exists in the collection."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog(db_session)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    # Pre-add a piece to the collection
    await client.post(
        f"/collections/{collection_id}/pieces",
        json={"part_num": "3001", "color_id": 1, "quantity": 5},
        headers=headers,
    )

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    fake_predictions = [
        Prediction(part_num="3001", color_id=1, confidence=0.95, bbox=None),
    ]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=fake_predictions)),
    ):
        process_resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    result_id = process_resp.json()["results"][0]["id"]

    await client.post(
        f"/scans/{scan_id}/confirm",
        json={"items": [{"scan_result_id": result_id, "accepted": True}]},
        headers=headers,
    )

    pieces_resp = await client.get(f"/collections/{collection_id}/pieces", headers=headers)
    pieces = pieces_resp.json()["items"]
    assert pieces[0]["quantity"] == 6  # 5 + 1


@pytest.mark.asyncio
async def test_confirm_scan_with_correction(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """Confirm with correction uses the corrected part/color when adding to collection."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog_multi(db_session)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    # ML predicts part 3001 / color 1, but user corrects to 3002 / color 2
    fake_predictions = [
        Prediction(part_num="3001", color_id=1, confidence=0.4, bbox=None),
    ]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=fake_predictions)),
    ):
        process_resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    result_id = process_resp.json()["results"][0]["id"]

    confirm_resp = await client.post(
        f"/scans/{scan_id}/confirm",
        json={
            "items": [
                {
                    "scan_result_id": result_id,
                    "corrected_part_num": "3002",
                    "corrected_color_id": 2,
                    "accepted": True,
                }
            ]
        },
        headers=headers,
    )
    assert confirm_resp.status_code == 200

    pieces_resp = await client.get(f"/collections/{collection_id}/pieces", headers=headers)
    pieces = pieces_resp.json()["items"]
    assert len(pieces) == 1
    assert pieces[0]["part_num"] == "3002"
    assert pieces[0]["color_id"] == 2


@pytest.mark.asyncio
async def test_confirm_scan_rejected_item_not_added(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """Rejected items (accepted=False) are not added to the collection."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog(db_session)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    fake_predictions = [
        Prediction(part_num="3001", color_id=1, confidence=0.95, bbox=None),
    ]

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=fake_predictions)),
    ):
        process_resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    result_id = process_resp.json()["results"][0]["id"]

    await client.post(
        f"/scans/{scan_id}/confirm",
        json={"items": [{"scan_result_id": result_id, "accepted": False}]},
        headers=headers,
    )

    pieces_resp = await client.get(f"/collections/{collection_id}/pieces", headers=headers)
    assert pieces_resp.json()["items"] == []


@pytest.mark.asyncio
async def test_confirm_scan_requires_completed_status(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """POST /scans/{id}/confirm returns 409 when scan is not COMPLETED."""
    user = await make_user()
    headers = auth_headers(user.id)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    # Try to confirm without processing (status = PENDING)
    resp = await client.post(
        f"/scans/{scan_id}/confirm",
        json={"items": []},
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_process_scan_conflict_if_already_processing(
    client: AsyncClient, make_user, auth_headers, db_session: AsyncSession
):
    """POST /scans/{id}/process returns 409 if already in PROCESSING status."""
    user = await make_user()
    headers = auth_headers(user.id)
    await _seed_catalog(db_session)

    col_resp = await client.post("/collections", json={"name": "Col"}, headers=headers)
    collection_id = col_resp.json()["id"]

    with patch("app.scanning.router.generate_presigned_url", return_value=FAKE_UPLOAD_URL):
        scan_resp = await client.post(
            "/scans",
            json={"collection_id": collection_id},
            headers=headers,
        )
    scan_id = scan_resp.json()["id"]

    # Manually set the scan to PROCESSING in DB
    result = await db_session.execute(
        __import__("sqlalchemy").select(Scan).where(Scan.id == uuid.UUID(scan_id))
    )
    scan_obj = result.scalar_one()
    scan_obj.status = ScanStatus.PROCESSING
    await db_session.commit()

    with (
        patch("app.scanning.router.generate_download_url", return_value=FAKE_DOWNLOAD_URL),
        patch("app.scanning.router.ml_client.predict", AsyncMock(return_value=[])),
    ):
        resp = await client.post(f"/scans/{scan_id}/process", headers=headers)

    assert resp.status_code == 409
