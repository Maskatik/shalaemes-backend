import time
from pathlib import Path

import httpx

from ..config import Settings
from .asr import AsrResult, AsrWord
from .audio import audio_duration_seconds


class RemoteAsr:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def transcribe(self, path: Path, offset_ms: int = 0) -> AsrResult:
        if not self.settings.asr_service_url:
            raise RuntimeError("ASR_SERVICE_URL is not configured")

        url = f"{self.settings.asr_service_url}/transcribe"
        headers = {}
        if self.settings.asr_service_api_key:
            headers["Authorization"] = f"Bearer {self.settings.asr_service_api_key}"

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self.settings.asr_service_timeout, transport=self.transport) as client:
                    with path.open("rb") as handle:
                        response = client.post(
                            url,
                            headers=headers,
                            files={"file": (path.name, handle, "application/octet-stream")},
                            data={"language": self.settings.asr_language},
                        )
                if response.status_code in {502, 503, 504} and attempt == 0:
                    time.sleep(1.0)
                    continue
                if response.status_code == 401:
                    raise RuntimeError("ASR service rejected the API key")
                if response.status_code >= 400:
                    raise RuntimeError(f"ASR service HTTP {response.status_code}: {response.text[:200]}")
                return self._parse(response.json(), path, offset_ms)
            except (httpx.TimeoutException, httpx.TransportError) as error:
                last_error = error
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                raise RuntimeError(f"ASR service unavailable: {error}") from error

        raise RuntimeError(f"ASR service unavailable: {last_error}")

    def _parse(self, data: dict, path: Path, offset_ms: int) -> AsrResult:
        text = str(data.get("text") or "").strip()
        duration = float(data.get("duration_sec") or audio_duration_seconds(path))
        words = []
        for item in data.get("words") or []:
            surface = str(item.get("surface") or "").strip()
            if not surface:
                continue
            start_ms = int(item.get("start_ms", 0)) + offset_ms
            end_ms = int(item.get("end_ms", start_ms)) + offset_ms
            if end_ms <= start_ms:
                end_ms = start_ms + 200
            words.append(AsrWord(surface, start_ms, end_ms))

        if not words and text:
            tokens = text.split()
            step = max(int(duration * 1000 / max(len(tokens), 1)), 1)
            words = [
                AsrWord(token, offset_ms + index * step, offset_ms + (index + 1) * step)
                for index, token in enumerate(tokens)
            ]

        return AsrResult(text=text, words=words, duration_sec=duration)
