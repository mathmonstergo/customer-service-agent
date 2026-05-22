from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests
from openai import OpenAI

from customer_service_agent.config import Settings


logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class RerankResult:
    """归一化的 rerank 返回单元，index 指向原候选位置，relevance_score 用于排序。"""

    index: int
    relevance_score: float


class RerankClient:
    """Cohere /v1/rerank 兼容协议的客户端，配齐三项配置才会被实例化。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        input_size: int = 50,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.input_size = input_size
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings | Any) -> "RerankClient | None":
        base_url = str(getattr(settings, "rerank_base_url", "") or "").strip()
        api_key = str(getattr(settings, "rerank_api_key", "") or "").strip()
        model = str(getattr(settings, "rerank_model", "") or "").strip()
        if not (base_url and api_key and model):
            return None
        input_size = int(getattr(settings, "rerank_input_size", 50) or 50)
        return cls(base_url=base_url, api_key=api_key, model=model, input_size=input_size)

    def rerank(self, query: str, documents: list[str], *, top_n: int) -> list[RerankResult]:
        """调用 rerank API，失败时返回空列表，让上层透传原候选。"""
        url = f"{self.base_url}/v1/rerank"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body = {
            "model": self.model,
            "query": query,
            "documents": list(documents),
            "top_n": top_n,
        }
        try:
            response = requests.post(url, json=body, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("rerank call failed: %s", exc, exc_info=True)
            return []
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        normalized: list[RerankResult] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item["index"])
                score = float(item["relevance_score"])
            except (KeyError, TypeError, ValueError):
                continue
            normalized.append(RerankResult(index=index, relevance_score=score))
        return normalized
