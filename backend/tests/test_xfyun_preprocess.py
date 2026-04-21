import math
import struct

from app.services import xfyun_transcription


def _pcm_silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(seconds * 16000)


def _pcm_tone(seconds: float, amplitude: int = 1000) -> bytes:
    samples = []
    for index in range(int(seconds * 16000)):
        value = int(amplitude * math.sin(2 * math.pi * 440 * index / 16000))
        samples.append(struct.pack("<h", value))
    return b"".join(samples)


def test_remove_long_silence_keeps_speech_and_drops_empty_audio():
    pcm = _pcm_silence(2.0) + _pcm_tone(1.0) + _pcm_silence(2.0)

    compacted = xfyun_transcription._remove_long_silence(pcm)

    assert 1.0 * 16000 * 2 < len(compacted) < len(pcm)
    assert xfyun_transcription._remove_long_silence(_pcm_silence(1.0)) == b""


def test_prepare_segments_splits_below_xfyun_limit(monkeypatch):
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_MAX_SEGMENT_SECONDS", 1.0)
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_SILENCE_RMS_THRESHOLD", 1)

    segments = xfyun_transcription._prepare_segments(_pcm_tone(2.5))

    assert len(segments) == 3
    assert all(len(segment) <= 16000 * 2 for segment in segments)


def test_prepare_segments_falls_back_to_original_when_no_speech_detected(monkeypatch):
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_SILENCE_RMS_THRESHOLD", 10_000)
    pcm = _pcm_tone(0.5, amplitude=100)

    segments = xfyun_transcription._prepare_segments(pcm)

    assert segments == [pcm]


def test_prepare_segments_splits_fallback_audio_below_xfyun_limit(monkeypatch):
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_MAX_SEGMENT_SECONDS", 1.0)
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_SILENCE_RMS_THRESHOLD", 10_000)
    pcm = _pcm_tone(2.5, amplitude=100)

    segments = xfyun_transcription._prepare_segments(pcm)

    assert len(segments) == 3
    assert [len(segment) for segment in segments] == [32000, 32000, 16000]


def test_prepare_segments_prefers_silence_boundaries(monkeypatch):
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_MAX_SEGMENT_SECONDS", 2.0)
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_SILENCE_RMS_THRESHOLD", 1)
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_SILENCE_SPLIT_SECONDS", 0.5)
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_KEEP_SILENCE_SECONDS", 0.0)
    first = _pcm_tone(1.0)
    second = _pcm_tone(1.0)
    pcm = first + _pcm_silence(1.0) + second

    segments = xfyun_transcription._prepare_segments(pcm)

    assert segments == [first + second]


def test_prepare_segments_hard_splits_single_oversized_speech_chunk(monkeypatch):
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_MAX_SEGMENT_SECONDS", 1.0)
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_SILENCE_RMS_THRESHOLD", 1)
    monkeypatch.setattr(xfyun_transcription.settings, "XFYUN_KEEP_SILENCE_SECONDS", 0.0)

    segments = xfyun_transcription._prepare_segments(_pcm_tone(2.5))

    assert len(segments) == 3
    assert [len(segment) for segment in segments] == [32000, 32000, 16000]


def test_frame_size_matches_xfyun_pcm_send_recommendation():
    assert xfyun_transcription._FRAME_SIZE == 1280
