"""Progression node — tracks NPC-driven relationship/story stage progression.

Reads each character's progression config and current stage from state.
Checks if conditions are met to advance (turn count, mood thresholds).
Writes _progression with per-character stage directives for character_agent
and _narrator_progression with pacing hints for the narrator.

Stage config lives in characters[key].progression:
  {
    "stages": ["meet", "chat", "flirt", "kiss", ...],
    "min_turns_per_stage": [1, 2, 2, 1, ...],
    "advance_threshold": {"trust": 6, "attraction": 7},
    "initiator": true,
    "style": "teasing",
    "stage_directives": {
      "meet": "Introduce yourself, be friendly, find common ground",
      "chat": "Open up, share personal details, find excuses to be near the player",
      ...
    }
  }

Runtime state lives in _progression_state:
  {
    "character_key": {"stage_index": 0, "turns_in_stage": 3}
  }
"""

import logging

from llm import get_llm
from llm.text import llm_result_to_text
from model_resolver import get_model_for_role

logger = logging.getLogger(__name__)


def _check_player_action(
    player_message: str,
    narrator_text: str,
    char_responses: dict,
    criteria: str,
    char_key: str,
) -> bool:
    """Ask the LLM: did the player's action meet the advancement criteria?"""
    if not player_message:
        return False

    # Build context from the turn
    context_parts = []
    if player_message:
        context_parts.append(f"Player said: {player_message}")
    if narrator_text:
        context_parts.append(f"Scene: {narrator_text[:200]}")
    turn_context = "\n".join(context_parts)

    prompt = f"""You are evaluating whether a player's action in a story meets a specific criteria.

What the player did this turn:
{turn_context}

Criteria to advance to the next stage:
"{criteria}"

Does the player's action meet this criteria? Consider what they said and did — not what the narrator or NPCs said.
Answer with ONLY "YES" or "NO"."""

    try:
        model = get_model_for_role("classification")
        llm = get_llm(model)
        raw = llm_result_to_text(llm.invoke(prompt)).strip().upper()
        result = raw.startswith("YES")
        logger.info("Progression check %s: criteria=%r → %s (raw=%r)",
                     char_key, criteria[:50], result, raw[:20])
        return result
    except Exception as e:
        logger.error("Progression check failed for %s: %s", char_key, e)
        return False


def progression_node(state: dict) -> dict:
    """Check and advance progression stages for each character."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    # Player's action this turn
    message = (state.get("message") or "").strip()
    narrator_text = (state.get("_narrator_text") or "").strip()
    char_responses = state.get("_character_responses") or {}

    # Load or initialize progression state
    prog_state = dict(state.get("_progression_state") or {})
    turn_count = state.get("turn_count", 0)

    progression = {}
    narrator_hints = []
    state_changed = False

    for char_key, char in characters.items():
        if not isinstance(char, dict):
            continue

        config = char.get("progression")
        if not config or not isinstance(config, dict):
            continue

        stages = config.get("stages", [])
        if not stages:
            continue

        # Get or initialize this character's progression state
        char_prog = prog_state.get(char_key, {})
        stage_index = char_prog.get("stage_index", 0)
        turns_in_stage = char_prog.get("turns_in_stage", 0)

        # Clamp to valid range
        if stage_index >= len(stages):
            stage_index = len(stages) - 1

        current_stage = stages[stage_index]

        # Check if we should advance
        advanced = False
        if stage_index < len(stages) - 1:
            # FLOOR: minimum turns in this stage must be met
            min_turns = config.get("min_turns_per_stage", [])
            min_for_current = min_turns[stage_index] if stage_index < len(min_turns) else 2
            turns_met = turns_in_stage >= min_for_current

            # PLAYER ACTION GATE: check if the player's words/actions
            # meet the criteria for advancing past this stage
            advance_criteria = config.get("advance_when", {})
            criteria = advance_criteria.get(current_stage, "")

            player_earned = False
            if turns_met and criteria:
                player_earned = _check_player_action(
                    message, narrator_text, char_responses, criteria, char_key
                )
            elif turns_met and not criteria:
                # No criteria defined — fall back to mood thresholds
                thresholds = config.get("advance_threshold", {})
                if thresholds:
                    char_moods = char.get("moods", [])
                    player_earned = True
                    for axis_name, required_val in thresholds.items():
                        for mood_axis in char_moods:
                            if isinstance(mood_axis, dict) and mood_axis.get("axis") == axis_name:
                                if mood_axis.get("value", 5) < required_val:
                                    player_earned = False
                                break
                else:
                    # No criteria AND no thresholds — advance on turn count alone
                    player_earned = True

            if player_earned:
                stage_index += 1
                current_stage = stages[stage_index]
                turns_in_stage = 0
                advanced = True
                state_changed = True
                logger.info("Progression %s: player earned advance to '%s' (index %d)",
                            char_key, current_stage, stage_index)

        # Increment turns in stage
        turns_in_stage += 1
        prog_state[char_key] = {
            "stage_index": stage_index,
            "turns_in_stage": turns_in_stage,
        }
        state_changed = True

        # Build directive for this character
        player_name = (state.get("player") or {}).get("name", "the player")

        directives = config.get("stage_directives", {})
        directive = directives.get(current_stage, f"You are in the {current_stage} stage.")
        directive = directive.replace("{player}", player_name)

        # Add initiator/style context
        initiator = config.get("initiator", False)
        style = config.get("style", "")
        pace = config.get("pace", "")

        context_parts = [f"STAGE: {current_stage.upper()} (turn {turns_in_stage} of this stage)"]
        context_parts.append(f"DIRECTIVE: {directive}")
        context_parts.append("Avoid repeating earlier beats — find a new angle on the same emotional territory.")
        if initiator:
            context_parts.append(f"You are the INITIATOR — you drive the interaction forward. Don't wait for {player_name} to lead.")
        if style:
            context_parts.append(f"STYLE: {style}")
        if pace:
            context_parts.append(f"PACE: {pace}")
        if advanced:
            context_parts.append("You have just advanced to a new stage. Mark this transition in your behavior — something has shifted.")

        # Stage boundary warning
        next_stage = stages[stage_index + 1] if stage_index + 1 < len(stages) else None
        if next_stage:
            context_parts.append(f"Do NOT skip ahead to the '{next_stage}' stage. Stay in '{current_stage}' until the moment is right.")

        progression[char_key] = "\n".join(context_parts)

        narrator_hint_map = config.get("stage_narrator_hints", {})
        hint = narrator_hint_map.get(current_stage, "")
        if hint:
            label = char_key.replace("_", " ").title()
            narrator_hints.append(f"{label} ({current_stage}): {hint}")

    results = {}
    if progression:
        results["_progression"] = progression
    if narrator_hints:
        results["_narrator_progression"] = "\n".join(narrator_hints)
    if state_changed:
        results["_progression_state"] = prog_state

    return results
