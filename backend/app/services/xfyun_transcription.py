"""
Speech-to-text via iFlytek Spark SLM IAT.

Docs: https://www.xfyun.cn/doc/spark/spark_slm_iat.html
"""
import audioop
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

_FRAME_SIZE = 1280
_SAMPLE_RATE = 16000
_SAMPLE_WIDTH_BYTES = 2
_CHANNELS = 1
_ANALYSIS_FRAME_MS = 20


async def transcribe_audio(audio_bytes: bytes, suffix: str = ".mp3") -> str:
    if not settings.XFYUN_APP_ID or not settings.XFYUN_API_KEY or not settings.XFYUN_API_SECRET:
        raise RuntimeError("xfyun_credentials_missing: XFYUN_APP_ID/API_KEY/API_SECRET are required")
    if not audio_bytes:
        return ""

    pcm_bytes = _convert_to_pcm16k(audio_bytes, suffix)
    segments = _prepare_segments(pcm_bytes)
    if not segments:
        return ""

    transcripts = await _transcribe_pcm_segments(segments)
    return "\n".join(text for text in transcripts if text).strip()


async def _transcribe_pcm_segments(segments: list[bytes]) -> list[str]:
    concurrency = max(1, int(settings.XFYUN_SEGMENT_CONCURRENCY or 1))
    if concurrency == 1 or len(segments) <= 1:
        return [await _transcribe_pcm_segment(segment) for segment in segments]

    semaphore = asyncio.Semaphore(concurrency)

    async def transcribe_with_limit(segment: bytes) -> str:
        async with semaphore:
            return await _transcribe_pcm_segment(segment)

    return await asyncio.gather(*(transcribe_with_limit(segment) for segment in segments))


async def _transcribe_pcm_segment(pcm_bytes: bytes) -> str:
    try:
        return await _transcribe_pcm_segment_once(
            pcm_bytes,
            max(0.0, float(settings.XFYUN_FRAME_INTERVAL_SECONDS or 0.0)),
        )
    except Exception:
        fallback_interval = max(0.0, float(settings.XFYUN_FALLBACK_FRAME_INTERVAL_SECONDS or 0.0))
        primary_interval = max(0.0, float(settings.XFYUN_FRAME_INTERVAL_SECONDS or 0.0))
        if not fallback_interval or fallback_interval <= primary_interval:
            raise
        return await _transcribe_pcm_segment_once(pcm_bytes, fallback_interval)


async def _transcribe_pcm_segment_once(pcm_bytes: bytes, frame_interval: float) -> str:
    fragments: Dict[int, str] = {}
    async with websockets.connect(_build_auth_url(settings.XFYUN_IAT_URL), max_size=16 * 1024 * 1024) as ws:
        sender = asyncio.create_task(_send_audio(ws, pcm_bytes, frame_interval))
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


async def _send_audio(ws, audio_bytes: bytes, frame_interval: float) -> None:
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
        if status != 2 and frame_interval:
            await asyncio.sleep(frame_interval)


def _request_frame(chunk: bytes, seq: int, status: int) -> dict:
    return {
        "header": {"app_id": settings.XFYUN_APP_ID, "status": status},
        "parameter": {
            "iat": {
                "language": "zh_cn",
                "accent": "mulacc",
                "domain": "slm",
                "eos": settings.XFYUN_EOS_MS,
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


def _prepare_segments(pcm_bytes: bytes) -> list[bytes]:
    """Remove long silence and pack speech chunks into API-safe segments."""
    chunks = _speech_chunks(pcm_bytes)
    max_bytes = _seconds_to_bytes(settings.XFYUN_MAX_SEGMENT_SECONDS)
    if not chunks:
        return _split_oversized_chunk(pcm_bytes, max_bytes) if pcm_bytes else []

    if max_bytes <= 0:
        return [b"".join(chunks)]

    segments = []
    current = bytearray()
    for chunk in chunks:
        if len(chunk) > max_bytes:
            if current:
                segments.append(bytes(current))
                current.clear()
            segments.extend(_split_oversized_chunk(chunk, max_bytes))
            continue

        if current and len(current) + len(chunk) > max_bytes:
            segments.append(bytes(current))
            current.clear()
        current.extend(chunk)

    if current:
        segments.append(bytes(current))
    return segments


def _split_oversized_chunk(chunk: bytes, max_bytes: int) -> list[bytes]:
    if not chunk:
        return []
    if max_bytes <= 0:
        return [chunk]
    return [
        chunk[offset:offset + max_bytes]
        for offset in range(0, len(chunk), max_bytes)
        if chunk[offset:offset + max_bytes]
    ]


def _remove_long_silence(pcm_bytes: bytes) -> bytes:
    chunks = _speech_chunks(pcm_bytes)
    if not chunks:
        return b""
    return b"".join(chunks)


def _speech_chunks(pcm_bytes: bytes) -> list[bytes]:
    if not pcm_bytes:
        return []

    frame_bytes = _seconds_to_bytes(_ANALYSIS_FRAME_MS / 1000)
    if frame_bytes <= 0:
        return [pcm_bytes]

    ranges = []
    for start in range(0, len(pcm_bytes), frame_bytes):
        frame = pcm_bytes[start:start + frame_bytes]
        if len(frame) < _SAMPLE_WIDTH_BYTES:
            continue
        if audioop.rms(frame, _SAMPLE_WIDTH_BYTES) > settings.XFYUN_SILENCE_RMS_THRESHOLD:
            ranges.append((start, min(start + len(frame), len(pcm_bytes))))

    if not ranges:
        return []

    split_gap_bytes = _seconds_to_bytes(settings.XFYUN_SILENCE_SPLIT_SECONDS)
    merged = []
    for start, end in ranges:
        if not merged or start - merged[-1][1] > split_gap_bytes:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    keep_bytes = _seconds_to_bytes(settings.XFYUN_KEEP_SILENCE_SECONDS)
    expanded = [
        (
            max(0, start - keep_bytes),
            min(len(pcm_bytes), end + keep_bytes),
        )
        for start, end in merged
    ]
    return [pcm_bytes[start:end] for start, end in expanded]


def _seconds_to_bytes(seconds: float) -> int:
    samples = max(0, int(seconds * _SAMPLE_RATE))
    return samples * _SAMPLE_WIDTH_BYTES * _CHANNELS


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
