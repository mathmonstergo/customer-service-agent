from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable


INTENT_FAQ_EXACT = "faq_exact"
INTENT_PROCEDURE = "procedure"
INTENT_TROUBLESHOOTING = "troubleshooting"
INTENT_REALTIME_STATUS = "realtime_status"
INTENT_CHITCHAT = "chitchat_or_out_of_scope"
INTENT_SENSITIVE = "sensitive_or_forbidden"

DOMAIN_KEYWORDS = (
    "团体报告",
    "测评报告",
    "报告",
    "生成",
    "导出",
    "下载",
    "登录",
    "密码",
    "账号",
    "账户",
    "订单",
    "退款",
    "发票",
    "上传",
    "配置",
    "审核",
    "失败",
    "报错",
    "无法",
    "权限",
    "微信",
    "后台",
    "状态",
    "进度",
)


@dataclass(frozen=True)
class QueryAnalysis:
    """表示用户问题的检索意图，关键约束是只影响召回策略，不直接生成答案。"""

    intent: str
    confidence: str
    query: str
    query_rewrite: str
    preferred_sources: list[str]
    must_not_answer_realtime: bool = False
    safety_action: str = "answer_with_retrieval"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为前端调试事件可直接序列化的字典。"""
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "query": self.query,
            "query_rewrite": self.query_rewrite,
            "preferred_sources": self.preferred_sources,
            "must_not_answer_realtime": self.must_not_answer_realtime,
            "safety_action": self.safety_action,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FusedCandidate:
    """表示多路召回融合后的候选，保留来源通道和原始分数供调试。"""

    document: Any
    fused_score: float
    channels: tuple[str, ...]
    vector_score: float | None = None
    keyword_score: float | None = None


@dataclass(frozen=True)
class EvalCaseResult:
    """表示单条检索评测结果，关键约束是 expected_ids 和 retrieved_ids 使用同一 id 口径。"""

    question: str
    expected_ids: list[str]
    retrieved_ids: list[str]


def analyze_query(question: str, chat: Any | None = None) -> QueryAnalysis:
    """分析用户问题意图；规则高置信命中优先，低置信场景可用 Chat 模型兜底。"""
    text = _normalize_query(question)
    analysis = _analyze_query_by_rules(text)
    if analysis.confidence == "high" or chat is None:
        return analysis
    fallback = _analyze_query_with_chat(text, chat)
    return fallback or analysis


def fuse_retrieval_candidates(
    *,
    vector_docs: Iterable[Any],
    keyword_docs: Iterable[Any],
    top_k: int,
    rrf_k: int = 60,
) -> list[FusedCandidate]:
    """用 RRF 融合向量和关键词候选，同一知识单元多通道命中时排位更靠前。"""
    candidates: dict[str, dict[str, Any]] = {}

    def add_channel(docs: Iterable[Any], channel: str) -> None:
        for rank, doc in enumerate(docs, start=1):
            doc_id = str(getattr(doc, "id"))
            item = candidates.setdefault(
                doc_id,
                {
                    "document": doc,
                    "fused_score": 0.0,
                    "channels": [],
                    "vector_score": None,
                    "keyword_score": None,
                },
            )
            item["fused_score"] += 1.0 / (rrf_k + rank)
            if channel not in item["channels"]:
                item["channels"].append(channel)
            score = float(getattr(doc, "score", 0.0) or 0.0)
            if channel == "vector":
                item["vector_score"] = score
            if channel == "keyword":
                item["keyword_score"] = score

    add_channel(vector_docs, "vector")
    add_channel(keyword_docs, "keyword")

    fused = [
        FusedCandidate(
            document=item["document"],
            fused_score=float(item["fused_score"]),
            channels=tuple(item["channels"]),
            vector_score=item["vector_score"],
            keyword_score=item["keyword_score"],
        )
        for item in candidates.values()
    ]
    return sorted(
        fused,
        key=lambda item: (
            item.fused_score,
            item.vector_score if item.vector_score is not None else -1.0,
            item.keyword_score if item.keyword_score is not None else -1.0,
        ),
        reverse=True,
    )[:top_k]


def build_keyword_terms(question: str, aliases: Iterable[dict[str, Any]] | None = None) -> list[str]:
    """构建关键词召回词表，关键约束是保留错误码并用人工别名扩展。"""
    text = _normalize_query(question)
    terms: list[str] = []

    for code in re.findall(r"\b[A-Za-z]+[-_]?\d{2,}[A-Za-z0-9_-]*\b", text):
        _append_unique(terms, code.upper())

    alias_rows = list(aliases or [])
    for row in alias_rows:
        canonical = str(row.get("canonical") or "").strip()
        row_aliases = _coerce_aliases(row.get("aliases"))
        matched_aliases = [alias for alias in row_aliases if alias in text]
        matched = bool(canonical and canonical in text) or bool(matched_aliases)
        if not matched:
            continue
        for alias in matched_aliases:
            _append_unique(terms, alias)
        if canonical:
            _append_unique(terms, canonical)
        for alias in row_aliases:
            _append_unique(terms, alias)

    for keyword in DOMAIN_KEYWORDS:
        if keyword in text:
            _append_unique(terms, keyword)

    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", text):
        upper = token.upper()
        if upper not in terms:
            _append_unique(terms, token)

    return terms[:20]


def compute_retrieval_metrics(cases: list[EvalCaseResult], *, k: int) -> dict[str, Any]:
    """计算检索评测指标，第一版聚焦 Recall@K、MRR 和首位命中率。"""
    if not cases:
        return {"case_count": 0, "recall_at_k": 0.0, "mrr": 0.0, "hit_rate_at_1": 0.0}

    recall_hits = 0
    reciprocal_ranks = 0.0
    top1_hits = 0
    for case in cases:
        expected = set(case.expected_ids)
        retrieved = case.retrieved_ids[:k]
        if not expected:
            continue
        if expected.intersection(retrieved):
            recall_hits += 1
        if retrieved and retrieved[0] in expected:
            top1_hits += 1
        for index, doc_id in enumerate(retrieved, start=1):
            if doc_id in expected:
                reciprocal_ranks += 1.0 / index
                break

    case_count = len(cases)
    return {
        "case_count": case_count,
        "recall_at_k": recall_hits / case_count,
        "mrr": reciprocal_ranks / case_count,
        "hit_rate_at_1": top1_hits / case_count,
    }


def _normalize_query(question: str) -> str:
    """清理用户问题的首尾空白，避免规则识别受换行和多空格影响。"""
    return re.sub(r"\s+", " ", str(question or "").strip())


def _analyze_query_by_rules(text: str) -> QueryAnalysis:
    """规则识别高确定性意图，关键约束是宁可保守也不误判敏感和实时状态。"""
    lowered = text.lower()
    if _contains_any(
        lowered,
        (
            "api key",
            "apikey",
            "secret",
            "access token",
            "system prompt",
            "系统提示词",
            "密钥",
            "数据库密码",
            "微信 token",
            "后台密码",
        ),
    ):
        return QueryAnalysis(
            intent=INTENT_SENSITIVE,
            confidence="high",
            query=text,
            query_rewrite=text,
            preferred_sources=[],
            safety_action="refuse",
            reason="命中敏感信息规则",
        )

    if _contains_any(
        text,
        ("现在", "当前", "实时", "到哪一步", "处理到哪", "有没有完成", "是否完成", "进度"),
    ) and _contains_any(text, ("状态", "报告", "订单", "账号", "后台", "生成", "处理")):
        return QueryAnalysis(
            intent=INTENT_REALTIME_STATUS,
            confidence="high",
            query=text,
            query_rewrite=text,
            preferred_sources=["faq", "document"],
            must_not_answer_realtime=True,
            reason="命中实时状态规则",
        )

    if _contains_any(
        text,
        ("怎么办", "无法", "不能", "失败", "报错", "没有生成", "没生成", "打不开", "登不上", "异常"),
    ):
        return QueryAnalysis(
            intent=INTENT_TROUBLESHOOTING,
            confidence="high",
            query=text,
            query_rewrite=text,
            preferred_sources=["faq", "document"],
            reason="命中故障排查规则",
        )

    if _contains_any(text, ("怎么", "如何", "步骤", "流程", "操作", "在哪里", "导出", "上传", "配置")):
        return QueryAnalysis(
            intent=INTENT_PROCEDURE,
            confidence="high",
            query=text,
            query_rewrite=text,
            preferred_sources=["document", "faq"],
            reason="命中操作流程规则",
        )

    if text in {"你好", "您好", "谢谢", "感谢", "在吗"}:
        return QueryAnalysis(
            intent=INTENT_CHITCHAT,
            confidence="high",
            query=text,
            query_rewrite=text,
            preferred_sources=[],
            safety_action="smalltalk",
            reason="命中闲聊规则",
        )

    return QueryAnalysis(
        intent=INTENT_FAQ_EXACT,
        confidence="medium",
        query=text,
        query_rewrite=text,
        preferred_sources=["faq", "document"],
        reason="未命中高置信规则，默认按标准知识库问答处理",
    )


def _analyze_query_with_chat(text: str, chat: Any) -> QueryAnalysis | None:
    """调用 Chat 模型做低置信兜底，只接受结构化 JSON，失败时回退规则结果。"""
    complete = getattr(chat, "complete", None)
    if complete is None:
        return None
    prompt = "\n".join(
        [
            "请判断客服知识库问题的检索意图，只输出 JSON。",
            "intent 只能是 faq_exact、procedure、troubleshooting、realtime_status、chitchat_or_out_of_scope、sensitive_or_forbidden。",
            "字段：intent, confidence, query_rewrite, preferred_sources, must_not_answer_realtime, safety_action, reason。",
            f"用户问题：{text}",
        ]
    )
    try:
        raw = complete("你是客服知识库检索意图分类器。", prompt)
        data = json.loads(str(raw))
    except Exception:
        return None
    intent = str(data.get("intent") or INTENT_FAQ_EXACT)
    if intent not in {
        INTENT_FAQ_EXACT,
        INTENT_PROCEDURE,
        INTENT_TROUBLESHOOTING,
        INTENT_REALTIME_STATUS,
        INTENT_CHITCHAT,
        INTENT_SENSITIVE,
    }:
        return None
    preferred_sources = data.get("preferred_sources")
    if not isinstance(preferred_sources, list):
        preferred_sources = ["faq", "document"]
    return QueryAnalysis(
        intent=intent,
        confidence=str(data.get("confidence") or "medium"),
        query=text,
        query_rewrite=str(data.get("query_rewrite") or text).strip() or text,
        preferred_sources=[str(item) for item in preferred_sources],
        must_not_answer_realtime=bool(data.get("must_not_answer_realtime")),
        safety_action=str(data.get("safety_action") or "answer_with_retrieval"),
        reason=str(data.get("reason") or "Chat 模型兜底识别"),
    )


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    """判断文本是否包含任一关键词，保持规则实现直接可读。"""
    return any(needle in text for needle in needles)


def _append_unique(values: list[str], value: str) -> None:
    """追加非空唯一词，保持关键词构造顺序稳定。"""
    normalized = str(value or "").strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _coerce_aliases(value: Any) -> list[str]:
    """把数据库或测试中的别名字段整理成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [item.strip() for item in value.split(",") if item.strip()]
        value = parsed
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
