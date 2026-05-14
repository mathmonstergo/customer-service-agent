import json
from types import SimpleNamespace

import pytest

from customer_service_agent.admin_server import (
    AdminApp,
    AdminValidationError,
    format_sse_event,
    parse_sse_event,
    normalize_faq_payload,
    static_path,
)
from customer_service_agent.config import Settings


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


def test_admin_app_create_retrieval_eval_case_stores_expected_hits():
    """检索评测用例接口应保存问题、意图和期望命中口径。"""
    calls = []

    class FakeDatabase:
        def create_retrieval_eval_case(self, row):
            calls.append(row)
            return row

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    result = app.create_retrieval_eval_case(
        {
            "question": "报告没有生成怎么办？",
            "intent": "troubleshooting",
            "expected_source_ids": ["faq_1"],
            "expected_chunk_ids": ["kc_faq_1"],
            "tags": "报告,失败",
            "note": "真实客服高频问题",
        }
    )

    assert result["id"].startswith("eval_")
    assert calls[0]["question"] == "报告没有生成怎么办？"
    assert calls[0]["intent"] == "troubleshooting"
    assert calls[0]["expected_source_ids"] == ["faq_1"]
    assert calls[0]["expected_chunk_ids"] == ["kc_faq_1"]
    assert calls[0]["tags"] == ["报告", "失败"]
    assert calls[0]["status"] == "active"


def test_admin_app_create_retrieval_eval_case_requires_question():
    """检索评测用例必须有问题，避免沉淀不可执行样本。"""
    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"))

    with pytest.raises(AdminValidationError, match="question"):
        app.create_retrieval_eval_case({"question": ""})


def test_admin_app_list_retrieval_eval_cases_passes_filters():
    """检索评测列表接口应把分页和状态筛选交给数据库。"""
    calls = []

    class FakeDatabase:
        def list_retrieval_eval_cases(self, *, status, limit, offset):
            calls.append((status, limit, offset))
            return {"items": [], "total": 0}

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    assert app.list_retrieval_eval_cases({"status": ["active"], "limit": ["20"], "offset": ["5"]}) == {
        "items": [],
        "total": 0,
    }
    assert calls == [("active", 20, 5)]


def test_admin_app_run_retrieval_eval_case_records_hybrid_result():
    """运行单条检索评测时应保存意图、候选、指标和命中结果。"""
    calls = []

    class FakeEmbedding:
        def embed(self, text):
            calls.append(("embed", text))
            return [0.1, 0.2, 0.3]

    class FakeChat:
        def complete(self, system_prompt, user_prompt):
            return '{"intent":"faq_exact","confidence":"medium","query_rewrite":"报告导出失败","preferred_sources":["faq","document"]}'

    class FakeDatabase:
        def get_retrieval_eval_case(self, case_id):
            assert case_id == "eval_1"
            return {
                "id": "eval_1",
                "question": "报告导出失败怎么办？",
                "expected_chunk_ids": ["kc_faq_1"],
                "expected_source_ids": [],
            }

        def list_retrieval_aliases(self, status="active"):
            return [{"canonical": "报告", "aliases": ["团体报告"]}]

        def search_knowledge(self, query_embedding, *, top_k, min_score):
            assert query_embedding == [0.1, 0.2, 0.3]
            assert top_k == 6
            assert min_score == 0.4
            return [
                SimpleNamespace(
                    id="kc_noise",
                    source_id="faq_noise",
                    source_type="faq",
                    score=0.91,
                )
            ]

        def search_knowledge_text(self, query_text, *, top_k, query_terms):
            assert query_text == "报告导出失败怎么办？"
            assert top_k == 6
            assert "报告" in query_terms
            assert "导出" in query_terms
            return [
                SimpleNamespace(
                    id="kc_faq_1",
                    source_id="faq_1",
                    source_type="faq",
                    score=0.8,
                )
            ]

        def record_retrieval_eval_run(self, row):
            calls.append(("run", row))
            return {**row, "id": "eval_run_1"}

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", rag_top_k=3, rag_min_score=0.4),
        db=FakeDatabase(),
        embeddings=FakeEmbedding(),
        chat=FakeChat(),
    )

    result = app.run_retrieval_eval_case("eval_1")

    assert result["id"] == "eval_run_1"
    assert result["metrics"]["recall_at_k"] == 1.0
    assert "kc_faq_1" in [item["id"] for item in result["retrieved_items"]]
    assert result["analysis"]["intent"] == "troubleshooting"
    assert calls[0] == ("embed", "报告导出失败怎么办？")
    assert calls[-1][0] == "run"


