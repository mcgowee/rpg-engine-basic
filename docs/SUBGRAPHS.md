# Builtin subgraphs

A **subgraph** is the LangGraph pipeline that runs on every turn: which **nodes** execute (narrator, mood, NPC, condense, memory, …) and in what order. You pick one per story in the Story Editor (**Subgraph** field).

This document describes the **builtin** subgraphs shipped in `graphs/*.json`. Custom subgraphs you build in the Graph Editor follow the same JSON shape.

---

## Quick reference

### Narrator pipelines (traditional RPG narration)

| Subgraph | Pipeline (simplified) | Conditional routing? |
|----------|------------------------|----------------------|
| `basic_narrator` | narrator → end | No |
| `conversation` | narrator → memory → end | No |
| `full_conversation` | narrator → condense → memory → end | No |
| `smart_conversation` | narrator → (npc → coda **or** condense) → memory → end | Yes (`route_after_narrator`) |
| `full_memory` | narrator → mood → npc → condense → memory → end | No |
| `full_story` | narrator → (mood → npc → coda **or** condense) → memory → end | Yes (`route_after_narrator`) |

### Chat pipelines (direct character conversation)

| Subgraph | Pipeline (simplified) | Conditional routing? |
|----------|------------------------|----------------------|
| `chat_only` | character_chat → memory → end | No |
| `chat_with_memory` | character_chat → mood → condense → memory → end | No |
| `scene_chat` | scene → character_chat → memory → end | No |
| `scene_chat_full` | scene → character_chat → mood → condense → memory → end | No |
| `scene_chat_action` | scene → character_chat → character_action → mood → condense → memory → end | No |

**Routing:** When conditional routing is present, the router `route_after_narrator` checks whether the story has **characters**. If yes, the graph continues along the NPC (and possibly mood) path; if no, it jumps to **condense** and skips NPC-facing nodes that would not apply. Chat pipelines do not use conditional routing — they always run the full chain.

---

## What each subgraph does

| Subgraph | What it does | Good for |
|----------|----------------|----------|
| **basic_narrator** | Runs **only** the narrator each turn and ends. **Fast and simple** (one LLM call), but **no** in-graph memory, condense, NPCs, or mood—each turn is isolated unless something outside this graph adds history. | One-shots, demos, tutorials, quick experiments—anywhere you want the leanest turns and do not need in-graph memory. |
| **conversation** | Narrator, then **memory** appends the turn. **Cheap** (one narrator LLM per turn) and keeps **raw** history for context, but **no** `condense`, so there is **no** rolling AI “story so far” summary from this graph—only what the narrator sees from history plus any existing summary. | Short solo arcs, light continuity, prototyping—stories where raw history is enough and you want cheap per-turn cost. |
| **full_conversation** | Narrator, then **condense** builds a compressed summary, then **memory** stores the turn. **Good for long solo arcs** with a real memory summary, but **two** LLM calls per turn (narrator + condense) and **no** NPC or mood nodes. | Long solo campaigns, exploration, epics without a named cast—when you need a rolling summary but not NPCs or mood. |
| **smart_conversation** | **Branches** after the narrator: with **characters**, scene → **NPC** lines → **narrator_coda** (player prompt) → condense → memory; with **no** characters, narrator goes straight to **condense** → memory (skips NPC + coda). **Flexible** for solo or cast, but **no mood** node. | Mysteries, ensemble dialogue, heists with a crew—any NPC-heavy plot where you do not need character mood axes. |
| **full_memory** | **Fixed** chain: narrator → **mood** → **NPC** → condense → memory—**no** branch after narrator, **no** `narrator_coda` node. **Full mood + NPC + summary** when you always have a cast, but the path does **not** skip mood/NPC for empty casts (unlike `full_story`). | Relationship drama, emotional beats, fixed-party adventures—stories where the cast is always present and mood matters. |
| **full_story** | **Branches** after the narrator: with **characters**, mood → NPC → **narrator_coda** → condense → memory; with **none**, straight to condense → memory. **Richest** behavior (mood, NPCs, coda, summary) with **skips** when there is no cast, but **most** LLM work per turn when the full path runs. | Full-featured games: mood + NPCs + post-scene player beat—works for solo or optional cast and scales down when no characters are defined. |
| **chat_only** | **Character_chat** generates pure dialogue (one character talking to the player), then **memory** stores the turn. **Fastest chat** (one LLM call) with history but **no** condense, mood, or scene. | Quick chats, testing character voices, simple dialogue-focused interactions. |
| **chat_with_memory** | Character_chat, then **mood** updates emotional axes, then **condense** compresses history, then **memory** stores. Dialogue-only but with **emotional tracking** and **long-term memory**. | Character-driven stories where dialogue matters more than scene description. |
| **scene_chat** | **Scene** generates 1-2 atmospheric sentences, then **character_chat** adds dialogue, then **memory** stores. Gives conversation **physical context** without full narration. | Casual interactions with a sense of place—romance, slice-of-life, hangouts. |
| **scene_chat_full** | Scene → character_chat → **mood** → **condense** → memory. **Recommended chat pipeline.** Atmosphere + dialogue + emotional tracking + compressed memory. | Relationship-focused stories, romance, any character-driven plot with emotional depth. |
| **scene_chat_action** | Scene → character_chat → **character_action** → mood → condense → memory. **Richest chat pipeline.** Adds a physical action node (body language, movement, gestures) after dialogue. Output has three layers: scene description, spoken words, physical action. | Stories where physicality matters—romance, tension, intimacy, character body language. |

---

## One-line picker

### Narrator style (traditional RPG)
- **Minimal / tutorial:** `basic_narrator`
- **Solo + cheap memory:** `conversation`
- **Solo + long-term summary:** `full_conversation`
- **NPCs, no mood axes:** `smart_conversation`
- **Mood + NPCs, cast always:** `full_memory`
- **Mood + NPCs + coda, cast optional:** `full_story`

### Chat style (direct character conversation)
- **Quick dialogue test:** `chat_only`
- **Dialogue + mood + memory:** `chat_with_memory`
- **Scene + dialogue:** `scene_chat`
- **Scene + dialogue + mood + memory (recommended):** `scene_chat_full`
- **Scene + dialogue + action + mood + memory (richest):** `scene_chat_action`

---

## Related

- In-app: **Creating Stories** (`/docs/stories`), **Engine Reference** (`/docs/engine`), **Playing** (`/docs/playing`).
- Repo: [ARCHITECTURE.md](ARCHITECTURE.md) (system shape), [NODE_STATUS.md](../NODE_STATUS.md) (nodes snapshot), [INDEX.md](INDEX.md) (full doc list).
- Source JSON: `graphs/<name>.json` in the repository.
