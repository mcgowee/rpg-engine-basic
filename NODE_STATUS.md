# Node status

Registered nodes (`nodes/__init__.py` → `NODE_REGISTRY`) and their roles in the current engine.

| Node | Module | LLM? | Role |
|------|--------|------|------|
| **narrator** | `nodes/narrator.py` | Yes (creative) | Scene narration in second person; sets `_narrator_text` for downstream nodes. |
| **character_agent** | `nodes/character_agent.py` | Yes (dialogue) | Per-character dialogue + short physical action; fills `_character_responses`. |
| **response_builder** | `nodes/response_builder.py` | No | Builds `_bubbles` (narrator + character bubbles) for the play UI. |
| **scene_image** | `nodes/scene_image.py` | No* | Resolves sidebar scene art from gallery / generation context (`_scene_image`). |
| **mood** | `nodes/mood.py` | Yes (classification) | Updates character mood axes from the turn. |
| **condense** | `nodes/condense.py` | Yes (summarization) | Rolling memory summary for long-term context. |
| **memory** | `nodes/memory.py` | No | Appends structured turns to `history` and bumps `turn_count`. |

\*May trigger image workflows via existing integrations; no prose LLM in the node itself.

## Builtin subgraphs (graphs)

| Subgraph | Chain | Notes |
|----------|-------|-------|
| **narrator_chat** | `__start__` → narrator → character_agent → response_builder → scene_image → mood → condense → memory → `__end__` | Full pipeline. |
| **narrator_chat_lite** | `__start__` → narrator → character_agent → response_builder → memory → `__end__` | No mood, condense, or scene_image. |
| **chat_direct** | `__start__` → character_agent → response_builder → memory → `__end__` | No narrator node. |

Graphs use **`__start__` / `__end__` edges only** — there are no routers or `entry_point` in current definitions.

Older databases may still store legacy subgraph names until `db.migrate_schema()` maps them to `narrator_chat` or `narrator_chat_lite`.
