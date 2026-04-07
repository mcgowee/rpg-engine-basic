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

    prompt = f"""{narrator_prompt}

Game: {state.get("game_title", "Untitled")}
Player: {player.get("name", "Adventurer")} — {player.get("background", "")}

Player just said: {state.get("message", "")}

Narrate what happens next:"""

    try:
        narration = llm.invoke(prompt)
        return {"response": narration, "turn_count": state.get("turn_count", 0) + 1}
    except Exception as e:
        logger.error(f"Narrator node error: {e}")
        return {"response": f"[The AI request failed. Try again later.]"}
