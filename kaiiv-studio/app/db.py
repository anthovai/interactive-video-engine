"""The record: people, lessons, the questions on them, and what was answered.

SQLite, in one file under the data directory, because a studio for one
organisation's lessons does not need a database server and every extra
container is one more thing a customer has to keep running. The engine holds
nothing, so this file is the whole of what needs backing up (with media/).

The answers to every question live in interactions.answers, and nothing that
builds a page reads that column: pages are given what the engine's /timeline
returned, which is the only place allowed to decide what a learner may see.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'teacher', 'learner')),
    password_hash TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS lessons (
    id           INTEGER PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    provider     TEXT NOT NULL CHECK (provider IN ('file', 'hls', 'youtube', 'vimeo')),
    src          TEXT NOT NULL DEFAULT '',
    videoid      TEXT NOT NULL DEFAULT '',
    mediafile    TEXT NOT NULL DEFAULT '',
    mustanswer   INTEGER NOT NULL DEFAULT 1,
    allowreview  INTEGER NOT NULL DEFAULT 1,
    maxattempts  INTEGER NOT NULL DEFAULT 0,
    published    INTEGER NOT NULL DEFAULT 0,
    created_by   INTEGER NOT NULL REFERENCES users(id),
    created      INTEGER NOT NULL,
    updated      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS interactions (
    id        INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    type      TEXT NOT NULL,
    start     REAL NOT NULL,
    end       REAL NOT NULL,
    display   TEXT NOT NULL DEFAULT 'poster',
    pauses    INTEGER NOT NULL,
    graded    INTEGER NOT NULL,
    x         REAL NOT NULL DEFAULT 20,
    y         REAL NOT NULL DEFAULT 20,
    width     REAL NOT NULL DEFAULT 60,
    height    REAL NOT NULL DEFAULT 40,
    label     TEXT NOT NULL DEFAULT '',
    content   TEXT NOT NULL,
    answers   TEXT NOT NULL,
    feedback  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS interactions_lesson ON interactions(lesson_id, start);

CREATE TABLE IF NOT EXISTS responses (
    id             INTEGER PRIMARY KEY,
    interaction_id INTEGER NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    response       TEXT NOT NULL,
    correct        INTEGER NOT NULL,
    attempt        INTEGER NOT NULL,
    created        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS responses_user ON responses(user_id, interaction_id);

CREATE TABLE IF NOT EXISTS progress (
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    furthest  REAL NOT NULL DEFAULT 0,
    finished  INTEGER NOT NULL DEFAULT 0,
    updated   INTEGER NOT NULL,
    PRIMARY KEY (lesson_id, user_id)
);
"""

_lock = threading.Lock()
_path = None


def init(path=None) -> None:
    """Create the file and the tables if they are not there."""
    global _path
    _path = str(path or (config.DATA_DIR / "studio.sqlite3"))
    with connect() as db:
        db.executescript(SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """One connection per unit of work, committed at the end or rolled back.

    Serialised by a lock: SQLite takes one writer at a time anyway, and
    waiting here is kinder than a "database is locked" in the middle of a
    learner's answer.
    """
    # With a limit, so that code which opens a second connection while holding
    # the first fails with a message instead of hanging the request forever.
    if not _lock.acquire(timeout=60):
        raise RuntimeError("database lock not released: a connection was opened inside another")
    try:
        db = sqlite3.connect(_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    finally:
        _lock.release()


def now() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# Shapes the engine reads
# ---------------------------------------------------------------------------

def interactions_for_engine(db: sqlite3.Connection, lesson_id: int) -> list[dict[str, Any]]:
    """Every interaction on a lesson, answers included, for /timeline and /score."""
    rows = db.execute(
        "SELECT * FROM interactions WHERE lesson_id = ? ORDER BY start, id",
        (lesson_id,)).fetchall()
    return [{
        "id": row["id"],
        "type": row["type"],
        "start": row["start"],
        "end": row["end"],
        "display": row["display"],
        "pauses": bool(row["pauses"]),
        "x": row["x"], "y": row["y"], "width": row["width"], "height": row["height"],
        "label": row["label"],
        "content": json.loads(row["content"]),
        "answers": json.loads(row["answers"]),
        "feedback": row["feedback"],
    } for row in rows]


def seen(db: sqlite3.Connection, lesson_id: int, user_id: int) -> dict[str, dict[str, Any]]:
    """What this learner has done, as the engine reads it.

    Interaction id to the latest response, whether it was right, how many
    attempts so far — and whether any of them was right, which is what the
    engine is told so it can refuse to mark another once the answer has been
    revealed.
    """
    rows = db.execute(
        """SELECT r.interaction_id, r.response, r.correct
             FROM responses r JOIN interactions i ON i.id = r.interaction_id
            WHERE i.lesson_id = ? AND r.user_id = ?
         ORDER BY r.id""", (lesson_id, user_id)).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["interaction_id"])
        before = out.get(key)
        out[key] = {
            "response": json.loads(row["response"]),
            "correct": bool(row["correct"]),
            "attempts": (before["attempts"] if before else 0) + 1,
            "ever_correct": bool(row["correct"]) or bool(before and before["ever_correct"]),
        }
    return out
