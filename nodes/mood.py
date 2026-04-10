"""Mood node — tracks NPC mood shifts across named axes via LLM.

Reads _narrator_text and _character_responses for this turn's context.
Rates each axis 1-10 directly.
"""

import logging
import re

from llm import get_llm
from llm.text import llm_result_to_text
from nodes.history_util import get_recent_context

logger = logging.getLogger(__name__)


def mood_node(state: dict) -> dict:
    """For each character's mood axis, ask the LLM to rate it 1-10."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    history = state.get("history") or []
    context_text = get_recent_context(history, count=3)
    memory_summary = (state.get("memory_summary") or "").strip()
    summary_block = f"Story so far: {memory_summary}\n\n" if memory_summary else ""
    player_message = state.get("message", "")

    # Current turn context from structured fields
    narrator_text = (state.get("_narrator_text") or "").strip()
    char_responses = state.get("_character_responses") or {}

    updated_characters = dict(characters)

    for npc_key, npc in characters.items():
        if not isinstance(npc, dict):
            continue

        moods = npc.get("moods")
        if not isinstance(moods, list) or not moods:
            continue

        from model_resolver import get_model_for_role
        char_model = npc.get("model", "")
        model = get_model_for_role("classification", character_override=char_model)

        try:
            llm = get_llm(model)
        except Exception as e:
            logger.error(f"Failed to get LLM for {npc_key}: {e}")
            continue

        label = npc_key.replace("_", " ").title()
        npc_prompt = (npc.get("prompt") or "").strip()
        personality_line = f"\nCharacter personality: {npc_prompt}" if npc_prompt else ""

        # This character's response this turn
        char_resp = char_responses.get(npc_key, {})
        turn_summary = ""
        if narrator_text:
            turn_summary += f"Scene: {narrator_text}\n"
        if isinstance(char_resp, dict):
            if char_resp.get("dialogue"):
                turn_summary += f"{label} said: {char_resp['dialogue']}\n"
            if char_resp.get("action"):
                turn_summary += f"{label} did: {char_resp['action']}\n"

        updated_moods = []

        for axis in moods:
            if not isinstance(axis, dict):
                updated_moods.append(axis)
                continue

            axis_name = axis.get("axis", "mood")
            low_label = axis.get("low", "low")
            high_label = axis.get("high", "high")
            value = int(axis.get("value", 5))

            prompt = f"""Rate a character's emotional state after this scene on a scale of 1-10.
{personality_line}

Character: {label}
Emotion: {axis_name} (1 = {low_label}, 10 = {high_label})
Previous value: {value}/10

What just happened:
Player: {player_message}
{turn_summary}

{summary_block}Previous context:
{context_text}

Based on the scene above, what should {label}'s {axis_name} be NOW? Consider:
- Flirting, bonding, compliments, physical closeness, shared laughter → higher
- Rejection, lies, conflict, distance, betrayal → lower
- If nothing changed this emotion, keep it the same

Reply with ONLY a single number from 1 to 10:"""

            try:
                result = llm_result_to_text(llm.invoke(prompt)).strip()
                numbers = re.findall(r'\b(\d+)\b', result)
                if numbers:
                    parsed = int(numbers[0])
                    new_value = max(1, min(10, parsed))
                else:
                    new_value = value
                    logger.warning(f"Mood: could not parse number from '{result}' for {npc_key}/{axis_name}")

                updated_moods.append({
                    "axis": axis_name,
                    "low": low_label,
                    "high": high_label,
                    "value": new_value,
                })
            except Exception as e:
                logger.error(f"Mood axis error for {npc_key}/{axis_name}: {e}")
                updated_moods.append(axis)

        updated_npc = dict(npc)
        updated_npc["moods"] = updated_moods
        updated_characters[npc_key] = updated_npc

    return {"characters": updated_characters}
