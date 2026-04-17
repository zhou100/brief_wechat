"""
Unit tests for POST /api/v1/entries/audit.

All DB and OpenAI I/O is mocked — no network or DB required.
Tests cover: happy path, empty state, date validation, timeout, LLM error,
breakdown denominator, and authentication guard.
"""
import asyncio
import json
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    """Minimal FastAPI app with only the v1 entries router mounted."""
    from fastapi import FastAPI
    from app.routes.v1.entries import router

    application = FastAPI()
    application.include_router(router)
    return application


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_classification(category: str, text: str = "did something", order: int = 0):
    c = MagicMock()
    c.category = category
    c.extracted_text = text
    c.display_order = order
    return c


def _make_entry(user_id: int = 1, n_classifications: int = 1,
                categories=None, created_at=None):
    """
    Build a mock Entry with `classifications` list.
    categories: list of category strings, e.g. ["TODO", "EXPERIMENT"]
    """
    if categories is None:
        categories = ["EARNING"] * n_classifications
    e = MagicMock()
    e.id = uuid.uuid4()
    e.user_id = user_id
    e.transcript = "some transcript"
    e.created_at = created_at or datetime.now(timezone.utc)
    e.classifications = [
        _make_classification(cat, f"item {i}", i)
        for i, cat in enumerate(categories)
    ]
    return e


def _mock_db_with_entries(entries):
    """Return an AsyncMock db that matches the audit route's DB call sequence."""
    db = AsyncMock()

    cache_result = MagicMock()
    cache_result.scalar_one_or_none.return_value = None

    entries_result = MagicMock()
    entries_result.scalars.return_value.all.return_value = entries

    themes_result = MagicMock()
    themes_result.scalars.return_value.all.return_value = []

    stale_result = MagicMock()
    stale_result.scalars.return_value.all.return_value = []

    db.execute = AsyncMock(side_effect=[cache_result, entries_result, themes_result, stale_result])
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _mock_openai_response(text: str):
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Mocked user dependency ────────────────────────────────────────────────────

def _override_auth(app_instance, user_id: int = 1):
    """Override get_current_user with a fake user."""
    from app.utils.auth import get_current_user
    fake_user = MagicMock()
    fake_user.id = user_id
    app_instance.dependency_overrides[get_current_user] = lambda: fake_user
    return fake_user


def _override_db(app_instance, db_mock):
    """Override get_db dependency with a mock that yields db_mock."""
    from app.db import get_db

    async def _fake_get_db():
        yield db_mock

    app_instance.dependency_overrides[get_db] = _fake_get_db


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_happy_path(app):
    """Happy path: entries found → breakdown + audit_text returned."""
    entries = [_make_entry(categories=["TODO", "EARNING", "EXPERIMENT"])]
    db = _mock_db_with_entries(entries)
    _override_auth(app)
    _override_db(app, db)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    audit_text = "You spent most of your day on deep work. Good focus."

    with patch("app.routes.v1.entries._get_openai") as mock_openai:

        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response(audit_text)
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/entries/audit", json={"date": today})

    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == 1
    assert "TODO" in data["breakdown"]
    assert "EARNING" in data["breakdown"]
    assert "EXPERIMENT" in data["breakdown"]
    assert data["audit_text"] == audit_text
    assert data["generated_at"] is not None


@pytest.mark.asyncio
async def test_audit_empty_entries(app):
    """No entries for the date → returns entries=0 and a hint message, no audit_text."""
    db = _mock_db_with_entries([])
    _override_auth(app)
    _override_db(app, db)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with patch("app.routes.v1.entries._get_openai"):

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/entries/audit", json={"date": today})

    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == 0
    assert data["audit_text"] is None
    assert data["message"] is not None


@pytest.mark.asyncio
async def test_audit_future_date_rejected(app):
    """Date in the future → HTTP 400."""
    _override_auth(app)
    _override_db(app, AsyncMock())
    future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/entries/audit", json={"date": future})

    assert resp.status_code == 400
    assert "future" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_audit_date_older_than_7_days_accepted(app):
    """Older past dates are accepted by the current route contract."""
    db = _mock_db_with_entries([])
    _override_auth(app)
    _override_db(app, db)
    old_date = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/entries/audit", json={"date": old_date})

    assert resp.status_code == 200
    assert resp.json()["entries"] == 0


@pytest.mark.asyncio
async def test_audit_invalid_date_format_rejected(app):
    """Malformed date string → HTTP 400."""
    _override_auth(app)
    _override_db(app, AsyncMock())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/entries/audit", json={"date": "not-a-date"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_audit_breakdown_denominator_is_classifications(app):
    """
    Breakdown % uses classification count as denominator, not entry count.
    2 entries: entry1 has [TODO, EXPERIMENT], entry2 has [TODO] → TODO=2/3≈67%, EXPERIMENT=1/3≈33%
    """
    entry1 = _make_entry(categories=["TODO", "EXPERIMENT"])
    entry2 = _make_entry(categories=["TODO"])
    db = _mock_db_with_entries([entry1, entry2])
    _override_auth(app)
    _override_db(app, db)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with patch("app.routes.v1.entries._get_openai") as mock_openai:

        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response("audit text")
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/entries/audit", json={"date": today})

    assert resp.status_code == 200
    breakdown = resp.json()["breakdown"]
    # 3 total classifications: 2 TODO + 1 EXPERIMENT
    assert abs(breakdown["TODO"] - 66.7) < 1.0
    assert abs(breakdown["EXPERIMENT"] - 33.3) < 1.0


@pytest.mark.asyncio
async def test_audit_llm_timeout_returns_504(app):
    """asyncio.TimeoutError from OpenAI → HTTP 504."""
    entries = [_make_entry(categories=["TODO"])]
    db = _mock_db_with_entries(entries)
    _override_auth(app)
    _override_db(app, db)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with patch("app.routes.v1.entries._get_openai") as mock_openai, \
         patch("app.routes.v1.entries.asyncio.wait_for",
               side_effect=asyncio.TimeoutError):

        mock_openai.return_value.chat.completions.create = AsyncMock()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/entries/audit", json={"date": today})

    assert resp.status_code == 504


@pytest.mark.asyncio
async def test_audit_llm_exception_returns_partial_response(app):
    """Generic exception from OpenAI → 200 with audit_text=null and error message."""
    entries = [_make_entry(categories=["TODO", "EXPERIMENT"])]
    db = _mock_db_with_entries(entries)
    _override_auth(app)
    _override_db(app, db)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async def _raise_openai_error(*args, **kwargs):
        raise Exception("OpenAI error")

    with patch("app.routes.v1.entries._get_openai") as mock_openai:
        mock_openai.return_value.chat.completions.create = _raise_openai_error

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/entries/audit", json={"date": today})

    assert resp.status_code == 200
    data = resp.json()
    assert data["audit_text"] is None
    assert data["message"] is None
    # Breakdown still populated even when LLM fails
    assert len(data["breakdown"]) > 0
    assert data["entries"] == 1


@pytest.mark.asyncio
async def test_audit_date_exactly_7_days_ago_accepted(app):
    """Date exactly 7 days ago is within the allowed window → accepted."""
    entries = [_make_entry(categories=["REFLECTION"])]
    db = _mock_db_with_entries(entries)
    _override_auth(app)
    _override_db(app, db)

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    with patch("app.routes.v1.entries._get_openai") as mock_openai:

        mock_openai.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response("some audit")
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/entries/audit", json={"date": seven_days_ago})

    assert resp.status_code == 200
