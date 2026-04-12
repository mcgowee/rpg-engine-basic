"""Quick test for the location node — run with: python scripts/test_location_node.py"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.location import location_node

MAP_DATA = {
    "start": "tavern",
    "order": ["tavern", "forest", "ruins"],
    "locations": {
        "tavern": {
            "name": "The Rusted Nail",
            "narrator_hint": "A dim, smoky tavern at a crossroads.",
            "opening_text": "You push through the heavy oak door.",
            "characters": ["barkeep"],
            "task": "Retrieve Aldric's stolen ledger from the back storeroom",
            "task_criteria": "Player finds and returns the ledger",
            "min_turns": 2,
        },
        "forest": {
            "name": "The Whispering Wood",
            "narrator_hint": "Ancient oaks press close. Strange whispers ride the wind.",
            "opening_text": "The road narrows to a dirt track that winds into shadow.",
            "characters": [],
            "task": "Follow the silver trail markers to find the hidden path",
            "task_criteria": "Player follows markers to find the path",
            "min_turns": 2,
        },
        "ruins": {
            "name": "The Silver Ruins",
            "narrator_hint": "Crumbling stone walls draped in ivy and moonflower.",
            "opening_text": "The trees thin and you step into a clearing of stone.",
            "characters": ["ghost_knight"],
            "task": "Place the Silver Crown on the altar",
            "task_criteria": "Player places the crown on the altar",
            "min_turns": 3,
        },
    },
}

ALL_CHARACTERS = {
    "barkeep": {"prompt": "You are Aldric, the barkeep.", "first_line": "What'll it be?"},
    "ghost_knight": {"prompt": "You are Sir Callum, a ghost.", "first_line": "Another seeker."},
}


def pp(label, result):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    loc = result.get("_location", {})
    ls = result.get("_location_state", {})
    chars = result.get("characters", {})
    hint = result.get("_narrator_location_hint", "")
    print(f"  Location:    {loc.get('name', '?')} ({loc.get('key', '?')})")
    print(f"  Task:        {loc.get('task', '?')}")
    print(f"  First turn:  {loc.get('is_first_turn', '?')}")
    print(f"  Task done:   {loc.get('task_complete', '?')}")
    print(f"  Characters:  {list(chars.keys())}")
    print(f"  Turns here:  {ls.get('turns_at_location', '?')}")
    print(f"  Completed:   {ls.get('completed_tasks', [])}")
    print(f"  Quest done:  {ls.get('quest_complete', False)}")
    print(f"  Narrator hint (first 120): {hint[:120]}...")


# --- Test 1: First turn (initialization) ---
state = {"map": MAP_DATA, "_all_characters": ALL_CHARACTERS, "message": "I look around"}
r = location_node(state)
pp("Turn 1: First arrival at tavern", r)
assert r["_location"]["key"] == "tavern"
assert r["_location"]["is_first_turn"] is True
assert list(r["characters"].keys()) == ["barkeep"]

# --- Test 2: Normal turn (no move) ---
state2 = {**state, "_location_state": r["_location_state"], "message": "I talk to the barkeep"}
r2 = location_node(state2)
pp("Turn 2: Normal turn at tavern", r2)
assert r2["_location"]["key"] == "tavern"
assert r2["_location"]["is_first_turn"] is False

# --- Test 3: Try to move without completing task ---
state3 = {**state, "_location_state": r2["_location_state"], "message": "I head out"}
r3 = location_node(state3)
pp("Turn 3: Try to leave (task not done)", r3)
assert r3["_location"]["key"] == "tavern"
assert "haven't completed" in r3["_narrator_location_hint"]

# --- Test 4: Task complete, then move ---
ls4 = dict(r3["_location_state"])
ls4["task_complete_current"] = True
ls4["completed_tasks"] = ["tavern"]
state4 = {**state, "_location_state": ls4, "message": "I head out into the forest"}
r4 = location_node(state4)
pp("Turn 4: Move to forest (task done)", r4)
assert r4["_location"]["key"] == "forest"
assert r4["_location"]["is_first_turn"] is True
assert r4["characters"] == {}  # No NPCs in forest

# --- Test 5: Normal turn in forest ---
state5 = {**state, "_location_state": r4["_location_state"], "message": "I look for trail markers"}
r5 = location_node(state5)
pp("Turn 5: Normal turn in forest", r5)
assert r5["_location"]["key"] == "forest"

# --- Test 6: Complete forest, move to ruins ---
ls6 = dict(r5["_location_state"])
ls6["task_complete_current"] = True
ls6["completed_tasks"] = ["tavern", "forest"]
state6 = {**state, "_location_state": ls6, "message": "I press on through the trees"}
r6 = location_node(state6)
pp("Turn 6: Move to ruins", r6)
assert r6["_location"]["key"] == "ruins"
assert list(r6["characters"].keys()) == ["ghost_knight"]

# --- Test 7: Complete ruins, try to move (quest complete) ---
ls7 = dict(r6["_location_state"])
ls7["task_complete_current"] = True
ls7["completed_tasks"] = ["tavern", "forest", "ruins"]
state7 = {**state, "_location_state": ls7, "message": "I leave the ruins"}
r7 = location_node(state7)
pp("Turn 7: Quest complete", r7)
assert r7["_location_state"]["quest_complete"] is True

# --- Test 8: No map data (non-quest story) ---
r8 = location_node({"message": "hello"})
assert r8 == {}
print(f"\n{'='*60}")
print("  Test 8: No map → empty result ✓")

print(f"\n{'='*60}")
print("  ALL TESTS PASSED ✓")
print(f"{'='*60}\n")
