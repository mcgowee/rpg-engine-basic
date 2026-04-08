"""Unit tests for narrator prompt alignment (no LLM)."""

from nodes.narrator import (
    DEFAULT_NARRATOR_PROMPT,
    DEFAULT_NARRATOR_PROMPT_SEPARATE_NPC,
    _effective_narrator_prompt,
)


def test_effective_prompt_unchanged_when_not_separate_layer():
    assert _effective_narrator_prompt(DEFAULT_NARRATOR_PROMPT, False) == DEFAULT_NARRATOR_PROMPT
    custom = "You are a grim narrator. End each beat with: What next?"
    assert _effective_narrator_prompt(custom, False) == custom


def test_effective_prompt_default_becomes_separate_variant():
    out = _effective_narrator_prompt(DEFAULT_NARRATOR_PROMPT, True)
    assert out == DEFAULT_NARRATOR_PROMPT_SEPARATE_NPC
    assert "What do you do" not in out


def test_effective_prompt_custom_gets_override_suffix():
    custom = "You are a grim narrator. Always ask what the player does at the end."
    out = _effective_narrator_prompt(custom, True)
    assert out.startswith(custom)
    assert "Turn structure:" in out and "Ignore any instruction above" in out
