"""
Unit tests for the worker's audio transcription loop.

All I/O (storage, transcription, DB) is mocked. Tests focus on the fast
transcript-save path and stale-job recovery.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.jobs import Job, JobStatus
from app.models.entry import Entry


def _make_entry(user_id=1, transcript="test transcript"):
    e = MagicMock(spec=Entry)
    e.id = uuid.uuid4()
    e.user_id = user_id
    e.raw_audio_key = f"audio/{user_id}/test.webm"
    e.raw_audio_download_url = None
    e.transcript = transcript
    e.duration_seconds = 60
    return e


def _make_job(entry_id=None):
    j = MagicMock(spec=Job)
    j.id = uuid.uuid4()
    j.entry_id = entry_id or uuid.uuid4()
    j.status = JobStatus.PROCESSING
    return j


def _standard_patches():
    return {
        "app.services.worker.queue_svc": MagicMock(
            mark_step=AsyncMock(),
            complete_job=AsyncMock(),
            fail_job=AsyncMock(),
        ),
        "app.services.worker.storage_svc": MagicMock(
            download_bytes=AsyncMock(return_value=b"fake audio bytes"),
        ),
        "app.services.worker.transcribe_audio": AsyncMock(return_value="some transcript"),
    }


def _mock_db(entry):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=entry)))
    db.added = []
    db.add = lambda obj: db.added.append(obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


async def _run_process_job(db, job):
    patches = _standard_patches()
    with patch("app.services.worker.queue_svc", patches["app.services.worker.queue_svc"]), \
         patch("app.services.worker.storage_svc", patches["app.services.worker.storage_svc"]), \
         patch("app.services.worker.transcribe_audio", patches["app.services.worker.transcribe_audio"]):
        from app.services.worker import _process_job
        await _process_job(db, job)


@pytest.mark.asyncio
async def test_worker_saves_transcript_without_classifying():
    entry = _make_entry()
    job = _make_job(entry_id=entry.id)
    db = _mock_db(entry)

    await _run_process_job(db, job)

    assert entry.transcript == "some transcript"
    assert not [obj for obj in db.added if obj.__class__.__name__ == "EntryClassification"]


@pytest.mark.asyncio
async def test_worker_completes_job_after_transcription():
    entry = _make_entry()
    job = _make_job(entry_id=entry.id)
    db = _mock_db(entry)

    await _run_process_job(db, job)

    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_worker_notification_reports_transcribed_entry():
    entry = _make_entry()
    job = _make_job(entry_id=entry.id)
    db = _mock_db(entry)

    await _run_process_job(db, job)

    notifications = [obj for obj in db.added if obj.__class__.__name__ == "Notification"]
    assert notifications
    assert notifications[-1].event_type == "entry.transcribed"


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
