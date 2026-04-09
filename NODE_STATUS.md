# Node Status

## Active Pipeline: `full_memory`

```
narrator → mood → npc → condense → memory
```

5 nodes, ~5.5s avg per turn with mistral-nemo:latest.

## Node Details

| Node | File | Status | LLM Call | Purpose |
|------|------|--------|----------|---------|
| **narrator** | `nodes/narrator.py` | Active | Yes (creative) | Core scene narration. Genre/tone/NSFW-aware. NPC-separation mode for subgraphs with dedicated NPC node. |
| **mood** | `nodes/mood.py` | Active | Yes (classification) | Rates each character's emotional axes (1-10) per turn. Number-based rating, not UP/DOWN/SAME. |
| **npc** | `nodes/npc.py` | Active | Yes (dialogue) | Each character speaks in their own voice. Reads mood state, memory summary, narrator scene. |
| **condense** | `nodes/condense.py` | Active | Yes (summarization) | Compresses full history into rolling 60-80 word summary. Story-context-aware. |
| **memory** | `nodes/memory.py` | Active | No | Appends current turn to history, stores condense output. Pure bookkeeping. |
| **quality_guard** | `nodes/quality_guard.py` | Available | Yes (classification) | Pre-narrator analysis suggesting plot twists. Removed from active pipeline — caused tone drift. |
| **narrator_coda** | `nodes/narrator_coda.py` | Available | Yes (creative) | Closing beat after NPC dialogue ("What do you do?"). Not needed when narrator handles this. |
| **prompt_trim** | `nodes/prompt_trim.py` | Utility | No | Truncates text to char limit. Used by narrator and NPC nodes. |

## Shared Utilities

| File | Purpose |
|------|---------|
| `nodes/story_context.py` | Builds genre/tone/NSFW context string from `state["story"]`. Used by narrator, quality_guard, condense. |
| `nodes/prompt_trim.py` | Text truncation utility. |

## Available Subgraphs

| Subgraph | Nodes | Recommended For |
|----------|-------|----------------|
| `full_memory` | narrator → mood → npc → condense → memory | **Default.** Stories with characters and mood axes. |
| `guarded_full_memory` | quality_guard → narrator → mood → npc → condense → memory | Testing quality guard behavior. |
| `guarded_narrator_with_memory` | quality_guard → narrator → condense → memory | Stories without characters. |
| `guarded_narrator` | quality_guard → narrator | Lightweight testing. |
| `basic_narrator` | narrator only | Simplest possible pipeline. |

## Planned Nodes

| Node | Priority | Purpose |
|------|----------|---------|
| **tension_tracker** | Next | Single 1-10 tension score per turn. Feeds into narrator for pacing awareness. |
| **consequence** | High | Tracks lasting effects of player choices ("Alex knows your secret"). |
| **world_state** | Medium | Tracks location, time of day, weather, who's present. |
| **director** | Medium | Determines narrative phase (setup → rising action → climax → resolution). |

## Story Metadata Flow

```
Story Editor → DB (genre, tone, nsfw_rating, nsfw_tags)
    → _build_state_from_story() → state["story"]
        → nodes/story_context.py → prompt strings
            → narrator, quality_guard, condense read it
```
