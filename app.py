"""Flask API — auth, subgraphs, main graph templates, stories, play, AI assist."""

import json
import logging
import os
import sqlite3
import threading
import time
import traceback
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
    log_friction,
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

# Friction detection — confusion patterns
CONFUSION_PATTERNS = {"?", "what", "huh", "idk", "i don't understand"}

app = Flask(__name__)
app.secret_key = SECRET_KEY


@app.errorhandler(500)
def _handle_500(exc):
    story_id = getattr(g, "log_story_id", None) if has_request_context() else None
    user_id = getattr(g, "user_id", None) if has_request_context() else None
    session_id = f"session_{story_id}_{user_id}" if story_id and user_id else None
    log_friction(
        event_type="error_500",
        story_id=story_id,
        session_id=session_id,
        context=request.path if has_request_context() else "",
        error_detail=traceback.format_exc(),
    )
    return jsonify({"error": "Internal server error"}), 500


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
    "expression_picker": {
        "summary": "Picks character portrait expression via LLM",
        "description": "For each character with portrait variants, asks the LLM to pick the best facial expression based on the current scene. One LLM call per character.",
        "llm": True,
        "reads": ["characters", "message", "_narrator_text", "_character_responses", "_active_portraits"],
        "writes": ["_active_portraits"],
    },
    "scene_image": {
        "summary": "Scene / gallery image for sidebar",
        "description": "Selects or records scene art (gallery tags, triggers) for the play sidebar. No prose LLM.",
        "llm": False,
        "reads": ["story", "_narrator_text", "_character_responses", "memory_summary"],
        "writes": ["_scene_image", "_shown_images"],
    },
    "progression": {
        "summary": "NPC-driven stage progression — advances when player earns it",
        "description": "Tracks relationship/story stages per character. Advances only when the player's actions meet the stage criteria (LLM evaluation). Falls back to mood thresholds if no criteria defined.",
        "llm": True,
        "reads": ["characters", "turn_count", "message", "_narrator_text", "_character_responses", "_progression_state"],
        "writes": ["_progression", "_progression_state", "_narrator_progression"],
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
        try:
            d["map"] = json.loads(r["map"] or "{}") if "map" in r.keys() else {}
        except (json.JSONDecodeError, TypeError):
            d["map"] = {}
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
        map_data = data.get("map", {})
        if not isinstance(map_data, dict):
            map_data = {}
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, tone,
                  nsfw_rating, nsfw_tags, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, main_graph_template_id, characters, notes, story_images, map)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                json.dumps(map_data),
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
        update_map = data.get("map")
        if update_map is not None:
            map_json = json.dumps(update_map if isinstance(update_map, dict) else {})
        else:
            map_json = row["map"] if "map" in row.keys() else "{}"
        conn.execute(
            """UPDATE stories SET title = ?, description = ?, genre = ?, tone = ?,
                  nsfw_rating = ?, nsfw_tags = ?, opening = ?,
                  narrator_prompt = ?, narrator_model = ?, player_name = ?,
                  player_background = ?, subgraph_name = ?, main_graph_template_id = ?,
                  characters = ?, notes = ?, story_images = ?, scene_gallery = ?,
                  map = ?, updated_at = datetime('now')
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
                map_json,
                story_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/stories/<int:story_id>/character-portraits", methods=["POST"])
@login_required
def merge_story_character_portraits(story_id: int):
    """Merge portrait / face-wizard fields for one character without a full story PUT."""
    data = request.get_json(silent=True) or {}
    character_key = (data.get("character_key") or "").strip()
    if not character_key:
        return jsonify({"error": "character_key is required"}), 400

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT characters FROM stories WHERE id = ? AND user_id = ?",
            (story_id, g.user_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404

        characters = json.loads(row["characters"] or "{}")
        char_data = characters.get(character_key)
        if not isinstance(char_data, dict):
            return jsonify({"error": f"Character '{character_key}' not found"}), 404

        if "portrait" in data:
            p = data.get("portrait")
            if isinstance(p, str) and p.strip():
                char_data["portrait"] = p.strip().split("?")[0]
            elif p is None or p == "":
                char_data.pop("portrait", None)

        if "portraits" in data and isinstance(data["portraits"], dict):
            portraits = dict(char_data.get("portraits") or {})
            for k, v in data["portraits"].items():
                if not isinstance(k, str):
                    continue
                k = k.strip()
                if not k or not isinstance(v, str):
                    continue
                vs = v.strip().split("?")[0]
                if vs:
                    portraits[k] = vs
            char_data["portraits"] = portraits

        if "face_ref" in data and isinstance(data["face_ref"], dict):
            cleaned: dict[str, str] = {}
            for k, v in data["face_ref"].items():
                if isinstance(k, str) and isinstance(v, str) and k.strip():
                    cleaned[k.strip()] = v.strip()[:500]
            if cleaned:
                char_data["face_ref"] = cleaned

        if "face_extra_details" in data:
            fed = data.get("face_extra_details")
            if isinstance(fed, str) and fed.strip():
                char_data["face_extra_details"] = fed.strip()[:2000]
            elif fed is None or fed == "":
                char_data.pop("face_extra_details", None)

        if "portrait_rules" in data:
            pr = data.get("portrait_rules")
            if pr is None:
                char_data.pop("portrait_rules", None)
            elif isinstance(pr, list):
                cleaned_rules: list[dict] = []
                for item in pr[:24]:
                    if not isinstance(item, dict):
                        continue
                    use = (item.get("use") or "").strip()
                    if not use or len(use) > 64:
                        continue
                    entry: dict = {"use": use}
                    mood = item.get("mood")
                    if isinstance(mood, dict):
                        mood_out: dict[str, list[int]] = {}
                        for mk, mv in mood.items():
                            if not isinstance(mk, str) or not mk.strip():
                                continue
                            if isinstance(mv, (list, tuple)) and len(mv) >= 2:
                                try:
                                    lo = int(mv[0])
                                    hi = int(mv[1])
                                    if 1 <= lo <= 10 and 1 <= hi <= 10 and lo <= hi:
                                        mood_out[mk.strip()[:64]] = [lo, hi]
                                except (TypeError, ValueError):
                                    pass
                        if mood_out:
                            entry["mood"] = mood_out
                    tags = item.get("tags")
                    if isinstance(tags, list):
                        entry["tags"] = [str(t).strip()[:80] for t in tags if str(t).strip()][:16]
                    try:
                        p = item.get("priority")
                        if p is not None:
                            entry["priority"] = int(p)
                    except (TypeError, ValueError):
                        pass
                    if entry.get("mood") or entry.get("tags"):
                        cleaned_rules.append(entry)
                char_data["portrait_rules"] = cleaned_rules

        characters[character_key] = char_data
        conn.execute(
            """UPDATE stories SET characters = ?, updated_at = datetime('now') WHERE id = ?""",
            (json.dumps(characters), story_id),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True, "character": char_data})


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
                  subgraph_name, main_graph_template_id, characters, notes, story_images, map)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                row["map"] if "map" in row.keys() else "{}",
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
    try:
        map_data = json.loads(row["map"] or "{}") if "map" in row.keys() else {}
    except (json.JSONDecodeError, TypeError):
        map_data = {}
    if map_data:
        export["map"] = map_data
        quests_export = json.loads(row["quests"] or "{}") if "quests" in row.keys() else {}
        if quests_export:
            export["quests"] = quests_export
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
        import_map = data.get("map", {})
        if not isinstance(import_map, dict):
            import_map = {}
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, tone,
                  nsfw_rating, nsfw_tags, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, main_graph_template_id, characters, scene_gallery,
                  notes, cover_image, map, quests)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                json.dumps(import_map),
                json.dumps(data.get("quests") or {}),
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
    map_data = {}
    try:
        map_data = json.loads(row["map"] or "{}")
    except (json.JSONDecodeError, TypeError):
        pass
    quests_data = {}
    try:
        quests_data = json.loads(row["quests"] or "{}")
    except (json.JSONDecodeError, TypeError):
        pass
    characters = json.loads(row["characters"] or "{}")
    return {
        "message": "",
        "response": "",
        "history": [],
        "memory_summary": "",
        "player": {
            "name": row["player_name"] or "Adventurer",
            "background": row["player_background"] or "",
        },
        "characters": characters,
        "_all_characters": characters if map_data.get("locations") else {},
        "map": map_data,
        "quests": quests_data,
        "_location": {},
        "_location_state": {},
        "_task_narrator_hint": "",
        "_narrator_location_hint": "",
        "story": {
            "title": row["title"],
            "genre": row["genre"] or "",
            "tone": row["tone"] or "",
            "setting": row["description"] or "",
            "nsfw_rating": row["nsfw_rating"] or "none",
            "nsfw_tags": nsfw_tags,
            "scene_images": scene_gallery,
        },
        "narrator_prompt": row["narrator_prompt"] or "",
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

        try:
            _upsert_save(conn, story_id, g.user_id, 0, state)
        except sqlite3.IntegrityError:
            logger.warning("play_start: save failed for user_id=%s story_id=%s (FK constraint)", g.user_id, story_id)
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
            "location": state.get("_location", {}),
            "location_state": state.get("_location_state", {}),
            "map": state.get("map", {}),
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

        # --- Friction detection (non-blocking) ---
        _hist = state.get("history") or []
        _last_narrator = ""
        if _hist and isinstance(_hist[-1], dict):
            _last_narrator = _hist[-1].get("narrator", "")
        if _hist and isinstance(_hist[-1], dict) and _hist[-1].get("player", "").strip().lower() == message.lower():
            log_friction(event_type="repeated_input", story_id=story_id,
                         session_id=session_key, player_input=message, context=_last_narrator)
        _norm = message.lower().strip().rstrip("?!.")
        if _norm in CONFUSION_PATTERNS or message.strip() == "?":
            log_friction(event_type="player_confused", story_id=story_id,
                         session_id=session_key, player_input=message, context=_last_narrator)
        # --- End friction detection ---

        state["message"] = message

        subgraph_name = state.get("_subgraph_name", "narrator_chat_lite")
        if subgraph_name not in registry:
            return jsonify({"error": f"Subgraph not available: {subgraph_name}"}), 503

        compiled = registry.require(subgraph_name)
        _t0 = time.monotonic()
        try:
            result = compiled.invoke(state)
        except Exception as e:
            logger.exception(
                "play/chat graph invoke failed request_id=%s story_id=%s user_id=%s",
                getattr(g, "request_id", "-"),
                story_id,
                getattr(g, "user_id", "-"),
            )
            log_friction(event_type="error_500", story_id=story_id,
                         session_id=session_key, player_input=message,
                         context=_last_narrator, error_detail=traceback.format_exc())
            return jsonify({"error": f"Internal error: {e}"}), 500
        _elapsed = time.monotonic() - _t0

        if not isinstance(result, dict):
            result = dict(state)

        # Detect empty narrator response
        _nt = (result.get("_narrator_text") or "").strip()
        if not _nt or _nt == "...":
            log_friction(event_type="empty_narrator", story_id=story_id,
                         session_id=session_key, player_input=message, context=_last_narrator)

        # Detect slow turn (>30s)
        if _elapsed > 30:
            log_friction(event_type="slow_turn", story_id=story_id,
                         session_id=session_key, player_input=message,
                         error_detail=f"{_elapsed:.1f}s")

        # Detect character fallback responses
        _char_resp = result.get("_character_responses") or {}
        for _ck, _cv in _char_resp.items():
            if isinstance(_cv, dict):
                _dial = (_cv.get("dialogue") or "").strip()
                if _dial in ("", "..."):
                    log_friction(event_type="empty_character", story_id=story_id,
                                 session_id=session_key, player_input=message,
                                 context=f"character={_ck}", error_detail=_dial)

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
            try:
                _upsert_save(conn, story_id, g.user_id, 0, result)
            except sqlite3.IntegrityError:
                logger.warning("play_chat: save failed for user_id=%s (FK constraint)", g.user_id)
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
            "progression_state": result.get("_progression_state", {}),
            "location": result.get("_location", {}),
            "location_state": result.get("_location_state", {}),
            "map": result.get("map", {}),
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
        "active_portraits": state.get("_active_portraits") or {},
        "progression_state": state.get("_progression_state") or {},
        "location": state.get("_location") or {},
        "location_state": state.get("_location_state") or {},
        "map": state.get("map") or {},
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
        try:
            _upsert_save(conn, story_id, g.user_id, slot, cached)
        except sqlite3.IntegrityError:
            logger.warning("save_game: save failed for user_id=%s (FK constraint)", g.user_id)
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
    # Remove opening fence line (```json or ``` or ```JSON etc.)
    first_nl = s.find("\n")
    if first_nl >= 0:
        s = s[first_nl + 1:]
    else:
        s = s[3:]
    # Remove closing fence
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
        llm = get_llm(get_model_for_role("creative"))
        raw = llm.invoke(prompt)
        text = llm_result_to_text(raw)
        cleaned = _strip_markdown_json_fences(text)
        story = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("ai/generate-story: JSON parse failed: %s — raw: %s", e, text[:300] if 'text' in dir() else '(no text)')
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
    character_names = data.get("character_names", [])

    if not scene:
        return jsonify({"error": "scene is required"}), 400

    # Build forbidden actions list — extract key verbs/phrases from ALL previous actions
    forbidden = ""
    if previous_actions:
        # Show recent actions in full
        recent = previous_actions[-3:]
        recent_lines = [f"- {a}" for a in recent]
        # Extract short summaries of older actions to catch repeats
        older_summaries = []
        for a in previous_actions[:-3]:
            # Take first 40 chars as a fingerprint
            short = a[:40].rstrip()
            if short.endswith("..."):
                short = short[:-3]
            older_summaries.append(short)
        parts = ["DO NOT repeat these previous actions:"]
        if older_summaries:
            parts.append("Earlier: " + " / ".join(older_summaries))
        parts.append("Recent:")
        parts.extend(recent_lines)
        parts.append("Your action must be COMPLETELY DIFFERENT from ALL of the above.")
        forbidden = "\n".join(parts)

    bg_block = f"\nYour character: {player_background}" if player_background else ""
    title_block = f"\nStory: {game_title}" if game_title else ""

    # Force variety based on turn number — each turn gets a specific ACTION TYPE
    variety_hints = [
        "PHYSICALLY DO something — grab an object, open a door, pick a lock, plant a device.",
        "SAY something confrontational to {char} — accuse, challenge, or provoke them.",
        "SEARCH or EXAMINE something specific — a document, a pocket, a briefcase, a room.",
        "MAKE A DECISION that changes things — agree to a deal, refuse an order, tell a lie.",
        "DEMAND ANSWERS from {char} — corner them, block their exit, force a response.",
        "LEAVE this area — go to a different room, follow someone, sneak away.",
        "TAKE A RISK — reveal your identity, make a threat, place a dangerous bet.",
        "DO SOMETHING SNEAKY — plant evidence, swap drinks, pick a pocket, hide something.",
        "ESCALATE THE SITUATION — pull a weapon, slam a table, make a scene, break something.",
        "MAKE A MOVE to end this — betray someone, expose the truth, trigger your exit plan.",
    ]
    turn_idx = max(0, (turn_number - 1)) % len(variety_hints)
    # Fill in a random character name if the hint references {char}
    hint_char = character_names[(turn_number - 1) % len(character_names)] if character_names else "someone"
    variety_hint = variety_hints[turn_idx].replace("{char}", hint_char)

    # Pacing hint for story arc
    if total_turns > 1:
        pct = turn_number / total_turns
        if pct <= 0.3:
            pacing = "EARLY — gather intel, test the waters."
        elif pct <= 0.7:
            pacing = "MIDDLE — escalate, take risks, make things happen."
        else:
            pacing = "CLIMAX — force a confrontation, go all in."
    else:
        pacing = ""

    chars_block = ""
    if character_names:
        chars_block = f"\nCharacters: {', '.join(character_names)}"

    # Build forbidden verbs from previous actions to force variety
    forbidden = ""
    if previous_actions:
        prev_lines = [f"- {a}" for a in previous_actions[-5:]]
        forbidden = "\nDO NOT repeat these previous actions:\n" + "\n".join(prev_lines) + "\nYour action must be COMPLETELY DIFFERENT from all of the above.\n"

    prompt = f"""TASK: Write what {player_name} does next. ONE sentence starting with "I".{title_block}{bg_block}{chars_block}

Scene:
{scene[:600]}
{forbidden}
>>> YOU MUST: {variety_hint} <<<
{f"Story phase: {pacing}" if pacing else ""}

Rules:
- ONE sentence only, starting with "I"
- Must follow the YOU MUST directive above
- Be specific: name the person, object, or place
- Do NOT just walk over and talk — DO something

{player_name}:"""

    try:
        llm = get_llm(get_model_for_role("creative"))
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

# Phase 1 (face wizard): forward-facing reference headshots for IP-Adapter / LoRA datasets.
FACE_CANDIDATE_PROMPT_SUFFIX = (
    "front view, facing camera, direct eye contact, symmetrical face, "
    "head and upper chest visible, neutral relaxed expression, mouth closed, "
    "plain solid light gray studio backdrop, no scenery, no environment, no props, "
    "empty background, centered subject, soft even studio lighting, clean headshot"
)

FACE_CANDIDATE_NEGATIVE_EXTRA = (
    "background detail, busy background, scenery, landscape, indoor, outdoor, "
    "room interior, sky, trees, windows, furniture, depth of field, bokeh, "
    "blurred background, crowd, text, watermark, signature, logo, "
    "profile, side view, three quarter view, looking away, looking down, dutch angle"
)

# Manual face-reference controls (phase 1 wizard) — keys sent from UI; values are prompt fragments.
FACE_REF_DEFAULTS: dict[str, str] = {
    "sex": "female",
    "ethnicity": "unspecified",
    "age": "young_adult",
    "hair_color": "brown",
    "hair_length": "medium",
    "eye_color": "brown",
    "facial_hair": "none",
    "image_style": "anime",
}

FACE_REF_OPTIONS_SEX = [
    ("unspecified", "Unspecified"),
    ("female", "Female"),
    ("male", "Male"),
    ("androgynous", "Androgynous"),
]

FACE_REF_OPTIONS_ETHNICITY = [
    ("unspecified", "Unspecified"),
    ("east_asian", "East Asian"),
    ("south_asian", "South Asian"),
    ("southeast_asian", "Southeast Asian"),
    ("black", "Black / African"),
    ("white_european", "White / European"),
    ("middle_eastern", "Middle Eastern"),
    ("latino", "Latino / Hispanic"),
    ("pacific", "Pacific Islander"),
    ("indigenous", "Indigenous"),
    ("mixed", "Mixed"),
]

FACE_REF_OPTIONS_AGE = [
    ("unspecified", "Unspecified"),
    ("teen", "Teen"),
    ("young_adult", "Young adult"),
    ("adult", "Adult"),
    ("middle_aged", "Middle-aged"),
    ("senior", "Senior"),
]

FACE_REF_OPTIONS_HAIR_COLOR = [
    ("black", "Black"),
    ("brown", "Brown"),
    ("blonde", "Blonde"),
    ("red", "Red / ginger"),
    ("auburn", "Auburn"),
    ("gray_white", "Gray / white"),
    ("silver", "Silver"),
    ("platinum", "Platinum blonde"),
    ("blue", "Blue (dyed)"),
    ("green", "Green (dyed)"),
    ("pink", "Pink (dyed)"),
    ("purple", "Purple (dyed)"),
    ("multicolor", "Multicolor"),
]

FACE_REF_OPTIONS_HAIR_LENGTH = [
    ("bald", "Bald"),
    ("buzz", "Buzz cut"),
    ("short", "Short"),
    ("medium", "Medium"),
    ("long", "Long"),
    ("very_long", "Very long"),
]

FACE_REF_OPTIONS_EYE_COLOR = [
    ("brown", "Brown"),
    ("dark_brown", "Dark brown"),
    ("blue", "Blue"),
    ("green", "Green"),
    ("hazel", "Hazel"),
    ("gray", "Gray"),
    ("amber", "Amber"),
    ("black", "Black"),
    ("red_violet", "Red / violet (fantasy)"),
    ("heterochromia", "Heterochromia"),
]

FACE_REF_OPTIONS_FACIAL_HAIR = [
    ("none", "None"),
    ("stubble", "Stubble"),
    ("mustache", "Mustache"),
    ("goatee", "Goatee"),
    ("short_beard", "Short beard"),
    ("full_beard", "Full beard"),
]

FACE_REF_OPTIONS_IMAGE_STYLE = [
    ("anime", "Anime / cel-shaded"),
    ("semi_realistic", "Semi-realistic illustration"),
    ("soft_anime", "Soft anime / VN"),
    ("realistic", "Photorealistic"),
    ("painterly", "Painterly / digital paint"),
    ("comic", "Comic / graphic novel"),
    ("watercolor", "Watercolor style"),
]

FACE_REF_PROMPT_SEX = {
    "unspecified": "",
    "female": "woman",
    "male": "man",
    "androgynous": "androgynous person",
}

FACE_REF_PROMPT_ETHNICITY = {
    "unspecified": "",
    "east_asian": "East Asian appearance",
    "south_asian": "South Asian appearance",
    "southeast_asian": "Southeast Asian appearance",
    "black": "Black African appearance",
    "white_european": "European appearance",
    "middle_eastern": "Middle Eastern appearance",
    "latino": "Latino appearance",
    "pacific": "Pacific Islander appearance",
    "indigenous": "Indigenous appearance",
    "mixed": "mixed ethnicity appearance",
}

FACE_REF_PROMPT_AGE = {
    "unspecified": "",
    "teen": "teenager, youthful face",
    "young_adult": "young adult",
    "adult": "adult",
    "middle_aged": "middle-aged",
    "senior": "elderly, aged face",
}

FACE_REF_PROMPT_HAIR_COLOR = {
    "black": "black",
    "brown": "brown",
    "blonde": "blonde",
    "red": "red ginger",
    "auburn": "auburn",
    "gray_white": "gray and white",
    "silver": "silver",
    "platinum": "platinum blonde",
    "blue": "blue dyed",
    "green": "green dyed",
    "pink": "pink dyed",
    "purple": "purple dyed",
    "multicolor": "multicolored",
}

FACE_REF_PROMPT_HAIR_LENGTH = {
    "bald": "completely bald",
    "buzz": "buzz cut",
    "short": "short hair",
    "medium": "medium length hair",
    "long": "long hair",
    "very_long": "very long hair",
}

FACE_REF_PROMPT_EYE = {
    "brown": "brown eyes",
    "dark_brown": "dark brown eyes",
    "blue": "blue eyes",
    "green": "green eyes",
    "hazel": "hazel eyes",
    "gray": "gray eyes",
    "amber": "amber eyes",
    "black": "dark brown to black eyes",
    "red_violet": "red or violet eyes",
    "heterochromia": "heterochromatic eyes",
}

FACE_REF_PROMPT_FACIAL_HAIR = {
    "none": "",
    "stubble": "light stubble",
    "mustache": "mustache",
    "goatee": "goatee",
    "short_beard": "short beard",
    "full_beard": "full beard",
}

FACE_REF_PROMPT_IMAGE_STYLE = {
    "anime": "anime style portrait, cel-shaded, clean lines",
    "semi_realistic": "semi-realistic illustrated portrait, detailed shading",
    "soft_anime": "soft anime visual novel portrait, gentle shading",
    "realistic": "photorealistic portrait, natural skin texture, DSLR photo",
    "painterly": "digital painting portrait, visible brush strokes",
    "comic": "comic book portrait, bold ink outlines",
    "watercolor": "watercolor illustration portrait, soft edges",
}


def _face_ref_allowed(key: str, value: str, allowed: set[str]) -> str:
    if value in allowed:
        return value
    return FACE_REF_DEFAULTS.get(key, next(iter(allowed)))


def build_face_reference_prompt(data: dict) -> tuple[str, str]:
    """Build positive prompt and a short human-readable summary from manual face controls."""
    d = dict(FACE_REF_DEFAULTS)
    for k in FACE_REF_DEFAULTS:
        if k in data and data[k] is not None:
            raw = str(data[k]).strip()
            if raw:
                d[k] = raw

    sex = _face_ref_allowed("sex", d["sex"], set(FACE_REF_PROMPT_SEX.keys()))
    eth = _face_ref_allowed("ethnicity", d["ethnicity"], set(FACE_REF_PROMPT_ETHNICITY.keys()))
    age = _face_ref_allowed("age", d["age"], set(FACE_REF_PROMPT_AGE.keys()))
    hc = _face_ref_allowed("hair_color", d["hair_color"], set(FACE_REF_PROMPT_HAIR_COLOR.keys()))
    hl = _face_ref_allowed("hair_length", d["hair_length"], set(FACE_REF_PROMPT_HAIR_LENGTH.keys()))
    eye = _face_ref_allowed("eye_color", d["eye_color"], set(FACE_REF_PROMPT_EYE.keys()))
    fh = _face_ref_allowed("facial_hair", d["facial_hair"], set(FACE_REF_PROMPT_FACIAL_HAIR.keys()))
    st = _face_ref_allowed("image_style", d["image_style"], set(FACE_REF_PROMPT_IMAGE_STYLE.keys()))

    parts: list[str] = [FACE_REF_PROMPT_IMAGE_STYLE[st]]

    s_sex = FACE_REF_PROMPT_SEX[sex]
    s_eth = FACE_REF_PROMPT_ETHNICITY[eth]
    s_age = FACE_REF_PROMPT_AGE[age]
    if s_sex:
        parts.append(s_sex)
    if s_eth:
        parts.append(s_eth)
    if s_age:
        parts.append(s_age)

    if hl == "bald":
        parts.append("bald head, no hair on scalp")
    else:
        h_str = FACE_REF_PROMPT_HAIR_LENGTH[hl]
        c_str = FACE_REF_PROMPT_HAIR_COLOR[hc]
        parts.append(f"{h_str}, {c_str} hair")

    parts.append(FACE_REF_PROMPT_EYE[eye])

    s_fh = FACE_REF_PROMPT_FACIAL_HAIR[fh]
    if s_fh:
        parts.append(s_fh)

    extra = (data.get("face_extra_details") or "").strip()
    if extra:
        parts.append(extra)

    parts.append(FACE_CANDIDATE_PROMPT_SUFFIX)
    prompt = ", ".join(p for p in parts if p)

    summary_bits = [f"{k}: {d[k]}" for k in FACE_REF_DEFAULTS]
    if extra:
        summary_bits.append(f"extra: {extra[:120]}")
    summary = "; ".join(summary_bits)

    return prompt, summary


@app.route("/ai/face-ref-options", methods=["GET"])
def ai_face_ref_options():
    """Static dropdown metadata for face wizard (phase 1)."""

    def opts(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
        return [{"value": a, "label": b} for a, b in pairs]

    return jsonify({
        "defaults": dict(FACE_REF_DEFAULTS),
        "fields": {
            "sex": opts(FACE_REF_OPTIONS_SEX),
            "ethnicity": opts(FACE_REF_OPTIONS_ETHNICITY),
            "age": opts(FACE_REF_OPTIONS_AGE),
            "hair_color": opts(FACE_REF_OPTIONS_HAIR_COLOR),
            "hair_length": opts(FACE_REF_OPTIONS_HAIR_LENGTH),
            "eye_color": opts(FACE_REF_OPTIONS_EYE_COLOR),
            "facial_hair": opts(FACE_REF_OPTIONS_FACIAL_HAIR),
            "image_style": opts(FACE_REF_OPTIONS_IMAGE_STYLE),
        },
    })


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


@app.route("/ai/scene-styles", methods=["GET"])
def list_scene_styles():
    return jsonify({"styles": [{"key": k, "description": v} for k, v in SCENE_STYLES.items()]})


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

    # Check if any characters have LoRAs — if so, inject trigger words and use LoRA workflow
    char_lora = None
    conn = get_db()
    try:
        row = conn.execute("SELECT characters FROM stories WHERE id = ?", (story_id,)).fetchone()
        if row:
            characters = json.loads(row["characters"] or "{}")
            for char_key, char_data in characters.items():
                if isinstance(char_data, dict) and char_data.get("lora") and char_data.get("trigger_word"):
                    char_lora = {
                        "lora": char_data["lora"],
                        "trigger_word": char_data["trigger_word"],
                        "lora_strength": float(char_data.get("lora_strength", 0.85)),
                    }
                    # Inject trigger word into prompt if not already present
                    tw = char_lora["trigger_word"]
                    if tw.lower() not in prompt.lower():
                        prompt = f"{tw}, {prompt}"
                    break  # Use the first character with a LoRA (single LoRA for now)
    finally:
        conn.close()

    use_lora = char_lora is not None
    workflow_name = "LoRA" if use_lora else ("PonyForRPG" if comfyui_client._pick_checkpoint(nsfw_rating) == "pony" else "FluxForRPG")
    model_name = comfyui_client.IPADAPTER_CHECKPOINT if use_lora else comfyui_client.CHECKPOINTS[comfyui_client._pick_checkpoint(nsfw_rating)]["ckpt_name"]

    image_id: int | None = None
    conn = get_db()
    try:
        image_id = create_image_record(
            conn,
            kind="scene",
            scope="turn",
            owner_type="story",
            owner_id=story_id,
            owner_key=None,
            prompt=prompt,
            workflow_name=workflow_name,
            model_name=model_name,
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

    if use_lora:
        comfyui_filename = comfyui_client.generate_with_lora(
            prompt, lora_name=char_lora["lora"],
            width=1024, height=576, prefix=prefix,
            lora_strength=char_lora["lora_strength"],
        )
    else:
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
            try:
                _upsert_save(conn, story_id, g.user_id, 0, state)
            except sqlite3.IntegrityError:
                logger.warning("generate_scene: save failed for user_id=%s (FK constraint)", g.user_id)
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


@app.route("/ai/generate-character-faces", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_character_faces():
    """Generate N candidate face images for a character. User picks one as the reference."""
    import comfyui_client

    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    character_key = (data.get("character_key") or "").strip()
    if not character_key:
        return jsonify({"error": "character_key is required"}), 400
    count = min(int(data.get("count", 3)), 6)  # Max 6 candidates

    if not comfyui_client.is_available():
        return jsonify({"error": "ComfyUI not available"}), 503

    conn = get_db()
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

        nsfw_rating = row["nsfw_rating"] or "none"

        custom_prompt = (data.get("prompt") or "").strip()
        if custom_prompt:
            base_prompt = custom_prompt
            visual_summary = "custom prompt"
        else:
            base_prompt, visual_summary = build_face_reference_prompt(data)

        ckpt_key = comfyui_client._pick_checkpoint(nsfw_rating)
        ckpt_cfg = comfyui_client.CHECKPOINTS[ckpt_key]
        neg_parts = [ckpt_cfg["negative_prompt"], FACE_CANDIDATE_NEGATIVE_EXTRA]
        face_negative = ", ".join(p for p in neg_parts if p)

        portraits_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "portraits")
        os.makedirs(portraits_dir, exist_ok=True)

        candidates = []
        for i in range(count):
            prefix = f"face_{story_id}_{character_key}_{i}"
            comfyui_filename = comfyui_client.generate_image(
                base_prompt,
                width=768,
                height=768,
                prefix=prefix,
                nsfw_rating=nsfw_rating,
                negative_prompt=face_negative,
            )
            if not comfyui_filename:
                continue

            local_filename = f"face_{story_id}_{character_key}_{i}.png"
            local_path = os.path.join(portraits_dir, local_filename)
            if comfyui_client.download_image(comfyui_filename, local_path):
                candidates.append({
                    "index": i,
                    "filename": local_filename,
                    "url": f"/images/portraits/{local_filename}",
                })

        if not candidates:
            return jsonify({"error": "All face generations failed"}), 500
    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "candidates": candidates,
        "visual_description": visual_summary,
        "count": len(candidates),
    })


@app.route("/ai/generate-character-variants", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_character_variants():
    """Generate mood-based portrait variants from an approved reference face using IP-Adapter."""
    import comfyui_client

    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    character_key = (data.get("character_key") or "").strip()
    if not character_key:
        return jsonify({"error": "character_key is required"}), 400
    reference_filename = (data.get("reference") or "").strip()
    if not reference_filename:
        return jsonify({"error": "reference filename is required"}), 400

    # Variants to generate — list of {variant_key, prompt_suffix}
    variants = data.get("variants")
    if not variants or not isinstance(variants, list):
        return jsonify({"error": "variants list is required"}), 400

    weight = float(data.get("weight", 0.75))

    if not comfyui_client.is_available():
        return jsonify({"error": "ComfyUI not available"}), 503

    conn = get_db()
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

        nsfw_rating = row["nsfw_rating"] or "none"
        genre = row["genre"] or "fantasy"
        char_label = character_key.replace("_", " ").title()

        portraits_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "portraits")
        os.makedirs(portraits_dir, exist_ok=True)

        ref_path = os.path.join(portraits_dir, reference_filename)
        if not os.path.exists(ref_path):
            return jsonify({"error": "Reference image not found on disk"}), 404

        results = []
        for v in variants[:12]:  # Cap at 12 variants
            variant_key = (v.get("key") or "").strip()
            prompt_suffix = (v.get("prompt") or "").strip()
            if not variant_key or not prompt_suffix:
                continue

            full_prompt = (
                f"{char_label}, {prompt_suffix}, portrait, head and shoulders, "
                "detailed face, cinematic lighting, high quality character art"
            )

            prefix = f"variant_{story_id}_{character_key}_{variant_key}"
            comfyui_filename = comfyui_client.generate_with_face_ref(
                prompt=full_prompt,
                ref_image_path=ref_path,
                width=512,
                height=768,
                prefix=prefix,
                nsfw_rating=nsfw_rating,
                weight=weight,
            )
            if not comfyui_filename:
                results.append({"key": variant_key, "ok": False, "error": "Generation failed"})
                continue

            local_filename = f"variant_{story_id}_{character_key}_{variant_key}.png"
            local_path = os.path.join(portraits_dir, local_filename)
            if comfyui_client.download_image(comfyui_filename, local_path):
                results.append({
                    "key": variant_key,
                    "ok": True,
                    "filename": local_filename,
                    "url": f"/images/portraits/{local_filename}",
                })
            else:
                results.append({"key": variant_key, "ok": False, "error": "Download failed"})

        # Auto-update character portraits dict with successful variants
        portraits = char_data.get("portraits") or {}
        updated = False
        for r in results:
            if r.get("ok"):
                portraits[r["key"]] = r["filename"]
                updated = True
        if updated:
            char_data["portraits"] = portraits
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
        "results": results,
        "total": len(results),
        "success": sum(1 for r in results if r.get("ok")),
    })


# --- LoRA training data ---

# 18 diverse prompts for SDXL LoRA training. {trigger} is replaced with the trigger word.
# Covers: expressions, poses, framing, lighting, angles.
LORA_TRAINING_PROMPTS = [
    # Close-up faces — expressions
    ("{trigger}, close-up portrait, neutral expression, front facing, soft studio lighting, plain background", "closeup_neutral"),
    ("{trigger}, close-up portrait, happy smiling, front facing, warm natural lighting, plain background", "closeup_happy"),
    ("{trigger}, close-up portrait, angry scowling, furrowed brows, front facing, dramatic lighting, plain background", "closeup_angry"),
    ("{trigger}, close-up portrait, sad melancholic, downcast eyes, front facing, soft lighting, plain background", "closeup_sad"),
    ("{trigger}, close-up portrait, surprised wide eyes, raised eyebrows, front facing, bright lighting, plain background", "closeup_surprised"),
    # Head and shoulders — angles
    ("{trigger}, head and shoulders portrait, three-quarter view, looking slightly left, soft lighting, plain background", "shoulders_3q_left"),
    ("{trigger}, head and shoulders portrait, three-quarter view, looking slightly right, natural lighting, plain background", "shoulders_3q_right"),
    ("{trigger}, head and shoulders portrait, slight profile view, looking away, cinematic rim lighting, dark background", "shoulders_profile"),
    ("{trigger}, head and shoulders portrait, looking up, hopeful expression, golden hour lighting, plain background", "shoulders_lookup"),
    ("{trigger}, head and shoulders portrait, looking down, thoughtful, soft overhead lighting, plain background", "shoulders_lookdown"),
    # Upper body — variety
    ("{trigger}, upper body portrait, arms crossed, confident stance, studio lighting, plain background", "upper_crossed"),
    ("{trigger}, upper body portrait, casual relaxed pose, leaning slightly, natural daylight, simple background", "upper_relaxed"),
    ("{trigger}, upper body portrait, sitting at a table, resting chin on hand, warm indoor lighting", "upper_sitting"),
    # Full body
    ("{trigger}, full body portrait, standing straight, casual clothing, studio lighting, plain white background", "full_standing"),
    ("{trigger}, full body portrait, walking pose, natural stride, outdoor daylight, blurred background", "full_walking"),
    # Lighting variety
    ("{trigger}, portrait, dramatic side lighting, high contrast, dark moody background", "light_dramatic"),
    ("{trigger}, portrait, soft diffused lighting, overcast day, muted colors, head and shoulders", "light_soft"),
    ("{trigger}, portrait, golden hour warm sunlight, glowing skin, head and shoulders, outdoor", "light_golden"),
]


@app.route("/ai/generate-lora-training-data", methods=["POST"])
@optional_rate_limit(RATE_LIMIT_AI)
@login_required
def ai_generate_lora_training_data():
    """Generate a diverse set of captioned images for SDXL LoRA training using FaceID."""
    import comfyui_client

    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    character_key = (data.get("character_key") or "").strip()
    if not character_key:
        return jsonify({"error": "character_key is required"}), 400
    trigger_word = (data.get("trigger_word") or "").strip()
    if not trigger_word:
        return jsonify({"error": "trigger_word is required (e.g. 'alexchar')"}), 400
    reference_filename = (data.get("reference") or "").strip()
    if not reference_filename:
        return jsonify({"error": "reference filename is required"}), 400

    weight = float(data.get("weight", 0.85))

    if not comfyui_client.is_available():
        return jsonify({"error": "ComfyUI not available"}), 503

    conn = get_db()
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

        portraits_dir = os.path.join(os.path.dirname(__file__), "web", "static", "images", "portraits")
        ref_path = os.path.join(portraits_dir, reference_filename)
        if not os.path.exists(ref_path):
            return jsonify({"error": "Reference image not found on disk"}), 404

        # Create training data output directory
        training_dir = os.path.join(
            os.path.dirname(__file__), "training_data",
            f"story_{story_id}_{character_key}",
        )
        os.makedirs(training_dir, exist_ok=True)

        # Copy reference image as first training image
        import shutil
        ref_dest = os.path.join(training_dir, "00_reference.png")
        shutil.copy2(ref_path, ref_dest)
        with open(os.path.join(training_dir, "00_reference.txt"), "w") as f:
            f.write(f"{trigger_word}, portrait, front facing, neutral expression, head and shoulders, detailed face")

        results = []
        for i, (prompt_template, label) in enumerate(LORA_TRAINING_PROMPTS):
            prompt = prompt_template.replace("{trigger}", trigger_word)
            prefix = f"lora_{story_id}_{character_key}_{label}"

            comfyui_filename = comfyui_client.generate_with_face_ref(
                prompt=prompt,
                ref_image_path=ref_path,
                width=768,
                height=1024,
                prefix=prefix,
                weight=weight,
            )
            if not comfyui_filename:
                results.append({"label": label, "ok": False, "error": "Generation failed"})
                continue

            # Save image to training directory with sequential naming
            local_filename = f"{i+1:02d}_{label}.png"
            local_path = os.path.join(training_dir, local_filename)
            if comfyui_client.download_image(comfyui_filename, local_path):
                # Write caption file (kohya format: same name, .txt extension)
                caption_path = os.path.join(training_dir, f"{i+1:02d}_{label}.txt")
                with open(caption_path, "w") as f:
                    f.write(prompt)
                results.append({"label": label, "ok": True, "filename": local_filename})
            else:
                results.append({"label": label, "ok": False, "error": "Download failed"})

        success_count = sum(1 for r in results if r.get("ok"))
    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "training_dir": training_dir,
        "trigger_word": trigger_word,
        "results": results,
        "total": len(results) + 1,  # +1 for reference image
        "success": success_count + 1,
    })


@app.route("/ai/lora-training-data/<int:story_id>/<character_key>", methods=["GET"])
@login_required
def ai_get_lora_training_data(story_id: int, character_key: str):
    """List generated training images for a character."""
    training_dir = os.path.join(
        os.path.dirname(__file__), "training_data",
        f"story_{story_id}_{character_key}",
    )
    if not os.path.isdir(training_dir):
        return jsonify({"images": [], "training_dir": None})

    images = []
    for fname in sorted(os.listdir(training_dir)):
        if not fname.endswith(".png"):
            continue
        caption_file = os.path.join(training_dir, fname.rsplit(".", 1)[0] + ".txt")
        caption = ""
        if os.path.exists(caption_file):
            with open(caption_file) as f:
                caption = f.read().strip()
        images.append({
            "filename": fname,
            "caption": caption,
            "url": f"/ai/lora-training-image/{story_id}/{character_key}/{fname}",
        })

    return jsonify({"images": images, "training_dir": training_dir})


@app.route("/ai/lora-training-image/<int:story_id>/<character_key>/<filename>", methods=["GET"])
@login_required
def ai_serve_lora_training_image(story_id: int, character_key: str, filename: str):
    """Serve a training image file."""
    # Sanitize filename to prevent directory traversal
    safe_name = os.path.basename(filename)
    training_dir = os.path.join(
        os.path.dirname(__file__), "training_data",
        f"story_{story_id}_{character_key}",
    )
    file_path = os.path.join(training_dir, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Not found"}), 404
    from flask import send_file
    return send_file(file_path, mimetype="image/png")


@app.route("/ai/export-lora-training", methods=["POST"])
@login_required
def ai_export_lora_training():
    """Copy selected training images to kohya_ss folder structure for manual training."""
    data = request.get_json(silent=True) or {}
    try:
        story_id = int(data.get("story_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "story_id is required"}), 400
    character_key = (data.get("character_key") or "").strip()
    if not character_key:
        return jsonify({"error": "character_key is required"}), 400
    trigger_word = (data.get("trigger_word") or "").strip()
    if not trigger_word:
        return jsonify({"error": "trigger_word is required"}), 400
    selected = data.get("selected", [])
    if not selected or not isinstance(selected, list):
        return jsonify({"error": "selected list of filenames is required"}), 400

    training_dir = os.path.join(
        os.path.dirname(__file__), "training_data",
        f"story_{story_id}_{character_key}",
    )
    if not os.path.isdir(training_dir):
        return jsonify({"error": "No training data found. Generate it first."}), 404

    # kohya folder structure: ~/kohya_ss/training/{charKey}/img/10_{trigger}/
    kohya_base = os.path.expanduser("~/kohya_ss/training")
    kohya_img_dir = os.path.join(kohya_base, character_key, "img", f"10_{trigger_word}")
    kohya_model_dir = os.path.join(kohya_base, character_key, "model")
    kohya_log_dir = os.path.join(kohya_base, character_key, "log")
    os.makedirs(kohya_img_dir, exist_ok=True)
    os.makedirs(kohya_model_dir, exist_ok=True)
    os.makedirs(kohya_log_dir, exist_ok=True)

    import shutil
    copied = 0
    for fname in selected:
        safe_name = os.path.basename(fname)
        src = os.path.join(training_dir, safe_name)
        if not os.path.isfile(src):
            continue
        shutil.copy2(src, os.path.join(kohya_img_dir, safe_name))
        # Copy matching caption file
        caption_src = os.path.join(training_dir, safe_name.rsplit(".", 1)[0] + ".txt")
        if os.path.isfile(caption_src):
            shutil.copy2(caption_src, os.path.join(kohya_img_dir, safe_name.rsplit(".", 1)[0] + ".txt"))
        copied += 1

    num_images = copied
    repeats = 10
    steps_per_epoch = num_images * repeats
    target_steps = 1800
    epochs = max(1, round(target_steps / steps_per_epoch)) if steps_per_epoch > 0 else 10

    training_command = (
        f"cd ~/kohya_ss && source venv/bin/activate && "
        f"accelerate launch --num_cpu_threads_per_process=2 sd-scripts/sdxl_train_network.py "
        f"--pretrained_model_name_or_path=/home/mcgowee/ComfyUI/models/checkpoints/juggernautXL_v8Rundiffusion.safetensors "
        f"--train_data_dir={os.path.join(kohya_base, character_key, 'img')} "
        f"--output_dir={kohya_model_dir} "
        f"--logging_dir={kohya_log_dir} "
        f"--output_name={character_key}_lora "
        f"--network_module=networks.lora "
        f"--network_dim=32 "
        f"--network_alpha=16 "
        f"--resolution=1024 "
        f"--train_batch_size=1 "
        f"--max_train_epochs={epochs} "
        f"--learning_rate=1e-4 "
        f"--unet_lr=1e-4 "
        f"--text_encoder_lr=5e-5 "
        f"--lr_scheduler=cosine "
        f"--lr_warmup_steps=100 "
        f"--optimizer_type=AdamW8bit "
        f"--mixed_precision=fp16 "
        f"--save_precision=fp16 "
        f"--gradient_checkpointing "
        f"--cache_latents "
        f"--seed=42 "
        f"--caption_extension=.txt "
        f"--enable_bucket "
        f"--min_bucket_reso=512 "
        f"--max_bucket_reso=1536 "
    )

    return jsonify({
        "ok": True,
        "kohya_dir": kohya_img_dir,
        "copied": copied,
        "selected": len(selected),
        "epochs": epochs,
        "steps_estimate": steps_per_epoch * epochs,
        "training_command": training_command,
        "output_model": os.path.join(kohya_model_dir, f"{character_key}_lora.safetensors"),
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
# Internal API (static API key auth, no session/cookie)
# ---------------------------------------------------------------------------

INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")


def _require_internal_key():
    """Check X-Internal-Key header. Returns an error response or None."""
    if not INTERNAL_API_KEY:
        return jsonify({"error": "INTERNAL_API_KEY not configured"}), 503
    key = request.headers.get("X-Internal-Key", "")
    if key != INTERNAL_API_KEY:
        return jsonify({"error": "Invalid or missing X-Internal-Key"}), 401
    return None


def _story_owner_id(conn, story_id: int) -> int | None:
    row = conn.execute("SELECT user_id FROM stories WHERE id = ?", (story_id,)).fetchone()
    return row["user_id"] if row else None


@app.route("/internal/health", methods=["GET"])
def internal_health():
    err = _require_internal_key()
    if err:
        return err
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
    return jsonify(body), 200 if db_ok else 503


@app.route("/internal/stories", methods=["GET"])
def internal_list_stories():
    err = _require_internal_key()
    if err:
        return err
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM stories ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return jsonify([_story_row_to_dict(r) for r in rows])


@app.route("/internal/stories/<int:story_id>/state", methods=["GET"])
def internal_story_state(story_id):
    err = _require_internal_key()
    if err:
        return err
    conn = get_db()
    try:
        owner_id = _story_owner_id(conn, story_id)
        if owner_id is None:
            return jsonify({"error": "Story not found"}), 404

        session_key = _play_session_key(story_id, owner_id)
        state = _ensure_play_session(session_key, story_id, owner_id)
        if state is None:
            return jsonify({"error": "No active game"}), 404

        save_rows = conn.execute(
            "SELECT slot, saved_at, state FROM saves WHERE story_id = ? AND user_id = ? ORDER BY slot",
            (story_id, owner_id),
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
        save_slots.append({"slot": sr["slot"], "timestamp": sr["saved_at"], "turns": turns})

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
        "active_portraits": state.get("_active_portraits") or {},
        "progression_state": state.get("_progression_state") or {},
        "location": state.get("_location") or {},
        "location_state": state.get("_location_state") or {},
        "map": state.get("map") or {},
    }
    if state.get("opening"):
        payload["opening"] = state["opening"]
    return jsonify(payload)


@app.route("/internal/stories/<int:story_id>/chat", methods=["POST"])
def internal_story_chat(story_id):
    err = _require_internal_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    conn = get_db()
    try:
        owner_id = _story_owner_id(conn, story_id)
    finally:
        conn.close()
    if owner_id is None:
        return jsonify({"error": "Story not found"}), 404

    session_key = _play_session_key(story_id, owner_id)

    adv_lock = _get_adventure_lock(session_key)
    if not adv_lock.acquire(timeout=CHAT_LOCK_TIMEOUT_S):
        return jsonify({"error": "Another turn is still in progress."}), 429

    try:
        state = _ensure_play_session(session_key, story_id, owner_id)
        if state is None:
            return jsonify({"error": "No active game. Start a new game first."}), 400

        if state.get("paused"):
            return jsonify({
                "response": "The game is paused. Unpause to continue playing.",
                "game_title": state.get("game_title", ""),
                "turn_count": state.get("turn_count", 0),
                "paused": True,
            })

        # --- Friction detection (non-blocking) ---
        _hist = state.get("history") or []
        _last_narrator = ""
        if _hist and isinstance(_hist[-1], dict):
            _last_narrator = _hist[-1].get("narrator", "")
        if _hist and isinstance(_hist[-1], dict) and _hist[-1].get("player", "").strip().lower() == message.lower():
            log_friction(event_type="repeated_input", story_id=story_id,
                         session_id=session_key, player_input=message, context=_last_narrator)
        _norm = message.lower().strip().rstrip("?!.")
        if _norm in CONFUSION_PATTERNS or message.strip() == "?":
            log_friction(event_type="player_confused", story_id=story_id,
                         session_id=session_key, player_input=message, context=_last_narrator)
        # --- End friction detection ---

        state["message"] = message

        subgraph_name = state.get("_subgraph_name", "narrator_chat_lite")
        if subgraph_name not in registry:
            return jsonify({"error": f"Subgraph not available: {subgraph_name}"}), 503

        compiled = registry.require(subgraph_name)
        _t0 = time.monotonic()
        try:
            result = compiled.invoke(state)
        except Exception as e:
            logger.exception(
                "internal/chat graph invoke failed story_id=%s",
                story_id,
            )
            log_friction(event_type="error_500", story_id=story_id,
                         session_id=session_key, player_input=message,
                         context=_last_narrator, error_detail=traceback.format_exc())
            return jsonify({"error": f"Internal error: {e}"}), 500
        _elapsed = time.monotonic() - _t0

        if not isinstance(result, dict):
            result = dict(state)

        # Detect empty narrator response
        _nt = (result.get("_narrator_text") or "").strip()
        if not _nt or _nt == "...":
            log_friction(event_type="empty_narrator", story_id=story_id,
                         session_id=session_key, player_input=message, context=_last_narrator)

        # Detect slow turn (>30s)
        if _elapsed > 30:
            log_friction(event_type="slow_turn", story_id=story_id,
                         session_id=session_key, player_input=message,
                         error_detail=f"{_elapsed:.1f}s")

        # Detect character fallback responses
        _char_resp = result.get("_character_responses") or {}
        for _ck, _cv in _char_resp.items():
            if isinstance(_cv, dict):
                _dial = (_cv.get("dialogue") or "").strip()
                if _dial in ("", "..."):
                    log_friction(event_type="empty_character", story_id=story_id,
                                 session_id=session_key, player_input=message,
                                 context=f"character={_ck}", error_detail=_dial)

        history = list(result.get("history") or state.get("history") or [])
        last_is_current = (
            history
            and isinstance(history[-1], dict)
            and history[-1].get("player") == message
        )
        if not last_is_current:
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
            advance_phase_after_turn(result, message, conn, owner_id)
            result["_subgraph_name"] = result.get("_subgraph_name", subgraph_name)
            try:
                _upsert_save(conn, story_id, owner_id, 0, result)
            except sqlite3.IntegrityError:
                logger.warning("internal_chat: save failed for story_id=%s (FK constraint)", story_id)
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
            "progression_state": result.get("_progression_state", {}),
            "location": result.get("_location", {}),
            "location_state": result.get("_location_state", {}),
            "map": result.get("map", {}),
        })
    finally:
        adv_lock.release()


@app.route("/internal/stories/<int:story_id>/saves", methods=["GET"])
def internal_story_saves(story_id):
    err = _require_internal_key()
    if err:
        return err
    conn = get_db()
    try:
        owner_id = _story_owner_id(conn, story_id)
        if owner_id is None:
            return jsonify({"error": "Story not found"}), 404
        rows = conn.execute(
            "SELECT slot, saved_at, state FROM saves WHERE story_id = ? AND user_id = ? ORDER BY slot",
            (story_id, owner_id),
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


@app.route("/internal/stories", methods=["POST"])
def internal_create_story():
    err = _require_internal_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    characters = data.get("characters", {})
    if not isinstance(characters, dict):
        characters = {}
    map_data = data.get("map", {})
    if not isinstance(map_data, dict):
        map_data = {}
    user_id = 1
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO stories (user_id, title, description, genre, tone,
                  nsfw_rating, nsfw_tags, opening,
                  narrator_prompt, narrator_model, player_name, player_background,
                  subgraph_name, main_graph_template_id, characters, notes, story_images, map)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                title,
                data.get("description", ""),
                data.get("genre", ""),
                data.get("tone", ""),
                "none",
                "[]",
                data.get("opening", ""),
                data.get("narrator_prompt", ""),
                data.get("narrator_model", "default"),
                data.get("player_name", "Adventurer"),
                data.get("player_background", ""),
                data.get("subgraph_name", "narrator_chat_lite"),
                None,
                json.dumps(characters),
                data.get("notes", ""),
                "[]",
                json.dumps(map_data),
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"id": new_id, "title": title}), 201


@app.route("/internal/stories/<int:story_id>/start", methods=["POST"])
def internal_start_game(story_id):
    err = _require_internal_key()
    if err:
        return err
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        if not row:
            return jsonify({"error": "Story not found"}), 404
        user_id = row["user_id"]
        state = _build_state_from_story(row)
        opening = (row["opening"] or "").strip()
        if opening:
            state["response"] = opening
        session_key = _play_session_key(story_id, user_id)
        state["_story_id"] = story_id
        perr = apply_main_graph_to_new_state(state, row, conn, user_id)
        if perr:
            return jsonify({"error": perr}), 400
        sg = state.get("_subgraph_name", "narrator_chat_lite")
        if sg not in registry:
            return jsonify({"error": f"Subgraph not available: {sg}"}), 503
        game_session_cache.set(session_key, state)
        try:
            _upsert_save(conn, story_id, user_id, 0, state)
        except sqlite3.IntegrityError:
            logger.warning("internal_start: save failed story_id=%s", story_id)
        conn.execute(
            "UPDATE stories SET play_count = play_count + 1 WHERE id = ?", (story_id,)
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({
        "session_id": session_key,
        "story_id": story_id,
        "response": state.get("response", ""),
        "turn_count": 0,
        "subgraph_name": state.get("_subgraph_name", ""),
    })


@app.route("/internal/stories/<int:story_id>/reset", methods=["POST"])
def internal_reset_game(story_id):
    err = _require_internal_key()
    if err:
        return err
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        if not row:
            return jsonify({"error": "Story not found"}), 404
        user_id = row["user_id"]
        session_key = _play_session_key(story_id, user_id)
        # Clear saves and cache
        conn.execute("DELETE FROM saves WHERE story_id = ? AND user_id = ?", (story_id, user_id))
        conn.commit()
        game_session_cache.delete(session_key)
        # Re-initialize
        state = _build_state_from_story(row)
        opening = (row["opening"] or "").strip()
        if opening:
            state["response"] = opening
        state["_story_id"] = story_id
        perr = apply_main_graph_to_new_state(state, row, conn, user_id)
        if perr:
            return jsonify({"error": perr}), 400
        sg = state.get("_subgraph_name", "narrator_chat_lite")
        if sg not in registry:
            return jsonify({"error": f"Subgraph not available: {sg}"}), 503
        game_session_cache.set(session_key, state)
        try:
            _upsert_save(conn, story_id, user_id, 0, state)
        except sqlite3.IntegrityError:
            logger.warning("internal_reset: save failed story_id=%s", story_id)
        conn.commit()
    finally:
        conn.close()
    return jsonify({
        "session_id": session_key,
        "story_id": story_id,
        "response": state.get("response", ""),
        "turn_count": 0,
        "subgraph_name": state.get("_subgraph_name", ""),
    })


# ---------------------------------------------------------------------------
# Self-improvement pipeline routes
# ---------------------------------------------------------------------------

@app.route("/internal/stories/<int:story_id>/config", methods=["GET"])
def internal_story_config(story_id):
    err = _require_internal_key()
    if err:
        return err
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Story not found"}), 404
    return jsonify(_story_row_to_dict(row, include_content=True))


@app.route("/internal/stories/<int:story_id>", methods=["PATCH"])
def internal_patch_story(story_id):
    err = _require_internal_key()
    if err:
        return err
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        if not row:
            return jsonify({"error": "Story not found"}), 404

        data = request.get_json(silent=True) or {}
        updatable = [
            "narrator_prompt", "narrator_model", "opening",
            "player_name", "player_background", "title",
            "description", "genre", "tone", "is_public",
        ]
        sets = []
        vals = []
        updated_fields = []
        for field in updatable:
            if field in data:
                sets.append(f"{field} = ?")
                vals.append(data[field])
                updated_fields.append(field)

        # characters_merge: deep-merge into existing characters dict
        if "characters_merge" in data and isinstance(data["characters_merge"], dict):
            try:
                existing = json.loads(row["characters"] or "{}")
            except (json.JSONDecodeError, TypeError):
                existing = {}
            for char_key, patch in data["characters_merge"].items():
                if char_key in existing and isinstance(patch, dict):
                    existing[char_key].update(patch)
                elif isinstance(patch, dict):
                    existing[char_key] = patch
            sets.append("characters = ?")
            vals.append(json.dumps(existing))
            updated_fields.append("characters_merge")

        # Full characters replacement
        if "characters" in data and isinstance(data["characters"], dict):
            sets.append("characters = ?")
            vals.append(json.dumps(data["characters"]))
            updated_fields.append("characters")

        if not sets:
            return jsonify({"ok": True, "updated_fields": []})

        sets.append("updated_at = datetime('now')")
        vals.append(story_id)
        conn.execute(
            f"UPDATE stories SET {', '.join(sets)} WHERE id = ?",
            vals,
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "updated_fields": updated_fields})


@app.route("/internal/stories/<int:story_id>/diagnose", methods=["POST"])
def internal_diagnose_story(story_id):
    err = _require_internal_key()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    hours = data.get("hours", 48)
    target = data.get("target", "auto")
    character_id = data.get("character_id")

    conn = get_db()
    try:
        # Load story config
        story_row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        if not story_row:
            return jsonify({"error": "Story not found"}), 404

        # Load friction logs
        friction_rows = conn.execute(
            """SELECT * FROM friction_logs
               WHERE story_id = ? AND timestamp >= datetime('now', ?)
               ORDER BY timestamp DESC LIMIT 20""",
            (story_id, f"-{hours} hours"),
        ).fetchall()

        # Load recent game history from save
        save_row = conn.execute(
            "SELECT state FROM saves WHERE story_id = ? ORDER BY saved_at DESC LIMIT 1",
            (story_id,),
        ).fetchone()
    finally:
        conn.close()

    friction_list = [dict(r) for r in friction_rows]
    if not friction_list:
        return jsonify({
            "story_id": story_id,
            "friction_summary": {"total_events": 0, "by_type": {}},
            "diagnosis": "No friction events found in the last {} hours.".format(hours),
            "prescription": None,
            "requires_developer": False,
            "error_events": [],
        })

    # Summarize friction
    by_type = {}
    error_events = []
    for evt in friction_list:
        by_type[evt["event_type"]] = by_type.get(evt["event_type"], 0) + 1
        if evt["event_type"] == "error_500":
            error_events.append(evt)

    # Parse story config
    narrator_prompt = story_row["narrator_prompt"] or ""
    try:
        characters = json.loads(story_row["characters"] or "{}")
    except (json.JSONDecodeError, TypeError):
        characters = {}

    # Parse recent history
    history = []
    if save_row:
        try:
            save_state = json.loads(save_row["state"])
            history = (save_state.get("history") or [])[-10:]
        except (json.JSONDecodeError, TypeError):
            pass

    # Build character summary
    char_lines = []
    for key, ch in characters.items():
        prompt_preview = (ch.get("prompt") or "")[:200]
        moods = ch.get("moods") or []
        mood_str = ", ".join(f"{m.get('name','?')}={m.get('value','?')}" for m in moods) if moods else "none"
        char_lines.append(f"- {ch.get('label', key)}: prompt='{prompt_preview}...' moods=[{mood_str}]")

    # Build history summary
    hist_lines = []
    for i, turn in enumerate(history):
        if not isinstance(turn, dict):
            continue
        player = (turn.get("player") or "")[:100]
        narrator = (turn.get("narrator") or "")[:200]
        chars = turn.get("characters") or {}
        char_parts = []
        for ck, cv in chars.items():
            if isinstance(cv, dict):
                char_parts.append(f"{ck}: \"{(cv.get('dialogue') or '')[:80]}\"")
        hist_lines.append(f"Turn {i+1}: Player: {player}\n  Narrator: {narrator}")
        if char_parts:
            hist_lines.append(f"  Characters: {'; '.join(char_parts)}")

    # Build friction event details
    event_lines = []
    for evt in friction_list:
        if evt["event_type"] == "error_500":
            continue
        event_lines.append(
            f"- [{evt['event_type']}] player_input=\"{evt['player_input'][:80]}\" "
            f"context=\"{evt['context'][:150]}...\""
        )

    # Determine target hint
    target_hint = ""
    if target == "narrator":
        target_hint = "Focus your diagnosis on the narrator_prompt."
    elif target == "character" and character_id:
        target_hint = f"Focus your diagnosis on character '{character_id}'."

    meta_prompt = f"""You are an RPG game design analyst. Diagnose player experience problems and prescribe specific prompt improvements.

## Story Configuration
Title: {story_row['title']}
Genre: {story_row['genre']}
Tone: {story_row['tone'] or 'not set'}
Subgraph: {story_row['subgraph_name']}

## Current Narrator Prompt
{narrator_prompt}

## Characters
{chr(10).join(char_lines) if char_lines else 'No characters (narrator-only story)'}

## Player
Name: {story_row['player_name']}
Background: {story_row['player_background']}

## Recent Game History (last {len(history)} turns)
{chr(10).join(hist_lines) if hist_lines else 'No turns played yet'}

## Friction Events ({len(friction_list)} events in last {hours}h)
Counts by type: {json.dumps(by_type)}

### Event Details
{chr(10).join(event_lines) if event_lines else 'Only error_500 events (no player-facing friction)'}

{target_hint}

## Your Task
1. DIAGNOSE: Identify the root cause pattern. What about the current prompts or game configuration is causing these friction signals? Be specific — cite particular friction events and the narrator/character responses that preceded them.

2. PRESCRIBE: Write an improved prompt that addresses the diagnosed issue.
   - If the problem is with narration quality (empty_narrator, player_confused after narrator responses), fix the narrator_prompt.
   - If the problem is with a specific character's responses, fix that character's prompt.
   - Keep ALL existing instructions intact — only ADD or REFINE instructions that address the diagnosed issue.
   - The fix should be minimal and targeted, not a full rewrite.

3. If error_500 events are present, note them but do NOT try to fix them — they require developer attention to the code, not prompt changes.

Respond in this EXACT JSON format (no markdown fences, no extra text):
{{"diagnosis": "2-3 sentence explanation of the root cause pattern", "target": "narrator_prompt" or "character_prompt", "character_id": null or "character_key", "proposed_value": "the complete improved prompt text", "rationale": "1-2 sentences explaining what you changed and why", "confidence": "high" or "medium" or "low", "requires_developer": true or false}}"""

    # Call LLM
    try:
        llm = get_llm()
        raw = llm_result_to_text(llm.invoke(meta_prompt))
    except Exception as e:
        logger.exception("diagnose LLM call failed story_id=%s", story_id)
        return jsonify({"error": f"LLM call failed: {e}"}), 500

    # Parse JSON response
    prescription = None
    diagnosis_text = raw
    try:
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
        diagnosis_text = parsed.get("diagnosis", raw)
        current_value = ""
        if parsed.get("target") == "narrator_prompt":
            current_value = narrator_prompt
        elif parsed.get("target") == "character_prompt" and parsed.get("character_id"):
            ch = characters.get(parsed["character_id"]) or {}
            current_value = ch.get("prompt", "")
        prescription = {
            "target": parsed.get("target", "narrator_prompt"),
            "character_id": parsed.get("character_id"),
            "current_value": current_value,
            "proposed_value": parsed.get("proposed_value", ""),
            "rationale": parsed.get("rationale", ""),
            "confidence": parsed.get("confidence", "medium"),
        }
        if parsed.get("requires_developer"):
            pass  # handled below
    except (json.JSONDecodeError, KeyError):
        logger.warning("diagnose: LLM returned non-JSON for story_id=%s", story_id)

    return jsonify({
        "story_id": story_id,
        "friction_summary": {
            "total_events": len(friction_list),
            "by_type": by_type,
            "has_errors": bool(error_events),
        },
        "diagnosis": diagnosis_text,
        "prescription": prescription,
        "requires_developer": bool(error_events),
        "error_events": error_events[:5],
    })


# ---------------------------------------------------------------------------
# Friction log query routes
# ---------------------------------------------------------------------------

@app.route("/internal/logs/friction", methods=["GET"])
def internal_friction_logs():
    err = _require_internal_key()
    if err:
        return err
    hours = int(request.args.get("hours", 48))
    story_id = request.args.get("story_id")
    conn = get_db()
    try:
        if story_id:
            rows = conn.execute(
                """SELECT * FROM friction_logs
                   WHERE timestamp >= datetime('now', ?)
                   AND story_id = ?
                   ORDER BY timestamp DESC LIMIT 200""",
                (f"-{hours} hours", int(story_id)),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM friction_logs
                   WHERE timestamp >= datetime('now', ?)
                   ORDER BY timestamp DESC LIMIT 200""",
                (f"-{hours} hours",),
            ).fetchall()
    finally:
        conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/internal/logs/errors", methods=["GET"])
def internal_error_logs():
    err = _require_internal_key()
    if err:
        return err
    hours = int(request.args.get("hours", 48))
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM friction_logs
               WHERE event_type = 'error_500'
               AND timestamp >= datetime('now', ?)
               ORDER BY timestamp DESC LIMIT 200""",
            (f"-{hours} hours",),
        ).fetchall()
    finally:
        conn.close()
    return jsonify([dict(r) for r in rows])


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
