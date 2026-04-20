import asyncio
import logging
import uuid
import json
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..models.audit_result import AuditResult
from ..models.classification import EntryClassification
from ..models.entry import Entry
from ..models.jobs import Job, JobStatus
from ..models.user import User
from ..services import queue as queue_svc
from ..services import storage as storage_svc
from ..services.llm_client import chat_model, get_chat_client
from ..settings import settings
from ..utils.auth import create_access_token, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/miniapp", tags=["miniapp"])


class MiniappLoginRequest(BaseModel):
    code: str


class MiniappUser(BaseModel):
    id: str
    display_name: Optional[str] = None


class MiniappLoginResponse(BaseModel):
    token: str
    user: MiniappUser


class UploadCreateRequest(BaseModel):
    fileName: str
    mimeType: str
    durationMs: int
    fileSize: Optional[int] = None


class UploadCreateResponse(BaseModel):
    upload_api_url: str
    object_key: str


class EntryCreateRequest(BaseModel):
    object_key: Optional[str] = None
    cloud_file_id: Optional[str] = None
    cloud_temp_url: Optional[str] = None
    duration_ms: int
    local_date: Optional[str] = None
    client_meta: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("duration_ms", mode="before")
    @classmethod
    def coerce_duration_ms(cls, value):
        if isinstance(value, float):
            return max(1, round(value))
        return value


class EntryCreateResponse(BaseModel):
    entry_id: str
    job_id: str


class JobResultPreview(BaseModel):
    summary: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    entry_id: Optional[str] = None
    local_date: Optional[str] = None
    status: str
    progress: int
    step: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    result_preview: Optional[JobResultPreview] = None


class EntryResultResponse(BaseModel):
    entry_id: str
    result_id: Optional[str] = None
    cloud_file_id: Optional[str] = None
    date: Optional[str] = None
    created_at: str
    summary: str
    key_points: List[str]
    open_loops: List[str]
    entries: List[Dict[str, Any]] = Field(default_factory=list)
    category_groups: List[Dict[str, Any]] = Field(default_factory=list)


class ShareCardRequest(BaseModel):
    entry_id: Optional[str] = None
    date: Optional[str] = None


class ClassificationPatchRequest(BaseModel):
    edited_text: Optional[str] = None
    status: Optional[str] = None


class ShareCard(BaseModel):
    share_id: str
    title: str
    summary: str
    open_loop_count: int
    image_url: Optional[str] = None


class ShareCardResponse(BaseModel):
    card: ShareCard


class SharedBrief(BaseModel):
    share_id: str
    summary: str
    open_loop_count: int
    created_at: str


class WeeklySuggestionResponse(BaseModel):
    show: bool
    week_start: str
    week_end: str
    entry_count: int


class WeeklyRequest(BaseModel):
    week_start: str
    force: bool = False


class WeeklyMainThing(BaseModel):
    title: str
    body: str


class WeeklySummaryResponse(BaseModel):
    title: str
    week_start: str
    week_end: str
    date_range: str
    opening: str
    main_things: List[WeeklyMainThing]
    remember_items: List[str]
    family_share_text: str
    next_week_nudge: str
    generated_at: str
    cached: bool = False
    stale: bool = False
    regen_count: int = 0


@router.post("/auth/login", response_model=MiniappLoginResponse)
async def miniapp_login(body: MiniappLoginRequest, db: AsyncSession = Depends(get_db)):
    session = await _exchange_wechat_code(body.code)
    openid = session.get("openid")
    if not openid:
        raise HTTPException(status_code=401, detail="WeChat login failed")

    user = await User.get_by_wechat_openid(db, openid)
    if not user:
        user = User(
            email=f"wechat_{openid}@miniapp.local",
            auth_provider="wechat",
            wechat_openid=openid,
            wechat_unionid=session.get("unionid"),
        )
        db.add(user)
        await db.flush()
    elif session.get("unionid") and not user.wechat_unionid:
        user.wechat_unionid = session["unionid"]
        await db.flush()

    await db.commit()
    token = create_access_token({"sub": str(user.id), "provider": "wechat"})
    return MiniappLoginResponse(
        token=token,
        user=MiniappUser(id=str(user.id), display_name="讲过就清爽"),
    )


