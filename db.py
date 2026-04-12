"""SQLite database — schema and seed data."""

import json
import logging
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
            tone TEXT DEFAULT '',
            nsfw_rating TEXT DEFAULT 'none',
            nsfw_tags TEXT DEFAULT '[]',
            opening TEXT DEFAULT '',
            narrator_prompt TEXT DEFAULT '',
            narrator_model TEXT DEFAULT 'default',
            player_name TEXT DEFAULT 'Adventurer',
            player_background TEXT DEFAULT '',
            subgraph_name TEXT DEFAULT 'narrator_chat_lite',
            main_graph_template_id INTEGER REFERENCES main_graph_templates(id),
            characters TEXT DEFAULT '{}',
            scene_gallery TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            cover_image TEXT DEFAULT '',
            story_images TEXT DEFAULT '[]',
            map TEXT DEFAULT '{}',
            is_public BOOLEAN DEFAULT 0,
            play_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            prose TEXT NOT NULL,
            content TEXT DEFAULT '[]',
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

        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'story',
            owner_type TEXT,
            owner_id INTEGER,
            owner_key TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued',
            prompt TEXT DEFAULT '',
            negative_prompt TEXT DEFAULT '',
            seed INTEGER,
            workflow_name TEXT DEFAULT '',
            model_name TEXT DEFAULT '',
            width INTEGER,
            height INTEGER,
            provider TEXT DEFAULT 'comfyui',
            mime TEXT DEFAULT '',
            storage_path TEXT DEFAULT '',
            sha256 TEXT DEFAULT '',
            error TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_images_owner ON images(owner_type, owner_id, owner_key);
        CREATE INDEX IF NOT EXISTS idx_images_kind_status ON images(kind, status);

        CREATE TABLE IF NOT EXISTS friction_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            story_id INTEGER,
            session_id TEXT,
            event_type TEXT NOT NULL,
            player_input TEXT DEFAULT '',
            context TEXT DEFAULT '',
            error_detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_friction_logs_event ON friction_logs(event_type);
        CREATE INDEX IF NOT EXISTS idx_friction_logs_ts ON friction_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_friction_logs_story ON friction_logs(story_id);
    """)
    conn.commit()
    migrate_schema(conn)
    conn.close()


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply additive schema changes for existing databases."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(stories)").fetchall()}
    if "main_graph_template_id" not in cols:
        conn.execute(
            """ALTER TABLE stories ADD COLUMN main_graph_template_id INTEGER
               REFERENCES main_graph_templates(id)"""
        )
        conn.commit()
    if "tone" not in cols:
        conn.execute("ALTER TABLE stories ADD COLUMN tone TEXT DEFAULT ''")
        conn.commit()
    if "nsfw_rating" not in cols:
        conn.execute("ALTER TABLE stories ADD COLUMN nsfw_rating TEXT DEFAULT 'none'")
        conn.commit()
    if "nsfw_tags" not in cols:
        conn.execute("ALTER TABLE stories ADD COLUMN nsfw_tags TEXT DEFAULT '[]'")
        conn.commit()
    if "cover_image_id" not in cols:
        conn.execute("ALTER TABLE stories ADD COLUMN cover_image_id INTEGER REFERENCES images(id)")
        conn.commit()
    if "story_images" not in cols:
        conn.execute("ALTER TABLE stories ADD COLUMN story_images TEXT DEFAULT '[]'")
        conn.commit()
    if "scene_gallery" not in cols:
        conn.execute("ALTER TABLE stories ADD COLUMN scene_gallery TEXT DEFAULT '[]'")
        conn.commit()
    if "map" not in cols:
        conn.execute("ALTER TABLE stories ADD COLUMN map TEXT DEFAULT '{}'")
        conn.commit()

    # Books: add content JSON column
    book_cols = {row[1] for row in conn.execute("PRAGMA table_info(books)").fetchall()}
    if "content" not in book_cols:
        conn.execute("ALTER TABLE books ADD COLUMN content TEXT DEFAULT '[]'")
        conn.commit()

    # Migrate all old subgraphs to narrator_chat architecture.
    old_subgraphs = [
        'basic_narrator', 'conversation', 'full_conversation',
        'smart_conversation', 'full_memory', 'full_story',
        'guarded_story', 'guarded_full_memory', 'guarded_narrator',
        'guarded_narrator_with_memory', 'guarded_narrator_npc_memory',
        'narrator_with_npc', 'narrator_with_mood', 'narrator_with_memory',
        'conversation_with_npc', 'conversation_with_mood',
        'chat_only', 'chat_with_memory', 'scene_chat',
        'scene_chat_full', 'scene_chat_action',
    ]
    placeholders = ",".join("?" * len(old_subgraphs))
    # Stories with characters get narrator_chat (full pipeline)
    conn.execute(
        f"""UPDATE stories SET subgraph_name = 'narrator_chat'
           WHERE subgraph_name IN ({placeholders})
           AND characters != '{{}}'
           AND characters != ''
           AND characters IS NOT NULL""",
        old_subgraphs,
    )
    conn.commit()
    # Stories without characters get narrator_chat_lite
    conn.execute(
        f"""UPDATE stories SET subgraph_name = 'narrator_chat_lite'
           WHERE subgraph_name IN ({placeholders})""",
        old_subgraphs,
    )
    conn.commit()

    # Ensure images table/indexes exist for older databases.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'story',
            owner_type TEXT,
            owner_id INTEGER,
            owner_key TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued',
            prompt TEXT DEFAULT '',
            negative_prompt TEXT DEFAULT '',
            seed INTEGER,
            workflow_name TEXT DEFAULT '',
            model_name TEXT DEFAULT '',
            width INTEGER,
            height INTEGER,
            provider TEXT DEFAULT 'comfyui',
            mime TEXT DEFAULT '',
            storage_path TEXT DEFAULT '',
            sha256 TEXT DEFAULT '',
            error TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_images_owner ON images(owner_type, owner_id, owner_key);
        CREATE INDEX IF NOT EXISTS idx_images_kind_status ON images(kind, status);
        """
    )
    conn.commit()

    # Friction logs table for self-improvement signals.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS friction_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            story_id INTEGER,
            session_id TEXT,
            event_type TEXT NOT NULL,
            player_input TEXT DEFAULT '',
            context TEXT DEFAULT '',
            error_detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_friction_logs_event ON friction_logs(event_type);
        CREATE INDEX IF NOT EXISTS idx_friction_logs_ts ON friction_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_friction_logs_story ON friction_logs(story_id);
    """)
    conn.commit()


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


def sync_builtin_subgraphs_from_disk() -> None:
    """Refresh builtin subgraph rows from graphs/*.json so code updates apply without reseeding."""
    from config import GRAPHS_DIR

    conn = get_db()
    try:
        names_on_disk: list[str] = []
        for path in sorted(GRAPHS_DIR.glob("*.json")):
            with open(path) as f:
                definition = json.load(f)
            name = definition.get("name", path.stem)
            names_on_disk.append(name)
            row = conn.execute(
                "SELECT id FROM subgraphs WHERE name = ? AND is_builtin = 1",
                (name,),
            ).fetchone()
            description = definition.get("description", "")
            if not row:
                # New builtin subgraph on disk — insert it
                system_user = conn.execute("SELECT id FROM users WHERE uid = 'system'").fetchone()
                if system_user:
                    conn.execute(
                        """INSERT INTO subgraphs (user_id, name, description, definition, is_builtin)
                           VALUES (?, ?, ?, ?, 1)""",
                        (system_user["id"], name, description, json.dumps(definition)),
                    )
                continue
            conn.execute(
                """UPDATE subgraphs SET definition = ?, description = ?,
                       updated_at = datetime('now')
                   WHERE name = ? AND is_builtin = 1""",
                (json.dumps(definition), description, name),
            )
        if names_on_disk:
            placeholders = ",".join("?" * len(names_on_disk))
            conn.execute(
                f"DELETE FROM subgraphs WHERE is_builtin = 1 AND name NOT IN ({placeholders})",
                tuple(names_on_disk),
            )
        conn.commit()
    finally:
        conn.close()


def sync_builtin_story_covers_from_disk() -> None:
    """Apply cover_image from stories/*.json to system user's stories (startup sync)."""
    from config import BASE_DIR

    stories_dir = BASE_DIR / "stories"
    if not stories_dir.exists():
        return

    conn = get_db()
    try:
        system = conn.execute(
            "SELECT id FROM users WHERE uid = 'system'"
        ).fetchone()
        if not system:
            return
        system_uid = system["id"]

        for path in sorted(stories_dir.glob("*.json")):
            with open(path) as f:
                data = json.load(f)
            title = data.get("title", path.stem)
            cover = (data.get("cover_image") or "").strip()
            if not cover:
                continue
            conn.execute(
                """UPDATE stories SET cover_image = ?, updated_at = datetime('now')
                   WHERE user_id = ? AND title = ?""",
                (cover, system_uid, title),
            )
        conn.commit()
    finally:
        conn.close()


def sync_builtin_story_characters_from_disk() -> None:
    """Apply characters (including portrait filenames) from stories/*.json to system user's stories."""
    from config import BASE_DIR

    stories_dir = BASE_DIR / "stories"
    if not stories_dir.exists():
        return

    conn = get_db()
    try:
        system = conn.execute(
            "SELECT id FROM users WHERE uid = 'system'"
        ).fetchone()
        if not system:
            return
        system_uid = system["id"]

        for path in sorted(stories_dir.glob("*.json")):
            with open(path) as f:
                data = json.load(f)
            title = data.get("title", path.stem)
            characters = data.get("characters", {})
            if not isinstance(characters, dict):
                characters = {}
            conn.execute(
                """UPDATE stories SET characters = ?, updated_at = datetime('now')
                   WHERE user_id = ? AND title = ?""",
                (json.dumps(characters), system_uid, title),
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
                      subgraph_name, characters, notes, cover_image, is_public)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
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
                    data.get("subgraph_name", "narrator_chat_lite"),
                    json.dumps(characters) if isinstance(characters, dict) else "{}",
                    data.get("notes", ""),
                    (data.get("cover_image") or "").strip(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Friction logging
# ---------------------------------------------------------------------------

def log_friction(
    event_type: str,
    story_id: int | None = None,
    session_id: str | None = None,
    player_input: str = "",
    context: str = "",
    error_detail: str = "",
) -> None:
    """Record a friction event for self-improvement analysis.

    Never raises — friction logging must not break the request that triggered it.
    """
    try:
        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO friction_logs
                   (story_id, session_id, event_type, player_input, context, error_detail)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (story_id, session_id, event_type,
                 player_input[:1000], context[:2000], error_detail[:5000]),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logging.getLogger(__name__).warning("Failed to write friction log", exc_info=True)
