from customer_service_agent.import_dedupe import (
    compare_candidate_duplicate,
    dedupe_signature,
)


def test_dedupe_signature_ignores_spacing_and_punctuation():
    """精确查重签名应忽略常见空格和标点差异。"""
    assert dedupe_signature("退款多久到账？", "一般 1-3 个工作日到账。") == dedupe_signature(
        "退款多久到账",
        "一般1-3个工作日到账",
    )


def test_compare_candidate_duplicate_marks_exact_match_high():
    """候选和已有 FAQ 完全一致时标记高度重复。"""
    result = compare_candidate_duplicate(
        {"id": "cand_1", "question": "退款多久到账？", "answer": "一般 1-3 个工作日到账。"},
        [{"id": "faq_1", "question": "退款多久到账", "answer": "一般1-3个工作日到账"}],
    )

    assert result.level == "high"
    assert result.score == 1.0
    assert result.target_id == "faq_1"
    assert result.reason == "exact_text"


def test_compare_candidate_duplicate_marks_similar_question_medium():
    """文字很接近但不完全一致时标记疑似重复。"""
    result = compare_candidate_duplicate(
        {"id": "cand_1", "question": "退款需要多久？", "answer": "通常 1-3 个工作日。"},
        [{"id": "faq_1", "question": "退款多久到账？", "answer": "一般 1-3 个工作日到账。"}],
    )

    assert result.level in {"medium", "high"}
    assert result.target_id == "faq_1"


def test_compare_candidate_duplicate_returns_none_without_match():
    """没有相似问题时不标记重复。"""
    result = compare_candidate_duplicate(
        {"id": "cand_1", "question": "如何修改收货地址？", "answer": "发货前可以联系客服修改。"},
        [{"id": "faq_1", "question": "退款多久到账？", "answer": "一般 1-3 个工作日到账。"}],
    )

    assert result.level == "none"
    assert result.score == 0.0
    assert result.target_id is None
