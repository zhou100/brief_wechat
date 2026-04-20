import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    from app.routes.miniapp import router

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


def _classification(text, category="MAITAISHAO", status="open"):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.category = category
    item.extracted_text = text
    item.edited_text = None
    item.display_text = text
    item.display_order = 0
    item.estimated_minutes = None
    item.status = status
    return item


def _job(status="done"):
    job = MagicMock()
    job.status = status
    job.created_at = datetime(2026, 4, 18, 8, 0, tzinfo=timezone.utc)
    return job


def _entry(local_day, classifications):
    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.local_date = local_day
    entry.created_at = datetime(local_day.year, local_day.month, local_day.day, 8, 0, tzinfo=timezone.utc)
    entry.transcript = "今天讲了几件事。"
    entry.classifications = classifications
    entry.jobs = [_job()]
    return entry


def _audit_result(week_start, is_stale=False, report_json=None):
    ar = MagicMock()
    ar.id = uuid.uuid4()
    ar.audit_date = week_start
    ar.audit_type = "miniapp_weekly"
    ar.is_stale = is_stale
    ar.report_json = report_json or json.dumps({
        "title": "上个礼拜的事体",
        "week_start": week_start.isoformat(),
        "week_end": "2026-04-19",
        "date_range": "4月13日到4月19日",
        "opening": "这一礼拜，主要讲到买汰烧。",
        "main_things": [{"title": "买汰烧", "body": "你提到买菜。"}],
        "remember_items": [],
        "family_share_text": "上个礼拜主要讲了买汰烧。",
        "next_week_nudge": "想到事情就直接讲。",
        "generated_at": "2026-04-19T08:00:00+00:00",
        "cached": True,
    }, ensure_ascii=False)
    return ar


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def unique(self):
        return self

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None

    def scalar(self):
        return self.values[0] if self.values else None


class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _ScalarResult(self.values)

    def scalar(self):
        return self.values[0] if self.values else None


def _db_no_cache(entries):
    """DB with no cached weekly record — returns empty for cache queries, entries for fetch."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    # fresh cache miss, stale cache miss, count=0, entries fetch
    db.execute = AsyncMock(side_effect=[
        _Result([]),   # fresh cache lookup
        _Result([]),   # stale cache lookup
        _Result([0]),  # regen_count
        _Result(entries),  # entries fetch
    ])
    return db


def _db_with_fresh_cache(cached_ar):
    """DB with a fresh (non-stale) cached record."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    # fresh cache hit, count=1
    db.execute = AsyncMock(side_effect=[
        _Result([cached_ar]),  # fresh cache lookup
        _Result([1]),          # regen_count
    ])
    return db


