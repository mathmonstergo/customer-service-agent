from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "customer_service_agent" / "static"


def read_static_file(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def test_admin_brand_name_uses_internal_knowledge_base() -> None:
    """管理后台名称应使用内部知识库文案，不出现具体品牌名或客服限定。"""
    html = read_static_file("admin.html")

    assert "新锐" not in html
    assert "客服知识库管理系统" not in html
    assert "<title>内部知识库管理系统</title>" in html
    assert '<div class="brand">内部知识库管理系统</div>' in html


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
    """FAQ 自动生成入口只能选择已解析文件，不能在该页面继续上传原件。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert "FAQ 管理" in html
    assert "文档管理" in html
    assert 'id="importFileInput"' not in html
    assert 'id="importFileSelect"' in html
    assert "选择文件" in html
    assert "上传 Markdown" not in html
    assert "importFiles" in html
    assert "importChunks" in html
    assert "candidateList" in html
    assert "candidateDrawer" in html
    assert "candidatePanel" not in html
    assert ".candidate-drawer" in css
    assert "function openCandidateDrawer" in js
    assert "function switchWorkspace" in js
    assert "function isParsedImportFile" in js


def test_knowledge_home_uses_lightweight_entry_cards() -> None:
    """知识库主页只做轻量入口和待处理提示，不做沉重的数据大屏。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")

    assert 'id="knowledgeWorkspace"' in html
    assert "搜索 FAQ、文档、切片和来源" in html
    assert 'data-knowledge-entry="faq"' in html
    assert 'data-knowledge-entry="documents"' in html
    assert 'data-knowledge-entry="assistant"' in html
    assert "候选 FAQ 待审核" in html
    assert "FAQ 未生成向量" in html
    assert "大屏" not in html
    assert ".knowledge-home" in css
    assert ".knowledge-card.expanded" in css
    assert ".knowledge-popover" in css
    assert "position: absolute;" in css


def test_knowledge_entry_click_expands_then_enters_workspace() -> None:
    """知识库入口第一次点击展开悬浮面板，再次点击卡片本体进入页面。"""
    js = read_static_file("admin.js")

    assert 'workspace: "knowledge"' in js
    assert "expandedKnowledgeEntry: null" in js
    assert "function handleKnowledgeEntryClick" in js
    assert "state.expandedKnowledgeEntry === entry" in js
    assert "switchWorkspace(targetWorkspace)" in js
    assert "function renderKnowledgeEntryState" in js


def test_document_management_workspace_uses_overlay_drawer_for_file_details() -> None:
    """文档管理页点击文件行后用顶层侧拉抽屉展示详情和切片，不挤压列表布局。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert 'data-target-workspace="documents"' in html
    assert 'id="documentWorkspace"' in html
    assert 'id="documentFileInput"' in html
    assert 'id="documentRows"' in html
    assert 'id="documentDrawer"' in html
    assert 'id="documentDrawerBackdrop"' in html
    assert 'id="documentChunkIndex"' in html
    assert 'id="documentChunkContent"' in html
    assert "文档导入" in html
    assert "文档解析" in html
    assert "切片查看" in html
    assert "解析失败的切片" not in html
    assert 'id="documentFailedChunks"' in html
    assert 'class="document-failed-chunks hidden"' in html
    assert ".document-drawer" in css
    assert "position: fixed;" in css
    assert "transform: translateX(100%);" in css
    assert ".document-chunk-reader" in css
    assert ".document-chunk-index" in css
    assert ".document-chunk-content" in css
    assert "function openDocumentDrawer" in js
    assert "function renderDocumentChunks" in js
    assert "function renderDocumentFailedChunks" in js
    assert "function parseCurrentDocumentFile" in js
    assert "/api/import/files?parse=false" in js


def test_document_management_workspace_polls_dynamic_mineru_progress() -> None:
    """文档解析需要按 MinerU 批量任务状态轮询，而不是阻塞到最终结果。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert 'id="documentStatusTabs"' in html
    assert 'data-document-status="processing"' in html
    assert 'id="documentParseProgress"' in html
    assert 'id="documentParseProgressBar"' in html
    assert 'id="documentParseProgressText"' in html
    assert 'id="documentParseProgressMeta"' in html
    assert ".document-progress-track" in css
    assert ".document-progress-fill" in css
    assert "documentParsePollTimer" in js
    assert "function pollDocumentParseStatus" in js
    assert "function applyDocumentParseStatus" in js
    assert "extract_progress" in js
    assert "/api/import/files/${encodeURIComponent(file.id)}/parse-jobs" in js
    assert "/api/import/files/${encodeURIComponent(fileId)}/parse-status" in js
    document_parse_function = js.split("async function parseCurrentDocumentFile", 1)[1].split(
        "function downloadCurrentDocumentFile",
        1,
    )[0]
    assert "/reparse" not in document_parse_function


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
    assert "识别所选切片 FAQ" in html
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


def test_faq_management_has_list_generation_and_review_buttons() -> None:
    """FAQ 管理页顶部用三个按钮切换列表、自动生成和审核视图。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")
    css = read_static_file("admin.css")

    assert 'data-faq-subview="list"' in html
    assert 'data-faq-subview="generate"' in html
    assert 'data-faq-subview="review"' in html
    assert "FAQ 列表" in html
    assert "FAQ 自动生成" in html
    assert "FAQ 审核" in html
    assert "状态范围" not in html
    assert "importView" in js
    assert "function switchFaqSubview" in js
    assert "function switchImportView" in js
    assert "function loadImportFileCandidates" in js
    assert ".faq-subview-tab" in css
    assert ".faq-subview-tab.active::after" in css
    assert ".faq-subview-tab.active::before" not in css
    assert "linear-gradient(90deg, transparent" in css
    assert "@keyframes faq-view-slide-from-right" in css
    assert "@keyframes faq-view-slide-from-left" in css
    assert "function animateFaqSubviewTransition" in js
    assert "function faqSubviewDirection" in js


def test_faq_generation_sidebar_matches_faq_list_width() -> None:
    """FAQ 列表和自动生成/审核页左栏宽度需要一致，避免切换时跳变。"""
    css = read_static_file("admin.css")

    assert "grid-template-columns: 324px minmax(660px, 1fr);" in css
    assert "grid-template-columns: 324px minmax(720px, 1fr);" in css
    assert "grid-template-columns: 348px minmax(720px, 1fr);" not in css


def test_faq_generation_tabs_match_list_header_height() -> None:
    """FAQ 自动生成和审核页右栏应和 FAQ 列表页从同一高度开始。"""
    css = read_static_file("admin.css")

    assert "grid-template-rows: 60px 126px 213px minmax(0, 1fr);" in css
    assert ".import-faq-tabs" in css
    assert "height: 60px;" in css
    assert "padding: 0 24px;" in css
    assert "height: calc(100% + 44px);" not in css
    assert "margin-top: -44px;" not in css
    assert "height: 100%;" in css
    assert "grid-template-rows: 52px 126px 213px minmax(0, 1fr);" not in css


def test_faq_view_slide_animation_is_clipped_inside_workspace() -> None:
    """FAQ 子页滑入动效不能让整个工作区横向溢出触发页面滚动条。"""
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert ".import-shell" in css
    assert "overflow: hidden;" in css
    assert "function faqSubviewAnimationTarget" in js
    assert "document.querySelector(\"#faqWorkspace .content\")" in js
    assert "document.querySelector(\"#importWorkspace .import-chunks-panel\")" in js
    assert 'startFaqSubviewAnimation(faqSubviewAnimationTarget(subview), direction)' in js
    assert 'startFaqSubviewAnimation($("importWorkspace"), direction)' not in js
    assert 'startFaqSubviewAnimation($("faqWorkspace"), direction)' not in js


def test_faq_generation_and_review_panels_align_with_right_column_edge() -> None:
    """FAQ 自动生成和审核页的右栏面板应贴齐右栏左边界，保持和 FAQ 列表一致。"""
    css = read_static_file("admin.css")

    assert ".import-file-overview" in css
    assert ".generation-progress" in css
    assert ".import-view-panel" in css
    assert "margin: 0 24px 14px;" not in css
    assert "margin: 0 0 14px;" in css


def test_faq_subviews_share_one_admin_workspace_frame() -> None:
    """FAQ 三个子页应共用相同左栏宽度、顶部高度和右栏裁剪规则。"""
    css = read_static_file("admin.css")

    assert ".app-shell" in css
    assert ".import-shell" in css
    assert "grid-template-columns: 324px minmax(660px, 1fr);" in css
    assert "grid-template-columns: 324px minmax(720px, 1fr);" in css
    assert ".sidebar {\n  background: var(--panel);\n  border-right: 1px solid var(--line);\n  padding: 22px 24px;" in css
    assert ".import-files-panel {\n  background: #fff;\n  border-right: 1px solid var(--line);\n  padding: 22px 24px;" in css
    assert ".content {\n  display: grid;\n  grid-template-rows: 60px minmax(0, 1fr) 58px;" in css
    assert ".import-chunks-panel {\n  display: grid;\n  grid-template-rows: 60px 126px 213px minmax(0, 1fr);" in css
    assert ".import-chunks-panel {\n  display: grid;" in css
    assert "overflow: hidden;" in css


def test_import_candidate_view_groups_candidates_by_file() -> None:
    """候选 FAQ 视图需要展示文件级候选表格和批量审核入口。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'id="candidateWorkspace"' in html
    assert 'id="fileCandidateList"' in html
    assert 'id="candidateSearchInput"' in html
    assert "批量保存" in html
    assert "AI 保守改写" in html
    assert "/api/import/files/${encodeURIComponent(fileId)}/candidates" in js


def test_import_candidate_view_can_filter_by_source_chunk() -> None:
    """从解析块跳到候选 FAQ 时，只展示该来源块生成的候选。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert 'id="candidateSourceFilterLabel"' in html
    assert 'id="clearCandidateChunkFilterButton"' in html
    assert "candidateChunkFilter: null" in js
    assert "function setCandidateChunkFilter" in js
    assert "item.chunk_id === state.candidateChunkFilter.id" in js
    assert "setCandidateChunkFilter(state.currentImportChunk)" in js
    assert 'switchImportView("candidates", { keepCandidateChunkFilter: true })' in js


def test_import_review_progress_removes_redundant_reviewed_summary_copy() -> None:
    """解析块和候选 FAQ 顶部进度不再重复展示已解析/已审核 xx/xx。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert "generationResolvedSummary" not in html
    assert "candidateReviewedSummary" not in html
    assert "已解析 0 / 0" not in html
    assert "已审核" not in html
    assert "generationResolvedSummary" not in js


def test_import_shared_shell_hides_candidate_only_metric_in_parse_mode() -> None:
    """低置信度是候选 FAQ 指标，解析块模式不能被 CSS display 覆盖后露出。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert 'id="overviewExtraMetric"' in html
    assert "overviewExtraMetric\").classList.add(\"hidden\")" in js
    assert ".overview-metric.hidden" in css
    assert ".generation-progress-item.metric-enter" in css


def test_import_view_switch_animates_metric_and_progress_cards_without_resizing_shell() -> None:
    """解析块和候选 FAQ 切换时只做内部元素动效，外层框架高度保持一致。"""
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert "function animatePanelCards" in js
    assert "animatePanelCards(\".generation-progress-item\")" in js
    assert "grid-template-rows: 60px 126px 213px minmax(0, 1fr);" in css
    assert "min-height: 66px;" in css
    assert "height: 66px;" in css
    assert "overflow: hidden;" in css


def test_candidate_review_uses_duplicate_score_not_importance() -> None:
    """候选审核抽屉展示重复度，不能把查重风险误写成重要程度。"""
    html = read_static_file("admin.html")

    assert "重复度" in html
    assert "重要程度" not in html
    assert "candidateDuplicatePercent" in html
    assert "candidateDuplicateBar" in html


def test_faq_drawer_matches_candidate_review_editor_structure() -> None:
    """标准问答编辑抽屉也需要采用新版审核抽屉的信息层级。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")

    assert "标准问答编辑" in html
    assert 'id="faqSourceBox"' in html
    assert 'id="faqInternalNote"' in html
    assert 'id="faqEditorToolbar"' in html
    assert ".review-editor-toolbar" in css


def test_drawers_are_hidden_until_explicitly_opened() -> None:
    """关闭态抽屉不能停在页面右侧，避免横向滑动看到未打开的详情页。"""
    css = read_static_file("admin.css")

    assert ".drawer {\n  position: fixed;" in css
    assert "transform: translateX(100%);" in css
    assert "visibility: hidden;" in css
    assert "pointer-events: none;" in css
    assert "opacity: 0;" in css
    assert ".drawer.open {\n  transform: translateX(0);\n  visibility: visible;" in css
    assert "pointer-events: auto;" in css
    assert "opacity: 1;" in css


def test_drawer_backdrop_closes_drawers_from_outside_click() -> None:
    """抽屉打开后点击非抽屉区域，需要通过透明遮罩关闭当前详情页。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert 'id="drawerBackdrop"' in html
    assert ".drawer-backdrop" in css
    assert ".drawer-backdrop.open" in css
    assert "function syncDrawerBackdrop" in js
    assert "closeDrawer({ force: true })" in js
    assert '$("drawerBackdrop").addEventListener("click", () => {' in js
    assert "closeCandidateDrawer();" in js


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
    """候选 FAQ 列表和审核抽屉需要展示重复度。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert "重复度" in html
    assert "candidateDuplicateLevel" in html
    assert "duplicate_level" in js
    assert "function duplicateLevelLabel" in js


def test_import_chunk_table_has_bounded_layout_and_pagination() -> None:
    """导入切块表格必须被限制在自己的网格区域内，避免覆盖候选审核区。"""
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert "grid-template-areas:" in css
    assert ".chunk-workspace > .table-wrap" in css
    assert "grid-template-rows: 54px minmax(170px, 1fr) 220px 58px;" in css
    assert "chunkPageSize" in js
    assert 'id="prevChunkPage"' in read_static_file("admin.html")
    assert '$("prevChunkPage").addEventListener("click"' in js
    assert '$("nextChunkPage").addEventListener("click"' in js
    assert '$("chunkPageSize").addEventListener("change"' in js


def test_import_chunk_selection_shows_source_text_before_candidate_navigation() -> None:
    """点击解析块应先查看原始切片内容，不应直接跳到候选 FAQ 页。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")
    css = read_static_file("admin.css")

    assert 'id="chunkPreviewPanel"' in html
    assert 'id="chunkPreviewText"' in html
    assert 'id="viewChunkCandidatesButton"' in html
    assert "function renderChunkPreview" in js
    assert "function viewCurrentChunkCandidates" in js
    assert "选择切块后切到候选审核视图" not in js
    assert "选择切块后展示原始切片内容" in js
    assert 'switchImportView("candidates", { keepCandidateChunkFilter: true })' in js
    assert ".chunk-preview-panel" in css


def test_document_chunk_reader_only_renders_raw_text_with_internal_scroll() -> None:
    """文档详情里的切片查看框只展示原文，并由查看框自身滚动。"""
    js = read_static_file("admin.js")
    css = read_static_file("admin.css")

    render_function = js.split("function renderDocumentChunkContent", 1)[1].split(
        "function renderDocumentFailedChunks",
        1,
    )[0]
    assert "document-chunk-text" in render_function
    assert "source_text" in render_function
    assert "chunkDisplayName" not in render_function
    assert "document-chunk-tags" not in render_function
    assert "chunk-meta" not in render_function
    assert "可用于 FAQ 生成" not in render_function
    assert ".document-chunk-reader" in css
    assert ".document-chunk-text" in css
    assert "overflow-y: auto;" in css


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
    assert html.index('id="notificationButton"') < html.index('id="settingsButton"') < html.index('class="user-pill"')
    assert '$("notificationButton").addEventListener("click"' in js
    assert '$("settingsButton").addEventListener("click"' in js
    assert "没有需要保存的改动" in js
    assert "state.aiRequestInFlight" in js


def test_settings_center_modal_matches_config_groups() -> None:
    """设置中心应按截图提供居中弹窗、玻璃遮罩和配置分组入口。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert 'id="settingsOverlay"' in html
    assert 'id="settingsModal"' in html
    assert 'data-settings-section="parser"' in html
    assert 'data-settings-section="llm"' in html
    assert 'data-settings-section="embedding"' in html
    assert 'data-settings-section="retrieval"' in html
    assert 'name="mineruMode"' not in html
    assert 'id="mineruApiUrl"' not in html
    assert 'id="mineruResultUrlTemplate"' not in html
    assert "官方批量文件接口" in html
    assert 'id="mineruApiToken"' in html
    assert 'data-secret-toggle="mineruApiToken"' in html
    assert 'id="saveSettingsButton"' in html
    assert 'id="saveAndTestSettingsButton"' not in html
    assert "保存并测试" not in html
    assert ".settings-overlay" in css
    assert "backdrop-filter: blur(14px);" in css
    assert "function openSettingsModal" in js
    assert "function closeSettingsModal" in js
    assert "function switchSettingsSection" in js


def test_settings_secret_fields_load_runtime_values_and_use_standard_icons() -> None:
    """密钥框应读取运行配置，并使用眼睛与复制图标而不是占位符号。"""
    html = read_static_file("admin.html")
    css = read_static_file("admin.css")
    js = read_static_file("admin.js")

    assert 'value="********************************"' not in html
    assert 'data-secret-icon="eye"' in html
    assert 'data-secret-icon="copy"' in html
    assert 'data-secret-icon="x"' in html
    assert "function loadSettingsValues" in js
    assert 'requestJson("/api/settings")' in js
    assert "setSecretValue(\"mineruApiToken\", settings.mineru_api_token)" in js
    assert 'button.dataset.secretVisible = visible ? "true" : "false"' in js
    assert ".secret-icon-eye-off" in css


def test_settings_toast_stays_above_glass_overlay() -> None:
    """设置弹窗内触发的保存或错误提示必须显示在玻璃遮罩之上。"""
    css = read_static_file("admin.css")

    assert ".settings-overlay" in css
    assert "z-index: 60;" in css
    assert ".toast" in css
    assert "z-index: 90;" in css


def test_secret_hidden_state_uses_fixed_mask_length() -> None:
    """密钥隐藏态应统一显示固定黑点，不暴露真实 Key 长度。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")
    css = read_static_file("admin.css")

    assert 'id="mineruApiToken" type="text"' in html
    assert 'id="chatApiKey" type="text"' in html
    assert 'id="embeddingApiKey" type="text"' in html
    assert 'id="databaseUrl" type="text"' in html
    assert 'const SECRET_MASK = "●".repeat(16);' in js
    assert "function setSecretValue" in js
    assert "function renderSecretInput" in js
    assert "function readSecretValue" in js
    assert "setSecretValue(\"mineruApiToken\", settings.mineru_api_token)" in js
    assert "navigator.clipboard.writeText(readSecretValue(input))" in js
    assert ".secret-mask-value" in css


def test_settings_chat_model_accepts_custom_model_names() -> None:
    """Chat 模型配置应允许直接输入自定义模型名，同时保留常用候选。"""
    html = read_static_file("admin.html")
    js = read_static_file("admin.js")

    assert '<input id="chatModel"' in html
    assert 'list="chatModelOptions"' in html
    assert '<datalist id="chatModelOptions">' in html
    assert '<select id="chatModel">' not in html
    assert "setInputValue(\"chatModel\", settings.chat_model)" in js
    assert "function setSelectValue" not in js


def test_settings_save_posts_payload_and_dirty_state_compares_baseline() -> None:
    """保存设置应调用后端接口；未保存提示要按表单快照比较，改回原值应自动消失。"""
    js = read_static_file("admin.js")

    assert "async function saveSettings" in js
    assert 'requestJson("/api/settings", {' in js
    assert 'method: "POST"' in js
    assert "function collectSettingsPayload" in js
    assert "function settingsFingerprint" in js
    assert "state.settingsBaseline = settingsFingerprint(collectSettingsPayload())" in js
    assert "state.settingsDirty = current !== state.settingsBaseline" in js
    assert 'showToast("设置已保存")' in js
    assert "设置保存接口待接入" not in js
    assert "saveAndTestSettingsButton" not in js
