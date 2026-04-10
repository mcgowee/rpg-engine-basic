"""Flask API — auth, subgraphs, main graph templates, stories, play, AI assist."""

import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

from flask import Flask, g, has_request_context, jsonify, request, session, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from auth import check_password, hash_password, login_required
from config import (
    DEFAULT_MODEL,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    GAME_SESSION_CACHE_MAX,
    GAME_SESSION_CACHE_TTL_S,
    LLM_PROVIDER,
    OLLAMA_HOST,
    RATE_LIMIT_AI,
    RATE_LIMIT_PLAY_CHAT,
    SAVE_SLOTS,
    SECRET_KEY,
)
from db import (
    get_db,
    init_db,
    seed_builtin_stories,
    seed_builtin_subgraphs,
    sync_builtin_story_characters_from_disk,
    sync_builtin_story_covers_from_disk,
    sync_builtin_subgraphs_from_disk,
)
from game_cache import GameSessionCache
from graphs.builder import validate_graph_definition
from graphs.registry import registry
from llm import get_llm
from llm.text import llm_result_to_text
from image_records import create_image_record, mark_image_failed, mark_image_ready
from nodes import NODE_REGISTRY

# Default narrator prompt — kept for backward compatibility with story CRUD
DEFAULT_NARRATOR_PROMPT = (
    "You are the narrator for a text adventure. Describe scenes in second person. "
    "End each beat with: What do you do?"
)
from play_phases import (
    advance_phase_after_turn,
    apply_main_graph_to_new_state,
    hydrate_runtime_from_story_save,
)
# Routers no longer used — graphs use __start__/__end__ edges

logger = logging.getLogger(__name__)


class _RequestExtraFilter(logging.Filter):
    def filter(self, record):
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
            record.user_id_log = getattr(g, "user_id", "-")
            record.story_id_log = getattr(g, "log_story_id", "-")
        else:
            record.request_id = "-"
            record.user_id_log = "-"
            record.story_id_log = "-"
        return True


logger.addFilter(_RequestExtraFilter())

app = Flask(__name__)
app.secret_key = SECRET_KEY


def _rate_limit_key():
    uid = session.get("user_id")
    if uid is not None:
        return f"uid:{uid}"
    return f"ip:{get_remote_address()}"


limiter = Limiter(
    key_func=_rate_limit_key,
    app=app,
    default_limits=[],
    storage_uri="memory://",
    headers_enabled=True,
)


def optional_rate_limit(limit_string: str):
    spec = (limit_string or "").strip()

    def deco(f):
        if spec:
            return limiter.limit(spec)(f)
        return f

    return deco


@app.before_request
def _assign_request_id():
    g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]


game_session_cache = GameSessionCache(GAME_SESSION_CACHE_TTL_S, GAME_SESSION_CACHE_MAX)
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
        "description": "Takes the player's message and generates narrative prose (no character dialogue). Writes `_narrator_text` and participates in the shared `response` field for downstream nodes.",
        "llm": True,
        "reads": [
            "message", "narrator", "player", "characters", "history", "memory_summary",
            "game_title", "_subgraph_name",
        ],
        "writes": ["_narrator_text"],
    },
    "character_agent": {
        "summary": "Per-character dialogue and action via LLM",
        "description": "For each character, generates spoken line(s) and a short physical action from personality, history, and mood. Writes `_character_responses` for the response builder.",
        "llm": True,
        "reads": ["characters", "message", "player", "history", "memory_summary", "_narrator_text"],
        "writes": ["_character_responses"],
    },
    "response_builder": {
        "summary": "Assembles play UI bubbles",
        "description": "No LLM. Merges `_narrator_text` and `_character_responses` into `_bubbles` and a combined `response` string for clients that read a single field.",
        "llm": False,
        "reads": ["characters", "_narrator_text", "_character_responses"],
        "writes": ["_bubbles", "response"],
    },
    "scene_image": {
        "summary": "Scene / gallery image for sidebar",
        "description": "Selects or records scene art (gallery tags, triggers) for the play sidebar. No prose LLM.",
        "llm": False,
        "reads": ["story", "characters", "history", "_narrator_text", "_character_responses"],
        "writes": ["_scene_image", "_active_portraits", "_shown_images"],
    },
    "mood": {
        "summary": "Tracks character mood axes via LLM",
        "description": "For each character's mood axis, asks the LLM for UP, DOWN, or SAME from the turn context. Multiple axes mean multiple LLM calls.",
        "llm": True,
        "reads": ["characters", "message", "history", "memory_summary", "_character_responses"],
        "writes": ["characters"],
    },
    "condense": {
        "summary": "Rolling memory summary via LLM",
        "description": "Compresses structured `history` into `memory_summary` (short paragraph). Used for long-term context in narrator and agents.",
        "llm": True,
        "reads": ["history", "memory_summary", "message", "response", "narrator"],
        "writes": ["memory_summary"],
    },
    "memory": {
        "summary": "Records structured turn in history",
        "description": "Appends a structured dict (player, narrator, characters, mood snapshot) to `history` and updates `turn_count`. No LLM.",
        "llm": False,
        "reads": ["message", "history", "_narrator_text", "_character_responses", "characters"],
        "writes": ["history", "turn_count"],
    },
}

ROUTER_DESCRIPTIONS = {}  # Routers no longer used — graphs use __start__/__end__ edges


@app.route("/models", methods=["GET"])
def list_models():
    """Return available LLM models from all configured providers."""
    from config import LLM_PROVIDER, DEFAULT_MODEL, OLLAMA_HOST
    from config import AZURE_ENDPOINT, AZURE_DEPLOYMENT

    # Embedding model families to exclude
    EMBEDDING_FAMILIES = {"nomic-bert", "nomic-bert-moe"}

    providers = {}

    # Query Ollama
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3)
        data = json.loads(resp.read())
        ollama_models = []
        for m in data.get("models", []):
            details = m.get("details", {})
            family = details.get("family", "")
            # Skip embedding models
            if family in EMBEDDING_FAMILIES:
                continue
            ollama_models.append({
                "id": m["name"],
                "name": m["name"].split(":")[0].split("/")[-1],
                "size": details.get("parameter_size", ""),
                "family": family,
                "quantization": details.get("quantization_level", ""),
            })
        providers["ollama"] = {
            "available": True,
            "models": ollama_models,
        }
    except Exception:
        providers["ollama"] = {"available": False, "models": []}

    # Azure
    if AZURE_ENDPOINT:
        providers["azure"] = {
            "available": True,
            "models": [{
                "id": AZURE_DEPLOYMENT,
                "name": AZURE_DEPLOYMENT,
                "size": "",
                "family": "openai",
                "quantization": "",
            }],
        }
    else:
        providers["azure"] = {"available": False, "models": []}

    # Role defaults — resolved through the cascade
    roles = {
        "creative": get_model_for_role("creative"),
        "dialogue": get_model_for_role("dialogue"),
        "classification": get_model_for_role("classification"),
        "summarization": get_model_for_role("summarization"),
        "tools": get_model_for_role("tools"),
        "image_prompt": get_model_for_role("image_prompt"),
    }

    # Image model
    import comfyui_client
    image_model = comfyui_client.get_image_model_setting()
    image_models = [
        {"key": k, "name": v["ckpt_name"], "description": k.title()}
        for k, v in comfyui_client.CHECKPOINTS.items()
    ]

    return jsonify({
        "providers": providers,
        "roles": roles,
        "default": DEFAULT_MODEL,
        "active_provider": LLM_PROVIDER,
        "image_model": image_model,
        "image_models": image_models,
        "comfyui_available": comfyui_client.is_available(),
    })


from model_resolver import get_model_for_role, load_role_settings, save_role_settings, VALID_ROLES, set_session_model_override, clear_session_model_override


@app.route("/settings/model-override", methods=["POST"])
@login_required
def set_model_override():
    """Temporarily override all model selections (for A/B testing)."""
    data = request.get_json(silent=True) or {}
    model = (data.get("model") or "").strip()
    if model:
        set_session_model_override(model)
        return jsonify({"ok": True, "model": model})
    else:
        clear_session_model_override()
        return jsonify({"ok": True, "model": None})


@app.route("/settings/models", methods=["GET"])
@login_required
def get_model_settings():
    return jsonify(load_role_settings())


@app.route("/settings/models", methods=["PUT"])
@login_required
def save_model_settings():
    data = request.get_json(silent=True) or {}
    roles = data.get("roles", {})
    if not isinstance(roles, dict):
        return jsonify({"error": "roles must be an object"}), 400
    cleaned = {k: v for k, v in roles.items() if k in VALID_ROLES and isinstance(v, str)}
    save_role_settings(cleaned)

    # Save image model setting if provided
    image_model = data.get("image_model")
    if isinstance(image_model, str):
        import comfyui_client
        if image_model in comfyui_client.CHECKPOINTS:
            settings = load_role_settings()
            settings["image_model"] = image_model
            import json as _json
            settings_path = os.path.join(os.path.dirname(__file__), "model_settings.json")
            with open(settings_path, "w") as f:
                _json.dump(settings, f, indent=2)

    return jsonify({"ok": True})


