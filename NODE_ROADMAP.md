# Node Roadmap

## Current Architecture

Full subgraph (`narrator_chat`):

```
narrator → character_agent → response_builder → scene_image → mood → condense → memory
```

`narrator_chat_lite` omits **scene_image**, **mood**, and **condense**. `chat_direct` starts at **character_agent** (no narrator).

Narrator describes the world. Character agents respond with dialogue + action. Response builder assembles multi-bubble UI payload. Scene image picks sidebar art when present. Mood tracks axes. Condense compresses memory. Memory stores structured turns.

## Implemented Nodes

| Node | LLM? | What it does | Status |
|------|------|-------------|--------|
| **narrator** | Yes (creative) | Describes scene, events, consequences. No character dialogue. | ✅ Done |
| **character_agent** | Yes (dialogue) | Each character responds with SAY + DO. Independent agents. | ✅ Done |
| **response_builder** | No | Assembles narrator + character bubbles for frontend. | ✅ Done |
| **scene_image** | No* | Scene / gallery image selection for play sidebar. | ✅ Done |
| **mood** | Yes (classification) | Rates each character's emotional axes 1-10 per turn. | ✅ Done |
| **condense** | Yes (summarization) | Rolling 60-80 word memory summary from structured history. | ✅ Done |
| **memory** | No | Stores structured turn dict: player, narrator, characters, mood. | ✅ Done |

\*Image side effects may use ComfyUI; no prose LLM in-node.

---

## Planned: Bubble-Producing Nodes

These nodes create new bubble types in the UI.

### inner_thought
**Priority:** High | **LLM:** Yes (creative) | **Runs after:** character_agent

Generates what a character is *thinking* but not saying. Displayed as a faded/italic thought bubble. Creates dramatic irony — the player sees what the character won't admit.

```
┌─────────────────────────────────┐
│ 💭 Alex (thinking)              │
│ He remembered how I take my     │
│ coffee. No one ever remembers.  │
└─────────────────────────────────┘
```

