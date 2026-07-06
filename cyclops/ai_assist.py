from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


class AiSuggestionError(ValueError):
    pass


@dataclass(frozen=True)
class AiSuggestion:
    optimized_question: str
    optimized_answer: str
    similar_questions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "optimized_question": self.optimized_question,
            "optimized_answer": self.optimized_answer,
            "similar_questions": self.similar_questions,
        }


class AiAssistant:
    def __init__(self, chat: Any):
        self.chat = chat

    def optimize(self, question: str, answer: str) -> AiSuggestion:
        response = self.chat.complete(
            self._system_prompt(),
            self._user_prompt(question, answer),
        )
        payload = self._parse_json_object(response)
        missing = [
            field
            for field in ("optimized_question", "optimized_answer", "similar_questions")
            if field not in payload
        ]
        if missing:
            raise AiSuggestionError(f"AI suggestion missing field: {', '.join(missing)}")

        variants = payload["similar_questions"]
        if not isinstance(variants, list):
            raise AiSuggestionError("AI suggestion field similar_questions must be a list")

        return AiSuggestion(
            optimized_question=str(payload["optimized_question"]).strip(),
            optimized_answer=str(payload["optimized_answer"]).strip(),
            similar_questions=[str(item).strip() for item in variants if str(item).strip()],
        )

    @staticmethod
    def _system_prompt() -> str:
        return "\n".join(
            [
                "你是客服知识库编辑助手，只做保守改写。",
                "必须遵守：不新增业务事实，不编造流程，不改变原始答复含义。",
                "只优化表达、结构、清晰度和客服口吻。",
                "请输出一个 JSON 对象，不要输出 Markdown。",
                "JSON 字段必须是 optimized_question, optimized_answer, similar_questions。",
                "similar_questions 生成 5 到 10 条自然问法。",
            ]
        )

    @staticmethod
    def _user_prompt(question: str, answer: str) -> str:
        return "\n".join(
            [
                "请优化以下 FAQ：",
                "",
                f"原始问题：{question}",
                "",
                f"原始答复：{answer}",
            ]
        )

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        stripped = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.S)
        if fence_match:
            stripped = fence_match.group(1)
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AiSuggestionError("AI suggestion must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise AiSuggestionError("AI suggestion must be a JSON object")
        return payload
