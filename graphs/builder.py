"""Graph builder — constructs LangGraph from JSON definitions."""

from langgraph.graph import StateGraph, START, END
from typing import TypedDict

from nodes import NODE_REGISTRY


class State(TypedDict):
    # Player input / output
    message: str
    response: str

    # Structured turn history — list of dicts, each with:
    #   player, narrator, characters: {key: {dialogue, action}}, mood
    history: list

    # Rolling compressed summary (60-80 words)
    memory_summary: str

    # Story data
    characters: dict
    story: dict
    player: dict
    game_title: str
    opening: str
    paused: bool
    turn_count: int

    # Internal node communication
    _narrator_text: str
    _character_responses: dict
    _bubbles: list
    _subgraph_name: str
    _story_id: int


def _normalize_node(value: str):
    """Map __start__ and __end__ to LangGraph constants."""
    if value == "__start__":
        return START
    if value == "__end__":
        return END
    return value


def build_graph_from_json(definition: dict):
    """Build a compiled LangGraph from a JSON definition dict."""
    g = StateGraph(State)

    for node_name in definition["nodes"]:
        fn = NODE_REGISTRY[node_name]
        g.add_node(node_name, fn)

    for edge in definition.get("edges", []):
        g.add_edge(_normalize_node(edge["from"]), _normalize_node(edge["to"]))

    return g.compile()


def validate_graph_definition(definition: dict) -> list[str]:
    """Validate a graph definition. Returns list of error strings (empty = valid)."""
    errors = []

    name = definition.get("name")
    if not name or not isinstance(name, str):
        errors.append("name is required and must be a string")

    nodes = definition.get("nodes")
    if not nodes or not isinstance(nodes, list):
        errors.append("nodes must be a non-empty list")
    else:
        for n in nodes:
            if n not in NODE_REGISTRY:
                errors.append(f"unknown node: {n}")

    node_set = set(nodes or [])

    edges = definition.get("edges", [])
    has_start = False
    has_end = False
    for edge in edges:
        frm = edge.get("from", "")
        to = edge.get("to", "")
        if frm == "__start__":
            has_start = True
        elif frm not in node_set:
            errors.append(f"edge from unknown node: {frm}")
        if to == "__end__":
            has_end = True
        elif to not in node_set:
            errors.append(f"edge to unknown node: {to}")

    if not has_start:
        errors.append("no edge from __start__ — graph has no entry point")
    if not has_end:
        errors.append("no edge to __end__ — graph has no exit")

    if not errors:
        try:
            build_graph_from_json(definition)
        except Exception as e:
            errors.append(f"compilation failed: {e}")

    return errors
