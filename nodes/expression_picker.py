"""Expression picker node — LLM picks a portrait variant for each character.

Reads the current turn text (narrator + character dialogue/action) and asks the
LLM to choose the best facial expression from the character's available portrait
variants.  Falls back to the default portrait if no variants exist.

Runs after mood so mood values are available as optional context.

Writes:
  _active_portraits: {char_key: "variant_filename"} — current portrait per character
"""

import logging
import re

from llm import get_llm
from llm.text import llm_result_to_text
from model_resolver import get_model_for_role

logger = logging.getLogger(__name__)


def expression_picker_node(state: dict) -> dict:
    """For each character with portrait variants, ask the LLM to pick an expression."""
    characters = state.get("characters") or {}
    if not characters:
        return {}

    narrator_text = (state.get("_narrator_text") or "").strip()
    char_responses = state.get("_character_responses") or {}
    player_message = (state.get("message") or "").strip()
    previous_portraits = state.get("_active_portraits") or {}

    active_portraits = {}

    for char_key, char in characters.items():
        if not isinstance(char, dict):
            continue

        portraits = char.get("portraits")
        if not isinstance(portraits, dict) or not portraits:
            # No variants — keep default portrait
            if char.get("portrait"):
                active_portraits[char_key] = char["portrait"]
            continue

        variant_keys = sorted(portraits.keys())
        if not variant_keys:
            continue

        # If only one variant, use it directly — no LLM needed
        if len(variant_keys) == 1:
            active_portraits[char_key] = portraits[variant_keys[0]]
            continue

        # Build context for the LLM
        label = char_key.replace("_", " ").title()

        char_resp = char_responses.get(char_key, {})
        turn_lines = []
        if narrator_text:
            turn_lines.append(f"Scene: {narrator_text}")
        if player_message:
            turn_lines.append(f"Player: {player_message}")
        if isinstance(char_resp, dict):
            if char_resp.get("dialogue"):
                turn_lines.append(f'{label} said: "{char_resp["dialogue"]}"')
            if char_resp.get("action"):
                turn_lines.append(f"{label} did: {char_resp['action']}")
        turn_block = "\n".join(turn_lines) if turn_lines else "No scene text available."

        # Mood context (optional — enriches the pick but doesn't govern it)
        mood_lines = []
        for axis in (char.get("moods") or []):
            if isinstance(axis, dict) and "axis" in axis and "value" in axis:
                mood_lines.append(f"  {axis['axis']}: {axis['value']}/10")
        mood_block = "\n".join(mood_lines) if mood_lines else ""

        # Previous expression for continuity
        prev_variant = None
        prev_file = previous_portraits.get(char_key, "")
        if prev_file:
            for vk, vf in portraits.items():
                if vf == prev_file:
                    prev_variant = vk
                    break
        prev_line = f"\nPrevious expression: {prev_variant}" if prev_variant else ""

        prompt = f"""Pick the facial expression that best matches what {label} is feeling RIGHT NOW in this scene.

Available expressions: {', '.join(variant_keys)}

What just happened:
{turn_block}
{"" if not mood_block else f"""
{label}'s current mood:
{mood_block}
"""}{prev_line}

Pick the single best expression for {label}'s face in this moment.
Reply with ONLY the expression name, nothing else:"""

        char_model = char.get("model", "")
        model = get_model_for_role("classification", character_override=char_model)

        try:
            llm = get_llm(model)
            result = llm_result_to_text(llm.invoke(prompt)).strip().lower()

            # Parse — extract the variant key from the response
            picked = _parse_variant(result, variant_keys)

            if picked:
                active_portraits[char_key] = portraits[picked]
                logger.info("Expression %s → %s", char_key, picked)
            elif prev_file:
                # LLM gave garbage — keep previous expression
                active_portraits[char_key] = prev_file
                logger.warning("Expression %s: unparseable '%s', keeping previous", char_key, result)
            else:
                # No previous, fall back to default portrait
                if char.get("portrait"):
                    active_portraits[char_key] = char["portrait"]
                logger.warning("Expression %s: unparseable '%s', using default", char_key, result)

        except Exception as e:
            logger.error("Expression picker failed for %s: %s", char_key, e)
            # On error, preserve previous or use default
            if prev_file:
                active_portraits[char_key] = prev_file
            elif char.get("portrait"):
                active_portraits[char_key] = char["portrait"]

    if active_portraits:
        return {"_active_portraits": active_portraits}
    return {}


def _parse_variant(response: str, variant_keys: list[str]) -> str | None:
    """Extract a variant key from the LLM response. Tolerates minor formatting."""
    cleaned = response.strip().strip('"\'').lower()

    # Exact match
    for vk in variant_keys:
        if cleaned == vk.lower():
            return vk

    # Response contains a variant key as a whole word
    for vk in variant_keys:
        if re.search(rf'\b{re.escape(vk.lower())}\b', cleaned):
            return vk

    # Substring match (last resort)
    for vk in variant_keys:
        if vk.lower() in cleaned:
            return vk

    return None
