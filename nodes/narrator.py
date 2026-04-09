"""Narrator node — main scene narration via LLM."""

import logging

from config import DEFAULT_MODEL, PROMPT_HISTORY_ENTRY_MAX_CHARS
from llm import get_llm
from llm.text import llm_result_to_text
from nodes.prompt_trim import truncate_prompt_text

logger = logging.getLogger(__name__)

# Subgraphs that run a dedicated npc (or mood→npc) node after the narrator.
_SUBGRAPHS_WITH_SEPARATE_NPC_LAYER = frozenset({
    "smart_conversation",
    "conversation_with_npc",
    "conversation_with_mood",
    "guarded_narrator_npc_memory",
    "guarded_story",
    "guarded_full_memory",
    "full_memory",
})

DEFAULT_NARRATOR_PROMPT = (
    "You are the narrator for a text adventure. Describe scenes in second person. "
    "End each beat with: What do you do?"
)

# Used when the graph runs a dedicated npc (and optional coda) after this node — avoids
# contradicting beat_instr ("do not prompt the player yet") with the default ending line.
DEFAULT_NARRATOR_PROMPT_SEPARATE_NPC = (
    "You are the narrator for a text adventure. Describe scenes in second person. "
    "In this segment only, do not ask the player what they do or end with a direct prompt to the player — "
    "that comes after any character dialogue in this turn."
)

_SEPARATE_NPC_OVERRIDE = (
    "\n\n[Turn structure: This block is only the narrator scene-setting before character lines. "
    "Ignore any instruction above to ask the player what they do or to end with a player-directed question in this segment.]"
)


def _effective_narrator_prompt(narrator_prompt: str, separate_npc_layer: bool) -> str:
    """Align stored narrator instructions with separate-NPC graphs (no conflicting \"What do you do?\")."""
    if not separate_npc_layer:
        return narrator_prompt
    stripped = narrator_prompt.strip()
    if stripped == DEFAULT_NARRATOR_PROMPT.strip():
        return DEFAULT_NARRATOR_PROMPT_SEPARATE_NPC
    return narrator_prompt + _SEPARATE_NPC_OVERRIDE


def narrator_node(state: dict) -> dict:
    """Call the LLM with the narrator prompt and player's message."""
    player = state.get("player") or {}
    from model_resolver import get_model_for_role
    narrator = state.get("narrator") or {}
    story_model = narrator.get("model", "")
    model = get_model_for_role("creative", story_override=story_model)

    try:
        llm = get_llm(model)
    except Exception as e:
        logger.error(f"Failed to get LLM: {e}")
        return {"response": "[System error: Could not connect to LLM. Try again.]"}

    narrator_prompt = (narrator.get("prompt") or "").strip() or DEFAULT_NARRATOR_PROMPT

    # Build context — memory summary (compressed story so far) + last 2 raw turns
    memory_summary = (state.get("memory_summary") or "").strip()
    history = state.get("history") or []
    recent = history[-2:] if len(history) > 2 else history
    trimmed_recent = [
        truncate_prompt_text(entry, PROMPT_HISTORY_ENTRY_MAX_CHARS) for entry in recent
    ]
    summary_block = f"Story so far: {memory_summary}\n\n" if memory_summary else ""
    recent_block = "\n\n".join(trimmed_recent) if trimmed_recent else ""
    context_text = summary_block + recent_block
    context_section = f"\nContext:\n{context_text}\n" if context_text.strip() else ""

    # Characters present
    characters = state.get("characters") or {}
    char_names = [k.replace("_", " ").title() for k in characters.keys()] if characters else []
    chars_line = f"Characters present: {', '.join(char_names)}" if char_names else "Characters present: none"

    subgraph = (state.get("_subgraph_name") or "").strip()
    separate_npc_layer = bool(characters) and subgraph in _SUBGRAPHS_WITH_SEPARATE_NPC_LAYER
    narrator_prompt = _effective_narrator_prompt(narrator_prompt, separate_npc_layer)

    if separate_npc_layer:
        char_names_str = ", ".join(char_names) if char_names else "characters"
        beat_instr = (
            "Narrate what happens next — describe the scene, actions, body language, and atmosphere. "
            f"CRITICAL RULE: Do NOT write any dialogue or quoted speech for {char_names_str}. "
            "They will speak in their own voice in a separate section after yours. "
            "You may describe their expressions, gestures, and reactions but NEVER put words in their mouth. "
            "Do not ask 'What do you do?' or prompt the player. "
            "Keep your response concise — aim for 2-4 short paragraphs."
        )
    else:
        beat_instr = (
            "Narrate what happens next. Include spoken lines as needed using quotes; "
            "keep second person on the player character. "
            "Keep your response concise — aim for 2-4 short paragraphs, not long prose:"
        )
        if not characters:
            beat_instr += (
                " No named characters are defined for this story — do not invent recurring named NPCs or "
                "give them dialogue here; anonymous or environmental voices are fine if clearly not a cast member."
            )

    # Story metadata — genre, tone, NSFW boundaries
    from nodes.story_context import build_story_context
    story_context_line = build_story_context(state)

    # Quality guard guidance (injected by quality_guard node if it ran)
    guidance = (state.get("_narrator_guidance") or "").strip()
    guidance_block = f"\nIMPORTANT — quality notes for this turn:\n{guidance}\n" if guidance else ""

    prompt = f"""{narrator_prompt}

Game: {state.get("game_title", "Untitled")}
Player: {player.get("name", "Adventurer")} — {player.get("background", "")}
{chars_line}
{story_context_line}
{context_section}{guidance_block}
Player just said: {state.get("message", "")}

{beat_instr}"""

    try:
        narration = llm_result_to_text(llm.invoke(prompt))
        return {"response": narration}
    except Exception as e:
        logger.error(f"Narrator node error: {e}")
        return {"response": f"[The AI request failed. Try again later.]"}
