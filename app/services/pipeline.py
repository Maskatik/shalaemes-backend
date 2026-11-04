import json
import shutil
from collections import Counter

from ..config import Settings
from ..db import connect, now_iso
from .annotate import AnnotatedWord
from .asr import AsrWord, get_asr
from .llm import get_annotator
from .progress import award_xp, evaluate_achievements


def build_summary(words: list[AnnotatedWord], warnings: list[str] | None = None) -> dict:
    total = len(words)
    replace_words = [word for word in words if word.category == "replace"]
    filler_words = [word for word in words if word.category == "filler"]
    foreign = len(replace_words) + len(filler_words)

    replace_counts = Counter(word.lemma for word in replace_words)
    filler_counts = Counter(word.lemma for word in filler_words)
    first_word = {}
    for word in words:
        first_word.setdefault(word.lemma, word)

    def items(counts: Counter) -> list[dict]:
        return [
            {
                "lemma": lemma,
                "count": count,
                "suggestions": first_word[lemma].suggestions,
                "meaning_kk": first_word[lemma].meaning_kk,
                "advice": first_word[lemma].advice,
            }
            for lemma, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ]

    return {
        "total_words": total,
        "foreign_ratio": round(foreign / total, 4) if total else 0.0,
        "replace": items(replace_counts),
        "filler": items(filler_counts),
        "warnings": warnings or [],
    }


def update_user_words(connection, user_id: int, summary: dict) -> None:
    for category, items in (("replace", summary["replace"]), ("filler", summary["filler"])):
        for item in items:
            row = connection.execute("SELECT id FROM lexicon WHERE lemma = ?", (item["lemma"],)).fetchone()
            if row is None:
                cursor = connection.execute(
                    "INSERT INTO lexicon (lemma, category, meaning_kk, example, created_at) VALUES (?, ?, ?, '', ?)",
                    (item["lemma"], category, item.get("meaning_kk", ""), now_iso()),
                )
                for suggestion in item.get("suggestions", []):
                    connection.execute(
                        "INSERT INTO suggestions (lexicon_id, replacement, meaning_kk, example) VALUES (?, ?, ?, '')",
                        (cursor.lastrowid, suggestion, item.get("meaning_kk", "")),
                    )
                lexicon_id = cursor.lastrowid
            else:
                lexicon_id = row["id"]
            connection.execute(
                """
                INSERT INTO user_words (user_id, lexicon_id, status, times_seen, last_seen_at)
                VALUES (?, ?, 'suggested', ?, ?)
                ON CONFLICT(user_id, lexicon_id) DO UPDATE SET
                    times_seen = times_seen + excluded.times_seen,
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, lexicon_id, item["count"], now_iso()),
            )


def process_session(settings: Settings, session_id: int) -> None:
    connection = connect(settings.db_path)
    try:
        session = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None or session["status"] != "processing":
            return

        chunk_dir = settings.data_dir / "chunks" / str(session_id)
        files = []
        if chunk_dir.exists():
            files = sorted(path for path in chunk_dir.iterdir() if path.is_file() and path.suffix.lower() != ".txt")
        if not files:
            raise ValueError("No audio chunks uploaded")

        asr = get_asr(settings)
        raw_words: list[AsrWord] = []
        offset_ms = 0
        total_duration = 0.0
        for path in files:
            result = asr.transcribe(path, offset_ms)
            total_duration += result.duration_sec
            raw_words.extend(result.words)
            offset_ms += int(result.duration_sec * 1000)

        annotator = get_annotator(settings)
        annotated = annotator.annotate(raw_words)
        warnings = list(getattr(annotator, "warnings", []))

        connection.execute("DELETE FROM transcript_words WHERE session_id = ?", (session_id,))
        for index, word in enumerate(annotated):
            connection.execute(
                """
                INSERT INTO transcript_words
                    (session_id, idx, surface, lemma, start_ms, end_ms, lang, category, user_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'none')
                """,
                (session_id, index, word.surface, word.lemma, word.start_ms, word.end_ms, word.lang, word.category),
            )

        summary = build_summary(annotated, warnings)
        update_user_words(connection, session["user_id"], summary)
        connection.execute(
            """
            UPDATE sessions
            SET status = 'ready', ended_at = ?, duration_sec = ?, foreign_ratio = ?, summary_json = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                max(int(round(total_duration)), 1),
                summary["foreign_ratio"],
                json.dumps(summary, ensure_ascii=False),
                session_id,
            ),
        )
        if total_duration > 300:
            award_xp(connection, session["user_id"], 10)
        evaluate_achievements(connection, session["user_id"])
        connection.commit()

        if not settings.keep_audio:
            shutil.rmtree(chunk_dir, ignore_errors=True)
    except Exception as error:
        connection.rollback()
        connection.execute(
            "UPDATE sessions SET status = 'failed', ended_at = ?, summary_json = ? WHERE id = ?",
            (now_iso(), json.dumps({"error": str(error)}, ensure_ascii=False), session_id),
        )
        connection.commit()
    finally:
        connection.close()
