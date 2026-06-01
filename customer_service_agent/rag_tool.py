from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from customer_service_agent.db import RetrievedDocument
from customer_service_agent.rag import EMPTY_RESPONSE_FALLBACK, build_user_prompt


@dataclass(frozen=True)
class RagToolDocument:
    id: str
    score: float
    question: str
    answer: str
    category: str | None
    tags: list[str]
    source_date: str | None
    confidence: str
    status: str

    @classmethod
    def from_retrieved(cls, doc: RetrievedDocument) -> "RagToolDocument":
        return cls(
            id=doc.id,
            score=doc.score,
            question=doc.question,
            answer=doc.answer,
            category=doc.category,
            tags=doc.tags,
            source_date=doc.source_date,
            confidence=doc.confidence,
            status=doc.status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
            "tags": self.tags,
            "source_date": self.source_date,
            "confidence": self.confidence,
            "status": self.status,
        }


@dataclass(frozen=True)
class RagToolSearchResult:
    question: str
    documents: list[RagToolDocument]
    top_k: int
    min_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": "faq_rag",
            "mode": "search",
            "question": self.question,
            "has_context": bool(self.documents),
            "top_score": self.documents[0].score if self.documents else None,
            "top_k": self.top_k,
            "min_score": self.min_score,
            "documents": [doc.to_dict() for doc in self.documents],
        }


@dataclass(frozen=True)
class RagToolAnswerResult:
    question: str
    answer_draft: str
    documents: list[RagToolDocument]
    top_k: int
    min_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": "faq_rag",
            "mode": "answer_draft",
            "question": self.question,
            "answer_draft": self.answer_draft,
            "has_context": bool(self.documents),
            "top_score": self.documents[0].score if self.documents else None,
            "top_k": self.top_k,
            "min_score": self.min_score,
            "documents": [doc.to_dict() for doc in self.documents],
        }


class RagTool:
    def __init__(
        self,
        embeddings: Any,
        db: Any,
        chat: Any,
        system_prompt: str,
        top_k: int,
        min_score: float,
    ):
        self.embeddings = embeddings
        self.db = db
        self.chat = chat
        self.system_prompt = system_prompt
        self.top_k = top_k
        self.min_score = min_score

    def search(self, question: str) -> RagToolSearchResult:
        docs = self._retrieve(question)
        return RagToolSearchResult(
            question=question,
            documents=[RagToolDocument.from_retrieved(doc) for doc in docs],
            top_k=self.top_k,
            min_score=self.min_score,
        )

    def answer(self, question: str) -> RagToolAnswerResult:
        docs = self._retrieve(question)
        prompt = build_user_prompt(question, docs)
        answer_draft = self.chat.complete(self.system_prompt, prompt).strip()
        if not answer_draft:
            answer_draft = EMPTY_RESPONSE_FALLBACK
        return RagToolAnswerResult(
            question=question,
            answer_draft=answer_draft,
            documents=[RagToolDocument.from_retrieved(doc) for doc in docs],
            top_k=self.top_k,
            min_score=self.min_score,
        )

    def _retrieve(self, question: str) -> list[RetrievedDocument]:
        query_embedding = self.embeddings.embed(question)
        return self.db.search(
            query_embedding,
            top_k=self.top_k,
            min_score=self.min_score,
        )

    def stream_answer(self, question: str) -> Iterator[dict[str, Any]]:
        """流式回答生成器；先 yield 多个 delta 事件，最后 yield 一个 final 事件。

        关键约束：每个 delta 事件形如 {"type": "delta", "text": "..."}，
        final 事件含完整 answer_draft + documents + top_score + hit_count，
        供上游 MCP / SSE 等流式 transport 直接转发。空回复时给占位文案。
        """
        docs = self._retrieve(question)
        prompt = build_user_prompt(question, docs)
        parts: list[str] = []
        for delta in self.chat.stream_complete(self.system_prompt, prompt):
            if not delta:
                continue
            parts.append(delta)
            yield {"type": "delta", "text": delta}
        answer_draft = "".join(parts).strip()
        if not answer_draft:
            answer_draft = EMPTY_RESPONSE_FALLBACK
        documents = [RagToolDocument.from_retrieved(doc) for doc in docs]
        yield {
            "type": "final",
            "answer_draft": answer_draft,
            "documents": [doc.to_dict() for doc in documents],
            "top_score": documents[0].score if documents else None,
            "hit_count": len(documents),
            "top_k": self.top_k,
            "min_score": self.min_score,
            "has_context": bool(documents),
        }
