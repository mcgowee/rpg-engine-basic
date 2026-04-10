"""Narrator node — describes the world, scene, events, consequences.

NEVER writes dialogue for characters — they speak independently via character_agent.
Outputs to _narrator_text which character_agent and response_builder read.
"""

import logging

from llm import get_llm
from llm.text import llm_result_to_text
from nodes.history_util import get_recent_narrator, get_recent_dialogue_all
from nodes.story_context import build_story_context

logger = logging.getLogger(__name__)


def narrator_node(state: dict) -> dict:
    """Describe what happens in the world. No character dialogue."""
    message = (state.get("message") or "").strip()
    memory_summary = (state.get("memory_summary") or "").strip()
    history = state.get("history") or []
    player = state.get("player") or {}
    characters = state.get("characters") or {}

    # Story context
    story_context = build_story_context(state)
    story_line = f"{story_context}\n" if story_context else ""

    # Character names for the "do not speak for" instruction
    char_names = [k.replace("_", " ").title() for k in characters.keys()]
    char_list = ", ".join(char_names) if char_names else "any characters"

    # Previous narrator entries — for continuity
    prev_narrator = get_recent_narrator(history, count=3)
    narrator_block = ""
    if prev_narrator:
        narrator_block = "Recent narration (for continuity):\n" + "\n".join(f"- {n}" for n in prev_narrator) + "\n"

    # Previous dialogue — so narrator knows what was said
    prev_dialogue = get_recent_dialogue_all(history, count=3)
    dialogue_block = ""
    if prev_dialogue:
        dialogue_block = "Recent dialogue:\n" + "\n".join(prev_dialogue) + "\n"

    summary_block = f"Story so far: {memory_summary}\n\n" if memory_summary else ""

    from model_resolver import get_model_for_role
    model = get_model_for_role("creative")

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Narrator: failed to get LLM: {e}")
        return {"_narrator_text": "[System error: Could not connect to LLM.]"}

    prompt = f"""You are the narrator for a story. Describe what happens in the world.

{story_line}Game: {state.get("game_title", "Untitled")}
Player: {player.get("name", "Adventurer")} — {player.get("background", "")}
Characters present: {char_list}

{summary_block}{narrator_block}{dialogue_block}
Player: {message}

Describe what happens next. Rules:
- Second person, present tense ("You walk into the room...")
- Describe environment, physical events, consequences of player actions
- CRITICAL: Do NOT write dialogue or quoted speech for {char_list}. They speak separately.
- You may describe their body language, expressions, and physical reactions
- 2-4 sentences, concise and atmospheric
- If this is a response to player action, show the result of that action

Narration:"""

    try:
        raw = llm_result_to_text(llm.invoke(prompt)).strip()

        # Clean up
        for prefix in ["Narration:", "narration:"]:
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()

        # Remove any dialogue the model snuck in (lines starting with quotes)
        lines = raw.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # Skip lines that look like character dialogue
            if stripped.startswith('"') and stripped.endswith('"'):
                continue
            if any(stripped.startswith(f"{name}:") for name in char_names):
                continue
            cleaned.append(line)
        raw = "\n".join(cleaned).strip()

        if not raw:
            raw = "..."

        logger.info("Narrator: %s", raw[:80])
        return {"_narrator_text": raw}

    except Exception as e:
        logger.error(f"Narrator error: {e}")
        return {"_narrator_text": "[The narrator failed to respond.]"}
