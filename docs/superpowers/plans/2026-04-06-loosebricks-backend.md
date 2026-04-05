# LooseBricks Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete FastAPI backend for LooseBricks — auth, collections, scanning, catalog sync, and build matching.

**Architecture:** Single FastAPI monolith with domain-based modules (auth, collections, scanning, builds, catalog). PostgreSQL via async SQLAlchemy. Brickognize API as the MVP ML service via an in-process adapter. Rebrickable CSV catalog synced weekly.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy[asyncio] + asyncpg, Alembic, Pydantic, python-jose, boto3, httpx, pytest, Docker Compose (PostgreSQL + LocalStack)

**Design Spec:** `docs/superpowers/specs/2026-04-05-loosebricks-backend-design.md`

---

## File Map

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, routers, lifespan
│   ├── config.py            # pydantic-settings config
│   ├── database.py          # Async engine + session factory
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── router.py        # POST /auth/apple, /auth/refresh, DELETE /auth/account
│   │   ├── apple.py         # Fetch + cache Apple JWKS, verify identity tokens
│   │   ├── jwt.py           # Create + decode access/refresh JWTs
│   │   └── dependencies.py  # get_current_user FastAPI dependency
│   │
│   ├── collections/
│   │   ├── __init__.py
│   │   ├── router.py        # Collections + pieces CRUD endpoints
│   │   ├── models.py        # Collection, CollectionPiece SQLAlchemy models
│   │   └── schemas.py       # Pydantic request/response schemas
│   │
│   ├── scanning/
│   │   ├── __init__.py
│   │   ├── router.py        # POST /scans, /scans/{id}/process, GET /scans/{id}, POST /scans/{id}/confirm
│   │   ├── models.py        # Scan, ScanResult SQLAlchemy models
│   │   ├── schemas.py       # Pydantic schemas
│   │   └── ml_client.py     # MLClient protocol + BrickognizeAdapter
│   │
│   ├── builds/
│   │   ├── __init__.py
│   │   ├── router.py        # GET /builds/suggest, /builds/{set_num}/details
│   │   ├── matching.py      # Completeness SQL query builder
│   │   └── schemas.py       # Pydantic schemas
│   │
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── router.py        # GET /catalog/parts, /catalog/colors, /catalog/parts/{part_num}
│   │   ├── models.py        # Part, Color, Set, SetPart, Moc, MocPart models
│   │   ├── schemas.py       # Pydantic schemas
│   │   └── sync.py          # Rebrickable CSV download + import
│   │
│   └── models/
│       ├── __init__.py
│       └── user.py          # User SQLAlchemy model
│
├── migrations/
│   ├── env.py               # Alembic env
│   └── versions/            # Migration files
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Async test fixtures, test DB, test client
│   ├── test_auth.py
│   ├── test_collections.py
│   ├── test_pieces.py
│   ├── test_scanning.py
│   ├── test_builds.py
│   ├── test_catalog.py
│   └── test_catalog_sync.py
│
├── alembic.ini
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/docker-compose.yml`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`

- [ ] **Step 1: Create pyproject.toml with all dependencies**

```toml
# backend/pyproject.toml
[project]
name = "loosebricks-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.35",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pydantic-settings>=2.6.0",
    "python-jose[cryptography]>=3.3.0",
    "boto3>=1.35.0",
    "httpx>=0.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx",
    "moto[s3]>=5.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create docker-compose.yml for local dev**

```yaml
# backend/docker-compose.yml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: loosebricks
      POSTGRES_PASSWORD: loosebricks
      POSTGRES_DB: loosebricks
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  localstack:
    image: localstack/localstack:latest
    environment:
      SERVICES: s3
      DEFAULT_REGION: us-east-1
    ports:
      - "4566:4566"

volumes:
  pgdata:
```

- [ ] **Step 3: Create .env.example**

```bash
# backend/.env.example
DATABASE_URL=postgresql+asyncpg://loosebricks:loosebricks@localhost:5432/loosebricks
JWT_SECRET_KEY=change-me-in-production
APPLE_BUNDLE_ID=com.loosebricks.app
AWS_S3_BUCKET=loosebricks-scans
AWS_S3_ENDPOINT_URL=http://localhost:4566
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
BRICKOGNIZE_API_URL=https://api.brickognize.com
REBRICKABLE_API_KEY=your-rebrickable-api-key
CONFIDENCE_THRESHOLD=0.7
```

- [ ] **Step 4: Create config.py**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://loosebricks:loosebricks@localhost:5432/loosebricks"
    jwt_secret_key: str = "change-me-in-production"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    apple_bundle_id: str = "com.loosebricks.app"
    aws_s3_bucket: str = "loosebricks-scans"
    aws_s3_endpoint_url: str | None = None
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    brickognize_api_url: str = "https://api.brickognize.com"
    rebrickable_api_key: str = ""
    confidence_threshold: float = 0.7

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

- [ ] **Step 5: Create empty __init__.py**

```python
# backend/app/__init__.py
```

- [ ] **Step 6: Commit**

```bash
cd backend
git add pyproject.toml docker-compose.yml .env.example app/__init__.py app/config.py
git commit -m "feat: project scaffold with dependencies, docker-compose, and config"
```

---

### Task 2: Database Setup

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`

- [ ] **Step 1: Create database.py with async engine and session factory**

```python
# backend/app/database.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
```

- [ ] **Step 2: Initialize Alembic**

```bash
cd backend
pip install -e ".[dev]"
alembic init migrations
```

