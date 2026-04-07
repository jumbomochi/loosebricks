import uuid
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

from app.auth.apple import verify_apple_identity_token
from app.auth.jwt import TokenError, create_access_token, create_refresh_token, decode_token
from app.config import settings


class TestJWT:
    def test_create_access_token(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(subject=user_id)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        assert payload["sub"] == user_id
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        user_id = str(uuid.uuid4())
        token = create_refresh_token(subject=user_id)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"

    def test_decode_valid_access_token(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(subject=user_id)
        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == user_id

    def test_decode_wrong_type_raises(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(subject=user_id)
        with pytest.raises(TokenError, match="Expected refresh token"):
            decode_token(token, expected_type="refresh")

    def test_decode_invalid_token_raises(self):
        with pytest.raises(TokenError):
            decode_token("garbage.token.value", expected_type="access")


class TestAppleAuth:
    @pytest.mark.asyncio
    async def test_verify_apple_token_valid(self):
        fake_claims = {
            "sub": "001234.abcdef",
            "email": "user@privaterelay.appleid.com",
            "iss": "https://appleid.apple.com",
            "aud": settings.apple_bundle_id,
        }
        with patch("app.auth.apple._decode_and_verify", return_value=fake_claims):
            result = await verify_apple_identity_token("fake.token.here")
            assert result["sub"] == "001234.abcdef"
            assert result["email"] == "user@privaterelay.appleid.com"

    @pytest.mark.asyncio
    async def test_verify_apple_token_wrong_audience(self):
        fake_claims = {
            "sub": "001234.abcdef",
            "iss": "https://appleid.apple.com",
            "aud": "wrong.bundle.id",
        }
        with patch("app.auth.apple._decode_and_verify", return_value=fake_claims):
            with pytest.raises(ValueError, match="audience"):
                await verify_apple_identity_token("fake.token.here")


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_apple_login_creates_user(self, client, db_session):
        fake_claims = {"sub": "apple-user-123", "email": "test@example.com"}
        with patch("app.auth.router.verify_apple_identity_token", new_callable=AsyncMock, return_value=fake_claims):
            response = await client.post("/auth/apple", json={"identity_token": "fake.token"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["apple_sub"] == "apple-user-123"

    @pytest.mark.asyncio
    async def test_apple_login_returns_existing_user(self, client, db_session, make_user):
        user = await make_user(apple_sub="apple-user-123")
        fake_claims = {"sub": "apple-user-123", "email": "test@example.com"}
        with patch("app.auth.router.verify_apple_identity_token", new_callable=AsyncMock, return_value=fake_claims):
            response = await client.post("/auth/apple", json={"identity_token": "fake.token"})
        assert response.status_code == 200
        assert response.json()["user"]["id"] == str(user.id)

    @pytest.mark.asyncio
    async def test_refresh_token(self, client, make_user):
        user = await make_user()
        refresh = create_refresh_token(subject=str(user.id))
        response = await client.post("/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 200
        assert "access_token" in response.json()

    @pytest.mark.asyncio
    async def test_delete_account(self, client, make_user, auth_headers):
        user = await make_user()
        headers = auth_headers(user.id)
        response = await client.delete("/auth/account", headers=headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self, client):
        response = await client.delete("/auth/account")
        assert response.status_code == 401
