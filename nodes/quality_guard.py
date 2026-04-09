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

    prompt = f"""You are a quality monitor for a text adventure game. Analyze the recent turns and identify problems.

Recent turns:
{recent_text[:1500]}

Player's current message: {message}

Story summary: {memory_summary[:300]}

Check for these issues and respond with a SHORT list of narrator instructions (2-3 lines max).
Only include instructions that are relevant — if everything is fine, say "NONE".

Issues to check:
1. REPETITION: Are the narrator's descriptions repeating similar themes, settings, or phrases?
2. PASSIVITY: Is the player just observing/looking without taking action? If so, force a consequence.
3. STAGNATION: Has the story stopped progressing? No new events or complications in the last 3 turns?
4. MONOTONE: Is every response the same tone/mood without variation?
5. NO STAKES: Is there nothing at risk? No tension or urgency?

Format: One instruction per line, starting with a dash. Be specific.
Example:
- Introduce an unexpected interruption or complication in this scene
- The player has been passive — have something happen TO them, not just around them
- Vary the tone — the last 3 turns were all tense, add a moment of humor or calm

Instructions for the narrator (or NONE):"""

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
