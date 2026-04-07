"""Routing functions — conditional edge logic for LangGraph."""


def route_graph_entry(_state: dict) -> str:
    """Entry point: always go to narrator."""
    return "narrator"


def route_after_narrator(state: dict) -> str:
    """After narrator: npc if characters exist, else condense."""
    characters = state.get("characters") or {}
    if characters:
        return "npc"
    return "condense"
