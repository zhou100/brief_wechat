"""
Object storage abstraction (Cloudflare R2 / MinIO / S3).

All audio files go directly to object storage — the app server never holds
audio bytes in memory beyond the upload request.

Production: Cloudflare R2 (S3-compatible, zero egress fees)
Local dev:  MinIO via docker-compose (S3-compatible)
"""
import logging
from typing import Optional
import aioboto3
from botocore.exceptions import ClientError
from ..settings import settings

logger = logging.getLogger(__name__)

_session: Optional[aioboto3.Session] = None


def _get_session() -> aioboto3.Session:
    global _session
    if _session is None:
        _session = aioboto3.Session(
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )
    return _session


def _client():
    return _get_session().client("s3", endpoint_url=settings.S3_ENDPOINT_URL)


async def ensure_bucket() -> None:
    """
    Verify the audio bucket exists and has CORS configured. Called at startup.

    For MinIO (local dev): auto-creates the bucket if missing.
    For R2 (production): only verifies — R2 buckets are created in the dashboard.
    """
    is_r2 = "r2.cloudflarestorage.com" in settings.S3_ENDPOINT_URL
    async with _client() as s3:
        try:
            await s3.head_bucket(Bucket=settings.S3_BUCKET)
            logger.debug(f"Bucket '{settings.S3_BUCKET}' exists")
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("404", "NoSuchBucket"):
                if is_r2:
                    raise RuntimeError(
                        f"R2 bucket '{settings.S3_BUCKET}' not found. "
                        "Create it in the Cloudflare dashboard first."
                    )
                await s3.create_bucket(Bucket=settings.S3_BUCKET)
                logger.info(f"Created bucket '{settings.S3_BUCKET}'")
            else:
                raise

        # Ensure CORS is configured so browsers can PUT audio directly
        try:
            await s3.put_bucket_cors(
                Bucket=settings.S3_BUCKET,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedOrigins": ["*"],
                            "AllowedMethods": ["PUT", "GET"],
                            "AllowedHeaders": ["*"],
                            "MaxAgeSeconds": 3600,
                        }
                    ]
                },
            )
            logger.info(f"CORS configured for bucket '{settings.S3_BUCKET}'")
        except ClientError as e:
            logger.warning(f"Could not set CORS on bucket: {e}")


async def generate_presigned_put(key: str, content_type: str, expires_in: int = 3600) -> str:
    """
    Return a presigned PUT URL so the client can upload audio directly to
    object storage without routing bytes through the app server.
    """
    async with _client() as s3:
        url = await s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.S3_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
    if settings.S3_PUBLIC_ENDPOINT_URL:
        url = url.replace(settings.S3_ENDPOINT_URL, settings.S3_PUBLIC_ENDPOINT_URL, 1)
    return url


async def generate_presigned_get(key: str, expires_in: int = 3600) -> str:
    """Return a presigned GET URL for reading a stored file."""
    async with _client() as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    return url


async def download_bytes(key: str) -> bytes:
    """Download a file from object storage as raw bytes."""
    async with _client() as s3:
        response = await s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
        async with response["Body"] as stream:
            return await stream.read()


async def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    """Upload raw bytes directly (used internally / for tests)."""
    async with _client() as s3:
        await s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    logger.debug(f"Uploaded {len(data)} bytes to {key}")


async def delete_object(key: str) -> None:
    """Delete a file from object storage."""
    async with _client() as s3:
        await s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
    logger.debug(f"Deleted {key}")


def make_audio_key(user_id: int, entry_id: str, suffix: str = ".webm") -> str:
    """Deterministic object storage key for an audio file."""
    return f"audio/{user_id}/{entry_id}{suffix}"
