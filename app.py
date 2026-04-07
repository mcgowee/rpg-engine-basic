"""Flask API — auth, subgraphs, main graph templates, stories, play, AI assist."""

import json
import logging
import os
import sqlite3
import threading

from flask import Flask, g, jsonify, request, session, Response

from auth import check_password, hash_password, login_required
from config import (
    DEFAULT_MODEL,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    SAVE_SLOTS,
    SECRET_KEY,
)
from db import get_db, init_db, seed_builtin_subgraphs, seed_builtin_stories
from graphs.builder import validate_graph_definition
from graphs.registry import registry
from llm import get_llm
from nodes import NODE_REGISTRY
from nodes.narrator import DEFAULT_NARRATOR_PROMPT
from routers import ROUTER_REGISTRY, ROUTER_RETURNS

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY
if not FLASK_DEBUG:
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
        app.config["SESSION_COOKIE_SECURE"] = True

if os.environ.get("SECRET_KEY") is None and not FLASK_DEBUG:
    logger.warning("SECRET_KEY is not set — using built-in default.")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route("/register", methods=["POST"])
def register_user():
    data = request.get_json(silent=True) or {}
    uid = (data.get("uid") or "").strip()
    password = data.get("password") or ""
    if not uid:
        return jsonify({"error": "uid is required"}), 400
    if len(password) < 4:
        return jsonify({"error": "password must be at least 4 characters"}), 400
    conn = get_db()
    try:
        try:
            conn.execute(
                "INSERT INTO users (uid, password_hash) VALUES (?, ?)",
                (uid, hash_password(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Username already taken"}), 409
        row = conn.execute("SELECT id FROM users WHERE uid = ?", (uid,)).fetchone()
    finally:
        conn.close()
    session["user_id"] = row["id"]
    return jsonify({"uid": uid}), 201


@app.route("/login", methods=["POST"])
def login_user():
    data = request.get_json(silent=True) or {}
    uid = (data.get("uid") or "").strip()
    password = data.get("password") or ""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE uid = ?", (uid,)
        ).fetchone()
    finally:
        conn.close()
    if not row or not check_password(password, row["password_hash"]):
        return jsonify({"error": "Invalid uid or password"}), 401
    session["user_id"] = row["id"]
    return jsonify({"uid": uid})


@app.route("/logout", methods=["POST"])
def logout_user():
    session.clear()
    return jsonify({"ok": True})


@app.route("/me", methods=["GET"])
@login_required
def me():
    conn = get_db()
    try:
        row = conn.execute("SELECT id, uid FROM users WHERE id = ?", (g.user_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"uid": row["uid"], "user_id": row["id"]})


# ---------------------------------------------------------------------------
# Graph registry
# ---------------------------------------------------------------------------

NODE_DESCRIPTIONS = {
    "narrator": {
        "summary": "Main scene narration via LLM",
        "description": "Takes the player's message and generates a narrative response. Builds a prompt from the narrator system instructions, game title, player info, characters present, memory summary, and recent history. This is the core node — every graph needs it.",
        "llm": True,
        "reads": ["message", "narrator", "player", "characters", "history", "memory_summary", "game_title"],
        "writes": ["response"],
    },
    "memory": {
        "summary": "Records turn in history",
        "description": "Appends the current turn (player message + narrator response) to the history list and updates the turn count. No LLM call — pure bookkeeping. Without this node, the narrator has no memory of previous turns.",
        "llm": False,
        "reads": ["message", "response", "history"],
        "writes": ["history", "turn_count"],
    },
    "condense": {
        "summary": "Rolling memory summary via LLM",
        "description": "Calls the LLM to compress the story so far into a short summary (under 100 words). Focuses on key facts, relationship changes, and important events. Drops scenery and small talk. The narrator reads this summary for long-term context beyond the raw history window.",
        "llm": True,
        "reads": ["history", "memory_summary", "message", "response", "narrator"],
        "writes": ["memory_summary"],
    },
    "npc": {
        "summary": "NPC dialogue in character via LLM",
        "description": "For each character in the story, generates a response in their voice using their personality prompt. Includes the narrator's scene description, the player's message, and the character's current mood. Each character gets their own LLM call. Dialogue is appended to the narrator's response.",
        "llm": True,
        "reads": ["characters", "message", "response", "player", "history", "memory_summary"],
        "writes": ["response"],
    },
    "mood": {
        "summary": "Tracks NPC mood shifts via LLM",
        "description": "For each character's mood axis, asks the LLM whether it should go UP, DOWN, or SAME based on the player's action. Supports multiple named axes per character (e.g. trust, fear, cooperativeness) with custom low/high labels. Each axis is a separate LLM call. Falls back to a single mood number for legacy characters.",
        "llm": True,
        "reads": ["characters", "message", "history", "memory_summary"],
        "writes": ["characters"],
    },
}

ROUTER_DESCRIPTIONS = {
    "route_graph_entry": {
        "summary": "Entry point — always routes to narrator",
        "description": "The default entry router. Currently always returns 'narrator' since there's only one entry path. In the future, this could check for multiple locations and route to a movement node first.",
        "returns": ROUTER_RETURNS.get("route_graph_entry", []),
    },
    "route_after_narrator": {
        "summary": "After narrator — routes to NPC/mood or skips to condense",
        "description": "Checks if characters exist in the story. If yes, routes to the NPC path (which may go through mood first depending on the graph's mapping). If no characters, skips directly to condense. This is a conditional edge — same graph handles stories with or without NPCs.",
        "returns": ROUTER_RETURNS.get("route_after_narrator", []),
    },
}


@app.route("/graph-registry", methods=["GET"])
def graph_registry_keys():
    return jsonify({
        "nodes": sorted(NODE_REGISTRY.keys()),
        "node_descriptions": NODE_DESCRIPTIONS,
        "routers": {name: ROUTER_RETURNS.get(name, []) for name in sorted(ROUTER_REGISTRY.keys())},
        "router_descriptions": ROUTER_DESCRIPTIONS,
    })


# ---------------------------------------------------------------------------
# Subgraphs CRUD
# ---------------------------------------------------------------------------

@app.route("/subgraphs", methods=["GET"])
@login_required
def list_subgraphs():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, user_id, name, description, definition, is_public, is_builtin,
                      created_at, updated_at
               FROM subgraphs
               WHERE user_id = ? OR is_public = 1 OR is_builtin = 1
               ORDER BY is_builtin DESC, (user_id = ?) DESC, updated_at DESC""",
            (g.user_id, g.user_id),
        ).fetchall()
    finally:
        conn.close()

    items = []
    for r in rows:
        try:
            defn = json.loads(r["definition"])
            node_count = len(defn.get("nodes", []))
        except (json.JSONDecodeError, TypeError):
            node_count = 0
        items.append({
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "node_count": node_count,
            "is_public": bool(r["is_public"]),
            "is_builtin": bool(r["is_builtin"]),
            "owned": r["user_id"] == g.user_id,
            "compiled": r["name"] in registry,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return jsonify(items)


@app.route("/subgraphs", methods=["POST"])
@login_required
def create_subgraph():
    definition = request.get_json(silent=True)
    if not isinstance(definition, dict):
        return jsonify({"error": "JSON body required"}), 400
    errors = validate_graph_definition(definition)
    if errors:
        return jsonify({"error": "Validation failed", "errors": errors}), 400
    name = definition["name"]
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM subgraphs WHERE user_id = ? AND name = ?", (g.user_id, name)
        ).fetchone()
        if existing:
            return jsonify({"error": f"Subgraph '{name}' already exists"}), 409
        cur = conn.execute(
            """INSERT INTO subgraphs (user_id, name, description, definition)
               VALUES (?, ?, ?, ?)""",
            (g.user_id, name, definition.get("description", ""), json.dumps(definition)),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    registry.reload_one(name, definition)
    return jsonify({"id": new_id, "name": name}), 201


@app.route("/subgraphs/<int:subgraph_id>", methods=["GET"])
@login_required
def get_subgraph(subgraph_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM subgraphs WHERE id = ?", (subgraph_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    if row["user_id"] != g.user_id and not row["is_public"] and not row["is_builtin"]:
        return jsonify({"error": "Not found"}), 404
    try:
        defn = json.loads(row["definition"])
    except (json.JSONDecodeError, TypeError):
        defn = {}
    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "definition": defn,
        "is_public": bool(row["is_public"]),
        "is_builtin": bool(row["is_builtin"]),
        "owned": row["user_id"] == g.user_id,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    })


@app.route("/subgraphs/<int:subgraph_id>", methods=["PUT"])
@login_required
def update_subgraph(subgraph_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM subgraphs WHERE id = ?", (subgraph_id,)).fetchone()
        if not row or row["user_id"] != g.user_id:
            return jsonify({"error": "Not found"}), 404
        if row["is_builtin"]:
            return jsonify({"error": "Cannot edit builtin subgraphs"}), 403
        definition = request.get_json(silent=True)
        if not isinstance(definition, dict):
            return jsonify({"error": "JSON body required"}), 400
        errors = validate_graph_definition(definition)
        if errors:
            return jsonify({"error": "Validation failed", "errors": errors}), 400
        old_name = row["name"]
        new_name = definition["name"]
        conn.execute(
            """UPDATE subgraphs SET name = ?, description = ?, definition = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (new_name, definition.get("description", ""), json.dumps(definition), subgraph_id),
        )
        conn.commit()
    finally:
        conn.close()
    if old_name != new_name:
        registry.remove(old_name)
    registry.reload_one(new_name, definition)
    return jsonify({"ok": True})


@app.route("/subgraphs/<int:subgraph_id>", methods=["DELETE"])
@login_required
def delete_subgraph(subgraph_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM subgraphs WHERE id = ?", (subgraph_id,)).fetchone()
        if not row or row["user_id"] != g.user_id:
            return jsonify({"error": "Not found"}), 404
        if row["is_builtin"]:
            return jsonify({"error": "Cannot delete builtin subgraphs"}), 403
        conn.execute("DELETE FROM subgraphs WHERE id = ?", (subgraph_id,))
        conn.commit()
    finally:
        conn.close()
    registry.remove(row["name"])
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Subgraph test/trace
# ---------------------------------------------------------------------------

@app.route("/subgraphs/<int:subgraph_id>/test", methods=["POST"])
@login_required
def test_subgraph(subgraph_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM subgraphs WHERE id = ?", (subgraph_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    if row["user_id"] != g.user_id and not row["is_public"] and not row["is_builtin"]:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    try:
        defn = json.loads(row["definition"])
    except (json.JSONDecodeError, TypeError):
        return jsonify({"error": "Invalid subgraph definition"}), 400

    # Build initial state — from story or dummy
    story_id = data.get("story_id")
    if story_id is not None:
        try:
            sid = int(story_id)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid story_id"}), 400
        sconn = get_db()
        try:
            srow = sconn.execute(
                "SELECT * FROM stories WHERE id = ? AND (user_id = ? OR is_public = 1)",
                (sid, g.user_id),
            ).fetchone()
        finally:
            sconn.close()
        if not srow:
            return jsonify({"error": "Story not found"}), 404
        state = _build_state_from_story(srow)
        state["message"] = message
    else:
        state = {
            "message": message,
            "response": "",
            "narrator": {"prompt": DEFAULT_NARRATOR_PROMPT, "model": DEFAULT_MODEL},
            "player": {"name": "Tester", "background": "A brave adventurer testing this subgraph.", },
            "game_title": "Subgraph Test",
            "opening": "",
            "paused": False,
            "turn_count": 0,
        }

    try:
        from graphs.builder import build_graph_from_json
        compiled = build_graph_from_json(defn)
    except Exception as e:
        return jsonify({"error": f"Compilation failed: {e}"}), 400

    initial_state = dict(state)
    trace = []

    try:
        for chunk in compiled.stream(state):
            for node_name, updates in chunk.items():
                if node_name == "__end__":
                    continue
                if not isinstance(updates, dict):
                    continue
                state.update(updates)
                trace.append({
                    "node": node_name,
                    "updates": updates,
                    "state_after": dict(state),
                })
    except Exception as e:
        trace.append({"error": str(e)})

    return jsonify({"initial_state": initial_state, "trace": trace})


# ---------------------------------------------------------------------------
# Main graph templates CRUD
# ---------------------------------------------------------------------------

def _validate_main_graph_definition(definition) -> list[str]:
    errors = []
    if not isinstance(definition, dict):
        return ["definition must be an object"]
    phases = definition.get("phases")
    if not isinstance(phases, list) or len(phases) == 0:
        return ["phases must be a non-empty array"]
    seen = set()
    n = len(phases)
    allowed_types = {"milestone", "rules", "turns", "location", "manual"}
    for i, phase in enumerate(phases):
        if not isinstance(phase, dict):
            errors.append(f"phase {i}: must be an object")
            continue
        pname = phase.get("name")
        if not pname or not isinstance(pname, str):
            errors.append(f"phase {i}: name is required")
        else:
            if pname in seen:
                errors.append(f"duplicate phase name: {pname}")
            seen.add(pname)
        subgraph = phase.get("subgraph")
        if not subgraph or not isinstance(subgraph, str):
            errors.append(f"phase {i}: subgraph is required")
        is_last = i == n - 1
        tr = phase.get("transition")
        if not is_last:
            if not isinstance(tr, dict):
                errors.append(f"phase {i}: transition required")
            else:
                if tr.get("type") not in allowed_types:
                    errors.append(f"phase {i}: invalid transition type")
                if not isinstance(tr.get("condition"), str):
                    errors.append(f"phase {i}: transition.condition must be a string")
        elif tr is not None:
            errors.append(f"phase {i}: final phase must have transition null or omitted")
    return errors


def _phase_count(definition) -> int:
    try:
        if isinstance(definition, str):
            definition = json.loads(definition)
        return len(definition.get("phases", []))
    except Exception:
        return 0


@app.route("/main-graph-templates", methods=["GET"])
@login_required
def list_main_graph_templates():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, user_id, name, description, definition, is_public, created_at, updated_at
               FROM main_graph_templates
               WHERE user_id = ? OR is_public = 1
               ORDER BY (user_id = ?) DESC, updated_at DESC""",
            (g.user_id, g.user_id),
        ).fetchall()
    finally:
        conn.close()
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "phase_count": _phase_count(r["definition"]),
            "is_public": bool(r["is_public"]),
            "owned": r["user_id"] == g.user_id,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return jsonify(items)


@app.route("/main-graph-templates", methods=["POST"])
@login_required
def create_main_graph_template():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    definition = data.get("definition")
    errors = _validate_main_graph_definition(definition)
    if errors:
        return jsonify({"error": "Validation failed", "errors": errors}), 400
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM main_graph_templates WHERE user_id = ? AND name = ?",
            (g.user_id, name),
        ).fetchone()
        if existing:
            return jsonify({"error": f"Template '{name}' already exists"}), 409
        cur = conn.execute(
            """INSERT INTO main_graph_templates (user_id, name, description, definition)
               VALUES (?, ?, ?, ?)""",
            (g.user_id, name, data.get("description", ""), json.dumps(definition)),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"id": new_id, "name": name}), 201


@app.route("/main-graph-templates/<int:tmpl_id>", methods=["GET"])
@login_required
def get_main_graph_template(tmpl_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM main_graph_templates WHERE id = ?", (tmpl_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    if row["user_id"] != g.user_id and not row["is_public"]:
        return jsonify({"error": "Not found"}), 404
    try:
        defn = json.loads(row["definition"])
    except (json.JSONDecodeError, TypeError):
        defn = {}
    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "definition": defn,
        "is_public": bool(row["is_public"]),
        "owned": row["user_id"] == g.user_id,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    })


@app.route("/main-graph-templates/<int:tmpl_id>", methods=["PUT"])
@login_required
def update_main_graph_template(tmpl_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM main_graph_templates WHERE id = ?", (tmpl_id,)).fetchone()
        if not row or row["user_id"] != g.user_id:
            return jsonify({"error": "Not found"}), 404
        data = request.get_json(silent=True) or {}
        definition = data.get("definition")
        errors = _validate_main_graph_definition(definition)
        if errors:
            return jsonify({"error": "Validation failed", "errors": errors}), 400
        conn.execute(
            """UPDATE main_graph_templates SET name = ?, description = ?, definition = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (data.get("name", row["name"]), data.get("description", row["description"]),
             json.dumps(definition), tmpl_id),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/main-graph-templates/<int:tmpl_id>", methods=["DELETE"])
@login_required
def delete_main_graph_template(tmpl_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM main_graph_templates WHERE id = ?", (tmpl_id,)).fetchone()
        if not row or row["user_id"] != g.user_id:
            return jsonify({"error": "Not found"}), 404
        conn.execute("DELETE FROM main_graph_templates WHERE id = ?", (tmpl_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Stories CRUD (flat columns)
# ---------------------------------------------------------------------------

def _story_row_to_dict(r, include_content=False) -> dict:
    d = {
        "id": r["id"],
        "title": r["title"],
        "description": r["description"],
        "genre": r["genre"],
        "subgraph_name": r["subgraph_name"],
        "notes": r["notes"] or "",
        "is_public": bool(r["is_public"]),
        "play_count": r["play_count"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
    if include_content:
        d["opening"] = r["opening"]
        d["narrator_prompt"] = r["narrator_prompt"]
        d["narrator_model"] = r["narrator_model"]
        d["player_name"] = r["player_name"]
        d["player_background"] = r["player_background"]
        try:
            d["characters"] = json.loads(r["characters"] or "{}")
        except (json.JSONDecodeError, TypeError):
            d["characters"] = {}
    return d


@app.route("/stories/public", methods=["GET"])
def list_public_stories():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT s.*, u.uid as author_uid
               FROM stories s LEFT JOIN users u ON s.user_id = u.id
               WHERE s.is_public = 1
               ORDER BY s.play_count DESC, s.created_at DESC"""
        ).fetchall()
    finally:
        conn.close()
    items = []
    for r in rows:
        d = _story_row_to_dict(r)
        d["author_uid"] = r["author_uid"] or "unknown"
        items.append(d)
    return jsonify({"stories": items})


@app.route("/stories", methods=["GET"])
@login_required
def list_stories():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM stories WHERE user_id = ? ORDER BY updated_at DESC",
            (g.user_id,),
        ).fetchall()
    finally:
        conn.close()
    return jsonify([_story_row_to_dict(r) for r in rows])


@app.route("/stories", methods=["POST"])
@login_required
def create_story():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    characters = data.get("characters", {})
    if not isinstance(characters, dict):
        characters = {}
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, characters, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user_id,
                title,
                data.get("description", ""),
                data.get("genre", ""),
                data.get("opening", ""),
                data.get("narrator_prompt", DEFAULT_NARRATOR_PROMPT),
                data.get("narrator_model", "default"),
                data.get("player_name", "Adventurer"),
                data.get("player_background", ""),
                data.get("subgraph_name", "conversation"),
                json.dumps(characters),
                data.get("notes", ""),
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"id": new_id, "title": title}), 201


@app.route("/stories/<int:story_id>", methods=["GET"])
@login_required
def get_story(story_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    if row["user_id"] != g.user_id and not row["is_public"]:
        return jsonify({"error": "Not found"}), 404
    return jsonify(_story_row_to_dict(row, include_content=True))


@app.route("/stories/<int:story_id>", methods=["PUT"])
@login_required
def update_story(story_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        data = request.get_json(silent=True) or {}
        characters = data.get("characters")
        characters_json = json.dumps(characters) if characters is not None else row["characters"]
        conn.execute(
            """UPDATE stories SET title = ?, description = ?, genre = ?, opening = ?,
                  narrator_prompt = ?, narrator_model = ?, player_name = ?,
                  player_background = ?, subgraph_name = ?, characters = ?,
                  notes = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (
                data.get("title", row["title"]),
                data.get("description", row["description"]),
                data.get("genre", row["genre"]),
                data.get("opening", row["opening"]),
                data.get("narrator_prompt", row["narrator_prompt"]),
                data.get("narrator_model", row["narrator_model"]),
                data.get("player_name", row["player_name"]),
                data.get("player_background", row["player_background"]),
                data.get("subgraph_name", row["subgraph_name"]),
                characters_json,
                data.get("notes", row["notes"]),
                story_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/stories/<int:story_id>", methods=["DELETE"])
@login_required
def delete_story(story_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        conn.execute("DELETE FROM saves WHERE story_id = ?", (story_id,))
        conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/stories/<int:story_id>/publish", methods=["POST"])
@login_required
def publish_story(story_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        new_val = 0 if row["is_public"] else 1
        conn.execute("UPDATE stories SET is_public = ?, updated_at = datetime('now') WHERE id = ?",
                     (new_val, story_id))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "is_public": bool(new_val)})


@app.route("/stories/<int:story_id>/copy", methods=["POST"])
@login_required
def copy_story(story_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND (is_public = 1 OR user_id = ?)",
            (story_id, g.user_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, characters, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user_id,
                row["title"],
                row["description"],
                row["genre"],
                row["opening"],
                row["narrator_prompt"],
                row["narrator_model"],
                row["player_name"],
                row["player_background"],
                row["subgraph_name"],
                row["characters"] or "{}",
                row["notes"] or "",
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"id": new_id, "title": row["title"]}), 201


# ---------------------------------------------------------------------------
# Story export/import
# ---------------------------------------------------------------------------

@app.route("/stories/<int:story_id>/export", methods=["GET"])
@login_required
def export_story(story_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    finally:
        conn.close()
    if not row or (row["user_id"] != g.user_id and not row["is_public"]):
        return jsonify({"error": "Not found"}), 404
    export = {
        "export_version": 1,
        "title": row["title"],
        "description": row["description"],
        "genre": row["genre"],
        "opening": row["opening"],
        "narrator_prompt": row["narrator_prompt"],
        "narrator_model": row["narrator_model"],
        "player_name": row["player_name"],
        "player_background": row["player_background"],
        "subgraph_name": row["subgraph_name"],
        "characters": json.loads(row["characters"] or "{}"),
        "notes": row["notes"] or "",
    }
    slug = row["title"].lower().replace(" ", "_")[:50]
    return Response(
        json.dumps(export, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{slug}.json"'},
    )


@app.route("/stories/import", methods=["POST"])
@login_required
def import_story():
    data = request.get_json(silent=True) or {}
    if data.get("export_version") != 1:
        return jsonify({"error": "Unsupported export version"}), 400
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    characters = data.get("characters", {})
    if not isinstance(characters, dict):
        characters = {}
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, characters, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user_id,
                title,
                data.get("description", ""),
                data.get("genre", ""),
                data.get("opening", ""),
                data.get("narrator_prompt", DEFAULT_NARRATOR_PROMPT),
                data.get("narrator_model", "default"),
                data.get("player_name", "Adventurer"),
                data.get("player_background", ""),
                data.get("subgraph_name", "conversation"),
                json.dumps(characters),
                data.get("notes", ""),
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"id": new_id, "title": title}), 201


# ---------------------------------------------------------------------------
# Play
# ---------------------------------------------------------------------------

active_games: dict[str, dict] = {}
_adventure_locks: dict[str, threading.Lock] = {}
_adventure_locks_guard = threading.Lock()
CHAT_LOCK_TIMEOUT_S = 60


def _get_adventure_lock(session_key: str) -> threading.Lock:
    with _adventure_locks_guard:
        lock = _adventure_locks.get(session_key)
        if lock is None:
            lock = threading.Lock()
            _adventure_locks[session_key] = lock
        return lock


def _play_session_key(story_id: int, user_id: int) -> str:
    return f"session_{story_id}_{user_id}"


def _build_state_from_story(row) -> dict:
    narrator_prompt = (row["narrator_prompt"] or "").strip() or DEFAULT_NARRATOR_PROMPT
    model = (row["narrator_model"] or "default").strip()
    if model == "default":
        model = DEFAULT_MODEL
    return {
        "message": "",
        "response": "",
        "history": [],
        "memory_summary": "",
        "narrator": {"prompt": narrator_prompt, "model": model},
        "player": {
            "name": row["player_name"] or "Adventurer",
            "background": row["player_background"] or "",
        },
        "characters": json.loads(row["characters"] or "{}"),
        "game_title": row["title"],
        "opening": row["opening"] or "",
        "paused": False,
        "turn_count": 0,
    }


def _serialize_state(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False)


def _upsert_save(conn, story_id: int, user_id: int, slot: int, state: dict):
    conn.execute(
        """INSERT INTO saves (story_id, user_id, slot, state, saved_at)
           VALUES (?, ?, ?, ?, datetime('now'))
           ON CONFLICT(story_id, user_id, slot) DO UPDATE SET
               state = excluded.state, saved_at = excluded.saved_at""",
        (story_id, user_id, slot, _serialize_state(state)),
    )


@app.route("/play/start", methods=["POST"])
@login_required
def play_start():
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND (user_id = ? OR is_public = 1)",
            (story_id, g.user_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Story not found"}), 404

        state = _build_state_from_story(row)
        opening = (row["opening"] or "").strip()
        if opening:
            state["response"] = opening

        session_key = _play_session_key(story_id, g.user_id)
        state["_story_id"] = story_id
        state["_subgraph_name"] = row["subgraph_name"] or "conversation"
        active_games[session_key] = state

        _upsert_save(conn, story_id, g.user_id, 0, state)
        conn.execute(
            "UPDATE stories SET play_count = play_count + 1 WHERE id = ?", (story_id,)
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "session_id": session_key,
        "response": state.get("response", ""),
        "state": {
            "game_title": state["game_title"],
            "turn_count": state["turn_count"],
            "paused": state["paused"],
            "characters": state.get("characters", {}),
            "memory_summary": state.get("memory_summary", ""),
            "player": state.get("player", {}),
            "subgraph_name": state.get("_subgraph_name", ""),
        },
    })


@app.route("/play/chat", methods=["POST"])
@login_required
def play_chat():
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    session_key = _play_session_key(story_id, g.user_id)

    # Load from save if not in memory
    if session_key not in active_games:
        conn = get_db()
        try:
            save_row = conn.execute(
                """SELECT state FROM saves WHERE story_id = ? AND user_id = ?
                   ORDER BY saved_at DESC LIMIT 1""",
                (story_id, g.user_id),
            ).fetchone()
        finally:
            conn.close()
        if not save_row:
            return jsonify({"error": "No active game. Start a new game first."}), 400
        try:
            st = json.loads(save_row["state"])
        except (json.JSONDecodeError, TypeError):
            return jsonify({"error": "Save data is corrupt"}), 400
        # Restore runtime metadata
        conn2 = get_db()
        try:
            story_row = conn2.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        finally:
            conn2.close()
        if story_row:
            st["_story_id"] = story_id
            st["_subgraph_name"] = story_row["subgraph_name"] or "conversation"
        active_games[session_key] = st

    adv_lock = _get_adventure_lock(session_key)
    if not adv_lock.acquire(timeout=CHAT_LOCK_TIMEOUT_S):
        return jsonify({"error": "Another turn is still in progress."}), 429

    try:
        state = active_games[session_key]

        if state.get("paused"):
            return jsonify({
                "response": "The game is paused. Unpause to continue playing.",
                "game_title": state.get("game_title", ""),
                "turn_count": state.get("turn_count", 0),
                "paused": True,
            })

        state["message"] = message

        subgraph_name = state.get("_subgraph_name", "conversation")
        if subgraph_name not in registry:
            return jsonify({"error": f"Subgraph not available: {subgraph_name}"}), 503

        compiled = registry.get(subgraph_name)
        try:
            result = compiled.invoke(state)
        except Exception as e:
            logger.exception("play/chat graph invoke failed")
            return jsonify({"error": f"Internal error: {e}"}), 500

        if not isinstance(result, dict):
            result = dict(state)

        result["_story_id"] = story_id
        result["_subgraph_name"] = subgraph_name
        active_games[session_key] = result

        conn = get_db()
        try:
            _upsert_save(conn, story_id, g.user_id, 0, result)
            conn.commit()
        finally:
            conn.close()

        return jsonify({
            "response": result.get("response", ""),
            "game_title": result.get("game_title", ""),
            "turn_count": result.get("turn_count", 0),
            "paused": result.get("paused", False),
            "characters": result.get("characters", {}),
            "memory_summary": result.get("memory_summary", ""),
            "player": result.get("player", {}),
            "subgraph_name": result.get("_subgraph_name", ""),
        })
    finally:
        adv_lock.release()


@app.route("/play/status", methods=["GET"])
@login_required
def play_status():
    try:
        story_id = int(request.args.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400

    session_key = _play_session_key(story_id, g.user_id)
    if session_key not in active_games:
        conn = get_db()
        try:
            save_row = conn.execute(
                """SELECT state FROM saves WHERE story_id = ? AND user_id = ?
                   ORDER BY saved_at DESC LIMIT 1""",
                (story_id, g.user_id),
            ).fetchone()
        finally:
            conn.close()
        if not save_row:
            return jsonify({"error": "No active game"}), 404
        try:
            st = json.loads(save_row["state"])
        except (json.JSONDecodeError, TypeError):
            return jsonify({"error": "Save data is corrupt"}), 400
        conn2 = get_db()
        try:
            story_row = conn2.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        finally:
            conn2.close()
        if story_row:
            st["_story_id"] = story_id
            st["_subgraph_name"] = story_row["subgraph_name"] or "conversation"
        active_games[session_key] = st

    state = active_games[session_key]

    conn = get_db()
    try:
        save_rows = conn.execute(
            "SELECT slot, saved_at, state FROM saves WHERE story_id = ? AND user_id = ? ORDER BY slot",
            (story_id, g.user_id),
        ).fetchall()
    finally:
        conn.close()

    save_slots = []
    for sr in save_rows:
        try:
            sd = json.loads(sr["state"])
            turns = sd.get("turn_count", 0)
        except Exception:
            turns = 0
        save_slots.append({
            "slot": sr["slot"],
            "timestamp": sr["saved_at"],
            "turns": turns,
        })

    payload = {
        "response": state.get("response", ""),
        "game_title": state.get("game_title", ""),
        "turn_count": state.get("turn_count", 0),
        "paused": state.get("paused", False),
        "characters": state.get("characters", {}),
        "memory_summary": state.get("memory_summary", ""),
        "player": state.get("player", {}),
        "subgraph_name": state.get("_subgraph_name", ""),
        "save_slots": save_slots,
    }
    if state.get("turn_count", 0) == 0 and state.get("opening"):
        payload["empty_history_opening"] = state["opening"]

    return jsonify(payload)


@app.route("/play/save", methods=["POST"])
@login_required
def play_save():
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
        slot = int(data.get("slot", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid story_id or slot"}), 400
    if slot < 0 or slot >= SAVE_SLOTS:
        return jsonify({"error": "invalid slot"}), 400
    session_key = _play_session_key(story_id, g.user_id)
    if session_key not in active_games:
        return jsonify({"error": "No active game"}), 400
    conn = get_db()
    try:
        _upsert_save(conn, story_id, g.user_id, slot, active_games[session_key])
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/play/load", methods=["POST"])
@login_required
def play_load():
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
        slot = int(data.get("slot", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid story_id or slot"}), 400
    conn = get_db()
    try:
        save_row = conn.execute(
            "SELECT state FROM saves WHERE story_id = ? AND user_id = ? AND slot = ?",
            (story_id, g.user_id, slot),
        ).fetchone()
    finally:
        conn.close()
    if not save_row:
        return jsonify({"error": "Save slot empty"}), 404
    try:
        st = json.loads(save_row["state"])
    except (json.JSONDecodeError, TypeError):
        return jsonify({"error": "Save data is corrupt"}), 400
    conn2 = get_db()
    try:
        story_row = conn2.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    finally:
        conn2.close()
    if story_row:
        st["_story_id"] = story_id
        st["_subgraph_name"] = story_row["subgraph_name"] or "conversation"
    session_key = _play_session_key(story_id, g.user_id)
    active_games[session_key] = st
    return jsonify({
        "ok": True,
        "turn_count": st.get("turn_count", 0),
        "response": st.get("response", ""),
    })


@app.route("/play/saves", methods=["GET"])
@login_required
def play_saves():
    try:
        story_id = int(request.args.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT slot, saved_at, state FROM saves WHERE story_id = ? AND user_id = ? ORDER BY slot",
            (story_id, g.user_id),
        ).fetchall()
    finally:
        conn.close()
    slots = []
    for r in rows:
        try:
            sd = json.loads(r["state"])
            turns = sd.get("turn_count", 0)
        except Exception:
            turns = 0
        slots.append({"slot": r["slot"], "timestamp": r["saved_at"], "turns": turns})
    return jsonify({"slots": slots})


@app.route("/play/pause", methods=["POST"])
@login_required
def play_pause():
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    session_key = _play_session_key(story_id, g.user_id)
    if session_key not in active_games:
        return jsonify({"error": "No active game"}), 400
    active_games[session_key]["paused"] = True
    return jsonify({"ok": True, "paused": True})


@app.route("/play/unpause", methods=["POST"])
@login_required
def play_unpause():
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    session_key = _play_session_key(story_id, g.user_id)
    if session_key not in active_games:
        return jsonify({"error": "No active game"}), 400
    active_games[session_key]["paused"] = False
    return jsonify({"ok": True, "paused": False})


# ---------------------------------------------------------------------------
# AI assist
# ---------------------------------------------------------------------------

def _llm_result_to_text(result) -> str:
    if isinstance(result, str):
        return result
    content = getattr(result, "content", result)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(content)


def _strip_markdown_json_fences(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s[3:]
    if s.lower().startswith("json"):
        s = s[4:].lstrip()
    if s.startswith("\n"):
        s = s[1:]
    else:
        idx = s.find("\n")
        if idx >= 0:
            s = s[idx + 1:]
    fence = s.rfind("```")
    if fence >= 0:
        s = s[:fence]
    return s.strip()


@app.route("/ai/generate-story", methods=["POST"])
@login_required
def ai_generate_story():
    data = request.get_json(silent=True) or {}
    concept = (data.get("concept") or "").strip()
    if not concept:
        return jsonify({"error": "concept is required"}), 400
    if len(concept) > 5000:
        return jsonify({"error": "concept must be at most 5000 characters"}), 400

    prompt = f"""You are a game designer for a parser-style text RPG (second-person, "you").

The user described this story idea:
---
{concept}
---

Output a single JSON object (no markdown, no code fences, no commentary) with these fields:
- title: string
- opening: string (second person, present tense; first thing the player reads)
- description: string (short catalog pitch, 1-2 sentences)
- genre: one of mystery, thriller, drama, comedy, sci-fi, horror, fantasy
- narrator_prompt: string (voice/style instructions for the narrator)
- player_name: string
- player_background: string

Respond with ONLY valid JSON."""

    try:
        llm = get_llm(DEFAULT_MODEL)
        raw = llm.invoke(prompt)
        text = _llm_result_to_text(raw)
        cleaned = _strip_markdown_json_fences(text)
        story = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return jsonify({"error": "The model did not return valid JSON. Try again.", "detail": str(e)}), 422
    except Exception as e:
        logger.exception("ai/generate-story failed")
        return jsonify({"error": "The AI request failed. Try again later."}), 500

    if not isinstance(story, dict):
        return jsonify({"error": "AI response was not a JSON object"}), 422

    return jsonify({"story": story, "prompt_used": prompt})


_IMPROVE_FIELDS = {
    "opening": {
        "purpose": "Opening prose the player reads first. Second person, present tense. Should set the scene and hook the player.",
        "default_task": "Improve the opening — tighten prose, strengthen sensory details, build atmosphere. Keep second person present tense. Make the player want to keep reading.",
    },
    "description": {
        "purpose": "One- or two-sentence catalog pitch. Enticing, spoiler-light.",
        "default_task": "Improve the description — make it punchier and more enticing. Keep it to 1-2 sentences. No spoilers.",
    },
    "narrator_prompt": {
        "purpose": "System instructions for the narrator LLM: tone, pacing, second person, how to end beats.",
        "default_task": "Improve the narrator instructions — make them clearer and more specific about tone, pacing, and style. Ensure they tell the narrator to use second person and how to end beats.",
    },
    "player_background": {
        "purpose": "Player character history and situation — concrete, playable, gives the narrator context.",
        "default_task": "Improve the player background — make it more concrete and vivid. Give the narrator specific details to reference. Keep it playable and interesting.",
    },
    "character_prompt": {
        "purpose": "Personality instructions for an NPC: speech patterns, secrets, attitude, goals. The NPC speaks in first person as themselves.",
        "default_task": "Improve the character personality — make the instructions more specific about speech patterns, attitude, and motivations. Add distinct verbal habits or quirks that make this character unique.",
    },
    "character_first_line": {
        "purpose": "The NPC's first spoken line when the game begins — short, in-character, sets their tone immediately.",
        "default_task": "Improve the first line — make it feel natural, in-character, and immediately reveal something about this person's personality. Keep it short (1-2 sentences).",
    },
}


@app.route("/ai/improve-text", methods=["POST"])
@login_required
def ai_improve_text():
    data = request.get_json(silent=True) or {}
    field = (data.get("field") or "").strip()
    text = (data.get("text") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    context = data.get("context") or {}

    field_config = _IMPROVE_FIELDS.get(field)
    if not field_config:
        return jsonify({"error": "invalid field"}), 400
    if not text:
        return jsonify({"error": "text is required"}), 400

    purpose = field_config["purpose"]
    task = f"Author request:\n{instruction}" if instruction else (
        f"Task: {field_config['default_task']}"
    )

    # Build context block from related story data
    context_lines = []
    if context.get("title"):
        context_lines.append(f"Story title: {context['title']}")
    if context.get("genre"):
        context_lines.append(f"Genre: {context['genre']}")
    if context.get("narrator_prompt") and field != "narrator_prompt":
        context_lines.append(f"Narrator style: {context['narrator_prompt'][:200]}")
    if context.get("player_name"):
        context_lines.append(f"Player character: {context['player_name']}")
    if context.get("player_background") and field != "player_background":
        context_lines.append(f"Player background: {context['player_background'][:200]}")
    if context.get("character_prompt") and field == "character_first_line":
        context_lines.append(f"Character personality: {context['character_prompt'][:300]}")
    if context.get("character_key"):
        context_lines.append(f"Character name: {context['character_key'].replace('_', ' ').title()}")
    context_block = "\n".join(context_lines)
    context_section = f"\nStory context (use this to stay consistent):\n{context_block}\n" if context_block else ""

    prompt = f"""You help authors write content for a text-based RPG engine.

Field: {field}
Purpose: {purpose}
{context_section}
Current draft:
---
{text}
---

{task}

Output rules:
- Reply with ONLY the replacement text for this field.
- No title, no code fences, no quotation marks wrapping.
- Stay consistent with the story context above."""

    try:
        llm = get_llm(DEFAULT_MODEL)
        raw = llm.invoke(prompt)
        out = _llm_result_to_text(raw).strip()
        if out.startswith("```"):
            out = _strip_markdown_json_fences(out)
        return jsonify({"text": out, "prompt_used": prompt})
    except Exception as e:
        logger.exception("ai/improve-text failed")
        return jsonify({"error": "The AI request failed. Try again later."}), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

init_db()
seed_builtin_subgraphs()
seed_builtin_stories()

_conn = get_db()
registry.load_from_db(_conn)
_conn.close()

if __name__ == "__main__":
    print(f"RPG Engine Basic running on http://{FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
