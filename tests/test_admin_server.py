from types import SimpleNamespace

import pytest

from customer_service_agent.admin_server import (
    AdminApp,
    AdminValidationError,
    normalize_faq_payload,
    static_path,
)


def test_normalize_faq_payload_sets_defaults_and_splits_lists():
    row = normalize_faq_payload(
        {
            "question": " 商品可以退货吗？ ",
            "answer": " 可以退。 ",
            "category": "售后服务",
            "tags": "退货, 退款",
            "question_variants": "退货条件是什么？\n多久内可以退？",
        }
    )

    assert row["id"].startswith("faq_")
    assert row["question"] == "商品可以退货吗？"
    assert row["answer"] == "可以退。"
    assert row["status"] == "usable"
    assert row["confidence"] == "high"
    assert row["tags"] == ["退货", "退款"]
    assert row["question_variants"] == ["退货条件是什么？", "多久内可以退？"]


def test_normalize_faq_payload_rejects_missing_question():
    with pytest.raises(AdminValidationError, match="question"):
        normalize_faq_payload({"answer": "可以退。"})


def test_normalize_faq_payload_rejects_missing_answer():
    with pytest.raises(AdminValidationError, match="answer"):
        normalize_faq_payload({"question": "商品可以退货吗？"})


def test_admin_app_batch_update_status_requires_ids():
    """批量状态更新必须明确选择 FAQ，避免空选择误操作。"""
    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"))

    with pytest.raises(AdminValidationError, match="ids"):
        app.batch_update_status({"ids": [], "status": "disabled"})


def test_admin_app_batch_update_status_calls_database():
    """批量状态更新只把合法 id 和状态交给数据库层。"""
    calls = []

    class FakeDatabase:
        def update_faq_statuses(self, ids, status):
            calls.append((ids, status))
            return [{"id": ids[0], "status": status}]

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    assert app.batch_update_status({"ids": ["faq_1"], "status": "disabled"}) == {
        "count": 1,
        "items": [{"id": "faq_1", "status": "disabled"}],
    }
    assert calls == [(["faq_1"], "disabled")]


def test_admin_app_create_import_file_parses_markdown(tmp_path):
    """上传 Markdown 时保存原件并生成时间切块。"""
    calls = []

    class FakeDatabase:
        def create_import_file(self, row):
            calls.append(("file", row))
            return {**row, "created_at": "now", "updated_at": "now"}

        def replace_import_chunks(self, file_id, chunks):
            calls.append(("chunks", file_id, chunks))
            return [{**chunk, "id": f"chunk_{index}"} for index, chunk in enumerate(chunks, start=1)]

        def update_import_file_summary(self, file_id, **fields):
            calls.append(("summary", file_id, fields))
            return {"id": file_id, **fields}

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", upload_dir=tmp_path),
        db=FakeDatabase(),
    )
    markdown = b"- [2025-08-25 16:20] A: \xe6\x8a\xa5\xe5\x91\x8a\xe6\xb2\xa1\xe7\x94\x9f\xe6\x88\x90\xe6\x80\x8e\xe4\xb9\x88\xe5\x8a\x9e\n- [2025-08-25 16:21] B: \xe9\x9a\x9410\xe5\x88\x86\xe9\x92\x9f\xe5\x88\xb7\xe6\x96\xb0\n"

    result = app.create_import_file("chat.md", markdown)

    assert result["file_type"] == "markdown"
    assert result["parser"] == "markdown_chat"
    assert result["status"] == "needs_review"
    assert calls[1][0] == "chunks"
    assert calls[1][2][0]["message_count"] == 2


