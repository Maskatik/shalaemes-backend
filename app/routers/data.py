import shutil

from fastapi import APIRouter, Depends, Response

from ..config import Settings
from ..db import connect
from ..deps import get_settings

router = APIRouter(prefix="/api/data", tags=["data"])


@router.delete("", status_code=204)
def delete_all_data(settings: Settings = Depends(get_settings)) -> Response:
    connection = connect(settings.db_path)
    try:
        connection.execute("DELETE FROM sessions")
        connection.execute("DELETE FROM user_words")
        connection.execute("DELETE FROM user_achievements")
        connection.execute("UPDATE users SET xp = 0, level = 1")
        connection.commit()
    finally:
        connection.close()
    shutil.rmtree(settings.data_dir / "chunks", ignore_errors=True)
    return Response(status_code=204)
