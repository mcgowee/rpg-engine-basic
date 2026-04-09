"""Quality guard node — analyzes recent turns and injects dynamic narrator instructions.

Runs BEFORE the narrator. Reads history, detects patterns (repetition, passivity,
stagnation), and adds instructions to state["_narrator_guidance"] which the narrator
node reads and includes in its prompt.
"""

import logging

from config import DEFAULT_MODEL
from llm import get_llm
from llm.text import llm_result_to_text
from model_resolver import get_model_for_role

logger = logging.getLogger(__name__)


def quality_guard_node(state: dict) -> dict:
    """Analyze recent history and generate dynamic narrator guidance."""
    history = state.get("history") or []
    message = state.get("message", "")
    memory_summary = state.get("memory_summary", "")

    # Not enough history to analyze — skip on first few turns
    if len(history) < 2:
        return {}

    # Extract recent turns for analysis
    recent = history[-4:] if len(history) > 4 else history
    recent_text = "\n\n".join(recent)

    # Build analysis prompt — ask the LLM to detect issues
    model = get_model_for_role("classification")
    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Quality guard: failed to get LLM: {e}")
        return {}

    prompt = f"""You are a creative writing coach helping improve a text adventure story. Read the recent turns and suggest what should happen NEXT to make the story more exciting.

Recent story turns:
{recent_text[:1500]}

The player is about to say: {message}

Story summary: {memory_summary[:300]}

Your task: Write 1-3 short creative directions for what should happen next. Each direction should make the story MORE interesting. Think about:
- Has the story been covering the same ground? If so, suggest a NEW direction.
- Has nothing surprising happened recently? Suggest a twist or interruption.
- Are characters repeating themselves? Suggest a revelation or conflict.
- Is the mood stuck? Suggest a tonal shift.

Write each direction on its own line starting with a dash. Be specific and creative.
If the story is already exciting and varied, write: NONE

Directions:"""

    try:
        raw = llm_result_to_text(llm.invoke(prompt)).strip()

        # Check if the guard says everything is fine
        if raw.upper().startswith("NONE") or raw.upper() == "NONE":
            logger.info("Quality guard: no issues detected")
            return {}

        # Clean up — only keep lines starting with -
        lines = [l.strip() for l in raw.split("\n") if l.strip().startswith("-")]
        if not lines:
            # Try to use the whole response if no dashes
            lines = [l.strip() for l in raw.split("\n") if l.strip() and len(l.strip()) > 10]

        if not lines:
            return {}

        # Limit to 3 instructions max
        guidance = "\n".join(lines[:3])
        logger.info("Quality guard: %s", guidance[:100])

        return {"_narrator_guidance": guidance}

    except Exception as e:
        logger.error(f"Quality guard error: {e}")
        return {}
