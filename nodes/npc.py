"""NPC node — each character responds in character via LLM."""

import logging

from config import DEFAULT_MODEL
from llm import get_llm

logger = logging.getLogger(__name__)


def npc_node(state: dict) -> dict:
    """Generate dialogue for each character. Appends to response."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    player = state.get("player") or {}
    player_name = player.get("name", "Adventurer")
    narrator_beat = (state.get("response") or "").strip()
    history = state.get("history") or []
    recent = history[-2:] if len(history) > 2 else history
    context_text = "\n\n".join(recent) if recent else ""

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

        model = npc.get("model", DEFAULT_MODEL)
        if model == "default":
            model = DEFAULT_MODEL

        try:
            llm = get_llm(model)
        except Exception as e:
            logger.error(f"Failed to get LLM for {npc_key}: {e}")
            continue

        mood = npc.get("mood", 5)

        prompt = f"""{npc_prompt}

You are speaking to {player_name}. {player.get("background", "")}
Current mood: {mood}/10

What the narrator just established in this scene (stay consistent; react naturally):
{narrator_beat}

{summary_block}Context:
{context_text}

{player_name} just said: {state.get("message", "")}

Respond as {npc_key.replace("_", " ").title()} in one or two short sentences:"""

        try:
            npc_response = llm.invoke(prompt)
            label = npc_key.replace("_", " ").title()
            responses.append(f"{label}: {npc_response.strip()}")
        except Exception as e:
            logger.error(f"NPC response error for {npc_key}: {e}")

    if not responses:
        return {}

    full_response = state.get("response", "")
    full_response = f"{full_response}\n\n" + "\n\n".join(responses)
    return {"response": full_response}
