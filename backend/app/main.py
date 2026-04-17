import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import init_db, engine
from .settings import settings

from .routes.v1 import router as v1_router
from .routes.miniapp import router as miniapp_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database and storage")
    if settings.ENVIRONMENT != "test":
        await init_db()

    if not settings.USE_CLOUDBASE_STORAGE:
        # Ensure the S3-compatible storage bucket exists (no-op if already present).
        try:
            from .services.storage import ensure_bucket
            await ensure_bucket()
        except Exception as exc:
            logger.warning(f"Storage bucket init skipped: {exc}")

    # Start embedded worker loop as a background task
    from .services.worker import run_worker
    worker_task = asyncio.create_task(run_worker())
    logger.info("Embedded worker started")

    yield

    logger.info("Shutting down")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(
    title="Time Logger API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "Content-Type"],
    expose_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(v1_router, prefix="/api")
app.include_router(miniapp_router)


# ── Utility endpoints ─────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": app.version,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/")
async def root():
    return {"message": "Time Logger API", "docs": "/docs"}


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {request.method} {request.url} — {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
