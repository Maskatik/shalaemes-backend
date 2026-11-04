import json

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings
from ..db import connect
from ..deps import get_settings
from ..schemas import AchievementOut, ProfileOut, ProfileWords
from ..services.progress import evaluate_achievements, level_info

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(settings: Settings = Depends(get_settings)) -> ProfileOut:
    connection = connect(settings.db_path)
    try:
        user = connection.execute("SELECT * FROM users WHERE id = 1").fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        evaluate_achievements(connection, user["id"])
        connection.commit()

        stats = connection.execute(
            "SELECT COUNT(*) AS sessions, COALESCE(SUM(duration_sec), 0) AS seconds, AVG(foreign_ratio) AS ratio "
            "FROM sessions WHERE user_id = ? AND status = 'ready'",
            (user["id"],),
        ).fetchone()

        word_rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM user_words WHERE user_id = ? GROUP BY status",
            (user["id"],),
        ).fetchall()
        counts = {row["status"]: row["count"] for row in word_rows}
        words = ProfileWords(
            suggested=counts.get("suggested", 0),
            learned=counts.get("learned", 0),
            used=counts.get("used", 0),
            consolidated=counts.get("consolidated", 0),
        )

        achievement_rows = connection.execute(
            """
            SELECT a.key, a.title, a.description, a.condition, ua.unlocked_at, ua.progress
            FROM achievements a
            LEFT JOIN user_achievements ua ON ua.achievement_id = a.id AND ua.user_id = ?
            ORDER BY a.id
            """,
            (user["id"],),
        ).fetchall()

        achievements = []
        for row in achievement_rows:
            condition = json.loads(row["condition"])
            target = int(condition.get("value", 1))
            progress = json.loads(row["progress"]) if row["progress"] else {}
            current = int(progress.get("current", 0))
            achievements.append(
                AchievementOut(
                    key=row["key"],
                    title=row["title"],
                    description=row["description"],
                    unlocked=row["unlocked_at"] is not None,
                    current=current,
                    target=target,
                )
            )

        info = level_info(user["xp"])
        return ProfileOut(
            display_name=user["display_name"],
            level=info["level"],
            level_title=info["title"],
            xp=user["xp"],
            current_level_xp=info["current_xp"],
            next_level_xp=info["next_xp"],
            progress=info["progress"],
            sessions=stats["sessions"],
            minutes=int(stats["seconds"] // 60),
            foreign_ratio_avg=round(stats["ratio"], 4) if stats["ratio"] is not None else None,
            words=words,
            achievements=achievements,
        )
    finally:
        connection.close()
