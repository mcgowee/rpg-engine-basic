"""LLM abstraction — factory + cache. Same interface regardless of provider."""

# TODO: Port from v1 ~/projects/roleplay-langgraph/llm/__init__.py

from llm.base import LLMProvider

_cache = {}


def get_llm(model: str = "") -> LLMProvider:
    """Get or create an LLM provider instance. Cached by model name."""
    from config import LLM_PROVIDER, DEFAULT_MODEL

    model = model or DEFAULT_MODEL
    if model == "default":
        model = DEFAULT_MODEL

    cache_key = f"{LLM_PROVIDER}:{model}"
    if cache_key not in _cache:
        if LLM_PROVIDER == "azure":
            from llm.azure_provider import AzureProvider
            _cache[cache_key] = AzureProvider(model)
        else:
            from llm.ollama_provider import OllamaProvider
            _cache[cache_key] = OllamaProvider(model)

    return _cache[cache_key]
