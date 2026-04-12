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

    # Character names and brief descriptions for context
    char_names = [k.replace("_", " ").title() for k in characters.keys()]
    char_list = ", ".join(char_names) if char_names else "any characters"

    # Build character appearance lines so narrator knows gender/look
    char_desc_lines = []
    for key, char in characters.items():
        if not isinstance(char, dict):
            continue
        label = key.replace("_", " ").title()
        prompt_text = (char.get("prompt") or "").strip()
        # Extract appearance from "How she/he/they look(s):" section if present
        desc = ""
        for marker in ["How she looks:", "How he looks:", "How they look:",
                        "Appearance:", "Description:"]:
            idx = prompt_text.lower().find(marker.lower())
            if idx >= 0:
                desc = prompt_text[idx + len(marker):].strip()
                # Take first sentence or up to 120 chars
                for end in [". ", "\n"]:
                    eidx = desc.find(end)
                    if eidx > 0:
                        desc = desc[:eidx + 1] if end == ". " else desc[:eidx]
                        break
                if len(desc) > 150:
                    desc = desc[:147].rsplit(" ", 1)[0] + "..."
                break
        if desc:
            char_desc_lines.append(f"- {label}: {desc}")
        else:
            # Fallback: grab first sentence of prompt for basic context
            first = prompt_text.split(".")[0].strip() if prompt_text else ""
            if first:
                char_desc_lines.append(f"- {label}: {first}.")
    char_block = "\n".join(char_desc_lines) if char_desc_lines else ""

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

    # Use story-specific narrator prompt if available
    custom_prompt = (state.get("narrator_prompt") or "").strip()
    system_intro = custom_prompt if custom_prompt else "You are the narrator for a story. Describe what happens in the world."

    # Progression pacing hints
    narrator_prog = (state.get("_narrator_progression") or "").strip()
    progression_block = f"\nScene atmosphere:\n{narrator_prog}\n" if narrator_prog else ""

    # Location context (quest system)
    location_hint = (state.get("_narrator_location_hint") or "").strip()
    just_arrived = "just arrived" in location_hint.lower()
    location_block = f"\nLocation context:\n{location_hint}\n" if location_hint else ""

    # Arrival rule: when the player just moved to a new location, tell the
    # narrator to describe it; otherwise keep the "scene already in progress" rule
    if just_arrived:
        arrival_rule = "- The player just arrived at a NEW location. Describe this place vividly — focus on the new surroundings, NOT the previous location"
    else:
        arrival_rule = "- Do NOT re-describe the player entering the room or arriving — the scene is already in progress"

    prompt = f"""{system_intro}

{story_line}Game: {state.get("game_title", "Untitled")}
Player: {player.get("name", "Adventurer")} — {player.get("background", "")}
Characters present: {char_list}
{char_block}
{progression_block}{location_block}
{summary_block}{narrator_block}{dialogue_block}
Player: {message}

Describe what happens next. Rules:
- Second person, present tense
- Show the RESULT of what the player just did — what changed, what they discover, how others react
- CRITICAL: Do NOT write dialogue or quoted speech for {char_list}. They speak separately.
- You may describe their body language, expressions, and physical reactions
- 2-4 sentences, concise and atmospheric
{arrival_rule}
- Do NOT repeat descriptions from previous narration — advance the story forward
- AVOID these overused phrases: "deadly game", "deadly dance", "tension escalates", "charged with anticipation", "covert game of espionage". Use fresh, specific language instead.

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
