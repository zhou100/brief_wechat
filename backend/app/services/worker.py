"""
Audio processing worker.

Runs as a separate process alongside the FastAPI server.
Polls the jobs table, processes PENDING jobs through the pipeline:
  1. Download audio from object storage
  2. Transcribe via iFlytek
  3. Save transcript
  4. Write notification row (Supabase Realtime delivers to frontend)

Start with: python -m app.services.worker
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import async_session
from ..models.entry import Entry
from ..models.jobs import Job, JobStatus
from ..models.notification import Notification
from ..services import queue as queue_svc
from ..services import storage as storage_svc
from ..services.transcription import transcribe_audio

logger = logging.getLogger(__name__)

# Jobs stuck in PROCESSING longer than this are considered dead and will be failed.
_STALE_JOB_THRESHOLD = timedelta(minutes=5)

# Notification rows are transient pub/sub events consumed by Supabase Realtime.
# After the frontend has rendered the update, rows have no further value, so we
# delete anything older than this to keep the table bounded.
_NOTIFICATION_TTL = timedelta(hours=24)
_NOTIFICATION_CLEANUP_INTERVAL = timedelta(hours=1)


async def _recover_stale_jobs(db: AsyncSession) -> None:
    """
    At worker startup, fail any PROCESSING jobs that have been stuck for more than
    _STALE_JOB_THRESHOLD. This handles the case where the worker crashed mid-pipeline
    and left jobs in PROCESSING with no WebSocket event ever sent.
    """
    cutoff = datetime.now(timezone.utc) - _STALE_JOB_THRESHOLD
    result = await db.execute(
        select(Job).where(
            Job.status == JobStatus.PROCESSING,
            Job.updated_at < cutoff,
        )
    )
    stale_jobs = result.scalars().all()
    for job in stale_jobs:
        logger.warning(f"Recovering stale job {job.id} (stuck since {job.updated_at})")
        await queue_svc.fail_job(db, job, "stale_job_recovered: worker restarted while job was processing")
    if stale_jobs:
        await db.commit()
        logger.info(f"Recovered {len(stale_jobs)} stale job(s)")


async def _process_job(db: AsyncSession, job: Job) -> None:
    """Run one entry through the full pipeline."""
    job_started = time.perf_counter()
    result = await db.execute(select(Entry).where(Entry.id == job.entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        await queue_svc.fail_job(db, job, "entry_not_found: entry not found")
        return

    try:
        # ── Step 1: Transcribe ───────────────────────────────────────────────
        await queue_svc.mark_step(db, job, "transcribing")
        await db.commit()

        try:
            download_started = time.perf_counter()
            audio_bytes = await storage_svc.download_bytes(
                entry.raw_audio_key,
                entry.raw_audio_download_url,
            )
            logger.info(
                "Job %s audio downloaded: %.1f KB in %.2fs",
                job.id,
                len(audio_bytes) / 1024,
                time.perf_counter() - download_started,
            )
        except Exception as exc:
            raise RuntimeError(f"audio_download_failed: {exc}") from exc

        suffix = os.path.splitext(entry.raw_audio_key)[1] or ".mp3"
        try:
            transcription_started = time.perf_counter()
            raw_transcript = await transcribe_audio(
                audio_bytes,
                suffix,
                source_url=entry.raw_audio_download_url,
            )
            logger.info(
                "Job %s transcribed in %.2fs (%s chars): %s...",
                job.id,
                time.perf_counter() - transcription_started,
                len(raw_transcript),
                raw_transcript[:120],
            )
        except Exception as exc:
            raise RuntimeError(f"xfyun_transcription_failed: {exc}") from exc

        # ── Handle empty/silent audio ────────────────────────────────────────
        if not raw_transcript or not raw_transcript.strip():
            logger.info(f"Job {job.id}: empty transcript, skipping refinement and classification")
            entry.transcript = ""
            await db.flush()
            await queue_svc.complete_job(db, job)
            await db.commit()

            db.add(Notification(
                user_id=entry.user_id,
                event_type="entry.classified",
                payload_json=json.dumps({
                    "entry_id": str(entry.id),
                    "transcript": "",
                    "categories": [],
                }),
            ))
            await db.commit()
            return

        # Keep capture fast: refinement and categorization run only when the
        # miniapp user taps "一键理清爽".
        entry.transcript = raw_transcript.strip()
        await db.flush()
        logger.info(f"Stored transcript: {entry.transcript[:120]}...")

        await queue_svc.complete_job(db, job)
        await db.commit()

        logger.info(
            f"Job {job.id} done in {time.perf_counter() - job_started:.2f}s: entry={entry.id} "
            "transcript_saved=true"
        )

        # ── Step 4: Write notification (Supabase Realtime delivers to frontend)
        db.add(Notification(
            user_id=entry.user_id,
            event_type="entry.transcribed",
            payload_json=json.dumps({
                "entry_id": str(entry.id),
                "transcript": entry.transcript,
                "categories": [],
            }),
        ))
        await db.commit()

    except Exception as exc:
        logger.error(f"Job {job.id} failed: {exc}", exc_info=True)
        await db.rollback()

        # Re-open session to record failure
        async with async_session() as db2:
            result2 = await db2.execute(select(Job).where(Job.id == job.id))
            job2 = result2.scalar_one_or_none()
            if job2:
                await queue_svc.fail_job(db2, job2, str(exc))
                await db2.commit()

        try:
            async with async_session() as db3:
                r = await db3.execute(select(Entry).where(Entry.id == job.entry_id))
                e = r.scalar_one_or_none()
                if e:
                    # Do not leak raw exception text to the client — full
                    # traceback is already logged above via exc_info=True.
                    db3.add(Notification(
                        user_id=e.user_id,
                        event_type="entry.failed",
                        payload_json=json.dumps({
                            "entry_id": str(job.entry_id),
                            "error": "Processing failed. Please try again.",
                        }),
                    ))
                    await db3.commit()
        except Exception:
            pass


async def _cleanup_old_notifications(db: AsyncSession) -> None:
    """Delete notification rows older than _NOTIFICATION_TTL."""
    cutoff = datetime.now(timezone.utc) - _NOTIFICATION_TTL
    result = await db.execute(
        delete(Notification).where(Notification.created_at < cutoff)
    )
    await db.commit()
    if result.rowcount:
        logger.info(f"Pruned {result.rowcount} old notification row(s)")


async def run_worker(poll_interval: float = 2.0) -> None:
    """
    Main worker loop. Polls for PENDING jobs and processes them one at a time.
    On startup, recovers any jobs stuck in PROCESSING from a previous crash.
    Run multiple instances to scale throughput.
    """
    logger.info("Worker started — recovering stale jobs and polling...")
    async with async_session() as db:
        await _recover_stale_jobs(db)

    next_cleanup = datetime.now(timezone.utc)

    while True:
        try:
            now = datetime.now(timezone.utc)
            if now >= next_cleanup:
                async with async_session() as db:
                    await _cleanup_old_notifications(db)
                next_cleanup = now + _NOTIFICATION_CLEANUP_INTERVAL

            async with async_session() as db:
                job = await queue_svc.dequeue(db)
                if job:
                    await _process_job(db, job)
                else:
                    await asyncio.sleep(poll_interval)
        except Exception as exc:
            logger.error(f"Worker loop error: {exc}", exc_info=True)
            await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
