from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


class BaseDatabase:
    """Database 主类基础：连接管理 + schema 初始化 + 行字典统一化。"""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def init_schema(self, sql_path: str | Path = "sql/001_init.sql") -> None:
        sql = Path(sql_path).read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.execute(sql)

    @staticmethod
    def _row_dict(row: Any) -> dict[str, Any]:
        """psycopg dict_row 已返回 dict，这里只是统一对外类型。"""
        if isinstance(row, dict):
            return dict(row)
        return dict(row or {})