**State reads:** `_character_responses`, character personality, mood, memory_summary
**State writes:** `_character_thoughts: {"alex": "He remembered..."}`
**Response builder:** Adds thought bubbles after character bubbles
**Best for:** Romance, drama, psychological stories
**Toggle:** Per-story setting in story editor (some players don't want mind-reading)

### bystander
**Priority:** Medium | **LLM:** Yes (dialogue) | **Runs after:** response_builder

A non-main character who occasionally comments — the barista, a neighbor, a stranger. One-line color commentary. Only fires when the story setting implies other people are around.

```
┌─────────────────────────────────┐
│ 👤 Barista                      │
│ "You two are adorable. Just     │
│ saying."                         │
└─────────────────────────────────┘
```

**State reads:** narrator_text, character_responses, story context (setting)
**State writes:** `_bystander: {"name": "Barista", "dialogue": "..."}`
**Skip logic:** Only fires when setting suggests public space. Random chance (30-50% per turn) to avoid every turn.
**Best for:** Slice-of-life, comedy, public settings

### environment_reaction
**Priority:** Low | **LLM:** Yes (creative) | **Runs after:** character_agent

The world reacts to what happened — a phone rings, weather changes, a song comes on. Ambient events that aren't narrator (which describes player actions) but aren't character speech either.

```
┌─────────────────────────────────┐
│ 🌍 Environment                  │
│ Alex's phone buzzes on the      │
│ counter. The screen lights up.  │
└─────────────────────────────────┘
```

**State reads:** narrator_text, character_responses, memory_summary, story context
**State writes:** `_environment: "Alex's phone buzzes..."`
**Risk:** Could become the old quality guard problem — introducing random events. Needs strong genre/tone grounding.
**Best for:** Stories that need ambient world-building

---

## Planned: State-Modifying Nodes

These don't produce bubbles — they update state that other nodes read.

### relationship_tracker
**Priority:** High | **LLM:** Yes (classification) | **Runs after:** mood

Tracks the *stage* of the relationship, not just mood numbers. Writes a label that character agents read to adjust their behavior.

**Stages:** `strangers → acquaintances → friends → flirting → dating → intimate → committed`

**State writes:** `_relationship_stages: {"alex": "flirting"}`
**Character agent reads it:** "You are at the FLIRTING stage with the player. You tease and hint but haven't been direct about your feelings yet."
**Best for:** Romance, any story with relationship progression

### tension_clock
**Priority:** High | **LLM:** No (pure logic) | **Runs after:** mood

Counts turns since the last significant event (mood shift > 2, relationship stage change, new character). When count exceeds threshold, sets `_tension_high: true`. The narrator reads this and knows to escalate — but *it* decides how, not the clock.

**State writes:** `_tension_level: 7`, `_turns_since_event: 4`
**Zero LLM cost.** Just a counter with thresholds.
**Best for:** Any story longer than 5 turns

### time_tracker
**Priority:** Medium | **LLM:** No (logic + light classification) | **Runs after:** memory

Advances the in-story clock. Tracks time of day (morning/afternoon/evening/night) and day count. Narrator and character agents reference time naturally.

**State writes:** `_time: {"period": "evening", "day": 2}`
**Narrator reads it:** Describes lighting, atmosphere appropriate to time
**Prevents:** "They had 15 conversations in one evening"
**Best for:** Multi-day stories, stories with routines

### secret_keeper
**Priority:** Medium | **LLM:** Yes (classification) | **Runs after:** condense

Tracks what each character knows and doesn't know. When something is revealed, it's recorded. Character agents are told what they know so they don't accidentally reference hidden information.

```python
state["_secrets"] = {
    "alex": {
        "knows": ["player had a tough breakup", "player likes coding"],
        "doesnt_know": ["player's ex called yesterday"],
        "hiding": ["alex is in debt"]
    }
}
```

**Character agent reads it:** "You do NOT know that the player's ex called. You ARE hiding that you're in debt."
**Best for:** Mystery, drama, romance with secrets

---

## Planned: Game Mechanic Nodes

These add traditional RPG mechanics to the bubble-based system.

### inventory
**Priority:** Medium | **LLM:** Yes (classification) | **Runs after:** narrator

Extracts item changes from the narrator's description. "You pick up the key" → adds key to inventory. "You use the flashlight" → removes it if consumable.

```python
state["_inventory"] = ["apartment key", "phone", "alex's mixtape"]
```

**Narrator reads it:** Knows what the player is carrying, can reference items naturally
**Character agent reads it:** Can comment on items ("Is that my mixtape in your pocket?")
**UI:** Inventory sidebar or collapsible panel
**Story editor:** Define starting inventory, important items, consumable flags
**Best for:** Mystery (find clues), horror (limited resources), adventure (puzzle items)

### location_tracker
**Priority:** Medium | **LLM:** Yes (classification) | **Runs after:** narrator

Detects when the player moves to a new location. Tracks current location and available exits. Updates narrator context so scene descriptions match where they are.

```python
state["_location"] = {
    "current": "alex_apartment_kitchen",
    "label": "Alex's Kitchen",
    "exits": ["living_room", "hallway", "balcony"]
}
```

**Narrator reads it:** Describes the current location appropriately
**Character agent reads it:** Knows if they're in the same room as the player
**Story editor:** Define locations with descriptions and connections
**Best for:** Exploration, multi-room stories, any story with physical space

### skill_check
**Priority:** Low | **LLM:** No (dice roll + logic) | **Runs after:** narrator, before character_agent

When the narrator describes an attempt ("You try to pick the lock"), the skill check node rolls against the player's stats. Result modifies what the narrator described — success or failure.

```python
state["_player_stats"] = {"charm": 7, "stealth": 4, "tech": 8}
# Roll: tech 8 vs difficulty 6 → success
```

**Narrator reads result:** Describes success or failure
**UI:** Shows dice roll animation in a system bubble
**Story editor:** Define player stats, difficulty settings
**Best for:** RPG-style games with chance elements

### quest_tracker
**Priority:** Low | **LLM:** Yes (classification) | **Runs after:** condense

Tracks quest objectives and completion. Extracts progress from what happened each turn. Updates a quest log the player can reference.

```python
state["_quests"] = {
    "win_alex_over": {
        "status": "active",
        "objectives": [
            {"text": "Ask Alex on a date", "done": True},
            {"text": "Learn Alex's secret", "done": False},
            {"text": "First kiss", "done": False}
        ]
    }
}
```

**UI:** Quest log sidebar or tab
**Story editor:** Define quests with objectives
**Best for:** Longer stories with goals, gamified narratives

---

## Planned: Quality/Filter Nodes

### tone_guard
**Priority:** Low | **LLM:** Yes (classification) | **Runs after:** response_builder

Lightweight genre check. Scores the turn output 1-10 for tone consistency. If below threshold, sets a correction flag for next turn's narrator. Does NOT suggest plot twists (the old quality guard's mistake). Just says "you're drifting off-tone."

**State writes:** `_tone_score: 4, _tone_warning: "Story is drifting toward thriller elements"`
**Narrator reads it next turn:** Adjusts tone back toward genre
**Best for:** Any story — cheap insurance against genre drift

### continuity_check
**Priority:** Low | **LLM:** Yes (classification) | **Runs after:** response_builder

Reads the full turn output and checks for contradictions against memory_summary. "Alex has blue eyes" vs earlier "Alex has brown eyes." Flags issues in state — doesn't block or rewrite.

**State writes:** `_continuity_warnings: ["Eye color inconsistency"]`
**Best for:** Longer stories where details drift

---

## Parallel Character Execution (Future)

Currently `character_agent` loops through characters sequentially. Two upgrade paths:

**Option A (simple):** ThreadPoolExecutor inside the existing node. All characters generate in parallel. Same subgraph, no architecture change. 3 characters in the time of 1.

**Option B (advanced):** LangGraph `Send` API for true dynamic fan-out. A `character_dispatcher` node creates one `character_worker` per character at runtime. Visible in the graph as parallel branches.

---

## Build Priority

### Tier 1 (next to build)
1. **inner_thought** — biggest story quality impact
2. **relationship_tracker** — gives characters behavioral stages
3. **tension_clock** — zero cost pacing

### Tier 2 (after core is solid)
4. **time_tracker** — temporal awareness
5. **inventory** — enables puzzle/adventure stories
6. **bystander** — world depth
7. **location_tracker** — spatial awareness

### Tier 3 (specialized)
8. **secret_keeper** — information asymmetry
9. **skill_check** — RPG mechanics
10. **quest_tracker** — gamified goals
11. **tone_guard** — quality insurance
12. **environment_reaction** — ambient events
13. **continuity_check** — contradiction detection
