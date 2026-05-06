import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Mapping

from dotenv import load_dotenv


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    embedding_schema_dimensions: ClassVar[int] = 1024

    database_url: str
    chat_base_url: str
    chat_api_key: str
    chat_model: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    embedding_dimensions: int = 1024
    wechat_token_file: Path = Path("/home/adam/.wxbot/token.json")
    wechat_message_chunk_size: int = 1800
    rag_top_k: int = 5
    rag_min_score: float = 0.35

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "Settings":
        load_dotenv(env_file)
        return cls.from_env(os.environ)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        required_fields = {
            "DATABASE_URL": "database_url",
            "CHAT_BASE_URL": "chat_base_url",
            "CHAT_API_KEY": "chat_api_key",
            "CHAT_MODEL": "chat_model",
            "EMBEDDING_BASE_URL": "embedding_base_url",
            "EMBEDDING_API_KEY": "embedding_api_key",
            "EMBEDDING_MODEL": "embedding_model",
        }

        values: dict[str, object] = {}
        for env_name, field_name in required_fields.items():
            value = env.get(env_name, "").strip()
            if not value:
                raise SettingsError(f"Missing required environment variable: {env_name}")
            values[field_name] = value

        values["embedding_dimensions"] = cls._integer_env(env, "EMBEDDING_DIMENSIONS", 1024)
        # 当前数据库 schema 固定为 vector(1024)，这里提前拦截不匹配配置。
        if values["embedding_dimensions"] != cls.embedding_schema_dimensions:
            raise SettingsError(
                "EMBEDDING_DIMENSIONS must match database schema vector(1024)"
            )
        values["wechat_token_file"] = Path(
            env.get("WECHAT_TOKEN_FILE", "/home/adam/.wxbot/token.json")
        )
        values["wechat_message_chunk_size"] = cls._integer_env(
            env, "WECHAT_MESSAGE_CHUNK_SIZE", 1800
        )
        values["rag_top_k"] = cls._integer_env(env, "RAG_TOP_K", 5)
        values["rag_min_score"] = cls._float_env(env, "RAG_MIN_SCORE", 0.35)

        return cls(**values)

    @staticmethod
    def _integer_env(env: Mapping[str, str], name: str, default: int) -> int:
        value = env.get(name)
        if value is None or value == "":
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise SettingsError(f"{name} must be an integer") from exc

    @staticmethod
    def _float_env(env: Mapping[str, str], name: str, default: float) -> float:
        value = env.get(name)
        if value is None or value == "":
            return default
        try:
            return float(value)
        except ValueError as exc:
            raise SettingsError(f"{name} must be a float") from exc
