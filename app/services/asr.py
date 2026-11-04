from dataclasses import dataclass, field
from pathlib import Path

from .audio import audio_duration_seconds

CANNED_TRANSCRIPT = (
    "Бүгін дедлайн жақындап қалды, сондықтан проектті бітіруім керек. "
    "Короче, бюджет әлі бекітілген жоқ, типа бәрі кешігеді. "
    "Нормально, ертең отчётты тапсырамыз."
)


@dataclass
class AsrWord:
    surface: str
    start_ms: int
    end_ms: int


@dataclass
class AsrResult:
    text: str
    words: list[AsrWord] = field(default_factory=list)
    duration_sec: float = 0.0


class StubAsr:
    def transcribe(self, path: Path, offset_ms: int = 0) -> AsrResult:
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8-sig").strip()
        else:
            text = CANNED_TRANSCRIPT

        duration = audio_duration_seconds(path)
        tokens = text.split()
        step = max(int(duration * 1000 / max(len(tokens), 1)), 1)
        words = [
            AsrWord(
                surface=token,
                start_ms=offset_ms + index * step,
                end_ms=offset_ms + (index + 1) * step,
            )
            for index, token in enumerate(tokens)
        ]
        return AsrResult(text=text, words=words, duration_sec=duration)


def get_asr(settings):
    if settings.asr_provider == "stub":
        return StubAsr()
    if settings.asr_provider == "krasr":
        from .asr_krasr import KrasrAsr

        return KrasrAsr(settings)
    if settings.asr_provider == "remote":
        from .asr_remote import RemoteAsr

        return RemoteAsr(settings)
    raise ValueError(f"Unknown ASR provider: {settings.asr_provider}")
