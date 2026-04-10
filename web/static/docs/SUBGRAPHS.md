# Subgraphs

A **subgraph** is the per-turn LangGraph pipeline (nodes + edges) that runs after the player sends a message. Builtin subgraphs live as JSON under `graphs/` and are synced into the database.

All current graphs start at **`__start__`** and end at **`__end__`** with simple edges — there is **no** router layer.

## Builtin subgraphs

| Name | Pipeline | Best for |
|------|----------|----------|
| **narrator_chat** | narrator → character_agent → response_builder → scene_image → mood → condense → memory | Full experience: bubbles, optional scene art in the sidebar, mood axes, rolling summary. |
| **narrator_chat_lite** | narrator → character_agent → response_builder → memory | Faster turns: dialogue bubbles + memory, no mood/condense/scene_image. |
| **chat_direct** | character_agent → response_builder → memory | No narrator — characters speak directly (still uses shared memory/history). |

## Choosing a subgraph

- **Solo or minimal cast, fast play:** `narrator_chat_lite`
- **Cast with mood axes and long campaigns:** `narrator_chat`
- **Pure character-driven chat without narrator prose:** `chat_direct` (you still define characters and prompts)

## Migrating old stories

`db.migrate_schema()` rewrites legacy subgraph names (e.g. `conversation`, `full_story`, `scene_chat`, …) to **`narrator_chat`** when the story has characters, otherwise **`narrator_chat_lite`**.