def test_admin_app_settings_snapshot_exposes_runtime_config_for_local_modal(tmp_path):
    """设置中心读取当前运行配置，密钥只经本地管理接口返回给弹窗。"""
    app = AdminApp(
        SimpleNamespace(
            database_url="postgresql://user:pass@127.0.0.1:5432/app",
            chat_base_url="https://chat.example/v1",
            chat_api_key="chat-secret",
            chat_model="deepseek-chat",
            embedding_base_url="https://embed.example/v1",
            embedding_api_key="embedding-secret",
            embedding_model="text-embedding-v4",
            embedding_dimensions=1024,
            wechat_token_file=tmp_path / "token.json",
            wechat_message_chunk_size=1800,
            rag_top_k=6,
            rag_min_score=0.42,
            upload_dir=tmp_path / "uploads",
            mineru_api_token="mineru-secret",
            mineru_parse_timeout_seconds=600,
            mineru_use_kb_packager=True,
        )
    )

    snapshot = app.settings_snapshot()

    assert snapshot["mineru_api_token"] == "mineru-secret"
    assert snapshot["chat_api_key"] == "chat-secret"
    assert snapshot["embedding_api_key"] == "embedding-secret"
    assert snapshot["database_url"] == "postgresql://user:pass@127.0.0.1:5432/app"
    assert "mineru_batch_file_url" not in snapshot
    assert snapshot["rag_top_k"] == 6
    assert snapshot["wechat_token_file"].endswith("token.json")


def test_admin_app_update_settings_persists_local_tenant_settings_and_refreshes_runtime_config(tmp_path):
    """保存设置应写入本地租户配置文件，不修改 .env，并立即刷新运行时配置。"""
    settings_file = tmp_path / "settings.local.json"
    env_file = tmp_path / ".env"
    settings = Settings.from_env(
        {
            "DATABASE_URL": "postgresql://old@127.0.0.1:5432/app",
            "CHAT_BASE_URL": "https://old-chat.example/v1",
            "CHAT_API_KEY": "old-chat-key",
            "CHAT_MODEL": "old-model",
            "EMBEDDING_BASE_URL": "https://old-embedding.example/v1",
            "EMBEDDING_API_KEY": "old-embedding-key",
            "EMBEDDING_MODEL": "text-embedding-v4",
        }
    )
    app = AdminApp(settings, settings_file=settings_file)

    snapshot = app.update_settings(
        {
            "database_url": "postgresql://new@127.0.0.1:5432/app",
            "chat_base_url": "https://new-chat.example/v1",
            "chat_api_key": "new-chat-key",
            "chat_model": "mimo-v2.5-pro",
            "embedding_base_url": "https://new-embedding.example/v1",
            "embedding_api_key": "new-embedding-key",
            "embedding_model": "text-embedding-v4",
            "embedding_dimensions": "1024",
            "wechat_token_file": str(tmp_path / "token.json"),
            "wechat_message_chunk_size": "1800",
            "rag_top_k": "7",
            "rag_min_score": "0.4",
            "upload_dir": str(tmp_path / "uploads"),
            "mineru_api_token": "new-mineru-token",
            "mineru_parse_timeout_seconds": "600",
            "mineru_use_kb_packager": False,
        }
    )

    saved_settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert snapshot["chat_model"] == "mimo-v2.5-pro"
    assert "mineru_batch_file_url" not in snapshot
    assert "mineru_batch_result_url_template" not in snapshot
    assert "mineru_api_url" not in snapshot
    assert app.settings.chat_api_key == "new-chat-key"
    assert not env_file.exists()
    assert saved_settings["version"] == 1
    assert saved_settings["active_tenant_id"] == "default"
    assert saved_settings["tenants"]["default"]["chat_model"] == "mimo-v2.5-pro"
    assert "mineru_batch_file_url" not in saved_settings["tenants"]["default"]
    assert "mineru_batch_result_url_template" not in saved_settings["tenants"]["default"]
    assert saved_settings["tenants"]["default"]["mineru_use_kb_packager"] is False
    assert (settings_file.stat().st_mode & 0o777) == 0o600


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


def test_admin_app_create_import_file_can_store_without_parsing(tmp_path):
    """文档管理页上传文件只保存原件，用户点击解析后才生成切块。"""
    calls = []

    class FakeDatabase:
        def create_import_file(self, row):
            calls.append(("file", row))
            return {**row, "created_at": "now", "updated_at": "now"}

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", upload_dir=tmp_path),
        db=FakeDatabase(),
    )

    result = app.create_import_file("manual.pdf", b"%PDF-1.7", auto_parse=False)

    assert result["file_type"] == "pdf"
    assert result["parser"] == "mineru"
    assert result["status"] == "pending"
    assert calls == [
        (
            "file",
            {
                "id": result["id"],
                "original_name": "manual.pdf",
                "stored_path": str(tmp_path / f"{result['id']}_manual.pdf"),
                "file_type": "pdf",
                "parser": "mineru",
                "status": "pending",
            },
        )
    ]


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


