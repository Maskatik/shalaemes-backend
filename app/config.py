import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data"

PROVIDER_DEFAULTS = {
    "deepseek": ("deepseek-chat", "https://api.deepseek.com"),
    "openai": ("gpt-4o-mini", "https://api.openai.com/v1"),
    "openrouter": ("openai/gpt-4o-mini", "https://openrouter.ai/api/v1"),
    "ollama": ("llama3.1", "http://127.0.0.1:11434/v1"),
}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    asr_provider: str
    asr_model: str
    asr_adapter: str
    asr_device: str
    asr_language: str
    asr_service_url: str
    asr_service_api_key: str
    asr_service_timeout: float
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    llm_batch_size: int
    llm_max_tokens: int
    llm_timeout: float
    keep_audio: bool

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> "Settings":
        load_dotenv(BACKEND_DIR / ".env")
        root = Path(data_dir) if data_dir is not None else Path(os.getenv("SHALAEMES_DATA_DIR", DEFAULT_DATA_DIR))
        root.mkdir(parents=True, exist_ok=True)

        llm_provider = os.getenv("LLM_PROVIDER", "stub").lower()
        default_model, default_base_url = PROVIDER_DEFAULTS.get(llm_provider, ("", ""))
        llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
        if llm_provider != "stub" and llm_provider != "ollama" and not llm_api_key:
            raise ValueError(f"LLM_API_KEY is required for LLM_PROVIDER={llm_provider}")

        return cls(
            data_dir=root,
            db_path=root / "shalaemes.db",
            asr_provider=os.getenv("ASR_PROVIDER", "stub").lower(),
            asr_model=os.getenv("ASR_MODEL", "openai/whisper-large-v3"),
            asr_adapter=os.getenv("ASR_ADAPTER", "KRASR/kazakh-russian-asr-whisper-large-v3-lora"),
            asr_device=os.getenv("ASR_DEVICE", "auto").lower(),
            asr_language=os.getenv("ASR_LANGUAGE", "kazakh"),
            asr_service_url=os.getenv("ASR_SERVICE_URL", "").rstrip("/"),
            asr_service_api_key=os.getenv("ASR_SERVICE_API_KEY", ""),
            asr_service_timeout=float(os.getenv("ASR_SERVICE_TIMEOUT", "900")),
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_model=os.getenv("LLM_MODEL", default_model),
            llm_base_url=os.getenv("LLM_BASE_URL", default_base_url),
            llm_batch_size=int(os.getenv("LLM_BATCH_SIZE", "200")),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "8192")),
            llm_timeout=float(os.getenv("LLM_TIMEOUT", "120")),
            keep_audio=os.getenv("KEEP_AUDIO", "0") == "1",
        )
