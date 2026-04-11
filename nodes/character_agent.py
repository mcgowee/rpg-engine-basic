"""Character agent node — each character responds independently.

Runs AFTER narrator. Each character reads the narrator's scene description,
the player's message, and their own conversation history, then produces
dialogue + a brief physical action.

Writes to _character_responses: {"alex": {"dialogue": "...", "action": "..."}}
"""

import logging
import re

from llm import get_llm
from llm.text import llm_result_to_text
from nodes.history_util import get_character_history
from nodes.story_context import build_story_context

logger = logging.getLogger(__name__)


def character_agent_node(state: dict) -> dict:
    """Generate dialogue + action for each character independently."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    narrator_text = (state.get("_narrator_text") or "").strip()
    message = (state.get("message") or "").strip()
    memory_summary = (state.get("memory_summary") or "").strip()
    history = state.get("history") or []
    player = state.get("player") or {}
    player_name = player.get("name", "You")

    story_context = build_story_context(state)
    story_line = f"\n{story_context}\n" if story_context else ""

    summary_block = f"Conversation so far: {memory_summary}\n\n" if memory_summary else ""

    responses = {}

    for npc_key, npc in characters.items():
        if not isinstance(npc, dict):
            continue

        label = npc_key.replace("_", " ").title()
        npc_prompt = (npc.get("prompt") or "").strip()
        if not npc_prompt:
            npc_prompt = f"You are {label}. You're having a conversation."

        # This character's own dialogue history
        char_history = get_character_history(history, npc_key, count=6)
        convo_block = "\n".join(char_history) if char_history else ""

        # Extract this character's recent lines to prevent repetition
        recent_dialogue = []
        for turn in history[-4:]:
            if isinstance(turn, dict):
                chars = turn.get("characters") or {}
                char_resp = chars.get(npc_key)
                if isinstance(char_resp, dict) and char_resp.get("dialogue"):
                    recent_dialogue.append(char_resp["dialogue"][:60])
        antirepeat = ""
        if recent_dialogue:
            antirepeat = "\nDo NOT repeat or closely rephrase these recent lines:\n" + "\n".join(f"- \"{d}\"" for d in recent_dialogue[-3:]) + "\n"

        # Mood context
        moods = npc.get("moods")
        mood_block = ""
        if isinstance(moods, list) and moods:
            mood_lines = []
            for axis in moods:
                if not isinstance(axis, dict):
                    continue
                name = axis.get("axis", "mood")
                val = axis.get("value", 5)
                low = axis.get("low", "low")
                high = axis.get("high", "high")
                leaning = low if val <= 5 else high
                mood_lines.append(f"- {name}: {val}/10 (leaning {leaning})")
            if mood_lines:
                mood_block = "Your current emotional state:\n" + "\n".join(mood_lines) + "\n"

        # Model resolution
        from model_resolver import get_model_for_role
        char_model = npc.get("model", "")
        model = get_model_for_role("dialogue", character_override=char_model)

        try:
            llm = get_llm(model)
        except Exception as e:
            logger.error(f"Character agent: failed to get LLM for {npc_key}: {e}")
            continue

        prompt = f"""{npc_prompt}
{story_line}
You are having a conversation with {player_name}. {player.get("background", "")}
{mood_block}
{summary_block}Recent conversation:
{convo_block}
{antirepeat}
The narrator describes: {narrator_text}

{player_name}: {message}

Respond as {label}. Provide TWO things:
1. SAY: What you say out loud (1-3 sentences, natural and in character). IMPORTANT: Do NOT start with "Ah," or repeat phrases from the conversation above. Vary your sentence structure.
2. DO: A brief physical action in THIRD PERSON (5-15 words — body language, gesture, movement). Write "{label} does..." not "I do..."

Format your response EXACTLY like this:
SAY: your spoken words here
DO: {label} does something here"""

        try:
            raw = llm_result_to_text(llm.invoke(prompt)).strip()
            dialogue, action = _parse_say_do(raw, label)
            responses[npc_key] = {"dialogue": dialogue, "action": action}
            logger.info("Character %s: say=%s do=%s", npc_key, dialogue[:60], action[:40])

        except Exception as e:
            logger.error(f"Character agent error for {npc_key}: {e}")

    if not responses:
        return {}

    return {"_character_responses": responses}


def _parse_say_do(raw: str, label: str) -> tuple[str, str]:
    """Parse SAY/DO format from LLM response. Falls back gracefully."""
    dialogue = ""
    action = ""

    # Try to find SAY: and DO: markers
    say_match = re.search(r'(?:SAY|Say|say)\s*:\s*(.+?)(?=\n\s*(?:DO|Do|do)\s*:|$)', raw, re.DOTALL)
    do_match = re.search(r'(?:DO|Do|do)\s*:\s*(.+?)$', raw, re.DOTALL)

    if say_match:
        dialogue = say_match.group(1).strip()
    if do_match:
        action = do_match.group(1).strip()

    # If SAY/DO parsing failed, treat the whole response as dialogue
    if not dialogue:
        # Remove any action-like content in asterisks
        cleaned = re.sub(r'\*[^*]+\*', '', raw).strip()
        # Remove label prefix if present
        for prefix in [f"{label}:", f"{label} :", f'"{label}":', f"**{label}**:"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        dialogue = cleaned if cleaned else "..."

    # Clean up dialogue
    if dialogue.startswith('"') and dialogue.endswith('"') and dialogue.count('"') == 2:
        dialogue = dialogue[1:-1].strip()
    # Remove SAY/DO labels if they leaked into the text
    for prefix in ["SAY:", "Say:", "say:", "DO:", "Do:", "do:"]:
        dialogue = dialogue.replace(prefix, "").strip()
        action = action.replace(prefix, "").strip()

    # Clean up action
    action = action.replace("*", "").strip()
    # Convert first-person "I verb" to third-person "verbs"
    if re.match(r'^I [a-z]', action):
        action = action[2:]  # strip "I ", response_builder prefixes the name
    # Strip character name prefix (response_builder adds name separately)
    if action.lower().startswith(f"{label.lower()} "):
        action = action[len(label) + 1:].strip()
    # Truncate long actions
    if len(action) > 150:
        last_period = action[:150].rfind(".")
        if last_period > 20:
            action = action[:last_period + 1]
        else:
            action = action[:150].rsplit(" ", 1)[0]

    return dialogue, action
