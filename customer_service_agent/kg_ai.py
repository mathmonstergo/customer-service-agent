from __future__ import annotations

import re
from typing import Any

from customer_service_agent.kg import parse_kg_extraction_response


class KnowledgeGraphAiAssistant:
    """KG 抽取助手：调用 Chat 模型生成实体/关系候选，结果必须再进入人工审核。"""

    def __init__(self, chat: Any):
        self.chat = chat
        self.model = str(getattr(chat, "model", "") or "")

    def extract(self, *, source_text: str, source: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """从单条 FAQ 或文档切片抽取 KG 候选，关键约束是只返回待审核结构化结果。"""
        response = self.chat.complete(self._system_prompt(), self._user_prompt(source_text, source))
        return parse_kg_extraction_response(self._strip_json_fence(response), source=source)

    @staticmethod
    def _system_prompt() -> str:
        """约束模型使用固定客服领域 schema，避免自由造类型或事实。"""
        return "\n".join(
            [
                "你是客服知识图谱抽取助手。",
                "只从来源文本中抽取明确出现或可由文本直接支持的实体、关系和证据。",
                "不要补充来源文本没有支持的事实，不要输出客户隐私、密钥、token、一次性账号密码。",
                "实体类型只能使用：product_platform_module, feature_ui_action, error_symptom, process_task_object, role_permission_channel, condition_policy。",
                "关系类型只能使用：belongs_to, requires, causes, resolves_by, blocked_by, available_for, escalate_when。",
                "每个实体和关系都必须带 evidence 数组，每条 evidence 必须包含 excerpt。",
                "输出 JSON 对象，不要输出 Markdown。",
                "JSON 顶层字段为 entities 和 relations。",
                "entities 每项包含 name, entity_type, aliases, description, confidence, evidence。",
                "relations 每项包含 head, head_type, relation_type, tail, tail_type, description, confidence, evidence。",
            ]
        )

    @staticmethod
    def _user_prompt(source_text: str, source: dict[str, Any]) -> str:
        """构造来源提示，关键约束是明确来源信息和原文边界。"""
        source_title = str(source.get("source_title") or "").strip()
        section_path = " > ".join(str(item) for item in source.get("section_path") or [])
        parts = ["请从以下来源文本抽取知识图谱候选。"]
        if source_title:
            parts.append(f"来源标题：{source_title}")
        if section_path:
            parts.append(f"章节：{section_path}")
        page_start = source.get("page_start")
        page_end = source.get("page_end")
        if page_start is not None or page_end is not None:
            start_text = str(page_start) if page_start is not None else ""
            end_text = str(page_end) if page_end is not None else ""
            parts.append(f"页码：{start_text}-{end_text}".strip("-"))
        parts.extend(["", "来源文本：", str(source_text or "").strip()])
        return "\n".join(parts)

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        """兼容模型把 JSON 包在 ```json fence 里的情况，用括号计数正确提取嵌套 JSON。"""
        stripped = str(text or "").strip()
        # 找到第一个 ``` 标记，然后找到第一个 {，计数匹配 }
        fence_start = stripped.find("```")
        if fence_start == -1:
            return stripped
        after_fence = stripped[fence_start + 3:]
        # 跳过可选的 json 标记
        after_fence = after_fence.removeprefix("json").lstrip()
        brace_start = after_fence.find("{")
        if brace_start == -1:
            return stripped
        # 括号计数找到匹配的 }
        depth = 0
        brace_end = -1
        for i in range(brace_start, len(after_fence)):
            ch = after_fence[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break
        if brace_end == -1:
            return stripped
        return after_fence[brace_start:brace_end + 1]
