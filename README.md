# RPG Engine

**Copyright (c) 2026 Earl McGowen. All Rights Reserved.**

This is proprietary software. See [LICENSE](LICENSE) for terms. See [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) for platform usage terms.

---

A **text RPG authoring and play platform**: authors define stories (opening, narrator instructions, player, NPCs), pick a **conversation subgraph** (LangGraph), and players chat turn-by-turn with LLM-backed narration, optional NPC lines, mood tracking, and rolling memory summaries. A **SvelteKit** front end proxies to a **Flask** API; state lives in **SQLite** with optional **ComfyUI** image generation for covers, portraits, and scene art.

## What you can do

- **Register / log in** — session cookies; passwords hashed with bcrypt.
- **Stories** — create, edit, publish, copy, export/import JSON; builtin sample stories ship from `stories/*.json`.
- **Subgraphs** — JSON LangGraph definitions in `graphs/*.json` seed as builtin templates; users can add custom subgraphs (validated, compiled, cached in memory).
- **Play** — start a session, send messages through the story’s `subgraph_name`, autosave to slot 0, manual save/load slots, pause.
- **Books** — turn play history into polished prose via LLM and save edited “books.”
- **Graphs UI** — edit subgraph JSON and design **main graph templates**. Stories can attach a template (`main_graph_template_id`); play then runs phased subgraphs with transitions (turns, milestone text in the player message, manual phrase, `location` state key, or `_rules_transition`). Otherwise the story’s single `subgraph_name` is used—see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **AI assist** — generate story drafts from a concept, improve fields, suggestions (titles, names, mood axes), generate book prose.
- **Images** (optional) — ComfyUI endpoints for cover, portrait (LLM → visual prompt), and scene images.

## Repository layout

| Path | Role |
|------|------|
| `app.py` | Flask app: auth, CRUD, `/play/*`, `/ai/*`, graph registry metadata |
| `db.py` | SQLite schema, WAL, seeds builtins; `sync_builtin_subgraphs_from_disk()` reapplies `graphs/*.json` to builtin rows on startup |
| `config.py` | `.env` loading, Flask/LLM paths |
| `auth.py` | bcrypt + `login_required` |
| `graphs/` | JSON subgraph definitions, `builder.py` (LangGraph), `registry.py` (compile cache) |
| `nodes/` | Runnable nodes: narrator, memory, condense, npc, mood |
| `routers/` | Conditional edge functions for graph entry and post-narrator routing |
| `llm/` | `get_llm()` → Ollama or Azure OpenAI |
| `stories/` | Builtin public story JSON for first-time DB seed |
| `web/` | SvelteKit (adapter-node); `/api/*` proxies to Flask (`FLASK_API_URL`) |
| `deploy/` | systemd units, VPS setup notes |
| `deploy.sh` | pull, `pip install`, `npm ci` + `build`, restart services |

## Requirements

- Python 3.11+ (project uses modern typing)
- Node.js 20+ for `web/`

Dependencies: see `requirements.txt` (Flask, LangGraph/LangChain, bcrypt, gunicorn, etc.).

## Configuration

Environment variables are read in `config.py` (via `python-dotenv`). Common ones:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing (set in production) |
| `FLASK_HOST`, `FLASK_PORT` | API bind (default `0.0.0.0:5051`) |
| `FLASK_DEBUG` | `1` / `true` for debug |
| `LLM_PROVIDER` | `ollama` (default) or `azure` |
| `DEFAULT_MODEL` | Model id / deployment name |
| `OLLAMA_HOST` | Ollama base URL |
| `AZURE_*` | Azure OpenAI when `LLM_PROVIDER=azure` |
| `SAVE_SLOTS` | Number of save slots per story/user |
| `GAME_SESSION_CACHE_TTL_S` | In-memory play cache TTL (default 86400); entries expire and reload from SQLite |
| `GAME_SESSION_CACHE_MAX` | Max cached sessions (default 512); set `0` to disable cache (e.g. multiple gunicorn workers) |
| `RATE_LIMIT_PLAY_CHAT`, `RATE_LIMIT_AI` | Flask-Limiter strings (e.g. `60 per minute`); empty disables that group |
| `PROMPT_HISTORY_ENTRY_MAX_CHARS` | Cap each raw history line in the narrator prompt (default 1800; `0` = off) |
| `PROMPT_NPC_NARRATOR_BEAT_MAX_CHARS` | Cap “what the narrator established” in the NPC prompt (default 2800; `0` = off) |
| `PROMPT_NPC_HISTORY_CONTEXT_MAX_CHARS` | Cap each history line in the NPC prompt (default 1800; `0` = use narrator cap) |
| `COMFYUI_URL` | Used by `comfyui_client.py` (default in code may be LAN-specific—override locally) |

SvelteKit server uses `FLASK_API_URL` (default `http://127.0.0.1:5051`) to reach Flask.

## Local development

```bash
cd /path/to/rpg-engine-basic
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional: copy or create .env with LLM and SECRET_KEY settings
python app.py
```

In another terminal:

```bash
cd web
npm install
npm run dev
```

Open the dev URL Vite prints (often `http://localhost:5173`). API calls go to `/api/...` on the Kit server, which proxies to Flask.

## Production deploy (summary)

`deploy.sh` expects an app tree at `/var/www/rpg-engine`, a venv, and systemd units `rpg-flask` / `rpg-web` (see `deploy/`). Flask runs behind gunicorn; the Node adapter serves the built Kit app.

## Further reading

- [docs/INDEX.md](docs/INDEX.md) — map of repo docs vs in-app `/docs` pages.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — graph model, play flow, main graph phases, API boundaries.
- [docs/SUBGRAPHS.md](docs/SUBGRAPHS.md) — builtin subgraph pipelines and routing (mirrored under `web/static/docs/` for the web app).
- [docs/BUILTIN_STORIES.md](docs/BUILTIN_STORIES.md) — seed stories table (subgraph, genre, filenames).
- [NODE_STATUS.md](NODE_STATUS.md) — implemented nodes and builtins snapshot.
- [NODE_ROADMAP.md](NODE_ROADMAP.md) — node ideas and future work.
- [SECURITY.md](SECURITY.md) — trust boundaries, rate limits, production cookies.
- [LICENSE](LICENSE) — Proprietary license, all rights reserved.
- [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) — Platform usage terms.
- [deploy/](deploy/) — systemd and VPS notes (see also `deploy.sh`).
