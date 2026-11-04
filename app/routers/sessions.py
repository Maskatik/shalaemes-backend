import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile

from ..config import Settings
from ..db import connect, now_iso
from ..deps import get_settings
from ..schemas import ChunkOut, FinishOut, LearnOut, SessionDetail, SessionOut, WordFlagIn, WordOut
from ..services.pipeline import process_session
from ..services.progress import award_xp, evaluate_achievements, level_info

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def top_words_from_summary(summary_json: str | None) -> list[str]:
    if not summary_json:
        return []
    try:
        data = json.loads(summary_json)
    except (TypeError, ValueError):
        return []
    words = [item.get("lemma") for item in data.get("replace", [])[:2]]
    words += [item.get("lemma") for item in data.get("filler", [])[:1]]
    return [word for word in words if word][:3]


def load_session(db_path: Path, session_id: int):
    connection = connect(db_path)
    try:
        return connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    finally:
        connection.close()


def chunk_dir(settings: Settings, session_id: int) -> Path:
    return settings.data_dir / "chunks" / str(session_id)


def audio_chunks(settings: Settings, session_id: int) -> list[Path]:
    directory = chunk_dir(settings, session_id)
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() != ".txt")


@router.post("", response_model=SessionOut, status_code=201)
def create_session(settings: Settings = Depends(get_settings)) -> dict:
    connection = connect(settings.db_path)
    try:
        timestamp = now_iso()
        cursor = connection.execute(
            "INSERT INTO sessions (user_id, started_at, status, created_at) VALUES (1, ?, 'recording', ?)",
            (timestamp, timestamp),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM sessions WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        connection.close()


@router.get("", response_model=list[SessionOut])
def list_sessions(settings: Settings = Depends(get_settings)) -> list[dict]:
    connection = connect(settings.db_path)
    try:
        rows = connection.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["top_words"] = top_words_from_summary(row["summary_json"])
            result.append(item)
        return result
    finally:
        connection.close()


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: int, settings: Settings = Depends(get_settings)) -> dict:
    connection = connect(settings.db_path)
    try:
        row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        words = connection.execute(
            "SELECT idx, surface, lemma, start_ms, end_ms, lang, category, user_flag "
            "FROM transcript_words WHERE session_id = ? ORDER BY idx",
            (session_id,),
        ).fetchall()
    finally:
        connection.close()

    summary = None
    error = None
    if row["summary_json"]:
        data = json.loads(row["summary_json"])
        if "error" in data:
            error = data["error"]
        else:
            summary = data
    result = dict(row)
    result["words"] = [dict(word) for word in words]
    result["summary"] = summary
    result["error"] = error
    result["top_words"] = top_words_from_summary(row["summary_json"])
    return result


