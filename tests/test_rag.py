from customer_service_agent.db import RetrievedDocument
from customer_service_agent.rag import RagService


class FakeEmbedding:
    def embed(self, text):
        return [0.1, 0.2, 0.3]


class FakeDb:
    def __init__(self, docs):
        self.docs = docs

    def search(self, query_embedding, *, top_k, min_score):
        assert query_embedding == [0.1, 0.2, 0.3]
        assert top_k == 5
        assert min_score == 0.35
        return self.docs


class FakeChat:
    def __init__(self):
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return "Please check whether the assignment was published first."


class WhitespaceChat:
    def complete(self, system_prompt, user_prompt):
        return "   \n"


def test_rag_uses_retrieved_context():
    docs = [
        RetrievedDocument(
            id="doc_0001",
            question="Why is the assigned item missing?",
            answer="Please check whether the assignment was published.",
            category="support workflow",
            tags=["量表", "任务派发"],
            source_date="2025-09",
            confidence="high",
            status="usable",
            score=0.82,
        )
    ]
    chat = FakeChat()
    service = RagService(
        embeddings=FakeEmbedding(),
        db=FakeDb(docs),
        chat=chat,
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )
    assert service.answer("Why is the item missing?") == "Please check whether the assignment was published first."
    assert "Why is the assigned item missing?" in chat.calls[0][1]
    assert "score=0.82" in chat.calls[0][1]


def test_rag_handles_no_context_without_claiming_realtime_status():
    chat = FakeChat()
    service = RagService(
        embeddings=FakeEmbedding(),
        db=FakeDb([]),
        chat=chat,
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )
    service.answer("Has the backend refreshed?")
    assert "知识库没有检索到明确答案" in chat.calls[0][1]
    assert "不要编造后台实时状态" in chat.calls[0][1]


def test_rag_returns_safe_fallback_for_whitespace_model_response():
    service = RagService(
        embeddings=FakeEmbedding(),
        db=FakeDb([]),
        chat=WhitespaceChat(),
        system_prompt="系统提示",
        top_k=5,
        min_score=0.35,
    )
    assert service.answer("Why is the item missing?") == "模型服务暂时没有返回有效内容，请稍后重试或转人工处理。"
