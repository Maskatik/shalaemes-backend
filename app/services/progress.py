import json
from datetime import date, datetime, timezone

LEVELS = [
    (0, "Тыңдаушы"),
    (100, "Сөйлеуші"),
    (300, "Шешен"),
    (700, "Ділмар"),
    (1500, "Сөз зергері"),
]

ACHIEVEMENTS = [
    {
        "key": "first_session",
        "title": "Бірінші сеанс",
        "description": "Бірінші сеансты аяқтаңыз",
        "condition": {"type": "sessions_total", "value": 1},
    },
    {
        "key": "week_streak",
        "title": "Апта қатарынан",
        "description": "7 күн қатарынан сеанс жасаңыз",
        "condition": {"type": "week_streak", "value": 7},
    },
    {
        "key": "clean_speech",
        "title": "Таза сөйлеу",
        "description": "Шет сөздер үлесі 5%-дан төмен сеанс",
        "condition": {"type": "clean_speech", "value": 1},
    },
    {
        "key": "no_fillers",
        "title": "Паразитсіз",
        "description": "Паразит сөздерсіз сеанс",
        "condition": {"type": "no_fillers", "value": 1},
    },
    {
        "key": "used_10",
        "title": "10 сөз",
        "description": "10 сөзді сөйлеуде қолданыңыз",
        "condition": {"type": "used_words", "value": 10},
    },
    {
        "key": "used_50",
        "title": "50 сөз",
        "description": "50 сөзді сөйлеуде қолданыңыз",
        "condition": {"type": "used_words", "value": 50},
    },
    {
        "key": "breakthrough",
        "title": "Серпіліс",
        "description": "Апталық шет сөздер үлесін екі есе азайтыңыз",
        "condition": {"type": "breakthrough", "value": 1},
    },
    {
        "key": "consolidated",
        "title": "Бекітілді",
        "description": "5 сөзді бекітіңіз",
        "condition": {"type": "consolidated_words", "value": 5},
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def level_info(xp: int) -> dict:
    index = 0
    for position, (threshold, _title) in enumerate(LEVELS):
        if xp >= threshold:
            index = position
    current_xp = LEVELS[index][0]
    next_xp = LEVELS[index + 1][0] if index + 1 < len(LEVELS) else None
    progress = (xp - current_xp) / (next_xp - current_xp) if next_xp else 1.0
    return {
        "level": index + 1,
        "title": LEVELS[index][1],
        "current_xp": current_xp,
        "next_xp": next_xp,
        "progress": round(max(0.0, min(progress, 1.0)), 4),
    }


def award_xp(connection, user_id: int, amount: int) -> dict:
    row = connection.execute("SELECT xp FROM users WHERE id = ?", (user_id,)).fetchone()
    xp = max(0, (row["xp"] if row else 0) + amount)
    info = level_info(xp)
    connection.execute("UPDATE users SET xp = ?, level = ? WHERE id = ?", (xp, info["level"], user_id))
    return {"xp": xp, **info}


def _session_dates(connection, user_id: int) -> list[date]:
    rows = connection.execute(
        "SELECT started_at FROM sessions WHERE user_id = ? AND status = 'ready'",
        (user_id,),
    ).fetchall()
    return sorted({date.fromisoformat(row["started_at"][:10]) for row in rows})


def _longest_streak(days: list[date]) -> int:
    best = 0
    current = 0
    previous = None
    for day in days:
        if previous is not None and (day - previous).days == 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
        previous = day
    return best


def _breakthrough(connection, user_id: int) -> bool:
    rows = connection.execute(
        "SELECT started_at, foreign_ratio FROM sessions "
        "WHERE user_id = ? AND status = 'ready' AND foreign_ratio IS NOT NULL",
        (user_id,),
    ).fetchall()
    weeks: dict[tuple[int, int], list[float]] = {}
    for row in rows:
        day = date.fromisoformat(row["started_at"][:10])
        year, week, _ = day.isocalendar()
        weeks.setdefault((year, week), []).append(row["foreign_ratio"])
    averages = [sum(values) / len(values) for _key, values in sorted(weeks.items())]
    return len(averages) >= 2 and averages[0] > 0 and averages[-1] <= averages[0] / 2


def _no_filler_session(connection, user_id: int) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM sessions s
        WHERE s.user_id = ? AND s.status = 'ready'
          AND NOT EXISTS (
              SELECT 1 FROM transcript_words w
              WHERE w.session_id = s.id AND w.category = 'filler'
          )
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return row is not None


def _clean_session(connection, user_id: int) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sessions WHERE user_id = ? AND status = 'ready' AND foreign_ratio < 0.05 LIMIT 1",
        (user_id,),
    ).fetchone()
    return row is not None


def _word_count(connection, user_id: int, status: str) -> int:
    row = connection.execute(
        "SELECT COUNT(*) FROM user_words WHERE user_id = ? AND status = ?",
        (user_id, status),
    ).fetchone()
    return row[0] if row else 0


def evaluate_achievements(connection, user_id: int) -> None:
    sessions_total = connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE user_id = ? AND status = 'ready'",
        (user_id,),
    ).fetchone()[0]
    values = {
        "sessions_total": sessions_total,
        "week_streak": _longest_streak(_session_dates(connection, user_id)),
        "clean_speech": 1 if _clean_session(connection, user_id) else 0,
        "no_fillers": 1 if _no_filler_session(connection, user_id) else 0,
        "used_words": _word_count(connection, user_id, "used"),
        "breakthrough": 1 if _breakthrough(connection, user_id) else 0,
        "consolidated_words": _word_count(connection, user_id, "consolidated"),
    }

    catalog = connection.execute("SELECT id, key, condition FROM achievements").fetchall()
    for achievement in catalog:
        condition = json.loads(achievement["condition"])
        kind = condition.get("type", achievement["key"])
        target = int(condition.get("value", 1))
        current = int(values.get(kind, 0))
        unlocked = current >= target
        progress = json.dumps({"current": current, "target": target}, ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO user_achievements (user_id, achievement_id, unlocked_at, progress)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, achievement_id) DO UPDATE SET
                unlocked_at = COALESCE(user_achievements.unlocked_at, excluded.unlocked_at),
                progress = excluded.progress
            """,
            (user_id, achievement["id"], now_iso() if unlocked else None, progress),
        )
