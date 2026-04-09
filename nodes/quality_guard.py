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

    prompt = f"""You are a strict quality enforcer for a text adventure game. Your job is to PREVENT the narrator from being boring or repetitive.

Read the recent turns below. If you detect ANY of these problems, you MUST issue a forceful correction. Do NOT say "NONE" unless the story is genuinely fresh and engaging.

Recent turns:
{recent_text[:1500]}

Player's next message: {message}

Story so far: {memory_summary[:300]}

Problems to detect (be aggressive — it's better to over-correct than let boredom slide):

1. REPETITION: Same descriptions, same emotions, same sentence patterns? FORCE a completely different approach.
2. PASSIVITY: Player is just talking/looking/thinking? DEMAND that something unexpected HAPPENS — an interruption, a discovery, a threat.
3. STAGNATION: No new plot development in 2+ turns? REQUIRE a twist, revelation, or complication RIGHT NOW.
4. MONOTONE: Same emotional tone every turn? INSIST on a shift — if it's been tense, force a moment of dark humor. If romantic, introduce danger.
5. DIALOGUE LOOPS: Characters saying similar things? MANDATE new topics, secrets revealed, or arguments.

Write 1-3 FORCEFUL instructions. Start each with "YOU MUST" — these are not suggestions, they are requirements.

Example:
- YOU MUST introduce an unexpected interruption that changes the scene completely
- YOU MUST have a character reveal a secret or lie about something
- YOU MUST shift the emotional tone — break the pattern with surprise or humor

Instructions (or NONE only if truly engaging):"""

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
