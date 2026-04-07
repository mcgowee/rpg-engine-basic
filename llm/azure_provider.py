"""Azure OpenAI LLM provider."""

from config import AZURE_ENDPOINT, AZURE_API_KEY, AZURE_API_VERSION, AZURE_DEPLOYMENT


class AzureProvider:
    def __init__(self, model_name: str):
        # TODO: Port from v1
        from openai import AzureOpenAI
        self._client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            api_version=AZURE_API_VERSION,
        )
        self._deployment = AZURE_DEPLOYMENT

    def invoke(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )
        return response.choices[0].message.content or ""
