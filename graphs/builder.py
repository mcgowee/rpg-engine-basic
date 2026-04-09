"""Graph builder — constructs LangGraph from JSON definitions."""

from langgraph.graph import StateGraph, END
from typing import TypedDict

from nodes import NODE_REGISTRY
from routers import ROUTER_REGISTRY


class State(TypedDict):
    message: str
    response: str
    history: list
    memory_summary: str
    narrator: dict
    player: dict
    characters: dict
    game_title: str
    opening: str
    paused: bool
    _narrator_guidance: str
    turn_count: int


def _normalize_end(value):
    return END if value == "__end__" else value


def _normalize_mapping(mapping: dict) -> dict:
    return {_normalize_end(k): _normalize_end(v) for k, v in mapping.items()}


def build_graph_from_json(definition: dict):
    """Build a compiled LangGraph from a JSON definition dict."""
    g = StateGraph(State)

    for node_name in definition["nodes"]:
        fn = NODE_REGISTRY[node_name]
        g.add_node(node_name, fn)

    entry = definition["entry_point"]
    router_fn = ROUTER_REGISTRY[entry["router"]]
    g.set_conditional_entry_point(router_fn, _normalize_mapping(entry["mapping"]))

    for edge in definition.get("edges", []):
        g.add_edge(edge["from"], _normalize_end(edge["to"]))

    for ce in definition.get("conditional_edges", []):
        router_fn = ROUTER_REGISTRY[ce["router"]]
        g.add_conditional_edges(ce["from"], router_fn, _normalize_mapping(ce["mapping"]))

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

    entry = definition.get("entry_point")
    if not isinstance(entry, dict):
        errors.append("entry_point must be an object")
    else:
        router = entry.get("router")
        if router not in ROUTER_REGISTRY:
            errors.append(f"unknown entry router: {router}")
        mapping = entry.get("mapping")
        if not isinstance(mapping, dict):
            errors.append("entry_point.mapping must be an object")

    for edge in definition.get("edges", []):
        if edge.get("from") not in node_set:
            errors.append(f"edge from unknown node: {edge.get('from')}")
        to = edge.get("to")
        if to != "__end__" and to not in node_set:
            errors.append(f"edge to unknown node: {to}")

    for ce in definition.get("conditional_edges", []):
        if ce.get("from") not in node_set:
            errors.append(f"conditional edge from unknown node: {ce.get('from')}")
        router = ce.get("router")
        if router not in ROUTER_REGISTRY:
            errors.append(f"unknown conditional router: {router}")

    if not errors:
        try:
            build_graph_from_json(definition)
        except Exception as e:
            errors.append(f"compilation failed: {e}")

    return errors
