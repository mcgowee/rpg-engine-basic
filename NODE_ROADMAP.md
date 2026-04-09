# Node Roadmap

## Core (every graph needs these)
| Node | LLM? | What it does | Status |
|------|------|-------------|--------|
| **narrator** | Yes | Generates scene narration from player input | ✅ Done |
| **memory** | No | Records turn in history list, increments turn_count | ✅ Done |
| **condense** | Yes | Summarizes history into a rolling memory_summary so narrator has context | ✅ Done |

## Round 2: World interaction
| Node | LLM? | What it does | Status |
|------|------|-------------|--------|
| **movement** | Yes | Detects if player is trying to move to a different location | Not started |
| **npc** | Yes | NPCs respond in character based on their personality prompts | ✅ Done (`nodes/npc.py`, builtin `smart_conversation` / `full_story`) |
| **mood** | Yes | Per-axis **1–10** mood (axes) or legacy single field via **UP/DOWN/SAME** step | ✅ Done (`nodes/mood.py`; `route_after_narrator` in `routers/routing.py`) |
| **rules** | Yes | Checks win/lose conditions and trigger words | Not started (main-graph `rules` transitions can fire when state sets `_rules_transition` to the condition string) |

## Round 3: Social/milestone system
| Node | LLM? | What it does | Status |
|------|------|-------------|--------|
| **milestone** | No | Checks if player message matches the current milestone goal | Not started |
| **tension** | No | Tracks how many turns since last milestone, sets "stalling" mood | Not started |
| **guide_arrival** | No | Moves the guide NPC to the player's current room | Not started |

## Future ideas (not built yet)
| Node | What it would do |
|------|-----------------|
| **combat** | Turn-based combat system |
| **quest** | Quest tracking/journal |
| **dialogue_tree** | Branched dialogue choices |
| **perception** | Skill checks / awareness |
| **timer** | Real-time or turn-based countdown |

## Build order notes

Each round adds State fields, nodes, routers, and possibly story editor changes:

- **Round 2 (World)** needs: `location`, `locations`, `characters` in State. Movement node needs routers updated. NPC/mood need character data in story editor. New builtin subgraph with the full exploration flow.
- **Round 3 (Rules)** needs: `rules` in State. Rules data in story editor. Router `route_after_memory` to conditionally run rules.
- **Round 3 (Social)** needs: `milestones`, `milestone_progress`, `guide`, `tension_turns_since_milestone`, `tension_mood` in State. Social-specific routers. Guide/milestone/tension data in story editor.
