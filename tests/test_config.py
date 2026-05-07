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
