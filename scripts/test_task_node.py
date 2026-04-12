"""Test task node — non-LLM paths only.

Run with: python3 scripts/test_task_node.py

LLM-dependent evaluation will be tested during play testing.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.task import task_node

MAP_DATA = {
    "start": "tavern",
    "order": ["tavern", "forest", "ruins"],
    "locations": {
        "tavern": {
            "name": "The Rusted Nail",
            "characters": ["barkeep"],
            "task": "Retrieve the stolen ledger",
            "task_criteria": "Player finds and returns the ledger",
            "min_turns": 2,
        },
        "forest": {
            "name": "The Whispering Wood",
            "characters": [],
            "task": "Find the hidden path",
            "task_criteria": "",  # Empty = auto-complete
            "min_turns": 1,
        },
        "ruins": {
            "name": "The Silver Ruins",
            "characters": ["ghost_knight"],
            "task": "Place the crown on the altar",
            "task_criteria": "Player places the crown",
            "min_turns": 3,
        },
    },
}


def pp(label, result):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if not result:
        print("  (no changes)")
    else:
        ls = result.get("_location_state", {})
        hint = result.get("_task_narrator_hint", "")
        print(f"  Task complete: {ls.get('task_complete_current', '?')}")
        print(f"  Completed tasks: {ls.get('completed_tasks', [])}")
        print(f"  Hint: {hint[:100]}")


# --- Test 1: No map data → empty ---
r1 = task_node({"message": "hello"})
assert r1 == {}
print("  ✓ Test 1: No map → empty result")

# --- Test 2: Already complete → skip ---
state2 = {
    "map": MAP_DATA,
    "_location_state": {
        "current_location": "tavern",
        "location_index": 0,
        "completed_tasks": [],
        "task_complete_current": True,  # Already done
        "turns_at_location": 5,
    },
}
r2 = task_node(state2)
assert r2 == {}
print("  ✓ Test 2: Already complete → skip")

# --- Test 3: Min turns not met → skip ---
state3 = {
    "map": MAP_DATA,
    "_location_state": {
        "current_location": "tavern",
        "location_index": 0,
        "completed_tasks": [],
        "task_complete_current": False,
        "turns_at_location": 1,  # min_turns is 2
    },
    "message": "I found the ledger",
    "_narrator_text": "You find the ledger.",
}
r3 = task_node(state3)
assert r3 == {}
print("  ✓ Test 3: Min turns not met → skip")

# --- Test 4: No task_criteria → auto-complete ---
state4 = {
    "map": MAP_DATA,
    "_location_state": {
        "current_location": "forest",
        "location_index": 1,
        "completed_tasks": ["tavern"],
        "task_complete_current": False,
        "turns_at_location": 1,
    },
}
r4 = task_node(state4)
pp("Test 4: No criteria → auto-complete", r4)
assert r4["_location_state"]["task_complete_current"] is True
assert "forest" in r4["_location_state"]["completed_tasks"]
assert "free to move on" in r4["_task_narrator_hint"]
print("  ✓ Test 4: Auto-complete works")

# --- Test 5: Min turns met but no context → skip ---
state5 = {
    "map": MAP_DATA,
    "_location_state": {
        "current_location": "tavern",
        "location_index": 0,
        "completed_tasks": [],
        "task_complete_current": False,
        "turns_at_location": 2,
    },
    "message": "",
    "_narrator_text": "",
    "history": [],
}
r5 = task_node(state5)
assert r5 == {}
print("  ✓ Test 5: No context → skip (won't call LLM with empty context)")

# --- Test 6: Completed tasks list doesn't duplicate ---
state6 = {
    "map": MAP_DATA,
    "_location_state": {
        "current_location": "forest",
        "location_index": 1,
        "completed_tasks": ["tavern", "forest"],  # forest already in list
        "task_complete_current": False,
        "turns_at_location": 1,
    },
}
r6 = task_node(state6)
assert r6["_location_state"]["completed_tasks"].count("forest") == 1
print("  ✓ Test 6: No duplicate in completed_tasks")

print(f"\n{'='*60}")
print("  ALL TESTS PASSED ✓")
print(f"{'='*60}")
print("\n  Note: LLM evaluation (YES/NO) tested during play test.\n")
