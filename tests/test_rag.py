from cyclops.db import RetrievedDocument
from cyclops.rag import RagService, build_user_prompt, normalize_conversation_context


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


def test_build_user_prompt_includes_compacted_conversation_context():
    context = normalize_conversation_context(
        {
            "summary": "此前用户一直在排查报告导出失败。",
            "recent_messages": [
                {"role": "user", "content": "刚才说的那个报告在哪里下载？"},
                {"role": "assistant", "content": "可以在报告中心下载。"},
            ],
        }
    )

    prompt = build_user_prompt("那如果没有按钮呢？", [], conversation_context=context)

    assert "### [WORKING MEMORY]" in prompt
    assert "<earlier_context>\n此前用户一直在排查报告导出失败。\n</earlier_context>" in prompt
    assert "[USER] 刚才说的那个报告在哪里下载？" in prompt
    assert "[Agent] 可以在报告中心下载。" in prompt
    assert "当前用户问题：那如果没有按钮呢？" in prompt


def test_normalize_conversation_context_discards_invalid_or_empty_items():
    context = normalize_conversation_context(
        {
            "summary": "  摘要  ",
            "recent_messages": [
                {"role": "user", "content": "  有效问题  "},
                {"role": "system", "content": "不允许的角色"},
                {"role": "assistant", "content": ""},
                "not a dict",
            ],
        }
    )

    assert context == {
        "summary": "摘要",
        "recent_messages": [{"role": "user", "content": "有效问题"}],
    }