def test_admin_app_create_import_file_parses_pdf_with_mineru(tmp_path, monkeypatch):
    """上传 PDF 时调用 MinerU 解析并生成审核切块。"""
    calls = []

    class FakeDatabase:
        def create_import_file(self, row):
            calls.append(("file", row))
            return row

        def replace_import_chunks(self, file_id, chunks):
            calls.append(("chunks", file_id, chunks))
            return chunks

        def update_import_file_summary(self, file_id, **fields):
            calls.append(("summary", file_id, fields))
            return {"id": file_id, **fields}

    class FakeMineruClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["api_token"] == "mineru-token"
            assert kwargs["batch_file_url"] == "https://mineru.net/api/v4/file-urls/batch"
            assert (
                kwargs["batch_result_url_template"]
                == "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
            )

        def parse_file(self, path):
            assert path.exists()
            return [
                {
                    "text": "账号登录",
                    "block_type": "title",
                    "page_number": 1,
                    "section_title": "账号登录",
                    "evidence": {
                        "source_file": "manual.pdf",
                        "page_number": 1,
                        "block_type": "title",
                    },
                }
            ]

    monkeypatch.setattr("customer_service_agent.admin_server.MineruClient", FakeMineruClient)

    app = AdminApp(
        SimpleNamespace(
            database_url="postgresql://unused",
            upload_dir=tmp_path,
            mineru_api_token="mineru-token",
            mineru_parse_timeout_seconds=30,
            mineru_use_kb_packager=True,
        ),
        db=FakeDatabase(),
    )

    result = app.create_import_file("manual.pdf", b"%PDF")

    assert result["file_type"] == "pdf"
    assert result["parser"] == "mineru"
    assert result["status"] == "needs_review"
    assert calls[1][0] == "chunks"
    assert "账号登录" in calls[1][2][0]["source_text"]


def test_admin_app_starts_mineru_parse_job_without_blocking_for_result(tmp_path, monkeypatch):
    """文档管理触发 MinerU 解析时只提交任务并保存批次号，长任务交给状态轮询。"""
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF")
    calls = []

    class FakeDatabase:
        def get_import_file(self, file_id):
            assert file_id == "imp_1"
            return {
                "id": "imp_1",
                "original_name": "manual.pdf",
                "stored_path": str(source),
                "file_type": "pdf",
                "parser": "mineru",
                "status": "pending",
            }

        def update_import_file_summary(self, file_id, **fields):
            calls.append(("summary", file_id, fields))
            return {
                "id": file_id,
                "original_name": "manual.pdf",
                "stored_path": str(source),
                "file_type": "pdf",
                "parser": "mineru",
                **fields,
            }

    class FakeMineruClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["api_token"] == "mineru-token"

        def start_file(self, path):
            assert path == source
            return SimpleNamespace(
                batch_id="batch_1",
                file_name="manual.pdf",
                state="waiting-file",
                progress={},
                error=None,
                result={},
                zip_url=None,
            )

    monkeypatch.setattr("customer_service_agent.admin_server.MineruClient", FakeMineruClient)

    app = AdminApp(
        SimpleNamespace(
            database_url="postgresql://unused",
            upload_dir=tmp_path,
            mineru_api_token="mineru-token",
            mineru_parse_timeout_seconds=30,
            mineru_use_kb_packager=True,
        ),
        db=FakeDatabase(),
    )

    result = app.start_import_parse_job("imp_1", {})

    assert result["state"] == "waiting-file"
    assert result["percent"] == 0
    assert calls == [
        (
            "summary",
            "imp_1",
            {
                "status": "processing",
                "parse_batch_id": "batch_1",
                "parse_file_name": "manual.pdf",
                "parse_progress": {"state": "waiting-file"},
                "error": None,
            },
        )
    ]


