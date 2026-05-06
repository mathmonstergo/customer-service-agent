import pytest

from customer_service_agent.ai_assist import AiAssistant, AiSuggestion, AiSuggestionError


class FakeChat:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.response


def test_ai_assistant_parses_conservative_suggestion_json():
    chat = FakeChat(
        """
        {
          "optimized_question": "商品支持退货吗？",
          "optimized_answer": "未发货订单可直接申请退款。",
          "similar_questions": ["退货条件是什么？", "多久内可以申请退货？"]
        }
        """
    )

    suggestion = AiAssistant(chat).optimize("商品能退吗", "可以退")

    assert suggestion == AiSuggestion(
        optimized_question="商品支持退货吗？",
        optimized_answer="未发货订单可直接申请退款。",
        similar_questions=["退货条件是什么？", "多久内可以申请退货？"],
    )
    system_prompt, user_prompt = chat.calls[0]
    assert "不新增业务事实" in system_prompt
    assert "商品能退吗" in user_prompt
    assert "可以退" in user_prompt


def test_ai_assistant_rejects_malformed_json():
    with pytest.raises(AiSuggestionError, match="valid JSON"):
        AiAssistant(FakeChat("not json")).optimize("问题", "答案")


def test_ai_assistant_rejects_missing_required_fields():
    with pytest.raises(AiSuggestionError, match="optimized_answer"):
        AiAssistant(FakeChat('{"optimized_question":"问题"}')).optimize("问题", "答案")
