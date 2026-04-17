"""
Unit tests for /api/v1/entries/search.

All DB access is mocked so we can verify query behavior and response shaping.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    from app.routes.v1.entries import router
    application = FastAPI()
    application.include_router(router)
    return application


def _override_auth(app_instance, user_id: int = 1):
    from app.utils.auth import get_current_user
    fake_user = MagicMock()
    fake_user.id = user_id
    app_instance.dependency_overrides[get_current_user] = lambda: fake_user


def _override_db(app_instance, db_mock):
    from app.db import get_db

    async def _fake_get_db():
        yield db_mock

    app_instance.dependency_overrides[get_db] = _fake_get_db


def _make_classification(text: str, category: str = "TODO"):
    cid = uuid.uuid4()
    return SimpleNamespace(
        id=cid,
        category=category,
        extracted_text=text,
        edited_text=None,
        estimated_minutes=15,
        display_text=text,
    )


def _make_entry(text: str, category: str = "TODO", created_at: datetime | None = None):
    created = created_at or datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        transcript=text,
        recorded_at=created,
        created_at=created,
        local_date=created.date(),
        duration_seconds=60,
        classifications=[_make_classification(text, category)],
        user_id=1,
    )


@pytest.mark.asyncio
async def test_search_returns_paginated_entry_items(app):
    entry_a = _make_entry("buy milk", "TODO", datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc))
    entry_b = _make_entry("weekly reflection", "REFLECTION", datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc))

    total_result = MagicMock()
    total_result.scalar.return_value = 2
    ids_result = MagicMock()
    ids_result.all.return_value = [
        SimpleNamespace(id=entry_a.id, created_at=entry_a.created_at),
        SimpleNamespace(id=entry_b.id, created_at=entry_b.created_at),
    ]
    entries_result = MagicMock()
    entries_result.scalars.return_value.all.return_value = [entry_a, entry_b]

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[total_result, ids_result, entries_result])

    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/entries/search?q=milk")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [str(entry_a.id), str(entry_b.id)]
    assert body["items"][0]["categories"][0]["category"] == "TODO"
    assert body["items"][0]["local_date"] == "2026-04-10"
    assert body["items"][0]["match_sources"] == ["transcript", "category_line"]


@pytest.mark.asyncio
async def test_search_applies_user_and_filter_params_to_query(app):
    total_result = MagicMock()
    total_result.scalar.return_value = 0
    ids_result = MagicMock()
    ids_result.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[total_result, ids_result])

    _override_auth(app, user_id=42)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/entries/search?q=milk&category=TODO&date_from=2026-04-01&date_to=2026-04-10"
        )

    assert resp.status_code == 200
    compiled = str(db.execute.call_args_list[0][0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "42" in compiled
    assert "TODO" in compiled
    assert "2026-04-01" in compiled
    assert "2026-04-10" in compiled


@pytest.mark.asyncio
async def test_search_escapes_like_wildcards(app):
    """User-entered % and _ should be escaped so they don't act as LIKE wildcards."""
    total_result = MagicMock()
    total_result.scalar.return_value = 0
    ids_result = MagicMock()
    ids_result.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[total_result, ids_result])

    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/entries/search?q=50%25%20off")

    assert resp.status_code == 200
    compiled = str(db.execute.call_args_list[0][0][0].compile(compile_kwargs={"literal_binds": True}))
    assert r"50\%" in compiled, f"expected escaped literal '50\\%' in compiled SQL, got: {compiled}"


@pytest.mark.asyncio
async def test_search_rejects_invalid_date_range(app):
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/entries/search?q=milk&date_from=2026-04-10&date_to=2026-04-01")

    assert resp.status_code == 400
    assert "date_from cannot be after date_to" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_search_rejects_one_character_queries(app):
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/entries/search?q=a")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_rejects_whitespace_only_query(app):
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/entries/search?q=   ")

    assert resp.status_code == 400
    assert "Search query cannot be empty" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_search_rejects_invalid_category(app):
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/entries/search?q=milk&category=NOT_A_REAL_CATEGORY")

    assert resp.status_code == 400
    assert "category must be one of" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_search_returns_category_name_match_provenance(app):
    entry = _make_entry("finished the sprint review", "TODO", datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc))

    total_result = MagicMock()
    total_result.scalar.return_value = 1
    ids_result = MagicMock()
    ids_result.all.return_value = [
        SimpleNamespace(id=entry.id, created_at=entry.created_at),
    ]
    entries_result = MagicMock()
    entries_result.scalars.return_value.all.return_value = [entry]

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[total_result, ids_result, entries_result])

    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/entries/search?q=todo")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["match_sources"] == ["category_name"]
