"""Quality guard node — analyzes recent turns and injects dynamic narrator instructions.

Runs BEFORE the narrator. Reads history, detects patterns (repetition, passivity,
stagnation), and adds instructions to state["_narrator_guidance"] which the narrator
node reads and includes in its prompt.
"""

import logging

from llm import get_llm
from llm.text import llm_result_to_text
from model_resolver import get_model_for_role

logger = logging.getLogger(__name__)


def quality_guard_node(state: dict) -> dict:
    """Analyze recent history and generate dynamic narrator guidance."""
    history = state.get("history") or []
    message = state.get("message", "")
    memory_summary = state.get("memory_summary", "")
    previous_guidance = state.get("_narrator_guidance", "")

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

    # Pull story metadata for tone-appropriate suggestions
    from nodes.story_context import build_story_context_for_guard
    genre_hint = build_story_context_for_guard(state)

    prompt = f"""You are a creative writing coach helping improve a text adventure story. Read the recent turns and suggest what should happen NEXT to make the story more exciting.

Recent story turns:
{recent_text[:1500]}

The player is about to say: {message}

Story summary: {memory_summary[:300]}{genre_hint}

Your task: Write 1-3 short creative directions for what should happen next. Each direction should make the story MORE interesting. Think about:
- Has the story been covering the same ground? If so, suggest a NEW direction.
- Has nothing surprising happened recently? Suggest a twist or interruption.
- Are characters repeating themselves? Suggest a revelation or conflict.
- Is the mood stuck? Suggest a tonal shift.

Write each direction on its own line starting with a dash. Be specific and creative. Rules:
- Stay consistent with the story's established tone and genre — do not introduce elements that clash with the setting.
- Describe EVENTS and SITUATIONS, not dialogue. Do not write character speech or quoted lines.
- Keep each direction to 1-2 sentences.
If the story is already exciting and varied, write: NONE

Directions:"""

    try:
        raw = llm_result_to_text(llm.invoke(prompt)).strip()

        # Check if the guard says everything is fine
        if raw.upper().startswith("NONE") or raw.upper() == "NONE":
            logger.info("Quality guard: no issues detected")
            return {}

        # --- Refusal / junk detection ---
        refusal_phrases = [
            "i can't help", "i can't fulfill", "i can't assist",
            "i cannot help", "i cannot fulfill", "i cannot assist",
            "i'm not able to", "as an ai", "i'm sorry, but i",
            "would you like some suggestions for writing",
        ]
        raw_lower = raw.lower()
        if any(phrase in raw_lower for phrase in refusal_phrases):
            logger.warning("Quality guard: model refused — skipping")
            return {}

        # --- Prompt echo detection ---
        prompt_echo_phrases = [
            "has the story been covering the same ground",
            "has nothing surprising happened",
            "are characters repeating themselves",
            "is the mood stuck",
            "your task:",
            "write each direction",
        ]
        if any(phrase in raw_lower for phrase in prompt_echo_phrases):
            logger.warning("Quality guard: prompt echo detected — skipping")
            return {}

        # --- Line-level cleanup ---
        lines = []
        for line in raw.split("\n"):
            stripped = line.strip()
            # Skip empty lines
            if not stripped:
                continue
            # Remove leading dash(es) and whitespace for content check
            content = stripped.lstrip("- ").strip()
            # Skip lines that are just dashes/whitespace/punctuation
            if not content or len(content) < 15:
                continue
            # Skip lines that are numbered list artifacts (e.g. "1-", "1.")
            if content[:2].replace(".", "").replace("-", "").isdigit():
                content = content[2:].strip()
                if not content or len(content) < 15:
                    continue
            # Keep lines with real content, re-add the dash prefix
            lines.append(f"- {content}")

        if not lines:
            logger.info("Quality guard: all lines filtered out")
            return {}

        # Limit to 3 instructions max
        guidance = "\n".join(lines[:3])

        # --- Dedupe: skip if identical to previous turn's guidance ---
        if previous_guidance and guidance.strip() == previous_guidance.strip():
            logger.info("Quality guard: duplicate of previous guidance — skipping")
            return {}

        logger.info("Quality guard: %s", guidance[:100])

        return {"_narrator_guidance": guidance}

    except Exception as e:
        logger.error(f"Quality guard error: {e}")
        return {}
