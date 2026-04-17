from fastapi import APIRouter
from . import auth, entries, captures

router = APIRouter(prefix="/v1")
router.include_router(auth.router)
router.include_router(entries.router)
router.include_router(captures.router)
