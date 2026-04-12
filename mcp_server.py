#!/usr/bin/env python3
"""
RPG Platform MCP Server
=======================
Exposes the Flask RPG API as tools that Claude Code / Cursor can call
directly during coding sessions.

HOW MCP WORKS (the 60-second version):
  - The IDE launches this script as a subprocess (via settings config)
  - This process communicates over stdin/stdout using JSON-RPC 2.0
  - On startup, the IDE sends `initialize` then `tools/list`
  - This server responds with a list of tools (functions with schemas)
  - When the agent decides to use a tool, the IDE sends `tools/call`
  - We execute the call (HTTP request to Flask) and return the result

Install: pip install mcp httpx
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
from typing import Any

import httpx

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FLASK_BASE_URL = os.getenv("RPG_FLASK_URL", "http://localhost:5050")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
REQUEST_TIMEOUT = 120.0
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python3")
DB_PATH = os.path.join(PROJECT_DIR, "rpg.db")

_flask_proc: subprocess.Popen | None = None


# ---------------------------------------------------------------------------
# HTTP client — uses /internal/ routes with static API key
# ---------------------------------------------------------------------------

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=FLASK_BASE_URL,
            timeout=REQUEST_TIMEOUT,
            headers={"X-Internal-Key": INTERNAL_API_KEY},
        )
    return _client


async def flask_get(path: str, params: dict | None = None) -> Any:
    client = _get_client()
    resp = await client.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


async def flask_post(path: str, body: dict) -> Any:
    client = _get_client()
    resp = await client.post(path, json=body)
    resp.raise_for_status()
    return resp.json()


async def flask_patch(path: str, body: dict) -> Any:
    client = _get_client()
    resp = await client.patch(path, json=body)
    resp.raise_for_status()
    return resp.json()

# ---------------------------------------------------------------------------
# Flask server lifecycle
# ---------------------------------------------------------------------------

async def _restart_flask_server(keep_db: bool = False) -> dict:
    """Kill old Flask, optionally wipe DB, start fresh."""
    global _flask_proc, _client

    # Kill existing process
    if _flask_proc and _flask_proc.poll() is None:
        _flask_proc.terminate()
        try:
            _flask_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _flask_proc.kill()
            _flask_proc.wait()

    # Also kill any stray Flask on our port
    try:
        result = subprocess.run(
            ["fuser", "-k", FLASK_BASE_URL.split(":")[-1] + "/tcp"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass

    await asyncio.sleep(1)

    # Reset HTTP client so new requests get a fresh connection
    if _client:
        await _client.aclose()
        _client = None

    # Optionally wipe DB
    if not keep_db and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # Start Flask
    env = {**os.environ, "INTERNAL_API_KEY": INTERNAL_API_KEY}
    _flask_proc = subprocess.Popen(
        [VENV_PYTHON, os.path.join(PROJECT_DIR, "app.py")],
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to become ready
    for attempt in range(15):
        await asyncio.sleep(1)
        try:
            client = _get_client()
            resp = await client.get("/internal/health")
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "pid": _flask_proc.pid,
                    "db_wiped": not keep_db,
                    "health": resp.json(),
                }
        except Exception:
            continue

    return {"ok": False, "error": "Server did not become healthy within 15s"}


# ---------------------------------------------------------------------------
# Create the MCP Server instance
# ---------------------------------------------------------------------------
app = Server("rpg-platform")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    # --- Read tools ---
    Tool(
        name="rpg_get_server_health",
        description=(
            "Check whether the Flask RPG server is reachable and healthy. "
            "Returns server version, uptime, DB path, and Ollama connection status. "
            "Run this first when debugging connection issues."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="rpg_list_sessions",
        description=(
            "List all active RPG game sessions on the local Flask server. "
            "Returns session IDs, game titles, and player names. "
            "Use this first to discover which session_id to pass to other tools."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="rpg_get_game_state",
        description=(
            "Get the full current game state for a session: current scene, "
            "player stats, inventory, active NPCs, and last narrator output. "
            "Use this to understand where a game session stands before editing code."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID from rpg_list_sessions.",
                }
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="rpg_get_character",
        description=(
            "Get detailed info about a specific character in a game session: "
            "prompt, moods, model, and first_line. Pass the character's key "
            "(e.g. 'emma', 'barkeep') from the story's character dict."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID (story ID) from rpg_list_sessions.",
                },
                "character_id": {
                    "type": "string",
                    "description": "Character key, e.g. 'emma' or 'taylor'.",
                },
            },
            "required": ["session_id", "character_id"],
        },
    ),
    Tool(
        name="rpg_query_memory",
        description=(
            "Get the AI memory summary and recent history for a game session. "
            "Returns the rolling memory_summary and the last N history entries. "
            "Useful for verifying that memory/condense nodes are working correctly."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID (story ID) from rpg_list_sessions.",
                },
                "last_n": {
                    "type": "integer",
                    "description": "How many recent history entries to return (default 5).",
                    "default": 5,
                },
            },
            "required": ["session_id"],
        },
    ),

    # --- Action tools ---
    Tool(
        name="rpg_send_player_action",
        description=(
            "Send a player action to the LangGraph narrative engine and get the "
            "narrator's response. Use this to test the full graph pipeline (narrator -> "
            "mood -> npc -> memory nodes) without opening Open WebUI. "
            "Great for integration testing after modifying a graph node."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "description": "The player's action text, e.g. 'I ask Vera about the missing briefcase.'",
                },
            },
            "required": ["session_id", "action"],
        },
    ),

    # --- Story management tools ---
    Tool(
        name="rpg_create_story",
        description=(
            "Create a new RPG story on the server. Returns the new story ID. "
            "After creating, use rpg_start_game to initialize a playable session."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Story title (required)."},
                "description": {"type": "string", "description": "Short story description."},
                "genre": {"type": "string", "description": "Genre, e.g. 'thriller', 'romance'."},
                "tone": {"type": "string", "description": "Tone, e.g. 'dark, suspenseful'."},
                "characters": {
                    "type": "object",
                    "description": "Character definitions dict. Each key is a slug, value has prompt, first_line, model, moods.",
                },
                "map": {
                    "type": "object",
                    "description": "Map/location data for quest stories. Has start, order, locations keys.",
                },
                "subgraph_name": {
                    "type": "string",
                    "description": "LangGraph subgraph: narrator_chat_lite, narrator_chat, narrator_chat_quest, etc.",
                },
                "opening": {"type": "string", "description": "Opening narration text shown before first turn."},
                "narrator_prompt": {"type": "string", "description": "Custom system prompt for the narrator."},
                "player_name": {"type": "string", "description": "Player character name (default: Adventurer)."},
                "player_background": {"type": "string", "description": "Player character background text."},
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="rpg_start_game",
        description=(
            "Start a game session for a story. Initializes game state, creates a save, "
            "and returns the session_id needed for rpg_send_player_action. "
            "Must be called after rpg_create_story before playing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "story_id": {
                    "type": "integer",
                    "description": "Story ID from rpg_create_story or rpg_list_sessions.",
                },
            },
            "required": ["story_id"],
        },
    ),
    Tool(
        name="rpg_reset_game",
        description=(
            "Reset a game session: deletes all saves and cache, re-initializes from "
            "the story definition. Returns a fresh session_id. Use this to test from "
            "scratch after code changes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "story_id": {
                    "type": "integer",
                    "description": "Story ID to reset.",
                },
            },
            "required": ["story_id"],
        },
    ),
    Tool(
        name="rpg_restart_server",
        description=(
            "Restart the Flask RPG server with a fresh database. Kills the old "
            "process, deletes rpg.db, and starts app.py. Use after code changes "
            "to pick up new routes or node logic."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "keep_db": {
                    "type": "boolean",
                    "description": "If true, keep the existing database instead of deleting it. Default false.",
                    "default": False,
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="rpg_get_story_config",
        description=(
            "Get the full editable configuration for a story: narrator_prompt, "
            "characters (with prompts and moods), opening, player_background, etc. "
            "Use this to inspect what the LLM sees before diagnosing issues."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "story_id": {"type": "integer", "description": "Story ID."},
            },
            "required": ["story_id"],
        },
    ),
    Tool(
        name="rpg_diagnose_friction",
        description=(
            "Analyze friction logs for a story and generate a diagnosis + proposed fix. "
            "The LLM examines friction patterns, current prompts, and recent game history "
            "to produce a specific prompt improvement. Returns both the diagnosis and "
            "a proposed new prompt value. Does NOT auto-apply — use rpg_patch_story to apply."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "story_id": {"type": "integer", "description": "Story ID to diagnose."},
                "hours": {"type": "integer", "description": "Lookback hours (default 48).", "default": 48},
                "target": {
                    "type": "string",
                    "enum": ["narrator", "character", "auto"],
                    "description": "Which prompt to diagnose. 'auto' lets the LLM decide.",
                    "default": "auto",
                },
                "character_id": {
                    "type": "string",
                    "description": "Character key — required if target is 'character'.",
                },
            },
            "required": ["story_id"],
        },
    ),
    Tool(
        name="rpg_patch_story",
        description=(
            "Update specific fields of a story config. Only fields you include will "
            "be changed — everything else stays the same. Changes take effect on the "
            "next player turn without restart. Use characters_merge to update a single "
            "character's prompt without replacing all characters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "story_id": {"type": "integer", "description": "Story ID to update."},
                "narrator_prompt": {"type": "string", "description": "New narrator system prompt."},
                "characters_merge": {
                    "type": "object",
                    "description": "Partial character updates. Keys are character slugs, values are dicts to merge.",
                },
                "opening": {"type": "string"},
                "player_background": {"type": "string"},
                "player_name": {"type": "string"},
            },
            "required": ["story_id"],
        },
    ),
    Tool(
        name="rpg_get_friction_logs",
        description=(
            "Get recent friction log entries — signals of player confusion, "
            "empty narrator responses, repeated inputs, and errors. "
            "Use this to diagnose gameplay quality issues."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look-back window in hours (default 48).",
                    "default": 48,
                },
                "story_id": {
                    "type": "integer",
                    "description": "Optional: filter to a specific story.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="rpg_get_error_logs",
        description=(
            "Get recent 500-error friction logs with tracebacks. "
            "Use this to find and debug server errors."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look-back window in hours (default 48).",
                    "default": 48,
                },
            },
            "required": [],
        },
    ),
]


# ---------------------------------------------------------------------------
# Handle tools/list
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


# ---------------------------------------------------------------------------
# Handle tools/call
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        text = json.dumps(result, indent=2, ensure_ascii=False)

    except httpx.ConnectError:
        text = json.dumps({
            "error": "Cannot reach Flask RPG server",
            "hint": f"Is it running at {FLASK_BASE_URL}? Try: python app.py",
            "tool": name,
        }, indent=2)

    except httpx.HTTPStatusError as exc:
        text = json.dumps({
            "error": f"HTTP {exc.response.status_code}",
            "body": exc.response.text[:500],
            "tool": name,
            "url": str(exc.request.url),
        }, indent=2)

    except Exception as exc:
        text = json.dumps({
            "error": type(exc).__name__,
            "detail": str(exc),
            "tool": name,
        }, indent=2)

    return [TextContent(type="text", text=text)]


async def _dispatch(name: str, args: dict) -> Any:

    # --- Read tools ---

    if name == "rpg_get_server_health":
        return await flask_get("/internal/health")

    elif name == "rpg_list_sessions":
        return await flask_get("/internal/stories")

    elif name == "rpg_get_game_state":
        sid = args["session_id"]
        return await flask_get(f"/internal/stories/{sid}/state")

    elif name == "rpg_get_character":
        sid = args["session_id"]
        char_key = args["character_id"]
        state = await flask_get(f"/internal/stories/{sid}/state")
        characters = state.get("characters") or {}
        char_data = characters.get(char_key)
        if char_data is None:
            # Check _all_characters for quest stories where character may not be active
            all_chars = state.get("_all_characters") or characters
            char_data = all_chars.get(char_key)
        if char_data is None:
            return {"error": f"Character '{char_key}' not found in session {sid}"}
        return {"character_id": char_key, **char_data}

    elif name == "rpg_query_memory":
        sid = args["session_id"]
        last_n = args.get("last_n", 5)
        state = await flask_get(f"/internal/stories/{sid}/state")
        history = state.get("history") or []
        return {
            "memory_summary": state.get("memory_summary", ""),
            "turn_count": state.get("turn_count", 0),
            "recent_history": history[-last_n:] if history else [],
        }

    # --- Action tools ---

    elif name == "rpg_send_player_action":
        sid = args["session_id"]
        return await flask_post(f"/internal/stories/{sid}/chat", {
            "message": args["action"],
        })

    # --- Story management tools ---

    elif name == "rpg_create_story":
        body = {k: v for k, v in args.items() if v is not None}
        return await flask_post("/internal/stories", body)

    elif name == "rpg_start_game":
        story_id = args["story_id"]
        return await flask_post(f"/internal/stories/{story_id}/start", {})

    elif name == "rpg_reset_game":
        story_id = args["story_id"]
        return await flask_post(f"/internal/stories/{story_id}/reset", {})

    # --- Self-improvement pipeline ---

    elif name == "rpg_get_story_config":
        story_id = args["story_id"]
        return await flask_get(f"/internal/stories/{story_id}/config")

    elif name == "rpg_diagnose_friction":
        story_id = args["story_id"]
        body = {k: v for k, v in args.items() if k != "story_id" and v is not None}
        return await flask_post(f"/internal/stories/{story_id}/diagnose", body)

    elif name == "rpg_patch_story":
        story_id = args["story_id"]
        body = {k: v for k, v in args.items() if k != "story_id" and v is not None}
        return await flask_patch(f"/internal/stories/{story_id}", body)

    # --- Server management ---

    elif name == "rpg_restart_server":
        return await _restart_flask_server(keep_db=args.get("keep_db", False))

    # --- Friction log tools ---

    elif name == "rpg_get_friction_logs":
        params = {"hours": args.get("hours", 48)}
        if "story_id" in args:
            params["story_id"] = args["story_id"]
        return await flask_get("/internal/logs/friction", params=params)

    elif name == "rpg_get_error_logs":
        params = {"hours": args.get("hours", 48)}
        return await flask_get("/internal/logs/errors", params=params)

    else:
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
