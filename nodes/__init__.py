"""Node registry — maps node names to functions."""

from nodes.condense import condense_node
from nodes.memory import memory_node
from nodes.mood import mood_node
from nodes.narrator import narrator_node
from nodes.narrator_coda import narrator_coda_node
from nodes.npc import npc_node
from nodes.quality_guard import quality_guard_node

NODE_REGISTRY = {
    "condense": condense_node,
    "memory": memory_node,
    "mood": mood_node,
    "narrator": narrator_node,
    "narrator_coda": narrator_coda_node,
    "npc": npc_node,
    "quality_guard": quality_guard_node,
}
