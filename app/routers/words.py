from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings
from ..db import connect, now_iso
from ..deps import get_settings
from ..schemas import LearnOut, LexiconWordOut, WordListOut
from ..services.progress import award_xp, evaluate_achievements, level_info

router = APIRouter(prefix="/api/words", tags=["words"])


@router.get("", response_model=WordListOut)
def list_words(period: str = Query(default="all"), settings: Settings = Depends(get_settings)) -> WordListOut:
    connection = connect(settings.db_path)
    try:
        user = connection.execute("SELECT id FROM users WHERE id = 1").fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        date_clause = ""
        if period == "today":
            date_clause = "AND substr(uw.last_seen_at, 1, 10) = date('now')"
        elif period == "week":
            date_clause = "AND substr(uw.last_seen_at, 1, 10) >= date('now', '-6 days')"

        rows = connection.execute(
            f"""
            SELECT l.id, l.lemma, l.category, l.meaning_kk, l.example, uw.times_seen, uw.status
            FROM user_words uw
            JOIN lexicon l ON l.id = uw.lexicon_id
            WHERE uw.user_id = ? AND l.category IN ('replace', 'filler') {date_clause}
            ORDER BY uw.times_seen DESC, l.lemma
            LIMIT 40
            """,
            (user["id"],),
        ).fetchall()

        suggestions: dict[int, list[str]] = {}
        ids = [row["id"] for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            for suggestion in connection.execute(
                f"SELECT lexicon_id, replacement FROM suggestions WHERE lexicon_id IN ({placeholders}) ORDER BY id",
                ids,
            ):
                suggestions.setdefault(suggestion["lexicon_id"], []).append(suggestion["replacement"])

        replace = []
        filler = []
        for row in rows:
            item = LexiconWordOut(
                lemma=row["lemma"],
                category=row["category"],
                meaning_kk=row["meaning_kk"],
                example=row["example"],
                count=row["times_seen"],
                status=row["status"],
                suggestions=suggestions.get(row["id"], []),
            )
            if row["category"] == "replace":
                replace.append(item)
            else:
                filler.append(item)

        return WordListOut(replace=replace, filler=filler)
    finally:
        connection.close()


@router.post("/{lemma}/learn", response_model=LearnOut)
def learn_lemma(lemma: str, settings: Settings = Depends(get_settings)) -> LearnOut:
    connection = connect(settings.db_path)
    try:
        word = connection.execute("SELECT id, category FROM lexicon WHERE lemma = ?", (lemma,)).fetchone()
        if word is None:
            raise HTTPException(status_code=404, detail="Word not found")
        if word["category"] not in {"replace", "filler"}:
            raise HTTPException(status_code=400, detail="Only replace and filler words can be learned")

        existing = connection.execute(
            "SELECT status FROM user_words WHERE user_id = 1 AND lexicon_id = ?",
            (word["id"],),
        ).fetchone()
        if existing is not None and existing["status"] in {"learned", "used", "consolidated"}:
            user = connection.execute("SELECT xp FROM users WHERE id = 1").fetchone()
            info = level_info(user["xp"] if user else 0)
            return LearnOut(
                lemma=lemma,
                status=existing["status"],
                xp=user["xp"] if user else 0,
                level=info["level"],
                level_title=info["title"],
                already_learned=True,
            )

        timestamp = now_iso()
        connection.execute(
            """
            INSERT INTO user_words (user_id, lexicon_id, status, times_seen, last_seen_at, learned_at)
            VALUES (1, ?, 'learned', 0, ?, ?)
            ON CONFLICT(user_id, lexicon_id) DO UPDATE SET
                status = 'learned',
                learned_at = COALESCE(user_words.learned_at, excluded.learned_at)
            """,
            (word["id"], timestamp, timestamp),
        )
        info = award_xp(connection, 1, 20)
        evaluate_achievements(connection, 1)
        connection.commit()
        return LearnOut(
            lemma=lemma,
            status="learned",
            xp=info["xp"],
            level=info["level"],
            level_title=info["title"],
            already_learned=False,
        )
    finally:
        connection.close()
