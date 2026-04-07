"""LLM provider protocol — interface all providers must implement."""

from typing import Protocol


class LLMProvider(Protocol):
    def invoke(self, prompt: str) -> str:
        """Send a prompt and return the response text."""
        ...