- [ ] **Step 3: Replace alembic.ini sqlalchemy.url with empty string (we'll set it from env)**

Edit `backend/alembic.ini` — set:
```ini
sqlalchemy.url =
```

- [ ] **Step 4: Update migrations/env.py to use our engine config and import all models**

```python
# backend/migrations/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base

# Import all models so Alembic sees them
from app.models.user import User  # noqa: F401
from app.catalog.models import Part, Color, Set, SetPart, Moc, MocPart  # noqa: F401
from app.collections.models import Collection, CollectionPiece  # noqa: F401
from app.scanning.models import Scan, ScanResult  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 5: Commit**

```bash
git add app/database.py alembic.ini migrations/
git commit -m "feat: async database setup and Alembic configuration"
```

---

### Task 3: SQLAlchemy Models — All Tables

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/catalog/__init__.py`
- Create: `backend/app/catalog/models.py`
- Create: `backend/app/collections/__init__.py`
- Create: `backend/app/collections/models.py`
- Create: `backend/app/scanning/__init__.py`
- Create: `backend/app/scanning/models.py`

- [ ] **Step 1: Create User model**

```python
# backend/app/models/__init__.py
```

```python
# backend/app/models/user.py
import uuid
from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    apple_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    collections: Mapped[list["Collection"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    scans: Mapped[list["Scan"]] = relationship(back_populates="user", cascade="all, delete-orphan")
```

- [ ] **Step 2: Create catalog models (Part, Color, Set, SetPart, Moc, MocPart)**

```python
# backend/app/catalog/__init__.py
```

```python
# backend/app/catalog/models.py
from sqlalchemy import ForeignKey, Index, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Part(Base):
    __tablename__ = "parts"

    part_num: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    category_id: Mapped[int] = mapped_column(Integer)


class Color(Base):
    __tablename__ = "colors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200))
    rgb: Mapped[str] = mapped_column(String(6))
    is_trans: Mapped[bool] = mapped_column(Boolean, default=False)


class Set(Base):
    __tablename__ = "sets"

    set_num: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    year: Mapped[int] = mapped_column(Integer)
    num_parts: Mapped[int] = mapped_column(Integer)
    theme_id: Mapped[int] = mapped_column(Integer)


class SetPart(Base):
    __tablename__ = "set_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(String(50), ForeignKey("sets.set_num"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    quantity: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_set_parts_part_color", "part_num", "color_id"),
    )


class Moc(Base):
    __tablename__ = "mocs"

    set_num: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    designer_name: Mapped[str] = mapped_column(String(255))
    num_parts: Mapped[int] = mapped_column(Integer)


class MocPart(Base):
    __tablename__ = "moc_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(String(50), ForeignKey("mocs.set_num"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    quantity: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_moc_parts_part_color", "part_num", "color_id"),
    )
```

- [ ] **Step 3: Create collection models (Collection, CollectionPiece)**

```python
# backend/app/collections/__init__.py
```

```python
# backend/app/collections/models.py
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="collections")
    pieces: Mapped[list["CollectionPiece"]] = relationship(back_populates="collection", cascade="all, delete-orphan")


class CollectionPiece(Base):
    __tablename__ = "collection_pieces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    quantity: Mapped[int] = mapped_column(Integer)

    collection: Mapped["Collection"] = relationship(back_populates="pieces")

    __table_args__ = (
        UniqueConstraint("collection_id", "part_num", "color_id", name="uq_collection_part_color"),
        Index("ix_collection_pieces_lookup", "collection_id", "part_num", "color_id"),
    )
```

- [ ] **Step 4: Create scanning models (Scan, ScanResult)**

```python
# backend/app/scanning/__init__.py
```

```python
# backend/app/scanning/models.py
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    s3_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[ScanStatus] = mapped_column(Enum(ScanStatus), default=ScanStatus.PENDING)
    photo_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="scans")
    results: Mapped[list["ScanResult"]] = relationship(back_populates="scan", cascade="all, delete-orphan")


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    confidence: Mapped[float] = mapped_column(Float)
    bbox: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    user_correction_part: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_correction_color: Mapped[int | None] = mapped_column(Integer, nullable=True)

    scan: Mapped["Scan"] = relationship(back_populates="results")
```

- [ ] **Step 5: Generate and run initial Alembic migration**

```bash
docker compose up -d db
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add app/models/ app/catalog/__init__.py app/catalog/models.py app/collections/__init__.py app/collections/models.py app/scanning/__init__.py app/scanning/models.py migrations/versions/
git commit -m "feat: all SQLAlchemy models and initial migration"
```

---

### Task 4: FastAPI App Shell + Test Infrastructure

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Write test for health check endpoint**

```python
# backend/tests/__init__.py
```

```python
# backend/tests/conftest.py
import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

# Use a separate test database
TEST_DATABASE_URL = settings.database_url.replace("/loosebricks", "/loosebricks_test")
test_engine = create_async_engine(TEST_DATABASE_URL)
test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    async with test_session_factory() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session: AsyncSession):
    """Factory fixture to create a test user in the database."""
    from app.models.user import User

    async def _make_user(
        apple_sub: str = "test-apple-sub",
        display_name: str = "Test User",
        email: str = "test@example.com",
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            apple_sub=apple_sub,
            display_name=display_name,
            email=email,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture
def auth_headers():
    """Generate a valid JWT Authorization header for a given user."""
    from app.auth.jwt import create_access_token

    def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
        token = create_access_token(subject=str(user_id))
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers
```

```python
# backend/tests/test_health.py
import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_health.py -v
```
Expected: FAIL (app module not found or no /health route)

- [ ] **Step 3: Create main.py with health check**

```python
# backend/app/main.py
from fastapi import FastAPI

app = FastAPI(title="LooseBricks API", version="0.1.0")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_health.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/
git commit -m "feat: FastAPI app shell with health check and test infrastructure"
```

---

### Task 5: JWT Token Utilities

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/jwt.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write tests for JWT creation and validation**

```python
# backend/tests/test_auth.py
import uuid

import pytest
from jose import jwt

from app.auth.jwt import create_access_token, create_refresh_token, decode_token, TokenError
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth.py::TestJWT -v
```
Expected: FAIL (module not found)

- [ ] **Step 3: Implement JWT utilities**

```python
# backend/app/auth/__init__.py
```

```python
# backend/app/auth/jwt.py
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {"sub": subject, "type": "refresh", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except JWTError as e:
        raise TokenError(f"Invalid token: {e}") from e

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected {expected_type} token, got {payload.get('type')}")

    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_auth.py::TestJWT -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/auth/ tests/test_auth.py
git commit -m "feat: JWT access and refresh token creation and validation"
```

---

### Task 6: Apple Sign-In Verification

**Files:**
- Create: `backend/app/auth/apple.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write test for Apple token verification**

Append to `backend/tests/test_auth.py`:

```python
from unittest.mock import AsyncMock, patch

from app.auth.apple import verify_apple_identity_token


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth.py::TestAppleAuth -v
```
Expected: FAIL

- [ ] **Step 3: Implement Apple token verification**

```python
# backend/app/auth/apple.py
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
    """Verify an Apple identity token and return claims (sub, email)."""
    keys = await _fetch_apple_keys()
    claims = _decode_and_verify(identity_token, keys)

    if claims.get("iss") != APPLE_ISSUER:
        raise ValueError("Invalid issuer")
    if claims.get("aud") != settings.apple_bundle_id:
        raise ValueError("Invalid audience")

    return {"sub": claims["sub"], "email": claims.get("email")}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_auth.py::TestAppleAuth -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/auth/apple.py tests/test_auth.py
git commit -m "feat: Apple Sign In identity token verification"
```

---

### Task 7: Auth Dependencies + Router

**Files:**
- Create: `backend/app/auth/dependencies.py`
- Create: `backend/app/auth/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write tests for auth endpoints**

Append to `backend/tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth.py::TestAuthEndpoints -v
```
Expected: FAIL

- [ ] **Step 3: Implement auth dependency (get_current_user)**

```python
# backend/app/auth/dependencies.py
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import TokenError, decode_token
from app.database import get_db
from app.models.user import User

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

- [ ] **Step 4: Implement auth router**

```python
# backend/app/auth/router.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.apple import verify_apple_identity_token
from app.auth.dependencies import get_current_user
from app.auth.jwt import TokenError, create_access_token, create_refresh_token, decode_token
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class AppleLoginRequest(BaseModel):
    identity_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    apple_sub: str
    display_name: str
    email: str | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(id=str(user.id), apple_sub=user.apple_sub, display_name=user.display_name, email=user.email)


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse


@router.post("/apple", response_model=AuthResponse)
async def apple_login(body: AppleLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        claims = await verify_apple_identity_token(body.identity_token)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    apple_sub = claims["sub"]
    email = claims.get("email")

    result = await db.execute(select(User).where(User.apple_sub == apple_sub))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            apple_sub=apple_sub,
            display_name=email.split("@")[0] if email else "User",
            email=email,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.from_user(user),
    )


@router.post("/refresh")
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except TokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return {
        "access_token": create_access_token(subject=str(user.id)),
        "refresh_token": create_refresh_token(subject=str(user.id)),
    }


@router.delete("/account")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    return {"detail": "Account deleted"}
```

- [ ] **Step 5: Register auth router in main.py**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.auth.router import router as auth_router

app = FastAPI(title="LooseBricks API", version="0.1.0")
app.include_router(auth_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_auth.py -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add app/auth/ app/main.py tests/test_auth.py
git commit -m "feat: auth router with Apple sign-in, token refresh, and account deletion"
```

---

### Task 8: Collections CRUD

**Files:**
- Create: `backend/app/collections/schemas.py`
- Create: `backend/app/collections/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_collections.py`

- [ ] **Step 1: Write tests for collections CRUD**

```python
# backend/tests/test_collections.py
import uuid

import pytest


@pytest.fixture
async def user_and_headers(make_user, auth_headers):
    user = await make_user()
    headers = auth_headers(user.id)
    return user, headers


class TestCollections:
    @pytest.mark.asyncio
    async def test_create_collection(self, client, user_and_headers):
        user, headers = await user_and_headers
        response = await client.post(
            "/collections",
            json={"name": "Kids' box", "description": "Mixed pieces"},
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Kids' box"
        assert data["description"] == "Mixed pieces"

    @pytest.mark.asyncio
    async def test_list_collections(self, client, user_and_headers):
        user, headers = await user_and_headers
        await client.post("/collections", json={"name": "Box 1"}, headers=headers)
        await client.post("/collections", json={"name": "Box 2"}, headers=headers)
        response = await client.get("/collections", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_get_collection(self, client, user_and_headers):
        user, headers = await user_and_headers
        create_resp = await client.post("/collections", json={"name": "Box"}, headers=headers)
        collection_id = create_resp.json()["id"]
        response = await client.get(f"/collections/{collection_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Box"

    @pytest.mark.asyncio
    async def test_update_collection(self, client, user_and_headers):
        user, headers = await user_and_headers
        create_resp = await client.post("/collections", json={"name": "Old"}, headers=headers)
        collection_id = create_resp.json()["id"]
        response = await client.patch(
            f"/collections/{collection_id}",
            json={"name": "New"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New"

    @pytest.mark.asyncio
    async def test_delete_collection(self, client, user_and_headers):
        user, headers = await user_and_headers
        create_resp = await client.post("/collections", json={"name": "Delete me"}, headers=headers)
        collection_id = create_resp.json()["id"]
        response = await client.delete(f"/collections/{collection_id}", headers=headers)
        assert response.status_code == 200
        # Verify it's gone
        get_resp = await client.get(f"/collections/{collection_id}", headers=headers)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_merge_collections(self, client, user_and_headers, db_session):
        user, headers = await user_and_headers

        # Create two collections with pieces
        r1 = await client.post("/collections", json={"name": "Source"}, headers=headers)
        r2 = await client.post("/collections", json={"name": "Target"}, headers=headers)
        source_id = r1.json()["id"]
        target_id = r2.json()["id"]

        # Add pieces to source (requires catalog parts to exist — seed them)
        from app.catalog.models import Part, Color
        db_session.add(Part(part_num="3001", name="Brick 2x4", category_id=1))
        db_session.add(Color(id=1, name="Red", rgb="FF0000", is_trans=False))
        await db_session.commit()

        await client.post(
            f"/collections/{source_id}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 5},
            headers=headers,
        )
        await client.post(
            f"/collections/{target_id}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 3},
            headers=headers,
        )

        response = await client.post(
            f"/collections/{target_id}/merge",
            json={"source_collection_id": source_id},
            headers=headers,
        )
        assert response.status_code == 200

        # Target should now have 8 of part 3001 in red
        pieces_resp = await client.get(f"/collections/{target_id}/pieces", headers=headers)
        pieces = pieces_resp.json()["items"]
        assert len(pieces) == 1
        assert pieces[0]["quantity"] == 8

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_collection(self, client, make_user, auth_headers):
        user1 = await make_user(apple_sub="user1")
        user2 = await make_user(apple_sub="user2")
        headers1 = auth_headers(user1.id)
        headers2 = auth_headers(user2.id)

        create_resp = await client.post("/collections", json={"name": "Private"}, headers=headers1)
        collection_id = create_resp.json()["id"]

        response = await client.get(f"/collections/{collection_id}", headers=headers2)
        assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_collections.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement collection schemas**

```python
# backend/app/collections/schemas.py
import uuid
from datetime import datetime

from pydantic import BaseModel


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    piece_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MergeRequest(BaseModel):
    source_collection_id: uuid.UUID
```

- [ ] **Step 4: Implement collections router**

```python
# backend/app/collections/router.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.collections.models import Collection, CollectionPiece
from app.collections.schemas import CollectionCreate, CollectionResponse, CollectionUpdate, MergeRequest
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/collections", tags=["collections"])


async def _get_user_collection(
    collection_id: uuid.UUID, user: User, db: AsyncSession
) -> Collection:
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


def _to_response(collection: Collection, piece_count: int = 0) -> CollectionResponse:
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        piece_count=piece_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CollectionResponse)
async def create_collection(
    body: CollectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection = Collection(user_id=user.id, name=body.name, description=body.description)
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return _to_response(collection)


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Collection, func.coalesce(func.sum(CollectionPiece.quantity), 0).label("piece_count"))
        .outerjoin(CollectionPiece)
        .where(Collection.user_id == user.id)
        .group_by(Collection.id)
        .order_by(Collection.created_at.desc())
    )
    result = await db.execute(stmt)
    return [_to_response(row.Collection, int(row.piece_count)) for row in result.all()]


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection = await _get_user_collection(collection_id, user, db)
    count_result = await db.execute(
        select(func.coalesce(func.sum(CollectionPiece.quantity), 0))
        .where(CollectionPiece.collection_id == collection_id)
    )
    piece_count = int(count_result.scalar())
    return _to_response(collection, piece_count)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection = await _get_user_collection(collection_id, user, db)
    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(collection, key, value)
        await db.commit()
        await db.refresh(collection)
    return _to_response(collection)


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection = await _get_user_collection(collection_id, user, db)
    await db.delete(collection)
    await db.commit()
    return {"detail": "Collection deleted"}


