from typing import Any

from openai import OpenAI

from customer_service_agent.config import Settings


def build_openai_client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


class EmbeddingClient:
    def __init__(self, client: Any, *, model: str, dimensions: int):
        self.client = client
        self.model = model
        self.dimensions = dimensions

    @classmethod
    def from_settings(cls, settings: Settings) -> "EmbeddingClient":
        client = build_openai_client(settings.embedding_base_url, settings.embedding_api_key)
        return cls(
            client,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
        )
        return list(response.data[0].embedding)


class ChatClient:
    def __init__(self, client: Any, *, model: str):
        self.client = client
        self.model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> "ChatClient":
        client = build_openai_client(settings.chat_base_url, settings.chat_api_key)
        return cls(client, model=settings.chat_model)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
