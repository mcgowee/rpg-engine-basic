"""Main-graph phase transitions."""

from play_phases import transition_matches


def _phases_turns(n: str):
    return [
        {"name": "a", "subgraph": "sg1", "transition": {"type": "turns", "condition": n}},
        {"name": "b", "subgraph": "sg2", "transition": None},
    ]


def test_turns_transition():
    phases = _phases_turns("3")
    assert not transition_matches(phases, 0, "hi", {}, 2)
    assert transition_matches(phases, 0, "hi", {}, 3)
    assert transition_matches(phases, 0, "hi", {}, 4)


def test_milestone_substring():
    phases = [
        {
            "name": "a",
            "subgraph": "sg1",
            "transition": {"type": "milestone", "condition": "open door"},
        },
        {"name": "b", "subgraph": "sg2", "transition": None},
    ]
    assert transition_matches(phases, 0, "I open door now", {}, 1)
    assert not transition_matches(phases, 0, "wait", {}, 1)


def test_manual_exact():
    phases = [
        {
            "name": "a",
            "subgraph": "sg1",
            "transition": {"type": "manual", "condition": "next"},
        },
        {"name": "b", "subgraph": "sg2", "transition": None},
    ]
    assert transition_matches(phases, 0, "next", {}, 1)
    assert transition_matches(phases, 0, "Next", {}, 1)
    assert not transition_matches(phases, 0, "next phase", {}, 1)


def test_location():
    phases = [
        {
            "name": "a",
            "subgraph": "sg1",
            "transition": {"type": "location", "condition": "hall"},
        },
        {"name": "b", "subgraph": "sg2", "transition": None},
    ]
    assert transition_matches(phases, 0, "x", {"location": "hall"}, 1)
    assert not transition_matches(phases, 0, "x", {"location": "room"}, 1)


def test_rules_flag():
    phases = [
        {
            "name": "a",
            "subgraph": "sg1",
            "transition": {"type": "rules", "condition": "win"},
        },
        {"name": "b", "subgraph": "sg2", "transition": None},
    ]
    assert transition_matches(phases, 0, "x", {"_rules_transition": "win"}, 1)
    assert not transition_matches(phases, 0, "x", {}, 1)


def test_last_phase_never():
    phases = [
        {"name": "a", "subgraph": "sg1", "transition": {"type": "turns", "condition": "1"}},
        {"name": "b", "subgraph": "sg2", "transition": None},
    ]
    assert not transition_matches(phases, 1, "x", {}, 99)
