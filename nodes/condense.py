"""Condense node — rolling memory summary via LLM."""

import logging

from config import DEFAULT_MODEL
from llm import get_llm

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

    model = state.get("narrator", {}).get("model", DEFAULT_MODEL)
    if model == "default":
        model = DEFAULT_MODEL

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Condense node: could not get LLM: {e}")
        return {}

    prompt = f"""You are a story memory manager. Your job is to maintain a concise summary of everything important that has happened in this story.

Current summary:
{summary_placeholder}

Recent raw turns (last 3 completed exchanges):
{recent_block}

New events to incorporate:
{current_turn}

Update the summary to include any important new information from the new events. Rules:
- Keep the summary under 100 words
- Focus on: key facts, relationship developments, promises made, things characters revealed, emotional shifts, milestone moments
- Drop: scenery descriptions, small talk, redundant details
- Write in past tense, third person
- If the summary is getting long, compress older details to make room for new ones

Updated summary:

"""

    try:
        raw = llm.invoke(prompt)
        text = (raw or "").strip() if isinstance(raw, str) else str(raw).strip()
        if not text:
            return {}
        return {"memory_summary": text}
    except Exception as e:
        logger.error(f"Condense node error: {e}")
        return {}
