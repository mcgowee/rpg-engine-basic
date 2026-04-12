"""Location node — manages player position in quest/adventure stories.

Tracks current location, swaps active characters per location,
detects player movement intent, and builds narrator context hints.

Players can move freely between any location. NPCs only appear at
the location where the current active task is set. Other locations
are empty but visitable.

Runs first in the quest pipeline (before narrator). Reads map config
from state and maintains _location_state across turns.

Map config lives in state["map"]:
  {
    "start": "tavern",
    "order": ["tavern", "forest", "ruins"],
    "locations": {
      "tavern": {
        "name": "The Rusted Nail",
        "narrator_hint": "A dim, smoky tavern...",
        "opening_text": "You push through the heavy oak door...",
        "characters": ["barkeep"],
        "task": "Retrieve the stolen ledger",
        "task_criteria": "Player finds and returns the ledger",
        "min_turns": 2
      }
    }
  }

Runtime state lives in _location_state:
  {
    "current_location": "tavern",
    "current_task_index": 0,
    "completed_tasks": [],
    "task_complete_current": False,
    "turns_at_location": 0,
    "just_arrived": False,
    "quest_complete": False
  }
"""

import logging

logger = logging.getLogger(__name__)

MOVE_KEYWORDS = [
    "leave", "move on", "head out", "depart", "continue on",
    "travel", "move forward", "next location", "press on",
    "go to the next", "set out", "head to", "venture forth",
    "walk out", "step outside", "hit the road", "go to the",
]


def _find_target_location(message: str, locations: dict, current_key: str) -> str | None:
    """Find which location the player wants to go to by matching names/keys."""
    lower = message.lower()
    for loc_key, loc in locations.items():
        if loc_key == current_key:
            continue
        if not isinstance(loc, dict):
            continue
        loc_name = (loc.get("name") or "").lower()
        if loc_key.lower() in lower or (loc_name and loc_name in lower):
            return loc_key
    return None


def _wants_to_move(message: str, locations: dict, current_key: str) -> tuple[bool, str | None]:
    """Check if player wants to move. Returns (wants_move, target_key)."""
    lower = message.lower()
    # First check if they mention a specific location
    target = _find_target_location(message, locations, current_key)
    if target:
        return True, target
    # Then check generic move keywords
    if any(kw in lower for kw in MOVE_KEYWORDS):
        return True, None
    return False, None


def location_node(state: dict) -> dict:
    """Manage player location, swap characters, build narrator hints."""
    map_data = state.get("map") or {}
    if not map_data:
        return {}

    locations = map_data.get("locations", {})
    order = map_data.get("order", [])
    if not locations or not order:
        return {}

    all_chars = state.get("_all_characters") or {}
    loc_state = dict(state.get("_location_state") or {})
    message = (state.get("message") or "").strip()

    # --- Initialize on first turn ---
    if not loc_state.get("current_location"):
        start_key = map_data.get("start", order[0])
        loc_state = {
            "current_location": start_key,
            "current_task_index": 0,
            "completed_tasks": [],
            "task_complete_current": False,
            "turns_at_location": 0,
            "just_arrived": True,
            "quest_complete": False,
        }
        logger.info("Location: initialized at '%s'", start_key)

    current_key = loc_state["current_location"]
    current_loc = locations.get(current_key, {})

    # --- Current task info ---
    task_index = loc_state.get("current_task_index", 0)
    task_location_key = order[task_index] if task_index < len(order) else None
    task_location = locations.get(task_location_key, {}) if task_location_key else {}

    # --- Detect movement intent (free movement) ---
    if message:
        wants_move, target_key = _wants_to_move(message, locations, current_key)
    else:
        wants_move, target_key = False, None

    if wants_move:
        # Determine where to go
        dest_key = target_key
        if not dest_key:
            # Generic move keyword without specific target — no-op, narrator can ask where
            dest_key = None

        if dest_key and dest_key != current_key and dest_key in locations:
            loc_state["current_location"] = dest_key
            loc_state["turns_at_location"] = 0
            loc_state["just_arrived"] = True
            current_key = dest_key
            current_loc = locations.get(current_key, {})
            logger.info("Location: moved to '%s'", dest_key)

    # --- Advance task when current task is complete ---
    if loc_state.get("task_complete_current") and not loc_state.get("quest_complete"):
        next_index = task_index + 1
        if next_index >= len(order):
            loc_state["quest_complete"] = True
            logger.info("Location: quest complete — all tasks done")
        else:
            loc_state["current_task_index"] = next_index
            loc_state["task_complete_current"] = False
            task_index = next_index
            task_location_key = order[task_index]
            task_location = locations.get(task_location_key, {})
            logger.info("Location: advanced to task %d at '%s'", next_index, task_location_key)

    # --- Swap characters: only show NPCs at the current task's location ---
    if current_key == task_location_key and not loc_state.get("quest_complete"):
        active_char_keys = current_loc.get("characters", [])
        active_characters = {k: all_chars[k] for k in active_char_keys if k in all_chars}
    else:
        # Player is not at the task location — room is empty
        active_characters = {}

    # --- Build narrator hints ---
    narrator_hints = []

    # Read task hint from previous turn's task node
    prev_task_hint = (state.get("_task_narrator_hint") or "").strip()

    if loc_state.get("just_arrived"):
        narrator_hints.append(
            f"The player has just arrived at {current_loc.get('name', current_key)}. "
            f"{current_loc.get('narrator_hint', '')} "
            f"Describe this new location vividly."
        )
        opening = current_loc.get("opening_text", "")
        if opening:
            narrator_hints.append(f"Opening scene context: {opening}")
    else:
        narrator_hints.append(
            f"Current location: {current_loc.get('name', current_key)}. "
            f"{current_loc.get('narrator_hint', '')}"
        )

    # Indicate if the room is empty (not the task location)
    if current_key != task_location_key and not loc_state.get("quest_complete"):
        task_loc_name = task_location.get("name", task_location_key)
        narrator_hints.append(
            f"This location is quiet and empty right now. "
            f"The player's current objective is elsewhere."
        )

    if loc_state.get("quest_complete"):
        narrator_hints.append(
            "The player has completed their final objective and the quest is over. "
            "Narrate a sense of accomplishment and conclusion."
        )

    if prev_task_hint:
        narrator_hints.append(prev_task_hint)

    # --- Build location info for other nodes / UI ---
    # Show the current task (which may be at a different location)
    current_task_text = task_location.get("task", "") if not loc_state.get("quest_complete") else ""
    location_info = {
        "key": current_key,
        "name": current_loc.get("name", current_key),
        "task": current_task_text,
        "task_location": task_location_key,
        "task_complete": loc_state.get("task_complete_current", False),
        "is_first_turn": loc_state.get("just_arrived", False),
    }

    # --- Update turn counter and clear just_arrived ---
    loc_state["turns_at_location"] = loc_state.get("turns_at_location", 0) + 1
    clear_arrived = loc_state.get("just_arrived", False)

    results = {
        "characters": active_characters,
        "_location": location_info,
        "_location_state": loc_state,
        "_narrator_location_hint": "\n".join(narrator_hints),
    }

    if clear_arrived:
        loc_state["just_arrived"] = False

    return results
