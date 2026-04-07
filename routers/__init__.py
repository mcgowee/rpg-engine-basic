"""Router registry — maps router names to functions."""

from routers.routing import route_graph_entry, route_after_narrator

ROUTER_REGISTRY = {
    "route_graph_entry": route_graph_entry,
    "route_after_narrator": route_after_narrator,
}

ROUTER_RETURNS = {
    "route_graph_entry": ["narrator"],
    "route_after_narrator": ["npc", "condense"],
}
