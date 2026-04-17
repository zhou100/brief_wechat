"""
Unit tests for the worker's multi-entry classification loop.

All I/O (OpenAI, storage, DB) is mocked.
Tests focus on the classification insertion loop and stale-job recovery.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.jobs import Job, JobStatus
from app.models.entry import Entry
from app.models.classification import EntryClassification


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_entry(user_id=1, transcript="test transcript"):
    e = MagicMock(spec=Entry)
    e.id = uuid.uuid4()
    e.user_id = user_id
    e.raw_audio_key = f"audio/{user_id}/test.webm"
    e.transcript = transcript
    e.duration_seconds = 60
    return e


def _make_job(entry_id=None):
    j = MagicMock(spec=Job)
    j.id = uuid.uuid4()
    j.entry_id = entry_id or uuid.uuid4()
    j.status = JobStatus.PROCESSING
    return j


def _standard_patches(cat_results):
    """Return a dict of patches common to all _process_job tests."""
    return {
        "app.services.worker.queue_svc": MagicMock(
            mark_step=AsyncMock(),
            complete_job=AsyncMock(),
            fail_job=AsyncMock(),
        ),
        "app.services.worker.storage_svc": MagicMock(
            download_bytes=AsyncMock(return_value=b"fake audio bytes"),
        ),
        "app.services.worker.categorize_text": AsyncMock(return_value=cat_results),
        "app.services.worker.refine_transcript": AsyncMock(return_value="refined transcript"),
        "app.services.worker.transcribe_audio": AsyncMock(return_value="some transcript"),
    }


def _mock_db(entry):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=entry)))
    db.added = []
    original_add = db.add
    db.add = lambda obj: db.added.append(obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


async def _run_process_job(db, job, cat_results):
    patches = _standard_patches(cat_results)
    with patch("app.services.worker.queue_svc", patches["app.services.worker.queue_svc"]), \
         patch("app.services.worker.storage_svc", patches["app.services.worker.storage_svc"]), \
         patch("app.services.worker.categorize_text", patches["app.services.worker.categorize_text"]), \
         patch("app.services.worker.refine_transcript", patches["app.services.worker.refine_transcript"]), \
         patch("app.services.worker.transcribe_audio", patches["app.services.worker.transcribe_audio"]):
        from app.services.worker import _process_job
        await _process_job(db, job)


# ── Classification loop: correct number of rows ───────────────────────────────

@pytest.mark.asyncio
async def test_three_item_result_inserts_three_rows():
    """3-item categorization result → 3 EntryClassification rows added to db."""
    cat_results = [
        {"text": "Worked on dashboard", "category": "EARNING"},
        {"text": "Add voice replay experiment", "category": "EXPERIMENT"},
        {"text": "Write auth tests", "category": "TODO"},
    ]

    entry = _make_entry()
    job = _make_job(entry_id=entry.id)
    db = _mock_db(entry)

    await _run_process_job(db, job, cat_results)

    classification_rows = [o for o in db.added if isinstance(o, EntryClassification)]
    assert len(classification_rows) == 3


@pytest.mark.asyncio
async def test_display_order_is_sequential():
    """display_order values are 0, 1, 2 — not all 0."""
    cat_results = [
        {"text": "First", "category": "TODO"},
        {"text": "Second", "category": "EXPERIMENT"},
        {"text": "Third", "category": "REFLECTION"},
    ]

    entry = _make_entry()
    job = _make_job(entry_id=entry.id)
    db = _mock_db(entry)

    await _run_process_job(db, job, cat_results)

    rows = [o for o in db.added if isinstance(o, EntryClassification)]
    assert [r.display_order for r in rows] == [0, 1, 2]


@pytest.mark.asyncio
async def test_empty_categorization_fallback_inserts_one_reflection():
    """
    Fallback from categorize_text already returns [{"text": ..., "category": "REFLECTION"}],
    so the worker inserts exactly 1 row with category REFLECTION.
    """
    fallback = [{"text": "full transcript text", "category": "REFLECTION"}]

    entry = _make_entry(transcript="full transcript text")
    job = _make_job(entry_id=entry.id)
    db = _mock_db(entry)

    await _run_process_job(db, job, fallback)

    rows = [o for o in db.added if isinstance(o, EntryClassification)]
    assert len(rows) == 1
    assert rows[0].category == "REFLECTION"


# ── Stale-job recovery ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_job_recovery_fails_old_jobs():
    """_recover_stale_jobs marks PROCESSING jobs older than 5 min as failed."""
    from app.services.worker import _recover_stale_jobs

    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    stale_job = MagicMock(spec=Job)
    stale_job.id = uuid.uuid4()
    stale_job.status = JobStatus.PROCESSING
    stale_job.updated_at = stale_cutoff

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[stale_job]))))
    )
    db.commit = AsyncMock()

    with patch("app.services.worker.queue_svc") as mock_queue:
        mock_queue.fail_job = AsyncMock()
        await _recover_stale_jobs(db)

    mock_queue.fail_job.assert_called_once()
    call_args = mock_queue.fail_job.call_args
    assert call_args[0][1] == stale_job
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_stale_job_recovery_ignores_fresh_jobs():
    """_recover_stale_jobs does NOT fail jobs that are recent."""
    from app.services.worker import _recover_stale_jobs

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    db.commit = AsyncMock()

    with patch("app.services.worker.queue_svc") as mock_queue:
        mock_queue.fail_job = AsyncMock()
        await _recover_stale_jobs(db)

    mock_queue.fail_job.assert_not_called()
    db.commit.assert_not_called()
