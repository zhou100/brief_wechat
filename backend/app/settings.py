"""
Application settings — all configuration sourced from environment variables.
"""
from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── JWT ──────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    # Access tokens are short-lived; refresh tokens stored in DB are long-lived.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 240
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/brief_wechat"
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test.db"
    DB_ECHO: bool = False           # Never True in production

    # ── OpenAI ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = "dummy"
    MOONSHOT_API_KEY: str = ""
    MOONSHOT_BASE_URL: str = "https://api.moonshot.cn/v1"
    MOONSHOT_MODEL: str = "kimi-k2.5"

    XFYUN_APP_ID: str = ""
    XFYUN_API_KEY: str = ""
    XFYUN_API_SECRET: str = ""
    XFYUN_IAT_URL: str = "wss://iat.cn-huabei-1.xf-yun.com/v1"

    # ── Object Storage (Cloudflare R2 / S3-compatible) ─────────────────────────
    # R2 endpoint format: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
    # For local dev with MinIO: http://minio:9000
    S3_ENDPOINT_URL: str = "http://minio:9000"
    # Public URL reachable by browsers — replaces S3_ENDPOINT_URL in presigned URLs.
    # For R2: same as S3_ENDPOINT_URL. For local MinIO: http://localhost:9000
    S3_PUBLIC_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "time-logger-audio"
    S3_REGION: str = "auto"  # R2 uses "auto"; MinIO uses "us-east-1"

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Accepts comma-separated string or JSON array in env vars
    ALLOWED_ORIGINS_STR: str = "http://localhost:3000"

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        import json
        v = self.ALLOWED_ORIGINS_STR.strip()
        if v.startswith("["):
            return json.loads(v)
        return [o.strip() for o in v.split(",") if o.strip()]

    # ── Supabase ───────────────────────────────────────────────────────────────
    SUPABASE_URL: str = ""           # e.g. https://xyz.supabase.co
    SUPABASE_ANON_KEY: str = ""      # public anon key
    SUPABASE_JWT_SECRET: str = ""    # JWT secret for RS256 verification (Settings > API > JWT Secret)

    # ── Google OAuth (legacy — migrating to Supabase OAuth) ─────────────────
    GOOGLE_CLIENT_ID: str = ""  # empty = Google auth disabled

    WECHAT_APPID: str = ""
    WECHAT_SECRET: str = ""
    MINIAPP_PUBLIC_BASE_URL: str = ""
    MINIAPP_DEV_OPENID: str = ""
    MINIAPP_DEBUG_ERRORS: bool = False
    USE_CLOUDBASE_STORAGE: bool = False

    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "allow",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