@router.post("/{collection_id}/merge")
async def merge_collection(
    collection_id: uuid.UUID,
    body: MergeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await _get_user_collection(collection_id, user, db)
    source = await _get_user_collection(body.source_collection_id, user, db)

    # Get all pieces from source
    source_pieces_result = await db.execute(
        select(CollectionPiece).where(CollectionPiece.collection_id == source.id)
    )
    source_pieces = source_pieces_result.scalars().all()

    for sp in source_pieces:
        # Check if target already has this part+color
        existing_result = await db.execute(
            select(CollectionPiece).where(
                CollectionPiece.collection_id == target.id,
                CollectionPiece.part_num == sp.part_num,
                CollectionPiece.color_id == sp.color_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.quantity += sp.quantity
        else:
            db.add(CollectionPiece(
                collection_id=target.id,
                part_num=sp.part_num,
                color_id=sp.color_id,
                quantity=sp.quantity,
            ))

    # Delete source collection
    await db.delete(source)
    await db.commit()
    return {"detail": "Collections merged"}
```

- [ ] **Step 5: Register collections router in main.py**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.collections.router import router as collections_router

app = FastAPI(title="LooseBricks API", version="0.1.0")
app.include_router(auth_router)
app.include_router(collections_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_collections.py -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add app/collections/ app/main.py tests/test_collections.py
git commit -m "feat: collections CRUD with merge endpoint"
```

---

### Task 9: Collection Pieces CRUD

**Files:**
- Modify: `backend/app/collections/schemas.py`
- Modify: `backend/app/collections/router.py`
- Create: `backend/tests/test_pieces.py`

- [ ] **Step 1: Write tests for pieces CRUD with pagination**

```python
# backend/tests/test_pieces.py
import pytest

from app.catalog.models import Color, Part


@pytest.fixture
async def seed_catalog(db_session):
    """Seed minimal catalog data for piece tests."""
    db_session.add_all([
        Part(part_num="3001", name="Brick 2x4", category_id=1),
        Part(part_num="3003", name="Brick 2x2", category_id=1),
        Color(id=1, name="Red", rgb="FF0000", is_trans=False),
        Color(id=4, name="Blue", rgb="0000FF", is_trans=False),
    ])
    await db_session.commit()


@pytest.fixture
async def collection_with_auth(client, make_user, auth_headers, seed_catalog):
    user = await make_user()
    headers = auth_headers(user.id)
    resp = await client.post("/collections", json={"name": "Test"}, headers=headers)
    return resp.json()["id"], headers


class TestPieces:
    @pytest.mark.asyncio
    async def test_add_piece(self, client, collection_with_auth):
        cid, headers = await collection_with_auth
        response = await client.post(
            f"/collections/{cid}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 5},
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["quantity"] == 5

    @pytest.mark.asyncio
    async def test_add_duplicate_piece_increments(self, client, collection_with_auth):
        cid, headers = await collection_with_auth
        await client.post(
            f"/collections/{cid}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 5},
            headers=headers,
        )
        response = await client.post(
            f"/collections/{cid}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 3},
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["quantity"] == 8

    @pytest.mark.asyncio
    async def test_list_pieces_paginated(self, client, collection_with_auth):
        cid, headers = await collection_with_auth
        await client.post(f"/collections/{cid}/pieces", json={"part_num": "3001", "color_id": 1, "quantity": 5}, headers=headers)
        await client.post(f"/collections/{cid}/pieces", json={"part_num": "3003", "color_id": 1, "quantity": 2}, headers=headers)
        await client.post(f"/collections/{cid}/pieces", json={"part_num": "3001", "color_id": 4, "quantity": 1}, headers=headers)

        response = await client.get(f"/collections/{cid}/pieces?limit=2", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["next_cursor"] is not None

        # Fetch next page
        response2 = await client.get(
            f"/collections/{cid}/pieces?limit=2&cursor={data['next_cursor']}", headers=headers
        )
        assert len(response2.json()["items"]) == 1
        assert response2.json()["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_update_piece_quantity(self, client, collection_with_auth):
        cid, headers = await collection_with_auth
        create_resp = await client.post(
            f"/collections/{cid}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 5},
            headers=headers,
        )
        piece_id = create_resp.json()["id"]
        response = await client.patch(
            f"/collections/{cid}/pieces/{piece_id}",
            json={"quantity": 10},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 10

    @pytest.mark.asyncio
    async def test_delete_piece(self, client, collection_with_auth):
        cid, headers = await collection_with_auth
        create_resp = await client.post(
            f"/collections/{cid}/pieces",
            json={"part_num": "3001", "color_id": 1, "quantity": 5},
            headers=headers,
        )
        piece_id = create_resp.json()["id"]
        response = await client.delete(f"/collections/{cid}/pieces/{piece_id}", headers=headers)
        assert response.status_code == 200

        # Verify it's gone
        list_resp = await client.get(f"/collections/{cid}/pieces", headers=headers)
        assert len(list_resp.json()["items"]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pieces.py -v
```
Expected: FAIL

- [ ] **Step 3: Add piece schemas to collections/schemas.py**

Append to `backend/app/collections/schemas.py`:

```python
class PieceCreate(BaseModel):
    part_num: str
    color_id: int
    quantity: int


class PieceUpdate(BaseModel):
    quantity: int


class PieceResponse(BaseModel):
    id: uuid.UUID
    part_num: str
    color_id: int
    quantity: int

    model_config = {"from_attributes": True}


class PieceListResponse(BaseModel):
    items: list[PieceResponse]
    next_cursor: str | None
```

- [ ] **Step 4: Add piece endpoints to collections/router.py**

Append to `backend/app/collections/router.py`:

```python
from app.collections.schemas import PieceCreate, PieceListResponse, PieceResponse, PieceUpdate
import base64


@router.post("/{collection_id}/pieces", status_code=status.HTTP_201_CREATED, response_model=PieceResponse)
async def add_piece(
    collection_id: uuid.UUID,
    body: PieceCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_collection(collection_id, user, db)

    # Check if piece already exists — if so, increment quantity
    result = await db.execute(
        select(CollectionPiece).where(
            CollectionPiece.collection_id == collection_id,
            CollectionPiece.part_num == body.part_num,
            CollectionPiece.color_id == body.color_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity += body.quantity
        await db.commit()
        await db.refresh(existing)
        return PieceResponse.model_validate(existing)

    piece = CollectionPiece(
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
    cursor: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_collection(collection_id, user, db)

    stmt = (
        select(CollectionPiece)
        .where(CollectionPiece.collection_id == collection_id)
        .order_by(CollectionPiece.id)
        .limit(limit + 1)
    )

    if cursor:
        cursor_id = uuid.UUID(base64.b64decode(cursor).decode())
        stmt = stmt.where(CollectionPiece.id > cursor_id)

    result = await db.execute(stmt)
    pieces = list(result.scalars().all())

    has_more = len(pieces) > limit
    if has_more:
        pieces = pieces[:limit]

    next_cursor = None
    if has_more:
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
):
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


@router.delete("/{collection_id}/pieces/{piece_id}")
async def delete_piece(
    collection_id: uuid.UUID,
    piece_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    return {"detail": "Piece deleted"}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_pieces.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/collections/ tests/test_pieces.py
git commit -m "feat: collection pieces CRUD with cursor pagination"
```

---

### Task 10: ML Client (Brickognize Adapter)

**Files:**
- Create: `backend/app/scanning/ml_client.py`
- Create: `backend/app/scanning/schemas.py`
- Create: `backend/tests/test_scanning.py`

- [ ] **Step 1: Write tests for the ML client**

```python
# backend/tests/test_scanning.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.scanning.ml_client import BrickognizeAdapter, Prediction


class TestBrickognizeAdapter:
    @pytest.mark.asyncio
    async def test_predict_maps_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "id": "3001",
                    "name": "Brick 2x4",
                    "color": {"id": 1, "name": "Red"},
                    "score": 0.94,
                    "bounding_box": {"x": 120, "y": 80, "width": 45, "height": 30},
                },
                {
                    "id": "3003",
                    "name": "Brick 2x2",
                    "color": {"id": 4, "name": "Blue"},
                    "score": 0.55,
                    "bounding_box": {"x": 200, "y": 150, "width": 30, "height": 25},
                },
            ]
        }

        adapter = BrickognizeAdapter()
        with patch.object(adapter, "_http_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            predictions = await adapter.predict(
                image_url="https://s3.example.com/photo.jpg",
                request_id="test-request-id",
            )

        assert len(predictions) == 2
        assert predictions[0].part_num == "3001"
        assert predictions[0].color_id == 1
        assert predictions[0].confidence == 0.94
        assert predictions[0].bbox == {"x": 120, "y": 80, "w": 45, "h": 30}
        assert predictions[1].confidence == 0.55

    @pytest.mark.asyncio
    async def test_predict_handles_empty_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}

        adapter = BrickognizeAdapter()
        with patch.object(adapter, "_http_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            predictions = await adapter.predict(
                image_url="https://s3.example.com/photo.jpg",
                request_id="test-id",
            )

        assert predictions == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scanning.py::TestBrickognizeAdapter -v
```
Expected: FAIL

- [ ] **Step 3: Implement ML client**

```python
# backend/app/scanning/schemas.py
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.scanning.models import ScanStatus


class ScanCreate(BaseModel):
    collection_id: uuid.UUID
    photo_consent: bool = False


class ScanCreateResponse(BaseModel):
    id: uuid.UUID
    upload_url: str
    s3_key: str


class ScanResultResponse(BaseModel):
    id: uuid.UUID
    part_num: str
    color_id: int
    confidence: float
    bbox: dict | None
    user_verified: bool
    needs_review: bool

    model_config = {"from_attributes": True}


class ScanResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    status: ScanStatus
    created_at: datetime
    results: list[ScanResultResponse] = []

    model_config = {"from_attributes": True}


class ScanConfirmItem(BaseModel):
    scan_result_id: uuid.UUID
    corrected_part_num: str | None = None
    corrected_color_id: int | None = None
    accepted: bool = True


class ScanConfirmRequest(BaseModel):
    items: list[ScanConfirmItem]
```

```python
# backend/app/scanning/ml_client.py
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import settings


@dataclass
class Prediction:
    part_num: str
    color_id: int
    confidence: float
    bbox: dict | None


class MLClient(Protocol):
    async def predict(self, image_url: str, request_id: str) -> list[Prediction]:
        ...


class BrickognizeAdapter:
    def __init__(self):
        self._http_client = httpx.AsyncClient(
            base_url=settings.brickognize_api_url,
            timeout=30.0,
        )

    async def predict(self, image_url: str, request_id: str) -> list[Prediction]:
        # Brickognize expects the image as a URL or file upload
        # We download from S3 and send as file
        async with httpx.AsyncClient() as download_client:
            img_resp = await download_client.get(image_url)
            img_resp.raise_for_status()

        response = await self._http_client.post(
            "/predict/",
            files={"image": ("photo.jpg", img_resp.content, "image/jpeg")},
        )
        response.raise_for_status()
        data = response.json()

        predictions = []
        for item in data.get("items", []):
            bbox = None
            if "bounding_box" in item:
                bb = item["bounding_box"]
                bbox = {"x": bb["x"], "y": bb["y"], "w": bb["width"], "h": bb["height"]}

            predictions.append(Prediction(
                part_num=item["id"],
                color_id=item["color"]["id"],
                confidence=item["score"],
                bbox=bbox,
            ))

        return predictions
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scanning.py::TestBrickognizeAdapter -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/scanning/ml_client.py app/scanning/schemas.py tests/test_scanning.py
git commit -m "feat: Brickognize ML adapter with prediction interface"
```

---

### Task 11: Scanning Router

**Files:**
- Create: `backend/app/scanning/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_scanning.py`

- [ ] **Step 1: Write tests for scanning endpoints**

Append to `backend/tests/test_scanning.py`:

```python
from app.catalog.models import Color, Part


@pytest.fixture
async def scan_fixtures(client, make_user, auth_headers, db_session):
    """Set up user, collection, catalog data for scan tests."""
    db_session.add(Part(part_num="3001", name="Brick 2x4", category_id=1))
    db_session.add(Color(id=1, name="Red", rgb="FF0000", is_trans=False))
    await db_session.commit()

    user = await make_user()
    headers = auth_headers(user.id)
    coll_resp = await client.post("/collections", json={"name": "Test"}, headers=headers)
    collection_id = coll_resp.json()["id"]
    return user, headers, collection_id


class TestScanEndpoints:
    @pytest.mark.asyncio
    async def test_create_scan_returns_upload_url(self, client, scan_fixtures):
        user, headers, collection_id = await scan_fixtures

        with patch("app.scanning.router.generate_presigned_url", return_value="https://s3.example.com/upload"):
            response = await client.post(
                "/scans",
                json={"collection_id": collection_id, "photo_consent": False},
                headers=headers,
            )
        assert response.status_code == 201
        data = response.json()
        assert "upload_url" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_process_scan_calls_ml(self, client, scan_fixtures):
        user, headers, collection_id = await scan_fixtures

        with patch("app.scanning.router.generate_presigned_url", return_value="https://s3.example.com/upload"):
            create_resp = await client.post(
                "/scans", json={"collection_id": collection_id}, headers=headers,
            )
        scan_id = create_resp.json()["id"]

        fake_predictions = [
            Prediction(part_num="3001", color_id=1, confidence=0.94, bbox={"x": 1, "y": 2, "w": 3, "h": 4})
        ]
        with patch("app.scanning.router.ml_client.predict", new_callable=AsyncMock, return_value=fake_predictions):
            with patch("app.scanning.router.generate_download_url", return_value="https://s3.example.com/download"):
                response = await client.post(f"/scans/{scan_id}/process", headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_scan_with_results(self, client, scan_fixtures):
        user, headers, collection_id = await scan_fixtures

        with patch("app.scanning.router.generate_presigned_url", return_value="https://s3.example.com/upload"):
            create_resp = await client.post(
                "/scans", json={"collection_id": collection_id}, headers=headers,
            )
        scan_id = create_resp.json()["id"]

        fake_predictions = [
            Prediction(part_num="3001", color_id=1, confidence=0.94, bbox=None)
        ]
        with patch("app.scanning.router.ml_client.predict", new_callable=AsyncMock, return_value=fake_predictions):
            with patch("app.scanning.router.generate_download_url", return_value="https://s3.example.com/dl"):
                await client.post(f"/scans/{scan_id}/process", headers=headers)

        response = await client.get(f"/scans/{scan_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert len(data["results"]) == 1
        assert data["results"][0]["needs_review"] is False  # 0.94 > 0.7

    @pytest.mark.asyncio
    async def test_confirm_scan_adds_to_collection(self, client, scan_fixtures):
        user, headers, collection_id = await scan_fixtures

        with patch("app.scanning.router.generate_presigned_url", return_value="https://s3.example.com/upload"):
            create_resp = await client.post(
                "/scans", json={"collection_id": collection_id}, headers=headers,
            )
        scan_id = create_resp.json()["id"]

        fake_predictions = [
            Prediction(part_num="3001", color_id=1, confidence=0.94, bbox=None)
        ]
        with patch("app.scanning.router.ml_client.predict", new_callable=AsyncMock, return_value=fake_predictions):
            with patch("app.scanning.router.generate_download_url", return_value="https://s3.example.com/dl"):
                await client.post(f"/scans/{scan_id}/process", headers=headers)

        # Get the scan result IDs
        scan_resp = await client.get(f"/scans/{scan_id}", headers=headers)
        result_id = scan_resp.json()["results"][0]["id"]

        # Confirm
        response = await client.post(
            f"/scans/{scan_id}/confirm",
            json={"items": [{"scan_result_id": result_id, "accepted": True}]},
            headers=headers,
        )
        assert response.status_code == 200

        # Verify piece was added to collection
        pieces_resp = await client.get(f"/collections/{collection_id}/pieces", headers=headers)
        items = pieces_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["part_num"] == "3001"
        assert items[0]["quantity"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scanning.py::TestScanEndpoints -v
```
Expected: FAIL

- [ ] **Step 3: Implement scanning router**

```python
# backend/app/scanning/router.py
import uuid

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.collections.models import Collection, CollectionPiece
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.scanning.ml_client import BrickognizeAdapter
from app.scanning.models import Scan, ScanResult, ScanStatus
from app.scanning.schemas import (
    ScanConfirmRequest,
    ScanCreate,
    ScanCreateResponse,
    ScanResponse,
    ScanResultResponse,
)

router = APIRouter(prefix="/scans", tags=["scanning"])
ml_client = BrickognizeAdapter()


def _s3_client():
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_s3_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_s3_endpoint_url
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **kwargs)


def generate_presigned_url(s3_key: str) -> str:
    client = _s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": s3_key},
        ExpiresIn=3600,
    )


def generate_download_url(s3_key: str) -> str:
    client = _s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": s3_key},
        ExpiresIn=3600,
    )


def _scan_result_to_response(r: ScanResult) -> ScanResultResponse:
    return ScanResultResponse(
        id=r.id,
        part_num=r.part_num,
        color_id=r.color_id,
        confidence=r.confidence,
        bbox=r.bbox,
        user_verified=r.user_verified,
        needs_review=r.confidence < settings.confidence_threshold,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ScanCreateResponse)
async def create_scan(
    body: ScanCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify collection belongs to user
    result = await db.execute(
        select(Collection).where(Collection.id == body.collection_id, Collection.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    s3_key = f"scans/{user.id}/{uuid.uuid4()}.jpg"
    scan = Scan(
        collection_id=body.collection_id,
        user_id=user.id,
        s3_key=s3_key,
        photo_consent=body.photo_consent,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    upload_url = generate_presigned_url(s3_key)
    return ScanCreateResponse(id=scan.id, upload_url=upload_url, s3_key=s3_key)


@router.post("/{scan_id}/process", response_model=ScanResponse)
async def process_scan(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Scan).where(Scan.id == scan_id, Scan.user_id == user.id)
    )
    scan = result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    scan.status = ScanStatus.PROCESSING
    await db.commit()

    try:
        image_url = generate_download_url(scan.s3_key)
        predictions = await ml_client.predict(image_url=image_url, request_id=str(scan.id))
    except Exception:
        scan.status = ScanStatus.FAILED
        await db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ML service unavailable")

    for pred in predictions:
        scan_result = ScanResult(
            scan_id=scan.id,
            part_num=pred.part_num,
            color_id=pred.color_id,
            confidence=pred.confidence,
            bbox=pred.bbox,
        )
        db.add(scan_result)

    scan.status = ScanStatus.COMPLETED
    await db.commit()

    # Reload with results
    result = await db.execute(
        select(Scan).options(selectinload(Scan.results)).where(Scan.id == scan.id)
    )
    scan = result.scalar_one()

    return ScanResponse(
        id=scan.id,
        collection_id=scan.collection_id,
        status=scan.status,
        created_at=scan.created_at,
        results=[_scan_result_to_response(r) for r in scan.results],
    )


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Scan).options(selectinload(Scan.results)).where(Scan.id == scan_id, Scan.user_id == user.id)
    )
    scan = result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    return ScanResponse(
        id=scan.id,
        collection_id=scan.collection_id,
        status=scan.status,
        created_at=scan.created_at,
        results=[_scan_result_to_response(r) for r in scan.results],
    )


@router.post("/{scan_id}/confirm")
async def confirm_scan(
    scan_id: uuid.UUID,
    body: ScanConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Scan).options(selectinload(Scan.results)).where(Scan.id == scan_id, Scan.user_id == user.id)
    )
    scan = result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    result_map = {r.id: r for r in scan.results}

    for item in body.items:
        scan_result = result_map.get(item.scan_result_id)
        if scan_result is None:
            continue

        if not item.accepted:
            continue

        scan_result.user_verified = True
        if item.corrected_part_num:
            scan_result.user_correction_part = item.corrected_part_num
        if item.corrected_color_id is not None:
            scan_result.user_correction_color = item.corrected_color_id

        # Use corrected values if provided, otherwise use ML prediction
        final_part = item.corrected_part_num or scan_result.part_num
        final_color = item.corrected_color_id if item.corrected_color_id is not None else scan_result.color_id

        # Add to collection (increment if exists)
        existing_result = await db.execute(
            select(CollectionPiece).where(
                CollectionPiece.collection_id == scan.collection_id,
                CollectionPiece.part_num == final_part,
                CollectionPiece.color_id == final_color,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.quantity += 1
        else:
            db.add(CollectionPiece(
                collection_id=scan.collection_id,
                part_num=final_part,
                color_id=final_color,
                quantity=1,
            ))

    await db.commit()
    return {"detail": "Scan confirmed", "pieces_added": sum(1 for i in body.items if i.accepted)}
```

- [ ] **Step 4: Register scanning router in main.py**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.collections.router import router as collections_router
from app.scanning.router import router as scanning_router

app = FastAPI(title="LooseBricks API", version="0.1.0")
app.include_router(auth_router)
app.include_router(collections_router)
app.include_router(scanning_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_scanning.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/scanning/router.py app/main.py tests/test_scanning.py
git commit -m "feat: scanning endpoints with ML processing and confirmation flow"
```

---

### Task 12: Catalog Sync (Rebrickable CSV Import)

**Files:**
- Create: `backend/app/catalog/sync.py`
- Create: `backend/tests/test_catalog_sync.py`

- [ ] **Step 1: Write tests for catalog sync**

```python
# backend/tests/test_catalog_sync.py
import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.catalog.sync import RebrickableSync


def make_csv(header: str, rows: list[str]) -> bytes:
    content = header + "\n" + "\n".join(rows) + "\n"
    return content.encode("utf-8")


class TestRebrickableSync:
    @pytest.mark.asyncio
    async def test_sync_parts(self, db_session):
        csv_data = {
            "parts.csv.gz": make_csv("part_num,name,part_cat_id", ["3001,Brick 2x4,1", "3003,Brick 2x2,1"]),
            "colors.csv.gz": make_csv("id,name,rgb,is_trans", ["1,Red,FF0000,f", "4,Blue,0000FF,f"]),
            "sets.csv.gz": make_csv("set_num,name,year,theme_id,num_parts", ["10281-1,Bonsai Tree,2021,252,878"]),
            "themes.csv.gz": make_csv("id,name,parent_id", ["252,Botanical Collection,"]),
            "inventories.csv.gz": make_csv("id,version,set_num", ["1,1,10281-1"]),
            "inventory_parts.csv.gz": make_csv(
                "inventory_id,part_num,color_id,quantity,is_spare",
                ["1,3001,1,10,f", "1,3003,4,5,f", "1,3001,4,2,t"],
            ),
        }

        async def fake_download(url: str) -> bytes:
            for name, data in csv_data.items():
                if name in url:
                    return data
            raise ValueError(f"Unexpected URL: {url}")

        syncer = RebrickableSync(db_session)
        with patch.object(syncer, "_download_csv", side_effect=fake_download):
            await syncer.sync_catalog()

        # Verify parts were imported
        from sqlalchemy import select, func
        from app.catalog.models import Part, Color, Set, SetPart

        parts = (await db_session.execute(select(func.count()).select_from(Part))).scalar()
        assert parts == 2

        colors = (await db_session.execute(select(func.count()).select_from(Color))).scalar()
        assert colors == 2

        sets = (await db_session.execute(select(func.count()).select_from(Set))).scalar()
        assert sets == 1

        # Only non-spare parts should be imported (2 rows, not 3)
        set_parts = (await db_session.execute(select(func.count()).select_from(SetPart))).scalar()
        assert set_parts == 2

    @pytest.mark.asyncio
    async def test_sync_is_idempotent(self, db_session):
        csv_data = {
            "parts.csv.gz": make_csv("part_num,name,part_cat_id", ["3001,Brick 2x4,1"]),
            "colors.csv.gz": make_csv("id,name,rgb,is_trans", ["1,Red,FF0000,f"]),
            "sets.csv.gz": make_csv("set_num,name,year,theme_id,num_parts", []),
            "themes.csv.gz": make_csv("id,name,parent_id", []),
            "inventories.csv.gz": make_csv("id,version,set_num", []),
            "inventory_parts.csv.gz": make_csv("inventory_id,part_num,color_id,quantity,is_spare", []),
        }

        async def fake_download(url: str) -> bytes:
            for name, data in csv_data.items():
                if name in url:
                    return data
            raise ValueError(f"Unexpected URL: {url}")

        syncer = RebrickableSync(db_session)
        with patch.object(syncer, "_download_csv", side_effect=fake_download):
            await syncer.sync_catalog()
            await syncer.sync_catalog()  # Run again

        from sqlalchemy import select, func
        from app.catalog.models import Part

        parts = (await db_session.execute(select(func.count()).select_from(Part))).scalar()
        assert parts == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_catalog_sync.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement catalog sync**

```python
# backend/app/catalog/sync.py
import csv
import gzip
import io

import httpx
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Color, Moc, MocPart, Part, Set, SetPart

REBRICKABLE_CDN = "https://cdn.rebrickable.com/media/downloads"


class RebrickableSync:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _download_csv(self, url: str) -> bytes:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content

    def _parse_csv(self, data: bytes) -> list[dict]:
        try:
            text_data = gzip.decompress(data).decode("utf-8")
        except gzip.BadGzipFile:
            text_data = data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text_data))
        return list(reader)

    async def sync_catalog(self):
        """Download and import all Rebrickable catalog CSVs."""
        # Download all CSVs
        parts_data = await self._download_csv(f"{REBRICKABLE_CDN}/parts.csv.gz")
        colors_data = await self._download_csv(f"{REBRICKABLE_CDN}/colors.csv.gz")
        sets_data = await self._download_csv(f"{REBRICKABLE_CDN}/sets.csv.gz")
        inventories_data = await self._download_csv(f"{REBRICKABLE_CDN}/inventories.csv.gz")
        inv_parts_data = await self._download_csv(f"{REBRICKABLE_CDN}/inventory_parts.csv.gz")

        # Parse
        parts_rows = self._parse_csv(parts_data)
        colors_rows = self._parse_csv(colors_data)
        sets_rows = self._parse_csv(sets_data)
        inventories_rows = self._parse_csv(inventories_data)
        inv_parts_rows = self._parse_csv(inv_parts_data)

        # Build inventory_id → set_num mapping (use version 1 only)
        inv_to_set = {}
        for row in inventories_rows:
            if row["version"] == "1":
                inv_to_set[row["id"]] = row["set_num"]

        # Clear existing data (full replace strategy)
        await self.db.execute(delete(SetPart))
        await self.db.execute(delete(Set))
        await self.db.execute(delete(Part))
        await self.db.execute(delete(Color))

        # Insert colors
        for row in colors_rows:
            self.db.add(Color(
                id=int(row["id"]),
                name=row["name"],
                rgb=row["rgb"],
                is_trans=row["is_trans"].lower() in ("t", "true", "1"),
            ))
        await self.db.flush()

        # Insert parts
        for row in parts_rows:
            self.db.add(Part(
                part_num=row["part_num"],
                name=row["name"],
                category_id=int(row["part_cat_id"]),
            ))
        await self.db.flush()

        # Insert sets
        for row in sets_rows:
            self.db.add(Set(
                set_num=row["set_num"],
                name=row["name"],
                year=int(row["year"]),
                num_parts=int(row["num_parts"]),
                theme_id=int(row["theme_id"]),
            ))
        await self.db.flush()

        # Insert set_parts (skip spares)
        for row in inv_parts_rows:
            if row.get("is_spare", "f").lower() in ("t", "true", "1"):
                continue
            set_num = inv_to_set.get(row["inventory_id"])
            if set_num is None:
                continue
            self.db.add(SetPart(
                set_num=set_num,
                part_num=row["part_num"],
                color_id=int(row["color_id"]),
                quantity=int(row["quantity"]),
            ))

        await self.db.commit()

    async def sync_mocs(self):
        """Fetch MOCs from Rebrickable API and import them."""
        from app.config import settings

        if not settings.rebrickable_api_key:
            return

        async with httpx.AsyncClient() as client:
            # Clear existing MOC data
            await self.db.execute(delete(MocPart))
            await self.db.execute(delete(Moc))

            page = 1
            while True:
                resp = await client.get(
                    "https://rebrickable.com/api/v3/lego/mocs/",
                    params={"page": page, "page_size": 100, "key": settings.rebrickable_api_key},
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                for moc in data.get("results", []):
                    self.db.add(Moc(
                        set_num=moc["set_num"],
                        name=moc["name"],
                        designer_name=moc.get("designer_name", ""),
                        num_parts=moc.get("num_parts", 0),
                    ))
                await self.db.flush()

                # Fetch parts for each MOC
                for moc in data.get("results", []):
                    parts_resp = await client.get(
                        f"https://rebrickable.com/api/v3/lego/mocs/{moc['set_num']}/parts/",
                        params={"key": settings.rebrickable_api_key, "page_size": 500},
                    )
                    if parts_resp.status_code == 200:
                        for part in parts_resp.json().get("results", []):
                            self.db.add(MocPart(
                                set_num=moc["set_num"],
                                part_num=part["part"]["part_num"],
                                color_id=part["color"]["id"],
                                quantity=part["quantity"],
                            ))
                    await self.db.flush()

                if not data.get("next"):
                    break
                page += 1

            await self.db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_catalog_sync.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/catalog/sync.py tests/test_catalog_sync.py
git commit -m "feat: Rebrickable catalog CSV sync with full-replace strategy and MOC API sync"
```

---

### Task 13: Catalog API Endpoints

**Files:**
- Create: `backend/app/catalog/schemas.py`
- Create: `backend/app/catalog/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_catalog.py`

- [ ] **Step 1: Write tests for catalog endpoints**

```python
# backend/tests/test_catalog.py
import pytest

from app.catalog.models import Color, Part


@pytest.fixture
async def seed_catalog(db_session):
    db_session.add_all([
        Part(part_num="3001", name="Brick 2x4", category_id=1),
        Part(part_num="3003", name="Brick 2x2", category_id=1),
        Part(part_num="3010", name="Brick 1x4", category_id=1),
        Part(part_num="3700", name="Technic Brick 1x2", category_id=3),
        Color(id=1, name="Red", rgb="FF0000", is_trans=False),
        Color(id=4, name="Blue", rgb="0000FF", is_trans=False),
        Color(id=15, name="White", rgb="FFFFFF", is_trans=False),
    ])
    await db_session.commit()


class TestCatalog:
    @pytest.mark.asyncio
    async def test_search_parts_by_name(self, client, seed_catalog, make_user, auth_headers):
        user = await make_user()
        headers = auth_headers(user.id)
        response = await client.get("/catalog/parts?q=Brick+2x4", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["part_num"] == "3001"

    @pytest.mark.asyncio
    async def test_search_parts_by_number(self, client, seed_catalog, make_user, auth_headers):
        user = await make_user()
        headers = auth_headers(user.id)
        response = await client.get("/catalog/parts?q=3003", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_search_parts_partial(self, client, seed_catalog, make_user, auth_headers):
        user = await make_user()
        headers = auth_headers(user.id)
        response = await client.get("/catalog/parts?q=Brick", headers=headers)
        assert response.status_code == 200
        # Should match "Brick 2x4", "Brick 2x2", "Brick 1x4", "Technic Brick 1x2"
        assert len(response.json()["items"]) == 4

    @pytest.mark.asyncio
    async def test_list_colors(self, client, seed_catalog, make_user, auth_headers):
        user = await make_user()
        headers = auth_headers(user.id)
        response = await client.get("/catalog/colors", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) == 3

    @pytest.mark.asyncio
    async def test_get_part_detail(self, client, seed_catalog, make_user, auth_headers):
        user = await make_user()
        headers = auth_headers(user.id)
        response = await client.get("/catalog/parts/3001", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["part_num"] == "3001"
        assert data["name"] == "Brick 2x4"

    @pytest.mark.asyncio
    async def test_get_part_not_found(self, client, seed_catalog, make_user, auth_headers):
        user = await make_user()
        headers = auth_headers(user.id)
        response = await client.get("/catalog/parts/9999", headers=headers)
        assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_catalog.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement catalog schemas and router**

```python
# backend/app/catalog/schemas.py
from pydantic import BaseModel


class PartResponse(BaseModel):
    part_num: str
    name: str
    category_id: int

    model_config = {"from_attributes": True}


class PartSearchResponse(BaseModel):
    items: list[PartResponse]


class ColorResponse(BaseModel):
    id: int
    name: str
    rgb: str
    is_trans: bool

    model_config = {"from_attributes": True}
```

```python
# backend/app/catalog/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.catalog.models import Color, Part
from app.catalog.schemas import ColorResponse, PartResponse, PartSearchResponse
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/parts", response_model=PartSearchResponse)
async def search_parts(
    q: str = "",
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Part)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Part.name.ilike(pattern), Part.part_num.ilike(pattern)))
    stmt = stmt.order_by(Part.part_num).limit(limit)

    result = await db.execute(stmt)
    parts = result.scalars().all()
    return PartSearchResponse(items=[PartResponse.model_validate(p) for p in parts])


@router.get("/colors", response_model=list[ColorResponse])
async def list_colors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Color).order_by(Color.name))
    colors = result.scalars().all()
    return [ColorResponse.model_validate(c) for c in colors]


