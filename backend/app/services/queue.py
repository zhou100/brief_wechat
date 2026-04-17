"""
SQL-backed job queue for the audio processing pipeline.

Uses SELECT FOR UPDATE SKIP LOCKED so multiple workers can run safely
without a separate message broker.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.jobs import Job, JobStatus

logger = logging.getLogger(__name__)


async def enqueue(db: AsyncSession, entry_id, user_id: int) -> Job:
    """Create a PENDING job for the given entry."""
    job = Job(entry_id=entry_id, user_id=user_id, status=JobStatus.PENDING, step="queued")
    db.add(job)
    await db.flush()
    logger.info(f"Enqueued job {job.id} for entry {entry_id}")
    return job


async def dequeue(db: AsyncSession) -> Job | None:
    """
    Claim the next PENDING job atomically.
    Uses SKIP LOCKED so concurrent workers don't block each other.
    """
    result = await db.execute(
        select(Job)
        .where(Job.status == JobStatus.PENDING)
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job:
        job.status = JobStatus.PROCESSING
        job.step = "starting"
        await db.flush()
    return job


async def mark_step(db: AsyncSession, job: Job, step: str) -> None:
    """Record the current pipeline step on the job record."""
    job.step = step
    await db.flush()


async def complete_job(db: AsyncSession, job: Job) -> None:
    job.status = JobStatus.DONE
    job.step = "complete"
    await db.flush()


async def fail_job(db: AsyncSession, job: Job, error: str) -> None:
    job.status = JobStatus.FAILED
    job.step = "failed"
    job.error = error[:2000]  # cap error length
    await db.flush()


async def get_job_for_entry(db: AsyncSession, entry_id) -> Job | None:
    """Return the most recent job for an entry (for status polling)."""
    result = await db.execute(
        select(Job)
        .where(Job.entry_id == entry_id)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
