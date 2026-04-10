# Architecture

This document describes how **RPG Engine Basic** is structured: LangGraph **subgraphs**, **runtime state**, the **Flask API**, and how the **SvelteKit** client talks to the backend.

## System overview

```mermaid
flowchart LR
  Browser --> SvelteKit
  SvelteKit -->|"/api/* proxy, cookies"| Flask
  Flask --> SQLite
  Flask --> OllamaOrAzure["LLM (Ollama / Azure)"]
  Flask -.->|optional| ComfyUI
```

- **SvelteKit** (`web/`) is the user-facing app. Routes under `web/src/routes/api/[...path]/+server.ts` forward requests to Flask using `web/src/lib/server/flask.ts`, forwarding `Cookie` and relaying `Set-Cookie` so session auth works through the proxy.
- **Flask** (`app.py`) owns all business logic: users, stories, subgraphs, saves, play orchestration, and AI/image endpoints.
- **SQLite** (`rpg.db`, path in `db.py`) stores persistent data; compiled subgraphs are also held in an in-memory **registry** after load.

## Conversation engine: subgraphs (LangGraph)

A **subgraph** is a JSON document validated by `graphs/builder.py::validate_graph_definition` and compiled with **LangGraph**’s `StateGraph`. Edges use **`__start__`** and **`__end__`** only (no routers).

### State shape

The shared `State` `TypedDict` in `graphs/builder.py` defines the fields graphs expect, including:

- **Player input / output:** `message`, `response`
- **Memory:** `history` (structured turn dicts: player, narrator, per-character dialogue/action, mood snapshot), `memory_summary` (LLM-compressed summary)
- **Story context:** `narrator` (`prompt`, `model`), `player`, `characters`, `story` (genre, tone, NSFW metadata, etc.), `game_title`, `opening`, `paused`, `turn_count`
- **UI payload:** `_bubbles` (narrator + character bubbles), `_scene_image`, `_active_portraits`, `_narrator_text`, `_character_responses`

At runtime, `app.py` adds keys such as `_story_id` and `_subgraph_name` for bookkeeping.

### Nodes (`nodes/`)

Registered in `nodes/__init__.py` as `NODE_REGISTRY`:

| Node | LLM? | Role |
|------|------|------|
| `narrator` | Yes | Main scene narration; sets `_narrator_text` |
| `character_agent` | Yes | Per-character dialogue + short action → `_character_responses` |
| `response_builder` | No | Builds `_bubbles` for the play UI |
| `scene_image` | No* | Sidebar scene / gallery image selection |
| `mood` | Yes | Updates character mood axes |
| `condense` | Yes | Refreshes `memory_summary` from structured `history` |
| `memory` | No | Appends structured turns, updates `turn_count` |

\*May integrate ComfyUI; no prose LLM inside the node.

### Registry

`graphs/registry.py` loads subgraph rows, parses JSON, compiles, and caches. CRUD routes in `app.py` call `reload_one` / `remove` so the cache stays consistent. **Play** uses `registry.require(state["_subgraph_name"])` after checking `name in registry`.

## Play flow

1. **`POST /play/start`** — Builds state, applies main-graph phase 0 when `main_graph_template_id` is set (`play_phases`), optionally pre-fills `response` with `opening`, stores the session in **`GameSessionCache`** (LRU + TTL; `GAME_SESSION_CACHE_MAX=0` disables and forces DB reload each time), upserts slot 0, increments `play_count`.
2. **`POST /play/chat`** — Per-session lock, `registry.require(...).invoke(state)`, history merge, **`advance_phase_after_turn`**, persist slot 0. Response includes `bubbles`, `scene_image`, and related fields for the multi-bubble UI. Rate-limited via `RATE_LIMIT_PLAY_CHAT`.
3. **`GET /play/status`**, **`POST /play/save|load`**, pause/unpause — same cache + `_ensure_play_session` / `hydrate_runtime_from_story_save` so template-based saves keep `_subgraph_name`.

Concurrency: `threading.Lock` per `session_{story_id}_{user_id}` avoids overlapping LLM turns for the same adventure.

**`/health`** — DB `SELECT 1`; if `LLM_PROVIDER=ollama`, probes `OLLAMA_HOST/api/tags`.

## Stories and seed data

- **DB table `stories`** holds flat columns plus JSON `characters` (personalities, mood axes, portraits, variant rules, etc.).
- **`db.py::seed_builtin_stories`** imports `stories/*.json` once per title for the synthetic `system` user and marks them public.
- **`seed_builtin_subgraphs`** imports `graphs/*.json` as builtin subgraphs (same `system` user).

## Main graph templates (phases)

The **`main_graph_templates`** table and UI (`web/src/routes/graphs/main/+page.svelte`) let authors define ordered **phases**, each referencing a **subgraph name** and a **transition** (`milestone`, `rules`, `turns`, `location`, `manual`) with a string `condition`.

**Main graph in play:** If `stories.main_graph_template_id` is set, `play_phases.apply_main_graph_to_new_state` initializes `_phase_index`, `_turns_in_phase`, and `_subgraph_name` from the first phase. After each `/play/chat` turn, `advance_phase_after_turn` may advance the phase when the template’s `transition` matches. If the column is null, play uses `stories.subgraph_name` only.

## AI and images

- **LLM** — `llm/__init__.py::get_llm` selects `OllamaProvider` or `AzureProvider` from `LLM_PROVIDER`.
- **Text assist** — `/ai/generate-story`, `/ai/improve-text`, `/ai/suggest`, `/ai/generate-book` build prompts and parse or return plain text.
- **ComfyUI** — `comfyui_client.py` queues a fixed workflow template; `is_available()` checks `COMFYUI_URL`. Cover/portrait/scene routes write PNGs under `web/static/images/{covers,portraits,scenes}/`.

## Security notes (operational)

- Use a strong `SECRET_KEY` in production; enable `SESSION_COOKIE_SECURE` when serving HTTPS.
- Subgraphs are Python-callable graphs: only trusted users should publish arbitrary graph JSON (same trust model as any code-adjacent config).

## Related files

| Concern | Location |
|---------|----------|
| API surface | `app.py` |
| Schema + seeds | `db.py` |
| Graph compile | `graphs/builder.py`, `graphs/registry.py` |
| Node behavior | `nodes/*.py` |
| Frontend proxy | `web/src/lib/server/flask.ts`, `web/src/routes/api/[...path]/+server.ts` |

## Other docs

- [docs/SUBGRAPHS.md](SUBGRAPHS.md) — builtin subgraph comparison.
- [NODE_STATUS.md](../NODE_STATUS.md) — nodes and builtins snapshot.
- [docs/INDEX.md](INDEX.md) — list of documentation in this repo.
