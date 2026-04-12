"""Memory node — records the current turn as a structured dict in history."""


def memory_node(state: dict) -> dict:
    """Append this turn's structured data to history and update turn_count."""
    turn = {
        "player": (state.get("message") or "").strip(),
        "narrator": (state.get("_narrator_text") or "").strip(),
        "characters": {},
        "mood": {},
    }

    # Record location for quest stories
    loc_state = state.get("_location_state") or {}
    if loc_state.get("current_location"):
        turn["location"] = loc_state["current_location"]

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

    # Add scene image info to turn if one was matched
    scene_image = state.get("_scene_image")
    if isinstance(scene_image, dict) and scene_image.get("url"):
        turn["scene_image"] = scene_image

    # Add active portrait info
    active_portraits = state.get("_active_portraits")
    if isinstance(active_portraits, dict) and active_portraits:
        turn["active_portraits"] = active_portraits

    history = list(state.get("history") or [])
    history.append(turn)
    return {"history": history, "turn_count": len(history)}
