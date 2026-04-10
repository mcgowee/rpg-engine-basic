"""Shared history utilities — read structured turn history.

Turn format (dict):
    {
        "player": "what the player said",
        "narrator": "scene/event description",
        "characters": {
            "alex": {"dialogue": "what alex said", "action": "what alex did"}
        },
        "mood": {"alex": {"attraction": 8, "trust": 7}}
    }

Legacy format (str): "Player: msg\\nresponse text"
All helpers handle both formats gracefully.
"""


def get_recent_narrator(history: list, count: int = 3) -> list[str]:
    """Extract recent narrator descriptions from structured history."""
    entries = []
    for turn in history[-(count):]:
        if isinstance(turn, dict) and turn.get("narrator"):
            entries.append(turn["narrator"])
    return entries


def get_recent_dialogue_all(history: list, count: int = 3) -> list[str]:
    """Extract recent dialogue from all characters + player as readable lines."""
    lines = []
    for turn in history[-(count):]:
        if isinstance(turn, dict):
            if turn.get("player"):
                lines.append(f"Player: {turn['player']}")
            chars = turn.get("characters") or {}
            for key, resp in chars.items():
                if isinstance(resp, dict) and resp.get("dialogue"):
                    label = key.replace("_", " ").title()
                    lines.append(f"{label}: {resp['dialogue']}")
        elif isinstance(turn, str):
            lines.append(turn)
    return lines


def get_character_history(history: list, character_key: str, count: int = 6) -> list[str]:
    """Extract a specific character's conversation history with the player."""
    lines = []
    for turn in history[-(count):]:
        if isinstance(turn, dict):
            if turn.get("player"):
                lines.append(f"Player: {turn['player']}")
            chars = turn.get("characters") or {}
            char_resp = chars.get(character_key)
            if isinstance(char_resp, dict) and char_resp.get("dialogue"):
                label = character_key.replace("_", " ").title()
                lines.append(f"{label}: {char_resp['dialogue']}")
        elif isinstance(turn, str):
            lines.append(turn)
    return lines


def get_recent_actions(history: list, character_key: str, count: int = 4) -> list[str]:
    """Extract a specific character's recent physical actions."""
    actions = []
    for turn in history[-(count):]:
        if isinstance(turn, dict):
            chars = turn.get("characters") or {}
            char_resp = chars.get(character_key)
            if isinstance(char_resp, dict) and char_resp.get("action"):
                actions.append(char_resp["action"])
    return actions


def get_recent_context(history: list, count: int = 3) -> str:
    """Build a readable context block from recent structured turns."""
    lines = []
    for turn in history[-(count):]:
        if isinstance(turn, dict):
            if turn.get("player"):
                lines.append(f"Player: {turn['player']}")
            if turn.get("narrator"):
                lines.append(f"[{turn['narrator']}]")
            chars = turn.get("characters") or {}
            for key, resp in chars.items():
                if isinstance(resp, dict):
                    label = key.replace("_", " ").title()
                    if resp.get("action"):
                        lines.append(f"*{label} {resp['action']}*")
                    if resp.get("dialogue"):
                        lines.append(f'{label}: "{resp["dialogue"]}"')
            lines.append("")
        elif isinstance(turn, str):
            lines.append(turn)
            lines.append("")
    return "\n".join(lines).strip()


def get_structured_context_for_condense(history: list, count: int = 3) -> str:
    """Build a detailed context block for the condense node."""
    lines = []
    for turn in history[-(count):]:
        if isinstance(turn, dict):
            if turn.get("player"):
                lines.append(f"Player said: {turn['player']}")
            if turn.get("narrator"):
                lines.append(f"Narrator: {turn['narrator']}")
            chars = turn.get("characters") or {}
            for key, resp in chars.items():
                if isinstance(resp, dict):
                    label = key.replace("_", " ").title()
                    if resp.get("dialogue"):
                        lines.append(f"{label} said: {resp['dialogue']}")
                    if resp.get("action"):
                        lines.append(f"{label} action: {resp['action']}")
            lines.append("")
        elif isinstance(turn, str):
            lines.append(turn)
            lines.append("")
    return "\n".join(lines).strip()
