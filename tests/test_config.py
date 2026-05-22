import pytest

from customer_service_agent.config import Settings, SettingsError


def test_settings_from_env_parses_required_values():
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
    }
    settings = Settings.from_env(env)
    assert settings.database_url == env["DATABASE_URL"]
    assert settings.chat_base_url == env["CHAT_BASE_URL"]
    assert settings.chat_api_key == env["CHAT_API_KEY"]
    assert settings.chat_model == "deepseek-chat"
    assert settings.embedding_base_url == env["EMBEDDING_BASE_URL"]
    assert settings.embedding_api_key == env["EMBEDDING_API_KEY"]
    assert settings.embedding_model == env["EMBEDDING_MODEL"]
    assert settings.embedding_dimensions == 1024
    assert settings.rag_top_k == 5
    assert settings.wechat_message_chunk_size == 1800
    assert str(settings.upload_dir) == "data/uploads"
    assert settings.mineru_batch_file_url == "https://mineru.net/api/v4/file-urls/batch"
    assert (
        settings.mineru_batch_result_url_template
        == "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    )
    assert settings.mineru_api_mode == "standard"
    assert settings.mineru_parse_timeout_seconds == 600
    assert settings.mineru_use_kb_packager is True
    assert settings.document_chunk_token_num == 512
    assert settings.document_chunk_delimiter == "\n。；！？"
    assert settings.document_chunk_overlap_percent == 0
    assert settings.document_children_delimiter == ""
    assert settings.document_table_context_size == 0
    assert settings.document_image_context_size == 0


def test_settings_from_env_parses_document_chunking_values():
    """文档 chunk 配置应覆盖 RAGFlow naive merge 和 children_delimiter 参数。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
        "DOCUMENT_CHUNK_TOKEN_NUM": "256",
        "DOCUMENT_CHUNK_DELIMITER": "`###`",
        "DOCUMENT_CHUNK_OVERLAP_PERCENT": "15",
        "DOCUMENT_CHILDREN_DELIMITER": r"\n",
        "DOCUMENT_TABLE_CONTEXT_SIZE": "128",
        "DOCUMENT_IMAGE_CONTEXT_SIZE": "96",
    }

    settings = Settings.from_env(env)

    assert settings.document_chunk_token_num == 256
    assert settings.document_chunk_delimiter == "`###`"
    assert settings.document_chunk_overlap_percent == 15
    assert settings.document_children_delimiter == r"\n"
    assert settings.document_table_context_size == 128
    assert settings.document_image_context_size == 96


def test_settings_load_applies_default_tenant_local_settings(tmp_path, monkeypatch):
    """启动配置应支持用本地租户设置文件覆盖 .env，避免设置页写回 .env。"""
    env_file = tmp_path / ".env"
    settings_file = tmp_path / "settings.local.json"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql://u:p@127.0.0.1:5432/db",
                "CHAT_BASE_URL=https://newapi.example.com/v1",
                "CHAT_API_KEY=chat-key",
                "CHAT_MODEL=deepseek-chat",
                "EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1",
                "EMBEDDING_API_KEY=embedding-key",
                "EMBEDDING_MODEL=text-embedding-v4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    settings_file.write_text(
        """
{
  "version": 1,
  "active_tenant_id": "default",
  "tenants": {
    "default": {
      "chat_api_key": "tenant-chat-key",
      "chat_model": "mimo-v2.5-pro",
      "mineru_api_token": "tenant-mineru-token",
      "mineru_api_mode": "standard"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    for key in (
        "DATABASE_URL",
        "CHAT_BASE_URL",
        "CHAT_API_KEY",
        "CHAT_MODEL",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "SETTINGS_FILE",
        "TENANT_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings.load(env_file, local_settings_file=settings_file)

    assert settings.chat_api_key == "tenant-chat-key"
    assert settings.chat_model == "mimo-v2.5-pro"
    assert settings.mineru_api_token == "tenant-mineru-token"
    assert settings.mineru_api_mode == "standard"
    assert settings.mineru_batch_file_url == "https://mineru.net/api/v4/file-urls/batch"


def test_settings_uses_standard_mineru_mode_when_token_exists():
    """配置了 MinerU Token 时默认走精准 API，便于拿到结构化 JSON。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
        "MINERU_API_TOKEN": "mineru-token",
    }

    settings = Settings.from_env(env)

    assert settings.mineru_api_mode == "standard"
    assert settings.mineru_api_token == "mineru-token"
    assert settings.mineru_batch_file_url == "https://mineru.net/api/v4/file-urls/batch"
    assert (
        settings.mineru_batch_result_url_template
        == "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    )


def test_settings_rejects_invalid_mineru_api_mode():
    """MinerU 云端接入当前固定走官方批量精准 API，不暴露模式切换。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
        "MINERU_API_MODE": "other",
    }

    with pytest.raises(SettingsError, match="MINERU_API_MODE"):
        Settings.from_env(env)


def test_settings_rejects_missing_required_value():
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        Settings.from_env({})


def test_settings_rejects_blank_required_value():
    env = {
        "DATABASE_URL": "   ",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
    }
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        Settings.from_env(env)


def test_settings_rejects_non_integer_dimensions():
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
        "EMBEDDING_DIMENSIONS": "wide",
    }
    with pytest.raises(SettingsError, match="EMBEDDING_DIMENSIONS"):
        Settings.from_env(env)


def test_settings_rejects_embedding_dimensions_that_do_not_match_schema():
    """固定 schema 当前是 vector(1024)，配置不一致时要提前失败。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
        "EMBEDDING_DIMENSIONS": "1536",
    }
    with pytest.raises(SettingsError, match="EMBEDDING_DIMENSIONS.*1024"):
        Settings.from_env(env)


def test_settings_from_env_uses_default_admin_request_limits():
    """admin 请求体限额未配置时使用默认 10 MB / 200 MB。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
    }
    settings = Settings.from_env(env)
    assert settings.admin_max_json_bytes == 10 * 1024 * 1024
    assert settings.admin_max_request_bytes == 200 * 1024 * 1024


def test_settings_from_env_parses_admin_request_limits_from_env():
    """ADMIN_MAX_JSON_BYTES / ADMIN_MAX_REQUEST_BYTES 可覆盖默认限额。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
        "ADMIN_MAX_JSON_BYTES": str(5 * 1024 * 1024),
        "ADMIN_MAX_REQUEST_BYTES": str(50 * 1024 * 1024),
    }
    settings = Settings.from_env(env)
    assert settings.admin_max_json_bytes == 5 * 1024 * 1024
    assert settings.admin_max_request_bytes == 50 * 1024 * 1024


def test_settings_from_env_uses_default_rerank_values():
    """未配置 Rerank API 时，所有字段都返回空值且 input_size 默认 50。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
    }
    settings = Settings.from_env(env)
    assert settings.rerank_base_url == ""
    assert settings.rerank_api_key == ""
    assert settings.rerank_model == ""
    assert settings.rerank_input_size == 50


def test_settings_from_env_parses_rerank_values_from_env():
    """RERANK_BASE_URL / RERANK_API_KEY / RERANK_MODEL / RERANK_INPUT_SIZE 可覆盖默认。"""
    env = {
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/db",
        "CHAT_BASE_URL": "https://newapi.example.com/v1",
        "CHAT_API_KEY": "chat-key",
        "CHAT_MODEL": "deepseek-chat",
        "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_API_KEY": "embedding-key",
        "EMBEDDING_MODEL": "text-embedding-v4",
        "RERANK_BASE_URL": "https://rerank.example.com",
        "RERANK_API_KEY": "rerank-key",
        "RERANK_MODEL": "bge-reranker-v2-m3",
        "RERANK_INPUT_SIZE": "30",
    }
    settings = Settings.from_env(env)
    assert settings.rerank_base_url == "https://rerank.example.com"
    assert settings.rerank_api_key == "rerank-key"
    assert settings.rerank_model == "bge-reranker-v2-m3"
    assert settings.rerank_input_size == 30
