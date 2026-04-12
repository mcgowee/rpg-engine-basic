# Node status

Registered nodes (`nodes/__init__.py` → `NODE_REGISTRY`) and their roles in the current engine.

| Node | Module | LLM? | Role |
|------|--------|------|------|
| **progression** | `nodes/progression.py` | Optional (classification) | Stage gates (turns, mood thresholds, optional criteria check). Writes `_progression`, `_progression_state`, `_narrator_progression`. |
| **narrator** | `nodes/narrator.py` | Yes (creative) | Scene narration in second person; sets `_narrator_text` for downstream nodes. |
| **character_agent** | `nodes/character_agent.py` | Yes (dialogue) | Per-character dialogue + short physical action; fills `_character_responses`. |
| **response_builder** | `nodes/response_builder.py` | No | Builds `_bubbles` (narrator + character bubbles) for the play UI. |
| **mood** | `nodes/mood.py` | Yes (classification) | Updates character mood axes from the turn. |
| **expression_picker** | `nodes/expression_picker.py` | Yes (classification) | Picks portrait variant per character from `portraits` → `_active_portraits`. |
| **scene_image** | `nodes/scene_image.py` | No* | Resolves sidebar scene art from gallery / generation context (`_scene_image`). |
| **condense** | `nodes/condense.py` | Yes (summarization) | Rolling memory summary for long-term context. |
| **memory** | `nodes/memory.py` | No | Appends structured turns to `history` and bumps `turn_count`. |

\*May trigger image workflows via existing integrations; no prose LLM in the node itself.

## Builtin subgraphs (graphs)

| Subgraph | Chain | Notes |
|----------|-------|-------|
| **narrator_chat** | `__start__` → narrator → character_agent → response_builder → mood → expression_picker → scene_image → condense → memory → `__end__` | Full pipeline with LLM portrait picking. |
| **narrator_chat_classic** | `__start__` → narrator → character_agent → response_builder → mood → scene_image → condense → memory → `__end__` | Like full but no expression_picker (static portraits). |
| **narrator_chat_progression** | `__start__` → progression → narrator → … (same as narrator_chat) → `__end__` | Stage-gated NPC arcs prepended to the full pipeline. |
| **narrator_chat_lite** | `__start__` → narrator → character_agent → response_builder → memory → `__end__` | No mood, condense, expression_picker, or scene_image. |
| **chat_direct** | `__start__` → character_agent → response_builder → memory → `__end__` | No narrator node. |

Graphs use **`__start__` / `__end__` edges only** — there are no routers or `entry_point` in current definitions.

Older databases may still store legacy subgraph names until `db.migrate_schema()` maps them to `narrator_chat` or `narrator_chat_lite`.

For full architecture details and mermaid diagrams, see [`docs/GRAPHS.md`](docs/GRAPHS.md).
