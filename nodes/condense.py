"""Condense node — rolling memory summary via LLM."""

import logging

from llm import get_llm
from llm.text import llm_result_to_text

logger = logging.getLogger(__name__)


def condense_node(state: dict) -> dict:
    """Summarize recent turns into memory_summary. One LLM call."""
    history = state.get("history") or []
    memory_summary = (state.get("memory_summary") or "").strip()
    current_turn = f"Player: {state.get('message', '')}\n{state.get('response', '')}"

    # Nothing to summarize if no history and no current turn content
    if not history and not state.get("response"):
        return {}

    summary_placeholder = (
        memory_summary
        if memory_summary
        else "No summary yet — this is the beginning of the story."
    )

    recent_raw = history[-3:]
    recent_block = "\n\n".join(recent_raw) if recent_raw else ""

    from model_resolver import get_model_for_role
    story_model = state.get("narrator", {}).get("model", "")
    model = get_model_for_role("summarization", story_override=story_model)

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Condense node: could not get LLM: {e}")
        return {}

    # Story context for accurate summarization
    from nodes.story_context import build_story_context
    story_context = build_story_context(state)
    story_line = f"\nStory context: {story_context}\n" if story_context else ""

    prompt = f"""You are a story memory manager. Your job is to maintain a concise summary of everything important that has happened in this story.
{story_line}
Current summary:
{summary_placeholder}

Recent raw turns (last 3 completed exchanges):
{recent_block}

New events to incorporate:
{current_turn}

Rewrite the summary incorporating new events. You MUST follow these rules:
- HARD LIMIT: 60-80 words. Count your words. If over 80, delete sentences until under 80.
- When adding new info, REPLACE older details with shorter versions — do not just append
- Focus on: key facts, relationship status, secrets revealed, emotional turning points
- Drop: scenery, exact dialogue, small talk, redundant details, character greetings
- Write in past tense, third person
- Return ONLY the summary text — no labels, no word counts, no commentary

Updated summary:"""

    try:
        raw = llm.invoke(prompt)
        text = llm_result_to_text(raw).strip()
        if not text:
            return {}

        # Clean up common LLM meta-text artifacts
        for prefix in [
            "here is the updated summary:",
            "updated summary:",
            "here's the updated summary:",
            "summary:",
        ]:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()

        # Strip wrapping quotes if the model added them
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()

        if not text:
            return {}

        logger.info("Condense: %s", text[:100])
        return {"memory_summary": text}
    except Exception as e:
        logger.error(f"Condense node error: {e}")
        return {}
