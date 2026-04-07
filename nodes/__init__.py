"""Node registry — maps node names to functions."""

from nodes.narrator import narrator_node

NODE_REGISTRY = {
    "narrator": narrator_node,
}
