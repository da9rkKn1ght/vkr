import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import dispose_engine, get_engine, get_session_maker
from app.models.camera import Camera
from app.models.incident import Incident
from app.models.enums import UserRole
from app.models.user import User
from app.models.zone import Zone


@pytest.fixture(scope="session", autouse=True)
def test_environment(tmp_path_factory: pytest.TempPathFactory) -> None:
    db_path = tmp_path_factory.mktemp("phase1") / "phase1_test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    os.environ["JWT_SECRET"] = "test_jwt_secret_for_phase1_123456"
    os.environ["ADMIN_USERNAME"] = "seed_admin"
    os.environ["ADMIN_PASSWORD"] = "seed_password"
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def initialized_database(test_environment: None) -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest_asyncio.fixture
async def seeded_users(initialized_database: None) -> dict[str, str]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        await session.execute(delete(Incident))
        await session.execute(delete(Zone))
        await session.execute(delete(Camera))
        await session.execute(delete(User))
        session.add_all(
            [
                User(
                    username="admin",
                    password_hash=hash_password("admin_password"),
                    role=UserRole.admin,
                ),
                User(
                    username="manager",
                    password_hash=hash_password("manager_password"),
                    role=UserRole.manager,
                ),
            ]
        )
        await session.commit()
    return {
        "admin_username": "admin",
        "admin_password": "admin_password",
        "manager_username": "manager",
        "manager_password": "manager_password",
    }


@pytest_asyncio.fixture
async def client(initialized_database: None) -> AsyncClient:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
