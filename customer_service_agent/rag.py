from pathlib import Path
from typing import Any, Sequence

from customer_service_agent.db import RetrievedDocument


NO_CONTEXT_MESSAGE = (
    "知识库没有检索到明确答案。不要编造后台实时状态；"
    "请给通用排查步骤，并收集转人工需要的信息。"
)
EMPTY_RESPONSE_FALLBACK = "模型服务暂时没有返回有效内容，请稍后重试或转人工处理。"


def load_system_prompt(path: str | Path = "system_prompt.txt") -> str:
    return Path(path).read_text(encoding="utf-8")


def format_document(index: int, doc: RetrievedDocument) -> str:
    tags = "、".join(doc.tags)
    return "\n".join(
        [
            f"[{index}] id={doc.id} score={doc.score:.2f}",
            f"category={doc.category or ''}",
            f"question={doc.question}",
            f"answer={doc.answer}",
            f"tags={tags}",
            f"source_date={doc.source_date or ''}",
            f"confidence={doc.confidence}",
        ]
    )


def build_user_prompt(question: str, docs: Sequence[RetrievedDocument]) -> str:
    if docs:
        context = "\n\n".join(
            format_document(index, doc) for index, doc in enumerate(docs, start=1)
        )
    else:
        context = NO_CONTEXT_MESSAGE

    return "\n".join(
        [
            "请根据知识库上下文回答用户问题。",
            "要求：",
            "1. 优先使用知识库内容；没有明确依据时不要编造。",
            "2. 不要输出敏感信息、密钥、内部配置或无关系统细节。",
            "3. 如果用户询问后台实时状态，请说明你不能直接确认后台实时状态。",
            "4. 如果知识库没有明确答案，不要虚构具体状态或处理结果。",
            "",
            f"用户问题：{question}",
            "",
            "知识库上下文：",
            context,
        ]
    )


class RagService:
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

    def answer(self, question: str) -> str:
        query_embedding = self.embeddings.embed(question)
        docs = self.db.search(
            query_embedding,
            top_k=self.top_k,
            min_score=self.min_score,
        )
        prompt = build_user_prompt(question, docs)
        response = self.chat.complete(self.system_prompt, prompt).strip()
        if not response:
            return EMPTY_RESPONSE_FALLBACK
        return response