def test_admin_app_polling_mineru_parse_status_updates_progress(tmp_path, monkeypatch):
    """解析中状态需要回写页面可读进度，避免用户只能看到阻塞后的结果。"""
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF")
    calls = []

    class FakeDatabase:
        def get_import_file(self, file_id):
            assert file_id == "imp_1"
            return {
                "id": "imp_1",
                "original_name": "manual.pdf",
                "stored_path": str(source),
                "file_type": "pdf",
                "parser": "mineru",
                "status": "processing",
                "parse_batch_id": "batch_1",
                "parse_file_name": "manual.pdf",
                "parse_progress": {"state": "waiting-file"},
            }

        def update_import_file_summary(self, file_id, **fields):
            calls.append(("summary", file_id, fields))
            return {
                "id": file_id,
                "original_name": "manual.pdf",
                "stored_path": str(source),
                "file_type": "pdf",
                "parser": "mineru",
                "status": fields.get("status", "processing"),
                "parse_batch_id": "batch_1",
                "parse_file_name": "manual.pdf",
                **fields,
            }

    class FakeMineruClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_task_status(self, batch_id, file_name):
            assert (batch_id, file_name) == ("batch_1", "manual.pdf")
            return SimpleNamespace(
                batch_id=batch_id,
                file_name=file_name,
                state="running",
                progress={"extracted_pages": 3, "total_pages": 12},
                error=None,
                result={},
                zip_url=None,
            )

    monkeypatch.setattr("customer_service_agent.admin_server.MineruClient", FakeMineruClient)

    app = AdminApp(
        SimpleNamespace(
            database_url="postgresql://unused",
            upload_dir=tmp_path,
            mineru_api_token="mineru-token",
            mineru_parse_timeout_seconds=30,
            mineru_use_kb_packager=True,
        ),
        db=FakeDatabase(),
    )

    result = app.get_import_parse_status("imp_1")

    assert result["state"] == "running"
    assert result["percent"] == 25
    assert result["progress"] == {"extracted_pages": 3, "total_pages": 12, "state": "running"}
    assert calls == [
        (
            "summary",
            "imp_1",
            {
                "status": "processing",
                "parse_progress": {"extracted_pages": 3, "total_pages": 12, "state": "running"},
                "error": None,
            },
        )
    ]


def test_admin_app_polling_mineru_done_downloads_result_and_replaces_chunks(tmp_path, monkeypatch):
    """MinerU 状态到 done 后才下载结果并替换文档切片。"""
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF")
    calls = []

    class FakeDatabase:
        def get_import_file(self, file_id):
            assert file_id == "imp_1"
            return {
                "id": "imp_1",
                "original_name": "manual.pdf",
                "stored_path": str(source),
                "file_type": "pdf",
                "parser": "mineru",
                "status": "processing",
                "parse_batch_id": "batch_1",
                "parse_file_name": "manual.pdf",
                "parse_progress": {"state": "running"},
            }

        def replace_import_chunks(self, file_id, chunks):
            calls.append(("chunks", file_id, chunks))
            return chunks

        def update_import_file_summary(self, file_id, **fields):
            calls.append(("summary", file_id, fields))
            return {
                "id": file_id,
                "original_name": "manual.pdf",
                "stored_path": str(source),
                "file_type": "pdf",
                "parser": "mineru",
                **fields,
            }

    class FakeMineruClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_task_status(self, batch_id, file_name):
            assert (batch_id, file_name) == ("batch_1", "manual.pdf")
            return SimpleNamespace(
                batch_id=batch_id,
                file_name=file_name,
                state="done",
                progress={"extracted_pages": 12, "total_pages": 12},
                error=None,
                result={"file_name": "manual.pdf"},
                zip_url="https://cdn.example/result.zip",
            )

        def download_task_result(self, status):
            assert status.zip_url == "https://cdn.example/result.zip"
            return {
                "content_list": [
                    {"type": "title", "text": "账号登录", "page_idx": 0},
                    {"type": "text", "text": "先检查账号状态。", "page_idx": 0},
                ]
            }

    monkeypatch.setattr("customer_service_agent.admin_server.MineruClient", FakeMineruClient)

    app = AdminApp(
        SimpleNamespace(
            database_url="postgresql://unused",
            upload_dir=tmp_path,
            mineru_api_token="mineru-token",
            mineru_parse_timeout_seconds=30,
            mineru_use_kb_packager=True,
        ),
        db=FakeDatabase(),
    )

    result = app.get_import_parse_status("imp_1")

    assert result["state"] == "done"
    assert result["percent"] == 100
    assert calls[0][0] == "chunks"
    assert "先检查账号状态。" in calls[0][2][0]["source_text"]
    assert calls[1] == (
        "summary",
        "imp_1",
        {
            "status": "needs_review",
            "message_count": 0,
            "chunk_count": 1,
            "candidate_count": 0,
            "parse_progress": {"extracted_pages": 12, "total_pages": 12, "state": "done"},
            "error": None,
        },
    )


