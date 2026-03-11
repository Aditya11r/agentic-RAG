"""
database.py  –  SQLite persistence layer for threads & UI chat history
"""

from __future__ import annotations

import re
import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from contextlib import contextmanager

DB_PATH = "hospital_chat.db"


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id   TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                intent      TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id   TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                meta        TEXT DEFAULT '{}',
                created_at  TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_thread
                ON messages(thread_id);
        """)


# ─────────────────────────────────────────────────────────────
# ONE-TIME CLEANUP — strips HTML tags stored in content by old code versions
# Safe to call on every startup; is a no-op once rows are clean.
# ─────────────────────────────────────────────────────────────
_HTML_TAG = re.compile(r'<[^>]+>')

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = _HTML_TAG.sub('', text)
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    return text.strip()

def clean_html_messages() -> None:
    """
    Find any messages whose content contains raw HTML tags (from old buggy
    code that stored rendered HTML in the DB) and strip them to plain text.
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT id, content FROM messages WHERE content LIKE '%<%>%' OR content LIKE '%<div%'"
        ).fetchall()
        for row in rows:
            cleaned = _strip_html(row["content"])
            if cleaned != row["content"]:
                con.execute(
                    "UPDATE messages SET content=? WHERE id=?",
                    (cleaned, row["id"]),
                )


# ─────────────────────────────────────────────────────────────
# THREAD CRUD
# ─────────────────────────────────────────────────────────────
def create_thread(thread_id: str, title: str, intent: Optional[str] = None) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO threads VALUES (?,?,?,?,?)",
            (thread_id, title, intent, now, now),
        )


def update_thread(thread_id: str, title: Optional[str] = None,
                  intent: Optional[str] = None) -> None:
    with _conn() as con:
        if title:
            con.execute(
                "UPDATE threads SET title=?, updated_at=? WHERE thread_id=?",
                (title, _now(), thread_id),
            )
        if intent:
            con.execute(
                "UPDATE threads SET intent=?, updated_at=? WHERE thread_id=?",
                (intent, _now(), thread_id),
            )


def list_threads() -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM threads ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_thread(thread_id: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM messages WHERE thread_id=?", (thread_id,))
        con.execute("DELETE FROM threads  WHERE thread_id=?", (thread_id,))


def get_thread(thread_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM threads WHERE thread_id=?", (thread_id,)
        ).fetchone()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────
# MESSAGE CRUD
# ─────────────────────────────────────────────────────────────
def add_message(thread_id: str, role: str, content: str,
                meta: Optional[dict] = None) -> None:
    # Guard: never store HTML tags in content — strip them defensively
    if '<' in content and '>' in content:
        content = _strip_html(content)
    with _conn() as con:
        con.execute(
            "INSERT INTO messages (thread_id, role, content, meta, created_at) "
            "VALUES (?,?,?,?,?)",
            (thread_id, role, content, json.dumps(meta or {}), _now()),
        )
        con.execute(
            "UPDATE threads SET updated_at=? WHERE thread_id=?",
            (_now(), thread_id),
        )


def get_messages(thread_id: str) -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM messages WHERE thread_id=? ORDER BY id ASC",
            (thread_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d.get("meta") or "{}")
        out.append(d)
    return out


def clear_messages(thread_id: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM messages WHERE thread_id=?", (thread_id,))


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def smart_title(query: str, max_len: int = 48) -> str:
    q = query.strip().rstrip("?").strip()
    return q[:max_len] + ("…" if len(q) > max_len else "")