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
