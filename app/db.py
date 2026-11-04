import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .lexicon import SEED_LEXICON
from .services.progress import ACHIEVEMENTS

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    settings TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_sec INTEGER,
    foreign_ratio REAL,
    status TEXT NOT NULL,
    summary_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcript_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    surface TEXT NOT NULL,
    lemma TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    lang TEXT NOT NULL,
    category TEXT NOT NULL,
    user_flag TEXT NOT NULL DEFAULT 'none',
    UNIQUE (session_id, idx)
);

CREATE TABLE IF NOT EXISTS lexicon (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    meaning_kk TEXT NOT NULL DEFAULT '',
    example TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexicon_id INTEGER NOT NULL REFERENCES lexicon(id) ON DELETE CASCADE,
    replacement TEXT NOT NULL,
    meaning_kk TEXT NOT NULL DEFAULT '',
    example TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    lexicon_id INTEGER NOT NULL REFERENCES lexicon(id),
    status TEXT NOT NULL,
    times_seen INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT,
    learned_at TEXT,
    UNIQUE (user_id, lexicon_id)
);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    condition TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_achievements (
    user_id INTEGER NOT NULL REFERENCES users(id),
    achievement_id INTEGER NOT NULL REFERENCES achievements(id),
    unlocked_at TEXT,
    progress TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (user_id, achievement_id)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: Path) -> None:
    connection = connect(db_path)
    try:
        connection.executescript(SCHEMA)
        if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            connection.execute(
                "INSERT INTO users (display_name, level, xp, created_at, settings) VALUES (?, ?, ?, ?, ?)",
                ("Пайдаланушы", 1, 0, now_iso(), "{}"),
            )
        if connection.execute("SELECT COUNT(*) FROM lexicon").fetchone()[0] == 0:
            for lemma, (category, meaning_kk, example, replacements) in SEED_LEXICON.items():
                cursor = connection.execute(
                    "INSERT INTO lexicon (lemma, category, meaning_kk, example, created_at) VALUES (?, ?, ?, ?, ?)",
                    (lemma, category, meaning_kk, example, now_iso()),
                )
                for replacement in replacements:
                    connection.execute(
                        "INSERT INTO suggestions (lexicon_id, replacement, meaning_kk, example) VALUES (?, ?, ?, ?)",
                        (cursor.lastrowid, replacement, meaning_kk, example),
                    )
        if connection.execute("SELECT COUNT(*) FROM achievements").fetchone()[0] == 0:
            for achievement in ACHIEVEMENTS:
                connection.execute(
                    "INSERT INTO achievements (key, title, description, condition) VALUES (?, ?, ?, ?)",
                    (
                        achievement["key"],
                        achievement["title"],
                        achievement["description"],
                        json.dumps(achievement["condition"], ensure_ascii=False),
                    ),
                )
        connection.commit()
    finally:
        connection.close()
