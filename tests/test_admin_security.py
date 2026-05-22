"""Admin 后台安全守门相关的纯函数测试。

本文件聚焦五项加固：
1. host 守门（loopback 默认通过，非 loopback 需显式 env）
2. 请求体大小守门（超限抛 AdminPayloadTooLargeError）
3. 异常分类（500 类异常脱敏，业务异常保留原文案）
4. safe_upload_name 的 `.` / `..` / 空基名兜底
5. 上传路径 resolve 后必须落在 upload_dir 内
"""
from __future__ import annotations

from http import HTTPStatus

import pytest

from customer_service_agent.admin_server import (
    AdminNotFoundError,
    AdminPayloadTooLargeError,
    AdminValidationError,
    classify_error_response,
    ensure_loopback_or_explicit_opt_in,
    ensure_request_size,
    ensure_upload_path_within,
    safe_upload_name,
)


def test_ensure_loopback_or_explicit_opt_in_allows_loopback_hosts():
    """默认 host 命中 loopback 名单时直接通过，不需要任何 env。"""
    for host in ("127.0.0.1", "::1", "localhost"):
        ensure_loopback_or_explicit_opt_in(host, env={})


def test_ensure_loopback_or_explicit_opt_in_rejects_non_loopback_without_env():
    """非 loopback host 缺少显式 env 时拒绝启动，避免误暴露。"""
    with pytest.raises(RuntimeError, match="ALLOW_REMOTE_ADMIN"):
        ensure_loopback_or_explicit_opt_in("0.0.0.0", env={})


def test_ensure_loopback_or_explicit_opt_in_allows_non_loopback_with_env(capsys):
    """显式 ALLOW_REMOTE_ADMIN=1 时通过，但应在 stderr 提示无鉴权。"""
    ensure_loopback_or_explicit_opt_in("0.0.0.0", env={"ALLOW_REMOTE_ADMIN": "1"})
    captured = capsys.readouterr()
    assert "0.0.0.0" in captured.err
    assert "warning" in captured.err.lower()


def test_ensure_loopback_or_explicit_opt_in_treats_other_env_values_as_off():
    """ALLOW_REMOTE_ADMIN 非 "1" 时按未设置处理，避免拼写造成意外放行。"""
    with pytest.raises(RuntimeError, match="ALLOW_REMOTE_ADMIN"):
        ensure_loopback_or_explicit_opt_in(
            "192.168.1.10", env={"ALLOW_REMOTE_ADMIN": "true"}
        )


def test_ensure_request_size_rejects_oversized_body():
    """请求体超出限额时直接抛 AdminPayloadTooLargeError，不读 body。"""
    with pytest.raises(AdminPayloadTooLargeError, match="upload"):
        ensure_request_size(300 * 1024 * 1024, max_bytes=200 * 1024 * 1024, kind="upload")


def test_ensure_request_size_allows_within_limit():
    """限额内通过，等于上限也允许。"""
    ensure_request_size(100, max_bytes=200, kind="json")
    ensure_request_size(200, max_bytes=200, kind="json")


def test_classify_error_response_masks_internal_exception():
    """未识别异常脱敏为 internal error，不暴露 raw exception 信息。"""
    status, body = classify_error_response(
        RuntimeError("psycopg detail with /home/adam/secret path")
    )
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body == {"error": "internal error"}


def test_classify_error_response_keeps_validation_message():
    """业务异常保留原文案，方便前端展示具体原因。"""
    status, body = classify_error_response(AdminValidationError("question is required"))
    assert status == HTTPStatus.BAD_REQUEST
    assert body == {"error": "question is required"}


def test_classify_error_response_returns_not_found_for_admin_not_found():
    """AdminNotFoundError 仍然走 404，并保留 key 信息。"""
    status, body = classify_error_response(AdminNotFoundError("faq_999"))
    assert status == HTTPStatus.NOT_FOUND
    assert "faq_999" in body["error"]


def test_classify_error_response_maps_payload_too_large():
    """请求体超限走 413，并把限额信息回给前端。"""
    status, body = classify_error_response(
        AdminPayloadTooLargeError("upload body exceeds limit")
    )
    assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert body == {"error": "upload body exceeds limit"}


def test_safe_upload_name_rejects_dot_basenames():
    """`.` / `..` / 空基名都返回安全占位，避免拼接后落到上级目录。"""
    assert safe_upload_name(".") == "upload"
    assert safe_upload_name("..") == "upload"
    assert safe_upload_name("   ") == "upload"
    assert safe_upload_name("") == "upload"


def test_safe_upload_name_keeps_normal_filename():
    """普通带扩展名/中文文件名应保留原始字符。"""
    assert safe_upload_name("manual.pdf") == "manual.pdf"
    assert safe_upload_name("操作手册.docx") == "操作手册.docx"


def test_ensure_upload_path_within_rejects_symlink_escape(tmp_path):
    """resolve 后落到 upload_dir 外的路径必须抛错，覆盖 symlink 攻击。"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    link = upload_dir / "link"
    link.symlink_to(outside)

    with pytest.raises(AdminValidationError, match="upload_dir"):
        ensure_upload_path_within(upload_dir, link)


def test_ensure_upload_path_within_allows_normal_file(tmp_path):
    """正常落在 upload_dir 内的文件返回 resolve 后的路径。"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    candidate = upload_dir / "manual.pdf"
    candidate.write_text("x")

    resolved = ensure_upload_path_within(upload_dir, candidate)
    assert resolved == candidate.resolve()
