"""Memory node — records the current turn in history."""


def memory_node(state: dict) -> dict:
    """Append this turn to history and update turn_count."""
    msg = (state.get("message") or "").strip()
    resp = state.get("response") or ""
    turn = f"Player: {msg}\n{resp}"
    history = list(state.get("history") or [])
    history.append(turn)
    return {"history": history, "turn_count": len(history)}
