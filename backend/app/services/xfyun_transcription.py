"""
Speech-to-text via iFlytek Spark SLM IAT.

Docs: https://www.xfyun.cn/doc/spark/spark_slm_iat.html
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Dict
from urllib.parse import urlencode, urlparse

import websockets

from ..settings import settings

_FRAME_SIZE = 8192
_FRAME_INTERVAL_SECONDS = 0.04


async def transcribe_audio(audio_bytes: bytes, suffix: str = ".mp3") -> str:
    if not settings.XFYUN_APP_ID or not settings.XFYUN_API_KEY or not settings.XFYUN_API_SECRET:
        raise RuntimeError("xfyun_credentials_missing: XFYUN_APP_ID/API_KEY/API_SECRET are required")
    if not audio_bytes:
        return ""

    pcm_bytes = _convert_to_pcm16k(audio_bytes, suffix)
    fragments: Dict[int, str] = {}
    async with websockets.connect(_build_auth_url(settings.XFYUN_IAT_URL), max_size=16 * 1024 * 1024) as ws:
        sender = asyncio.create_task(_send_audio(ws, pcm_bytes))
        try:
            async for raw_message in ws:
                message = json.loads(raw_message)
                header = message.get("header") or {}
                code = int(header.get("code", 0))
                if code != 0:
                    raise RuntimeError(f"xfyun_error_{code}: {header.get('message', 'unknown error')}")

                result = ((message.get("payload") or {}).get("result") or {})
                if result.get("text"):
                    _merge_result(fragments, _decode_result_text(result["text"]))

                if int(header.get("status", 0)) == 2:
                    break
        finally:
            await sender

    return "".join(fragments[index] for index in sorted(fragments)).strip()


def _build_auth_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    host = parsed.netloc
    path = parsed.path or "/v1"
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature_sha = hmac.new(
        settings.XFYUN_API_SECRET.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    authorization_origin = (
        f'api_key="{settings.XFYUN_API_KEY}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )
    query = urlencode({
        "authorization": base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8"),
        "date": date,
        "host": host,
    })
    return f"{raw_url}?{query}"


async def _send_audio(ws, audio_bytes: bytes) -> None:
    seq = 0
    total = len(audio_bytes)
    offset = 0
    while offset < total:
        chunk = audio_bytes[offset:offset + _FRAME_SIZE]
        is_first = offset == 0
        offset += len(chunk)
        status = 0 if is_first else 1
        if offset >= total:
            status = 2

        await ws.send(json.dumps(_request_frame(chunk, seq, status), ensure_ascii=False))
        seq += 1
        if status != 2:
            await asyncio.sleep(_FRAME_INTERVAL_SECONDS)


def _request_frame(chunk: bytes, seq: int, status: int) -> dict:
    return {
        "header": {"app_id": settings.XFYUN_APP_ID, "status": status},
        "parameter": {
            "iat": {
                "language": "zh_cn",
                "accent": "mulacc",
                "domain": "slm",
                "eos": 5000,
                "ptt": 1,
                "nunum": 1,
                "result": {"encoding": "utf8", "compress": "raw", "format": "json"},
            },
        },
        "payload": {
            "audio": {
                "encoding": "raw",
                "sample_rate": 16000,
                "channels": 1,
                "bit_depth": 16,
                "status": status,
                "seq": seq,
                "audio": base64.b64encode(chunk).decode("utf-8"),
            },
        },
    }


def _decode_result_text(text_b64: str) -> dict:
    return json.loads(base64.b64decode(text_b64).decode("utf-8"))


def _merge_result(fragments: Dict[int, str], result: dict) -> None:
    sn = int(result.get("sn", len(fragments) + 1))
    if result.get("pgs") == "rpl" and isinstance(result.get("rg"), list) and len(result["rg"]) == 2:
        start, end = result["rg"]
        for index in range(int(start), int(end) + 1):
            fragments.pop(index, None)

    text = "".join(
        candidate.get("w", "")
        for word in result.get("ws", [])
        for candidate in word.get("cw", [])
    )
    if text:
        fragments[sn] = text


def _convert_to_pcm16k(audio_bytes: bytes, suffix: str) -> bytes:
    input_path = None
    output_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix or ".audio", delete=False) as input_file:
            input_file.write(audio_bytes)
            input_path = input_file.name
        with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as output_file:
            output_path = output_file.name

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                input_path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "unknown ffmpeg error").strip()
            raise RuntimeError(f"audio_convert_failed: {error[:500]}")

        with open(output_path, "rb") as output_file:
            converted = output_file.read()
        if not converted:
            raise RuntimeError("audio_convert_failed: ffmpeg produced empty audio")
        return converted
    finally:
        for path in [input_path, output_path]:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
