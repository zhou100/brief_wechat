import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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


def _classification(text="买点青菜", status="open"):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.entry_id = uuid.uuid4()
    item.category = "MAITAISHAO"
    item.extracted_text = text
    item.edited_text = None
    item.display_text = text
    item.display_order = 0
    item.estimated_minutes = None
    item.status = status
    item.user_override = False
    return item


def _entry(item):
    entry = MagicMock()
    entry.id = item.entry_id
    entry.local_date = date(2026, 4, 18)
    entry.created_at = datetime(2026, 4, 18, 8, 0, tzinfo=timezone.utc)
    entry.raw_audio_key = "cloud://env/audio.mp3"
    entry.transcript = "今天买点青菜。"
    entry.classifications = [item]
    return entry


def _db_for_item(row):
    db = AsyncMock()
    result = MagicMock()
    result.one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_update_miniapp_item_text(app):
    item = _classification()
    entry = _entry(item)
    db = _db_for_item((item, entry))
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/miniapp/items/{item.id}", json={"edited_text": "买两把青菜"})

    assert resp.status_code == 200
    assert item.edited_text == "买两把青菜"
    assert item.user_override is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_miniapp_item_dismisses_only_that_item(app):
    item = _classification()
    entry = _entry(item)
    db = _db_for_item((item, entry))
    _override_auth(app)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/miniapp/items/{item.id}")

    assert resp.status_code == 204
    assert item.status == "dismissed"
    assert item.user_override is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_miniapp_item_cross_user_returns_404(app):
    db = _db_for_item(None)
    _override_auth(app, user_id=2)
    _override_db(app, db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/miniapp/items/{uuid.uuid4()}", json={"edited_text": "别人家的事"})

    assert resp.status_code == 404


def test_daily_result_filters_dismissed_items():
    from app.routes.miniapp import _daily_result

    kept = _classification(text="买点青菜", status="open")
    hidden = _classification(text="不要显示", status="dismissed")
    entry = _entry(kept)
    entry.classifications = [kept, hidden]

    result = _daily_result([entry], "2026-04-18")

    assert result.category_groups[0]["items"] == [
        {
            "id": str(kept.id),
            "text": "买点青菜",
            "category": "MAITAISHAO",
            "estimated_minutes": None,
        }
    ]
    assert result.entries[0]["categories"] == [
        {
            "id": str(kept.id),
            "text": "买点青菜",
            "category": "MAITAISHAO",
            "estimated_minutes": None,
        }
    ]
