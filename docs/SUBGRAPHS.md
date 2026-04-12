# Subgraphs

A **subgraph** is the per-turn LangGraph pipeline (nodes + edges) that runs after the player sends a message. Builtin subgraphs live as JSON under `graphs/` and are synced into the database.

All current graphs start at **`__start__`** and end at **`__end__`** with simple edges — there is **no** router layer.

For node-by-node behavior and diagrams, see **[GRAPHS.md](GRAPHS.md)**.

## Builtin subgraphs

| Name | Pipeline | Best for |
|------|----------|----------|
| **narrator_chat** | narrator → character_agent → response_builder → mood → expression_picker → scene_image → condense → memory | Full experience: bubbles, mood axes, LLM portrait variants, optional sidebar scene art, rolling summary. |
| **narrator_chat_classic** | narrator → character_agent → response_builder → mood → scene_image → condense → memory | Like `narrator_chat` but **no** `expression_picker` — static `portrait` only. |
| **narrator_chat_progression** | progression → _(same as narrator_chat from narrator onward)_ | Stories with NPC `progression` stages (turn / mood / criteria gates). |
| **narrator_chat_lite** | narrator → character_agent → response_builder → memory | Faster turns: bubbles + `history`; no mood, condense, expression_picker, or scene_image. |
| **chat_direct** | character_agent → response_builder → memory | No narrator — characters speak directly (shared `history` still grows). |

## Choosing a subgraph

- **Solo or minimal cast, fast play:** `narrator_chat_lite`
- **Cast with mood axes, portraits variants, gallery, long campaigns:** `narrator_chat`
- **Same as full pipeline but no LLM portrait picking:** `narrator_chat_classic`
- **Stage-gated relationship or plot beats:** `narrator_chat_progression` (requires `progression` config on characters)
- **Pure character-driven chat without narrator prose:** `chat_direct`

## Migrating old stories

`db.migrate_schema()` rewrites legacy subgraph names (e.g. `conversation`, `full_story`, `scene_chat`, …) to **`narrator_chat`** when the story has characters, otherwise **`narrator_chat_lite`**.
