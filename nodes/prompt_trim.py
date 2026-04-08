"""Trim long strings before they go into LLM prompts (full state.history stays untrimmed)."""


def truncate_prompt_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or not text or len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
