# LooseBricks Backend — Design Spec

## Overview

Backend API for LooseBricks, a native iOS app that lets users photograph piles of Lego pieces, inventory them via ML recognition, and discover what official sets or community MOCs they can build.

This spec covers the backend only — the FastAPI monolith, ML service integration, Rebrickable catalog sync, and build matching engine. The iOS app will be designed separately, building against the API defined here.

## Decisions

- **Backend-first** build order — stable API contracts before iOS development
- **Python/FastAPI** — strong ML ecosystem, Pydantic validation, auto-generated API docs
- **Monolith API + separate ML service** — one FastAPI app for all API logic, ML service separate for independent scaling
- **Pre-cached Rebrickable catalog** — full catalog synced into PostgreSQL weekly for fast local matching
- **AWS hosting** — EC2/ECS for API, S3 for photo storage, RDS for PostgreSQL
- **Presigned S3 URLs** — iOS uploads photos directly to S3, keeping large payloads off the API server
- **Sign in with Apple only** for MVP — meets App Store requirements, avoids password management complexity

## Architecture

```
iOS App
  ↓
FastAPI Monolith
  Auth · Collections CRUD · Build Matching
  Rebrickable Sync · S3 Presigned URLs
  ↓           ↓           ↓
PostgreSQL   ML Service   S3
```

The FastAPI app handles all API logic. The ML service is the only separately deployed component — it has different scaling needs (GPU, model updates) and a clean interface boundary.

## Data Model

### User-Owned Tables

**users**
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| apple_sub | varchar | Unique, Apple's stable user identifier |
| display_name | varchar | |
| email | varchar | Nullable, provided by Apple on first sign-in |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**collections**
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| user_id | uuid | FK → users.id |
| name | varchar | e.g. "Kids' box", "Technic bin" |
| description | text | Nullable |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**collection_pieces**
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| collection_id | uuid | FK → collections.id |
| part_num | varchar | FK → parts.part_num |
| color_id | int | FK → colors.id |
| quantity | int | |
| | | UNIQUE (collection_id, part_num, color_id) |

**scans**
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| collection_id | uuid | FK → collections.id |
| user_id | uuid | FK → users.id |
| s3_key | varchar | |
| status | enum | pending, processing, completed, failed |
| photo_consent | bool | Default false, controls retention for ML retraining |
| created_at | timestamptz | |

**scan_results**
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK → scans.id |
| part_num | varchar | FK → parts.part_num |
| color_id | int | FK → colors.id |
| confidence | float | ML confidence score |
| bbox | jsonb | Nullable, bounding box for review UI |
| user_verified | bool | Default false |
| user_correction_part | varchar | Nullable, if user corrected the part |
| user_correction_color | int | Nullable, if user corrected the color |

### Rebrickable Catalog Tables (synced, read-only)

**parts** — part_num (PK, varchar), name, category_id

**colors** — id (PK, int), name, rgb, is_trans

**sets** — set_num (PK, varchar), name, year, num_parts, theme_id

**set_parts** — id (PK, serial), set_num (FK), part_num (FK), color_id (FK), quantity. Mapped from Rebrickable's `inventory_parts.csv` joined with `inventories.csv`.

**mocs** — set_num (PK, varchar), name, designer_name, num_parts

**moc_parts** — id (PK, serial), set_num (FK), part_num (FK), color_id (FK), quantity. Fetched via Rebrickable API.

### Key Design Choices

- **part_num is varchar** — Rebrickable part IDs include letters (e.g. "3001", "3001a", "60478")
- **scan_results are separate from inventory** — ML predictions are staged for user review before becoming collection_pieces
- **bbox stored as JSONB** — flexible format for highlighting pieces in the review UI
- **photo_consent per scan** — controls whether the photo is retained for ML retraining

## API Endpoints

All endpoints require JWT auth unless noted.

### Auth

- `POST /auth/apple` — exchange Apple identity token for JWT session
- `POST /auth/refresh` — refresh an expiring JWT
- `DELETE /auth/account` — delete account and all user data (GDPR)

### Collections

