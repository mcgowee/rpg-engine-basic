"""Narrator node — main scene narration via LLM."""

import logging

from config import DEFAULT_MODEL
from llm import get_llm

logger = logging.getLogger(__name__)

DEFAULT_NARRATOR_PROMPT = (
    "You are the narrator for a text adventure. Describe scenes in second person. "
    "End each beat with: What do you do?"
)


def narrator_node(state: dict) -> dict:
    """Call the LLM with the narrator prompt and player's message."""
    player = state.get("player") or {}
    narrator = state.get("narrator") or {}
    model = narrator.get("model", DEFAULT_MODEL)
    if model == "default":
        model = DEFAULT_MODEL

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Failed to get LLM: {e}")
        return {"response": "[System error: Could not connect to LLM. Try again.]"}

    narrator_prompt = (narrator.get("prompt") or "").strip() or DEFAULT_NARRATOR_PROMPT

    # Build context — memory summary (compressed story so far) + last 2 raw turns
    memory_summary = (state.get("memory_summary") or "").strip()
    history = state.get("history") or []
    recent = history[-2:] if len(history) > 2 else history
    summary_block = f"Story so far: {memory_summary}\n\n" if memory_summary else ""
    recent_block = "\n\n".join(recent) if recent else ""
    context_text = summary_block + recent_block
    context_section = f"\nContext:\n{context_text}\n" if context_text.strip() else ""

    prompt = f"""{narrator_prompt}

Game: {state.get("game_title", "Untitled")}
Player: {player.get("name", "Adventurer")} — {player.get("background", "")}
{context_section}
Player just said: {state.get("message", "")}

Narrate what happens next:"""

    try:
        narration = llm.invoke(prompt)
        return {"response": narration}
    except Exception as e:
        logger.error(f"Narrator node error: {e}")
        return {"response": f"[The AI request failed. Try again later.]"}
