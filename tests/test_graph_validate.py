"""Graph definition validation."""

import json
from pathlib import Path

from graphs.builder import validate_graph_definition


def test_valid_builtin_narrator_chat():
    path = Path(__file__).resolve().parent.parent / "graphs" / "narrator_chat.json"
    definition = json.loads(path.read_text())
    assert validate_graph_definition(definition) == []
    assert "narrator" in definition["nodes"]
    assert "character_agent" in definition["nodes"]
    assert "response_builder" in definition["nodes"]
    assert "mood" in definition["nodes"]
    assert "condense" in definition["nodes"]
    assert "memory" in definition["nodes"]
    # Check __start__ and __end__ edges
    froms = [e["from"] for e in definition["edges"]]
    tos = [e["to"] for e in definition["edges"]]
    assert "__start__" in froms
    assert "__end__" in tos


def test_valid_builtin_narrator_chat_lite():
    path = Path(__file__).resolve().parent.parent / "graphs" / "narrator_chat_lite.json"
    definition = json.loads(path.read_text())
    assert validate_graph_definition(definition) == []
    assert "mood" not in definition["nodes"]
    assert "condense" not in definition["nodes"]


def test_valid_builtin_chat_direct():
    path = Path(__file__).resolve().parent.parent / "graphs" / "chat_direct.json"
    definition = json.loads(path.read_text())
    assert validate_graph_definition(definition) == []
    assert "narrator" not in definition["nodes"]
    froms = [e["from"] for e in definition["edges"]]
    assert "__start__" in froms


def test_invalid_unknown_node():
    errors = validate_graph_definition(
        {
            "name": "bad",
            "nodes": ["character_agent", "nonexistent"],
            "edges": [
                {"from": "__start__", "to": "character_agent"},
                {"from": "character_agent", "to": "__end__"},
            ],
        }
    )
    assert any("unknown node" in e for e in errors)


def test_missing_start_edge():
    errors = validate_graph_definition(
        {
            "name": "no_start",
            "nodes": ["narrator"],
            "edges": [
                {"from": "narrator", "to": "__end__"},
            ],
        }
    )
    assert any("__start__" in e for e in errors)


def test_memory_node_structured_output():
    from nodes.memory import memory_node

    out = memory_node({
        "message": "hello",
        "_narrator_text": "The room is dark.",
        "_character_responses": {
            "alex": {"dialogue": "Hey there.", "action": "waves"}
        },
        "characters": {
            "alex": {
                "moods": [{"axis": "trust", "value": 7, "low": "wary", "high": "open"}]
            }
        },
        "history": [],
    })
    assert len(out["history"]) == 1
    turn = out["history"][0]
    assert turn["player"] == "hello"
    assert turn["narrator"] == "The room is dark."
    assert turn["characters"]["alex"]["dialogue"] == "Hey there."
    assert turn["characters"]["alex"]["action"] == "waves"
    assert turn["mood"]["alex"]["trust"] == 7
    assert out["turn_count"] == 1


def test_response_builder():
    from nodes.response_builder import response_builder_node

    out = response_builder_node({
        "_narrator_text": "The room is quiet.",
        "_character_responses": {
            "alex": {"dialogue": "Hey.", "action": "leans back"}
        },
        "characters": {"alex": {"portrait": "/img/alex.png"}},
    })
    assert len(out["_bubbles"]) == 2
    assert out["_bubbles"][0]["type"] == "narrator"
    assert out["_bubbles"][1]["type"] == "character"
    assert out["_bubbles"][1]["name"] == "Alex"


def test_game_cache_ttl_eviction():
    from game_cache import GameSessionCache

    c = GameSessionCache(ttl_s=0.01, max_entries=10)
    c.set("a", {"x": 1})
    import time

    time.sleep(0.05)
    assert c.get("a") is None