def test_admin_app_delete_import_file_removes_record_and_local_upload(tmp_path):
    """文档管理删除文件时需要同时删除导入记录和本地原件。"""
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF")
    calls = []

    class FakeDatabase:
        def delete_import_file(self, file_id):
            calls.append(("delete", file_id))
            return {"id": file_id, "stored_path": str(source), "original_name": "manual.pdf"}

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", upload_dir=tmp_path),
        db=FakeDatabase(),
    )

    result = app.delete_import_file("imp_1")

    assert result == {"deleted": True, "id": "imp_1"}
    assert calls == [("delete", "imp_1")]
    assert not source.exists()


def test_admin_app_save_import_candidate_writes_needs_review_faq_and_embeds():
    """候选 FAQ 保存到标准问答后立即生成 embedding，减少人工二次操作。"""
    calls = []
    saved_rows = {}

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
            saved = {**row, "embedding_status": "pending"}
            saved_rows[row["id"]] = saved
            return saved

        def get_faq(self, faq_id):
            calls.append(("get_faq", faq_id))
            return saved_rows[faq_id]

        def update_faq_embedding(self, faq_id, vector, *, embedding_model, embedding_dimensions):
            calls.append(("embedding", faq_id, vector, embedding_model, embedding_dimensions))
            saved = {
                **saved_rows[faq_id],
                "embedding_status": "ready",
                "embedding_model": embedding_model,
                "embedding_dimensions": embedding_dimensions,
            }
            saved_rows[faq_id] = saved
            return saved

        def upsert_knowledge_chunk(self, row, vector, *, embedding_model, embedding_dimensions):
            calls.append(("knowledge_chunk", row, vector, embedding_model, embedding_dimensions))
            return {**row, "embedding_status": "ready"}

        def get_import_file_embedding_summary(self, file_id):
            calls.append(("summary", file_id))
            return {"status": "ready", "total_chunks": 2, "ready_count": 2}

        def mark_embedding_failed(self, faq_id, error):
            calls.append(("embedding_failed", faq_id, error))
            saved = {**saved_rows[faq_id], "embedding_status": "failed", "embedding_error": error}
            saved_rows[faq_id] = saved
            return saved

        def mark_import_candidate_saved(self, candidate_id, faq_id):
            calls.append(("saved", candidate_id, faq_id))
            return {"id": candidate_id, "status": "saved", "saved_faq_id": faq_id}

    class FakeEmbedding:
        model = "fake-embedding"
        dimensions = 3

        def embed(self, text):
            calls.append(("embed", text))
            return [0.1, 0.2, 0.3]

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused"),
        db=FakeDatabase(),
        embeddings=FakeEmbedding(),
    )

    result = app.save_import_candidate("cand_1")

    assert calls[0][1]["status"] == "needs_review"
    assert calls[0][1]["embedding_text"].startswith("标准问题")
    assert ("embed", calls[0][1]["embedding_text"]) in calls
    assert ("embedding", result["saved_faq_id"], [0.1, 0.2, 0.3], "fake-embedding", 3) in calls
    knowledge_call = [call for call in calls if call[0] == "knowledge_chunk"][0]
    assert knowledge_call[1]["source_type"] == "faq"
    assert knowledge_call[1]["source_id"] == result["saved_faq_id"]
    assert knowledge_call[2] == [0.1, 0.2, 0.3]
    assert result["status"] == "saved"
    assert result["embedding_status"] == "ready"


def test_admin_app_embed_import_file_requires_parsed_document():
    """文档切片生成 embedding 只能在解析完成后触发。"""

    class FakeDatabase:
        def get_import_file(self, file_id):
            assert file_id == "imp_1"
            return {
                "id": "imp_1",
                "original_name": "manual.pdf",
                "status": "pending",
                "chunk_count": 0,
            }

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    with pytest.raises(AdminValidationError, match="parsed"):
        app.embed_import_file("imp_1")