- `GET /collections` — list user's collections
- `POST /collections` — create a collection
- `GET /collections/{id}` — collection details + piece summary
- `PATCH /collections/{id}` — rename or update description
- `DELETE /collections/{id}` — delete collection and its pieces
- `POST /collections/{id}/merge` — merge another collection into this one

### Collection Pieces

- `GET /collections/{id}/pieces` — list pieces (paginated, filterable by category/color)
- `POST /collections/{id}/pieces` — add piece(s) manually
- `PATCH /collections/{id}/pieces/{piece_id}` — update quantity
- `DELETE /collections/{id}/pieces/{piece_id}` — remove piece

### Scanning

- `POST /scans` — create scan, returns presigned S3 upload URL
- `POST /scans/{id}/process` — trigger ML processing after upload completes
- `GET /scans/{id}` — get scan status + results
- `POST /scans/{id}/confirm` — accept results (with user corrections), add confirmed pieces to collection

Scan flow: create → upload to S3 → trigger processing → poll status → confirm with corrections.

### Build Suggestions

- `GET /builds/suggest` — match collections against sets/MOCs
  - `?collection_ids=uuid,uuid` — which collections to match
  - `?min_completeness=70` — threshold (default 70%)
  - `?category=Technic` — filter by theme
  - `?min_parts=50&max_parts=500` — piece count range
  - `?type=set|moc|all` — official sets, MOCs, or both
- `GET /builds/{set_num}/details` — what you have, what you're missing, instructions link

### Catalog (read-only lookups)

- `GET /catalog/parts` — search parts by name or number
- `GET /catalog/colors` — list all Lego colors
- `GET /catalog/parts/{part_num}` — part details + available colors

## ML Service Integration

### MVP: Brickognize API Adapter

For MVP, the "ML service" is a thin adapter layer in the backend (`scanning/ml_client.py`) that:

1. Downloads the image from S3
2. Sends it to the Brickognize API (`POST /predict/`)
3. Maps Brickognize's response format to our internal prediction schema
4. Maps Brickognize part/color IDs to Rebrickable IDs

### ML Service Interface

The ML service has a defined prediction interface. For MVP, this is implemented as an in-process adapter class (`MLClient` in `ml_client.py`) that calls Brickognize. When a custom model is deployed as a standalone service, the adapter is swapped for an HTTP client implementing the same interface — the rest of the backend doesn't change.

```
Prediction interface:
Input:  { "image_url": "https://s3.../{key}", "request_id": "scan-uuid" }
Output: {
  "request_id": "scan-uuid",
  "predictions": [
    { "part_num": "3001", "color_id": 1, "confidence": 0.94, "bbox": {"x": 120, "y": 80, "w": 45, "h": 30} }
  ]
}
```

### Confidence Threshold

Pieces below 0.7 confidence are flagged as "needs review" in scan_results. The iOS app highlights these for the user to confirm or correct.

## Rebrickable Catalog Sync

- **Source**: Rebrickable CSV downloads (parts.csv, colors.csv, sets.csv, inventory_parts.csv, themes.csv)
- **MOCs**: Fetched via Rebrickable API (no CSV dump available), paginated fetch synced alongside
- **Strategy**: Full replace — download CSVs, load into temp tables, swap atomically
- **Schedule**: Weekly cron job. Rebrickable updates approximately weekly. Manual trigger available via CLI command.
- **Scale**: ~70K parts, ~200 colors, ~20K sets, ~1M set_parts rows. Fits comfortably in PostgreSQL.

## Build Matching Engine

Single SQL query computes completeness % for all sets against a user's collections:

```sql
SELECT s.set_num, s.name,
  SUM(LEAST(COALESCE(cp.quantity, 0), sp.quantity)) AS matched,
  SUM(sp.quantity) AS total,
  ROUND(100.0 * SUM(LEAST(COALESCE(cp.quantity, 0), sp.quantity)) / SUM(sp.quantity), 1) AS pct
FROM set_parts sp
JOIN sets s ON s.set_num = sp.set_num
LEFT JOIN collection_pieces cp
  ON sp.part_num = cp.part_num AND sp.color_id = cp.color_id
  AND cp.collection_id IN (:collection_ids)
GROUP BY s.set_num, s.name
HAVING ROUND(100.0 * SUM(LEAST(COALESCE(cp.quantity, 0), sp.quantity)) / SUM(sp.quantity), 1) >= :min_completeness
ORDER BY pct DESC
```

