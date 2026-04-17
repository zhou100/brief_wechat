"""
/api/v1/entries — Two-phase upload flow + audit endpoint.

Phase 1: POST /entries/presign
  → client receives a presigned PUT URL and an entry_id
  → client uploads audio directly to object storage (never transits the app server)

Phase 2: POST /entries/{id}/submit
  → app creates the Entry row and enqueues a processing job
  → client receives job_id for status polling / Realtime

Status polling: GET /entries/{id}/status
Listing:        GET /entries/
Audit:          POST /entries/audit
"""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from openai import AsyncOpenAI
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, or_, and_, case, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import get_db
from ...models.classification import EntryClassification
from ...models.entry import Entry
from ...models.user import User
from ...models.jobs import Job, JobStatus
from ...models.audit_result import AuditResult
from ...models.weekly_theme import WeeklyTheme
from ...services import queue as queue_svc
from ...services import storage as storage_svc
from ...settings import settings
from ...services.categorization import categorize_text
from ...utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/entries", tags=["entries"])

_openai: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai


# ── Schemas ───────────────────────────────────────────────────────────────────

class PresignResponse(BaseModel):
    entry_id: str
    upload_url: str
    audio_key: str


class SubmitRequest(BaseModel):
    audio_key: str                          # must match the key from presign
    recorded_at: Optional[datetime] = None  # client-side timestamp
    duration_seconds: Optional[int] = None
    local_date: Optional[str] = None        # YYYY-MM-DD in user's local timezone


class SubmitResponse(BaseModel):
    entry_id: str
    job_id: str


VALID_CATEGORIES = {"EARNING", "LEARNING", "RELAXING", "FAMILY", "TODO", "EXPERIMENT", "REFLECTION", "TIME_RECORD"}
LEGACY_CATEGORY_MAP = {"IDEA": "EXPERIMENT", "THOUGHT": "REFLECTION"}
ALL_VALID_CATEGORIES = VALID_CATEGORIES | set(LEGACY_CATEGORY_MAP.keys())

# Activity categories count toward time breakdown; capture categories are follow-up items
ACTIVITY_CATEGORIES = {"EARNING", "LEARNING", "RELAXING", "FAMILY", "TIME_RECORD"}
CAPTURE_CATEGORIES = {"TODO", "EXPERIMENT", "REFLECTION"}


def _normalize_category(category: str) -> str:
    return LEGACY_CATEGORY_MAP.get(category, category)


def _category_item_from_classification(c: EntryClassification) -> "CategoryItem":
    return CategoryItem(
        id=str(c.id),
        text=c.display_text,
        category=_normalize_category(c.category),
        estimated_minutes=c.estimated_minutes,
    )


class CategoryItem(BaseModel):
    id: Optional[str] = None
    text: Optional[str]
    category: str
    estimated_minutes: Optional[int] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        normalized = _normalize_category(v)
        if normalized not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {ALL_VALID_CATEGORIES}")
        return normalized

    @field_validator("estimated_minutes")
    @classmethod
    def validate_minutes(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 1440):
            raise ValueError("estimated_minutes must be 0-1440")
        return v


class EntryStatusResponse(BaseModel):
    entry_id: str
    job_id: Optional[str]
    status: str       # pending | processing | done | failed | unknown
    step: Optional[str]
    transcript: Optional[str]
    categories: List[CategoryItem]


class EntryItem(BaseModel):
    id: str
    transcript: Optional[str]
    recorded_at: Optional[str]
    created_at: str
    local_date: Optional[str] = None
    match_sources: Optional[List[str]] = None
    duration_seconds: Optional[int]
    categories: List[CategoryItem]


class EntryListResponse(BaseModel):
    items: List[EntryItem]
    total: int
    skip: int
    limit: int
    activity_breakdown: Optional[Dict[str, float]] = None
    capture_counts: Optional[Dict[str, int]] = None


class EntryUpdateRequest(BaseModel):
    transcript: Optional[str] = None
    categories: Optional[List[CategoryItem]] = None
    date: Optional[str] = None  # YYYY-MM-DD — moves entry to this day


class AuditRequest(BaseModel):
    date: str   # YYYY-MM-DD (UTC)
    regenerate: bool = False  # force re-generation even if cached


class AuditResponse(BaseModel):
    entries: int
    breakdown: Dict[str, float]
    approximate: bool = False  # True if some estimated_minutes were null (filled with avg)
    audit_text: Optional[str]
    report_json: Optional[Dict[str, Any]] = None  # structured 4-section weekly report
    generated_at: Optional[str]
    cached: bool = False
    message: Optional[str] = None
    week_start: Optional[str] = None
    week_end: Optional[str] = None
    days_covered: Optional[int] = None
    new_themes: Optional[List[Dict[str, Any]]] = None


def _entry_item_from_entry(entry: Entry) -> EntryItem:
    return EntryItem(
        id=str(entry.id),
        transcript=entry.transcript,
        recorded_at=entry.recorded_at.isoformat() if entry.recorded_at else None,
        created_at=entry.created_at.isoformat(),
        local_date=entry.local_date.isoformat() if entry.local_date else None,
        duration_seconds=entry.duration_seconds,
        categories=[_category_item_from_classification(c) for c in entry.classifications],
    )


def _search_match_sources(entry: Entry, query_text: str) -> List[str]:
    lowered_query = query_text.strip().lower()
    if not lowered_query:
        return []

    sources: List[str] = []
    if entry.transcript and lowered_query in entry.transcript.lower():
        sources.append("transcript")

    category_line_matched = False
    category_name_matched = False
    for classification in entry.classifications:
        extracted = classification.extracted_text or ""
        edited = classification.edited_text or ""
        if (extracted and lowered_query in extracted.lower()) or (edited and lowered_query in edited.lower()):
            category_line_matched = True
        if classification.category and lowered_query in classification.category.lower():
            category_name_matched = True

    if category_line_matched:
        sources.append("category_line")
    if category_name_matched:
        sources.append("category_name")
    return sources


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/presign", response_model=PresignResponse)
async def presign_upload(
    content_type: str = "audio/webm",
    current_user: User = Depends(get_current_user),
):
    """
    Generate a presigned PUT URL for direct client-to-storage audio upload.
    The client should PUT the audio file to upload_url, then call /submit.
    """
    entry_id = str(uuid.uuid4())
    suffix = _content_type_to_suffix(content_type)
    audio_key = storage_svc.make_audio_key(current_user.id, entry_id, suffix)
    upload_url = await storage_svc.generate_presigned_put(audio_key, content_type)
    return PresignResponse(entry_id=entry_id, upload_url=upload_url, audio_key=audio_key)


