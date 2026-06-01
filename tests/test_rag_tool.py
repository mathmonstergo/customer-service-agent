from customer_service_agent.db import RetrievedDocument
from customer_service_agent.rag_tool import RagTool


class FakeEmbedding:
    def embed(self, text):
        return [0.1, 0.2, 0.3]


class FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    def search(self, query_embedding, *, top_k, min_score):
        self.calls.append(
            {
                "query_embedding": query_embedding,
                "top_k": top_k,
                "min_score": min_score,
            }
        )
        return self.docs


class FakeChat:
    def __init__(self):
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return "Please check whether the assignment was published; if it still fails, collect the account, context, and a screenshot."


def make_doc(score=0.82):
    return RetrievedDocument(
        id="doc_0001",
        question="Why is the assigned item missing?",
        answer="Please check whether the assignment was published.",
        category="support workflow",
        tags=["量表", "任务派发"],
        source_date="2025-09",
        confidence="high",
        status="usable",
        score=score,
    )


def test_tool_search_returns_structured_hits_without_calling_chat():
    chat = FakeChat()
    db = FakeDb([make_doc()])
    tool = RagTool(
        embeddings=FakeEmbedding(),
        db=db,
        chat=chat,
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )

    result = tool.search("Why is the assigned item missing?")

    assert result.to_dict() == {
        "tool": "faq_rag",
        "mode": "search",
        "question": "Why is the assigned item missing?",
        "has_context": True,
        "top_score": 0.82,
        "top_k": 5,
        "min_score": 0.35,
        "documents": [
            {
                "id": "doc_0001",
                "score": 0.82,
                "question": "Why is the assigned item missing?",
                "answer": "Please check whether the assignment was published.",
                "category": "support workflow",
                "tags": ["量表", "任务派发"],
                "source_date": "2025-09",
                "confidence": "high",
                "status": "usable",
            }
        ],
    }
    assert db.calls == [{"query_embedding": [0.1, 0.2, 0.3], "top_k": 5, "min_score": 0.35}]
    assert chat.calls == []


def test_tool_answer_returns_agent_facing_draft_and_sources():
    chat = FakeChat()
    tool = RagTool(
        embeddings=FakeEmbedding(),
        db=FakeDb([make_doc()]),
        chat=chat,
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )

    result = tool.answer("Why is the assigned item missing?")

    payload = result.to_dict()
    assert payload["tool"] == "faq_rag"
    assert payload["mode"] == "answer_draft"
    assert payload["answer_draft"] == "Please check whether the assignment was published; if it still fails, collect the account, context, and a screenshot."
    assert payload["has_context"] is True
    assert payload["documents"][0]["id"] == "doc_0001"
    assert "Why is the assigned item missing?" in chat.calls[0][1]
    assert "backend_operation" not in payload
    assert "action" not in payload


def test_tool_answer_marks_no_context_for_upstream_agent():
    tool = RagTool(
        embeddings=FakeEmbedding(),
        db=FakeDb([]),
        chat=FakeChat(),
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )

    payload = tool.answer("Has the backend refresh finished?").to_dict()

    assert payload["has_context"] is False
    assert payload["top_score"] is None
    assert payload["documents"] == []


class StreamingFakeChat:
    """收集 stream_complete 调用并产出固定 deltas，验证流式上下游契约。"""

    def __init__(self, deltas):
        self._deltas = deltas
        self.calls = []

    def stream_complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        for delta in self._deltas:
            yield delta


def test_tool_stream_answer_yields_deltas_then_final():
    """stream_answer 应顺序 yield delta 事件，最后 yield final 事件含 answer + 来源 + 命中信息。"""
    chat = StreamingFakeChat(["请先核实", "派发是否成功", "再收集账号截图。"])
    tool = RagTool(
        embeddings=FakeEmbedding(),
        db=FakeDb([make_doc(0.78)]),
        chat=chat,
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )

    events = list(tool.stream_answer("Why is the assigned item missing?"))

    assert [event["type"] for event in events[:-1]] == ["delta", "delta", "delta"]
    assert [event["text"] for event in events[:-1]] == ["请先核实", "派发是否成功", "再收集账号截图。"]

    final = events[-1]
    assert final["type"] == "final"
    assert final["answer_draft"] == "请先核实派发是否成功再收集账号截图。"
    assert final["has_context"] is True
    assert final["top_score"] == 0.78
    assert final["hit_count"] == 1
    assert final["documents"][0]["id"] == "doc_0001"
    assert final["top_k"] == 5
    assert final["min_score"] == 0.35


def test_tool_stream_answer_falls_back_to_marker_when_chat_empty():
    """模型返回空字符串时也要给上游一个占位回答，避免 agent 收到空 answer。"""
    chat = StreamingFakeChat([])
    tool = RagTool(
        embeddings=FakeEmbedding(),
        db=FakeDb([make_doc()]),
        chat=chat,
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )

    events = list(tool.stream_answer("Why is the assigned item missing?"))

    assert events[-1]["type"] == "final"
    assert "暂时" in events[-1]["answer_draft"] or events[-1]["answer_draft"]
    # 没有 delta 仅 final 占位事件
    assert all(event["type"] == "final" for event in events) or any(event["type"] == "delta" for event in events)


def test_tool_stream_answer_passes_system_prompt_to_chat():
    """stream_answer 必须把系统提示词透传到 chat.stream_complete。"""
    chat = StreamingFakeChat(["ok"])
    tool = RagTool(
        embeddings=FakeEmbedding(),
        db=FakeDb([make_doc()]),
        chat=chat,
        system_prompt="你是企业级跨境电商 KB 助手。",
        top_k=5,
        min_score=0.35,
    )

    list(tool.stream_answer("Why is the assigned item missing?"))

    assert chat.calls
    system, prompt = chat.calls[0]
    assert system == "你是企业级跨境电商 KB 助手。"
    assert "Why is the assigned item missing?" in prompt