Indexed on `set_parts(part_num, color_id)` and `collection_pieces(collection_id, part_num, color_id)` for performance.

## Auth Flow

### Sign in with Apple

1. iOS app uses AuthenticationServices framework to get Apple identity token
2. App sends token to `POST /auth/apple`
3. Backend fetches Apple's public keys (JWKS endpoint, cached)
4. Verifies token signature, expiry, and audience
5. Extracts `sub` (stable Apple user ID) and email
6. Finds existing user by `apple_sub` or creates new user
7. Issues JWT access + refresh tokens
8. iOS app stores tokens in Keychain

### Token Lifecycle

- **Access token**: 15 minute expiry, sent in Authorization header
- **Refresh token**: 30 day expiry, used to obtain new access tokens
- **Refresh rotation**: Each refresh issues a new refresh token, old one is invalidated

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, middleware, lifespan
│   ├── config.py            # Settings via pydantic-settings (env vars)
│   ├── database.py          # SQLAlchemy async engine + session
│   │
│   ├── auth/
│   │   ├── router.py        # /auth/* endpoints
│   │   ├── apple.py         # Apple JWKS verification
│   │   ├── jwt.py           # Token creation + validation
│   │   └── dependencies.py  # get_current_user dependency
│   │
│   ├── collections/
│   │   ├── router.py        # /collections/* endpoints
│   │   ├── models.py        # SQLAlchemy models
│   │   └── schemas.py       # Pydantic request/response schemas
│   │
│   ├── scanning/
│   │   ├── router.py        # /scans/* endpoints
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── ml_client.py     # Brickognize adapter (MVP ML service)
│   │
│   ├── builds/
│   │   ├── router.py        # /builds/* endpoints
│   │   ├── matching.py      # Completeness query logic
│   │   └── schemas.py
│   │
│   ├── catalog/
│   │   ├── router.py        # /catalog/* endpoints
│   │   ├── models.py        # Parts, colors, sets, set_parts
│   │   └── sync.py          # Rebrickable CSV import job
│   │
│   └── models/
│       └── user.py          # User SQLAlchemy model
│
├── migrations/              # Alembic migrations
│   ├── alembic.ini
│   └── versions/
│
├── tests/
│   ├── conftest.py          # Fixtures, test DB setup
│   ├── test_auth.py
│   ├── test_collections.py
│   ├── test_scanning.py
│   ├── test_builds.py
│   └── test_catalog.py
│
├── pyproject.toml           # Dependencies (uv/pip)
├── Dockerfile
└── docker-compose.yml       # Local dev: API + PostgreSQL + LocalStack (S3)
```

## Key Dependencies

- **fastapi** — web framework
- **uvicorn** — ASGI server
- **sqlalchemy[asyncio]** + **asyncpg** — async ORM + PostgreSQL driver
- **alembic** — database migrations
- **pydantic-settings** — config from environment variables
- **python-jose[cryptography]** — JWT creation + Apple JWKS verification
- **boto3** — S3 presigned URLs
- **httpx** — async HTTP client for Brickognize + Rebrickable APIs
- **pytest** + **pytest-asyncio** — testing

## Error Handling & Conventions

- **HTTP status codes**: 200/201 success, 400 validation, 401 unauthed, 403 forbidden, 404 not found, 409 conflict, 503 ML service unavailable
- **Error response format**: `{"detail": "human message", "code": "MACHINE_CODE"}`
- **ML service timeout**: 30s per request, scan marked "failed" if exceeded — user can retry
- **Rate limiting**: per-user, 10 scans/min, 60 requests/min general
- **Pagination**: cursor-based, `?cursor=xxx&limit=50`, response includes `next_cursor`
