"""customer_service_agent.db 包：按业务域拆分的数据库层。

对外暴露与旧 db.py 完全相同的 public 接口：
- Database 类（通过 5 个业务 mixin 继承 BaseDatabase 组合而成）
- RetrievedDocument / RetrievedKnowledgeChunk dataclass
- format_vector / score_to_distance
- build_* / compute_* / next_embedding_status / empty_import_file_embedding_summary
"""

from __future__ import annotations

from customer_service_agent.db.analytics import AnalyticsMixin
from customer_service_agent.db.base import BaseDatabase
from customer_service_agent.db.builders import (
    build_document_knowledge_chunk_row,
    build_embedding_text,
    build_faq_knowledge_chunk_row,
    build_import_candidate_faq_row,
    compute_content_hash,
    compute_knowledge_chunk_hash,
    empty_import_file_embedding_summary,
    next_embedding_status,
)
from customer_service_agent.db.faq import FaqMixin
from customer_service_agent.db.imports import ImportMixin
from customer_service_agent.db.knowledge import KnowledgeMixin
from customer_service_agent.db.models import (
    RetrievedDocument,
    RetrievedKnowledgeChunk,
    format_vector,
    score_to_distance,
)
from customer_service_agent.db.retrieval_meta import RetrievalMetaMixin


class Database(
    FaqMixin,
    KnowledgeMixin,
    ImportMixin,
    RetrievalMetaMixin,
    AnalyticsMixin,
    BaseDatabase,
):
    """统一数据库入口：5 个业务 mixin 共享 BaseDatabase 的连接管理。"""

    pass


__all__ = [
    "Database",
    "RetrievedDocument",
    "RetrievedKnowledgeChunk",
    "format_vector",
    "score_to_distance",
    "build_embedding_text",
    "build_faq_knowledge_chunk_row",
    "build_document_knowledge_chunk_row",
    "build_import_candidate_faq_row",
    "compute_content_hash",
    "compute_knowledge_chunk_hash",
    "next_embedding_status",
    "empty_import_file_embedding_summary",
]
