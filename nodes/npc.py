"""NPC node — each character responds in character via LLM."""

import logging

from config import (
    DEFAULT_MODEL,
    PROMPT_HISTORY_ENTRY_MAX_CHARS,
    PROMPT_NPC_HISTORY_CONTEXT_MAX_CHARS,
    PROMPT_NPC_NARRATOR_BEAT_MAX_CHARS,
)
from llm import get_llm
from llm.text import llm_result_to_text
from nodes.prompt_trim import truncate_prompt_text

logger = logging.getLogger(__name__)


def npc_node(state: dict) -> dict:
    """Generate dialogue for each character. Appends to response."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    player = state.get("player") or {}
    player_name = player.get("name", "Adventurer")
    narrator_beat = truncate_prompt_text(
        (state.get("response") or "").strip(),
        PROMPT_NPC_NARRATOR_BEAT_MAX_CHARS,
    )
    history = state.get("history") or []
    recent = history[-2:] if len(history) > 2 else history
    lim = (
        PROMPT_NPC_HISTORY_CONTEXT_MAX_CHARS
        if PROMPT_NPC_HISTORY_CONTEXT_MAX_CHARS > 0
        else PROMPT_HISTORY_ENTRY_MAX_CHARS
    )
    trimmed = [truncate_prompt_text(entry, lim) for entry in recent]
    context_text = "\n\n".join(trimmed) if trimmed else ""

    memory_summary = (state.get("memory_summary") or "").strip()
    summary_block = f"Story so far: {memory_summary}\n\n" if memory_summary else ""

    responses = []
    for npc_key, npc in characters.items():
        if not isinstance(npc, dict):
            continue

        npc_prompt = (npc.get("prompt") or "").strip()
        if not npc_prompt:
            label = npc_key.replace("_", " ").title()
            npc_prompt = f"You are {label}. Stay in character. Reply in one or two short sentences."

        from model_resolver import get_model_for_role
        char_model = npc.get("model", "")
        model = get_model_for_role("dialogue", character_override=char_model)

        try:
            llm = get_llm(model)
        except Exception as e:
            logger.error(f"Failed to get LLM for {npc_key}: {e}")
            continue

        # Build mood context — axes or legacy single mood
        moods = npc.get("moods")
        if isinstance(moods, list) and moods:
            mood_lines = []
            for axis in moods:
                if not isinstance(axis, dict):
                    continue
                name = axis.get("axis", "mood")
                val = axis.get("value", 5)
                low = axis.get("low", "low")
                high = axis.get("high", "high")
                leaning = low if val <= 5 else high
                mood_lines.append(f"- {name}: {val}/10 (leaning {leaning})")
            mood_block = "Current emotional state:\n" + "\n".join(mood_lines) if mood_lines else "Current mood: neutral"
        else:
            mood = npc.get("mood", 5)
            mood_block = f"Current mood: {mood}/10"

        prompt = f"""{npc_prompt}

You are speaking to {player_name}. {player.get("background", "")}
{mood_block}

What the narrator just established in this scene (stay consistent; react naturally):
{narrator_beat}

{summary_block}Context:
{context_text}

{player_name} just said: {state.get("message", "")}

Respond as {npc_key.replace("_", " ").title()} in one or two short sentences:"""

        try:
            npc_response = llm_result_to_text(llm.invoke(prompt))
            label = npc_key.replace("_", " ").title()
            responses.append(f"{label}: {npc_response.strip()}")
        except Exception as e:
            logger.error(f"NPC response error for {npc_key}: {e}")

    if not responses:
        return {}

    full_response = state.get("response", "")
    full_response = f"{full_response}\n\n" + "\n\n".join(responses)
    return {"response": full_response}
