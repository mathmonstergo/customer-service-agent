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


def test_import_workspace_hidden_state_overrides_grid_display() -> None:
    """导入审核工作区隐藏时必须覆盖自身 grid 布局，避免标准问答页向下露出导入页。"""
    css = read_static_file("admin.css")

    assert ".import-shell.hidden" in css
    assert ".import-shell.hidden {\n  display: none;\n}" in css


def test_import_review_workspace_exposes_parse_options_and_chunk_selection() -> None:
    """导入审核需要支持解析参数、单选切块和全选切块。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'id="parseModeSelect"' in html
    assert 'id="chunkDaysInput"' in html
    assert 'id="selectAllChunks"' in html
    assert "自动识别 FAQ" in html
    assert "批量生成候选 FAQ" not in html
    assert "<th>编号</th>" in html
    assert "块编号" not in html
    assert "块 #" not in js
    assert "chunk_index" in js
    assert "function chunkDisplayName" in js
    assert "selectedImportChunks" in js
    assert "function updateSelectedChunkCount" in js
    assert "function reparseCurrentImportFile" in js
    assert "function generateCandidatesForSelectedChunks" in js


def test_ai_suggestion_request_clears_previous_visible_result() -> None:
    """第二次请求 AI 建议时不能继续展示上一次结果。"""
    js = read_static_file("admin.js")

    assert "function resetAiSuggestionPanel" in js
    assert 'resetAiSuggestionPanel("生成中")' in js


def test_import_generation_job_progress_uses_event_source() -> None:
    """批量生成候选 FAQ 需要创建任务并通过 SSE 展示过程状态。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'id="generationProgress"' in html
    assert 'id="generationProgressText"' in html
    assert 'id="generationProgressBar"' in html
    assert 'id="generationProgressRatio"' in html
    assert 'id="generationCurrentChunk"' in html
    assert "当前块" not in html
    assert 'id="generationProgressItems"' in html
    assert "function startGenerationJob" in js
    assert "function renderGenerationProgress" in js
    assert "state.generationItems" in js
    assert 'classList.add("running")' in js
    assert 'classList.remove("running")' in js
    assert "new EventSource" in js
    assert "event.type === \"done\"" in js
    assert ".slice(-12)" not in js
    assert "/api/import/generation-jobs" in js


def test_import_status_colors_cover_generation_states() -> None:
    """导入切块和任务状态需要按状态区分颜色，避免 pending/generated 看起来一样。"""
    css = read_static_file("admin.css")

    assert ".status-pill.generated" in css
    assert ".status-pill.processing" in css
    assert ".status-pill.skipped" in css
    assert ".generation-progress-item.generated" in css
    assert ".generation-progress-item.processing" in css
    assert ".generation-progress-item.failed" in css
    assert ".generation-progress.running .generation-progress-bar::after" in css
    assert "@keyframes progress-pulse" in css


def test_import_file_panel_spacing_and_failed_summary_behavior() -> None:
    """上传按钮不能压住搜索框；无失败文件时查看详情不应切空文件列表。"""
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert ".import-panel-header {\n  min-height: 38px;\n  margin-bottom: 12px;\n}" in css
    assert "当前没有解析失败文件" in js
    assert 'input[name="importStatus"][value="failed"]' in js


def test_import_candidate_list_shows_duplicate_level() -> None:
    """候选 FAQ 列表和审核抽屉需要展示重复程度。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert "重复程度" in html
    assert "candidateDuplicateLevel" in html
    assert "duplicate_level" in js
    assert "function duplicateLevelLabel" in js


def test_import_chunk_table_has_bounded_layout_and_pagination() -> None:
    """导入切块表格必须被限制在自己的网格区域内，避免覆盖候选审核区。"""
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert "grid-template-areas:" in css
    assert ".import-chunks-panel > .table-wrap" in css
    assert "grid-area: chunks;" in css
    assert "chunkPageSize" in js
    assert 'id="prevChunkPage"' in read_static_file("admin.html")
    assert '$("prevChunkPage").addEventListener("click"' in js
    assert '$("nextChunkPage").addEventListener("click"' in js
    assert '$("chunkPageSize").addEventListener("change"' in js


def test_candidate_drawer_visible_actions_are_wired() -> None:
    """候选审核抽屉底部按钮必须有实际行为或禁用态。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'id="rewriteCandidateButton"' in html
    assert 'id="viewCandidateSourceButton"' in html
    assert "function rewriteCurrentCandidate" in js
    assert "function focusCurrentCandidateSource" in js
    assert '$("rewriteCandidateButton").addEventListener("click"' in js
    assert '$("viewCandidateSourceButton").addEventListener("click"' in js
    assert '$("rewriteCandidateButton").disabled = !hasCandidate;' in js


def test_faq_drawer_noop_save_and_dead_buttons_are_removed() -> None:
    """FAQ 编辑抽屉不应保留无效果按钮，未修改保存也不应触发请求。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'title="最小化"' not in html
    assert 'id="notificationButton"' in html
    assert '$("notificationButton").addEventListener("click"' in js
    assert "没有需要保存的改动" in js
    assert "state.aiRequestInFlight" in js
