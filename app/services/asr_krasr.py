import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from ..config import Settings
from .asr import AsrResult, AsrWord

_PIPELINE = None
_PIPELINE_LOCK = threading.Lock()
_TRANSCRIBE_LOCK = threading.Lock()


def resolve_device(choice: str, torch_module) -> str:
    if choice in {"cpu", "cuda"}:
        return choice
    if torch_module.cuda.is_available():
        properties = torch_module.cuda.get_device_properties(0)
        if properties.total_memory >= 3.5 * 1024**3:
            return "cuda"
    return "cpu"


def build_generate_kwargs(duration_sec: float, language: str | None) -> dict:
    if duration_sec <= 5:
        max_new_tokens = 40
    elif duration_sec <= 10:
        max_new_tokens = 64
    elif duration_sec <= 15:
        max_new_tokens = 80
    elif duration_sec <= 20:
        max_new_tokens = 96
    elif duration_sec <= 25:
        max_new_tokens = 112
    else:
        max_new_tokens = 128

    kwargs = {
        "task": "transcribe",
        "num_beams": 3,
        "max_new_tokens": max_new_tokens,
        "no_repeat_ngram_size": 4,
        "repetition_penalty": 1.12,
    }
    if language:
        kwargs["language"] = language
    return kwargs


def words_from_result(result: dict, offset_ms: int, duration_sec: float) -> list[AsrWord]:
    chunks = result.get("chunks") or []
    if chunks:
        words = []
        for chunk in chunks:
            text = (chunk.get("text") or "").strip()
            if not text:
                continue
            timestamp = chunk.get("timestamp") or (None, None)
            start = timestamp[0] if len(timestamp) > 0 else None
            end = timestamp[1] if len(timestamp) > 1 else None
            start_ms = offset_ms + int(round((start or 0.0) * 1000))
            end_ms = offset_ms + int(round(end * 1000)) if end is not None else start_ms + 200
            if end_ms <= start_ms:
                end_ms = start_ms + 200
            words.append(AsrWord(text, start_ms, end_ms))
        return words

    text = (result.get("text") or "").strip()
    tokens = text.split()
    if not tokens:
        return []
    step = max(int(duration_sec * 1000 / len(tokens)), 1)
    return [
        AsrWord(token, offset_ms + index * step, offset_ms + (index + 1) * step)
        for index, token in enumerate(tokens)
    ]


def prepare_audio(source: Path, target: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for ASR but was not found in PATH")
    completed = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(source), "-ac", "1", "-ar", "16000", "-f", "wav", str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {completed.stderr[-500:]}")


def build_pipeline(settings: Settings):
    import torch
    from peft import PeftModel
    from transformers import WhisperForConditionalGeneration, WhisperProcessor, pipeline

    device = resolve_device(settings.asr_device, torch)
    dtype = torch.float16 if device == "cuda" else torch.float32

    model = WhisperForConditionalGeneration.from_pretrained(
        settings.asr_model,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    if settings.asr_adapter:
        model = PeftModel.from_pretrained(model, settings.asr_adapter)
        if device == "cuda":
            model = model.merge_and_unload()

    model.to(device)
    model.eval()
    processor = WhisperProcessor.from_pretrained(settings.asr_model)
    return pipeline(
        task="automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        dtype=dtype,
        device=0 if device == "cuda" else -1,
    )


def get_pipeline(settings: Settings):
    global _PIPELINE
    if _PIPELINE is None:
        with _PIPELINE_LOCK:
            if _PIPELINE is None:
                _PIPELINE = build_pipeline(settings)
    return _PIPELINE


class KrasrAsr:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(self, path: Path, offset_ms: int = 0) -> AsrResult:
        import librosa

        recognizer = get_pipeline(self.settings)
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory) / "audio.wav"
            prepare_audio(path, prepared)
            audio, sample_rate = librosa.load(str(prepared), sr=16000, mono=True)

        duration = len(audio) / sample_rate if sample_rate else 0.0
        with _TRANSCRIBE_LOCK:
            result = recognizer(
                {"array": audio, "sampling_rate": 16000},
                return_timestamps="word",
                generate_kwargs=build_generate_kwargs(duration, self.settings.asr_language),
            )
        text = (result.get("text") or "").strip()
        return AsrResult(text=text, words=words_from_result(result, offset_ms, duration), duration_sec=duration)
