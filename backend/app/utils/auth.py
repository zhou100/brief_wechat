from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError, jwk
import json
import httpx
from passlib.context import CryptContext
from sqlalchemy import select
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.user import User
from ..db import get_db
from ..settings import settings
import logging

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_user(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    user = await get_user(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


_jwks_cache: dict = {}


def _decode_supabase_jwt(token: str) -> dict:
    """
    Decode a Supabase JWT. Supports HS256 (HMAC) and ES256 (ECC P-256).
    For ES256, fetches the JWKS from Supabase to get the public key.
    """
    # Peek at the header to determine algorithm
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "HS256")

    if alg == "HS256":
        return jwt.decode(
            token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"],
            options={"verify_aud": False},
        )

    if alg == "ES256":
        # Fetch JWKS from Supabase (cached)
        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        if jwks_url not in _jwks_cache:
            resp = httpx.get(jwks_url, timeout=10)
            resp.raise_for_status()
            _jwks_cache[jwks_url] = resp.json()

        jwks = _jwks_cache[jwks_url]
        kid = header.get("kid")
        key_data = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key_data = k
                break
        if not key_data:
            raise JWTError(f"No matching key for kid={kid}")

        public_key = jwk.construct(key_data, algorithm="ES256")
        return jwt.decode(
            token, public_key, algorithms=["ES256"],
            options={"verify_aud": False},
        )

    raise JWTError(f"Unsupported JWT algorithm: {alg}")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    """
    Validate a JWT and return the current user.

    Supports three token types (tried in order):
    1. Supabase JWT (if SUPABASE_JWT_SECRET is configured) — sub is Supabase UUID
    2. v1 app JWT — sub is integer user_id
    3. Legacy app JWT — sub is email
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    if token.startswith("Bearer "):
        token = token[7:]

    # ── Try Supabase JWT first ────────────────────────────────────────────
    if settings.SUPABASE_JWT_SECRET:
        try:
            payload = _decode_supabase_jwt(token)
            supabase_id = payload.get("sub")
            email = payload.get("email")
            if supabase_id:
                user = await User.get_by_supabase_id(db, supabase_id)
                if not user and email:
                    # Auto-create user on first Supabase login
                    user = await get_user(db, email)
                    if user:
                        user.supabase_id = supabase_id
                        user.auth_provider = "supabase"
                    else:
                        user = User(
                            email=email,
                            supabase_id=supabase_id,
                            auth_provider="supabase",
                        )
                        db.add(user)
                    await db.flush()
                if user:
                    return user
        except JWTError:
            pass  # Fall through to app JWT

    # ── Try app JWT ──────────────────────────────────────────────────────
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: str = payload.get("sub")
        if not sub:
            raise credentials_exception

        # v1 tokens use integer user_id as sub; legacy tokens use email
        try:
            user_id = int(sub)
            user = await User.get_by_id(db, user_id)
        except (ValueError, TypeError):
            user = await get_user(db, sub)

        if user is None:
            raise credentials_exception
        return user

    except JWTError as e:
        logger.debug(f"JWT validation failed: {e}")
        raise credentials_exception
