from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "customer_service_agent" / "static"


def read_static_file(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def test_faq_table_renders_a_dedicated_index_column() -> None:
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert '<th class="col-index">序号</th>' in html
    assert "const rowNumber = (state.page - 1) * state.pageSize + index + 1;" in js
    assert '<td class="row-index">${rowNumber}</td>' in js
    assert 'colspan="7"' in js


def test_faq_table_body_scrolls_independently_from_pagination() -> None:
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")

    assert '<div class="table-wrap">' in html
    assert "grid-template-rows: 60px minmax(0, 1fr) 58px;" in css
    assert ".table-wrap" in css
    assert "overflow-y: auto;" in css
    assert "position: static;" in css


def test_admin_static_escapes_faq_content_before_inserting_html() -> None:
    """用户内容来自知识库和 AI，拼入 HTML 前必须转义。"""
    js = read_static_file("admin.js")

    assert "function escapeHtml" in js
    assert 'data-id="${escapeHtml(item.id)}"' in js
    assert 'title="${escapeHtml(item.question || "")}"' in js
    assert '>${escapeHtml(item.question || "")}</td>' in js
    assert "<td>${escapeHtml(item.category || \"-\")}</td>" in js
    assert "${escapeHtml(value)}" in js
    assert "<li>${escapeHtml(item)}</li>" in js


def test_admin_static_wires_visible_batch_controls_to_actions() -> None:
    """页面出现的批量控件必须有对应 JS 行为。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'id="selectAll"' in html
    assert 'id="showFailedButton"' in html
    assert 'data-status="usable"' in html
    assert 'data-status="disabled"' in html
    assert "async function batchUpdateStatus" in js
    assert '"/api/faqs/batch-status"' in js
    assert '$("selectAll").addEventListener("change"' in js
    assert '$("showFailedButton").addEventListener("click"' in js


def test_import_review_workspace_uses_generic_upload_file_copy() -> None:
    """导入审核入口面向多格式扩展，不能把按钮写死为 Markdown。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert "标准问答" in html
    assert "导入审核" in html
    assert "上传文件" in html
    assert "上传 Markdown" not in html
    assert "importFiles" in html
    assert "importChunks" in html
    assert "candidateList" in html
    assert "candidateDrawer" in html
    assert "candidatePanel" not in html
    assert ".candidate-drawer" in css
    assert "function openCandidateDrawer" in js
    assert "function switchWorkspace" in js


def test_import_review_workspace_exposes_parse_options_and_chunk_selection() -> None:
    """导入审核需要支持解析参数、单选切块和全选切块。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'id="parseModeSelect"' in html
    assert 'id="chunkDaysInput"' in html
    assert 'id="selectAllChunks"' in html
    assert "selectedImportChunks" in js
    assert "function updateSelectedChunkCount" in js
    assert "function reparseCurrentImportFile" in js
    assert "function generateCandidatesForSelectedChunks" in js


def test_ai_suggestion_request_clears_previous_visible_result() -> None:
    """第二次请求 AI 建议时不能继续展示上一次结果。"""
    js = read_static_file("admin.js")

    assert "function resetAiSuggestionPanel" in js
    assert 'resetAiSuggestionPanel("生成中")' in js
