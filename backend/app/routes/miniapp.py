import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, HttpUrl
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..models.classification import EntryClassification
from ..models.entry import Entry
from ..models.jobs import Job, JobStatus
from ..models.user import User
from ..services import queue as queue_svc
from ..services import storage as storage_svc
from ..settings import settings
from ..utils.auth import create_access_token, get_current_user

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
    cloud_temp_url: Optional[HttpUrl] = None
    duration_ms: int
    local_date: Optional[str] = None
    client_meta: Dict[str, Any] = {}


class EntryCreateResponse(BaseModel):
    entry_id: str
    job_id: str


class JobResultPreview(BaseModel):
    summary: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    entry_id: Optional[str] = None
    status: str
    progress: int
    step: Optional[str] = None
    error_code: Optional[str] = None
    result_preview: Optional[JobResultPreview] = None


class EntryResultResponse(BaseModel):
    entry_id: str
    result_id: Optional[str] = None
    cloud_file_id: Optional[str] = None
    created_at: str
    summary: str
    key_points: List[str]
    open_loops: List[str]


class ShareCardRequest(BaseModel):
    entry_id: str


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
        user=MiniappUser(id=str(user.id), display_name="Brief"),
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
        status=_miniapp_job_status(job.status),
        progress=_job_progress(job),
        step=job.step,
        error_code="job_failed" if job.status == JobStatus.FAILED else None,
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


@router.post("/share/cards", response_model=ShareCardResponse)
async def create_share_card(
    body: ShareCardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = await _get_owned_entry(db, body.entry_id, current_user.id)
    result = _entry_result(entry)
    share_id = jwt.encode(
        {
            "entry_id": result.entry_id,
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
            title="我的 Brief 摘要",
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


def _entry_result(entry: Entry) -> EntryResultResponse:
    lines = [c.display_text for c in entry.classifications if c.display_text]
    transcript = entry.transcript or ""
    summary_source = transcript or "Brief 已整理这段语音。"
    key_points = lines[:5]
    if not key_points and transcript:
        key_points = [_one_sentence(transcript)]
    open_loops = [
        c.display_text
        for c in entry.classifications
        if c.display_text and c.category in {"TODO", "EXPERIMENT", "REFLECTION"}
    ][:5]
    return EntryResultResponse(
        entry_id=str(entry.id),
        result_id=str(entry.id),
        cloud_file_id=entry.raw_audio_key if entry.raw_audio_key and entry.raw_audio_key.startswith("cloud://") else None,
        created_at=entry.created_at.isoformat(),
        summary=_one_sentence(summary_source),
        key_points=key_points[:5],
        open_loops=open_loops,
    )


def _one_sentence(text: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return "Brief 已整理这段语音。"
    for sep in ["。", "！", "？", ".", "!", "?"]:
        if sep in compact:
            return compact.split(sep)[0][:120] + sep
    return compact[:120]


def _miniapp_job_status(status_value) -> str:
    value = status_value.value if hasattr(status_value, "value") else status_value
    if value == JobStatus.PENDING.value:
        return "queued"
    if value == JobStatus.PROCESSING.value:
        return "processing"
    if value == JobStatus.DONE.value:
        return "done"
    return "failed"


def _job_progress(job: Job) -> int:
    status_value = job.status.value if hasattr(job.status, "value") else job.status
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