@router.get("/parts/{part_num}", response_model=PartResponse)
async def get_part(
    part_num: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Part).where(Part.part_num == part_num))
    part = result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Part not found")
    return PartResponse.model_validate(part)
```

- [ ] **Step 4: Register catalog router in main.py**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.catalog.router import router as catalog_router
from app.collections.router import router as collections_router
from app.scanning.router import router as scanning_router

app = FastAPI(title="LooseBricks API", version="0.1.0")
app.include_router(auth_router)
app.include_router(collections_router)
app.include_router(scanning_router)
app.include_router(catalog_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_catalog.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/catalog/schemas.py app/catalog/router.py app/main.py tests/test_catalog.py
git commit -m "feat: catalog API endpoints for part search and color listing"
```

---

### Task 14: Build Matching Engine

**Files:**
- Create: `backend/app/builds/__init__.py`
- Create: `backend/app/builds/matching.py`
- Create: `backend/app/builds/schemas.py`
- Create: `backend/app/builds/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_builds.py`

- [ ] **Step 1: Write tests for build matching**

```python
# backend/tests/test_builds.py
import uuid

import pytest

from app.catalog.models import Color, Part, Set, SetPart
from app.collections.models import Collection, CollectionPiece


@pytest.fixture
async def build_fixtures(db_session, make_user, auth_headers):
    """Seed catalog with two sets and create a user collection."""
    # Catalog data
    db_session.add_all([
        Part(part_num="3001", name="Brick 2x4", category_id=1),
        Part(part_num="3003", name="Brick 2x2", category_id=1),
        Part(part_num="3010", name="Brick 1x4", category_id=1),
        Color(id=1, name="Red", rgb="FF0000", is_trans=False),
        Color(id=4, name="Blue", rgb="0000FF", is_trans=False),
    ])
    await db_session.flush()

    # Set A: needs 10x 3001-red + 5x 3003-blue = 15 parts
    db_session.add(Set(set_num="10001-1", name="Small Set", year=2024, num_parts=15, theme_id=1))
    db_session.add(SetPart(set_num="10001-1", part_num="3001", color_id=1, quantity=10))
    db_session.add(SetPart(set_num="10001-1", part_num="3003", color_id=4, quantity=5))

    # Set B: needs 100x 3001-red + 50x 3010-red = 150 parts (user will have low %)
    db_session.add(Set(set_num="10002-1", name="Big Set", year=2024, num_parts=150, theme_id=1))
    db_session.add(SetPart(set_num="10002-1", part_num="3001", color_id=1, quantity=100))
    db_session.add(SetPart(set_num="10002-1", part_num="3010", color_id=1, quantity=50))

    await db_session.flush()

    # User collection: 10x 3001-red + 5x 3003-blue (100% of Set A, ~6.7% of Set B)
    user = await make_user()
    headers = auth_headers(user.id)
    collection = Collection(user_id=user.id, name="My Bricks")
    db_session.add(collection)
    await db_session.flush()

    db_session.add(CollectionPiece(collection_id=collection.id, part_num="3001", color_id=1, quantity=10))
    db_session.add(CollectionPiece(collection_id=collection.id, part_num="3003", color_id=4, quantity=5))
    await db_session.commit()

    return user, headers, collection


class TestBuildMatching:
    @pytest.mark.asyncio
    async def test_suggest_returns_matching_sets(self, client, build_fixtures):
        user, headers, collection = await build_fixtures
        response = await client.get(
            f"/builds/suggest?collection_ids={collection.id}&min_completeness=70",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["set_num"] == "10001-1"
        assert data["items"][0]["completeness_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_suggest_low_threshold_returns_more(self, client, build_fixtures):
        user, headers, collection = await build_fixtures
        response = await client.get(
            f"/builds/suggest?collection_ids={collection.id}&min_completeness=5",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2  # Both sets now

    @pytest.mark.asyncio
    async def test_suggest_default_threshold_70(self, client, build_fixtures):
        user, headers, collection = await build_fixtures
        response = await client.get(
            f"/builds/suggest?collection_ids={collection.id}",
            headers=headers,
        )
        assert response.status_code == 200
        # Only Set A (100%) should appear, Set B (~6.7%) should not
        assert len(response.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_build_details(self, client, build_fixtures):
        user, headers, collection = await build_fixtures
        response = await client.get(
            f"/builds/10001-1/details?collection_ids={collection.id}",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["set_num"] == "10001-1"
        assert data["completeness_pct"] == 100.0
        assert len(data["have"]) == 2
        assert len(data["missing"]) == 0

    @pytest.mark.asyncio
    async def test_build_details_with_missing_pieces(self, client, build_fixtures):
        user, headers, collection = await build_fixtures
        response = await client.get(
            f"/builds/10002-1/details?collection_ids={collection.id}",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["completeness_pct"] < 100
        assert len(data["missing"]) > 0
        # Missing 90x 3001-red (have 10, need 100) and 50x 3010-red (have 0, need 50)
        missing_parts = {m["part_num"] for m in data["missing"]}
        assert "3001" in missing_parts
        assert "3010" in missing_parts
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_builds.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement matching engine**

```python
# backend/app/builds/__init__.py
```

```python
# backend/app/builds/schemas.py
import uuid

