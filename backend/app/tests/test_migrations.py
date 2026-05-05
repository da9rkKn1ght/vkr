from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_creates_phase1_schema(tmp_path, monkeypatch) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    db_path = tmp_path / "migration_phase1.db"
    async_db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    sync_db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", async_db_url)
    monkeypatch.setenv("JWT_SECRET", "migration_secret_123456")
    monkeypatch.setenv("ADMIN_USERNAME", "migration_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "migration_admin_password")

    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", async_db_url)

    command.upgrade(config, "head")

    engine = create_engine(sync_db_url)
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())
    assert {"users", "cameras", "zones", "incidents"}.issubset(table_names)

    unique_constraints = inspector.get_unique_constraints("users")
    assert any("username" in constraint.get("column_names", []) for constraint in unique_constraints)

    zones_foreign_keys = inspector.get_foreign_keys("zones")
    assert any(fk.get("referred_table") == "cameras" for fk in zones_foreign_keys)

    incidents_foreign_keys = inspector.get_foreign_keys("incidents")
    assert any(fk.get("referred_table") == "cameras" for fk in incidents_foreign_keys)

    with engine.connect() as connection:
        seeded_user = connection.execute(
            text("SELECT username, role FROM users WHERE username = 'migration_admin'")
        ).fetchone()

    assert seeded_user is not None
    assert seeded_user[1] == "admin"
    engine.dispose()