def test_admin_app_embed_import_file_writes_document_chunks_to_knowledge_chunks():
    """解析完成的文档可以把每个切片写入统一知识单元并生成向量。"""
    calls = []

    class FakeDatabase:
        def get_import_file(self, file_id):
            calls.append(("file", file_id))
            return {
                "id": file_id,
                "original_name": "manual.pdf",
                "file_type": "pdf",
                "parser": "mineru",
                "status": "needs_review",
                "chunk_count": 2,
            }

        def list_import_chunks(self, file_id):
            calls.append(("chunks", file_id))
            return [
                {
                    "id": "chunk_1",
                    "file_id": file_id,
                    "chunk_index": 1,
                    "source_text": "第一段原文",
                    "keywords": ["登录"],
                    "status": "generated",
                    "message_count": 0,
                    "start_at": None,
                    "end_at": None,
                },
                {
                    "id": "chunk_2",
                    "file_id": file_id,
                    "chunk_index": 2,
                    "source_text": "第二段原文",
                    "keywords": ["报告"],
                    "status": "generated",
                    "message_count": 0,
                    "start_at": None,
                    "end_at": None,
                },
            ]

        def upsert_knowledge_chunk(self, row, vector, *, embedding_model, embedding_dimensions):
            calls.append(("knowledge_chunk", row, vector, embedding_model, embedding_dimensions))
            return {**row, "embedding_status": "ready"}

        def get_import_file_embedding_summary(self, file_id):
            calls.append(("summary", file_id))
            return {"status": "ready", "total_chunks": 2, "ready_count": 2}

    class FakeEmbedding:
        model = "fake-embedding"
        dimensions = 3

        def embed(self, text):
            calls.append(("embed", text))
            return [0.1, 0.2, 0.3]

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused"),
        db=FakeDatabase(),
        embeddings=FakeEmbedding(),
    )

    result = app.embed_import_file("imp_1")

    assert result["count"] == 2
    assert calls[0] == ("file", "imp_1")
    assert calls[1] == ("chunks", "imp_1")
    assert ("embed", "第一段原文") in calls
    chunk_calls = [call for call in calls if call[0] == "knowledge_chunk"]
    assert chunk_calls[0][1]["source_type"] == "document"
    assert chunk_calls[0][1]["source_id"] == "imp_1"
    assert chunk_calls[0][1]["source_chunk_id"] == "chunk_1"
    assert chunk_calls[0][1]["status"] == "usable"
    assert chunk_calls[0][2] == [0.1, 0.2, 0.3]


def test_admin_app_update_import_chunk_text_marks_embedding_stale():
    """保存切片原文后返回更新后的切片和文档向量摘要。"""
    calls = []

    class FakeDatabase:
        def update_import_chunk_text(self, chunk_id, source_text):
            calls.append(("update", chunk_id, source_text))
            return {
                "id": chunk_id,
                "file_id": "imp_1",
                "chunk_index": 1,
                "source_text": source_text,
            }

        def get_import_file_embedding_summary(self, file_id):
            calls.append(("summary", file_id))
            return {
                "status": "stale",
                "total_chunks": 2,
                "ready_count": 1,
                "stale_count": 1,
            }

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    result = app.update_import_chunk_text("chunk_1", {"source_text": "更新后的切片原文"})

    assert calls == [
        ("update", "chunk_1", "更新后的切片原文"),
        ("summary", "imp_1"),
    ]
    assert result["item"]["source_text"] == "更新后的切片原文"
    assert result["embedding_summary"]["status"] == "stale"


def test_admin_app_update_import_chunk_text_rejects_blank_text():
    """切片正文不能为空，避免保存后破坏后续 embedding 输入。"""
    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"))

    with pytest.raises(AdminValidationError, match="source_text"):
        app.update_import_chunk_text("chunk_1", {"source_text": "   "})


def test_admin_app_list_import_file_candidates_delegates_to_database():
    """候选 FAQ 视图按文件汇总候选，不要求用户先进入某个切块。"""
    calls = []

    class FakeDatabase:
        def list_import_file_candidates(self, file_id):
            calls.append(file_id)
            return [{"id": "cand_1", "file_id": file_id, "chunk_index": 3}]

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    assert app.list_import_file_candidates("imp_1") == {
        "items": [{"id": "cand_1", "file_id": "imp_1", "chunk_index": 3}]
    }
    assert calls == ["imp_1"]


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


def test_admin_app_create_import_generation_job_requires_chunk_ids():
    """创建生成任务时必须提供切块 id。"""
    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"))

    with pytest.raises(AdminValidationError, match="chunk_ids"):
        app.create_import_generation_job({"chunk_ids": []})


def test_admin_app_create_import_generation_job_delegates_to_database():
    """批量生成任务创建只把去重后的切块 id 交给数据库。"""
    calls = []

    class FakeDatabase:
        def create_import_generation_job(self, chunk_ids):
            calls.append(chunk_ids)
            return {"id": "job_1", "items": [{"chunk_id": "chunk_1", "status": "queued"}]}

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase())

    result = app.create_import_generation_job({"chunk_ids": ["chunk_1", "chunk_1", "chunk_2"]})

    assert calls == [["chunk_1", "chunk_2"]]
    assert result["id"] == "job_1"


