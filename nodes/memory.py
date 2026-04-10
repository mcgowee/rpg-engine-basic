"""Memory node — records the current turn as a structured dict in history."""


def memory_node(state: dict) -> dict:
    """Append this turn's structured data to history and update turn_count."""
    turn = {
        "player": (state.get("message") or "").strip(),
        "narrator": (state.get("_narrator_text") or "").strip(),
        "characters": {},
        "mood": {},
    }

    # Character responses (dialogue + action per character)
    char_responses = state.get("_character_responses") or {}
    for key, resp in char_responses.items():
        if isinstance(resp, dict):
            turn["characters"][key] = {
                "dialogue": (resp.get("dialogue") or "").strip(),
                "action": (resp.get("action") or "").strip(),
            }

    # Snapshot current mood values from characters
    for key, char in (state.get("characters") or {}).items():
        if not isinstance(char, dict):
            continue
        moods = char.get("moods")
        if isinstance(moods, list):
            turn["mood"][key] = {
                a["axis"]: a["value"]
                for a in moods
                if isinstance(a, dict) and "axis" in a and "value" in a
            }

    history = list(state.get("history") or [])
    history.append(turn)
    return {"history": history, "turn_count": len(history)}