def _db_with_stale_cache(stale_ar, entries):
    """DB with only a stale cached record — POST without force should regenerate."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    # fresh miss, stale hit, count=1 (for GET path)
    # For POST path: fresh miss, stale hit, count=1, entries fetch
    db.execute = AsyncMock(side_effect=[
        _Result([]),         # fresh cache lookup
        _Result([stale_ar]), # stale cache lookup
        _Result([1]),        # regen_count
        _Result(entries),    # entries fetch
    ])
    return db


# ── Existing 3 tests (updated for new DB call pattern) ─────────────────────

@pytest.mark.asyncio
async def test_weekly_suggestion_hidden_with_fewer_than_three_entries(app):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result([
            _entry(date(2026, 4, 13), [_classification("买菜")]),
            _entry(date(2026, 4, 14), [_classification("烧菜")]),
        ]),
    ])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/miniapp/weekly/suggestion?week_start=2026-04-13")

    assert resp.status_code == 200
    assert resp.json()["show"] is False
    assert resp.json()["entry_count"] == 2
    assert "has_report" not in resp.json()


@pytest.mark.asyncio
async def test_weekly_suggestion_shows_for_three_entries(app):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result([
            _entry(date(2026, 4, 13), [_classification("买菜")]),
            _entry(date(2026, 4, 14), [_classification("烧菜")]),
            _entry(date(2026, 4, 15), [_classification("问药", "TODO")]),
        ]),
    ])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/miniapp/weekly/suggestion?week_start=2026-04-16")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["show"] is True
    assert payload["week_start"] == "2026-04-13"
    assert payload["week_end"] == "2026-04-19"


@pytest.mark.asyncio
async def test_create_weekly_summary_persists_miniapp_shape(app):
    entries = [
        _entry(date(2026, 4, 13), [_classification("买菜")]),
        _entry(date(2026, 4, 14), [_classification("烧菜")]),
        _entry(date(2026, 4, 15), [_classification("问一下药还有没有", "TODO")]),
    ]
    db = _db_no_cache(entries)
    _override_auth(app)
    _override_db(app, db)

    with patch("app.routes.miniapp._generate_opening_sentence", new=AsyncMock(return_value="这一礼拜很充实。")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/miniapp/weekly", json={"week_start": "2026-04-13"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["title"] == "上个礼拜的事体"
    assert payload["remember_items"] == ["问一下药还有没有"]
    assert payload["family_share_text"]
    assert payload["stale"] is False
    assert payload["regen_count"] == 1
    db.add.assert_called_once()
    saved = db.add.call_args.args[0]
    assert saved.audit_type == "miniapp_weekly"
    assert json.loads(saved.report_json)["title"] == "上个礼拜的事体"
    db.commit.assert_awaited_once()


# ── 12 new tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_weekly_returns_cached_when_fresh(app):
    """POST /weekly returns cached record without generating when fresh cache exists."""
    cached_ar = _audit_result(date(2026, 4, 13))
    db = _db_with_fresh_cache(cached_ar)
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/miniapp/weekly", json={"week_start": "2026-04-13"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["title"] == "上个礼拜的事体"
    assert payload["cached"] is True
    assert payload["stale"] is False
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_weekly_400_too_few_entries(app):
    """POST /weekly returns 400 when fewer than 3 completed entries."""
    entries = [
        _entry(date(2026, 4, 13), [_classification("买菜")]),
        _entry(date(2026, 4, 14), [_classification("烧菜")]),
    ]
    db = _db_no_cache(entries)
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/miniapp/weekly", json={"week_start": "2026-04-13"})

    assert resp.status_code == 400
    assert "3" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_weekly_summary_404_when_not_cached(app):
    """GET /weekly/{week_start} returns 404 when no record exists."""
    db = AsyncMock()
    # fresh miss, stale miss
    db.execute = AsyncMock(side_effect=[
        _Result([]),  # fresh cache lookup
        _Result([]),  # stale cache lookup
    ])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/miniapp/weekly/2026-04-13")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_weekly_summary_returns_fresh(app):
    """GET /weekly/{week_start} returns 200 with stale=False for fresh record."""
    cached_ar = _audit_result(date(2026, 4, 13), is_stale=False)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result([cached_ar]),  # fresh cache hit
        _Result([1]),          # regen_count
    ])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/miniapp/weekly/2026-04-13")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["stale"] is False
    assert payload["cached"] is True
    assert payload["regen_count"] == 1


@pytest.mark.asyncio
async def test_get_weekly_summary_returns_stale_true(app):
    """GET /weekly/{week_start} returns stale=True when only stale record exists."""
    stale_ar = _audit_result(date(2026, 4, 13), is_stale=True)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _Result([]),        # fresh cache miss
        _Result([stale_ar]),  # stale cache hit
        _Result([1]),       # regen_count
    ])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/miniapp/weekly/2026-04-13")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["stale"] is True
    assert payload["cached"] is True


@pytest.mark.asyncio
async def test_invalid_week_start_returns_400_get(app):
    """GET /weekly/{week_start} returns 400 for invalid date format."""
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/miniapp/weekly/not-a-date")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_week_start_returns_400_post(app):
    """POST /weekly returns 400 for invalid week_start format."""
    db = AsyncMock()
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/miniapp/weekly", json={"week_start": "not-a-date"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_mark_weekly_audits_stale(app):
    """_mark_weekly_audits_stale sets is_stale=True on active weekly records."""
    from app.routes.miniapp import _mark_weekly_audits_stale

    audit = MagicMock()
    audit.is_stale = False
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Result([audit]))

    await _mark_weekly_audits_stale(db, user_id=1, local_date=date(2026, 4, 15))

    assert audit.is_stale is True


@pytest.mark.asyncio
async def test_force_regen_429_at_limit(app):
    """POST /weekly with force=True returns 429 when regen_count >= 5."""
    db = AsyncMock()
    # force=True skips cache check — first call is regen_count
    db.execute = AsyncMock(side_effect=[
        _Result([5]),  # regen_count
    ])
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/miniapp/weekly", json={"week_start": "2026-04-13", "force": True})

    assert resp.status_code == 429
    assert "这个礼拜" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_force_regen_creates_new_record(app):
    """POST /weekly with force=True generates a new record and keeps stale ones."""
    entries = [
        _entry(date(2026, 4, 13), [_classification("买菜")]),
        _entry(date(2026, 4, 14), [_classification("烧菜")]),
        _entry(date(2026, 4, 15), [_classification("问药", "TODO")]),
    ]
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    # count=2, entries fetch
    db.execute = AsyncMock(side_effect=[
        _Result([2]),     # regen_count
        _Result(entries), # entries fetch
    ])
    _override_auth(app)
    _override_db(app, db)

    with patch("app.routes.miniapp._generate_opening_sentence", new=AsyncMock(return_value="这一礼拜很充实。")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/miniapp/weekly", json={"week_start": "2026-04-13", "force": True})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["stale"] is False
    assert payload["regen_count"] == 3
    db.add.assert_called_once()
    saved = db.add.call_args.args[0]
    assert saved.is_stale is False
    assert saved.audit_type == "miniapp_weekly"


@pytest.mark.asyncio
async def test_regen_count_in_response(app):
    """regen_count reflects the total number of weekly records for this user×week."""
    entries = [
        _entry(date(2026, 4, 13), [_classification("买菜")]),
        _entry(date(2026, 4, 14), [_classification("烧菜")]),
        _entry(date(2026, 4, 15), [_classification("问药")]),
    ]
    db = _db_no_cache(entries)
    _override_auth(app)
    _override_db(app, db)

    with patch("app.routes.miniapp._generate_opening_sentence", new=AsyncMock(return_value="这一礼拜很充实。")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/miniapp/weekly", json={"week_start": "2026-04-13"})

    assert resp.status_code == 200
    assert resp.json()["regen_count"] == 1


@pytest.mark.asyncio
async def test_cached_stale_field_not_stored_in_report_json(app):
    """stale and regen_count fields are not stored inside report_json."""
    entries = [
        _entry(date(2026, 4, 13), [_classification("买菜")]),
        _entry(date(2026, 4, 14), [_classification("烧菜")]),
        _entry(date(2026, 4, 15), [_classification("问药")]),
    ]
    db = _db_no_cache(entries)
    _override_auth(app)
    _override_db(app, db)

    with patch("app.routes.miniapp._generate_opening_sentence", new=AsyncMock(return_value="这一礼拜很充实。")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/miniapp/weekly", json={"week_start": "2026-04-13"})

    saved = db.add.call_args.args[0]
    stored = json.loads(saved.report_json)
    assert "stale" not in stored
    assert "regen_count" not in stored
