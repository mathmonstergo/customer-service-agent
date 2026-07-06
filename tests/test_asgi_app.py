from types import SimpleNamespace

from fastapi.testclient import TestClient

from cyclops.asgi_app import create_app


class FakeAdminApp:
    """ASGI route adapter 测试用服务；关键约束是只验证 HTTP 适配层，不碰真实数据库。"""

    settings = SimpleNamespace(admin_max_json_bytes=1024, admin_max_request_bytes=1024)

    def settings_snapshot(self):
        return {"app_name": "Cyclops", "chat_model": "deepseek-chat"}

    def update_settings(self, payload):
        return {"saved": payload}

    def list_faqs(self, params):
        assert params.get("status") == ["usable"]
        return {"items": [], "total": 0}

    def create_import_file(self, filename, content, *, auto_parse):
        assert filename == "manual.pdf"
        assert content == b"file-content"
        assert auto_parse is False
        return {"id": "file_1", "original_name": filename}

    def iter_assistant_chat_events(self, payload):
        assert payload["question"] == "怎么生成报告？"
        yield {"type": "meta", "flow_id": "basic_rag"}
        yield {
            "type": "done",
            "flow_id": "basic_rag",
            "question": payload["question"],
            "answer_draft": "请先检查报告任务状态。",
            "documents": [],
        }


def test_asgi_app_serves_settings_and_faq_routes():
    """FastAPI app 应复用现有 /api 路径，避免前端迁移时改请求地址。"""
    client = TestClient(create_app(admin_app=FakeAdminApp()))

    assert client.get("/api/settings").json()["app_name"] == "Cyclops"
    assert client.get("/api/faqs?status=usable").json() == {"items": [], "total": 0}


def test_asgi_app_exposes_migrated_admin_route_surface():
    """ASGI app 必须覆盖旧 make_handler 的管理端 API 路由面。"""
    app = create_app(admin_app=FakeAdminApp())
    route_pairs = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    expected_pairs = {
        ("GET", "/api/settings"),
        ("POST", "/api/settings"),
        ("GET", "/api/retrieval/eval-cases"),
        ("POST", "/api/retrieval/eval-cases"),
        ("POST", "/api/retrieval/eval-cases/{case_id}/run"),
        ("GET", "/api/retrieval/aliases"),
        ("POST", "/api/retrieval/aliases"),
        ("GET", "/api/kg/entities"),
        ("GET", "/api/kg/relations"),
        ("GET", "/api/kg/subgraph"),
        ("POST", "/api/kg/extraction-jobs"),
        ("POST", "/api/kg/entities/{entity_id}/confirm"),
        ("POST", "/api/kg/entities/{entity_id}/status"),
        ("POST", "/api/kg/relations/{relation_id}/confirm"),
        ("POST", "/api/kg/relations/{relation_id}/status"),
        ("GET", "/api/import/files"),
        ("POST", "/api/import/files"),
        ("DELETE", "/api/import/files/{file_id}"),
        ("GET", "/api/import/files/{file_id}/download"),
        ("GET", "/api/import/files/{file_id}/assets/{asset_relpath:path}"),
        ("GET", "/api/import/files/{file_id}/chunks"),
        ("GET", "/api/import/files/{file_id}/parse-status"),
        ("GET", "/api/import/files/{file_id}/candidates"),
        ("POST", "/api/import/files/{file_id}/reparse"),
        ("POST", "/api/import/files/{file_id}/parse-jobs"),
        ("POST", "/api/import/files/{file_id}/disabled"),
        ("POST", "/api/import/files/{file_id}/generate-questions"),
        ("POST", "/api/import/files/{file_id}/embed"),
        ("GET", "/api/import/chunks/{chunk_id}/candidates"),
        ("POST", "/api/import/chunks/{chunk_id}/generate"),
        ("POST", "/api/import/chunks/{chunk_id}/disabled"),
        ("POST", "/api/import/chunks/{chunk_id}/embed"),
        ("POST", "/api/import/chunks/{chunk_id}"),
        ("POST", "/api/import/generation-jobs"),
        ("GET", "/api/import/generation-jobs/{job_id}/events"),
        ("POST", "/api/import/candidates/{candidate_id}/save"),
        ("POST", "/api/import/candidates/{candidate_id}/ignore"),
        ("POST", "/api/import/candidates/{candidate_id}"),
        ("GET", "/api/faqs"),
        ("POST", "/api/faqs"),
        ("POST", "/api/faqs/batch-status"),
        ("POST", "/api/faqs/embed-pending"),
        ("GET", "/api/faqs/{faq_id}"),
        ("POST", "/api/faqs/{faq_id}/embed"),
        ("POST", "/api/ai/optimize"),
        ("POST", "/api/assistant/chat-stream"),
        ("POST", "/api/assistant/probe"),
        ("POST", "/api/assistant/models"),
        ("GET", "/api/analytics/overview"),
        ("GET", "/api/analytics/top-queries"),
        ("GET", "/api/analytics/zero-hit"),
        ("GET", "/api/analytics/low-score"),
        ("GET", "/api/analytics/top-chunks"),
        ("GET", "/api/analytics/hit-rate"),
        ("GET", "/api/analytics/cluster-summaries"),
        ("POST", "/api/analytics/cluster-zero-hit"),
    }

    assert expected_pairs <= route_pairs


