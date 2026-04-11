"""Response builder node — assembles narrator + character responses into bubbles.

No LLM call. Pure assembly. Reads _narrator_text and _character_responses,
builds both the legacy combined response and the structured bubbles list.
"""


def response_builder_node(state: dict) -> dict:
    """Assemble narrator text and character responses into response + bubbles."""
    narrator_text = (state.get("_narrator_text") or "").strip()
    char_responses = state.get("_character_responses") or {}
    characters = state.get("characters") or {}

    # Build bubbles list
    bubbles = []

    if narrator_text:
        bubbles.append({
            "type": "narrator",
            "text": narrator_text,
        })

    for npc_key, resp in char_responses.items():
        if not isinstance(resp, dict):
            continue
        label = npc_key.replace("_", " ").title()
        dialogue = (resp.get("dialogue") or "").strip()
        action = (resp.get("action") or "").strip()

        if not dialogue and not action:
            continue

        # Get portrait if available
        char_data = characters.get(npc_key, {})
        portrait = char_data.get("portrait", "") if isinstance(char_data, dict) else ""

        bubble = {
            "type": "character",
            "name": label,
            "key": npc_key,
        }
        if dialogue:
            bubble["text"] = dialogue
        if action:
            bubble["action"] = action
        if portrait:
            bubble["portrait"] = portrait

        bubbles.append(bubble)

    # Build combined legacy response string
    parts = []
    if narrator_text:
        parts.append(narrator_text)
    for npc_key, resp in char_responses.items():
        if not isinstance(resp, dict):
            continue
        label = npc_key.replace("_", " ").title()
        action = (resp.get("action") or "").strip()
        dialogue = (resp.get("dialogue") or "").strip()
        if action:
            parts.append(f"*{label} {action}*")
        if dialogue:
            parts.append(f'{label}: "{dialogue}"')

    response = "\n\n".join(parts) if parts else "..."

    return {
        "response": response,
        "_bubbles": bubbles,
    }
