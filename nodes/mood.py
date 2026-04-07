"""Mood node — tracks NPC mood shifts across named axes via LLM."""

import logging

from config import DEFAULT_MODEL
from llm import get_llm

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

        model = npc.get("model", DEFAULT_MODEL)
        if model == "default":
            model = DEFAULT_MODEL

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

            prompt = f"""You are evaluating how a character's emotional state should change after a conversation exchange.

Character: {label}
Trait: {axis_name} (currently {value}/10, where 1 = {low_label} and 10 = {high_label})
Player action: {player_message}

{summary_block}Context:
{context_text}

Based on the player's action, should {label}'s {axis_name} go UP (toward {high_label}), DOWN (toward {low_label}), or SAME?
Reply with ONLY one word: UP, DOWN, or SAME."""

            try:
                result = llm.invoke(prompt).strip().upper()
                if "UP" in result:
                    new_value = min(10, value + 1)
                elif "DOWN" in result:
                    new_value = max(1, value - 1)
                else:
                    new_value = value

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
    current_mood = npc.get("mood", 5)
    model = npc.get("model", DEFAULT_MODEL)
    if model == "default":
        model = DEFAULT_MODEL

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
        result = llm.invoke(prompt).strip().upper()
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
