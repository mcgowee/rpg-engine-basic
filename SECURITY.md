# Security notes

## Trust boundaries

- **Subgraph definitions** are JSON stored in the database and compiled into LangGraph graphs. They may only reference **registered node names** (`validate_graph_definition`), which limits arbitrary code execution. Still, treat **public subgraphs** and **public main graph templates** as content from trusted authors only: a malicious author could craft prompts-heavy graphs that increase LLM cost or produce unwanted output.

- **Stories** include narrator prompts, character prompts, and optional notes. These strings are sent to the LLM as instructions. Users who can publish **public** stories can influence what visitors’ LLM sessions do (within the game’s prompt structure).

- **Session cookies** protect account actions. In production, set a strong `SECRET_KEY`, serve over HTTPS, and enable `SESSION_COOKIE_SECURE` when appropriate.

## Rate limiting

- `Flask-Limiter` applies per-route limits using **user id** when logged in, otherwise **client IP**. Tune with `RATE_LIMIT_PLAY_CHAT` and `RATE_LIMIT_AI` (empty string disables that route group’s limit). For multiple app processes, switch Limiter to Redis or another shared storage (see [Flask-Limiter docs](https://flask-limiter.readthedocs.io/)).

## Operational

- **ComfyUI** and **Ollama/Azure** endpoints should not be exposed to untrusted networks without authentication; the Flask app assumes they are reachable only from trusted infrastructure.

- **`/health`** is unauthenticated for load balancers; it returns database and (for Ollama) upstream status only.

## API surface (high level)

Session-protected JSON APIs live in `app.py` (proxied as `/api/*` from SvelteKit). Examples: **`/me`**, **`/subgraphs`**, **`/stories`**, **`/play/start`**, **`/play/chat`**, **`/play/status`**, **`/settings/models`**, **`/graph-registry`**, **`/ai/*`** assist routes, and image routes under **`/ai/generate-*`**. There is **no** router registry in API responses — `graph-registry` returns node metadata and empty router maps for compatibility.
