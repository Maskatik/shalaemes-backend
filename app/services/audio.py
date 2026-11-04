import wave
from pathlib import Path

FALLBACK_CHUNK_SECONDS = 30.0


def audio_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if rate > 0:
                return frames / rate
    except (wave.Error, EOFError, OSError):
        pass
    return FALLBACK_CHUNK_SECONDS
