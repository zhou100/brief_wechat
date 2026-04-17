"""
Unit tests for POST /api/v1/entries/{entry_id}/reclassify.

All DB and OpenAI I/O is mocked — no network or DB required.
Tests cover: happy path, 404, empty text, and edited text input.
"""
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    """Minimal FastAPI app with only the v1 entries router mounted."""
    from app.routes.v1.entries import router

    application = FastAPI()
    application.include_router(router)
    return application


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_classification(category: str, text: str = "did something", order: int = 0):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.category = category
    c.extracted_text = text
    c.edited_text = None
    c.display_text = text
    c.display_order = order
    c.estimated_minutes = 30
    return c


def _make_entry(entry_id=None, user_id=1, classifications=None, transcript="original transcript"):
    e = MagicMock()
    e.id = entry_id or uuid.uuid4()
    e.user_id = user_id
    e.transcript = transcript
    e.recorded_at = datetime.now(timezone.utc)
    e.created_at = datetime.now(timezone.utc)
    e.duration_seconds = 60
    e.local_date = datetime.now(timezone.utc).date()
    e.classifications = classifications or []
    return e


def _override_auth(app_instance, user_id: int = 1):
    from app.utils.auth import get_current_user
    fake_user = MagicMock()
    fake_user.id = user_id
    app_instance.dependency_overrides[get_current_user] = lambda: fake_user
    return fake_user


def _override_db(app_instance, db_mock):
    """Override get_db dependency with a mock that yields the db_mock."""
    from app.db import get_db

    async def _fake_get_db():
        yield db_mock

    app_instance.dependency_overrides[get_db] = _fake_get_db


def _mock_db_returning_entry(entry):
    """Return an AsyncMock db whose execute() returns the given entry via scalar_one_or_none."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = entry

    # For audit invalidation query
    stale_result_mock = MagicMock()
    stale_result_mock.scalars.return_value.all.return_value = []

    db.execute = AsyncMock(side_effect=[result_mock, stale_result_mock])
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_db_returning_none():
    """Return an AsyncMock db whose execute() returns None (entry not found)."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reclassify_happy_path(app):
    """Reclassify returns new categories from the AI categorizer."""
    entry_id = uuid.uuid4()
    entry = _make_entry(
        entry_id=entry_id,
        classifications=[
            _make_classification("REFLECTION", "worked on project", 0),
        ],
    )
    db = _mock_db_returning_entry(entry)
    _override_auth(app)
    _override_db(app, db)

    cat_results = [{"category": "EARNING", "text": "worked on project", "estimated_minutes": 30}]

    with patch("app.routes.v1.entries.categorize_text", new_callable=AsyncMock, return_value=cat_results):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/entries/{entry_id}/reclassify")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(entry_id)


@pytest.mark.asyncio
async def test_reclassify_entry_not_found(app):
    """Reclassify returns 404 when entry doesn't exist."""
    db = _mock_db_returning_none()
    _override_auth(app)
    _override_db(app, db)
    entry_id = uuid.uuid4()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/entries/{entry_id}/reclassify")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Entry not found"


@pytest.mark.asyncio
async def test_reclassify_empty_text(app):
    """Reclassify returns 400 when entry has no text to classify."""
    entry_id = uuid.uuid4()
    entry = _make_entry(
        entry_id=entry_id,
        classifications=[],
        transcript="",
    )
    db = _mock_db_returning_entry(entry)
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(f"/entries/{entry_id}/reclassify")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Entry has no text to classify"


@pytest.mark.asyncio
async def test_reclassify_uses_edited_texts(app):
    """Reclassify uses edited classification texts, not the original transcript."""
    entry_id = uuid.uuid4()
    entry = _make_entry(
        entry_id=entry_id,
        classifications=[
            _make_classification("REFLECTION", "edited text about learning", 0),
            _make_classification("TODO", "edited todo item", 1),
        ],
        transcript="original unedited transcript",
    )
    db = _mock_db_returning_entry(entry)
    _override_auth(app)
    _override_db(app, db)

    cat_results = [
        {"category": "LEARNING", "text": "edited text about learning", "estimated_minutes": 30},
        {"category": "TODO", "text": "edited todo item", "estimated_minutes": 10},
    ]

    captured_text = None

    async def mock_categorize(text):
        nonlocal captured_text
        captured_text = text
        return cat_results

    with patch("app.routes.v1.entries.categorize_text", side_effect=mock_categorize):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(f"/entries/{entry_id}/reclassify")

    assert resp.status_code == 200
    # Should have used edited texts joined with ". ", NOT the original transcript
    assert captured_text == "edited text about learning. edited todo item"
    assert "original unedited transcript" not in (captured_text or "")
