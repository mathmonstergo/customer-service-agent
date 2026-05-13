import io
import json
import zipfile

import pytest

from customer_service_agent.document_parser import (
    MineruClient,
    MineruParseError,
    MineruParseStatus,
    ParsedBlock,
    build_import_chunks_from_blocks,
    extract_blocks_from_mineru_payload,
    package_mineru_payload_for_kb,
)


def test_extract_blocks_from_mineru_content_list_preserves_page_and_type():
    """MinerU content_list 会被转成本项目统一块结构。"""
    payload = {
        "content_list": [
            {"type": "title", "text": "账号登录", "page_idx": 0},
            {"type": "text", "text": "用户无法登录时先检查账号状态。", "page_idx": 1},
            {"type": "table", "text": "原因 | 处理\n密码错误 | 重置密码", "page_idx": 1},
        ]
    }

    blocks = extract_blocks_from_mineru_payload(payload, source_file="manual.pdf")

    assert blocks == [
        ParsedBlock(
            text="账号登录",
            block_type="title",
            page_number=1,
            section_title="账号登录",
            evidence={"source_file": "manual.pdf", "page_number": 1, "block_type": "title"},
        ),
        ParsedBlock(
            text="用户无法登录时先检查账号状态。",
            block_type="text",
            page_number=2,
            section_title="账号登录",
            evidence={"source_file": "manual.pdf", "page_number": 2, "block_type": "text"},
        ),
        ParsedBlock(
            text="原因 | 处理\n密码错误 | 重置密码",
            block_type="table",
            page_number=2,
            section_title="账号登录",
            evidence={"source_file": "manual.pdf", "page_number": 2, "block_type": "table"},
        ),
    ]


def test_build_import_chunks_from_blocks_batches_text_with_evidence():
    """解析块进入导入审核前会带上页码、章节和来源证据。"""
    blocks = [
        ParsedBlock(
            text="账号登录",
            block_type="title",
            page_number=1,
            section_title="账号登录",
            evidence={"source_file": "manual.pdf", "page_number": 1, "block_type": "title"},
        ),
        ParsedBlock(
            text="用户无法登录时先检查账号状态。",
            block_type="text",
            page_number=1,
            section_title="账号登录",
            evidence={"source_file": "manual.pdf", "page_number": 1, "block_type": "text"},
        ),
    ]

    chunks = build_import_chunks_from_blocks("imp_1", blocks, max_chars=1000)

    assert len(chunks) == 1
    assert chunks[0]["file_id"] == "imp_1"
    assert chunks[0]["chunk_index"] == 1
    assert "章节：账号登录" in chunks[0]["source_text"]
    assert "页码：1" in chunks[0]["source_text"]
    assert "用户无法登录时先检查账号状态。" in chunks[0]["source_text"]
    assert "manual.pdf" in chunks[0]["keywords"]


def test_extract_blocks_from_mineru_payload_rejects_empty_result():
    """MinerU 没有可用正文时明确报错，避免保存空切块。"""
    with pytest.raises(MineruParseError, match="no parseable text"):
        extract_blocks_from_mineru_payload({"content_list": []}, source_file="manual.pdf")


def test_package_mineru_payload_for_kb_skips_noise_and_tracks_sections():
    """可选再处理层按 mineru-kb-packager 思路生成知识库友好的块。"""
    payload = {
        "content_list_v2": [
            [
                {
                    "type": "title",
                    "content": {
                        "level": 1,
                        "title_content": [{"type": "text", "content": "账号登录"}],
                    },
                },
                {
                    "type": "paragraph",
                    "content": {
                        "paragraph_content": [
                            {"type": "text", "content": "用户无法登录时先检查账号状态。"}
                        ]
                    },
                },
                {"type": "page_footer", "content": {"text": "1"}},
            ],
            [
                {
                    "type": "title",
                    "content": {
                        "level": 1,
                        "title_content": [{"type": "text", "content": "Contents"}],
                    },
                },
                {
                    "type": "paragraph",
                    "content": {
                        "paragraph_content": [{"type": "text", "content": "这一段目录不应进入知识库。"}]
                    },
                },
            ],
        ]
    }

    blocks = package_mineru_payload_for_kb(payload, source_file="manual.pdf")

    assert len(blocks) == 1
    assert blocks[0].text == "用户无法登录时先检查账号状态。"
    assert blocks[0].block_type == "text"
    assert blocks[0].page_number == 1
    assert blocks[0].section_title == "账号登录"
    assert blocks[0].evidence["postprocess"] == "mineru-kb-packager"