def test_asgi_app_accepts_import_upload_with_parse_flag():
    """上传路由应使用 FastAPI UploadFile，同时保留 parse=false 语义。"""
    client = TestClient(create_app(admin_app=FakeAdminApp()))

    response = client.post(
        "/api/import/files?parse=false",
        files={"file": ("manual.pdf", b"file-content", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {"id": "file_1", "original_name": "manual.pdf"}


def test_asgi_app_serves_static_root():
    """根路径应返回 Vite 构建入口，保持管理后台无需 admin.html。"""
    client = TestClient(create_app(admin_app=FakeAdminApp()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Cyclops" in response.text
    assert "/static/dist/assets/" in response.text


def test_asgi_app_serves_download_and_import_assets(tmp_path):
    """下载和资产路由应保留文件响应语义与中文文件名编码。"""
    stored = tmp_path / "stored.bin"
    stored.write_bytes(b"download-body")
    asset = tmp_path / "asset.txt"
    asset.write_text("asset-body", encoding="utf-8")

    class FileAdminApp(FakeAdminApp):
        def get_import_file_for_download(self, file_id):
            assert file_id == "file_1"
            return {"original_name": "资料.pdf"}, stored

        def get_import_asset(self, file_id, asset_relpath):
            assert file_id == "file_1"
            assert asset_relpath == "images/a.txt"
            return {"id": file_id}, asset

    client = TestClient(create_app(admin_app=FileAdminApp()))

    download = client.get("/api/import/files/file_1/download")
    asset_response = client.get("/api/import/files/file_1/assets/images/a.txt")

    assert download.status_code == 200
    assert download.content == b"download-body"
    assert "filename*=UTF-8''%E8%B5%84%E6%96%99.pdf" in download.headers["content-disposition"]
    assert asset_response.status_code == 200
    assert asset_response.text == "asset-body"


def test_asgi_app_streams_assistant_events_as_sse():
    """Assistant route 必须保持现有 SSE event/data 格式，前端无需改解析器。"""
    client = TestClient(create_app(admin_app=FakeAdminApp()))

    response = client.post("/api/assistant/chat-stream", json={"question": "怎么生成报告？"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: meta" in response.text
    assert "event: done" in response.text
    assert '"answer_draft": "请先检查报告任务状态。"' in response.text


def test_asgi_app_rejects_invalid_json_as_validation_error():
    """JSON 解析失败应返回 400，避免非法请求被脱敏成泛化 500。"""
    client = TestClient(create_app(admin_app=FakeAdminApp()))

    response = client.post(
        "/api/settings",
        content=b"{",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "request body must be valid JSON"}


def test_asgi_app_lifespan_closes_database_pool():
    """ASGI lifespan 退出时应关闭已初始化的数据库资源。"""
    calls = []

    class FakeDatabase:
        def close(self):
            calls.append("close")

    fake_app = FakeAdminApp()
    fake_app.db = FakeDatabase()

    with TestClient(create_app(admin_app=fake_app)):
        pass

    assert calls == ["close"]
