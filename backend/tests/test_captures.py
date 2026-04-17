"""
Unit tests for /api/v1/captures — list + patch.

All DB I/O is mocked — no network or real DB.
"""
import uuid
from datetime import datetime, date, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    from app.routes.v1.captures import router
    application = FastAPI()
    application.include_router(router)
    return application


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_capture(category="TODO", text="buy milk", status="open", edited=None, cap_id=None):
    c = MagicMock()
    c.id = cap_id or uuid.uuid4()
    c.entry_id = uuid.uuid4()
    c.category = category
    c.extracted_text = text
    c.edited_text = edited
    c.status = status
    c.classified_at = datetime.now(timezone.utc)
    c.user_override = False
    return c


def _make_entry(user_id=1, local_date_=None):
    e = MagicMock()
    e.id = uuid.uuid4()
    e.user_id = user_id
    e.local_date = local_date_ or date(2026, 4, 5)
    return e


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


def _db_for_list(rows):
    """rows = list of (capture, entry) tuples."""
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


def _db_for_patch(row, stale_rows=None):
    """row = (capture, entry) tuple or None."""
    db = AsyncMock()
    patch_result = MagicMock()
    patch_result.one_or_none.return_value = row

    stale_result = MagicMock()
    stale_result.scalars.return_value.all.return_value = stale_rows or []

    # list_captures not involved here; patch does 2 executes (fetch + stale lookup)
    db.execute = AsyncMock(side_effect=[patch_result, stale_result])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ── List tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_happy_path(app):
    cap = _make_capture(category="TODO", text="buy milk")
    entry = _make_entry(user_id=1)
    db = _db_for_list([(cap, entry)])
    _override_auth(app, user_id=1)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/captures/")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["category"] == "TODO"
    assert data[0]["display_text"] == "buy milk"
    assert data[0]["status"] == "open"
    assert data[0]["edited"] is False
    assert data[0]["source_date"] == "2026-04-05"


@pytest.mark.asyncio
async def test_list_display_text_prefers_edited(app):
    cap = _make_capture(text="buy milk", edited="buy 2% milk, organic")
    entry = _make_entry()
    db = _db_for_list([(cap, entry)])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/captures/")

    data = resp.json()
    assert data[0]["display_text"] == "buy 2% milk, organic"
    assert data[0]["edited"] is True


@pytest.mark.asyncio
async def test_list_invalid_category(app):
    db = _db_for_list([])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/captures/?category=EARNING")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_invalid_status(app):
    db = _db_for_list([])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/captures/?status=bogus")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_cross_user_isolation(app):
    """
    User scoping lives in the SQL WHERE clause. We verify the query builder was
    called with the current_user.id filter by checking the compiled statement.
    """
    db = _db_for_list([])  # empty result — user has no captures
    _override_auth(app, user_id=42)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/captures/")

    assert resp.status_code == 200
    assert resp.json() == []
    # Verify the statement passed to execute mentions user_id filter
    called_stmt = db.execute.call_args[0][0]
    compiled = str(called_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "user_id" in compiled
    assert "42" in compiled


# ── Patch tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_status_done(app):
    cap = _make_capture(status="open")
    entry = _make_entry(user_id=1)
    db = _db_for_patch((cap, entry))
    _override_auth(app, user_id=1)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/captures/{cap.id}", json={"status": "done"})

    assert resp.status_code == 200
    assert cap.status == "done"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_edited_text(app):
    cap = _make_capture(text="follow up with guy")
    entry = _make_entry()
    db = _db_for_patch((cap, entry))
    _override_auth(app)
    _override_db(app, app.dependency_overrides)  # noop, just to get app wired
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/captures/{cap.id}",
            json={"edited_text": "follow up with John re: pricing"},
        )

    assert resp.status_code == 200
    assert cap.edited_text == "follow up with John re: pricing"
    assert cap.user_override is True


@pytest.mark.asyncio
async def test_patch_cross_user_returns_404(app):
    """
    Capture belongs to user B; user A requests patch. The join filter on
    entries.user_id = current_user.id means the query returns no row → 404.
    """
    db = _db_for_patch(None)  # simulate user-scoped query finding nothing
    _override_auth(app, user_id=999)
    _override_db(app, db)
    fake_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/captures/{fake_id}", json={"status": "done"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_invalid_id(app):
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch("/captures/not-a-uuid", json={"status": "done"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_empty_body(app):
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/captures/{uuid.uuid4()}", json={})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_invalid_status_value(app):
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/captures/{uuid.uuid4()}", json={"status": "bogus"})

    assert resp.status_code == 422  # pydantic Literal validation


@pytest.mark.asyncio
async def test_patch_invalidates_audit_cache(app):
    """When a capture is edited, the audit cache for the source entry's date is marked stale."""
    cap = _make_capture()
    entry = _make_entry(local_date_=date(2026, 4, 3))
    stale_audit = MagicMock()
    stale_audit.is_stale = False
    db = _db_for_patch((cap, entry), stale_rows=[stale_audit])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/captures/{cap.id}", json={"status": "done"})

    assert resp.status_code == 200
    assert stale_audit.is_stale is True