def test_admin_app_iter_import_generation_events_streams_statuses():
    """生成任务事件流应输出处理、完成和最终 done 状态。"""
    calls = []

    class FakeChat:
        def complete(self, system_prompt, user_prompt):
            return '{"candidates":[{"question":"报告没生成怎么办？","answer":"隔10分钟刷新。"}]}'

    class FakeDatabase:
        def get_import_generation_job(self, job_id):
            assert job_id == "job_1"
            return {"id": "job_1", "status": "queued"}

        def list_import_generation_job_items(self, job_id):
            assert job_id == "job_1"
            return [
                {"id": "item_1", "chunk_id": "chunk_1", "status": "queued"},
                {"id": "item_2", "chunk_id": "chunk_2", "status": "skipped", "reason": "already_generated"},
            ]

        def update_import_generation_job_item(self, item_id, **fields):
            calls.append(("item", item_id, fields))
            return {"id": item_id, **fields}

        def update_import_generation_job_summary(self, job_id, status):
            calls.append(("job", job_id, status))
            return {"id": job_id, "status": status}

        def get_import_chunk(self, chunk_id):
            return {
                "id": chunk_id,
                "file_id": "imp_1",
                "source_text": "[2025-08-25 16:20] 用户: 报告没生成怎么办",
            }

        def list_import_dedupe_references(self, chunk_id):
            return []

        def create_import_candidates(self, chunk, rows):
            calls.append(("candidates", chunk["id"], rows))
            return rows

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase(), chat=FakeChat())

    events = list(app.iter_import_generation_events("job_1"))

    assert [event["type"] for event in events] == ["processing", "generated", "skipped", "done"]
    assert events[1]["candidate_count"] == 1
    assert events[2]["reason"] == "already_generated"
    assert calls[-1] == ("job", "job_1", "completed")


def test_admin_app_generate_import_candidates_sets_duplicate_fields():
    """候选生成后需要写入重复程度，供人工审核判断。"""
    calls = []

    class FakeChat:
        def complete(self, system_prompt, user_prompt):
            return '{"candidates":[{"question":"退款多久到账？","answer":"一般1-3个工作日到账。"}]}'

    class FakeDatabase:
        def get_import_chunk(self, chunk_id):
            return {"id": chunk_id, "file_id": "imp_1", "source_text": "退款多久到账"}

        def list_import_dedupe_references(self, chunk_id):
            return [{"id": "faq_1", "question": "退款多久到账", "answer": "一般 1-3 个工作日到账"}]

        def create_import_candidates(self, chunk, rows):
            calls.extend(rows)
            return rows

    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"), db=FakeDatabase(), chat=FakeChat())

    app.generate_import_candidates("chunk_1")

    assert calls[0]["duplicate_level"] == "high"
    assert calls[0]["duplicate_target_id"] == "faq_1"
    assert calls[0]["duplicate_reason"] == "exact_text"


def test_format_sse_event_outputs_named_json_event():
    """SSE 输出需要包含事件名和 JSON 数据。"""
    content = format_sse_event({"type": "generated", "chunk_id": "chunk_1", "candidate_count": 2})

    assert content.startswith("event: generated\n")
    assert '"chunk_id": "chunk_1"' in content
    assert content.endswith("\n\n")


def test_parse_sse_event_round_trips_named_json_event():
    """测试工具需要能解析后端 SSE 文本，避免前后端事件名不一致。"""
    content = format_sse_event({"type": "delta", "text": "回答片段"})

    parsed = parse_sse_event(content)

    assert parsed == {"event": "delta", "data": {"type": "delta", "text": "回答片段"}}


