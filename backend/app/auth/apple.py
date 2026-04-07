import httpx
from jose import jwt

from app.config import settings

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

_cached_keys: dict | None = None


async def _fetch_apple_keys() -> dict:
    global _cached_keys
    if _cached_keys is not None:
        return _cached_keys
    async with httpx.AsyncClient() as client:
        resp = await client.get(APPLE_JWKS_URL)
        resp.raise_for_status()
        _cached_keys = resp.json()
        return _cached_keys


def _decode_and_verify(token: str, keys: dict) -> dict:
    return jwt.decode(
        token,
        keys,
        algorithms=["RS256"],
        audience=settings.apple_bundle_id,
        issuer=APPLE_ISSUER,
    )


async def verify_apple_identity_token(identity_token: str) -> dict:
    keys = await _fetch_apple_keys()
    claims = _decode_and_verify(identity_token, keys)

    if claims.get("iss") != APPLE_ISSUER:
        raise ValueError("Invalid issuer")
    if claims.get("aud") != settings.apple_bundle_id:
        raise ValueError("Invalid audience")

    return {"sub": claims["sub"], "email": claims.get("email")}