@router.patch("/{session_id}/words/{idx}", response_model=WordOut)
def set_word_flag(
    session_id: int,
    idx: int,
    payload: WordFlagIn,
    settings: Settings = Depends(get_settings),
) -> dict:
    connection = connect(settings.db_path)
    try:
        row = connection.execute(
            "SELECT id FROM transcript_words WHERE session_id = ? AND idx = ?",
            (session_id, idx),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Word not found")
        connection.execute(
            "UPDATE transcript_words SET user_flag = ? WHERE session_id = ? AND idx = ?",
            (payload.user_flag, session_id, idx),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT idx, surface, lemma, start_ms, end_ms, lang, category, user_flag "
            "FROM transcript_words WHERE session_id = ? AND idx = ?",
            (session_id, idx),
        ).fetchone()
        return dict(updated)
    finally:
        connection.close()


@router.post("/{session_id}/words/{idx}/learn", response_model=LearnOut)
def learn_word(
    session_id: int,
    idx: int,
    settings: Settings = Depends(get_settings),
) -> LearnOut:
    connection = connect(settings.db_path)
    try:
        word = connection.execute(
            "SELECT w.*, l.id AS lexicon_id FROM transcript_words w "
            "LEFT JOIN lexicon l ON l.lemma = w.lemma "
            "WHERE w.session_id = ? AND w.idx = ?",
            (session_id, idx),
        ).fetchone()
        if word is None:
            raise HTTPException(status_code=404, detail="Word not found")
        if word["category"] not in {"replace", "filler"}:
            raise HTTPException(status_code=400, detail="Only replace and filler words can be learned")

        session = connection.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        user_id = session["user_id"]

        lexicon_id = word["lexicon_id"]
        if lexicon_id is None:
            cursor = connection.execute(
                "INSERT INTO lexicon (lemma, category, meaning_kk, example, created_at) VALUES (?, ?, '', '', ?)",
                (word["lemma"], word["category"], now_iso()),
            )
            lexicon_id = cursor.lastrowid

        existing = connection.execute(
            "SELECT status FROM user_words WHERE user_id = ? AND lexicon_id = ?",
            (user_id, lexicon_id),
        ).fetchone()
        if existing is not None and existing["status"] in {"learned", "used", "consolidated"}:
            user = connection.execute("SELECT xp FROM users WHERE id = ?", (user_id,)).fetchone()
            user_xp = user["xp"] if user else 0
            info = level_info(user_xp)
            return LearnOut(
                lemma=word["lemma"],
                status=existing["status"],
                xp=user_xp,
                level=info["level"],
                level_title=info["title"],
                already_learned=True,
            )

        timestamp = now_iso()
        connection.execute(
            """
            INSERT INTO user_words (user_id, lexicon_id, status, times_seen, last_seen_at, learned_at)
            VALUES (?, ?, 'learned', 0, ?, ?)
            ON CONFLICT(user_id, lexicon_id) DO UPDATE SET
                status = 'learned',
                learned_at = COALESCE(user_words.learned_at, excluded.learned_at)
            """,
            (user_id, lexicon_id, timestamp, timestamp),
        )
        info = award_xp(connection, user_id, 20)
        evaluate_achievements(connection, user_id)
        connection.commit()
        return LearnOut(
            lemma=word["lemma"],
            status="learned",
            xp=info["xp"],
            level=info["level"],
            level_title=info["title"],
            already_learned=False,
        )
    finally:
        connection.close()


@router.post("/{session_id}/chunks", response_model=ChunkOut, status_code=201)
async def upload_chunk(
    session_id: int,
    file: UploadFile = File(...),
    idx: int | None = Form(None),
    settings: Settings = Depends(get_settings),
) -> dict:
    row = load_session(settings.db_path, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if row["status"] != "recording":
        raise HTTPException(status_code=409, detail="Session is not recording")

    directory = chunk_dir(settings, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix.lower() or ".wav"
    if idx is None:
        used = {int(path.stem) for path in directory.iterdir() if path.stem.isdigit()}
        idx = max(used, default=-1) + 1
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio chunk")
    (directory / f"{idx:04d}{suffix}").write_bytes(content)

    return {"session_id": session_id, "chunks": len(audio_chunks(settings, session_id))}


@router.post("/{session_id}/finish", response_model=FinishOut, status_code=202)
def finish_session(
    session_id: int,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> dict:
    row = load_session(settings.db_path, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if row["status"] != "recording":
        raise HTTPException(status_code=409, detail="Session is not recording")
    if not audio_chunks(settings, session_id):
        raise HTTPException(status_code=400, detail="No audio chunks uploaded")

    connection = connect(settings.db_path)
    try:
        connection.execute("UPDATE sessions SET status = 'processing' WHERE id = ?", (session_id,))
        connection.commit()
    finally:
        connection.close()

    background_tasks.add_task(process_session, settings, session_id)
    return {"id": session_id, "status": "processing"}


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: int, settings: Settings = Depends(get_settings)) -> Response:
    row = load_session(settings.db_path, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    connection = connect(settings.db_path)
    try:
        connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        connection.commit()
    finally:
        connection.close()
    shutil.rmtree(chunk_dir(settings, session_id), ignore_errors=True)
    return Response(status_code=204)
