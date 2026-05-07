from customer_service_agent.db import build_import_candidate_faq_row, format_vector, score_to_distance


def test_format_vector_outputs_pgvector_literal():
    assert format_vector([0.1, -0.2, 3]) == "[0.1,-0.2,3.0]"


def test_score_to_distance_converts_similarity_threshold():
    assert score_to_distance(0.35) == 0.65


def test_build_import_candidate_faq_row_defaults_to_needs_review():
    candidate = {
        "id": "cand_1",
        "question": "报告没生成怎么办？",
        "answer": "建议隔 10 分钟刷新查看进度。",
        "similar_questions": ["团体报告下载不了怎么办？"],
        "category": "报告服务",
        "tags": ["报告", "生成中"],
        "confidence": "medium",
        "source_excerpt": "客服 09:16: 隔10分钟刷新一次页面查看进度",
        "file_name": "chat.md",
        "chunk_id": "chunk_1",
    }

    row = build_import_candidate_faq_row(candidate)

    assert row["id"].startswith("faq_cand_1")
    assert row["status"] == "needs_review"
    assert row["question_variants"] == ["团体报告下载不了怎么办？"]
    assert row["evidence"] == [
        {
            "source_file": "chat.md",
            "chunk_id": "chunk_1",
            "excerpt": "客服 09:16: 隔10分钟刷新一次页面查看进度",
        }
    ]