def test_admin_app_reparse_import_file_uses_day_range_options(tmp_path):
    """重新解析可以按用户选择的天数范围生成切块。"""
    stored = tmp_path / "chat.md"
    stored.write_text(
        "\n".join(
            [
                "- [2025-08-25 23:50] 用户: 报告下载不了",
                "- [2025-08-26 00:05] 客服: 请隔10分钟刷新",
            ]
        ),
        encoding="utf-8",
    )
    calls = []

    class FakeDatabase:
        def get_import_file(self, file_id):
            assert file_id == "imp_1"
            return {
                "id": "imp_1",
                "original_name": "chat.md",
                "stored_path": str(stored),
                "parser": "markdown_chat",
            }

        def update_import_file_summary(self, file_id, **fields):
            calls.append(("summary", file_id, fields))
            return {"id": file_id, **fields}

        def replace_import_chunks(self, file_id, chunks):
            calls.append(("chunks", file_id, chunks))
            return chunks

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", upload_dir=tmp_path),
        db=FakeDatabase(),
    )

    result = app.reparse_import_file("imp_1", {"parse_mode": "by_days", "chunk_days": 1})

    assert result["chunk_count"] == 2
    assert calls[0][0] == "chunks"


def test_admin_app_create_import_file_marks_unsupported(tmp_path):
    """非 Markdown 文件第一期只识别类型，不进入解析。"""
    calls = []

    class FakeDatabase:
        def create_import_file(self, row):
            calls.append(row)
            return row

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", upload_dir=tmp_path),
        db=FakeDatabase(),
    )

    result = app.create_import_file("manual.pdf", b"%PDF")

    assert result["file_type"] == "pdf"
    assert result["parser"] == "unsupported"
    assert result["status"] == "unsupported"


def test_admin_app_save_import_candidate_writes_needs_review_faq():
    """候选 FAQ 保存到标准问答时默认仍需审核且不生成 embedding。"""
    calls = []

    class FakeDatabase:
        def get_import_candidate(self, candidate_id):
            assert candidate_id == "cand_1"
            return {
                "id": "cand_1",
                "question": "报告没生成怎么办？",
                "answer": "建议隔 10 分钟刷新查看进度。",
                "similar_questions": ["团体报告下载不了怎么办？"],
                "category": "报告服务",
                "tags": ["报告"],
                "confidence": "medium",
                "source_excerpt": "客服: 隔10分钟刷新",
                "file_name": "chat.md",
                "chunk_id": "chunk_1",
            }

        def save_faq_text(self, row):
            calls.append(("faq", row))
            return {**row, "embedding_status": "pending"}

        def mark_import_candidate_saved(self, candidate_id, faq_id):
            calls.append(("saved", candidate_id, faq_id))
            return {"id": candidate_id, "status": "saved", "saved_faq_id": faq_id}

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    result = app.save_import_candidate("cand_1")

    assert calls[0][1]["status"] == "needs_review"
    assert calls[0][1]["embedding_text"].startswith("标准问题")
    assert result["status"] == "saved"


def test_static_path_accepts_admin_html_route():
    """用户直接访问 /admin.html 时也应返回管理页。"""
    assert static_path("/admin.html").name == "admin.html"


def test_admin_app_save_faq_keeps_existing_metadata_when_payload_omits_it():
    """前端保存未改动 FAQ 时不能因省略置信度等字段触发 embedding stale。"""
    calls = []

    class FakeDatabase:
        def get_faq(self, faq_id):
            assert faq_id == "faq_1"
            return {
                "id": "faq_1",
                "source_file": "seed.jsonl",
                "source_group": "manual",
                "source_date": None,
                "evidence": [],
                "confidence": "low",
                "sensitivity": None,
            }

        def save_faq_text(self, row):
            calls.append(row)
            return {**row, "embedding_status": "ready"}

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    app.save_faq(
        {
            "id": "faq_1",
            "question": "未完成名单下载后不准怎么办？",
            "answer": "重新下载最新名单后核对。",
            "question_variants": [],
            "category": "测评数据",
            "tags": [],
            "status": "usable",
        }
    )

    assert calls[0]["confidence"] == "low"
    assert calls[0]["source_file"] == "seed.jsonl"