def test_extract_blocks_from_mineru_payload_can_use_kb_packager_mode():
    """开关开启后优先使用知识库再处理块，而不是原始 MinerU 扁平块。"""
    payload = {
        "content_list": [
            [
                {
                    "type": "title",
                    "content": {
                        "level": 1,
                        "title_content": [{"type": "text", "content": "账号登录"}],
                    },
                },
                {
                    "type": "paragraph",
                    "content": {
                        "paragraph_content": [
                            {"type": "text", "content": "按章节整理后的正文。"}
                        ]
                    },
                },
            ]
        ]
    }

    blocks = extract_blocks_from_mineru_payload(
        payload,
        source_file="manual.pdf",
        use_kb_packager=True,
    )

    assert blocks[0].text == "按章节整理后的正文。"
    assert blocks[0].evidence["postprocess"] == "mineru-kb-packager"


def test_mineru_client_standard_mode_downloads_zip_content_list(tmp_path):
    """第三方精准 API 使用 Token、签名上传、轮询任务并读取 zip 里的结构化结果。"""
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF")
    calls = []
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr(
            "manual_content_list.json",
            json.dumps(
                [
                    {"type": "title", "text": "账号登录", "page_idx": 0},
                    {"type": "text", "text": "先检查账号状态。", "page_idx": 0},
                ],
                ensure_ascii=False,
            ),
        )

    class FakeResponse:
        def __init__(self, payload=None, status_code=200, text="", content=b""):
            self.payload = payload or {}
            self.status_code = status_code
            self.text = text
            self.content = content

        def json(self):
            return self.payload

    class FakeSession:
        def post(self, url, **kwargs):
            calls.append(("post", url, kwargs))
            assert url == "https://mineru.net/api/v4/file-urls/batch"
            assert kwargs["headers"]["Authorization"] == "Bearer mineru-token"
            assert kwargs["json"]["files"][0]["name"] == "manual.pdf"
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch_1",
                        "file_urls": [
                            {
                                "file_name": "manual.pdf",
                                "upload_url": "https://oss.example/upload",
                            }
                        ],
                    },
                }
            )

        def put(self, url, **kwargs):
            calls.append(("put", url, kwargs))
            assert url == "https://oss.example/upload"
            return FakeResponse(status_code=200)

        def get(self, url, **kwargs):
            calls.append(("get", url, kwargs))
            if url == "https://mineru.net/api/v4/extract-results/batch/batch_1":
                return FakeResponse(
                    {
                        "code": 0,
                        "data": {
                            "extract_result": [
                                {
                                    "file_name": "manual.pdf",
                                    "state": "done",
                                    "full_zip_url": "https://cdn.example/result.zip",
                                }
                            ]
                        },
                    }
                )
            if url == "https://cdn.example/result.zip":
                return FakeResponse(content=zip_buffer.getvalue())
            raise AssertionError(url)

    blocks = MineruClient(
        api_token="mineru-token",
        timeout_seconds=1,
        session=FakeSession(),
    ).parse_file(source)

    assert blocks[0].section_title == "账号登录"
    assert blocks[0].text == "先检查账号状态。"
    assert [call[0] for call in calls] == ["post", "put", "get", "get"]


