from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.services.asr_remote import RemoteAsr


def make_settings() -> Settings:
    return replace(
        Settings.from_env(),
        asr_provider="remote",
        asr_service_url="http://asr.local",
        asr_service_api_key="secret",
        asr_service_timeout=5.0,
    )


def test_remote_asr_parses_words(tmp_path):
    audio = tmp_path / "0000.wav"
    audio.write_bytes(b"fake")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transcribe"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "text": "Сәлем дедлайн",
                "duration_sec": 2.0,
                "words": [{"surface": "дедлайн", "start_ms": 100, "end_ms": 600}],
            },
        )

    result = RemoteAsr(make_settings(), transport=httpx.MockTransport(handler)).transcribe(audio, offset_ms=1000)

    assert result.text == "Сәлем дедлайн"
    assert result.duration_sec == 2.0
    assert result.words[0].surface == "дедлайн"
    assert result.words[0].start_ms == 1100
    assert result.words[0].end_ms == 1600


def test_remote_asr_rejects_bad_key(tmp_path):
    audio = tmp_path / "0000.wav"
    audio.write_bytes(b"fake")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid API key"})

    with pytest.raises(RuntimeError, match="API key"):
        RemoteAsr(make_settings(), transport=httpx.MockTransport(handler)).transcribe(audio)


def test_remote_asr_retries_server_error(tmp_path):
    audio = tmp_path / "0000.wav"
    audio.write_bytes(b"fake")
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, text="starting")
        return httpx.Response(200, json={"text": "дайын", "duration_sec": 1.0, "words": []})

    result = RemoteAsr(make_settings(), transport=httpx.MockTransport(handler)).transcribe(audio)

    assert calls["count"] == 2
    assert result.text == "дайын"
    assert result.words
