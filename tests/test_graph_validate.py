"""Graph definition validation."""

import json
from pathlib import Path

from graphs.builder import validate_graph_definition


def test_valid_builtin_full_story():
    path = Path(__file__).resolve().parent.parent / "graphs" / "full_story.json"
    definition = json.loads(path.read_text())
    assert validate_graph_definition(definition) == []
    assert "narrator_coda" in definition["nodes"]
    assert "mood" in definition["nodes"]


def test_valid_builtin_smart_conversation():
    path = Path(__file__).resolve().parent.parent / "graphs" / "smart_conversation.json"
    definition = json.loads(path.read_text())
    assert validate_graph_definition(definition) == []
    assert definition["nodes"] == [
        "narrator",
        "npc",
        "narrator_coda",
        "condense",
        "memory",
    ]
    # One branch: characters → npc → coda → …; empty cast → condense (skip npc + coda).
    ce = definition["conditional_edges"]
    assert len(ce) == 1 and ce[0]["from"] == "narrator"
    assert ce[0]["router"] == "route_after_narrator"
    assert ce[0]["mapping"] == {"npc": "npc", "condense": "condense"}


def test_valid_builtin_conversation():
    path = Path(__file__).resolve().parent.parent / "graphs" / "conversation.json"
    definition = json.loads(path.read_text())
    assert validate_graph_definition(definition) == []
    assert "memory" in definition["nodes"]


def test_valid_builtin_full_conversation():
    path = Path(__file__).resolve().parent.parent / "graphs" / "full_conversation.json"
    definition = json.loads(path.read_text())
    assert validate_graph_definition(definition) == []
    assert definition["nodes"] == ["narrator", "condense", "memory"]


def test_invalid_unknown_node():
    errors = validate_graph_definition(
        {
            "name": "bad",
            "nodes": ["narrator", "nonexistent"],
            "entry_point": {"router": "route_graph_entry", "mapping": {"narrator": "narrator"}},
            "edges": [],
            "conditional_edges": [],
        }
    )
    assert any("unknown node" in e for e in errors)


def test_memory_node_tolerates_missing_message():
    from nodes.memory import memory_node

    out = memory_node({"response": "Narration", "history": []})
    assert out["history"] == ["Player: \nNarration"]
    assert out["turn_count"] == 1


def test_game_cache_ttl_eviction():
    from game_cache import GameSessionCache

    c = GameSessionCache(ttl_s=0.01, max_entries=10)
    c.set("a", {"x": 1})
    import time

    time.sleep(0.05)
    assert c.get("a") is None
