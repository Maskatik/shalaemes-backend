from fastapi import APIRouter, Depends

from ..config import Settings
from ..db import connect
from ..deps import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    connection = connect(settings.db_path)
    try:
        connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
    return {
        "status": "ok",
        "asr": settings.asr_provider,
        "llm": settings.llm_provider,
    }
