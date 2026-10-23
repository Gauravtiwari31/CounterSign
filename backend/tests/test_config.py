import pytest

from app.config import Settings


def test_pr_preview_uses_preview_database():
    s = Settings(database_url="postgres://prod/db", is_pull_request=True, preview_database_url="postgres://preview/db")
    assert s.async_database_url == "postgresql+asyncpg://preview/db"


def test_pr_preview_without_preview_database_refuses_production():
    s = Settings(database_url="postgres://prod/db", is_pull_request=True, preview_database_url="")
    with pytest.raises(RuntimeError):
        _ = s.async_database_url


def test_production_ignores_preview_database():
    s = Settings(database_url="postgres://prod/db", preview_database_url="postgres://preview/db")
    assert s.async_database_url == "postgresql+asyncpg://prod/db"
