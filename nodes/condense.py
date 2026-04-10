"""Condense node — rolling memory summary via LLM.

Reads structured turn history and current turn fields.
"""

import logging

from llm import get_llm
from llm.text import llm_result_to_text
from nodes.history_util import get_structured_context_for_condense
from nodes.story_context import build_story_context

logger = logging.getLogger(__name__)


def condense_node(state: dict) -> dict:
    """Summarize recent turns into memory_summary. One LLM call."""
    history = state.get("history") or []
    memory_summary = (state.get("memory_summary") or "").strip()

    # Build current turn from structured fields
    current_parts = []
    player_msg = (state.get("message") or "").strip()
    if player_msg:
        current_parts.append(f"Player said: {player_msg}")
    narrator = (state.get("_narrator_text") or "").strip()
    if narrator:
        current_parts.append(f"Narrator: {narrator}")
    char_responses = state.get("_character_responses") or {}
    for key, resp in char_responses.items():
        if isinstance(resp, dict):
            label = key.replace("_", " ").title()
            if resp.get("dialogue"):
                current_parts.append(f"{label} said: {resp['dialogue']}")
            if resp.get("action"):
                current_parts.append(f"{label} action: {resp['action']}")
    current_turn = "\n".join(current_parts)

    if not history and not current_turn:
        return {}

    summary_placeholder = (
        memory_summary
        if memory_summary
        else "No summary yet — this is the beginning of the story."
    )

    recent_block = get_structured_context_for_condense(history, count=3)

    from model_resolver import get_model_for_role
    model = get_model_for_role("summarization")

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Condense node: could not get LLM: {e}")
        return {}

    story_context = build_story_context(state)
    story_line = f"\nStory context: {story_context}\n" if story_context else ""

    prompt = f"""You are a story memory manager. Your job is to maintain a concise summary of everything important that has happened in this story.
{story_line}
Current summary:
{summary_placeholder}

Recent turns:
{recent_block}

New events to incorporate:
{current_turn}

Rewrite the summary incorporating new events. You MUST follow these rules:
- HARD LIMIT: 60-80 words. Count your words. If over 80, delete sentences until under 80.
- When adding new info, REPLACE older details with shorter versions — do not just append
- Focus on: key facts, relationship status, secrets revealed, emotional turning points
- Drop: scenery, exact dialogue, small talk, redundant details
- Write in past tense, third person
- Return ONLY the summary text — no labels, no word counts, no commentary

Updated summary:"""

    try:
        raw = llm.invoke(prompt)
        text = llm_result_to_text(raw).strip()
        if not text:
            return {}

        for prefix in [
            "here is the updated summary:",
            "updated summary:",
            "here's the updated summary:",
            "summary:",
        ]:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()

        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()

        if not text:
            return {}

        logger.info("Condense: %s", text[:100])
        return {"memory_summary": text}
    except Exception as e:
        logger.error(f"Condense node error: {e}")
        return {}
