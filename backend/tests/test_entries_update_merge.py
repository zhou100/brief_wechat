"""
Tests for PATCH /api/v1/entries/{entry_id} category merge by stable id.

Verifies bidirectional inbox sync: entry-side category edits must preserve
EntryClassification id and status (done/dismissed) for rows the client echoes
back, and must delete rows whose ids the client omits.
"""
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.models.classification import EntryClassification


class FakeClassification:
    """Lightweight stand-in that supports the same attribute mutations and the
    display_text property the route depends on, without needing a real DB row."""
    def __init__(self, text, category="TODO", order=0, status="open", cid=None, edited=None):
        self.id = cid or uuid.uuid4()
        self.category = category
        self.extracted_text = text
        self.edited_text = edited
        self.display_order = order
        self.estimated_minutes = 10
        self.status = status
        self.user_override = False

    @property
    def display_text(self):
        return self.edited_text if self.edited_text else self.extracted_text


@pytest.fixture
def app():
    from app.routes.v1.entries import router
    application = FastAPI()
    application.include_router(router)
    return application


def _make_classification(text: str, category: str = "TODO", order: int = 0,
                         status: str = "open", cid=None, edited=None):
    return FakeClassification(text, category, order, status, cid, edited)


def _make_entry(classifications):
    e = MagicMock()
    e.id = uuid.uuid4()
    e.user_id = 1
    e.transcript = "transcript"
    e.recorded_at = datetime.now(timezone.utc)
    e.created_at = datetime.now(timezone.utc)
    e.duration_seconds = 60
    e.local_date = datetime.now(timezone.utc).date()
    e.classifications = list(classifications)
    return e


def _override_deps(app_instance, entry):
    from app.utils.auth import get_current_user
    from app.db import get_db

    fake_user = MagicMock()
    fake_user.id = 1
    app_instance.dependency_overrides[get_current_user] = lambda: fake_user

    db = AsyncMock()
    fetch_result = MagicMock()
    fetch_result.scalar_one_or_none.return_value = entry
    stale_result = MagicMock()
    stale_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[fetch_result, stale_result])
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    async def _refresh(obj, attrs=None):
        return None
    db.refresh = AsyncMock(side_effect=_refresh)

    async def _delete(obj):
        if obj in entry.classifications:
            entry.classifications.remove(obj)
    db.delete = AsyncMock(side_effect=_delete)

    async def _fake_get_db():
        yield db

    app_instance.dependency_overrides[get_db] = _fake_get_db
    return db


@pytest.mark.asyncio
async def test_update_preserves_status_and_id_when_editing_unrelated_row(app):
    """Editing row A must not touch row B's status or id (regression test)."""
    a = _make_classification("buy milk", order=0, status="open")
    b = _make_classification("call mom", order=1, status="done")
    entry = _make_entry([a, b])
    _override_deps(app, entry)

    payload = {
        "categories": [
            {"id": str(a.id), "text": "buy oat milk", "category": "TODO", "estimated_minutes": 10},
            {"id": str(b.id), "text": "call mom", "category": "TODO", "estimated_minutes": 10},
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/entries/{entry.id}", json=payload)

    assert resp.status_code == 200
    # Row A mutated, edited_text cleared
    assert a.extracted_text == "buy oat milk"
    assert a.edited_text is None
    # Row B untouched: status preserved, id preserved (it's the same Python object)
    assert b.status == "done"
    assert b.extracted_text == "call mom"
    # Both still in the entry — nothing was deleted
    assert a in entry.classifications
    assert b in entry.classifications


@pytest.mark.asyncio
async def test_update_after_middle_delete_keeps_status_on_correct_row(app):
    """Deleting the middle row must not bleed status onto the wrong row.

    This is the bug Finding A1 described: an index-based merge would have
    transferred row B's status onto row C's slot. With id-based merge, B is
    deleted and C keeps its 'done' status intact.
    """
    a = _make_classification("call mom", order=0, status="open")
    b = _make_classification("buy milk", order=1, status="open")
    c = _make_classification("draft memo", order=2, status="done")
    entry = _make_entry([a, b, c])
    _override_deps(app, entry)

    # User deletes middle row (b), keeps a and c.
    payload = {
        "categories": [
            {"id": str(a.id), "text": "call mom", "category": "TODO", "estimated_minutes": 10},
            {"id": str(c.id), "text": "draft memo", "category": "TODO", "estimated_minutes": 10},
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/entries/{entry.id}", json=payload)

    assert resp.status_code == 200
    # b was removed
    assert b not in entry.classifications
    # c (the originally "done" row) is still here, status intact
    assert c in entry.classifications
    assert c.status == "done"
    assert c.extracted_text == "draft memo"
    # And display_order was rewritten so c is now at index 1
    assert c.display_order == 1
    assert a.display_order == 0


@pytest.mark.asyncio
async def test_update_inserts_new_row_when_id_omitted(app):
    """Items without an id are treated as fresh inserts."""
    a = _make_classification("existing item", order=0, status="open")
    entry = _make_entry([a])
    _override_deps(app, entry)

    payload = {
        "categories": [
            {"id": str(a.id), "text": "existing item", "category": "TODO", "estimated_minutes": 10},
            {"text": "brand new", "category": "EXPERIMENT", "estimated_minutes": 5},
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/entries/{entry.id}", json=payload)

    assert resp.status_code == 200
    assert len(entry.classifications) == 2
    # Original row preserved
    assert a in entry.classifications
    # New row appended
    new = [c for c in entry.classifications if c is not a][0]
    assert new.extracted_text == "brand new"
    assert new.category == "EXPERIMENT"


@pytest.mark.asyncio
async def test_move_entry_updates_local_date_for_empty_target_day(app):
    """Moving an entry must update local_date, not just timestamps.

    The Day page filters by local_date. If PATCH only changes created_at, the
    entry still appears on the old day and an empty target day stays empty.
    """
    old_day = date(2026, 4, 5)
    new_day = date(2026, 4, 8)
    entry = _make_entry([])
    entry.created_at = datetime(2026, 4, 5, 18, 30, tzinfo=timezone.utc)
    entry.recorded_at = entry.created_at
    entry.local_date = old_day
    db = _override_deps(app, entry)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/entries/{entry.id}", json={"date": "2026-04-08"})

    assert resp.status_code == 200
    assert entry.local_date == new_day
    assert entry.created_at == datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    assert entry.recorded_at == datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    assert resp.json()["local_date"] == "2026-04-08"

    stale_query = db.execute.await_args_list[1].args[0]
    rendered_query = str(stale_query.compile(compile_kwargs={"literal_binds": True}))
    assert "audit_results.audit_date IN" in rendered_query
    assert "'2026-04-05'" in rendered_query
    assert "'2026-04-08'" in rendered_query