from pydantic import BaseModel


class BuildSuggestion(BaseModel):
    set_num: str
    name: str
    year: int
    num_parts: int
    matched_parts: int
    total_parts: int
    completeness_pct: float


class BuildSuggestResponse(BaseModel):
    items: list[BuildSuggestion]


class BuildPieceDetail(BaseModel):
    part_num: str
    color_id: int
    needed: int
    have: int


class BuildDetailResponse(BaseModel):
    set_num: str
    name: str
    year: int
    num_parts: int
    completeness_pct: float
    have: list[BuildPieceDetail]
    missing: list[BuildPieceDetail]
```

```python
# backend/app/builds/matching.py
import uuid

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import case

from app.catalog.models import Moc, MocPart, Set, SetPart
from app.collections.models import CollectionPiece


def _build_user_pieces_subquery(collection_ids: list[uuid.UUID]):
    return (
        select(
            CollectionPiece.part_num,
            CollectionPiece.color_id,
            func.sum(CollectionPiece.quantity).label("qty"),
        )
        .where(CollectionPiece.collection_id.in_(collection_ids))
        .group_by(CollectionPiece.part_num, CollectionPiece.color_id)
        .subquery("user_pieces")
    )


def _rows_to_dicts(rows) -> list[dict]:
    return [
        {
            "set_num": row.set_num,
            "name": row.name,
            "year": getattr(row, "year", 0),
            "num_parts": row.num_parts,
            "matched_parts": int(row.matched),
            "total_parts": int(row.total),
            "completeness_pct": round(float(row.pct), 1),
        }
        for row in rows
    ]


