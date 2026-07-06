from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


def format_vector(values: Iterable[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def score_to_distance(score: float) -> float:
    return 1.0 - score


@dataclass(frozen=True)
class RetrievedDocument:
    id: str
    question: str
    answer: str
    category: str | None
    tags: list[str]
    source_date: str | None
    confidence: str
    status: str
    score: float


@dataclass(frozen=True)
class RetrievedKnowledgeChunk:
    """统一知识单元检索结果，兼容 FAQ 和文档切片两类来源。"""

    id: str
    source_type: str
    source_id: str
    source_chunk_id: str | None
    parent_chunk_id: str | None
    chunk_level: str
    source_title: str | None
    section_path: list[str]
    page_start: int | None
    page_end: int | None
    block_type: str | None
    source_offsets: dict[str, Any]
    content: str
    metadata: dict[str, Any]
    tags: list[str]
    confidence: str | None
    status: str
    score: float

    @property
    def question(self) -> str:
        """兼容旧 RAG prompt 的问题字段，文档切片使用来源标题。"""
        return self.source_title or self.source_id

    @property
    def answer(self) -> str:
        """兼容旧 RAG prompt 的答案字段，统一返回可引用正文。"""
        return self.content

    @property
    def category(self) -> str | None:
        """兼容旧 RAG prompt 的分类字段，优先使用元数据分类。"""
        return self.metadata.get("category") or self.source_type

    @property
    def source_date(self) -> str | None:
        """兼容旧 RAG prompt 的来源日期字段，来自元数据。"""
        value = self.metadata.get("source_date")
        return str(value) if value else None
