import pytest
from pydantic import ValidationError

from app.core.config import get_settings


def test_settings_load_with_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./settings_test.db")
    monkeypatch.setenv("JWT_SECRET", "settings_secret_123456")
    monkeypatch.setenv("ADMIN_USERNAME", "config_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "config_admin_password")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url.startswith("sqlite+aiosqlite")
    assert settings.jwt_secret == "settings_secret_123456"
    assert settings.admin_username == "config_admin"


def test_settings_fail_without_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./settings_test.db")
    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("ADMIN_USERNAME", "config_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "config_admin_password")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()