def test_mineru_client_standard_mode_uses_configured_batch_urls_for_local_file(tmp_path):
    """本地文件导入走用户配置的批量文件 URL，参数由 MinerU 适配器内部构造。"""
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF")
    calls = []
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr(
            "manual_content_list.json",
            json.dumps(
                [
                    {"type": "title", "text": "地址配置", "page_idx": 0},
                    {"type": "text", "text": "具体接口地址不会拼接重复路径。", "page_idx": 0},
                ],
                ensure_ascii=False,
            ),
        )

    class FakeResponse:
        def __init__(self, payload=None, status_code=200, content=b""):
            self.payload = payload or {}
            self.status_code = status_code
            self.text = ""
            self.content = content

        def json(self):
            return self.payload

    class FakeSession:
        def post(self, url, **kwargs):
            calls.append(("post", url, kwargs))
            assert url == "https://proxy.example/mineru/file-urls/batch"
            assert kwargs["json"]["files"] == [{"name": "manual.pdf", "data_id": "manual.pdf"}]
            assert kwargs["json"]["enable_formula"] is True
            assert kwargs["json"]["enable_table"] is True
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch_1",
                        "file_urls": [
                            {
                                "file_name": "manual.pdf",
                                "upload_url": "https://oss.example/upload",
                            }
                        ],
                    },
                }
            )

        def put(self, url, **kwargs):
            calls.append(("put", url, kwargs))
            return FakeResponse(status_code=200)

        def get(self, url, **kwargs):
            calls.append(("get", url, kwargs))
            if url == "https://proxy.example/mineru/extract-results/batch/batch_1":
                return FakeResponse(
                    {
                        "code": 0,
                        "data": {
                            "extract_result": [
                                {
                                    "file_name": "manual.pdf",
                                    "state": "done",
                                    "full_zip_url": "https://cdn.example/result.zip",
                                }
                            ]
                        },
                    }
                )
            if url == "https://cdn.example/result.zip":
                return FakeResponse(content=zip_buffer.getvalue())
            raise AssertionError(url)

    blocks = MineruClient(
        api_token="mineru-token",
        batch_file_url="https://proxy.example/mineru/file-urls/batch",
        batch_result_url_template="https://proxy.example/mineru/extract-results/batch/{batch_id}",
        timeout_seconds=1,
        session=FakeSession(),
    ).parse_file(source)

    assert blocks[0].text == "具体接口地址不会拼接重复路径。"
    assert [call[1] for call in calls if call[0] in {"post", "get"}] == [
        "https://proxy.example/mineru/file-urls/batch",
        "https://proxy.example/mineru/extract-results/batch/batch_1",
        "https://cdn.example/result.zip",
    ]


def test_mineru_client_can_start_file_and_read_running_progress(tmp_path):
    """MinerU 批量上传和状态查询要拆开，前端才能展示动态解析进度。"""
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"%PDF")
    calls = []

    class FakeResponse:
        def __init__(self, payload=None, status_code=200):
            self.payload = payload or {}
            self.status_code = status_code
            self.text = ""
            self.content = b""

        def json(self):
            return self.payload

    class FakeSession:
        def post(self, url, **kwargs):
            calls.append(("post", url, kwargs))
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch_1",
                        "file_urls": [
                            {
                                "file_name": "manual.pdf",
                                "upload_url": "https://oss.example/upload",
                            }
                        ],
                    },
                }
            )

        def put(self, url, **kwargs):
            calls.append(("put", url, kwargs))
            return FakeResponse(status_code=200)

        def get(self, url, **kwargs):
            calls.append(("get", url, kwargs))
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "batch_id": "batch_1",
                        "extract_result": [
                            {
                                "file_name": "manual.pdf",
                                "state": "running",
                                "extract_progress": {
                                    "extracted_pages": 3,
                                    "total_pages": 12,
                                    "start_time": "2026-05-13 10:00:00",
                                },
                            }
                        ],
                    },
                }
            )

    client = MineruClient(api_token="mineru-token", timeout_seconds=1, session=FakeSession())

    started = client.start_file(source)
    status = client.get_task_status(started.batch_id, started.file_name)

    assert started == MineruParseStatus(
        batch_id="batch_1",
        file_name="manual.pdf",
        state="waiting-file",
        progress={},
        result={},
        error=None,
        zip_url=None,
    )
    assert status.state == "running"
    assert status.progress == {
        "extracted_pages": 3,
        "total_pages": 12,
        "start_time": "2026-05-13 10:00:00",
    }
    assert [call[0] for call in calls] == ["post", "put", "get"]
