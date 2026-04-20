import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import selectinload

from app.models.entry import Entry


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


def _classification(text="买点青菜", status="open", category="MAITAISHAO"):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.entry_id = uuid.uuid4()
    item.category = category
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
    job = MagicMock()
    job.status = "done"
    job.created_at = datetime(2026, 4, 18, 8, 1, tzinfo=timezone.utc)
    entry.jobs = [job]
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


@pytest.mark.asyncio
async def test_reclassify_day_replaces_items_with_model_version(app):
    old_item = _classification(text="整段错进感悟", category="REFLECTION")
    entry = _entry(old_item)

    entries_result = MagicMock()
    entries_result.scalars.return_value.unique.return_value.all.return_value = [entry]
    stale_result = MagicMock()
    stale_result.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[entries_result, stale_result])
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    _override_auth(app)
    _override_db(app, db)

    with patch(
        "app.routes.miniapp.categorize_text",
        AsyncMock(return_value=[
            {
                "text": "出门买菜做饭",
                "category": "MAITAISHAO",
                "estimated_minutes": None,
                "model": "deepseek-v3.2",
            }
        ]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/miniapp/daily/2026-04-18/reclassify")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "reclassified": 1}
    db.delete.assert_awaited_once_with(old_item)
    added = db.add.call_args.args[0]
    assert added.category == "MAITAISHAO"
    assert added.extracted_text == "出门买菜做饭"
    assert added.model_version == "deepseek-v3.2"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reclassify_day_eager_loads_jobs_for_completed_filter(app):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=AssertionError("stop after statement inspection"))

    _override_auth(app)
    _override_db(app, db)

    with pytest.raises(AssertionError, match="stop after statement inspection"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/miniapp/daily/2026-04-18/reclassify")

    stmt = db.execute.call_args.args[0]
    expected_jobs_option = selectinload(Entry.jobs)
    assert any(
        option.path == expected_jobs_option.path
        for option in stmt._with_options
    )


@pytest.mark.asyncio
async def test_reclassify_day_returns_503_when_classifier_unavailable(app):
    old_item = _classification(text="整段错进感悟", category="REFLECTION")
    entry = _entry(old_item)

    entries_result = MagicMock()
    entries_result.scalars.return_value.unique.return_value.all.return_value = [entry]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=entries_result)
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()

    _override_auth(app)
    _override_db(app, db)

    with patch(
        "app.routes.miniapp.categorize_text",
        AsyncMock(side_effect=RuntimeError("classification_api_failed: upstream timeout")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/miniapp/daily/2026-04-18/reclassify")

    assert resp.status_code == 503
    assert resp.json() == {"detail": "分类服务暂时不可用，请稍后重试。"}
    db.rollback.assert_awaited_once()
    db.delete.assert_not_awaited()
    db.flush.assert_not_awaited()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


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


def test_daily_result_groups_done_categories_before_followups():
    from app.routes.miniapp import _daily_result

    earning = _classification(text="上午办完证件", category="EARNING")
    todo = _classification(text="明天提醒我买菜", category="TODO")
    reflection = _classification(text="今天安排太碎了", category="REFLECTION")
    family = _classification(text="下午接小孩回家", category="FAMILY")
    entry = _entry(earning)
    entry.classifications = [todo, reflection, earning, family]

    result = _daily_result([entry], "2026-04-18")

    assert [group["category"] for group in result.category_groups] == [
        "EARNING",
        "FAMILY",
        "TODO",
        "REFLECTION",
    ]
    assert [group["label"] for group in result.category_groups] == [
        "办事体",
        "照顾家人",
        "还要做",
        "感悟",
    ]
