"""Task node — evaluates whether the player completed the current location's objective.

Runs after response_builder, before condense. Reads the current location's
task_criteria and evaluates recent player actions against it using an LLM
YES/NO classification (same pattern as progression._check_player_action).

On completion, sets task_complete_current in _location_state and writes
_task_narrator_hint so the narrator can hint at moving on next turn.
"""

import logging

from llm import get_llm
from llm.text import llm_result_to_text
from model_resolver import get_model_for_role

logger = logging.getLogger(__name__)


def _evaluate_task(turn_context: str, task: str, task_criteria: str, location_name: str) -> bool:
    """Ask the LLM: has the player completed the task at this location?"""
    prompt = f"""You are evaluating whether a quest objective has been achieved in a story.

Location: {location_name}
Objective: {task}
Completion criteria: {task_criteria}

Recent events at this location:
{turn_context}

Based on what has happened, has the completion criteria been met?
Consider the overall arc of events, not just the latest turn.
Answer with ONLY "YES" or "NO"."""

    try:
        model = get_model_for_role("classification")
        llm = get_llm(model)
        raw = llm_result_to_text(llm.invoke(prompt)).strip().upper()
        result = raw.startswith("YES")
        logger.info("Task check at %s: criteria=%r → %s (raw=%r)",
                     location_name, task_criteria[:50], result, raw[:20])
        return result
    except Exception as e:
        logger.error("Task check failed at %s: %s", location_name, e)
        return False


def task_node(state: dict) -> dict:
    """Evaluate task completion at the current location."""
    map_data = state.get("map") or {}
    loc_state = state.get("_location_state") or {}
    if not map_data or not loc_state:
        return {}

    current_key = loc_state.get("current_location", "")
    locations = map_data.get("locations", {})
    order = map_data.get("order", [])

    # Already complete — nothing to evaluate
    if loc_state.get("task_complete_current", False):
        return {}

    # Find the current task's location (may differ from player's location)
    task_index = loc_state.get("current_task_index", 0)
    task_location_key = order[task_index] if task_index < len(order) else None
    if not task_location_key:
        return {}

    # Only evaluate when player is at the task's location
    if current_key != task_location_key:
        return {}

    task_loc = locations.get(task_location_key, {})
    if not task_loc:
        return {}

    task_criteria = (task_loc.get("task_criteria") or "").strip()
    task_text = (task_loc.get("task") or "").strip()
    location_name = task_loc.get("name", task_location_key)

    # No criteria means auto-complete (pure exploration locations)
    if not task_criteria:
        updated = dict(loc_state)
        updated["task_complete_current"] = True
        if task_location_key not in updated.get("completed_tasks", []):
            updated["completed_tasks"] = list(updated.get("completed_tasks", [])) + [task_location_key]
        return {
            "_location_state": updated,
            "_task_narrator_hint": "The player is free to move on whenever they choose.",
        }

    # Minimum turns gate
    min_turns = task_loc.get("min_turns", 1)
    turns_here = loc_state.get("turns_at_location", 0)
    if turns_here < min_turns:
        return {}

    # Build context from recent history at this location + current turn
    context_parts = []

    history = state.get("history") or []
    recent = history[-turns_here:] if turns_here > 0 else []
    for turn in recent[-4:]:  # Last 4 turns max
        if isinstance(turn, dict):
            if turn.get("player"):
                context_parts.append(f"Player: {turn['player']}")
            if turn.get("narrator"):
                context_parts.append(f"Scene: {turn['narrator'][:150]}")
            for ck, cr in (turn.get("characters") or {}).items():
                if isinstance(cr, dict) and cr.get("dialogue"):
                    label = ck.replace("_", " ").title()
                    context_parts.append(f"{label}: {cr['dialogue'][:100]}")

    # Current turn (not yet in history)
    player_msg = (state.get("message") or "").strip()
    narrator_text = (state.get("_narrator_text") or "").strip()
    if player_msg:
        context_parts.append(f"Player (this turn): {player_msg}")
    if narrator_text:
        context_parts.append(f"Scene (this turn): {narrator_text[:150]}")
    char_responses = state.get("_character_responses") or {}
    for ck, cr in char_responses.items():
        if isinstance(cr, dict) and cr.get("dialogue"):
            label = ck.replace("_", " ").title()
            context_parts.append(f"{label} (this turn): {cr['dialogue'][:100]}")

    turn_context = "\n".join(context_parts)
    if not turn_context.strip():
        return {}

    # LLM evaluation
    task_done = _evaluate_task(turn_context, task_text, task_criteria, location_name)

    if task_done:
        updated = dict(loc_state)
        updated["task_complete_current"] = True
        if task_location_key not in updated.get("completed_tasks", []):
            updated["completed_tasks"] = list(updated.get("completed_tasks", [])) + [task_location_key]

        # Check if this was the last location
        order = map_data.get("order", [])
        if len(updated["completed_tasks"]) >= len(order):
            return {
                "_location_state": updated,
                "_task_narrator_hint": (
                    "The player has completed their final objective. The quest is complete! "
                    "Narrate a sense of accomplishment and conclusion."
                ),
            }

        return {
            "_location_state": updated,
            "_task_narrator_hint": (
                f"The player has completed their objective at {location_name}. "
                f"Subtly hint that they can now move on to the next destination."
            ),
        }

    return {}