@router.post("/{entry_id}/submit", response_model=SubmitResponse)
async def submit_entry(
    entry_id: str,
    body: SubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Register the entry and enqueue it for async processing.
    Call this after the client has successfully PUT audio to the presign URL.
    """
    try:
        entry_uuid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry_id")

    # Verify the audio_key belongs to this user
    expected_prefix = f"audio/{current_user.id}/"
    if not body.audio_key.startswith(expected_prefix):
        raise HTTPException(status_code=400, detail="audio_key does not match user")

    # Compute local_date: prefer explicit value, fallback to recorded_at date, then UTC today
    if body.local_date:
        try:
            entry_local_date = datetime.strptime(body.local_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid local_date format, use YYYY-MM-DD")
    elif body.recorded_at:
        entry_local_date = body.recorded_at.date()
    else:
        entry_local_date = datetime.now(timezone.utc).date()

    entry = Entry(
        id=entry_uuid,
        user_id=current_user.id,
        raw_audio_key=body.audio_key,
        recorded_at=body.recorded_at,
        duration_seconds=body.duration_seconds,
        local_date=entry_local_date,
    )
    db.add(entry)
    await db.flush()

    # Invalidate cached audits for this local date (new entry may change breakdown)
    # Invalidate both daily (keyed on exact date) and weekly (keyed on Monday)
    weekly_monday = _current_week_start(entry_local_date)
    stale_result = await db.execute(
        select(AuditResult).where(
            AuditResult.user_id == current_user.id,
            AuditResult.audit_date.in_([entry_local_date, weekly_monday]),
            AuditResult.is_stale.is_(False),
        )
    )
    for ar in stale_result.scalars().all():
        ar.is_stale = True

    job = await queue_svc.enqueue(db, entry_uuid, current_user.id)
    await db.commit()

    logger.info(f"Entry {entry_id} submitted, job {job.id} enqueued")
    return SubmitResponse(entry_id=entry_id, job_id=str(job.id))


@router.get("/{entry_id}/status", response_model=EntryStatusResponse)
async def get_entry_status(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll the processing status of an entry."""
    try:
        entry_uuid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry_id")

    result = await db.execute(
        select(Entry)
        .options(selectinload(Entry.classifications))
        .where(Entry.id == entry_uuid, Entry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    job = await queue_svc.get_job_for_entry(db, entry_uuid)

    return EntryStatusResponse(
        entry_id=entry_id,
        job_id=str(job.id) if job else None,
        status=job.status.value if job and hasattr(job.status, "value") else (job.status if job else "unknown"),
        step=job.step if job else None,
        transcript=entry.transcript,
        categories=[_category_item_from_classification(c) for c in entry.classifications],
    )


@router.get("/active-dates", response_model=List[str])
async def get_active_dates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return sorted list of YYYY-MM-DD dates on which the user has entries."""
    effective_date = func.coalesce(Entry.local_date, func.date(Entry.created_at))
    result = await db.execute(
        select(effective_date.label("d"))
        .join(Job, Job.entry_id == Entry.id)
        .where(
            Entry.user_id == current_user.id,
            Job.status != JobStatus.FAILED,
        )
        .group_by(effective_date)
        .order_by(effective_date.desc())
    )
    return [str(row[0]) for row in result.all()]


@router.get("/", response_model=EntryListResponse)
async def list_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    date: Optional[str] = Query(None, description="Filter by local date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated list of the user's entries, newest first. Optionally filter by date."""
    base_filters = [Entry.user_id == current_user.id, Job.status != JobStatus.FAILED]

    # Optional date filter (uses local_date column)
    if date:
        try:
            filter_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
        base_filters.append(_date_match(filter_date))

    total_result = await db.execute(
        select(func.count(Entry.id)).join(Job, Job.entry_id == Entry.id).where(*base_filters)
    )
    total = total_result.scalar()

    result = await db.execute(
        select(Entry)
        .join(Job, Job.entry_id == Entry.id)
        .options(selectinload(Entry.classifications))
        .where(*base_filters)
        .order_by(Entry.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    entries = result.scalars().all()

    items = [_entry_item_from_entry(e) for e in entries]

    # Compute server-side breakdown when date filter is present (avoids pagination truncation)
    activity_breakdown = None
    capture_counts = None
    if date and entries:
        # Fetch ALL classifications for this user+date (not paginated)
        all_cls_result = await db.execute(
            select(EntryClassification)
            .join(Entry, EntryClassification.entry_id == Entry.id)
            .join(Job, Job.entry_id == Entry.id)
            .where(
                Entry.user_id == current_user.id,
                _date_match(filter_date),
                Job.status != JobStatus.FAILED,
            )
        )
        all_classifications = all_cls_result.scalars().all()
        activity_breakdown, _ = _compute_activity_breakdown(all_classifications)
        capture_counts = _compute_capture_counts(all_classifications)

    return EntryListResponse(
        items=items, total=total, skip=skip, limit=limit,
        activity_breakdown=activity_breakdown, capture_counts=capture_counts,
    )


@router.get("/search", response_model=EntryListResponse)
async def search_entries(
    q: str = Query(..., min_length=2, max_length=200, description="Search past records"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="Filter by category"),
    date_from: Optional[str] = Query(None, description="Filter from local date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Filter to local date YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search the user's entries by transcript and classification content."""
    query_text = q.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    if len(query_text) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")

    normalized_category = None
    if category:
        try:
            normalized_category = _normalize_category(category)
        except Exception:
            normalized_category = category
        if normalized_category not in VALID_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"category must be one of {sorted(VALID_CATEGORIES)}")

    parsed_date_from = None
    parsed_date_to = None
    if date_from:
        try:
            parsed_date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format, use YYYY-MM-DD")
    if date_to:
        try:
            parsed_date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format, use YYYY-MM-DD")
    if parsed_date_from and parsed_date_to and parsed_date_from > parsed_date_to:
        raise HTTPException(status_code=400, detail="date_from cannot be after date_to")

    escaped = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    effective_date = func.coalesce(Entry.local_date, func.date(Entry.created_at))
    base_filters = [
        Entry.user_id == current_user.id,
        Job.status != JobStatus.FAILED,
        or_(
            Entry.transcript.ilike(pattern),
            EntryClassification.extracted_text.ilike(pattern),
            EntryClassification.edited_text.ilike(pattern),
            EntryClassification.category.ilike(pattern),
        ),
    ]
    # Category filter semantics: the matched classification row must itself belong
    # to the given category. Entries whose matched content lives in a different
    # classification row are excluded, even if they also have a classification in
    # the filtered category. This is intentional — "show me TODO-line matches".
    if normalized_category:
        base_filters.append(EntryClassification.category == normalized_category)
    if parsed_date_from:
        base_filters.append(effective_date >= parsed_date_from)
    if parsed_date_to:
        base_filters.append(effective_date <= parsed_date_to)

    total_result = await db.execute(
        select(func.count(func.distinct(Entry.id)))
        .select_from(Entry)
        .join(Job, Job.entry_id == Entry.id)
        .outerjoin(EntryClassification, EntryClassification.entry_id == Entry.id)
        .where(*base_filters)
    )
    total = total_result.scalar() or 0

    ids_result = await db.execute(
        select(Entry.id, Entry.created_at)
        .join(Job, Job.entry_id == Entry.id)
        .outerjoin(EntryClassification, EntryClassification.entry_id == Entry.id)
        .where(*base_filters)
        .group_by(Entry.id, Entry.created_at)
        .order_by(Entry.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = ids_result.all()
    entry_ids = [row.id for row in rows]

    if not entry_ids:
        return EntryListResponse(items=[], total=total, skip=skip, limit=limit)

    entries_result = await db.execute(
        select(Entry)
        .options(selectinload(Entry.classifications))
        .where(Entry.id.in_(entry_ids), Entry.user_id == current_user.id)
    )
    entries_by_id = {entry.id: entry for entry in entries_result.scalars().all()}
    ordered_entries = [entries_by_id[entry_id] for entry_id in entry_ids if entry_id in entries_by_id]

    return EntryListResponse(
        items=[
            _entry_item_from_entry(entry).model_copy(
                update={"match_sources": _search_match_sources(entry, query_text)}
            )
            for entry in ordered_entries
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an entry and its associated audio, classifications, and jobs."""
    try:
        entry_uuid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry_id")

    result = await db.execute(
        select(Entry).where(Entry.id == entry_uuid, Entry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Delete audio from object storage (best-effort)
    if entry.raw_audio_key:
        try:
            await storage_svc.delete_object(entry.raw_audio_key)
        except Exception as exc:
            logger.warning(f"Failed to delete audio {entry.raw_audio_key}: {exc}")

    await db.delete(entry)  # cascades to classifications, jobs, metadata
    await db.commit()
    logger.info(f"Deleted entry {entry_id} for user {current_user.id}")


@router.patch("/{entry_id}", response_model=EntryItem)
async def update_entry(
    entry_id: str,
    body: EntryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an entry's transcript and/or categories."""
    try:
        entry_uuid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry_id")

    result = await db.execute(
        select(Entry)
        .options(selectinload(Entry.classifications))
        .where(Entry.id == entry_uuid, Entry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    original_audit_date = entry.local_date or entry.created_at.date()

    if body.date is not None:
        try:
            target_date = datetime.strptime(body.date, "%Y-%m-%d").date()
            target_dt = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
        entry.created_at = target_dt
        entry.recorded_at = target_dt
        entry.local_date = target_date

    if body.transcript is not None:
        entry.transcript = body.transcript

    if body.categories is not None:
        # Merge by stable classification id to preserve capture inbox state
        # (status, id) across reorders, deletes, and inserts. Items without an
        # id are treated as new inserts; existing rows whose ids are absent
        # from the incoming list are deleted.
        existing_by_id = {str(c.id): c for c in entry.classifications}
        seen_ids: set[str] = set()

        for i, cat_item in enumerate(body.categories):
            existing = existing_by_id.get(cat_item.id) if cat_item.id else None
            if existing is not None:
                seen_ids.add(cat_item.id)
                existing.category = cat_item.category
                existing.extracted_text = cat_item.text
                # New text becomes canonical — drop any prior inbox edit.
                existing.edited_text = None
                existing.estimated_minutes = cat_item.estimated_minutes
                existing.display_order = i
                existing.user_override = True
            else:
                # No id, or id refers to a row on a different entry — insert fresh.
                entry.classifications.append(
                    EntryClassification(
                        entry_id=entry.id,
                        category=cat_item.category,
                        extracted_text=cat_item.text,
                        estimated_minutes=cat_item.estimated_minutes,
                        display_order=i,
                        user_override=True,
                    )
                )

        # Delete any existing rows the client did not echo back.
        for cid, c in existing_by_id.items():
            if cid not in seen_ids:
                await db.delete(c)
        await db.flush()

    # Invalidate cached audits for both source and target dates (daily + weekly).
    # Moving an entry changes the old day's totals and the new day's totals.
    entry_date = entry.local_date or entry.created_at.date()
    audit_dates = {original_audit_date, entry_date,
                   _current_week_start(original_audit_date),
                   _current_week_start(entry_date)}
    stale_result = await db.execute(
        select(AuditResult).where(
            AuditResult.user_id == current_user.id,
            AuditResult.audit_date.in_(audit_dates),
            AuditResult.is_stale.is_(False),
        )
    )
    for ar in stale_result.scalars().all():
        ar.is_stale = True

    await db.commit()
    await db.refresh(entry, ["classifications"])

    return EntryItem(
        id=str(entry.id),
        transcript=entry.transcript,
        recorded_at=entry.recorded_at.isoformat() if entry.recorded_at else None,
        created_at=entry.created_at.isoformat(),
        local_date=entry.local_date.isoformat() if entry.local_date else None,
        duration_seconds=entry.duration_seconds,
        categories=[_category_item_from_classification(c) for c in entry.classifications],
    )


@router.post("/{entry_id}/reclassify", response_model=EntryItem)
async def reclassify_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run AI categorization on an entry's transcript."""
    try:
        entry_uuid = uuid.UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry_id")

    result = await db.execute(
        select(Entry)
        .options(selectinload(Entry.classifications))
        .where(Entry.id == entry_uuid, Entry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Use edited classification texts if available, fall back to original transcript
    if entry.classifications:
        text_to_classify = ". ".join(
            c.display_text for c in sorted(entry.classifications, key=lambda c: c.display_order)
            if c.display_text
        )
    else:
        text_to_classify = entry.transcript

    if not text_to_classify or not text_to_classify.strip():
        raise HTTPException(status_code=400, detail="Entry has no text to classify")

    # Run AI categorization
    cat_results = await categorize_text(text_to_classify)

    # Remove existing classifications
    for c in list(entry.classifications):
        await db.delete(c)
    await db.flush()

    # Insert new ones
    for i, item in enumerate(cat_results):
        est_min = item.get("estimated_minutes")
        try:
            est_min_val = int(est_min) if est_min is not None else None
            if est_min_val is not None and not (0 <= est_min_val <= 1440):
                est_min_val = None
        except (ValueError, TypeError):
            est_min_val = None
        entry.classifications.append(
            EntryClassification(
                entry_id=entry.id,
                category=item["category"],
                extracted_text=item.get("text"),
                estimated_minutes=est_min_val,
                display_order=i,
                model_version="gpt-5.4-nano",
            )
        )

    # Invalidate cached audits for this date (categories may have changed)
    # Invalidate both daily (keyed on exact date) and weekly (keyed on Monday)
    audit_date = entry.local_date or entry.created_at.date()
    weekly_monday = _current_week_start(audit_date)
    stale_result = await db.execute(
        select(AuditResult).where(
            AuditResult.user_id == current_user.id,
            AuditResult.audit_date.in_([audit_date, weekly_monday]),
            AuditResult.is_stale.is_(False),
        )
    )
    for ar in stale_result.scalars().all():
        ar.is_stale = True

    await db.commit()
    await db.refresh(entry, ["classifications"])

    return EntryItem(
        id=str(entry.id),
        transcript=entry.transcript,
        recorded_at=entry.recorded_at.isoformat() if entry.recorded_at else None,
        created_at=entry.created_at.isoformat(),
        duration_seconds=entry.duration_seconds,
        categories=[_category_item_from_classification(c) for c in entry.classifications],
    )


@router.post("/audit", response_model=AuditResponse)
async def generate_audit(
    body: AuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate an AI-powered time audit for a given UTC date.

    - Accepts any past date; rejects future dates.
    - Persisted: returns cached result if fresh; set regenerate=true to force re-generation.
    - Invalidated automatically when new entries arrive for the same date.
    """
    # ── Validate date ────────────────────────────────────────────────────────
    try:
        target_date = datetime.strptime(body.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    today_utc = datetime.now(timezone.utc).date()
    if target_date > today_utc:
        raise HTTPException(status_code=400, detail="Date cannot be in the future.")

    # ── Check cache ──────────────────────────────────────────────────────────
    if not body.regenerate:
        cached = await _get_cached_audit(db, current_user.id, target_date, "daily")
        if cached is not None:
            return cached

    # ── Fetch entries for the UTC day ────────────────────────────────────────
    entries, all_classifications = await _fetch_entries_for_date(
        db, current_user.id, target_date
    )

    if not entries:
        return AuditResponse(
            entries=0, breakdown={}, approximate=False,
            audit_text=None, generated_at=None, message="Record your day first",
        )

    breakdown, approximate = _compute_breakdown(all_classifications)

    # ── Generate audit text ──────────────────────────────────────────────────
    audit_text = await _generate_audit_text(entries, all_classifications, breakdown, db, current_user.id)

    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Persist result ───────────────────────────────────────────────────────
    await _save_audit(
        db, current_user.id, target_date, "daily",
        len(entries), breakdown, audit_text,
    )

    return AuditResponse(
        entries=len(entries),
        breakdown=breakdown,
        approximate=approximate,
        audit_text=audit_text,
        generated_at=now_iso,
    )


class WeeklyAuditRequest(BaseModel):
    regenerate: bool = False
    week_start: Optional[str] = None  # YYYY-MM-DD, auto-normalized to Monday


def _current_week_start(today) -> "date":
    """Monday of the calendar week containing *today*."""
    from datetime import date as _date
    if isinstance(today, str):
        today = _date.fromisoformat(today)
    return today - timedelta(days=today.weekday())


@router.get("/audit/weekly")
async def get_weekly_audit(
    week_start: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return cached weekly report for a given week, or 204 if none."""
    today_utc = datetime.now(timezone.utc).date()
    if week_start:
        try:
            from datetime import date as _date
            target_monday = _current_week_start(_date.fromisoformat(week_start))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid week_start date format. Use YYYY-MM-DD.")
        if target_monday > today_utc:
            raise HTTPException(status_code=400, detail="Cannot query a future week.")
    else:
        target_monday = _current_week_start(today_utc)
    cached = await _get_cached_audit(db, current_user.id, target_monday, "weekly")
    if cached is not None:
        return cached
    return Response(status_code=204)


@router.post("/audit/weekly", response_model=AuditResponse)
async def generate_weekly_audit(
    body: WeeklyAuditRequest = WeeklyAuditRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a structured weekly report + AI Coach letter.

    Calendar-week aligned (Monday–Sunday). Produces both prose audit_text
    and structured report_json with 4 sections: time_breakdown, open_loops,
    recurring_themes, draft_status_update.

    Accepts optional week_start (YYYY-MM-DD) to target a specific week.
    Defaults to the current calendar week.
    """
    today_utc = datetime.now(timezone.utc).date()

    # Determine target week
    if body.week_start:
        try:
            from datetime import date as _date
            week_start_date = _current_week_start(_date.fromisoformat(body.week_start))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid week_start date format. Use YYYY-MM-DD.")
        if week_start_date > today_utc:
            raise HTTPException(status_code=400, detail="Cannot generate report for a future week.")
    else:
        week_start_date = _current_week_start(today_utc)

    # week_end: full 7 days for past weeks, up-to-today for current week
    week_end_date = min(week_start_date + timedelta(days=6), today_utc)

    # Check cache (keyed on Monday)
    if not body.regenerate:
        cached = await _get_cached_audit(db, current_user.id, week_start_date, "weekly")
        if cached is not None:
            return cached

    result = await db.execute(
        select(Entry)
        .join(Job, Job.entry_id == Entry.id)
        .options(selectinload(Entry.classifications))
        .where(
            Entry.user_id == current_user.id,
            func.coalesce(Entry.local_date, func.date(Entry.created_at)) >= week_start_date,
            func.coalesce(Entry.local_date, func.date(Entry.created_at)) <= week_end_date,
            Job.status == JobStatus.DONE,
        )
        .order_by(Entry.created_at.asc())
    )
    entries = result.scalars().all()

    if len(entries) < 3:
        return AuditResponse(
            entries=len(entries), breakdown={}, approximate=False,
            audit_text=None, generated_at=None,
            message="Record more this week for a useful report. Need at least 3 entries.",
            week_start=week_start_date.isoformat(),
            week_end=week_end_date.isoformat(),
        )

    all_classifications = [c for e in entries for c in e.classifications]
    breakdown, approximate = _compute_breakdown(all_classifications)

    # Query open loops: TODOs still marked 'open'
    open_loops_q = await db.execute(
        select(EntryClassification)
        .where(
            EntryClassification.entry_id.in_([e.id for e in entries]),
            EntryClassification.category == "TODO",
            EntryClassification.status == "open",
        )
        .order_by(EntryClassification.classified_at.asc())
    )
    open_loops = [
        (c.display_text or c.extracted_text or "") for c in open_loops_q.scalars().all()
    ]

    # Build per-day summary for the coach prompt
    day_summaries: Dict[str, List[str]] = {}
    for e in entries:
        day_key = e.local_date.strftime("%A %m/%d") if e.local_date else e.created_at.strftime("%A %m/%d")
        for c in e.classifications:
            text = c.display_text or e.transcript or ""
            mins = f" ({c.estimated_minutes}min)" if c.estimated_minutes else ""
            day_summaries.setdefault(day_key, []).append(f"  - [{c.category}]{mins} {text}")

    day_text = "\n".join(
        f"{day}:\n" + "\n".join(items)
        for day, items in day_summaries.items()
    )
    activity_breakdown, _ = _compute_activity_breakdown(all_classifications)
    capture_counts = _compute_capture_counts(all_classifications)
    activity_summary = ", ".join(f"{cat}: {pct}%" for cat, pct in activity_breakdown.items()) or "No activity entries"
    capture_summary = ", ".join(f"{count} {cat}{'s' if count > 1 else ''}" for cat, count in capture_counts.items()) or "None"

    # Pull active prior themes for continuity in the prompt + later dedup
    prior_themes_q = await db.execute(
        select(WeeklyTheme).where(
            WeeklyTheme.user_id == current_user.id,
            WeeklyTheme.status.in_(["active", "pinned"]),
        ).order_by(WeeklyTheme.last_seen.desc()).limit(20)
    )
    prior_themes = prior_themes_q.scalars().all()
    prior_themes_text = "\n".join(
        f"- [{t.polarity}] {t.title}: {t.description or ''} (seen {t.occurrences}x)"
        for t in prior_themes
    ) or "(none yet)"

    open_loops_text = "\n".join(f"- {t}" for t in open_loops) if open_loops else "(none)"

    # Stage 1 — THINKING (gpt-5.4): structured analysis + theme extraction in JSON
    thinking_prompt = f"""You are an analytical AI time coach.

Analyze the user's week and produce STRUCTURED JSON only.

Naval's framework:
EARNING (money/work) | LEARNING (knowledge) | RELAXING (recharge) | FAMILY (relationships)

Prior recurring themes (for continuity):
{prior_themes_text}

This week's activity summary:
{activity_summary}

Follow-up items:
{capture_summary}

Open TODOs:
{open_loops_text}

Daily activities:
{day_text}

---

INTERNAL SCORING RULES (do not output):
- Score each day 0–5 across EARNING, LEARNING, RELAXING, FAMILY
- Balance = variance across the 4 categories (lower is better)
- Best day = high total score + low imbalance
- Worst day = low total score OR extreme imbalance

---

THEME RULES:
- Reuse exact title if the same pattern continues
- Only create new theme if it cannot map to an existing one
- Themes must represent recurring behavior, not one-off events
- Max 3 themes

---

OUTPUT REQUIREMENTS:
- Be specific, not generic
- "uncomfortable_truth" must be concrete and slightly uncomfortable
- "next_week_action" must be specific and measurable

---

Respond with ONLY a valid JSON object:

{{
  "best_day": "...",
  "worst_day": "...",
  "patterns": ["..."],
  "uncomfortable_truth": "...",
  "naval_balance": "...",
  "next_week_action": "...",
  "themes": [
    {{
      "title": "...",
      "description": "...",
      "polarity": "positive|negative|neutral",
      "category": "EARNING|LEARNING|RELAXING|FAMILY|other"
    }}
  ]
}}"""

    try:
        thinking_response = await asyncio.wait_for(
            _get_openai().chat.completions.create(
                model="gpt-5.4",
                messages=[{"role": "user", "content": thinking_prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            ),
            timeout=30.0,
        )
        thinking_raw = thinking_response.choices[0].message.content or "{}"
        try:
            analysis = json.loads(thinking_raw)
        except json.JSONDecodeError:
            logger.warning(f"Weekly thinking returned non-JSON: {thinking_raw[:200]}")
            analysis = {}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Weekly review timed out. Try again.")
    except Exception as exc:
        logger.error(f"Weekly thinking LLM call failed: {exc}", exc_info=True)
        return AuditResponse(
            entries=len(entries), breakdown=breakdown, approximate=approximate,
            audit_text=None, generated_at=None, message="Weekly review generation failed",
        )

    # Stage 2 — WRITING (gpt-5.4-mini): turn the analysis into a prose letter
    analysis_json_str = json.dumps(analysis, ensure_ascii=False, indent=2)
    writing_prompt = f"""You are an opinionated, honest AI time coach.

Your job is to convert structured analysis into a weekly review letter.

---

STRICT RULES:
- Use ONLY facts explicitly present in the Analysis JSON
- Do NOT infer, speculate, or add new information
- Treat the Analysis JSON as the single source of truth
- Do NOT introduce new patterns or reinterpret conclusions

---

LANGUAGE:
- Detect dominant language from Original daily activities
- If mostly Chinese → write in Chinese
- Otherwise → write in English
- Do NOT mix languages

---

MANDATORY CONTENT:
- You MUST include the "uncomfortable_truth" clearly (verbatim or nearly verbatim)
- You MUST include "next_week_action" clearly at the end

---

STRUCTURE (MANDATORY):

Paragraph 1:
- Overall weekly pattern (use patterns + naval_balance)

Paragraph 2:
- What is working

Paragraph 3:
- What is not working (center on uncomfortable_truth, be direct)

Paragraph 4:
- One concrete behavior change (next_week_action)

---

STYLE:
- Direct, slightly provocative
- Respectful but not soft
- No fluff, no generic advice

---

Analysis JSON:
{analysis_json_str}

Original daily activities (for language detection only):
{day_text[:500]}

Write the letter."""

    async def _run_writing(prompt: str) -> str:
        response = await asyncio.wait_for(
            _get_openai().chat.completions.create(
                model="gpt-5.4-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
            ),
            timeout=20.0,
        )
        return (response.choices[0].message.content or "").strip()

    try:
        audit_text = await _run_writing(writing_prompt)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Weekly review timed out. Try again.")
    except Exception as exc:
        logger.error(f"Weekly writing LLM call failed: {exc}", exc_info=True)
        return AuditResponse(
            entries=len(entries), breakdown=breakdown, approximate=approximate,
            audit_text=None, generated_at=None, message="Weekly review generation failed",
        )

    # Stage 2 check — lightweight validator (gpt-5.4-nano). Rewrites once if checks fail.
    check_issues = await _check_weekly_letter(audit_text, analysis)
    if check_issues:
        logger.info(f"Weekly letter failed validation, rewriting once. Issues: {check_issues}")
        rewrite_prompt = (
            writing_prompt
            + "\n\n---\n\nPREVIOUS ATTEMPT FAILED THESE CHECKS — FIX ALL OF THEM:\n"
            + "\n".join(f"- {issue}" for issue in check_issues)
            + "\n\nRewrite the letter from scratch, following every rule above."
        )
        try:
            audit_text = await _run_writing(rewrite_prompt)
        except asyncio.TimeoutError:
            logger.warning("Weekly letter rewrite timed out; keeping original draft.")
        except Exception as exc:
            logger.warning(f"Weekly letter rewrite failed ({exc}); keeping original draft.")

    # Build structured 4-section report from analysis + DB data
    report_json = {
        "time_breakdown": {
            "activity": dict(activity_breakdown),
            "captures": dict(capture_counts),
            "best_day": analysis.get("best_day"),
            "worst_day": analysis.get("worst_day"),
            "naval_balance": analysis.get("naval_balance"),
        },
        "open_loops": open_loops,
        "recurring_themes": analysis.get("patterns", []),
        "draft_status_update": analysis.get("uncomfortable_truth", ""),
    }

    now_iso = datetime.now(timezone.utc).isoformat()

    await _save_audit(
        db, current_user.id, week_start_date, "weekly",
        len(entries), breakdown, audit_text, report_json=report_json,
    )

    # Persist + dedup themes
    new_theme_payloads: List[Dict[str, Any]] = []
    extracted = analysis.get("themes") or []
    if isinstance(extracted, list):
        prior_by_title = {t.title.strip().lower(): t for t in prior_themes}
        snippet = (audit_text or "")[:240]
        for t in extracted:
            if not isinstance(t, dict):
                continue
            title = (t.get("title") or "").strip()
            if not title:
                continue
            key = title.lower()
            existing = prior_by_title.get(key)
            if existing is None:
                # Cheap fuzzy dedup: substring overlap
                for k, pt in prior_by_title.items():
                    if k in key or key in k:
                        existing = pt
                        break
            evidence_entry = {"audit_date": week_start_date.isoformat(), "snippet": snippet}
            if existing is not None:
                existing.last_seen = today_utc
                existing.occurrences = (existing.occurrences or 0) + 1
                existing.description = t.get("description") or existing.description
                existing.polarity = t.get("polarity") or existing.polarity
                existing.category = t.get("category") or existing.category
                ev = list(existing.evidence or [])
                ev.append(evidence_entry)
                existing.evidence = ev[-10:]
                new_theme_payloads.append({
                    "id": str(existing.id), "title": existing.title,
                    "polarity": existing.polarity, "is_new": False,
                    "occurrences": existing.occurrences,
                })
            else:
                theme = WeeklyTheme(
                    user_id=current_user.id,
                    title=title[:200],
                    description=t.get("description"),
                    polarity=(t.get("polarity") or "neutral")[:20],
                    category=(t.get("category") or None),
                    first_seen=today_utc,
                    last_seen=today_utc,
                    occurrences=1,
                    status="active",
                    evidence=[evidence_entry],
                )
                db.add(theme)
                await db.flush()
                new_theme_payloads.append({
                    "id": str(theme.id), "title": theme.title,
                    "polarity": theme.polarity, "is_new": True,
                    "occurrences": 1,
                })
    await db.commit()

    return AuditResponse(
        entries=len(entries),
        breakdown=breakdown,
        approximate=approximate,
        audit_text=audit_text,
        report_json=report_json,
        generated_at=now_iso,
        week_start=week_start_date.isoformat(),
        week_end=week_end_date.isoformat(),
        days_covered=(week_end_date - week_start_date).days + 1,
        new_themes=new_theme_payloads,
    )


class AvailableWeek(BaseModel):
    week_start: str
    week_end: str
    entry_count: int
    has_report: bool


@router.get("/audit/weekly/available-weeks", response_model=List[AvailableWeek])
async def get_available_weeks(
    limit: int = Query(default=20, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return calendar weeks with 3+ entries for the current user, newest first."""
    today_utc = datetime.now(timezone.utc).date()

    # Group entries by ISO week (Monday-based) using date_trunc, cast to date
    week_col = cast(
        func.date_trunc(
            "week",
            func.coalesce(Entry.local_date, func.date(Entry.created_at)),
        ),
        Date,
    ).label("week_monday")

    result = await db.execute(
        select(
            week_col,
            func.count(Entry.id).label("cnt"),
        )
        .join(Job, Job.entry_id == Entry.id)
        .where(
            Entry.user_id == current_user.id,
            Job.status == JobStatus.DONE,
        )
        .group_by(week_col)
        .having(func.count(Entry.id) >= 3)
        .order_by(week_col.desc())
        .limit(limit)
    )
    week_rows = result.all()

    if not week_rows:
        return []

    # Batch-check which weeks have a non-stale report
    monday_dates = [row.week_monday.date() if hasattr(row.week_monday, 'date') else row.week_monday for row in week_rows]
    report_result = await db.execute(
        select(AuditResult.audit_date).where(
            AuditResult.user_id == current_user.id,
            AuditResult.audit_type == "weekly",
            AuditResult.audit_date.in_(monday_dates),
            AuditResult.is_stale.is_(False),
            AuditResult.audit_text.isnot(None),
        )
    )
    has_report_dates = {row[0] for row in report_result.all()}

    weeks = []
    for row in week_rows:
        monday = row.week_monday.date() if hasattr(row.week_monday, 'date') else row.week_monday
        week_end = min(monday + timedelta(days=6), today_utc)
        weeks.append(AvailableWeek(
            week_start=monday.isoformat(),
            week_end=week_end.isoformat(),
            entry_count=row.cnt,
            has_report=monday in has_report_dates,
        ))
    return weeks


# ── Themes ────────────────────────────────────────────────────────────────────

class ThemeOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    polarity: str
    category: Optional[str]
    first_seen: str
    last_seen: str
    occurrences: int
    status: str
    user_note: Optional[str]
    evidence: List[Dict[str, Any]]
    streak: List[bool] = []  # last 14 days, oldest → newest, true = day had relevant activity


class ThemeUpdateRequest(BaseModel):
    status: Optional[str] = None  # active | pinned | dismissed | resolved
    user_note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in {"active", "pinned", "dismissed", "resolved"}:
            raise ValueError("invalid status")
        return v


def _theme_to_out(t: WeeklyTheme, streak: Optional[List[bool]] = None) -> ThemeOut:
    return ThemeOut(
        id=str(t.id),
        title=t.title,
        description=t.description,
        polarity=t.polarity,
        category=t.category,
        first_seen=t.first_seen.isoformat(),
        last_seen=t.last_seen.isoformat(),
        occurrences=t.occurrences,
        status=t.status,
        user_note=t.user_note,
        evidence=list(t.evidence or []),
        streak=streak or [],
    )


async def _compute_theme_streaks(
    db: AsyncSession, user_id: int, themes: List[WeeklyTheme]
) -> Dict[str, List[bool]]:
    """For each theme, return a 14-element bool list (oldest→newest) indicating
    whether the user had any classification matching the theme's category on that day.
    Themes with no category fall back to "any entry that day."
    """
    if not themes:
        return {}
    today = datetime.now(timezone.utc).date()
    window_start = today - timedelta(days=13)
    days = [window_start + timedelta(days=i) for i in range(14)]

    day_col = func.coalesce(Entry.local_date, func.date(Entry.created_at))
    rows = await db.execute(
        select(day_col.label("d"), EntryClassification.category)
        .join(EntryClassification, EntryClassification.entry_id == Entry.id)
        .where(
            Entry.user_id == user_id,
            day_col >= window_start,
            day_col <= today,
        )
    )
    by_day_categories: Dict[Any, set] = {}
    any_day: set = set()
    for d, cat in rows.all():
        any_day.add(d)
        by_day_categories.setdefault(d, set()).add(cat)

    out: Dict[str, List[bool]] = {}
    for t in themes:
        if t.category:
            out[str(t.id)] = [t.category in by_day_categories.get(d, set()) for d in days]
        else:
            out[str(t.id)] = [d in any_day for d in days]
    return out


@router.get("/themes", response_model=List[ThemeOut])
async def list_themes(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recurring weekly themes for the current user."""
    q = select(WeeklyTheme).where(WeeklyTheme.user_id == current_user.id)
    if status_filter:
        q = q.where(WeeklyTheme.status == status_filter)
    else:
        q = q.where(WeeklyTheme.status.in_(["active", "pinned"]))
    q = q.order_by(
        case((WeeklyTheme.status == "pinned", 0), else_=1),
        WeeklyTheme.last_seen.desc(),
    )
    result = await db.execute(q)
    themes = result.scalars().all()
    streaks = await _compute_theme_streaks(db, current_user.id, themes)
    return [_theme_to_out(t, streaks.get(str(t.id))) for t in themes]


@router.patch("/themes/{theme_id}", response_model=ThemeOut)
async def update_theme(
    theme_id: str,
    body: ThemeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WeeklyTheme).where(
            WeeklyTheme.id == theme_id,
            WeeklyTheme.user_id == current_user.id,
        )
    )
    theme = result.scalar_one_or_none()
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    if body.status is not None:
        theme.status = body.status
    if body.user_note is not None:
        theme.user_note = body.user_note
    await db.commit()
    return _theme_to_out(theme)


@router.delete("/themes/{theme_id}", status_code=204)
async def delete_theme(
    theme_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WeeklyTheme).where(
            WeeklyTheme.id == theme_id,
            WeeklyTheme.user_id == current_user.id,
        )
    )
    theme = result.scalar_one_or_none()
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    await db.delete(theme)
    await db.commit()


# ── Audit helpers ─────────────────────────────────────────────────────────────

async def _fetch_entries_for_date(
    db: AsyncSession, user_id: int, target_date
) -> tuple:
    """Fetch processed entries for a local date. Returns (entries, all_classifications)."""
    result = await db.execute(
        select(Entry)
        .join(Job, Job.entry_id == Entry.id)
        .options(selectinload(Entry.classifications))
        .where(
            Entry.user_id == user_id,
            _date_match(target_date),
            Job.status == JobStatus.DONE,
        )
        .order_by(Entry.created_at.asc())
    )
    entries = result.scalars().all()
    all_classifications = [c for e in entries for c in e.classifications]
    return entries, all_classifications


def _compute_breakdown(
    all_classifications: list,
) -> tuple[Dict[str, float], bool]:
    """Time-weighted breakdown (all categories). Returns (breakdown_dict, approximate_flag)."""
    if not all_classifications:
        return {}, False

    has_any = any(c.estimated_minutes is not None for c in all_classifications)
    has_all = all(c.estimated_minutes is not None for c in all_classifications)

    weights: Dict[str, float] = {}
    if has_any:
        non_null = [c.estimated_minutes for c in all_classifications if c.estimated_minutes is not None]
        avg = sum(non_null) / len(non_null) if non_null else 1
        for c in all_classifications:
            w = float(c.estimated_minutes) if c.estimated_minutes is not None else avg
            weights[c.category] = weights.get(c.category, 0) + w
    else:
        for c in all_classifications:
            weights[c.category] = weights.get(c.category, 0) + 1

    total = sum(weights.values()) or 1
    breakdown = {cat: round(w / total * 100, 1) for cat, w in weights.items()}
    return breakdown, not has_all


def _compute_activity_breakdown(
    all_classifications: list,
) -> tuple[Dict[str, float], bool]:
    """Time-weighted breakdown of activity categories only (EARNING/LEARNING/RELAXING/FAMILY/TIME_RECORD)."""
    activity_cls = [c for c in all_classifications if c.category in ACTIVITY_CATEGORIES]
    return _compute_breakdown(activity_cls)


def _compute_capture_counts(
    all_classifications: list,
) -> Dict[str, int]:
    """Simple counts of capture categories (TODO/EXPERIMENT/REFLECTION)."""
    counts: Dict[str, int] = {}
    for c in all_classifications:
        normalized = _normalize_category(c.category)
        if normalized in CAPTURE_CATEGORIES:
            counts[normalized] = counts.get(normalized, 0) + 1
    return counts


async def _check_weekly_letter(letter: str, analysis: Dict[str, Any]) -> List[str]:
    """Lightweight validator for the Stage 2 letter. Returns a list of failure reasons (empty = pass).

    Deterministic checks: paragraph count, presence of uncomfortable_truth and next_week_action.
    LLM check (gpt-5.4-nano): flag claims not grounded in the analysis JSON. Best-effort — if the
    check call itself fails, we skip it rather than block letter delivery.
    """
    issues: List[str] = []
    text = (letter or "").strip()
    if not text:
        return ["Letter is empty."]

    # 1) Exactly 4 paragraphs (blocks separated by blank lines)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) != 4:
        issues.append(f"Letter must have exactly 4 paragraphs; found {len(paragraphs)}.")

    def _fuzzy_contains(haystack: str, needle: str, min_ratio: float = 0.5) -> bool:
        """Cheap fuzzy containment: share enough non-trivial word tokens."""
        if not needle:
            return True
        needle_tokens = [t for t in re.findall(r"\w+", needle.lower()) if len(t) > 2]
        if not needle_tokens:
            return needle.strip().lower() in haystack.lower()
        hay_tokens = set(re.findall(r"\w+", haystack.lower()))
        overlap = sum(1 for t in needle_tokens if t in hay_tokens)
        return overlap / len(needle_tokens) >= min_ratio

    uncomfortable = (analysis.get("uncomfortable_truth") or "").strip()
    if uncomfortable and not _fuzzy_contains(text, uncomfortable):
        issues.append("Letter must include the uncomfortable_truth (verbatim or nearly so).")

    next_action = (analysis.get("next_week_action") or "").strip()
    if next_action and not _fuzzy_contains(text, next_action):
        issues.append("Letter must include the next_week_action clearly at the end.")

    # 2) LLM groundedness check (gpt-5.4-nano). Best-effort: on failure, skip silently.
    try:
        analysis_json_str = json.dumps(analysis, ensure_ascii=False, indent=2)
        check_prompt = (
            "You are a strict fact-checker. Compare a weekly review LETTER against an ANALYSIS JSON. "
            "Respond with ONLY a JSON object: {\"grounded\": true|false, \"reason\": \"...\"}. "
            "Set grounded=false ONLY if the letter introduces concrete claims (people, numbers, events, "
            "conclusions) that are not supported by the ANALYSIS JSON. Minor paraphrasing is fine.\n\n"
            f"ANALYSIS JSON:\n{analysis_json_str}\n\nLETTER:\n{text}"
        )
        check_response = await asyncio.wait_for(
            _get_openai().chat.completions.create(
                model="gpt-5.4-nano",
                messages=[{"role": "user", "content": check_prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            ),
            timeout=10.0,
        )
        raw = check_response.choices[0].message.content or "{}"
        parsed = json.loads(raw) if raw else {}
        grounded = parsed.get("grounded")
        is_ungrounded = (
            grounded is False
            or (isinstance(grounded, str) and grounded.strip().lower() in ("false", "no", "0"))
        )
        if is_ungrounded:
            reason = (parsed.get("reason") or "letter includes claims not in the analysis").strip()
            issues.append(f"Letter contains information not in the analysis JSON: {reason}")
    except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
        logger.info(f"Weekly letter groundedness check skipped: {exc}")
    except Exception as exc:
        logger.info(f"Weekly letter groundedness check failed, skipping: {exc}")

    return issues


async def _generate_audit_text(
    entries: list, all_classifications: list, breakdown: Dict[str, float],
    db: Optional[AsyncSession] = None, user_id: Optional[int] = None,
) -> Optional[str]:
    """Call GPT to generate audit text. Returns None on failure."""
    entry_lines = []
    for e in entries:
        for c in e.classifications:
            text = c.display_text or e.transcript or ""
            mins = f" ({c.estimated_minutes}min)" if c.estimated_minutes else ""
            entry_lines.append(f"- [{_normalize_category(c.category)}]{mins} {text}")

    activity_breakdown, _ = _compute_activity_breakdown(all_classifications)
    capture_counts = _compute_capture_counts(all_classifications)

    activity_summary = ", ".join(f"{cat}: {pct}%" for cat, pct in activity_breakdown.items()) or "No activity entries"
    capture_summary = ", ".join(f"{count} {cat}{'s' if count > 1 else ''}" for cat, count in capture_counts.items()) or "None"
    entry_summary = "\n".join(entry_lines)

    # Pull recurring themes (pinned + active) for long-arc context.
    themes_block = ""
    if db is not None and user_id is not None:
        try:
            themes_q = await db.execute(
                select(WeeklyTheme).where(
                    WeeklyTheme.user_id == user_id,
                    WeeklyTheme.status.in_(["active", "pinned"]),
                ).order_by(
                    case((WeeklyTheme.status == "pinned", 0), else_=1),
                    WeeklyTheme.last_seen.desc(),
                ).limit(8)
            )
            themes = themes_q.scalars().all()
            if themes:
                themes_block = "\n".join(
                    f"- [{t.polarity}] {t.title}"
                    + (f": {t.description}" if t.description else "")
                    + f" (seen {t.occurrences}x)"
                    for t in themes
                )
        except Exception as exc:
            logger.warning(f"Failed to load themes for daily audit: {exc}")

    themes_section = (
        f"""

The user has been tracking these recurring themes from past weeks:
{themes_block}

If today's activities clearly extend, support, or contradict any of these themes, mention it in ONE sentence at most. If today's data has nothing to do with any theme, ignore them entirely. Do not force a connection."""
        if themes_block
        else ""
    )

    audit_prompt = f"""You are an honest, direct AI time coach. Based ONLY on the \
activities listed below, write a short audit (2-3 paragraphs, under 300 words) that:
- Summarizes how the day was actually spent
- Calls out what the numbers reveal (e.g. blocked time, admin overhead, shallow work)
- Gives one specific, actionable insight

Frame your analysis using Naval's time framework:
- EARNING = making money (work, meetings, clients)
- LEARNING = building knowledge (reading, courses, practice)
- RELAXING = recharging (exercise, rest, hobbies)
- FAMILY = relationships (partner, kids, parents)
Point out the balance or imbalance. If one category dominates or is missing, call it out.

IMPORTANT: Respond in the same language as the activities. If they are in Chinese, write in Chinese. If in English, write in English. Never mix up languages (e.g. do NOT respond in Japanese to Chinese entries).
Reference ONLY the activities listed. Do not invent activities not mentioned.{themes_section}

Activity breakdown: {activity_summary}
Follow-up items: {capture_summary}

Activities recorded today:
{entry_summary}"""

    try:
        response = await asyncio.wait_for(
            _get_openai().chat.completions.create(
                model="gpt-5.4-nano",
                messages=[{"role": "user", "content": audit_prompt}],
                temperature=0.7,
            ),
            timeout=15.0,
        )
        return response.choices[0].message.content
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Audit generation timed out. Try again.")
    except Exception as exc:
        logger.error(f"Audit LLM call failed: {exc}", exc_info=True)
        return None


async def _get_cached_audit(
    db: AsyncSession, user_id: int, audit_date, audit_type: str,
) -> Optional[AuditResponse]:
    """Return cached AuditResponse if fresh, else None."""
    result = await db.execute(
        select(AuditResult).where(
            AuditResult.user_id == user_id,
            AuditResult.audit_date == audit_date,
            AuditResult.audit_type == audit_type,
            AuditResult.is_stale.is_(False),
        ).order_by(AuditResult.generated_at.desc()).limit(1)
    )
    cached = result.scalar_one_or_none()
    if not cached or not cached.audit_text:
        return None

    breakdown = json.loads(cached.breakdown_json) if cached.breakdown_json else {}
    week_start = None
    week_end = None
    days_covered = None
    report_json_parsed = None
    if audit_type == "weekly":
        # audit_date is now the Monday of the week (post-migration)
        today_utc = datetime.now(timezone.utc).date()
        week_start_d = cached.audit_date
        week_end_d = min(week_start_d + timedelta(days=6), today_utc)
        week_end = week_end_d.isoformat()
        week_start = week_start_d.isoformat()
        days_covered = (week_end_d - week_start_d).days + 1
        if cached.report_json:
            try:
                report_json_parsed = json.loads(cached.report_json)
            except json.JSONDecodeError:
                pass
    return AuditResponse(
        entries=cached.entries_count,
        breakdown=breakdown,
        approximate=False,
        audit_text=cached.audit_text,
        report_json=report_json_parsed,
        generated_at=cached.generated_at.isoformat() if cached.generated_at else None,
        cached=True,
        week_start=week_start,
        week_end=week_end,
        days_covered=days_covered,
    )


async def _save_audit(
    db: AsyncSession, user_id: int, audit_date, audit_type: str,
    entries_count: int, breakdown: Dict[str, float], audit_text: Optional[str],
    report_json: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist an audit result, replacing any previous for the same user+date+type."""
    # Mark old results stale
    old = await db.execute(
        select(AuditResult).where(
            AuditResult.user_id == user_id,
            AuditResult.audit_date == audit_date,
            AuditResult.audit_type == audit_type,
        )
    )
    for r in old.scalars().all():
        r.is_stale = True

    db.add(AuditResult(
        user_id=user_id,
        audit_date=audit_date,
        audit_type=audit_type,
        entries_count=entries_count,
        breakdown_json=json.dumps(breakdown),
        audit_text=audit_text,
        report_json=json.dumps(report_json, ensure_ascii=False) if report_json else None,
    ))
    await db.flush()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _date_match(target_date):
    """Match entries by local_date, falling back to DATE(created_at) for old rows with NULL local_date."""
    return or_(
        Entry.local_date == target_date,
        and_(Entry.local_date.is_(None), func.date(Entry.created_at) == target_date),
    )


def _content_type_to_suffix(content_type: str) -> str:
    mapping = {
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
    }
    base = content_type.split(";")[0].strip().lower()
    return mapping.get(base, ".webm")
