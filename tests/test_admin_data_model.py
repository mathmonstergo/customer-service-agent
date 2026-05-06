from customer_service_agent.db import (
    build_embedding_text,
    compute_content_hash,
    next_embedding_status,
)


def test_build_embedding_text_includes_question_variants_answer_and_metadata():
    row = {
        "question": "商品可以退货吗？",
        "question_variants": ["退货条件是什么？", "多久内可以退？"],
        "answer": "未发货订单可直接申请退款。",
        "category": "售后服务",
        "tags": ["退货", "退款"],
    }

    text = build_embedding_text(row)

    assert "标准问题：商品可以退货吗？" in text
    assert "相似问法：退货条件是什么？；多久内可以退？" in text
    assert "答案：未发货订单可直接申请退款。" in text
    assert "分类：售后服务" in text
    assert "标签：退货，退款" in text


def test_compute_content_hash_changes_when_answer_changes():
    original = {
        "question": "商品可以退货吗？",
        "answer": "未发货订单可直接申请退款。",
        "question_variants": ["退货条件是什么？"],
        "category": "售后服务",
        "tags": ["退货"],
        "status": "usable",
        "confidence": "high",
    }
    changed = {**original, "answer": "签收后七天内可以申请退货。"}

    assert compute_content_hash(original) != compute_content_hash(changed)


def test_next_embedding_status_keeps_ready_when_content_is_unchanged():
    content_hash = "abc123"

    assert next_embedding_status("ready", content_hash, content_hash) == "ready"


def test_next_embedding_status_marks_ready_record_stale_when_content_changes():
    assert next_embedding_status("ready", "old", "new") == "stale"


def test_next_embedding_status_marks_new_record_pending():
    assert next_embedding_status(None, None, "new") == "pending"
