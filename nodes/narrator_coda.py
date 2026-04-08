"""Narrator coda — after NPC lines, add a short closing beat and player prompt."""

import logging

from config import DEFAULT_MODEL, PROMPT_NPC_NARRATOR_BEAT_MAX_CHARS
from llm import get_llm
from llm.text import llm_result_to_text
from nodes.prompt_trim import truncate_prompt_text

logger = logging.getLogger(__name__)

_CODA_INSTRUCTION = """\
After the narration and character lines above, add a brief closing (1–3 short sentences):
react to what was said, ground the moment in atmosphere or stakes, stay in second person for the player.
End with one clear invitation to act, e.g. "What do you do?" (match the story's style).

Rules:
- Do not repeat or paraphrase dialogue already shown above.
- Do not speak in any NPC's voice or add new quoted speech for them.
- Output ONLY this closing addition — no headings or labels."""


def narrator_coda_node(state: dict) -> dict:
    """Append narrator closing after NPC dialogue. No-op if there are no characters (misconfigured graph)."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    body = (state.get("response") or "").strip()
    if not body:
        return {}

    player = state.get("player") or {}
    narrator = state.get("narrator") or {}
    model = narrator.get("model", DEFAULT_MODEL)
    if model == "default":
        model = DEFAULT_MODEL

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error("narrator_coda: failed to get LLM: %s", e)
        return {
            "response": body + "\n\nWhat do you do?",
        }

    excerpt = truncate_prompt_text(body, max(PROMPT_NPC_NARRATOR_BEAT_MAX_CHARS, 4000))

    prompt = f"""{narrator.get("prompt") or ""}

Game: {state.get("game_title", "Untitled")}
Player: {player.get("name", "Adventurer")}

Turn so far:
---
{excerpt}
---

{_CODA_INSTRUCTION}"""

    try:
        coda = llm_result_to_text(llm.invoke(prompt)).strip()
        if not coda:
            return {"response": body + "\n\nWhat do you do?"}
        return {"response": f"{body}\n\n{coda}"}
    except Exception as e:
        logger.error("narrator_coda node error: %s", e)
        return {"response": body + "\n\nWhat do you do?"}
