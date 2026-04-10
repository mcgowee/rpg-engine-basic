# Node Status

Snapshot of **implemented nodes**, **builtin subgraphs**, and how they fit together. For a player-facing comparison of pipelines (when to pick which graph), see [docs/SUBGRAPHS.md](docs/SUBGRAPHS.md). For architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Nodes (implemented)

### Narrator pipeline nodes
| Node | File | LLM? | Purpose |
|------|------|------|---------|
| **narrator** | `nodes/narrator.py` | Yes (creative) | Core scene narration. Genre/tone/NSFW-aware. Can separate “scene only” vs NPC dialogue when the subgraph uses a dedicated `npc` node. |
| **mood** | `nodes/mood.py` | Yes (classification) | Updates per-character mood. **Mood axes:** LLM outputs a **1–10** value per axis. **Legacy single field:** UP / DOWN / SAME adjusts a single `mood` number by ±1. |
| **npc** | `nodes/npc.py` | Yes (dialogue) | NPCs speak in character; reads mood and memory context. |
| **narrator_coda** | `nodes/narrator_coda.py` | Yes (creative) | Closing beat after NPC lines (e.g. prompt the player). Used in `smart_conversation` and `full_story`. |
| **condense** | `nodes/condense.py` | Yes (summarization) | Compresses history into a rolling `memory_summary` for long-term context. |
| **memory** | `nodes/memory.py` | No | Appends the turn to `history`, stores condense output, increments `turn_count`. |

### Chat pipeline nodes
| Node | File | LLM? | Purpose |
|------|------|------|---------|
| **scene** | `nodes/scene.py` | Yes (creative) | Brief 1-2 sentence atmospheric scene-setting. Describes environment, mood, sensory details. No plot, no dialogue. Writes to `_scene_text` which `character_chat` prepends to its response. Skips turn 1 (opening text handles it). |
| **character_chat** | `nodes/character_chat.py` | Yes (dialogue) | Pure dialogue — one character talks directly to the player. No narration, no stage directions. Uses first character in story. Reads mood state, memory summary, last 6 conversation turns. Prepends scene text if available. |
| **character_action** | `nodes/character_action.py` | Yes (creative) | Generates a brief physical action for the character (5-15 words). Body language, movement, gestures. Runs after `character_chat` and appends the action in `*italics*` format. |

## Routers

| Router | Returns | Role |
|--------|---------|------|
| `route_graph_entry` | `narrator` | Entry: always start at narrator. |
| `route_after_narrator` | `npc` or `condense` | If `characters` is non-empty, return value is **`npc`** (graphs map that string to the next node, e.g. `mood` or `npc`). If no characters, **`condense`** — skips NPC/mood/coda paths that depend on a cast. |

## Builtin subgraphs (see `graphs/*.json`)

The Story Editor default for new stories is **`conversation`** (`web/src/lib/components/StoryEditor.svelte`). All six builtins are registered from DB seed / `sync_builtin_subgraphs_from_disk()`.

| Subgraph | Pipeline (simplified) | Conditional after narrator? |
|----------|------------------------|-----------------------------|
| `basic_narrator` | narrator → end | No |
| `conversation` | narrator → memory → end | No |
| `full_conversation` | narrator → condense → memory → end | No |
| `smart_conversation` | narrator → (npc → coda or condense) → memory → end | Yes |
| `full_memory` | narrator → mood → npc → condense → memory → end | No (fixed chain; does not skip when there are no characters) |
| `full_story` | narrator → (mood → npc → coda or condense) → memory → end | Yes |
| `chat_only` | character_chat → memory → end | No |
| `chat_with_memory` | character_chat → mood → condense → memory → end | No |
| `scene_chat` | scene → character_chat → memory → end | No |
| `scene_chat_full` | scene → character_chat → mood → condense → memory → end | No |
| `scene_chat_action` | scene → character_chat → character_action → mood → condense → memory → end | No |

**Rename:** older stories may have had `conversation_with_mood`; migrations in `db.py` map that to **`full_story`**.

## Story metadata → prompts

```
Story Editor → DB (genre, tone, nsfw_rating, nsfw_tags, …)
    → state["story"] in play
        → nodes/story_context.py → prompt strings for narrator, condense, etc.
```

## Planned / future nodes

See [NODE_ROADMAP.md](NODE_ROADMAP.md) for ideas (tension, consequence, world_state, director, …).
