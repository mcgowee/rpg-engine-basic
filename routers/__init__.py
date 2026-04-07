"""Router registry — maps router names to functions."""

from routers.routing import route_graph_entry

ROUTER_REGISTRY = {
    "route_graph_entry": route_graph_entry,
}

ROUTER_RETURNS = {
    "route_graph_entry": ["narrator"],
}
