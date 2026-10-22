"""DB-backed tests run against a real Postgres + pgvector (docker compose or the CI service).

They are skipped when TEST_DATABASE_URL is unreachable, so the pure unit tests still run anywhere.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql://countersign:countersign@localhost:5432/countersign_test")
os.environ.update({
    "DATABASE_URL": TEST_DB, "EMBEDDINGS": "hash", "PII_ENGINE": "regex", "RUN_WORKER": "false",
    "SANDBOX_POOL_SIZE": "0", "GEMINI_API_KEY": "", "GROQ_API_KEY": "", "REVIEWS_PER_HOUR": "1000",
    "DEMO_SESSIONS_PER_HOUR_PER_IP": "1000", "LOG_PROMPTS": "true", "COOKIE_SECURE": "false",
})
BACKEND = Path(__file__).resolve().parent.parent
_db_state: dict = {}


def _prepare_db() -> str | None:
    import asyncio

    import asyncpg

    async def reset():
        conn = await asyncpg.connect(TEST_DB.replace("+asyncpg", ""), timeout=5)
        try:
            await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        finally:
            await conn.close()

    try:
        asyncio.run(reset())
    except Exception as e:  # no database available
        return f"Postgres not reachable at {TEST_DB}: {e}"
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, capture_output=True,
                       text=True, env=os.environ.copy())
    if r.returncode != 0:
        return "alembic failed: " + r.stderr[-2000:]
    return None


def pytest_collection_modifyitems(config, items):
    # one event loop for the whole run: the app's engine pool outlives individual tests
    session_loop = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if pytest_asyncio.is_async_test(item):
            item.add_marker(session_loop, append=False)
    db_items = [i for i in items if "db" in i.keywords]
    if not db_items:
        return
    err = _prepare_db()
    if err:
        if os.environ.get("CI"):
            raise pytest.UsageError(err)
        skip = pytest.mark.skip(reason=err)
        for i in db_items:
            i.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "db: needs a Postgres database")


@pytest.fixture(scope="session")
async def app():
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
async def client_factory(app):
    import httpx

    clients = []

    def make():
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()


async def demo_client(make, role: str):
    c = make()
    r = await c.post("/api/demo/session", json={"role": role})
    assert r.status_code == 200, r.text
    return c
