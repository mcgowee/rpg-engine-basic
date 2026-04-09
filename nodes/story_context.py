"""Shared story context builder — extracts genre, tone, and NSFW metadata from state.

Used by any node that needs story metadata in its prompt. Reads from state["story"]
which is populated by _build_state_from_story() in app.py.
"""


def build_story_context(state: dict) -> str:
    """Build a one-line summary of genre, tone, and content rating from state.

    Returns a string like:
        'Genre: romance | Tone: dark, romantic | Content rating: explicit (gay/lesbian, dom/sub)'
    or empty string if no story metadata is available.
    """
    story = state.get("story") or {}
    parts = []

    if story.get("genre"):
        parts.append(f"Genre: {story['genre']}")
    if story.get("tone"):
        parts.append(f"Tone: {story['tone']}")
    if story.get("setting"):
        parts.append(f"Setting: {story['setting']}")

    nsfw = story.get("nsfw_rating", "none")
    if nsfw and nsfw != "none":
        tags = story.get("nsfw_tags", [])
        tag_str = f" ({', '.join(tags)})" if tags else ""
        parts.append(f"Content rating: {nsfw}{tag_str}")
    else:
        parts.append("Content rating: clean (no sexual or graphic content)")

    return " | ".join(parts) if parts else ""


def build_story_context_for_guard(state: dict) -> str:
    """Build a genre/tone hint for the quality guard prompt.

    Returns a string to append to the guard's prompt, or empty string.
    Includes instruction to stay on-tone.
    """
    story = state.get("story") or {}
    title = story.get("title", "")
    parts = []

    if story.get("genre"):
        parts.append(f"Genre: {story['genre']}")
    if story.get("tone"):
        parts.append(f"Tone: {story['tone']}")
    if story.get("setting"):
        parts.append(f"Setting: {story['setting']}")

    nsfw = story.get("nsfw_rating", "none")
    if nsfw and nsfw != "none":
        tags = story.get("nsfw_tags", [])
        tag_str = ", ".join(tags) if tags else ""
        parts.append(f"NSFW rating: {nsfw}" + (f" ({tag_str})" if tag_str else ""))

    if parts:
        return "\n" + ". ".join(parts) + ". Keep suggestions grounded in this tone and rating."
    elif title:
        return f"\nStory title: {title}. Keep suggestions consistent with the story's established tone."
    return ""