@router.post("/uploads/create", response_model=UploadCreateResponse)
async def create_upload(
    body: UploadCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if body.durationMs <= 0:
        raise HTTPException(status_code=400, detail="durationMs must be positive")
    if body.fileSize is not None and body.fileSize > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="audio file is too large")

    entry_id = str(uuid.uuid4())
    suffix = _content_type_to_suffix(body.mimeType)
    object_key = storage_svc.make_audio_key(current_user.id, entry_id, suffix)
    base_url = settings.MINIAPP_PUBLIC_BASE_URL.rstrip("/") or str(request.base_url).rstrip("/")
    return UploadCreateResponse(
        upload_api_url=f"{base_url}/miniapp/uploads/audio?object_key={object_key}",
        object_key=object_key,
    )


@router.post("/uploads/audio")
async def upload_audio(
    object_key: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    expected_prefix = f"audio/{current_user.id}/"
    if not object_key.startswith(expected_prefix):
        raise HTTPException(status_code=400, detail="object_key does not match user")

    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="file must be audio")

    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="audio file is too large")

    await storage_svc.upload_bytes(object_key, data, content_type)
    return {"ok": True, "object_key": object_key}


@router.post("/entries", response_model=EntryCreateResponse)
async def create_entry(
    body: EntryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.duration_ms <= 0:
        raise HTTPException(status_code=400, detail="duration_ms must be positive")

    raw_audio_key = body.cloud_file_id or body.object_key
    if not raw_audio_key:
        raise HTTPException(status_code=400, detail="audio file reference is required")

    if body.cloud_file_id:
        if not body.cloud_file_id.startswith("cloud://"):
            raise HTTPException(status_code=400, detail="cloud_file_id must be a CloudBase fileID")
        if not body.cloud_temp_url:
            raise HTTPException(status_code=400, detail="cloud_temp_url is required for CloudBase uploads")
        if not body.cloud_temp_url.startswith("https://"):
            raise HTTPException(status_code=400, detail="cloud_temp_url must be an HTTPS URL")
        entry_id = uuid.uuid4()
    else:
        expected_prefix = f"audio/{current_user.id}/"
        if not body.object_key or not body.object_key.startswith(expected_prefix):
            raise HTTPException(status_code=400, detail="object_key does not match user")
        entry_id = _entry_id_from_object_key(body.object_key) or uuid.uuid4()

    local_date = None
    if body.local_date:
        try:
            local_date = datetime.strptime(body.local_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid local_date format")

    entry = Entry(
        id=entry_id,
        user_id=current_user.id,
        raw_audio_key=raw_audio_key,
        raw_audio_download_url=str(body.cloud_temp_url) if body.cloud_temp_url else None,
        duration_seconds=max(1, round(body.duration_ms / 1000)),
        recorded_at=datetime.now(timezone.utc),
        local_date=local_date,
    )
    db.add(entry)
    await db.flush()
    if local_date:
        await _mark_weekly_audits_stale(db, current_user.id, local_date)

    job = await queue_svc.enqueue(db, entry.id, current_user.id)
    await db.commit()
    return EntryCreateResponse(entry_id=str(entry.id), job_id=str(job.id))


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_uuid = _parse_uuid(job_id, "job_id")
    result = await db.execute(
        select(Job)
        .where(Job.id == job_uuid, Job.user_id == current_user.id)
        .options(selectinload(Job.entry).selectinload(Entry.classifications))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    preview = None
    if job.entry and job.entry.transcript:
        preview = JobResultPreview(summary=_one_sentence(job.entry.transcript))

    return JobResponse(
        job_id=str(job.id),
        entry_id=str(job.entry_id),
        local_date=job.entry.local_date.isoformat() if job.entry and job.entry.local_date else None,
        status=_miniapp_job_status(job.status),
        progress=_job_progress(job),
        step=job.step,
        error_code=_job_error_code(job),
        error_message=_job_error_message(job),
        result_preview=preview,
    )


@router.get("/entries/{entry_id}/result", response_model=EntryResultResponse)
async def get_entry_result(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = await _get_owned_entry(db, entry_id, current_user.id)
    return _entry_result(entry)


@router.get("/daily/{date}", response_model=EntryResultResponse)
async def get_daily_result(
    date: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        local_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    result = await db.execute(
        select(Entry)
        .where(Entry.user_id == current_user.id, Entry.local_date == local_date)
        .options(selectinload(Entry.classifications), selectinload(Entry.jobs))
        .order_by(Entry.created_at.asc())
    )
    entries = _completed_entries(result.scalars().unique().all())
    return _daily_result(entries, date)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = await _get_owned_entry(db, entry_id, current_user.id)
    if entry.raw_audio_key and not entry.raw_audio_key.startswith("cloud://"):
        await storage_svc.delete_object(entry.raw_audio_key)
    await db.delete(entry)
    await db.commit()


@router.post("/entries/{entry_id}/regenerate", response_model=EntryCreateResponse)
async def regenerate_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = await _get_owned_entry(db, entry_id, current_user.id)
    for classification in list(entry.classifications):
        await db.delete(classification)
    job = await queue_svc.enqueue(db, entry.id, current_user.id)
    await db.commit()
    return EntryCreateResponse(entry_id=str(entry.id), job_id=str(job.id))


@router.post("/items/{item_id}")
async def update_classification_item(
    item_id: str,
    body: ClassificationPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.edited_text is None and body.status is None:
        raise HTTPException(status_code=400, detail="edited_text or status is required")
    if body.status is not None and body.status not in {"open", "done", "dismissed"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    classification, _entry = await _get_owned_classification(db, item_id, current_user.id)
    if body.edited_text is not None:
        classification.edited_text = body.edited_text.strip() or None
        classification.user_override = True
    if body.status is not None:
        classification.status = body.status
        classification.user_override = True

    if _entry.local_date:
        await _mark_weekly_audits_stale(db, current_user.id, _entry.local_date)
    await db.commit()
    return {"ok": True}


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classification_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    classification, _entry = await _get_owned_classification(db, item_id, current_user.id)
    classification.status = "dismissed"
    classification.user_override = True
    if _entry.local_date:
        await _mark_weekly_audits_stale(db, current_user.id, _entry.local_date)
    await db.commit()


@router.get("/weekly/suggestion", response_model=WeeklySuggestionResponse)
async def get_weekly_suggestion(
    week_start: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_week = _parse_week_start(week_start)
    week_end = target_week + timedelta(days=6)
    entries = await _fetch_weekly_entries(db, current_user.id, target_week, week_end)
    return WeeklySuggestionResponse(
        show=len(entries) >= 3,
        week_start=target_week.isoformat(),
        week_end=week_end.isoformat(),
        entry_count=len(entries),
    )


@router.get("/weekly/{week_start}", response_model=WeeklySummaryResponse)
async def get_weekly_summary(
    week_start: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_week = _parse_week_start(week_start)
    cached = await _get_cached_miniapp_weekly(db, current_user.id, target_week)
    if cached is None:
        raise HTTPException(status_code=404, detail="Weekly summary not found")
    return cached


@router.post("/weekly", response_model=WeeklySummaryResponse)
async def create_weekly_summary(
    body: WeeklyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_week = _parse_week_start(body.week_start)

    if not body.force:
        cached = await _get_cached_miniapp_weekly(db, current_user.id, target_week)
        if cached is not None and not cached.stale:
            return cached

    regen_count = await _count_weekly_regens(db, current_user.id, target_week)
    if body.force and regen_count >= 5:
        raise HTTPException(status_code=429, detail="这个礼拜已经理了好几次了，下次再来。")

    week_end = target_week + timedelta(days=6)
    entries = await _fetch_weekly_entries(db, current_user.id, target_week, week_end)
    if len(entries) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 entries for a weekly summary")

    summary = await _build_miniapp_weekly_summary(entries, target_week, week_end, cached=False)
    summary.regen_count = regen_count + 1
    report_payload = summary.model_dump(exclude={"stale", "regen_count"})
    db.add(AuditResult(
        user_id=current_user.id,
        audit_date=target_week,
        audit_type="miniapp_weekly",
        entries_count=len(entries),
        breakdown_json=None,
        audit_text=summary.family_share_text,
        report_json=json.dumps(report_payload, ensure_ascii=False),
        is_stale=False,
    ))
    await db.commit()
    logger.info("[brief-weekly] generated weekly for user %s week %s (force=%s)", current_user.id, target_week, body.force)
    return summary


@router.post("/share/cards", response_model=ShareCardResponse)
async def create_share_card(
    body: ShareCardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.date:
        try:
            local_date = datetime.strptime(body.date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
        daily_result = await db.execute(
            select(Entry)
            .where(Entry.user_id == current_user.id, Entry.local_date == local_date)
            .options(selectinload(Entry.classifications), selectinload(Entry.jobs))
            .order_by(Entry.created_at.asc())
        )
        result = _daily_result(_completed_entries(daily_result.scalars().unique().all()), body.date)
        if not result.entries:
            raise HTTPException(status_code=404, detail="No shareable entries for this date")
    elif body.entry_id:
        entry = await _get_owned_entry(db, body.entry_id, current_user.id)
        result = _entry_result(entry)
    else:
        raise HTTPException(status_code=400, detail="date or entry_id is required")

    share_id = jwt.encode(
        {
            "entry_id": result.entry_id,
            "date": result.date,
            "summary": result.summary,
            "open_loop_count": len(result.open_loops),
            "created_at": result.created_at,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return ShareCardResponse(
        card=ShareCard(
            share_id=share_id,
            title="今天已经整理清爽了",
            summary=result.summary,
            open_loop_count=len(result.open_loops),
        )
    )


@router.get("/share/cards/{share_id}", response_model=SharedBrief)
async def get_share_card(share_id: str):
    try:
        payload = jwt.decode(share_id, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=404, detail="Share card not found")
    return SharedBrief(
        share_id=share_id,
        summary=payload.get("summary", ""),
        open_loop_count=int(payload.get("open_loop_count", 0)),
        created_at=payload.get("created_at", ""),
    )


async def _exchange_wechat_code(code: str) -> Dict[str, str]:
    if settings.MINIAPP_DEV_OPENID and not settings.WECHAT_SECRET:
        return {"openid": settings.MINIAPP_DEV_OPENID}

    if not settings.WECHAT_APPID or not settings.WECHAT_SECRET:
        raise HTTPException(status_code=500, detail="WeChat app credentials are not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": settings.WECHAT_APPID,
                "secret": settings.WECHAT_SECRET,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
    data = response.json()
    if data.get("errcode"):
        raise HTTPException(status_code=401, detail=f"WeChat login failed: {data.get('errmsg')}")
    return data


async def _mark_weekly_audits_stale(db: AsyncSession, user_id: int, local_date: date_cls) -> None:
    week_start = _week_start(local_date)
    result = await db.execute(
        select(AuditResult).where(
            AuditResult.user_id == user_id,
            AuditResult.audit_date == week_start,
            AuditResult.audit_type.in_(["weekly", "miniapp_weekly"]),
            AuditResult.is_stale.is_(False),
        )
    )
    for audit in result.scalars().all():
        audit.is_stale = True


async def _get_owned_entry(db: AsyncSession, entry_id: str, user_id: int) -> Entry:
    entry_uuid = _parse_uuid(entry_id, "entry_id")
    result = await db.execute(
        select(Entry)
        .where(Entry.id == entry_uuid, Entry.user_id == user_id)
        .options(selectinload(Entry.classifications), selectinload(Entry.jobs))
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


async def _get_owned_classification(
    db: AsyncSession,
    item_id: str,
    user_id: int,
) -> tuple[EntryClassification, Entry]:
    item_uuid = _parse_uuid(item_id, "item_id")
    result = await db.execute(
        select(EntryClassification, Entry)
        .join(Entry, EntryClassification.entry_id == Entry.id)
        .where(EntryClassification.id == item_uuid, Entry.user_id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return row


def _parse_week_start(value: str) -> date_cls:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid week_start format")
    return _week_start(parsed)


def _week_start(day: date_cls) -> date_cls:
    return day - timedelta(days=day.weekday())


async def _fetch_weekly_entries(
    db: AsyncSession,
    user_id: int,
    week_start: date_cls,
    week_end: date_cls,
) -> List[Entry]:
    result = await db.execute(
        select(Entry)
        .where(
            Entry.user_id == user_id,
            Entry.local_date >= week_start,
            Entry.local_date <= week_end,
        )
        .options(selectinload(Entry.classifications), selectinload(Entry.jobs))
        .order_by(Entry.local_date.asc(), Entry.created_at.asc())
    )
    return _completed_entries(result.scalars().unique().all())


async def _get_cached_miniapp_weekly(
    db: AsyncSession,
    user_id: int,
    week_start: date_cls,
) -> Optional[WeeklySummaryResponse]:
    # Phase 1: try fresh (non-stale) record
    result = await db.execute(
        select(AuditResult)
        .where(
            AuditResult.user_id == user_id,
            AuditResult.audit_date == week_start,
            AuditResult.audit_type == "miniapp_weekly",
            AuditResult.is_stale.is_(False),
            AuditResult.report_json.isnot(None),
        )
        .order_by(AuditResult.generated_at.desc())
    )
    cached = result.scalars().first()
    is_stale = False

    # Phase 2: fall back to most recent stale record
    if cached is None:
        stale_result = await db.execute(
            select(AuditResult)
            .where(
                AuditResult.user_id == user_id,
                AuditResult.audit_date == week_start,
                AuditResult.audit_type == "miniapp_weekly",
                AuditResult.is_stale.is_(True),
                AuditResult.report_json.isnot(None),
            )
            .order_by(AuditResult.generated_at.desc())
        )
        cached = stale_result.scalars().first()
        is_stale = True

    if cached is None or not cached.report_json:
        return None

    regen_count = await _count_weekly_regens(db, user_id, week_start)

    try:
        payload = json.loads(cached.report_json)
        payload["cached"] = True
        payload["stale"] = is_stale
        payload["regen_count"] = regen_count
        return WeeklySummaryResponse(**payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.error("[brief-weekly] JSONDecodeError in _get_cached_miniapp_weekly for user %s week %s", user_id, week_start)
        return None


async def _count_weekly_regens(
    db: AsyncSession,
    user_id: int,
    week_start: date_cls,
) -> int:
    result = await db.execute(
        select(func.count()).select_from(AuditResult).where(
            AuditResult.user_id == user_id,
            AuditResult.audit_date == week_start,
            AuditResult.audit_type == "miniapp_weekly",
        )
    )
    return result.scalar() or 0


def _entry_result(entry: Entry) -> EntryResultResponse:
    date = entry.local_date.isoformat() if entry.local_date else None
    return _daily_result([entry], date)


def _completed_entries(entries: List[Entry]) -> List[Entry]:
    return [
        entry
        for entry in entries
        if (entry.transcript or entry.classifications)
        and _latest_job_status(entry) == JobStatus.DONE.value
    ]


def _daily_result(entries: List[Entry], date: Optional[str]) -> EntryResultResponse:
    entries = sorted(entries, key=lambda item: item.created_at)
    primary_entry = entries[-1] if entries else None
    all_classifications = [
        classification
        for entry in entries
        for classification in sorted(entry.classifications, key=lambda item: item.display_order)
        if classification.display_text and classification.status != "dismissed"
    ]
    lines = [c.display_text for c in all_classifications if c.display_text]
    transcript_lines = [entry.transcript for entry in entries if entry.transcript]
    transcript = " ".join(transcript_lines)
    summary = _daily_summary(entries, lines)
    category_groups = _category_groups(all_classifications)
    open_loops = [
        c.display_text
        for c in all_classifications
        if c.display_text and c.category in {"TODO", "EXPERIMENT"}
    ][:8]
    entry_items = [_entry_item(entry) for entry in entries]

    return EntryResultResponse(
        entry_id=str(primary_entry.id) if primary_entry else "",
        result_id=str(primary_entry.id) if primary_entry else None,
        cloud_file_id=(
            primary_entry.raw_audio_key
            if primary_entry and primary_entry.raw_audio_key and primary_entry.raw_audio_key.startswith("cloud://")
            else None
        ),
        date=date,
        created_at=primary_entry.created_at.isoformat() if primary_entry else datetime.now(timezone.utc).isoformat(),
        summary=summary if summary else _one_sentence(transcript),
        key_points=lines[:8],
        open_loops=open_loops,
        entries=entry_items,
        category_groups=category_groups,
    )


async def _generate_opening_sentence(labels: List[str], items: List[str]) -> str:
    label_str = "、".join(labels[:3]) if labels else "日常生活"
    prompt = f"用温暖的沪语风格写一句话，总结这个礼拜用户主要做了：{label_str}。不超过50个字。"
    response = await get_chat_client().chat.completions.create(
        model=chat_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    text = response.choices[0].message.content or ""
    for char in ("*", "_", "#"):
        text = text.replace(char, "")
    return text.strip() or "这个礼拜，你讲过的话已经帮你整理好了。"


async def _build_miniapp_weekly_summary(
    entries: List[Entry],
    week_start: date_cls,
    week_end: date_cls,
    cached: bool = False,
) -> WeeklySummaryResponse:
    visible_classifications = [
        classification
        for entry in entries
        for classification in sorted(entry.classifications, key=lambda item: item.display_order)
        if classification.display_text and classification.status != "dismissed"
    ]
    grouped: Dict[str, List[str]] = {}
    for classification in visible_classifications:
        category = classification.category if classification.category else "REFLECTION"
        grouped.setdefault(category, []).append(classification.display_text)

    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (0 if item[0] in {"TODO", "MAITAISHAO", "FAMILY"} else 1, -len(item[1])),
    )
    main_things = [
        WeeklyMainThing(
            title=_weekly_thing_title(category),
            body=_weekly_thing_body(category, items),
        )
        for category, items in ordered_groups
        if category != "TODO"
    ][:3]
    if not main_things:
        transcript_snippets = [entry.transcript for entry in entries if entry.transcript]
        main_things = [
            WeeklyMainThing(
                title="这礼拜讲过几件事体",
                body=_join_examples(transcript_snippets, "讲过的话已经放在一起，方便回头看。"),
            )
        ]

    remember_items = [
        text
        for classification in visible_classifications
        if classification.category == "TODO"
        for text in [classification.display_text]
    ][:5]
    top_labels = [_category_label(category) for category, _items in ordered_groups[:3]]
    display_items = [c.display_text for c in visible_classifications if c.display_text][:5]

    try:
        opening = await asyncio.wait_for(
            _generate_opening_sentence(top_labels, display_items),
            timeout=3.0,
        )
    except Exception:
        opening = "这个礼拜，你讲过的话已经帮你整理好了。"

    family_share_text = _weekly_family_share_text(top_labels, remember_items)

    return WeeklySummaryResponse(
        title="上个礼拜的事体",
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        date_range=f"{week_start.month}月{week_start.day}日到{week_end.month}月{week_end.day}日",
        opening=opening,
        main_things=main_things,
        remember_items=remember_items,
        family_share_text=family_share_text,
        next_week_nudge="想到事情就直接讲，不用等想清楚。讲过了，我再帮你理清爽。",
        generated_at=datetime.now(timezone.utc).isoformat(),
        cached=cached,
    )


def _weekly_thing_title(category: str) -> str:
    label = _category_label(category)
    titles = {
        "MAITAISHAO": "买汰烧和吃饭的事讲得比较多",
        "FAMILY": "家里人的事放在心上",
        "EARNING": "办过的事体已经放好",
        "LEARNING": "这礼拜也有学到和想明白的事",
        "RELAXING": "休息和放松也记下来了",
        "EXPERIMENT": "有几件事可以试试看",
        "REFLECTION": "有些想法值得留着回头看",
        "TIME_RECORD": "这礼拜的时间也记了一些",
    }
    return titles.get(category, f"{label}讲得比较多")


def _weekly_thing_body(category: str, items: List[str]) -> str:
    fallback = "这些话已经帮你整理在一起，回头看会清楚一点。"
    examples = _join_examples(items, fallback)
    if category == "MAITAISHAO":
        return f"你提到{examples}，家里吃饭安排不少。"
    if category == "FAMILY":
        return f"你提到{examples}，这些都是跟家里人有关的事。"
    if category == "EXPERIMENT":
        return f"你提到{examples}，可以留着之后慢慢试。"
    if category == "REFLECTION":
        return f"你提到{examples}，这些想法以后回头看也有用。"
    return f"你提到{examples}，我先帮你放在这一类。"


def _weekly_family_share_text(labels: List[str], remember_items: List[str]) -> str:
    if labels:
        text = f"上个礼拜主要讲了{'、'.join(labels[:3])}"
    else:
        text = "上个礼拜讲过的几件事已经整理好了"
    if remember_items:
        return text + f"。还有{len(remember_items)}件事要记得跟进，我已经帮你列出来了。"
    return text + "。事情已经放在一起，看起来清爽一点。"


def _join_examples(items: List[str], fallback: str) -> str:
    clean_items = ["".join((item or "").split()) for item in items if item]
    clean_items = [item[:36] for item in clean_items if item]
    if not clean_items:
        return fallback
    if len(clean_items) == 1:
        return clean_items[0]
    return "、".join(clean_items[:3])


def _entry_item(entry: Entry) -> Dict[str, Any]:
    categories = [
        {
            "id": str(classification.id),
            "text": classification.display_text,
            "category": classification.category,
            "estimated_minutes": classification.estimated_minutes,
        }
        for classification in sorted(entry.classifications, key=lambda item: item.display_order)
        if classification.display_text and classification.status != "dismissed"
    ]
    return {
        "id": str(entry.id),
        "transcript": entry.transcript,
        "local_date": entry.local_date.isoformat() if entry.local_date else None,
        "created_at": entry.created_at.isoformat(),
        "duration_seconds": entry.duration_seconds,
        "categories": categories,
    }


def _daily_summary(entries: List[Entry], lines: List[str]) -> str:
    if not entries:
        return "今天还没有记录。"
    if len(entries) == 1 and len(lines) <= 1:
        return lines[0] if lines else _one_sentence(entries[0].transcript or "这段已经整理清爽了。")
    return "今天主要讲了这些事。"


def _category_groups(classifications: List[EntryClassification]) -> List[Dict[str, Any]]:
    category_order = ["EARNING", "MAITAISHAO", "FAMILY", "LEARNING", "RELAXING", "TODO", "EXPERIMENT", "REFLECTION"]
    grouped: Dict[str, List[Dict[str, Any]]] = {category: [] for category in category_order}
    for classification in classifications:
        category = classification.category if classification.category in grouped else "REFLECTION"
        grouped[category].append(
            {
                "id": str(classification.id),
                "text": classification.display_text,
                "category": category,
                "estimated_minutes": classification.estimated_minutes,
            }
        )

    return [
        {
            "category": category,
            "label": _category_label(category),
            "items": items,
        }
        for category in category_order
        if (items := grouped.get(category))
    ]


def _category_label(category: str) -> str:
    labels = {
        "TODO": "还要做",
        "MAITAISHAO": "买汰烧",
        "EXPERIMENT": "可以试试",
        "REFLECTION": "感悟",
        "EARNING": "办事体",
        "LEARNING": "学到的",
        "FAMILY": "照顾家人",
        "RELAXING": "休息",
        "TIME_RECORD": "时间记录",
    }
    return labels.get(category, category)


def _one_sentence(text: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return "这段已经整理清爽了。"
    for sep in ["。", "！", "？", ".", "!", "?"]:
        if sep in compact:
            return compact.split(sep)[0][:120] + sep
    return compact[:120]


def _miniapp_job_status(status_value) -> str:
    value = _job_status_value(status_value)
    if value == JobStatus.PENDING.value:
        return "queued"
    if value == JobStatus.PROCESSING.value:
        return "processing"
    if value == JobStatus.DONE.value:
        return "done"
    return "failed"


def _job_progress(job: Job) -> int:
    status_value = _job_status_value(job.status)
    if status_value == JobStatus.DONE.value:
        return 100
    if status_value == JobStatus.FAILED.value:
        return 100
    if status_value == JobStatus.PROCESSING.value:
        if job.step == "transcribing":
            return 45
        if job.step == "classifying":
            return 75
        return 35
    return 15


def _job_status_value(status_value) -> str:
    return status_value.value if hasattr(status_value, "value") else status_value


def _latest_job_status(entry: Entry) -> Optional[str]:
    if not entry.jobs:
        return None
    latest = max(entry.jobs, key=lambda job: job.created_at or datetime.min)
    return _job_status_value(latest.status)


def _job_error_code(job: Job) -> Optional[str]:
    if job.status != JobStatus.FAILED:
        return None
    if job.error and ":" in job.error:
        prefix = job.error.split(":", 1)[0].strip()
        if prefix:
            return prefix[:80]
    return "job_failed"


def _job_error_message(job: Job) -> Optional[str]:
    if job.status != JobStatus.FAILED:
        return None
    if not job.error:
        return "Job failed without a stored error. Check CloudBase service logs."
    return _sanitize_job_error(job.error)


def _sanitize_job_error(error: str) -> str:
    text = " ".join(error.split())
    sensitive_markers = ["api key", "authorization", "bearer ", "secret"]
    if any(marker in text.lower() for marker in sensitive_markers):
        if settings.MINIAPP_DEBUG_ERRORS:
            return text[:500]
        return "处理失败：后端密钥或第三方服务配置异常。"
    return text[:500]


def _content_type_to_suffix(content_type: str) -> str:
    mapping = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
    }
    return mapping.get(content_type.split(";")[0].strip().lower(), ".mp3")


def _entry_id_from_object_key(object_key: str) -> Optional[uuid.UUID]:
    try:
        name = object_key.rsplit("/", 1)[-1].split(".", 1)[0]
        return uuid.UUID(name)
    except (ValueError, IndexError):
        return None


def _parse_uuid(value: str, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {name}")
