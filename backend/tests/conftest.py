import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = settings.database_url.rsplit("/loosebricks", 1)[0] + "/loosebricks_test"
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
    from app.auth.jwt import create_access_token

    def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
        token = create_access_token(subject=str(user_id))
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers
