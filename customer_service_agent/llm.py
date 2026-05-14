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

    @staticmethod
    def _messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
        """构造 Chat messages；系统提示词为空时不发送空 system 消息。"""
        messages: list[dict[str, str]] = []
        if str(system_prompt or "").strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """同步生成完整回答，用于非流式内部任务。"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self._messages(system_prompt, user_prompt),
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def stream_complete(self, system_prompt: str, user_prompt: str):
        """流式生成回答片段，关键约束是只产出非空 delta 文本。"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self._messages(system_prompt, user_prompt),
            temperature=0.2,
            stream=True,
        )
        for chunk in response:
            choices = getattr(chunk, "choices", [])
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if content:
                yield content
