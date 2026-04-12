# Documentation index

What lives where in this repository and how it relates to the **in-app** guides (`/docs/*` in the SvelteKit app).

## In-app guides (SvelteKit)

| URL | Topic |
|-----|--------|
| `/docs` | Hub — links to all guides |
| `/docs/playing` | Browsing, play UI, saves, moods (player-facing) |
| `/docs/stories` | Story Editor, characters, subgraph field, **builtin stories table** |
| `/docs/engine` | Nodes, edges, state, builtin graphs (author / builder) |
| `/docs/subgraphs` | Builtin subgraph comparison tables and picker |

The app also serves a copy of **SUBGRAPHS.md** at `/docs/SUBGRAPHS.md` (from `web/static/docs/SUBGRAPHS.md`) for quick raw viewing.

## Repository markdown (`docs/` and repo root)

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Flask ↔ SvelteKit, LangGraph, play flow, main graph phases, ComfyUI |
| [GRAPHS.md](GRAPHS.md) | Full architecture survey: every graph definition, node roles, mermaid diagrams, comparison table |
| [SUBGRAPHS.md](SUBGRAPHS.md) | Builtin subgraph reference (keep in sync with `web/static/docs/SUBGRAPHS.md`) |
| [BUILTIN_STORIES.md](BUILTIN_STORIES.md) | Builtin seed stories: subgraph, genre, filenames |
| [IMAGE_ASSET_BACKLOG.md](IMAGE_ASSET_BACKLOG.md) | Planned/generated image assets for the web UI |
| [../NODE_STATUS.md](../NODE_STATUS.md) | Implemented nodes, builtin subgraphs |
| [../NODE_ROADMAP.md](../NODE_ROADMAP.md) | Future nodes and features (not yet built) |
| [../README.md](../README.md) | Setup, env vars, layout of the repo |
| [../SECURITY.md](../SECURITY.md) | Operational security notes |
| [../MODEL_STRATEGY.md](../MODEL_STRATEGY.md) | LLM / model selection notes |

## When to update what

- **Change a builtin graph** (`graphs/*.json`) → update `docs/GRAPHS.md`, `docs/SUBGRAPHS.md`, `web/static/docs/SUBGRAPHS.md`, and verify `/docs/engine` and `/docs/subgraphs` copy on the site.
- **Add or change a builtin story** (`stories/*.json`) → update `docs/BUILTIN_STORIES.md` and the table on `/docs/stories#builtin-stories`.
- **Add or rename a node** → update `nodes/__init__.py`, Flask `app.py` registry descriptions if any, `NODE_STATUS.md`, and the Engine Reference (loaded from API).
- **Change play / saves / env** → `README.md`, `docs/ARCHITECTURE.md`, and player docs as needed.

## Ideas for future documentation

- **Main graph templates** — a walkthrough with a sample template (phases, transitions, when `_rules_transition` fires) beyond the summary in [ARCHITECTURE.md](ARCHITECTURE.md).
- **Contributor guide** — local dev, `pytest`, `npm run check`, how graph JSON is validated (`tests/test_graph_validate.py`).
- **Operations** — backing up `rpg.db`, production cookies / HTTPS, and when to set `GAME_SESSION_CACHE_MAX=0` for multiple gunicorn workers (see [README.md](../README.md)).
