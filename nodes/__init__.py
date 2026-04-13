"""Node registry — maps node names to functions."""

from nodes.character_agent import character_agent_node
from nodes.condense import condense_node
from nodes.expression_picker import expression_picker_node
from nodes.location import location_node
from nodes.memory import memory_node
from nodes.mood import mood_node
from nodes.narrator import narrator_node
from nodes.progression import progression_node
from nodes.response_builder import response_builder_node
from nodes.scene_image import scene_image_node
from nodes.task import task_node
from nodes.quest import quest_node

NODE_REGISTRY = {
    "character_agent": character_agent_node,
    "condense": condense_node,
    "expression_picker": expression_picker_node,
    "location": location_node,
    "memory": memory_node,
    "mood": mood_node,
    "narrator": narrator_node,
    "progression": progression_node,
    "response_builder": response_builder_node,
    "scene_image": scene_image_node,
    "task": task_node,
    "quest": quest_node,
}
