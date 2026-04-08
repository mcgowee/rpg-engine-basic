"""Ollama LLM provider — ChatOllama, normalized text output."""

from config import OLLAMA_HOST
from llm.text import llm_result_to_text


class OllamaProvider:
    def __init__(self, model_name: str):
        from langchain_ollama import ChatOllama

        self._llm = ChatOllama(model=model_name, base_url=OLLAMA_HOST)

    def invoke(self, prompt: str) -> str:
        return llm_result_to_text(self._llm.invoke(prompt))
