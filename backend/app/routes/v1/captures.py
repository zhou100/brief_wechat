"""
/api/v1/captures — Capture Inbox endpoints.

Cross-day triage for voice-extracted TODO/EXPERIMENT/REFLECTION items. Captures live
on `entry_classifications`; ownership flows through `entries.user_id`. Every
query joins entries and filters on the current user — there is no user_id
column on classifications directly.
"""
import logging
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models.classification import EntryClassification
from ...models.entry import Entry
from ...models.audit_result import AuditResult
from ...models.user import User
from ...utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/captures", tags=["captures"])

CAPTURE_CATEGORIES = {"TODO", "EXPERIMENT", "REFLECTION"}
LEGACY_CAPTURE_CATEGORY_MAP = {"IDEA": "EXPERIMENT", "THOUGHT": "REFLECTION"}
VALID_STATUSES = {"open", "done", "dismissed"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class CaptureItem(BaseModel):
    id: str
    entry_id: str
    category: str
    display_text: Optional[str]      # edited_text if set, else extracted_text
    status: str
    edited: bool                     # true iff edited_text is not null
    source_date: Optional[str]       # YYYY-MM-DD of source entry's local_date
    classified_at: Optional[str]


class CapturePatchRequest(BaseModel):
    status: Optional[Literal["open", "done", "dismissed"]] = None
    edited_text: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_item(c: EntryClassification, entry: Entry) -> CaptureItem:
    return CaptureItem(
        id=str(c.id),
        entry_id=str(c.entry_id),
        category=LEGACY_CAPTURE_CATEGORY_MAP.get(c.category, c.category),
        display_text=c.edited_text if c.edited_text else c.extracted_text,
        status=c.status,
        edited=c.edited_text is not None,
        source_date=entry.local_date.isoformat() if entry.local_date else None,
        classified_at=c.classified_at.isoformat() if c.classified_at else None,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[CaptureItem])
async def list_captures(
    category: Optional[str] = Query(None, description="TODO | EXPERIMENT | REFLECTION"),
    status: Optional[str] = Query("open", description="open | done | dismissed | all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List the current user's captures. Scoped by user via entries join.

    - category: optional filter; must be one of TODO/EXPERIMENT/REFLECTION. If omitted, returns all three.
    - status:   open (default) | done | dismissed | all
    """
    if category is not None and category not in CAPTURE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CAPTURE_CATEGORIES)}")

    stmt = (
        select(EntryClassification, Entry)
        .join(Entry, EntryClassification.entry_id == Entry.id)
        .where(Entry.user_id == current_user.id)
    )

    if category:
        legacy_filter_values = [category]
        if category == "EXPERIMENT":
            legacy_filter_values.append("IDEA")
        elif category == "REFLECTION":
            legacy_filter_values.append("THOUGHT")
        stmt = stmt.where(EntryClassification.category.in_(legacy_filter_values))
    else:
        stmt = stmt.where(
            EntryClassification.category.in_(CAPTURE_CATEGORIES | set(LEGACY_CAPTURE_CATEGORY_MAP.keys()))
        )

    if status and status != "all":
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)} or 'all'")
        stmt = stmt.where(EntryClassification.status == status)

    stmt = stmt.order_by(Entry.local_date.desc().nullslast(), EntryClassification.classified_at.desc())

    result = await db.execute(stmt)
    rows = result.all()
    return [_to_item(c, e) for (c, e) in rows]


@router.patch("/{capture_id}", response_model=CaptureItem)
async def patch_capture(
    capture_id: str,
    body: CapturePatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update a capture's status and/or edited_text. Cross-user access returns 404.
    Invalidates audit cache for the source entry's local_date.
    """
    try:
        cap_uuid = uuid.UUID(capture_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid capture id")

    if body.status is None and body.edited_text is None:
        raise HTTPException(status_code=400, detail="Must provide status or edited_text")

    # Join with entries to enforce ownership in a single query.
    result = await db.execute(
        select(EntryClassification, Entry)
        .join(Entry, EntryClassification.entry_id == Entry.id)
        .where(
            EntryClassification.id == cap_uuid,
            Entry.user_id == current_user.id,
        )
    )
    row = result.one_or_none()
    if not row:
        # Either doesn't exist or belongs to another user — 404 either way.
        raise HTTPException(status_code=404, detail="Capture not found")

    capture, entry = row

    if body.status is not None:
        capture.status = body.status
    if body.edited_text is not None:
        # Empty string clears the edit; None is a no-op (handled above).
        capture.edited_text = body.edited_text if body.edited_text.strip() else None
        capture.user_override = True

    # Invalidate cached audits for this date — capture edits affect breakdown counts.
    if entry.local_date:
        stale_result = await db.execute(
            select(AuditResult).where(
                AuditResult.user_id == current_user.id,
                AuditResult.audit_date == entry.local_date,
                AuditResult.is_stale.is_(False),
            )
        )
        for ar in stale_result.scalars().all():
            ar.is_stale = True

    await db.commit()
    await db.refresh(capture)
    logger.info(f"Capture {capture_id} patched by user {current_user.id}")
    return _to_item(capture, entry)
