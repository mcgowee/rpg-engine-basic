"""SQLite database — schema and seed data."""

import json
import sqlite3
from pathlib import Path

from config import BASE_DIR

DB_PATH = BASE_DIR / "rpg.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS subgraphs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            definition TEXT NOT NULL,
            is_public BOOLEAN DEFAULT 0,
            is_builtin BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS main_graph_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            definition TEXT NOT NULL,
            is_public BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            genre TEXT DEFAULT '',
            opening TEXT DEFAULT '',
            narrator_prompt TEXT DEFAULT '',
            narrator_model TEXT DEFAULT 'default',
            player_name TEXT DEFAULT 'Adventurer',
            player_background TEXT DEFAULT '',
            subgraph_name TEXT DEFAULT 'conversation',
            characters TEXT DEFAULT '{}',
            notes TEXT DEFAULT '',
            is_public BOOLEAN DEFAULT 0,
            play_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS saves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            slot INTEGER DEFAULT 0,
            state TEXT NOT NULL,
            saved_at TEXT DEFAULT (datetime('now')),
            UNIQUE(story_id, user_id, slot)
        );
    """)
    conn.commit()
    conn.close()


def seed_builtin_subgraphs():
    """Seed builtin subgraph definitions from graphs/*.json files."""
    from config import GRAPHS_DIR

    conn = get_db()
    try:
        existing = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM subgraphs WHERE is_builtin = 1"
            ).fetchall()
        }

        system_user = conn.execute("SELECT id FROM users WHERE uid = 'system'").fetchone()
        if not system_user:
            conn.execute(
                "INSERT INTO users (uid, password_hash) VALUES ('system', 'nologin')"
            )
            conn.commit()
            system_user = conn.execute("SELECT id FROM users WHERE uid = 'system'").fetchone()
        system_uid = system_user["id"]

        for path in sorted(GRAPHS_DIR.glob("*.json")):
            with open(path) as f:
                definition = json.load(f)
            name = definition.get("name", path.stem)
            if name in existing:
                continue
            description = definition.get("description", "")
            conn.execute(
                """INSERT INTO subgraphs (user_id, name, description, definition, is_builtin)
                   VALUES (?, ?, ?, ?, 1)""",
                (system_uid, name, description, json.dumps(definition)),
            )
        conn.commit()
    finally:
        conn.close()


def seed_builtin_stories():
    """Seed public stories from stories/*.json files."""
    from config import BASE_DIR

    stories_dir = BASE_DIR / "stories"
    if not stories_dir.exists():
        return

    conn = get_db()
    try:
        existing = {
            row["title"]
            for row in conn.execute(
                "SELECT title FROM stories WHERE user_id = (SELECT id FROM users WHERE uid = 'system')"
            ).fetchall()
        }

        system_user = conn.execute("SELECT id FROM users WHERE uid = 'system'").fetchone()
        if not system_user:
            conn.execute(
                "INSERT INTO users (uid, password_hash) VALUES ('system', 'nologin')"
            )
            conn.commit()
            system_user = conn.execute("SELECT id FROM users WHERE uid = 'system'").fetchone()
        system_uid = system_user["id"]

        for path in sorted(stories_dir.glob("*.json")):
            with open(path) as f:
                data = json.load(f)
            title = data.get("title", path.stem)
            if title in existing:
                continue
            characters = data.get("characters", {})
            conn.execute(
                """INSERT INTO stories (user_id, title, description, genre, opening,
                      narrator_prompt, narrator_model, player_name, player_background,
                      subgraph_name, characters, notes, is_public)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    system_uid,
                    title,
                    data.get("description", ""),
                    data.get("genre", ""),
                    data.get("opening", ""),
                    data.get("narrator_prompt", ""),
                    data.get("narrator_model", "default"),
                    data.get("player_name", "Adventurer"),
                    data.get("player_background", ""),
                    data.get("subgraph_name", "conversation"),
                    json.dumps(characters) if isinstance(characters, dict) else "{}",
                    data.get("notes", ""),
                ),
            )
        conn.commit()
    finally:
        conn.close()