@app.route("/graph-registry", methods=["GET"])
def graph_registry_keys():
    return jsonify({
        "nodes": sorted(NODE_REGISTRY.keys()),
        "node_descriptions": NODE_DESCRIPTIONS,
        "routers": {},
        "router_descriptions": {},
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
            "history": [],
            "memory_summary": "",
            "player": {"name": "Tester", "background": "A brave adventurer testing this subgraph."},
            "characters": {},
            "story": {},
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

def _row_main_graph_template_id(row) -> int | None:
    if "main_graph_template_id" not in row.keys():
        return None
    v = row["main_graph_template_id"]
    return int(v) if v is not None else None


def _resolve_main_template_for_write(conn, user_id, raw) -> tuple[int | None, str | None]:
    """Return (template_id or None, error message or None). None id clears the link."""
    if raw is None:
        return None, None
    if raw in ("", 0, "0", False):
        return None, None
    try:
        tid = int(raw)
    except (TypeError, ValueError):
        return None, "invalid main_graph_template_id"
    ok = conn.execute(
        "SELECT id FROM main_graph_templates WHERE id = ? AND (user_id = ? OR is_public = 1)",
        (tid, user_id),
    ).fetchone()
    if not ok:
        return None, "main graph template not found"
    return tid, None


def _story_row_to_dict(r, include_content=False) -> dict:
    try:
        story_images = json.loads(r["story_images"] or "[]") if "story_images" in r.keys() else []
    except (json.JSONDecodeError, TypeError):
        story_images = []
    if not isinstance(story_images, list):
        story_images = []
    d = {
        "id": r["id"],
        "title": r["title"],
        "description": r["description"],
        "genre": r["genre"],
        "tone": r["tone"] or "",
        "nsfw_rating": r["nsfw_rating"] or "none",
        "nsfw_tags": json.loads(r["nsfw_tags"] or "[]") if isinstance(r["nsfw_tags"], str) else (r["nsfw_tags"] or []),
        "subgraph_name": r["subgraph_name"],
        "main_graph_template_id": _row_main_graph_template_id(r),
        "notes": r["notes"] or "",
        "cover_image": r["cover_image"] or "",
        "cover_image_id": r["cover_image_id"] if "cover_image_id" in r.keys() else None,
        "story_images": story_images,
        "scene_gallery": json.loads(r["scene_gallery"] or "[]") if "scene_gallery" in r.keys() else [],
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
        tid, terr = _resolve_main_template_for_write(conn, g.user_id, data.get("main_graph_template_id"))
        if terr:
            return jsonify({"error": terr}), 400
        nsfw_tags = data.get("nsfw_tags", [])
        if not isinstance(nsfw_tags, list):
            nsfw_tags = []
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, tone,
                  nsfw_rating, nsfw_tags, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, main_graph_template_id, characters, notes, story_images)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user_id,
                title,
                data.get("description", ""),
                data.get("genre", ""),
                data.get("tone", ""),
                data.get("nsfw_rating", "none"),
                json.dumps(nsfw_tags),
                data.get("opening", ""),
                data.get("narrator_prompt", DEFAULT_NARRATOR_PROMPT),
                data.get("narrator_model", "default"),
                data.get("player_name", "Adventurer"),
                data.get("player_background", ""),
                data.get("subgraph_name", "narrator_chat_lite"),
                tid,
                json.dumps(characters),
                data.get("notes", ""),
                "[]",
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
        update_story_images = data.get("story_images")
        if update_story_images is not None:
            if not isinstance(update_story_images, list):
                update_story_images = []
            story_images_json = json.dumps(update_story_images)
        else:
            story_images_json = row["story_images"] if "story_images" in row.keys() else "[]"
        if "main_graph_template_id" in data:
            tid, terr = _resolve_main_template_for_write(conn, g.user_id, data.get("main_graph_template_id"))
            if terr:
                return jsonify({"error": terr}), 400
        else:
            tid = _row_main_graph_template_id(row)
        update_nsfw_tags = data.get("nsfw_tags")
        if update_nsfw_tags is not None:
            if not isinstance(update_nsfw_tags, list):
                update_nsfw_tags = []
            nsfw_tags_json = json.dumps(update_nsfw_tags)
        else:
            nsfw_tags_json = row["nsfw_tags"] or "[]"
        update_scene_gallery = data.get("scene_gallery")
        if update_scene_gallery is not None:
            scene_gallery_json = json.dumps(update_scene_gallery if isinstance(update_scene_gallery, list) else [])
        else:
            scene_gallery_json = row["scene_gallery"] if "scene_gallery" in row.keys() else "[]"
        conn.execute(
            """UPDATE stories SET title = ?, description = ?, genre = ?, tone = ?,
                  nsfw_rating = ?, nsfw_tags = ?, opening = ?,
                  narrator_prompt = ?, narrator_model = ?, player_name = ?,
                  player_background = ?, subgraph_name = ?, main_graph_template_id = ?,
                  characters = ?, notes = ?, story_images = ?, scene_gallery = ?,
                  updated_at = datetime('now')
               WHERE id = ?""",
            (
                data.get("title", row["title"]),
                data.get("description", row["description"]),
                data.get("genre", row["genre"]),
                data.get("tone", row["tone"] or ""),
                data.get("nsfw_rating", row["nsfw_rating"] or "none"),
                nsfw_tags_json,
                data.get("opening", row["opening"]),
                data.get("narrator_prompt", row["narrator_prompt"]),
                data.get("narrator_model", row["narrator_model"]),
                data.get("player_name", row["player_name"]),
                data.get("player_background", row["player_background"]),
                data.get("subgraph_name", row["subgraph_name"]),
                tid,
                characters_json,
                data.get("notes", row["notes"]),
                story_images_json,
                scene_gallery_json,
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
        mtid = _row_main_graph_template_id(row)
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, tone,
                  nsfw_rating, nsfw_tags, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, main_graph_template_id, characters, notes, story_images)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user_id,
                row["title"],
                row["description"],
                row["genre"],
                row["tone"] or "",
                row["nsfw_rating"] or "none",
                row["nsfw_tags"] or "[]",
                row["opening"],
                row["narrator_prompt"],
                row["narrator_model"],
                row["player_name"],
                row["player_background"],
                row["subgraph_name"],
                mtid,
                row["characters"] or "{}",
                row["notes"] or "",
                row["story_images"] if "story_images" in row.keys() else "[]",
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
        tmpl_name = None
        mtid = _row_main_graph_template_id(row) if row else None
        if mtid is not None:
            trow = conn.execute(
                "SELECT name FROM main_graph_templates WHERE id = ?", (mtid,)
            ).fetchone()
            if trow:
                tmpl_name = trow["name"]
    finally:
        conn.close()
    if not row or (row["user_id"] != g.user_id and not row["is_public"]):
        return jsonify({"error": "Not found"}), 404
    try:
        nsfw_tags = json.loads(row["nsfw_tags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        nsfw_tags = []
    try:
        scene_gallery = json.loads(row["scene_gallery"] or "[]") if "scene_gallery" in row.keys() else []
    except (json.JSONDecodeError, TypeError):
        scene_gallery = []
    export = {
        "export_version": 2,
        "title": row["title"],
        "description": row["description"],
        "genre": row["genre"],
        "tone": row["tone"] or "",
        "nsfw_rating": row["nsfw_rating"] or "none",
        "nsfw_tags": nsfw_tags,
        "opening": row["opening"],
        "narrator_prompt": row["narrator_prompt"],
        "narrator_model": row["narrator_model"],
        "player_name": row["player_name"],
        "player_background": row["player_background"],
        "subgraph_name": row["subgraph_name"],
        "main_graph_template_name": tmpl_name,
        "characters": json.loads(row["characters"] or "{}"),
        "scene_gallery": scene_gallery,
        "notes": row["notes"] or "",
        "cover_image": row["cover_image"] or "",
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
    if data.get("export_version") not in (1, 2):
        return jsonify({"error": "Unsupported export version"}), 400
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    characters = data.get("characters", {})
    if not isinstance(characters, dict):
        characters = {}
    conn = get_db()
    try:
        tid = None
        tname = data.get("main_graph_template_name")
        if isinstance(tname, str) and tname.strip():
            trow = conn.execute(
                """SELECT id FROM main_graph_templates WHERE name = ?
                   AND (user_id = ? OR is_public = 1)""",
                (tname.strip(), g.user_id),
            ).fetchone()
            if trow:
                tid = trow["id"]
        import_nsfw_tags = data.get("nsfw_tags", [])
        if not isinstance(import_nsfw_tags, list):
            import_nsfw_tags = []
        import_scene_gallery = data.get("scene_gallery", [])
        if not isinstance(import_scene_gallery, list):
            import_scene_gallery = []
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, tone,
                  nsfw_rating, nsfw_tags, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, main_graph_template_id, characters, scene_gallery,
                  notes, cover_image)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user_id,
                title,
                data.get("description", ""),
                data.get("genre", ""),
                data.get("tone", ""),
                data.get("nsfw_rating", "none"),
                json.dumps(import_nsfw_tags),
                data.get("opening", ""),
                data.get("narrator_prompt", ""),
                data.get("narrator_model", "default"),
                data.get("player_name", "Adventurer"),
                data.get("player_background", ""),
                data.get("subgraph_name", "narrator_chat_lite"),
                tid,
                json.dumps(characters),
                json.dumps(import_scene_gallery),
                data.get("notes", ""),
                (data.get("cover_image") or "").strip(),
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
    nsfw_tags = []
    try:
        nsfw_tags = json.loads(row["nsfw_tags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        pass
    scene_gallery = []
    try:
        scene_gallery = json.loads(row["scene_gallery"] or "[]")
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "message": "",
        "response": "",
        "history": [],
        "memory_summary": "",
        "player": {
            "name": row["player_name"] or "Adventurer",
            "background": row["player_background"] or "",
        },
        "characters": json.loads(row["characters"] or "{}"),
        "story": {
            "title": row["title"],
            "genre": row["genre"] or "",
            "tone": row["tone"] or "",
            "setting": row["description"] or "",
            "nsfw_rating": row["nsfw_rating"] or "none",
            "nsfw_tags": nsfw_tags,
            "scene_images": scene_gallery,
        },
        "game_title": row["title"],
        "opening": row["opening"] or "",
        "paused": False,
        "turn_count": 0,
        "_shown_images": [],
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


def _ensure_play_session(session_key: str, story_id: int, user_id: int) -> dict | None:
    """Load latest save into the session cache, or return cached state."""
    st = game_session_cache.get(session_key)
    if st is not None:
        return st
    conn = get_db()
    try:
        save_row = conn.execute(
            """SELECT state FROM saves WHERE story_id = ? AND user_id = ?
               ORDER BY saved_at DESC LIMIT 1""",
            (story_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    if not save_row:
        return None
    try:
        st = json.loads(save_row["state"])
    except (json.JSONDecodeError, TypeError):
        return None
    conn2 = get_db()
    try:
        story_row = conn2.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    finally:
        conn2.close()
    if story_row:
        hydrate_runtime_from_story_save(st, story_id, story_row)
    game_session_cache.set(session_key, st)
    return st


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
        perr = apply_main_graph_to_new_state(state, row, conn, g.user_id)
        if perr:
            return jsonify({"error": perr}), 400
        sg = state.get("_subgraph_name", "narrator_chat_lite")
        if sg not in registry:
            return jsonify({"error": f"Subgraph not available: {sg}"}), 503

        game_session_cache.set(session_key, state)

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
@optional_rate_limit(RATE_LIMIT_PLAY_CHAT)
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
    g.log_story_id = story_id

    adv_lock = _get_adventure_lock(session_key)
    if not adv_lock.acquire(timeout=CHAT_LOCK_TIMEOUT_S):
        return jsonify({"error": "Another turn is still in progress."}), 429

    try:
        state = _ensure_play_session(session_key, story_id, g.user_id)
        if state is None:
            return jsonify({"error": "No active game. Start a new game first."}), 400

        if state.get("paused"):
            return jsonify({
                "response": "The game is paused. Unpause to continue playing.",
                "game_title": state.get("game_title", ""),
                "turn_count": state.get("turn_count", 0),
                "paused": True,
            })

        state["message"] = message

        subgraph_name = state.get("_subgraph_name", "narrator_chat_lite")
        if subgraph_name not in registry:
            return jsonify({"error": f"Subgraph not available: {subgraph_name}"}), 503

        compiled = registry.require(subgraph_name)
        try:
            result = compiled.invoke(state)
        except Exception as e:
            logger.exception(
                "play/chat graph invoke failed request_id=%s story_id=%s user_id=%s",
                getattr(g, "request_id", "-"),
                story_id,
                getattr(g, "user_id", "-"),
            )
            return jsonify({"error": f"Internal error: {e}"}), 500

        if not isinstance(result, dict):
            result = dict(state)

        # Ensure history is recorded even if subgraph has no memory node
        history = list(result.get("history") or state.get("history") or [])
        # Check if memory node already recorded this turn (structured dict)
        last_is_current = (
            history
            and isinstance(history[-1], dict)
            and history[-1].get("player") == message
        )
        if not last_is_current:
            # Fallback: record as structured turn
            char_responses = result.get("_character_responses") or {}
            turn_entry = {
                "player": message,
                "narrator": (result.get("_narrator_text") or "").strip(),
                "characters": {
                    k: {"dialogue": v.get("dialogue", ""), "action": v.get("action", "")}
                    for k, v in char_responses.items()
                    if isinstance(v, dict)
                },
                "mood": {},
            }
            history.append(turn_entry)
            result["history"] = history
        if "turn_count" not in result or result["turn_count"] == state.get("turn_count", 0):
            result["turn_count"] = len(history)

        result["_story_id"] = story_id

        conn = get_db()
        try:
            advance_phase_after_turn(result, message, conn, g.user_id)
            result["_subgraph_name"] = result.get("_subgraph_name", subgraph_name)
            _upsert_save(conn, story_id, g.user_id, 0, result)
            conn.commit()
        finally:
            conn.close()

        game_session_cache.set(session_key, result)

        return jsonify({
            "response": result.get("response", ""),
            "bubbles": result.get("_bubbles", []),
            "narrator_text": result.get("_narrator_text", ""),
            "character_responses": result.get("_character_responses", {}),
            "game_title": result.get("game_title", ""),
            "turn_count": result.get("turn_count", 0),
            "paused": result.get("paused", False),
            "characters": result.get("characters", {}),
            "memory_summary": result.get("memory_summary", ""),
            "player": result.get("player", {}),
            "subgraph_name": result.get("_subgraph_name", ""),
            "scene_image": result.get("_scene_image"),
            "active_portraits": result.get("_active_portraits", {}),
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
    state = _ensure_play_session(session_key, story_id, g.user_id)
    if state is None:
        return jsonify({"error": "No active game"}), 404

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
        "history": state.get("history", []),
        "game_title": state.get("game_title", ""),
        "turn_count": state.get("turn_count", 0),
        "paused": state.get("paused", False),
        "characters": state.get("characters", {}),
        "memory_summary": state.get("memory_summary", ""),
        "player": state.get("player", {}),
        "subgraph_name": state.get("_subgraph_name", ""),
        "save_slots": save_slots,
    }
    if state.get("opening"):
        payload["opening"] = state["opening"]

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
    cached = _ensure_play_session(session_key, story_id, g.user_id)
    if cached is None:
        return jsonify({"error": "No active game"}), 400
    conn = get_db()
    try:
        _upsert_save(conn, story_id, g.user_id, slot, cached)
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
        hydrate_runtime_from_story_save(st, story_id, story_row)
    session_key = _play_session_key(story_id, g.user_id)
    game_session_cache.set(session_key, st)
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
    st = _ensure_play_session(session_key, story_id, g.user_id)
    if st is None:
        return jsonify({"error": "No active game"}), 400
    st["paused"] = True
    game_session_cache.set(session_key, st)
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
    st = _ensure_play_session(session_key, story_id, g.user_id)
    if st is None:
        return jsonify({"error": "No active game"}), 400
    st["paused"] = False
    game_session_cache.set(session_key, st)
    return jsonify({"ok": True, "paused": False})


# ---------------------------------------------------------------------------
# AI assist
# ---------------------------------------------------------------------------

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
@optional_rate_limit(RATE_LIMIT_AI)
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
        llm = get_llm(get_model_for_role("tools"))
        raw = llm.invoke(prompt)
        text = llm_result_to_text(raw)
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
    "notes": {
        "purpose": "Author notes explaining what this story demonstrates, tips for players, or design rationale.",
        "default_task": "Improve the notes — make them clearer and more helpful. Explain what engine features the story demonstrates and what players should try. Keep it concise.",
    },
}


@app.route("/ai/improve-text", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
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
        llm = get_llm(get_model_for_role("tools"))
        raw = llm.invoke(prompt)
        out = llm_result_to_text(raw).strip()
        if out.startswith("```"):
            out = _strip_markdown_json_fences(out)
        return jsonify({"text": out, "prompt_used": prompt})
    except Exception as e:
        logger.exception("ai/improve-text failed")
        return jsonify({"error": "The AI request failed. Try again later."}), 500


@app.route("/ai/suggest", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_suggest():
    data = request.get_json(silent=True) or {}
    field = (data.get("field") or "").strip()
    context = data.get("context") or {}
    current = (data.get("current") or "").strip()
    count = min(int(data.get("count", 5)), 8)

    # Build context block
    ctx_lines = []
    if context.get("title"):
        ctx_lines.append(f"Story title: {context['title']}")
    if context.get("genre"):
        ctx_lines.append(f"Genre: {context['genre']}")
    if context.get("opening"):
        ctx_lines.append(f"Opening: {context['opening'][:300]}")
    if context.get("narrator_prompt"):
        ctx_lines.append(f"Narrator style: {context['narrator_prompt'][:200]}")
    if context.get("player_name"):
        ctx_lines.append(f"Player character: {context['player_name']}")
    if context.get("player_background"):
        ctx_lines.append(f"Player background: {context['player_background'][:200]}")
    if context.get("character_key"):
        ctx_lines.append(f"Character name: {context['character_key'].replace('_', ' ').title()}")
    if context.get("character_prompt"):
        ctx_lines.append(f"Character personality: {context['character_prompt'][:300]}")
    if context.get("existing_axes"):
        ctx_lines.append(f"Existing mood axes: {context['existing_axes']}")
    ctx_block = "\n".join(ctx_lines)

    if field == "title":
        prompt = f"""You are naming a text-based RPG story. Based on the context below, suggest {count} short, evocative titles.

{ctx_block}

Rules:
- Each title should be 2-5 words
- Fit the genre and tone
- Be intriguing without spoilers
- One per line, no numbering, no quotes, no explanation"""

    elif field == "player_name":
        prompt = f"""You are naming a player character for a text-based RPG. Based on the context below, suggest {count} character names.

{ctx_block}

Rules:
- Names should fit the genre, setting, and era
- Mix of styles: first name only, full name, nickname
- One per line, no numbering, no quotes, no explanation"""

    elif field == "mood_axis_new":
        prompt = f"""You are designing emotional dimensions for an NPC in a text-based RPG. Based on the context below, suggest {count} mood axes.

{ctx_block}

Each axis has a name, a low label (1/10), and a high label (10/10).
The axis should create interesting gameplay — something the player's actions can influence.

Rules:
- Format each as: axis_name|low_label|high_label
- Use lowercase for axis name
- Labels should be single descriptive words or short phrases
- Don't repeat axes that already exist
- One per line, no numbering, no explanation

Example format:
trust|suspicious|trusting
courage|terrified|brave"""

    elif field == "mood_axis_refine":
        prompt = f"""You are refining mood axis labels for an NPC in a text-based RPG. The current axis needs better labels that more precisely capture the emotional range.

{ctx_block}
Current axis: {current}

Suggest {count} alternative versions of this axis with improved labels. Keep the same concept but find more evocative, specific, or gameplay-useful wordings.

Rules:
- Format each as: axis_name|low_label|high_label
- Use lowercase for axis name
- One per line, no numbering, no explanation"""

    else:
        return jsonify({"error": f"Unknown suggest field: {field}"}), 400

    try:
        llm = get_llm(get_model_for_role("tools"))
        raw = llm.invoke(prompt)
        text = llm_result_to_text(raw).strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        suggestions = []
        for line in lines[:count]:
            # Clean up common LLM formatting artifacts
            cleaned = line.lstrip("0123456789.-) ").strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            if cleaned.startswith("'") and cleaned.endswith("'"):
                cleaned = cleaned[1:-1]
            if not cleaned:
                continue

            if field in ("mood_axis_new", "mood_axis_refine") and "|" in cleaned:
                parts = cleaned.split("|", 2)
                if len(parts) == 3:
                    suggestions.append({
                        "axis": parts[0].strip(),
                        "low": parts[1].strip(),
                        "high": parts[2].strip(),
                    })
            else:
                suggestions.append({"text": cleaned})

        return jsonify({"suggestions": suggestions})
    except Exception as e:
        logger.exception("ai/suggest failed")
        return jsonify({"error": "The AI request failed. Try again later."}), 500


# ---------------------------------------------------------------------------
# Story book
# ---------------------------------------------------------------------------

@app.route("/stories/<int:story_id>/book-data", methods=["GET"])
@login_required
def story_book_data(story_id: int):
    """Return story metadata + play history for book rendering."""
    conn = get_db()
    try:
        story_row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND (user_id = ? OR is_public = 1)",
            (story_id, g.user_id),
        ).fetchone()
        if not story_row:
            return jsonify({"error": "Story not found"}), 404

        # Get the latest save for this user
        save_row = conn.execute(
            """SELECT state FROM saves WHERE story_id = ? AND user_id = ?
               ORDER BY saved_at DESC LIMIT 1""",
            (story_id, g.user_id),
        ).fetchone()
    finally:
        conn.close()

    history = []
    if save_row:
        try:
            state = json.loads(save_row["state"])
            history = state.get("history", [])
        except (json.JSONDecodeError, TypeError):
            pass

    characters = {}
    try:
        characters = json.loads(story_row["characters"] or "{}")
    except (json.JSONDecodeError, TypeError):
        pass

    return jsonify({
        "title": story_row["title"],
        "description": story_row["description"],
        "genre": story_row["genre"],
        "tone": story_row["tone"] or "",
        "opening": story_row["opening"],
        "cover_image": story_row["cover_image"] or "",
        "player_name": story_row["player_name"],
        "player_background": story_row["player_background"],
        "characters": characters,
        "history": history,
    })


@app.route("/ai/generate-book", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_book():
    """Rewrite play history into polished prose, scene by scene."""
    data = request.get_json(silent=True) or {}
    history = data.get("history", [])
    opening = (data.get("opening") or "").strip()
    title = (data.get("title") or "Untitled").strip()
    player_name = (data.get("player_name") or "the adventurer").strip()
    characters = data.get("characters", {})
    genre = (data.get("genre") or "").strip()
    tone = (data.get("tone") or "").strip()

    if not history:
        return jsonify({"error": "No play history to convert"}), 400

    # Build character list
    char_names = []
    for key, val in characters.items():
        if isinstance(val, dict):
            char_names.append(key.replace("_", " ").title())

    char_block = f"\nCharacters: {', '.join(char_names)}" if char_names else ""
    genre_block = f"\nGenre: {genre}" if genre else ""
    tone_block = f"\nTone: {tone}" if tone else ""

    # Build structured transcript — one scene per turn
    scenes = []
    if opening:
        scenes.append({"type": "opening", "text": opening})

    for i, entry in enumerate(history):
        scene = {"turn": i + 1, "type": "turn"}

        if isinstance(entry, dict):
            # New structured format
            scene["player"] = entry.get("player", "")
            scene["narrator"] = entry.get("narrator", "")
            scene["characters"] = {}
            for ck, cv in (entry.get("characters") or {}).items():
                if isinstance(cv, dict):
                    label = ck.replace("_", " ").title()
                    scene["characters"][label] = {
                        "dialogue": cv.get("dialogue", ""),
                        "action": cv.get("action", ""),
                    }
            # Include scene image and portrait info if available
            if entry.get("scene_image"):
                si = entry["scene_image"]
                scene["scene_image"] = si.get("url", "") if isinstance(si, dict) else ""
            if entry.get("active_portraits"):
                scene["active_portraits"] = entry["active_portraits"]
        elif isinstance(entry, str):
            # Legacy flat format
            scene["text"] = entry
        else:
            scene["text"] = str(entry)

        scenes.append(scene)

    # Build transcript parts per turn
    def _build_turn_transcript(scene):
        if scene.get("type") == "opening":
            return f"[Opening]\n{scene['text']}"
        elif scene.get("narrator") or scene.get("characters"):
            part = ""
            if scene.get("player"):
                part += f"Player: {scene['player']}\n"
            if scene.get("narrator"):
                part += f"Narrator: {scene['narrator']}\n"
            for label, resp in scene.get("characters", {}).items():
                if resp.get("action"):
                    part += f"*{label} {resp['action']}*\n"
                if resp.get("dialogue"):
                    part += f'{label}: "{resp["dialogue"]}"\n'
            return part.strip()
        elif scene.get("text"):
            # Skip scene image markers
            text = scene.get("text", "")
            if text.startswith("[SCENE_IMAGE:"):
                return ""
            return text
        return ""

    try:
        llm = get_llm(get_model_for_role("creative"))

        # Generate scene by scene for reliable section breaks
        prose_sections = []
        content_scenes = []
        prev_context = ""

        for i, scene in enumerate(scenes):
            turn_transcript = _build_turn_transcript(scene)
            if not turn_transcript.strip():
                continue

            if scene.get("type") == "opening":
                scene_prompt = f"""You are a skilled fiction writer. Write the opening scene for a story.

Title: {title}
Player character: {player_name}{char_block}{genre_block}{tone_block}

Opening text:
{turn_transcript}

Rewrite this opening into 2-3 polished paragraphs. Third person past tense. Set the scene and atmosphere.
Output ONLY the prose, no title, no labels:"""
            else:
                scene_prompt = f"""You are a skilled fiction writer. Write the next scene of a story.

Title: {title}
Player character: {player_name}{char_block}{genre_block}{tone_block}

Previous context: {prev_context[:300]}

This turn:
{turn_transcript}

Rewrite this turn into 2-3 polished paragraphs. Rules:
- Third person past tense
- Replace "Player:" with narrative prose about {player_name}
- Character dialogue in quotes with attribution
- Weave actions and narrator descriptions into prose
- Output ONLY the prose, no labels, no "---":"""

            raw = llm.invoke(scene_prompt)
            section_text = llm_result_to_text(raw).strip()

            # Clean up
            for prefix in ["Scene:", "scene:", "Opening:", "opening:"]:
                if section_text.startswith(prefix):
                    section_text = section_text[len(prefix):].strip()

            if section_text:
                # Build structured scene object
                scene_obj = {
                    "turn": scene.get("turn", 0),
                    "prose": section_text,
                }
                # Attach scene image if available
                if scene.get("scene_image"):
                    scene_obj["scene_image"] = scene["scene_image"]
                # Attach active portraits or defaults
                if scene.get("active_portraits"):
                    scene_obj["portraits"] = scene["active_portraits"]
                else:
                    # Use default character portraits
                    for ck, cv in characters.items():
                        if isinstance(cv, dict) and cv.get("portrait"):
                            label = ck.replace("_", " ").title()
                            if "portraits" not in scene_obj:
                                scene_obj["portraits"] = {}
                            scene_obj["portraits"][label] = cv["portrait"]

                prose_sections.append(section_text)
                content_scenes.append(scene_obj)
                prev_context = section_text[-200:]

        prose_text = "\n\n---\n\n".join(prose_sections)

        return jsonify({
            "prose": prose_text,
            "content": content_scenes,
        })
    except Exception as e:
        logger.exception("ai/generate-book failed")
        return jsonify({"error": "The AI request failed. Try again later."}), 500


# ---------------------------------------------------------------------------
@app.route("/books", methods=["GET"])
@login_required
def list_books():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT b.id, b.story_id, b.title, b.created_at, b.updated_at,
                      s.genre, s.cover_image
               FROM books b LEFT JOIN stories s ON b.story_id = s.id
               WHERE b.user_id = ?
               ORDER BY b.updated_at DESC""",
            (g.user_id,),
        ).fetchall()
    finally:
        conn.close()
    return jsonify([{
        "id": r["id"],
        "story_id": r["story_id"],
        "title": r["title"],
        "genre": r["genre"] or "",
        "cover_image": r["cover_image"] or "",
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    } for r in rows])


@app.route("/books", methods=["POST"])
@login_required
def save_book():
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    title = (data.get("title") or "").strip()
    prose = (data.get("prose") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not prose:
        return jsonify({"error": "prose is required"}), 400

    content = data.get("content", [])
    content_json = json.dumps(content) if isinstance(content, list) else "[]"

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO books (story_id, user_id, title, prose, content) VALUES (?, ?, ?, ?, ?)",
            (story_id, g.user_id, title, prose, content_json),
        )
        conn.commit()
        book_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"id": book_id, "title": title}), 201


@app.route("/books/<int:book_id>", methods=["GET"])
@login_required
def get_book(book_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT b.*, s.genre, s.cover_image
               FROM books b LEFT JOIN stories s ON b.story_id = s.id
               WHERE b.id = ? AND b.user_id = ?""",
            (book_id, g.user_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    try:
        content = json.loads(row["content"] or "[]")
    except (json.JSONDecodeError, TypeError):
        content = []
    return jsonify({
        "id": row["id"],
        "story_id": row["story_id"],
        "title": row["title"],
        "prose": row["prose"],
        "content": content,
        "genre": row["genre"] or "",
        "cover_image": row["cover_image"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    })


@app.route("/books/<int:book_id>", methods=["PUT"])
@login_required
def update_book(book_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM books WHERE id = ? AND user_id = ?", (book_id, g.user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        data = request.get_json(silent=True) or {}
        update_content = data.get("content")
        content_json = json.dumps(update_content) if update_content is not None else (row["content"] or "[]")
        conn.execute(
            "UPDATE books SET title = ?, prose = ?, content = ?, updated_at = datetime('now') WHERE id = ?",
            (data.get("title", row["title"]), data.get("prose", row["prose"]), content_json, book_id),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/books/<int:book_id>", methods=["DELETE"])
@login_required
def delete_book(book_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM books WHERE id = ? AND user_id = ?", (book_id, g.user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/ai/analyze-evaluation", methods=["POST"])
@login_required
def ai_analyze_evaluation():
    """Take evaluation scores and generate actionable coding recommendations."""
    from config import AZURE_ENDPOINT, AZURE_API_KEY

    if not AZURE_ENDPOINT or not AZURE_API_KEY or AZURE_ENDPOINT.startswith("https://your-"):
        return jsonify({"error": "Azure not configured"}), 503

    data = request.get_json(silent=True) or {}
    evaluation = data.get("evaluation", {})
    game_title = data.get("game_title", "")
    subgraph = data.get("subgraph", "")
    turns = data.get("turns", [])

    if not evaluation:
        return jsonify({"error": "No evaluation data"}), 400

    # Build context about the engine architecture
    engine_context = """
The RPG Engine architecture:
- Narrator node: LLM generates scene descriptions. Has a "narrator_prompt" in the story that controls tone and style.
- NPC node: each character has a "prompt" (personality instructions) and responds after the narrator.
- Mood node: evaluates mood axes (UP/DOWN/SAME) before NPC speaks. Characters have named axes like "trust", "fear".
- Condense node: LLM summarizes the story so far into memory_summary (~100 words).
- Memory node: records each turn in history list.
- Narrator coda: LLM writes a closing beat after NPCs speak, prompts the player.
- Player action generator: LLM generates what the player says next (for automated testing).
- Subgraphs wire these nodes together in different orders.

Configurable per-story:
- narrator_prompt: system instructions for the narrator LLM
- character prompts: personality instructions per NPC
- mood axes: named emotional scales per character
- subgraph_name: which graph pipeline to use
- player_name, player_background: who the player is
"""

    # Build the turn transcript summary
    turn_summary = ""
    for t in turns[:10]:
        turn_summary += f"Turn {t.get('turn')}: Player: {t.get('message', '')[:60]} → Response: {t.get('response', '')[:100]}...\n"

    prompt = f"""You are a senior game engineer analyzing playtest results for a text RPG engine. Based on the evaluation scores and the engine architecture, generate specific, actionable coding recommendations.

Game: {game_title}
Subgraph: {subgraph}

Evaluation summary:
{json.dumps(evaluation, indent=2)[:2000]}

Turn transcript (abbreviated):
{turn_summary}

{engine_context}

Generate a JSON response with specific recommendations. Each recommendation should say exactly WHAT to change, WHERE in the code/config, and WHY based on the evaluation data.

{{
  "analysis": {{
    "primary_issue": "<the single biggest problem identified>",
    "score_trend": "<are scores improving, degrading, or flat across turns?>",
    "worst_turn": <turn number with lowest average score>,
    "best_turn": <turn number with highest average score>
  }},
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "category": "narrator_prompt|character_prompt|mood_config|subgraph|condense|player_generator|new_node|story_content",
      "title": "<short title>",
      "description": "<what to change and why>",
      "implementation": "<specific text to add/change, or code approach>",
      "expected_impact": "<what improvement this should cause>"
    }}
  ],
  "prompt_suggestions": {{
    "narrator_prompt_additions": "<specific text to append to narrator_prompt to fix issues>",
    "player_generator_improvements": "<how to improve auto-generated player actions>"
  }}
}}

Respond with ONLY valid JSON, no markdown fences."""

    try:
        from llm.azure_provider import AzureProvider
        azure = AzureProvider("analyst")
        raw = azure.invoke(prompt)
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        analysis = json.loads(text)
        return jsonify({"analysis": analysis})
    except json.JSONDecodeError:
        return jsonify({"analysis": {"raw_response": raw[:2000], "parse_error": True}})
    except Exception as e:
        logger.exception("Azure analysis failed")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Playback scripts
# ---------------------------------------------------------------------------

PLAYBACK_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "web", "static", "playback_scripts")


@app.route("/ai/evaluate-playback", methods=["POST"])
@login_required
def ai_evaluate_playback():
    """Send playback results to Azure for evaluation."""
    from config import AZURE_ENDPOINT, AZURE_API_KEY, AZURE_DEPLOYMENT, AZURE_API_VERSION

    if not AZURE_ENDPOINT or not AZURE_API_KEY or AZURE_ENDPOINT.startswith("https://your-"):
        return jsonify({"error": "Azure not configured. Add AZURE_ENDPOINT and AZURE_API_KEY to .env"}), 503

    data = request.get_json(silent=True) or {}
    game_title = data.get("game_title", "")
    turns = data.get("turns", [])
    opening = data.get("opening", "")

    if not turns:
        return jsonify({"error": "No turns to evaluate"}), 400

    # Build the transcript for the judge
    transcript_parts = []
    if opening:
        transcript_parts.append(f"[Opening]: {opening[:300]}")
    for t in turns:
        transcript_parts.append(f"[Player Turn {t.get('turn', '?')}]: {t.get('message', '')}")
        resp = t.get("response", "")
        transcript_parts.append(f"[Response]: {resp[:500]}")
    transcript = "\n\n".join(transcript_parts)

    prompt = f"""You are an expert evaluator of interactive fiction and text adventure games. Analyze this play session and provide detailed feedback.

Game: {game_title}
Turns: {len(turns)}

Transcript:
{transcript}

Evaluate the following and provide a JSON response:

{{
  "overall_score": <1-10>,
  "summary": "<2-3 sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>"],
  "turn_scores": [
    {{
      "turn": 1,
      "relevance": <1-10 did the response address what the player said>,
      "prose_quality": <1-10 writing quality, atmosphere, detail>,
      "engagement": <1-10 does this make you want to keep playing>,
      "note": "<brief note about this turn>"
    }}
  ],
  "consistency": "<any contradictions between turns?>",
  "pacing": "<is the story moving at a good pace?>",
  "suggestions": ["<improvement suggestion 1>", "<suggestion 2>"]
}}

Respond with ONLY valid JSON, no markdown fences."""

    try:
        from llm.azure_provider import AzureProvider
        azure = AzureProvider("judge")
        raw = azure.invoke(prompt)
        text = raw.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        evaluation = json.loads(text)
        return jsonify({"evaluation": evaluation})
    except json.JSONDecodeError as e:
        logger.warning("Azure evaluation returned invalid JSON: %s", str(e))
        return jsonify({"evaluation": {"summary": raw[:1000], "parse_error": True}})
    except Exception as e:
        logger.exception("Azure evaluation failed")
        return jsonify({"error": f"Azure evaluation failed: {str(e)}"}), 500


@app.route("/ai/generate-player-action", methods=["POST"])
@login_required
def ai_generate_player_action():
    """Generate what the player would naturally do next."""
    data = request.get_json(silent=True) or {}
    scene = (data.get("scene") or "").strip()
    player_name = (data.get("player_name") or "the player").strip()
    player_background = (data.get("player_background") or "").strip()
    game_title = (data.get("game_title") or "").strip()
    previous_actions = data.get("previous_actions", [])
    turn_number = data.get("turn_number", 1)
    total_turns = data.get("total_turns", 5)

    if not scene:
        return jsonify({"error": "scene is required"}), 400

    prev_block = ""
    if previous_actions:
        prev_lines = [f"Turn {i+1}: {a}" for i, a in enumerate(previous_actions[-5:])]
        prev_block = f"\nYour previous actions (DO NOT repeat any of these):\n" + "\n".join(prev_lines)

    bg_block = f"\nYour character: {player_background}" if player_background else ""
    title_block = f"\nStory: {game_title}" if game_title else ""

    # Force variety based on turn number
    variety_hints = [
        "Take a bold physical action.",
        "Say something provocative or unexpected to someone.",
        "Investigate something specific you noticed.",
        "Make a decision that changes the situation.",
        "Confront someone or challenge something directly.",
        "Try to leave, move, or change location.",
        "Reveal something personal or take an emotional risk.",
        "Do something sneaky, subtle, or clever.",
        "React physically — grab, push, run, hide.",
        "Ask a pointed question that demands an answer.",
    ]
    turn_idx = max(0, (turn_number - 1)) % len(variety_hints)
    variety_hint = variety_hints[turn_idx]

    prompt = f"""What does {player_name} do next? ONE short sentence starting with "I".{title_block}{bg_block}

Hint: {variety_hint}

Scene: {scene[:400]}
{prev_block}

{player_name}'s action (one sentence, must be DIFFERENT from all previous actions):"""

    try:
        llm = get_llm(get_model_for_role("tools"))
        raw = llm.invoke(prompt)
        text = llm_result_to_text(raw).strip()
        # Take first sentence only — split on period, question mark, or exclamation
        for end in ['. ', '? ', '! ']:
            idx = text.find(end)
            if idx > 0:
                text = text[:idx + 1]
                break
        # Take first line only
        text = text.split("\n")[0].strip()
        # Strip quotes
        if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
            text = text[1:-1]
        # Strip common prefixes
        for prefix in [f"{player_name}:", f"{player_name}'s action:", "Action:", "Next:", "I would "]:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
        # Ensure starts with I
        if text and not text.startswith("I "):
            text = "I " + text[0].lower() + text[1:] if text else "I act."
        # Hard cap at 120 chars
        if len(text) > 120:
            text = text[:117].rsplit(" ", 1)[0] + "..."
        logger.info("generate-player-action: turn=%s, action=%r", data.get("turn_number"), text[:100])
        return jsonify({"action": text})
    except Exception as e:
        logger.exception("generate-player-action failed")
        return jsonify({"error": "Failed to generate action"}), 500


@app.route("/playback-scripts", methods=["GET"])
@login_required
def list_playback_scripts():
    """List saved playback scripts."""
    os.makedirs(PLAYBACK_SCRIPTS_DIR, exist_ok=True)
    scripts = []
    for f in sorted(os.listdir(PLAYBACK_SCRIPTS_DIR)):
        if not f.endswith(".json"):
            continue
        path = os.path.join(PLAYBACK_SCRIPTS_DIR, f)
        try:
            with open(path) as fh:
                data = json.load(fh)
            scripts.append({
                "filename": f,
                "name": data.get("name", f),
                "story_title": data.get("story_title", ""),
                "turns": len(data.get("messages", [])),
                "created": data.get("created", ""),
            })
        except Exception:
            continue
    return jsonify(scripts)


@app.route("/playback-scripts", methods=["POST"])
@login_required
def save_playback_script():
    """Save a playback script."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "messages is required"}), 400

    os.makedirs(PLAYBACK_SCRIPTS_DIR, exist_ok=True)
    from datetime import datetime, timezone
    script = {
        "name": name,
        "story_id": data.get("story_id"),
        "story_title": data.get("story_title", ""),
        "messages": messages,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    filename = name.lower().replace(" ", "_").replace("/", "_")[:50] + ".json"
    path = os.path.join(PLAYBACK_SCRIPTS_DIR, filename)
    with open(path, "w") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True, "filename": filename}), 201


@app.route("/playback-scripts/<filename>", methods=["GET"])
@login_required
def get_playback_script(filename: str):
    """Load a playback script."""
    path = os.path.join(PLAYBACK_SCRIPTS_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    with open(path) as f:
        return jsonify(json.load(f))


COVER_STYLES = {
    "cinematic": "cinematic film still, dramatic lighting, shallow depth of field, moody atmosphere",
    "anime": "anime key visual, vibrant colors, cel-shaded, detailed background, studio quality",
    "painterly": "digital painting, oil paint texture, rich colors, impressionistic, concept art",
    "noir": "film noir, high contrast black and white with selective color, dramatic shadows, moody",
    "watercolor": "watercolor illustration, soft edges, delicate colors, artistic, storybook quality",
    "comic": "graphic novel panel, bold lines, dynamic composition, ink and color, sequential art style",
    "photorealistic": "photorealistic, professional photography, natural lighting, high detail, 8k",
    "retro": "retro 80s aesthetic, synthwave colors, neon glow, vintage poster style",
    "fantasy-art": "fantasy illustration, epic composition, magical lighting, detailed, artstation quality",
    "minimalist": "minimalist design, simple shapes, limited palette, clean composition, modern art",
}


@app.route("/ai/cover-styles", methods=["GET"])
def list_cover_styles():
    """Return available cover image styles."""
    return jsonify({
        "styles": [
            {"key": k, "description": v}
            for k, v in COVER_STYLES.items()
        ]
    })


# Cover prompt builder
# ---------------------------------------------------------------------------

@app.route("/ai/build-cover-prompt", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_build_cover_prompt():
    """Use LLM to build a detailed image prompt from story data + style."""
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400

    style_key = (data.get("style") or "cinematic").strip()
    style_suffix = COVER_STYLES.get(style_key, COVER_STYLES["cinematic"])

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Story not found"}), 404

    title = row["title"] or "Untitled"
    genre_val = row["genre"] or "fantasy"
    description = row["description"] or ""
    opening = (row["opening"] or "")[:300]
    tone = row["tone"] or ""
    characters_raw = row["characters"] or "{}"
    try:
        chars = json.loads(characters_raw)
        char_names = list(chars.keys())
    except (json.JSONDecodeError, TypeError):
        char_names = []

    char_line = f"Characters: {', '.join(c.replace('_', ' ').title() for c in char_names)}" if char_names else ""

    from model_resolver import get_model_for_role
    model = get_model_for_role("image_prompt")
    try:
        llm = get_llm(model)
    except Exception as e:
        return jsonify({"error": f"LLM unavailable: {e}"}), 503

    llm_prompt = f"""Write a detailed image generation prompt for a story cover image.

Story title: {title}
Genre: {genre_val}
Tone: {tone}
Description: {description}
Opening: {opening}
{char_line}

Visual style: {style_suffix}

Write a single paragraph image prompt (50-80 words) that captures the story's mood and setting.
Rules:
- Describe a visual scene, not a plot summary
- Include composition details (foreground, background, lighting, color palette)
- Do NOT include character names — describe figures by appearance
- End with the style: {style_suffix}
- Return ONLY the prompt text, no labels or commentary

Prompt:"""

    try:
        raw = llm_result_to_text(llm.invoke(llm_prompt)).strip()
        # Clean up
        for prefix in ["Prompt:", "prompt:", "Image prompt:", "Cover prompt:"]:
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].strip()
        # Ensure style suffix is appended if model didn't include it
        if style_key not in raw.lower() and style_suffix.split(",")[0].lower() not in raw.lower():
            raw = f"{raw}, {style_suffix}"
        return jsonify({"prompt": raw, "style": style_key})
    except Exception as e:
        return jsonify({"error": f"Prompt generation failed: {e}"}), 500


# Cover image generation
# ---------------------------------------------------------------------------

@app.route("/ai/generate-cover", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_cover():
    import comfyui_client

    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400

    if not comfyui_client.is_available():
        return jsonify({"error": "Image generation is not available (ComfyUI not running)"}), 503

    conn = get_db()
    image_id: int | None = None
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Story not found"}), 404

        # Use custom prompt if provided, otherwise build from story data
        title = row["title"] or "Untitled"
        genre = row["genre"] or "fantasy"
        description = row["description"] or ""
        opening = (row["opening"] or "")[:200]
        nsfw_rating = row["nsfw_rating"] or "none"

        custom_prompt = (data.get("prompt") or "").strip()
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = f"{genre} scene, {title}, {description}. {opening}. RPG concept art, atmospheric, cinematic lighting, detailed, moody"
        ckpt_key = comfyui_client._pick_checkpoint(nsfw_rating)
        ckpt_name = comfyui_client.CHECKPOINTS[ckpt_key]["ckpt_name"]
        image_id = create_image_record(
            conn,
            kind="cover",
            scope="story",
            owner_type="story",
            owner_id=story_id,
            owner_key=None,
            prompt=prompt,
            workflow_name="PonyForRPG" if ckpt_key == "pony" else "FluxForRPG",
            model_name=ckpt_name,
            width=800,
            height=500,
        )
        conn.commit()

        # Generate via ComfyUI
        prefix = f"cover_{story_id}"
        comfyui_filename = comfyui_client.generate_image(prompt, width=800, height=500, prefix=prefix, nsfw_rating=nsfw_rating)
        if not comfyui_filename:
            if image_id is not None:
                mark_image_failed(conn, image_id, "Image generation failed")
                conn.commit()
            return jsonify({"error": "Image generation failed"}), 500

        # Download to static/images/covers/
        covers_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "covers")
        os.makedirs(covers_dir, exist_ok=True)
        local_filename = f"story_{story_id}.png"
        local_path = os.path.join(covers_dir, local_filename)

        if not comfyui_client.download_image(comfyui_filename, local_path):
            if image_id is not None:
                mark_image_failed(conn, image_id, "Failed to save image")
                conn.commit()
            return jsonify({"error": "Failed to save image"}), 500

        if image_id is not None:
            mark_image_ready(conn, image_id, local_path)
        # Update DB
        conn.execute(
            "UPDATE stories SET cover_image = ?, cover_image_id = ?, updated_at = datetime('now') WHERE id = ?",
            (local_filename, image_id, story_id),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "image_id": image_id,
        "cover_image": local_filename,
        "url": f"/images/covers/{local_filename}",
    })


SCENE_STYLES = {
    "cinematic": "cinematic film still, dramatic lighting, wide angle, moody atmosphere",
    "anime": "anime background art, vibrant colors, detailed scenery, studio ghibli inspired",
    "painterly": "digital painting, oil paint texture, rich colors, concept art",
    "noir": "film noir, high contrast shadows, rain-slicked streets, monochrome with accent color",
    "watercolor": "watercolor illustration, soft edges, delicate washes, storybook quality",
    "photorealistic": "photorealistic, natural lighting, high detail, professional photography",
}

PORTRAIT_STYLES = {
    "anime": "anime character portrait, cel-shaded, expressive eyes, clean lines, vibrant",
    "realistic": "photorealistic portrait, studio lighting, high detail, sharp focus",
    "painterly": "digital painting portrait, oil paint texture, dramatic lighting, concept art",
    "comic": "graphic novel character, bold lines, dynamic shading, ink and color",
    "watercolor": "watercolor portrait, soft edges, delicate features, artistic",
    "fantasy-art": "fantasy character portrait, epic lighting, detailed armor/clothing, artstation",
}


@app.route("/ai/build-scene-prompt", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_build_scene_prompt():
    """Use LLM to build a scene image prompt from the current play context + style."""
    data = request.get_json(silent=True) or {}
    scene_text = (data.get("scene_text") or "").strip()
    if not scene_text:
        return jsonify({"error": "scene_text is required"}), 400

    style_key = (data.get("style") or "cinematic").strip()
    style_suffix = SCENE_STYLES.get(style_key, SCENE_STYLES["cinematic"])

    # Try to get story context for genre/tone and character gender
    story_context = ""
    gender_hint = ""
    story_id = data.get("story_id")
    if story_id:
        try:
            conn = get_db()
            row = conn.execute("SELECT genre, tone, description, characters, player_name FROM stories WHERE id = ?", (int(story_id),)).fetchone()
            conn.close()
            if row:
                parts = []
                if row["genre"]:
                    parts.append(f"Genre: {row['genre']}")
                if row["tone"]:
                    parts.append(f"Tone: {row['tone']}")
                if row["description"]:
                    parts.append(f"Story: {row['description'][:150]}")
                if parts:
                    story_context = "\n".join(parts) + "\n"

                # Detect character genders from prompts
                male_keywords = {"man", "male", "he", "his", "him", "guy", "boy", "masculine", "gay man"}
                female_keywords = {"woman", "female", "she", "her", "girl", "feminine"}
                male_count = 0
                female_count = 0
                try:
                    chars = json.loads(row["characters"] or "{}")
                    for ck, cv in chars.items():
                        if isinstance(cv, dict):
                            prompt_lower = (cv.get("prompt") or "").lower()
                            if any(kw in prompt_lower for kw in male_keywords):
                                male_count += 1
                            if any(kw in prompt_lower for kw in female_keywords):
                                female_count += 1
                except Exception:
                    pass
                # Player is typically male in these stories
                player_name = row["player_name"] or ""
                if player_name:
                    male_count += 1  # assume player is male unless specified

                if male_count > 0 and female_count == 0:
                    gender_hint = "\nIMPORTANT: All characters in this story are MALE. Describe men only — no women."
                elif male_count > female_count:
                    gender_hint = f"\nNote: This story has {male_count} male and {female_count} female characters. Describe accordingly."
        except Exception:
            pass

    from model_resolver import get_model_for_role
    model = get_model_for_role("image_prompt")
    try:
        llm = get_llm(model)
    except Exception as e:
        return jsonify({"error": f"LLM unavailable: {e}"}), 503

    llm_prompt = f"""Extract visual elements from this scene. ONLY use details explicitly mentioned in the text below — do NOT invent or assume anything.
{gender_hint}
{story_context}
TEXT:
{scene_text[:800]}

Reply with EXACTLY these 6 lines. Each line: 3-8 words, comma-separated tags ONLY from the text above.

SETTING: (exact location and time mentioned)
PEOPLE: (appearance details mentioned — hair, build, clothing)
POSE: (exact body positions and actions described)
MOOD: (emotional words used in the text)
DETAILS: (specific objects mentioned — cards, cups, games, furniture)
LIGHTING: (lighting described or implied by time of day)

CRITICAL: Only extract what the text says. Do not add laptops if text says cards. Do not add afternoon if text says evening."""

    try:
        raw_response = llm_result_to_text(llm.invoke(llm_prompt)).strip()

        # Parse the structured response into tags
        tags = {}
        for line in raw_response.split("\n"):
            line = line.strip()
            for key in ["SETTING:", "PEOPLE:", "POSE:", "MOOD:", "DETAILS:", "LIGHTING:"]:
                if line.upper().startswith(key):
                    tags[key.rstrip(":")] = line[len(key):].strip().strip('"')
                    break

        # Post-process: strip filler words, character names, and shorten to real tags
        import re

        # Collect character names to strip
        char_names_to_strip = set()
        for ck in (data.get("characters") or {}).keys() if isinstance(data.get("characters"), dict) else []:
            char_names_to_strip.add(ck.replace("_", " ").title())
            char_names_to_strip.add(ck)
        # Also try to get from story
        if story_id:
            try:
                conn2 = get_db()
                srow = conn2.execute("SELECT characters FROM stories WHERE id = ?", (int(story_id),)).fetchone()
                conn2.close()
                if srow and srow["characters"]:
                    for ck in json.loads(srow["characters"] or "{}").keys():
                        char_names_to_strip.add(ck.replace("_", " ").title())
                        char_names_to_strip.add(ck)
            except Exception:
                pass
        # Also strip player name
        char_names_to_strip.update(["John", "Player", "you", "You"])

        name_pattern = "|".join(re.escape(n) for n in sorted(char_names_to_strip, key=len, reverse=True))

        filler = re.compile(
            r'\b(with|the|and|from|through|across|beside|that|what|might|happen|next|'
            r'his|her|their|its|this|of|in|on|at|to|a|an|is|are|was|were|'
            r'streaming|casting|discarded|faint|gazing|focused|sits?|stands?|leans?|over)\b',
            re.IGNORECASE,
        )

        def _clean_tags(text: str) -> str:
            # Split on commas and semicolons
            raw_tags = re.split(r'[;,]', text)
            cleaned = []
            for tag in raw_tags:
                tag = tag.strip()
                if not tag:
                    continue
                # Remove character names
                if name_pattern:
                    tag = re.sub(name_pattern, '', tag).strip()
                # Remove filler words
                tag = filler.sub('', tag).strip()
                # Collapse whitespace
                tag = re.sub(r'\s+', ' ', tag).strip()
                # Skip if too short after cleaning
                if len(tag) < 3:
                    continue
                # Skip tags that are just pronouns or articles left over
                if tag.lower() in ('him', 'them', 'he', 'she', 'they', 'it', 'man', 'men'):
                    continue
                # Truncate long tags
                words = tag.split()
                if len(words) > 5:
                    tag = ' '.join(words[:5])
                cleaned.append(tag)
            return ', '.join(cleaned)

        # Assemble into a clean image prompt
        parts = []

        # Add gender tags at the front if all-male story
        if gender_hint and "MALE" in gender_hint.upper():
            parts.append("two men, male characters, no women")

        for key in ["SETTING", "PEOPLE", "POSE", "MOOD", "DETAILS", "LIGHTING"]:
            if tags.get(key):
                cleaned = _clean_tags(tags[key])
                # Reinforce male if needed
                if key == "PEOPLE" and gender_hint and "MALE" in gender_hint.upper():
                    # Make sure "man" or "male" appears
                    if "man" not in cleaned.lower() and "male" not in cleaned.lower():
                        cleaned = "male, " + cleaned
                parts.append(cleaned)
        parts.append(style_suffix)

        assembled = ", ".join(p for p in parts if p)

        return jsonify({
            "prompt": assembled,
            "tags": tags,
            "style": style_key,
        })
    except Exception as e:
        return jsonify({"error": f"Prompt generation failed: {e}"}), 500


@app.route("/ai/build-portrait-prompt", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_build_portrait_prompt():
    """Use LLM to build a portrait prompt from character data + style."""
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    character_key = (data.get("character_key") or "").strip()
    if not character_key:
        return jsonify({"error": "character_key is required"}), 400

    style_key = (data.get("style") or "anime").strip()
    style_suffix = PORTRAIT_STYLES.get(style_key, PORTRAIT_STYLES["anime"])

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Story not found"}), 404

    try:
        chars = json.loads(row["characters"] or "{}")
    except (json.JSONDecodeError, TypeError):
        chars = {}
    char_data = chars.get(character_key)
    if not char_data or not isinstance(char_data, dict):
        return jsonify({"error": f"Character '{character_key}' not found"}), 404

    char_prompt = char_data.get("prompt", "")
    genre_val = row["genre"] or "fantasy"

    from model_resolver import get_model_for_role
    model = get_model_for_role("image_prompt")
    try:
        llm = get_llm(model)
    except Exception as e:
        return jsonify({"error": f"LLM unavailable: {e}"}), 503

    label = character_key.replace("_", " ").title()
    llm_prompt = f"""Write a detailed image generation prompt for a character portrait.

Character name: {label}
Character description: {char_prompt}
Story genre: {genre_val}

Visual style: {style_suffix}

Write a single paragraph image prompt (40-60 words) describing this character's appearance.
Rules:
- Describe physical appearance: face, hair, build, clothing, expression
- Include lighting and background appropriate to the genre
- Do NOT use the character's name — describe them visually
- End with the style: {style_suffix}
- Return ONLY the prompt text

Prompt:"""

    try:
        raw = llm_result_to_text(llm.invoke(llm_prompt)).strip()
        for prefix in ["Prompt:", "prompt:", "Image prompt:", "Portrait prompt:"]:
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].strip()
        if style_suffix.split(",")[0].lower() not in raw.lower():
            raw = f"{raw}, {style_suffix}"
        return jsonify({"prompt": raw, "style": style_key})
    except Exception as e:
        return jsonify({"error": f"Prompt generation failed: {e}"}), 500


@app.route("/ai/scene-styles", methods=["GET"])
def list_scene_styles():
    return jsonify({"styles": [{"key": k, "description": v} for k, v in SCENE_STYLES.items()]})


@app.route("/ai/portrait-styles", methods=["GET"])
def list_portrait_styles():
    return jsonify({"styles": [{"key": k, "description": v} for k, v in PORTRAIT_STYLES.items()]})


@app.route("/ai/list-scene-images", methods=["GET"])
@login_required
def list_scene_image_files():
    """List existing scene image files for this story."""
    story_id = request.args.get("story_id", "")
    scenes_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "scenes")
    portraits_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "portraits")

    images = []
    # Scene images
    if os.path.isdir(scenes_dir):
        for f in sorted(os.listdir(scenes_dir)):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                url = f"/images/scenes/{f}"
                # Optionally filter by story_id
                if story_id and f"story_{story_id}" not in f and f"scene_{story_id}" not in f:
                    continue
                images.append({"url": url, "filename": f, "type": "scene"})
    # Portrait images
    if os.path.isdir(portraits_dir):
        for f in sorted(os.listdir(portraits_dir)):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                url = f"/images/portraits/{f}"
                if story_id and f"story_{story_id}" not in f:
                    continue
                images.append({"url": url, "filename": f, "type": "portrait"})
    return jsonify({"images": images})


@app.route("/ai/build-gallery-item", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_build_gallery_item():
    """Use LLM to build trigger, caption, tags, and image prompt for a gallery scene."""
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400

    scene_id = (data.get("scene_id") or "").strip()
    tags_input = data.get("tags") or []
    style_key = (data.get("style") or "cinematic").strip()
    style_suffix = SCENE_STYLES.get(style_key, SCENE_STYLES.get("cinematic", "cinematic"))

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Story not found"}), 404

    title = row["title"] or "Untitled"
    genre_val = row["genre"] or "fantasy"
    tone = row["tone"] or ""
    description = row["description"] or ""
    opening = (row["opening"] or "")[:200]

    from model_resolver import get_model_for_role
    model = get_model_for_role("image_prompt")
    try:
        llm = get_llm(model)
    except Exception as e:
        return jsonify({"error": f"LLM unavailable: {e}"}), 503

    tags_str = ", ".join(tags_input) if tags_input else scene_id.replace("_", ", ")

    llm_prompt = f"""You are helping create a scene image for an interactive story.

Story: {title}
Genre: {genre_val}
Tone: {tone}
Description: {description}
Opening: {opening}

Scene ID: {scene_id}
Initial tags: {tags_str}

Generate all of the following for this scene. Return EXACTLY this format:

TAGS: comma-separated keywords for matching (5-8 tags, include location, time of day, mood, objects)
TRIGGER: a concrete, literal phrase (2-4 words) describing the situation, like "cooking breakfast" or "first kiss" or "rooftop at night" — NOT literary or poetic, just plain keywords the narrator would use
CAPTION: one sentence describing the scene for display under the image
PROMPT: a detailed image generation prompt (40-60 words) describing the visual scene, ending with: {style_suffix}

Return ONLY the four lines above, no other text."""

    try:
        raw = llm_result_to_text(llm.invoke(llm_prompt)).strip()

        result = {"scene_id": scene_id}
        for line in raw.split("\n"):
            line = line.strip()
            if line.upper().startswith("TAGS:"):
                result["tags"] = [t.strip() for t in line[5:].split(",") if t.strip()]
            elif line.upper().startswith("TRIGGER:"):
                result["trigger"] = line[8:].strip().strip('"')
            elif line.upper().startswith("CAPTION:"):
                result["caption"] = line[8:].strip().strip('"')
            elif line.upper().startswith("PROMPT:"):
                prompt_text = line[7:].strip().strip('"')
                if style_suffix.split(",")[0].lower() not in prompt_text.lower():
                    prompt_text = f"{prompt_text}, {style_suffix}"
                result["prompt"] = prompt_text

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Generation failed: {e}"}), 500


@app.route("/ai/generate-scene", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_scene():
    import comfyui_client

    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    scene_text = (data.get("scene_text") or "").strip()
    if not scene_text:
        return jsonify({"error": "scene_text is required"}), 400

    if not comfyui_client.is_available():
        return jsonify({"error": "Image generation not available (ComfyUI not running)"}), 503

    # Use custom prompt if provided, otherwise build from scene text
    custom_prompt = (data.get("prompt") or "").strip()
    if custom_prompt:
        prompt = custom_prompt
    else:
        scene_excerpt = scene_text[:500]
        prompt = f"{scene_excerpt}, RPG scene illustration, atmospheric, cinematic lighting, detailed environment, moody"
    nsfw_rating = (data.get("nsfw_rating") or "none").strip()
    image_id: int | None = None
    conn = get_db()
    try:
        ckpt_key = comfyui_client._pick_checkpoint(nsfw_rating)
        ckpt_name = comfyui_client.CHECKPOINTS[ckpt_key]["ckpt_name"]
        image_id = create_image_record(
            conn,
            kind="scene",
            scope="turn",
            owner_type="story",
            owner_id=story_id,
            owner_key=None,
            prompt=prompt,
            workflow_name="PonyForRPG" if ckpt_key == "pony" else "FluxForRPG",
            model_name=ckpt_name,
            width=1024,
            height=576,
        )
        conn.commit()
    finally:
        conn.close()

    scenes_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "scenes")
    os.makedirs(scenes_dir, exist_ok=True)

    import time as _time
    timestamp = int(_time.time())
    prefix = f"scene_{story_id}_{timestamp}"
    local_filename = f"{prefix}.png"

    comfyui_filename = comfyui_client.generate_image(prompt, width=1024, height=576, prefix=prefix, nsfw_rating=nsfw_rating)
    if not comfyui_filename:
        if image_id is not None:
            conn = get_db()
            try:
                mark_image_failed(conn, image_id, "Scene generation failed")
                conn.commit()
            finally:
                conn.close()
        return jsonify({"error": "Scene generation failed"}), 500

    local_path = os.path.join(scenes_dir, local_filename)
    if not comfyui_client.download_image(comfyui_filename, local_path):
        if image_id is not None:
            conn = get_db()
            try:
                mark_image_failed(conn, image_id, "Failed to save scene image")
                conn.commit()
            finally:
                conn.close()
        return jsonify({"error": "Failed to save scene image"}), 500
    if image_id is not None:
        conn = get_db()
        try:
            mark_image_ready(conn, image_id, local_path)
            conn.commit()
        finally:
            conn.close()

    # Record the scene image in the active game's history
    session_key = _play_session_key(story_id, g.user_id)
    state = game_session_cache.get(session_key)
    if state is not None:
        history = list(state.get("history") or [])
        history.append(f"[SCENE_IMAGE:/images/scenes/{local_filename}]")
        state["history"] = history
        game_session_cache.set(session_key, state)
        conn = get_db()
        try:
            _upsert_save(conn, story_id, g.user_id, 0, state)
            conn.commit()
        finally:
            conn.close()

    return jsonify({
        "ok": True,
        "image_id": image_id,
        "url": f"/images/scenes/{local_filename}",
    })


@app.route("/ai/generate-story-image", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_story_image():
    import comfyui_client

    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400

    prompt_input = (data.get("prompt") or "").strip()
    if not comfyui_client.is_available():
        return jsonify({"error": "Image generation not available (ComfyUI not running)"}), 503

    conn = get_db()
    image_id: int | None = None
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?",
            (story_id, g.user_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Story not found"}), 404

        title = row["title"] or "Untitled"
        genre = row["genre"] or "fantasy"
        description = row["description"] or ""
        opening = (row["opening"] or "")[:220]
        nsfw_rating = row["nsfw_rating"] or "none"
        prompt = prompt_input
        if not prompt:
            prompt = (
                f"{genre} RPG scene concept art inspired by '{title}'. "
                f"{description}. {opening}. "
                "Anime RPG style, vibrant colors, cinematic composition, detailed background"
            )

        ckpt_key = comfyui_client._pick_checkpoint(nsfw_rating)
        ckpt_name = comfyui_client.CHECKPOINTS[ckpt_key]["ckpt_name"]
        image_id = create_image_record(
            conn,
            kind="story_image",
            scope="story",
            owner_type="story",
            owner_id=story_id,
            owner_key=None,
            prompt=prompt,
            workflow_name="PonyForRPG" if ckpt_key == "pony" else "FluxForRPG",
            model_name=ckpt_name,
            width=1024,
            height=640,
        )
        conn.commit()

        out_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "story")
        os.makedirs(out_dir, exist_ok=True)

        image_suffix = image_id if image_id is not None else int(time.time())
        local_filename = f"story_{story_id}_{image_suffix}.png"
        local_path = os.path.join(out_dir, local_filename)

        comfyui_filename = comfyui_client.generate_image(
            prompt,
            width=1024,
            height=640,
            prefix=f"storyimg_{story_id}",
            nsfw_rating=nsfw_rating,
        )
        if not comfyui_filename:
            if image_id is not None:
                mark_image_failed(conn, image_id, "Story image generation failed")
                conn.commit()
            return jsonify({"error": "Story image generation failed"}), 500

        if not comfyui_client.download_image(comfyui_filename, local_path):
            if image_id is not None:
                mark_image_failed(conn, image_id, "Failed to save story image")
                conn.commit()
            return jsonify({"error": "Failed to save story image"}), 500

        if image_id is not None:
            mark_image_ready(conn, image_id, local_path)

        try:
            existing_images = json.loads(row["story_images"] or "[]") if "story_images" in row.keys() else []
        except (json.JSONDecodeError, TypeError):
            existing_images = []
        if not isinstance(existing_images, list):
            existing_images = []

        existing_images.append({
            "filename": local_filename,
            "image_id": image_id,
            "prompt": prompt,
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        # Keep this bounded to avoid unbounded story payload growth.
        existing_images = existing_images[-20:]
        conn.execute(
            "UPDATE stories SET story_images = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing_images), story_id),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify(
        {
            "ok": True,
            "image_id": image_id,
            "filename": local_filename,
            "prompt": prompt,
            "url": f"/images/story/{local_filename}",
        }
    )


@app.route("/ai/generate-portrait", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_portrait():
    import comfyui_client

    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    character_key = (data.get("character_key") or "").strip()
    if not character_key:
        return jsonify({"error": "character_key is required"}), 400

    if not comfyui_client.is_available():
        return jsonify({"error": "Image generation not available (ComfyUI not running)"}), 503

    conn = get_db()
    image_id: int | None = None
    try:
        row = conn.execute(
            "SELECT * FROM stories WHERE id = ? AND user_id = ?", (story_id, g.user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "Story not found"}), 404

        characters = json.loads(row["characters"] or "{}")
        char_data = characters.get(character_key)
        if not char_data or not isinstance(char_data, dict):
            return jsonify({"error": f"Character '{character_key}' not found"}), 404

        # Step 1: Use LLM to convert personality prompt to visual description
        personality = char_data.get("prompt", "")
        char_label = character_key.replace("_", " ").title()
        genre = row["genre"] or "fantasy"

        style_hint = ""
        g0 = (genre or "").lower()
        if g0 in ("romance", "comedy"):
            style_hint = (
                "\nStyle hint: describe a cute anime-inspired look (slice-of-life romance VN) — "
                "soft features, expressive eyes, warm palette for hair/outfit; keep it PG.\n"
            )
        elif g0 == "drama":
            style_hint = (
                "\nStyle hint: corporate job interview — interviewers in a glass conference room, "
                "polished office clothing, professional grooming; stylized cartoon/anime portrait, not photorealistic.\n"
            )
        elif g0 == "thriller":
            style_hint = (
                "\nStyle hint: spy thriller — intelligence operatives, formal gala or field attire, "
                "sharp eyes, composed face; stylized anime portrait, not photorealistic.\n"
            )
        visual_prompt = f"""Based on this RPG character description, write a short physical appearance description (2-3 sentences) for generating a portrait image. Focus on: face, hair, clothing, expression, age, build. Do not include personality or behavior — only visual details.
{style_hint}
Character name: {char_label}
Genre: {genre}
Personality description: {personality}

Physical appearance:"""

        try:
            llm = get_llm(get_model_for_role("tools"))
            visual_desc = llm_result_to_text(llm.invoke(visual_prompt)).strip()
        except Exception as e:
            logger.error("Portrait LLM failed: %s", e)
            if (genre or "").lower() == "drama":
                visual_desc = (
                    f"{char_label}, corporate job interviewer, business professional, stylized anime cartoon look, "
                    "sharp office attire, glass conference room, evaluating candidate"
                )
            elif (genre or "").lower() == "thriller":
                visual_desc = (
                    f"{char_label}, seasoned intelligence operative, sharp observant eyes, "
                    "composed expression, formal or field-appropriate attire, anime spy thriller portrait"
                )
            else:
                visual_desc = f"{char_label}, {genre} character"

        g_low = (genre or "").lower()
        if g_low in ("romance", "comedy"):
            style_suffix = (
                "cute anime style portrait, cel-shaded, soft warm lighting, large expressive eyes, "
                "friendly approachable face, head and shoulders, cozy slice-of-life mood"
            )
        elif g_low == "drama":
            style_suffix = (
                "stylized cartoon anime portrait, business professionals conducting a job interview, "
                "modern glass-walled conference room daylight, sharp office attire, attentive interviewer "
                "expression facing the candidate, cel-shaded, clean character design, head and shoulders, "
                "subtle blurred meeting table or chairs in background"
            )
        elif g_low == "thriller":
            style_suffix = (
                "anime spy thriller portrait, seasoned intelligence operative, sharp observant eyes, "
                "controlled expression, evening formal or tactical-chic attire, cool cinematic rim light, "
                "cel-shaded, dangerous competence, head and shoulders, dark moody background"
            )
        else:
            style_suffix = (
                "portrait, head and shoulders, dark atmospheric background, RPG character art, "
                "detailed face, cinematic lighting"
            )

        # Step 2: Generate portrait via ComfyUI
        nsfw_rating = row["nsfw_rating"] or "none"
        custom_prompt = (data.get("prompt") or "").strip()
        comfyui_prompt = custom_prompt if custom_prompt else f"{visual_desc}, {style_suffix}"
        ckpt_key = comfyui_client._pick_checkpoint(nsfw_rating)
        ckpt_name = comfyui_client.CHECKPOINTS[ckpt_key]["ckpt_name"]
        image_id = create_image_record(
            conn,
            kind="portrait",
            scope="character",
            owner_type="story",
            owner_id=story_id,
            owner_key=character_key,
            prompt=comfyui_prompt,
            workflow_name="PonyForRPG" if ckpt_key == "pony" else "FluxForRPG",
            model_name=ckpt_name,
            width=512,
            height=768,
        )
        conn.commit()

        portraits_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "portraits")
        os.makedirs(portraits_dir, exist_ok=True)

        prefix = f"portrait_{story_id}_{character_key}"
        comfyui_filename = comfyui_client.generate_image(comfyui_prompt, width=512, height=768, prefix=prefix, nsfw_rating=nsfw_rating)
        if not comfyui_filename:
            if image_id is not None:
                mark_image_failed(conn, image_id, "Portrait generation failed")
                conn.commit()
            return jsonify({"error": "Portrait generation failed"}), 500

        local_filename = f"story_{story_id}_{character_key}.png"
        local_path = os.path.join(portraits_dir, local_filename)

        if not comfyui_client.download_image(comfyui_filename, local_path):
            if image_id is not None:
                mark_image_failed(conn, image_id, "Failed to save portrait")
                conn.commit()
            return jsonify({"error": "Failed to save portrait"}), 500
        if image_id is not None:
            mark_image_ready(conn, image_id, local_path)

        # Step 3: Update character data with portrait filename
        char_data["portrait"] = local_filename
        characters[character_key] = char_data
        conn.execute(
            "UPDATE stories SET characters = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(characters), story_id),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "image_id": image_id,
        "portrait": local_filename,
        "url": f"/images/portraits/{local_filename}",
        "visual_description": visual_desc,
    })


@app.route("/images/<int:image_id>", methods=["GET"])
@login_required
def get_image_record(image_id: int):
    """Return image metadata for images visible to the current user."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404

        owner_type = row["owner_type"] or ""
        owner_id = row["owner_id"]
        if owner_type == "story" and owner_id:
            s = conn.execute("SELECT user_id, is_public FROM stories WHERE id = ?", (owner_id,)).fetchone()
            if not s:
                return jsonify({"error": "Not found"}), 404
            if s["user_id"] != g.user_id and not s["is_public"]:
                return jsonify({"error": "Not found"}), 404

        data = dict(row)
        return jsonify(data)
    finally:
        conn.close()


@app.route("/health", methods=["GET"])
def health():
    """Liveness: SQLite ping. When using Ollama, best-effort check of the tags endpoint."""
    db_ok = False
    try:
        c = get_db()
        try:
            c.execute("SELECT 1")
            db_ok = True
        finally:
            c.close()
    except Exception:
        pass
    ollama_ok: bool | None = None
    if LLM_PROVIDER == "ollama":
        ollama_ok = False
        try:
            base = OLLAMA_HOST.rstrip("/")
            urllib.request.urlopen(f"{base}/api/tags", timeout=2)
            ollama_ok = True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
    body = {"ok": db_ok, "database": db_ok, "llm_provider": LLM_PROVIDER}
    if ollama_ok is not None:
        body["ollama"] = ollama_ok
    status = 200 if db_ok else 503
    return jsonify(body), status


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

init_db()
seed_builtin_subgraphs()
sync_builtin_subgraphs_from_disk()
seed_builtin_stories()
sync_builtin_story_covers_from_disk()
sync_builtin_story_characters_from_disk()

_conn = get_db()
registry.load_from_db(_conn)
_conn.close()

if __name__ == "__main__":
    print(f"RPG Engine Basic running on http://{FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
