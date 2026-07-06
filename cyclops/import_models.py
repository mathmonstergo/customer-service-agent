from __future__ import annotations

from pathlib import Path


SUPPORTED_UPLOAD_SUFFIXES = {".md", ".markdown", ".pdf", ".docx", ".xlsx", ".xls"}


def detect_file_type(filename: str) -> tuple[str, str]:
    """识别上传文件类型，并返回当前导入流程应使用的解析器名称。"""
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown", "markdown_chat"
    if suffix == ".pdf":
        return "pdf", "mineru"
    if suffix in {".xlsx", ".xls"}:
        return "excel", "mineru"
    if suffix == ".docx":
        return "word", "mineru"
    return "unknown", "unsupported"
