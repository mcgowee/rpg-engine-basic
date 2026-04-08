"""Main graph template phases — load template, init play state, advance after each turn."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _template_phases_from_row(row) -> list[dict[str, Any]] | None:
    if not row:
        return None
    try:
        defn = json.loads(row["definition"])
    except (json.JSONDecodeError, TypeError):
        return None
    phases = defn.get("phases")
    if not isinstance(phases, list) or not phases:
        return None
    return phases


def fetch_template_phases(conn, template_id: int, user_id: int) -> list[dict[str, Any]] | None:
    """Return phases list if template exists and is visible to user."""
    row = conn.execute(
        """SELECT definition FROM main_graph_templates
           WHERE id = ? AND (user_id = ? OR is_public = 1)""",
        (template_id, user_id),
    ).fetchone()
    return _template_phases_from_row(row)


def transition_matches(
    phases: list[dict[str, Any]],
    phase_index: int,
    player_message: str,
    state: dict,
    turns_in_phase_after_turn: int,
) -> bool:
    """Whether to move from phase_index to phase_index + 1 after this turn."""
    if phase_index >= len(phases) - 1:
        return False
    phase = phases[phase_index]
    tr = phase.get("transition")
    if not isinstance(tr, dict):
        return False
    t = tr.get("type")
    cond = (tr.get("condition") or "").strip()
    msg = (player_message or "").strip()
    msg_l = msg.lower()
    cond_l = cond.lower()

    if t == "turns":
        try:
            n = max(0, int(cond))
        except ValueError:
            return False
        return turns_in_phase_after_turn >= n

    if t == "milestone":
        if not cond:
            return False
        return cond_l in msg_l

    if t == "manual":
        return msg_l == cond_l

    if t == "location":
        loc = (state.get("location") or "").strip()
        return loc == cond

    if t == "rules":
        return state.get("_rules_transition") == cond

    return False


def apply_main_graph_to_new_state(state: dict, story_row, conn, user_id: int) -> str | None:
    """
    Set _subgraph_name and phase fields for a new game. Returns error string or None.
    """
    tmpl_id = story_row["main_graph_template_id"]
    if tmpl_id is None:
        state["_subgraph_name"] = story_row["subgraph_name"] or "conversation"
        return None

    phases = fetch_template_phases(conn, int(tmpl_id), user_id)
    if not phases:
        return "Main graph template not found or inaccessible"

    sg0 = (phases[0].get("subgraph") or "").strip()
    if not sg0:
        return "First phase has no subgraph"

    state["_main_graph_template_id"] = int(tmpl_id)
    state["_phase_index"] = 0
    state["_turns_in_phase"] = 0
    state["_subgraph_name"] = sg0
    return None


def advance_phase_after_turn(
    state: dict,
    player_message: str,
    conn,
    user_id: int,
) -> None:
    """Mutate state after a completed graph turn: increment phase turn counter, maybe advance phase."""
    tmpl_id = state.get("_main_graph_template_id")
    if tmpl_id is None:
        return

    phases = fetch_template_phases(conn, int(tmpl_id), user_id)
    if not phases:
        logger.warning("advance_phase_after_turn: template %s missing", tmpl_id)
        return

    idx = int(state.get("_phase_index") or 0)
    if idx >= len(phases):
        idx = len(phases) - 1
        state["_phase_index"] = idx

    turns = int(state.get("_turns_in_phase") or 0) + 1
    state["_turns_in_phase"] = turns

    if not transition_matches(phases, idx, player_message, state, turns):
        return

    new_idx = idx + 1
    if new_idx >= len(phases):
        return

    sg = (phases[new_idx].get("subgraph") or "").strip()
    if not sg:
        return

    state["_phase_index"] = new_idx
    state["_turns_in_phase"] = 0
    state["_subgraph_name"] = sg
    state.pop("_rules_transition", None)


def hydrate_runtime_from_story_save(st: dict, story_id: int, story_row) -> None:
    """Attach runtime fields and sync editable story data into the save state.

    This ensures that edits to the story (adding characters, changing narrator
    prompt, etc.) take effect on existing saves without requiring a restart.
    """
    import json as _json

    st["_story_id"] = story_id
    if not st.get("_main_graph_template_id") and story_row:
        st["_subgraph_name"] = story_row["subgraph_name"] or "conversation"

    if not story_row:
        return

    # Sync characters from story — new/updated characters appear in play
    try:
        story_characters = _json.loads(story_row["characters"] or "{}")
    except (ValueError, TypeError):
        story_characters = {}
    if story_characters:
        st["characters"] = story_characters

    # Sync narrator settings
    narrator_prompt = (story_row["narrator_prompt"] or "").strip()
    narrator_model = (story_row["narrator_model"] or "default").strip()
    if narrator_prompt:
        narrator = st.get("narrator") or {}
        narrator["prompt"] = narrator_prompt
        if narrator_model:
            narrator["model"] = narrator_model
        st["narrator"] = narrator

    # Sync player info
    player_name = story_row["player_name"] or ""
    player_bg = story_row["player_background"] or ""
    if player_name or player_bg:
        player = st.get("player") or {}
        if player_name:
            player["name"] = player_name
        if player_bg:
            player["background"] = player_bg
        st["player"] = player

    # Sync title and opening
    if story_row["title"]:
        st["game_title"] = story_row["title"]
    if story_row["opening"]:
        st["opening"] = story_row["opening"]
