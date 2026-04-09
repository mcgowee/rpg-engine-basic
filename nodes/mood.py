"""Mood node — tracks NPC mood shifts across named axes via LLM."""

import logging

from config import DEFAULT_MODEL
from llm import get_llm
from llm.text import llm_result_to_text

logger = logging.getLogger(__name__)


def mood_node(state: dict) -> dict:
    """For each character's mood axis, ask the LLM if it goes UP, DOWN, or SAME."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    history = state.get("history") or []
    recent = history[-2:] if len(history) > 2 else history
    context_text = "\n\n".join(recent) if recent else ""
    memory_summary = (state.get("memory_summary") or "").strip()
    summary_block = f"Story so far: {memory_summary}\n\n" if memory_summary else ""
    player_message = state.get("message", "")

    updated_characters = dict(characters)

    for npc_key, npc in characters.items():
        if not isinstance(npc, dict):
            continue

        moods = npc.get("moods")
        if not isinstance(moods, list) or not moods:
            # Fallback: legacy single mood field
            _update_single_mood(npc_key, npc, state, updated_characters, summary_block, context_text)
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
        updated_moods = []

        for axis in moods:
            if not isinstance(axis, dict):
                updated_moods.append(axis)
                continue

            axis_name = axis.get("axis", "mood")
            low_label = axis.get("low", "low")
            high_label = axis.get("high", "high")
            value = int(axis.get("value", 5))

            npc_prompt = (npc.get("prompt") or "").strip()
            personality_line = f"\nCharacter personality: {npc_prompt}" if npc_prompt else ""

            narrator_response = (state.get("response") or "").strip()
            response_snippet = narrator_response[:500] if narrator_response else ""

            prompt = f"""Rate a character's emotional state after this scene on a scale of 1-10.
{personality_line}

Character: {label}
Emotion: {axis_name} (1 = {low_label}, 10 = {high_label})
Previous value: {value}/10

What just happened:
Player: {player_message}
Scene: {response_snippet}

{summary_block}
Based on the scene above, what should {label}'s {axis_name} be NOW? Consider:
- Flirting, bonding, compliments, physical closeness, shared laughter → higher
- Rejection, lies, conflict, distance, betrayal → lower
- If nothing changed this emotion, keep it the same

Reply with ONLY a single number from 1 to 10:"""

            try:
                result = llm_result_to_text(llm.invoke(prompt)).strip()
                # Extract first number found in response
                import re
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


def _update_single_mood(npc_key, npc, state, updated_characters, summary_block, context_text):
    """Fallback for characters with a single mood number instead of axes."""
    from model_resolver import get_model_for_role
    current_mood = npc.get("mood", 5)
    char_model = npc.get("model", "")
    model = get_model_for_role("classification", character_override=char_model)

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Failed to get LLM for {npc_key}: {e}")
        return

    label = npc_key.replace("_", " ").title()

    prompt = f"""You are evaluating how a character's mood should change after a conversation exchange.

Character: {label} (current mood: {current_mood}/10)
Player action: {state.get("message", "")}

{summary_block}Context:
{context_text}

Based on the player's action, should {label}'s mood go up, down, or stay the same?
Reply with ONLY one word: UP, DOWN, or SAME."""

    try:
        result = llm_result_to_text(llm.invoke(prompt)).strip().upper()
        if "UP" in result:
            new_mood = min(10, current_mood + 1)
        elif "DOWN" in result:
            new_mood = max(1, current_mood - 1)
        else:
            new_mood = current_mood

        updated_npc = dict(npc)
        updated_npc["mood"] = new_mood
        updated_characters[npc_key] = updated_npc
    except Exception as e:
        logger.error(f"Mood update error for {npc_key}: {e}")
