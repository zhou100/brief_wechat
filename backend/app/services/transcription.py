"""Speech-to-text entry point."""
from __future__ import annotations

from typing import Optional


async def transcribe_audio(
    audio_bytes: bytes,
    suffix: str = ".mp3",
    source_url: Optional[str] = None,
) -> str:
    del source_url  # Kept for the worker call signature; XFYUN uploads audio bytes.
    from .xfyun_transcription import transcribe_audio as transcribe_xfyun

    return await transcribe_xfyun(audio_bytes, suffix)