async def _match_sets(
    db: AsyncSession,
    user_pieces,
    min_completeness: float,
    min_parts: int | None,
    max_parts: int | None,
    theme_id: int | None,
    limit: int,
) -> list[dict]:
    matched_expr = func.least(func.coalesce(user_pieces.c.qty, 0), SetPart.quantity)
    stmt = (
        select(
            Set.set_num, Set.name, Set.year, Set.num_parts,
            func.sum(matched_expr).label("matched"),
            func.sum(SetPart.quantity).label("total"),
            (100.0 * func.sum(matched_expr) / func.sum(SetPart.quantity)).label("pct"),
        )
        .select_from(SetPart)
        .join(Set, Set.set_num == SetPart.set_num)
        .outerjoin(user_pieces, (SetPart.part_num == user_pieces.c.part_num) & (SetPart.color_id == user_pieces.c.color_id))
        .group_by(Set.set_num, Set.name, Set.year, Set.num_parts)
        .having((100.0 * func.sum(matched_expr) / func.sum(SetPart.quantity)) >= min_completeness)
        .order_by(literal_column("pct").desc())
        .limit(limit)
    )
    if min_parts is not None:
        stmt = stmt.where(Set.num_parts >= min_parts)
    if max_parts is not None:
        stmt = stmt.where(Set.num_parts <= max_parts)
    if theme_id is not None:
        stmt = stmt.where(Set.theme_id == theme_id)
    return _rows_to_dicts((await db.execute(stmt)).all())


