from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