def test_admin_app_iter_assistant_chat_events_streams_hybrid_retrieval_trace():
    """智能问答应展示意图识别、混合召回和来源融合信息。"""

    class FakeEmbedding:
        def embed(self, text):
            assert text == "报告没有生成怎么办？"
            return [0.1, 0.2, 0.3]

    class FakeDatabase:
        def search_knowledge(self, query_embedding, *, top_k, min_score):
            assert query_embedding == [0.1, 0.2, 0.3]
            assert top_k == 6
            assert min_score == 0.4
            return [
                SimpleNamespace(
                    id="faq_1",
                    source_type="faq",
                    source_id="faq_1",
                    source_chunk_id=None,
                    source_title="报告没有生成怎么办？",
                    content="问题：报告没有生成怎么办？\n答案：请等待 10 分钟后刷新。",
                    metadata={"category": "报告", "source_date": "2026-05"},
                    question="报告没有生成怎么办？",
                    answer="问题：报告没有生成怎么办？\n答案：请等待 10 分钟后刷新。",
                    category="报告",
                    tags=["报告", "刷新"],
                    source_date="2026-05",
                    confidence="high",
                    status="usable",
                    score=0.88,
                )
            ]

        def search_knowledge_text(self, query_text, *, top_k, query_terms):
            assert query_text == "报告没有生成怎么办？"
            assert top_k == 6
            assert "报告" in query_terms
            return [
                SimpleNamespace(
                    id="faq_1",
                    source_type="faq",
                    source_id="faq_1",
                    source_chunk_id=None,
                    source_title="报告没有生成怎么办？",
                    content="问题：报告没有生成怎么办？\n答案：请等待 10 分钟后刷新。",
                    metadata={"category": "报告", "source_date": "2026-05"},
                    question="报告没有生成怎么办？",
                    answer="问题：报告没有生成怎么办？\n答案：请等待 10 分钟后刷新。",
                    category="报告",
                    tags=["报告", "刷新"],
                    source_date="2026-05",
                    confidence="high",
                    status="usable",
                    score=0.77,
                )
            ]

    class FakeChat:
        def __init__(self):
            self.calls = []

        def stream_complete(self, system_prompt, user_prompt):
            self.calls.append((system_prompt, user_prompt))
            yield "请等待 "
            yield "10 分钟后刷新。"

    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", rag_top_k=3, rag_min_score=0.4),
        db=FakeDatabase(),
        embeddings=FakeEmbedding(),
        chat=FakeChat(),
    )

    events = list(app.iter_assistant_chat_events({"question": "报告没有生成怎么办？"}))

    assert [event["type"] for event in events] == [
        "meta",
        "step",
        "step",
        "step",
        "step",
        "step",
        "step",
        "delta",
        "delta",
        "step",
        "done",
    ]
    assert events[0]["flow_id"] == "basic_rag"
    assert events[0]["stream"] is True
    assert "intent_detection" in events[0]["available_nodes"]
    assert "intent_detection" in events[0]["enabled_nodes"]
    assert "keyword_search" in events[0]["enabled_nodes"]
    assert events[2]["step_id"] == "intent_detection"
    assert events[2]["analysis"]["intent"] == "troubleshooting"
    assert events[4]["step_id"] == "hybrid_retrieval"
    assert events[4]["status"] == "completed"
    assert events[4]["documents"][0]["id"] == "faq_1"
    assert events[4]["documents"][0]["retrieval_channels"] == ["vector", "keyword"]
    assert events[5]["title"] == "命中来源"
    assert events[-1]["answer_draft"] == "请等待 10 分钟后刷新。"
    assert events[-1]["documents"][0]["score"] == 0.88


def test_admin_app_iter_assistant_chat_events_uses_conversation_system_prompt():
    """会话级系统提示词应覆盖默认提示词，但不改变检索链路。"""

    class FakeEmbedding:
        def embed(self, text):
            return [0.1]

    class FakeDatabase:
        def search_knowledge(self, query_embedding, *, top_k, min_score):
            return []

        def search_knowledge_text(self, query_text, *, top_k, query_terms):
            return []

    class FakeChat:
        def __init__(self):
            self.calls = []

        def stream_complete(self, system_prompt, user_prompt):
            self.calls.append((system_prompt, user_prompt))
            yield "会话提示已生效"

    chat = FakeChat()
    app = AdminApp(
        SimpleNamespace(database_url="postgresql://unused", rag_top_k=3, rag_min_score=0.4),
        db=FakeDatabase(),
        embeddings=FakeEmbedding(),
        chat=chat,
    )

    events = list(
        app.iter_assistant_chat_events(
            {
                "question": "开票需要什么资料？",
                "system_prompt": "你是财务客服助手，只回答开票相关问题。",
            }
        )
    )

    assert chat.calls[0][0] == "你是财务客服助手，只回答开票相关问题。"
    assert events[-1]["answer_draft"] == "会话提示已生效"


def test_admin_app_assistant_system_prompt_has_no_code_default(monkeypatch):
    """智能问答没有会话提示词和本地文件时，不再注入代码硬编码默认提示。"""
    app = AdminApp(SimpleNamespace(database_url="postgresql://unused"))

    def missing_system_prompt():
        raise FileNotFoundError

    monkeypatch.setattr("customer_service_agent.admin_server.load_system_prompt", missing_system_prompt)

    assert app.assistant_system_prompt() == ""
    assert app.assistant_system_prompt_from_payload({"system_prompt": ""}) == ""