async def _match_mocs(
    db: AsyncSession,
    user_pieces,
    min_completeness: float,
    min_parts: int | None,
    max_parts: int | None,
    limit: int,
) -> list[dict]:
    matched_expr = func.least(func.coalesce(user_pieces.c.qty, 0), MocPart.quantity)
    stmt = (
        select(
            Moc.set_num, Moc.name, Moc.num_parts,
            func.sum(matched_expr).label("matched"),
            func.sum(MocPart.quantity).label("total"),
            (100.0 * func.sum(matched_expr) / func.sum(MocPart.quantity)).label("pct"),
        )
        .select_from(MocPart)
        .join(Moc, Moc.set_num == MocPart.set_num)
        .outerjoin(user_pieces, (MocPart.part_num == user_pieces.c.part_num) & (MocPart.color_id == user_pieces.c.color_id))
        .group_by(Moc.set_num, Moc.name, Moc.num_parts)
        .having((100.0 * func.sum(matched_expr) / func.sum(MocPart.quantity)) >= min_completeness)
        .order_by(literal_column("pct").desc())
        .limit(limit)
    )
    if min_parts is not None:
        stmt = stmt.where(Moc.num_parts >= min_parts)
    if max_parts is not None:
        stmt = stmt.where(Moc.num_parts <= max_parts)
    return _rows_to_dicts((await db.execute(stmt)).all())


