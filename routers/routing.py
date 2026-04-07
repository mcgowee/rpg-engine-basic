"""Routing functions — conditional edge logic for LangGraph."""


def route_graph_entry(_state: dict) -> str:
    """Entry point: always go to narrator."""
    return "narrator"
