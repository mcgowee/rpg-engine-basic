"""Node registry — maps node names to functions."""

from nodes.character_agent import character_agent_node
from nodes.condense import condense_node
from nodes.memory import memory_node
from nodes.mood import mood_node
from nodes.narrator import narrator_node
from nodes.response_builder import response_builder_node

NODE_REGISTRY = {
    "character_agent": character_agent_node,
    "condense": condense_node,
    "memory": memory_node,
    "mood": mood_node,
    "narrator": narrator_node,
    "response_builder": response_builder_node,
}
