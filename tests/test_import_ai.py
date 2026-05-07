import pytest

from customer_service_agent.import_ai import (
    ImportAiAssistant,
    ImportCandidate,
    ImportCandidateError,
)


class FakeChat:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.response


def test_import_ai_parses_candidate_faqs():
    """AI 候选问答解析为结构化结果，并保留内部备注。"""
    chat = FakeChat(
        """
        {
          "candidates": [
            {
              "question": "报告没生成怎么办？",
              "answer": "可提示报告服务正在生成，教育局数据量大时建议隔 10 分钟刷新查看进度。",
              "similar_questions": ["团体报告下载不了怎么办？"],
              "category": "报告服务",
              "tags": ["报告", "生成中"],
              "confidence": "medium",
              "internal_note": "不要承诺具体完成时间。"
            }
          ]
        }
        """
    )

    result = ImportAiAssistant(chat).generate_candidates("来源片段")

    assert result == [
        ImportCandidate(
            question="报告没生成怎么办？",
            answer="可提示报告服务正在生成，教育局数据量大时建议隔 10 分钟刷新查看进度。",
            similar_questions=["团体报告下载不了怎么办？"],
            category="报告服务",
            tags=["报告", "生成中"],
            confidence="medium",
            internal_note="不要承诺具体完成时间。",
        )
    ]
    system_prompt, user_prompt = chat.calls[0]
    assert "不输出一次性密码" in system_prompt
    assert "来源片段" in user_prompt


def test_import_ai_rejects_malformed_json():
    """模型输出不是合法 JSON 时向上报告候选生成错误。"""
    with pytest.raises(ImportCandidateError, match="valid JSON"):
        ImportAiAssistant(FakeChat("not json")).generate_candidates("来源片段")
