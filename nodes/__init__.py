"""Node registry — maps node names to functions."""

from nodes.condense import condense_node
from nodes.memory import memory_node
from nodes.narrator import narrator_node
from nodes.npc import npc_node

NODE_REGISTRY = {
    "condense": condense_node,
    "memory": memory_node,
    "narrator": narrator_node,
    "npc": npc_node,
}
