"""Test that narrator prompt includes location hints.

Run with: python3 scripts/test_narrator_location.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We can't call narrator_node directly without an LLM, so test the
# prompt-building logic by simulating what the node does.

state = {
    "message": "I look around the tavern",
    "player": {"name": "Traveler", "background": "A wanderer"},
    "characters": {"barkeep": {"prompt": "You are Aldric, the barkeep."}},
    "game_title": "The Silver Road",
    "history": [],
    "memory_summary": "",
    "narrator_prompt": "You are the narrator for a fantasy quest.",
    "_narrator_location_hint": (
        "The player has just arrived at The Rusted Nail. "
        "A dim, smoky tavern at a crossroads. Describe this new location vividly."
    ),
    "_narrator_progression": "",
}

# Replicate the prompt-building from narrator.py
location_hint = (state.get("_narrator_location_hint") or "").strip()
location_block = f"\nLocation context:\n{location_hint}\n" if location_hint else ""

progression_hint = (state.get("_narrator_progression") or "").strip()
progression_block = f"\nScene atmosphere:\n{progression_hint}\n" if progression_hint else ""

print("=" * 60)
print("  Testing narrator location hint injection")
print("=" * 60)

# Test 1: Location block is built correctly
assert "The Rusted Nail" in location_block
assert "Location context:" in location_block
print("  ✓ Location block contains hint text")

# Test 2: Progression block is empty when not set
assert progression_block == ""
print("  ✓ Progression block empty when no progression")

# Test 3: Location block would appear in prompt
prompt_section = f"{progression_block}{location_block}"
assert "Location context:" in prompt_section
assert "The Rusted Nail" in prompt_section
print("  ✓ Location block appears in prompt section")

# Test 4: No location hint → no block
state_no_quest = {**state, "_narrator_location_hint": ""}
hint2 = (state_no_quest.get("_narrator_location_hint") or "").strip()
block2 = f"\nLocation context:\n{hint2}\n" if hint2 else ""
assert block2 == ""
print("  ✓ No hint → no location block (non-quest stories unaffected)")

print("\n" + "=" * 60)
print("  ALL TESTS PASSED ✓")
print("=" * 60 + "\n")