async def find_matching_builds(
    db: AsyncSession,
    collection_ids: list[uuid.UUID],
    min_completeness: float = 70.0,
    min_parts: int | None = None,
    max_parts: int | None = None,
    theme_id: int | None = None,
    build_type: str = "all",
    limit: int = 50,
) -> list[dict]:
    """Find sets/MOCs ranked by completeness % against user's collections."""
    user_pieces = _build_user_pieces_subquery(collection_ids)

    results = []
    if build_type in ("set", "all"):
        results.extend(await _match_sets(db, user_pieces, min_completeness, min_parts, max_parts, theme_id, limit))
    if build_type in ("moc", "all"):
        results.extend(await _match_mocs(db, user_pieces, min_completeness, min_parts, max_parts, limit))

    # Sort combined results by completeness and trim to limit
    results.sort(key=lambda r: r["completeness_pct"], reverse=True)
    return results[:limit]


async def get_build_detail(
    db: AsyncSession,
    set_num: str,
    collection_ids: list[uuid.UUID],
) -> dict | None:
    """Get detailed breakdown of what user has/needs for a specific set or MOC."""

    # Try set first, then MOC
    set_result = await db.execute(select(Set).where(Set.set_num == set_num))
    set_obj = set_result.scalar_one_or_none()

    moc_obj = None
    parts_table = SetPart
    if set_obj is None:
        moc_result = await db.execute(select(Moc).where(Moc.set_num == set_num))
        moc_obj = moc_result.scalar_one_or_none()
        if moc_obj is None:
            return None
        parts_table = MocPart

    build_obj = set_obj or moc_obj
    user_pieces = _build_user_pieces_subquery(collection_ids)

    stmt = (
        select(
            parts_table.part_num,
            parts_table.color_id,
            parts_table.quantity.label("needed"),
            func.coalesce(user_pieces.c.qty, 0).label("have"),
        )
        .outerjoin(
            user_pieces,
            (parts_table.part_num == user_pieces.c.part_num)
            & (parts_table.color_id == user_pieces.c.color_id),
        )
        .where(parts_table.set_num == set_num)
    )

    result = await db.execute(stmt)
    rows = result.all()

    have = []
    missing = []
    total_matched = 0
    total_needed = 0

    for row in rows:
        matched = min(int(row.have), row.needed)
        total_matched += matched
        total_needed += row.needed

        piece = {
            "part_num": row.part_num,
            "color_id": row.color_id,
            "needed": row.needed,
            "have": int(row.have),
        }

        if int(row.have) >= row.needed:
            have.append(piece)
        else:
            missing.append(piece)

    pct = round(100.0 * total_matched / total_needed, 1) if total_needed > 0 else 0.0

    return {
        "set_num": build_obj.set_num,
        "name": build_obj.name,
        "year": getattr(build_obj, "year", 0),
        "num_parts": build_obj.num_parts,
        "completeness_pct": pct,
        "have": have,
        "missing": missing,
    }
```

- [ ] **Step 4: Implement builds router**

```python
# backend/app/builds/router.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.builds.matching import find_matching_builds, get_build_detail
from app.builds.schemas import BuildDetailResponse, BuildSuggestResponse
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/builds", tags=["builds"])


@router.get("/suggest", response_model=BuildSuggestResponse)
async def suggest_builds(
    collection_ids: str = Query(..., description="Comma-separated collection UUIDs"),
    min_completeness: float = 70.0,
    min_parts: int | None = None,
    max_parts: int | None = None,
    theme_id: int | None = None,
    type: str = "all",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ids = [uuid.UUID(cid.strip()) for cid in collection_ids.split(",")]

    results = await find_matching_builds(
        db=db,
        collection_ids=ids,
        min_completeness=min_completeness,
        min_parts=min_parts,
        max_parts=max_parts,
        theme_id=theme_id,
        build_type=type,
    )

    return BuildSuggestResponse(items=results)


@router.get("/{set_num}/details", response_model=BuildDetailResponse)
async def build_details(
    set_num: str,
    collection_ids: str = Query(..., description="Comma-separated collection UUIDs"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ids = [uuid.UUID(cid.strip()) for cid in collection_ids.split(",")]

    detail = await get_build_detail(db=db, set_num=set_num, collection_ids=ids)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Set not found")

    return BuildDetailResponse(**detail)
```

- [ ] **Step 5: Register builds router in main.py**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.builds.router import router as builds_router
from app.catalog.router import router as catalog_router
from app.collections.router import router as collections_router
from app.scanning.router import router as scanning_router

app = FastAPI(title="LooseBricks API", version="0.1.0")
app.include_router(auth_router)
app.include_router(collections_router)
app.include_router(scanning_router)
app.include_router(catalog_router)
app.include_router(builds_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_builds.py -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add app/builds/ app/main.py tests/test_builds.py
git commit -m "feat: build matching engine with completeness ranking and detail view"
```

---

### Task 15: Dockerfile

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Verify it builds**

```bash
cd backend
docker build -t loosebricks-backend .
```
Expected: successful build

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: production Dockerfile"
```

---

### Task 16: Full Integration Test Run

- [ ] **Step 1: Start dev services**

```bash
cd backend
docker compose up -d
```

- [ ] **Step 2: Create test database**

```bash
docker compose exec db psql -U loosebricks -c "CREATE DATABASE loosebricks_test;"
```

- [ ] **Step 3: Run all tests**

```bash
pytest -v
```
Expected: all tests PASS

- [ ] **Step 4: Verify the app starts**

```bash
uvicorn app.main:app --reload
# Visit http://localhost:8000/docs to see auto-generated API docs
# Visit http://localhost:8000/health to verify health check
```

- [ ] **Step 5: Commit any fixes if needed, then final commit**

```bash
git add -A
git commit -m "chore: final integration verification"
```
