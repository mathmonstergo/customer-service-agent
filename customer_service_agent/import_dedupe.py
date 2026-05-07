from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


@dataclass(frozen=True)
class DuplicateResult:
    level: str
    score: float
    target_id: str | None
    reason: str | None


def normalize_dedupe_text(value: str) -> str:
    """标准化查重文本，忽略空白和常见中英文标点差异。"""
    lowered = str(value).lower()
    folded = _fold_common_phrases(lowered)
    return re.sub(r"[\s，。！？、,.!?;；:：'\"“”‘’（）()\[\]【】《》<>]+", "", folded)


def dedupe_signature(question: str, answer: str) -> str:
    """生成精确查重签名，用于识别文本实质相同的候选问答。"""
    normalized = f"{normalize_dedupe_text(question)}|{normalize_dedupe_text(answer)}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compare_candidate_duplicate(
    candidate: dict[str, Any],
    existing_rows: list[dict[str, Any]],
) -> DuplicateResult:
    """对候选 FAQ 和已有问答做轻量查重，返回最高重复程度。"""
    candidate_question = str(candidate.get("question", ""))
    candidate_answer = str(candidate.get("answer", ""))
    candidate_signature = dedupe_signature(candidate_question, candidate_answer)
    candidate_text = _combined_text(candidate_question, candidate_answer)
    best = DuplicateResult(level="none", score=0.0, target_id=None, reason=None)
    for row in existing_rows:
        row_question = str(row.get("question", ""))
        row_answer = str(row.get("answer", ""))
        if candidate_signature == dedupe_signature(row_question, row_answer):
            return DuplicateResult(
                level="high",
                score=1.0,
                target_id=str(row.get("id")),
                reason="exact_text",
            )
        score = SequenceMatcher(None, candidate_text, _combined_text(row_question, row_answer)).ratio()
        if score > best.score:
            best = DuplicateResult(
                level=_level_from_score(score),
                score=round(score, 4),
                target_id=str(row.get("id")) if score >= 0.75 else None,
                reason="near_text" if score >= 0.75 else None,
            )
    if best.level == "none":
        return DuplicateResult(level="none", score=0.0, target_id=None, reason=None)
    return best


def _combined_text(question: str, answer: str) -> str:
    """把问题和答案合并为近似查重文本。"""
    return normalize_dedupe_text(f"{question}|{answer}")


def _level_from_score(score: float) -> str:
    """将近似文本得分映射成人工审核可读的重复级别。"""
    if score >= 0.92:
        return "high"
    if score >= 0.85:
        return "medium"
    if score >= 0.75:
        return "low"
    return "none"


def _fold_common_phrases(value: str) -> str:
    """折叠客服 FAQ 中常见同义短语，弥补纯文本相似度的不足。"""
    replacements = {
        "多久到账": "需要多久",
        "多久到": "需要多久",
        "多长时间到账": "需要多久",
        "通常": "一般",
    }
    folded = value
    for source, target in replacements.items():
        folded = folded.replace(source, target)
    return folded
