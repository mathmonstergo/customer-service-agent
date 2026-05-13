const state = {
  workspace: "knowledge",
  expandedKnowledgeEntry: null,
  faqSubview: "list",
  page: 1,
  pageSize: 10,
  query: "",
  status: "",
  embeddingStatus: "",
  selected: new Set(),
  current: null,
  dirty: false,
  aiSuggestion: null,
  variants: [],
  tags: [],
  importQuery: "",
  importStatus: "",
  importView: "chunks",
  importFiles: [],
  documentQuery: "",
  documentStatus: "",
  documentFiles: [],
  currentDocumentFile: null,
  documentChunks: [],
  currentDocumentChunkIndex: 0,
  documentParsePollTimer: null,
  currentImportFile: null,
  importChunks: [],
  selectedImportChunks: new Set(),
  selectedImportCandidates: new Set(),
  currentImportChunk: null,
  importCandidates: [],
  candidateQuery: "",
  candidateStatus: "",
  candidateCategory: "",
  candidateConfidence: "",
  candidateDuplicate: "",
  candidateOnlyPending: false,
  candidateChunkFilter: null,
  currentCandidateIndex: 0,
  candidateVariants: [],
  candidateTags: [],
  generationEvents: [],
  generationJob: null,
  generationItems: {},
  generationFocusText: "当前：-",
  progressDisplayPercent: 0,
  progressResetOnNextRender: false,
  overviewAnimateOnNextRender: false,
  progressCardsAnimateOnNextRender: false,
  chunkPage: 1,
  chunkPageSize: 10,
  aiRequestInFlight: false,
  settingsDirty: false,
  settingsBaseline: "",
};

const statusOptions = ["usable", "needs_review", "disabled"];
const embeddingOptions = ["pending", "ready", "stale", "failed"];
const SECRET_MASK = "●".repeat(16);
const workspaceLabels = {
  knowledge: "主页",
  faq: "FAQ 管理",
  documents: "文档管理",
  import: "FAQ 管理",
  assistant: "智能问答",
};
const faqSubviewOrder = ["list", "generate", "review"];

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  // 将用户内容写入 HTML 字符串前转义，避免知识库内容触发脚本。
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

function safeCssToken(value) {
  // 状态值会进入 class 名，只保留安全字符。
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "");
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}

async function requestJson(path, options = {}) {
  const headers =
    options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  const response = await fetch(path, {
    headers,
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败：${response.status}`);
  }
  return payload;
}

function formatDate(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 16);
}

function statusPill(value) {
  const status = value || "pending";
  return `<span class="status-pill ${safeCssToken(status)}">${escapeHtml(status)}</span>`;
}

function importChunkStatusPill(value) {
  // 切块表格使用中文状态，避免审核人员看到数据库状态值后还要二次理解。
  const status = value || "pending";
  const labels = {
    queued: "待解析",
    pending: "待审核",
    processing: "解析中",
    generated: "已完成",
    skipped: "已完成",
    failed: "解析失败",
  };
  const classes = {
    queued: "queued",
    pending: "needs_review",
    processing: "processing",
    generated: "generated",
    skipped: "skipped",
    failed: "failed",
  };
  return `<span class="status-pill ${classes[status] || safeCssToken(status)}">${escapeHtml(labels[status] || status)}</span>`;
}

function statusPillClass(value) {
  // 将状态值统一转成可复用的 CSS class 名。
  return safeCssToken(value || "pending");
}

function chunkDisplayName(chunkId) {
  // 优先使用解析阶段生成的切块编号，找不到时再退回短 id 便于定位。
  const chunk =
    state.importChunks.find((item) => item.id === chunkId) ||
    state.documentChunks.find((item) => item.id === chunkId);
  if (chunk?.chunk_index) return `#${chunk.chunk_index}`;
  return chunkId ? `#${String(chunkId).slice(-6)}` : "#-";
}

function chunkKeywordSummary(chunk) {
  // 当前处理区只展示能帮助定位的关键词摘要，避免把原文内容塞进进度卡。
  if (!chunk) return "当前：-";
  const keywords = Array.isArray(chunk.keywords) ? chunk.keywords.join(" / ") : "";
  return keywords || chunk.source_section || chunk.source_ref || "当前：-";
}

function progressFocusChunk(chunks = state.importChunks) {
  // 进度卡优先展示真实处理中的切块；没有任务时展示下一条待审核切块作为操作焦点。
  const processingItem = Object.values(state.generationItems).find(
    (item) => item.status === "processing",
  );
  if (processingItem?.chunk_id) {
    const processingChunk = state.importChunks.find((item) => item.id === processingItem.chunk_id);
    if (processingChunk) return processingChunk;
  }
  if (state.currentImportChunk) return state.currentImportChunk;
  return chunks.find((item) => item.status === "processing")
    || chunks.find((item) => item.status !== "generated")
    || chunks[0]
    || null;
}

function setCandidateChunkFilter(chunk) {
  // 记录候选 FAQ 的来源块筛选，保证从解析块进入时只看该块候选。
  state.candidateChunkFilter = chunk
    ? { id: chunk.id, index: chunk.chunk_index || "-", label: chunkDisplayName(chunk.id) }
    : null;
  if (!$("candidateSourceFilterLabel")) return;
  $("candidateSourceFilterLabel").textContent = state.candidateChunkFilter
    ? `来源块 ${state.candidateChunkFilter.label}`
    : "全部来源块";
  $("clearCandidateChunkFilterButton").classList.toggle("hidden", !state.candidateChunkFilter);
}

function animatePanelCards(selector) {
  // 切换解析块/候选 FAQ 时只让内部卡片逐个进入，外层框架保持固定。
  document.querySelectorAll(selector).forEach((item, index) => {
    item.classList.remove("metric-enter");
    item.style.animationDelay = `${index * 48}ms`;
    void item.offsetWidth;
    item.classList.add("metric-enter");
  });
}

function animateOverviewMetrics() {
  // 概览区只动画当前模式可见的指标卡。
  animatePanelCards(".overview-metric:not(.hidden)");
}

function setProgressPercent(percent, options = {}) {
  // 工作区切换时让同一条进度条先回到 0，再增长到新页面百分比。
  const bar = $("generationProgressBar");
  const track = bar.parentElement;
  const target = Math.max(Math.min(percent, 100), 0);
  if (options.reset) {
    bar.style.width = `${state.progressDisplayPercent || 0}%`;
    window.requestAnimationFrame(() => {
      bar.style.width = "0%";
      track.style.setProperty("--progress-percent", "0%");
      window.setTimeout(() => {
        bar.style.width = `${target}%`;
        track.style.setProperty("--progress-percent", `${target}%`);
      }, 220);
    });
  } else {
    bar.style.width = `${target}%`;
    track.style.setProperty("--progress-percent", `${target}%`);
  }
  state.progressDisplayPercent = target;
}

function renderKnowledgeEntryState() {
  // 同步知识库主页入口卡片展开态，浮层只覆盖页面，不参与布局。
  document.querySelectorAll(".knowledge-entry").forEach((entry) => {
    const active = entry.dataset.knowledgeEntry === state.expandedKnowledgeEntry;
    entry.classList.toggle("expanded", active);
    entry.querySelector(".knowledge-card")?.classList.toggle("expanded", active);
  });
}

function handleKnowledgeEntryClick(entry, targetWorkspace) {
  // 第一次点击只展开入口摘要；第二次点击同一卡片才进入对应工作区。
  if (state.expandedKnowledgeEntry === entry) {
    switchWorkspace(targetWorkspace);
    return;
  }
  state.expandedKnowledgeEntry = entry;
  renderKnowledgeEntryState();
}

function documentStatusLabel(status) {
  // 文档管理面向业务用户展示中文状态，避免混淆文件解析和 FAQ 审核状态。
  const labels = {
    pending: "未解析",
    processing: "解析中",
    needs_review: "已解析",
    completed: "已完成",
    failed: "解析失败",
    unsupported: "暂不支持",
    "waiting-file": "等待上传",
    running: "解析中",
    converting: "转换中",
    done: "已解析",
  };
  return labels[status || "pending"] || status || "未解析";
}

function documentStatusPill(status) {
  // 文档状态色只表达解析生命周期，不复用 FAQ 审核含义。
  const classes = {
    pending: "pending",
    processing: "processing",
    needs_review: "ready",
    completed: "completed",
    failed: "failed",
    unsupported: "unsupported",
  };
  const raw = status || "pending";
  return `<span class="status-pill ${classes[raw] || safeCssToken(raw)}">${escapeHtml(documentStatusLabel(raw))}</span>`;
}

function renderDocumentSummary(data = {}) {
  // 刷新文档管理页顶部轻量状态，不做复杂统计面板。
  const counts = data.status_counts || {};
  $("documentTotalCount").textContent = data.total || 0;
  $("documentPendingCount").textContent = counts.pending || 0;
  $("documentParsedCount").textContent = (counts.needs_review || 0) + (counts.completed || 0);
  $("documentFailedCount").textContent = counts.failed || 0;
  $("documentListMeta").textContent = `共 ${data.total || 0} 个文档`;
  updateDocumentStatusTabs();
}

function updateDocumentStatusTabs() {
  // 状态筛选用分段按钮表达当前条件，避免下拉框隐藏解析生命周期。
  document.querySelectorAll("#documentStatusTabs [data-document-status]").forEach((button) => {
    button.classList.toggle("active", button.dataset.documentStatus === state.documentStatus);
  });
}

function documentFileVisual(item = {}) {
  // 文件类型图标只用于扫描，不参与业务判断。
  const type = String(item.file_type || item.original_name?.split(".").pop() || "doc").toLowerCase();
  if (type === "pdf") return { label: "PDF", className: "pdf" };
  if (["xlsx", "xls"].includes(type)) return { label: "XLS", className: "excel" };
  if (["md", "markdown"].includes(type)) return { label: "MD", className: "markdown" };
  if (type === "docx") return { label: "W", className: "word" };
  return { label: type.slice(0, 3).toUpperCase() || "DOC", className: "word" };
}

async function loadDocumentFiles() {
  // 文档管理复用导入文件记录，但只表达文档生命周期，不承担 FAQ 生成审核。
  const params = new URLSearchParams({ limit: "100" });
  if (state.documentQuery) params.set("query", state.documentQuery);
  if (state.documentStatus) params.set("status", state.documentStatus);
  try {
    const data = await requestJson(`/api/import/files?${params.toString()}`);
    state.documentFiles = data.items || [];
    renderDocumentSummary(data);
    updateKnowledgeImportSummary(data);
    renderDocumentRows(state.documentFiles);
    if (
      state.currentDocumentFile &&
      !state.documentFiles.some((item) => item.id === state.currentDocumentFile.id)
    ) {
      closeDocumentDrawer();
    }
  } catch (error) {
    showToast(error.message);
  }
}

function renderDocumentRows(items) {
  // 渲染文档列表，行点击打开顶层侧拉详情，删除按钮只在 hover 时出现。
  if (!items.length) {
    $("documentRows").innerHTML =
      '<tr><td colspan="6" class="document-empty">暂无文档，点击右上角上传文档。</td></tr>';
    return;
  }
  $("documentRows").innerHTML = items
    .map((item) => {
      const visual = documentFileVisual(item);
      return `
      <tr data-document-file-id="${escapeHtml(item.id)}">
        <td>
          <span class="document-name-cell">
            <i class="document-file-icon ${escapeHtml(visual.className)}">${escapeHtml(visual.label)}</i>
            <span class="document-name-text">
              <strong>${escapeHtml(item.original_name || "-")}</strong>
              <small>${escapeHtml((item.file_type || "-").toUpperCase())}</small>
            </span>
          </span>
        </td>
        <td>${formatDate(item.created_at)}</td>
        <td>${documentStatusPill(item.status)}</td>
        <td>${item.chunk_count || 0}</td>
        <td>${formatDate(item.updated_at || item.created_at)}</td>
        <td>
          <span class="document-row-actions">
            <button class="document-row-action" type="button" data-parse-document-id="${escapeHtml(item.id)}">解析</button>
            <button class="document-delete-row" type="button" data-delete-document-id="${escapeHtml(item.id)}" aria-label="删除文档">×</button>
          </span>
        </td>
      </tr>
    `;
    })
    .join("");
}

async function uploadDocumentFile(file) {
  // 文档管理上传只保存原件，不立即解析；解析由用户在详情抽屉中显式触发。
  const formData = new FormData();
  formData.append("file", file);
  try {
    const saved = await requestJson("/api/import/files?parse=false", {
      method: "POST",
      body: formData,
    });
    showToast("文档已导入，尚未解析");
    await loadDocumentFiles();
    await openDocumentDrawer(saved.id);
  } catch (error) {
    showToast(error.message);
  }
}

function renderDocumentDrawer(file = state.currentDocumentFile) {
  // 在顶层侧拉抽屉中展示文件详情和当前可执行操作，不影响列表布局。
  const hasFile = Boolean(file);
  const chunkCount = file?.chunk_count || state.documentChunks.length || 0;
  const visual = documentFileVisual(file || {});
  const progress = normalizeDocumentProgress(file?.parse_progress);
  const isParsing = file?.status === "processing";
  $("documentDrawerFileBadge").textContent = visual.label;
  $("documentDrawerFileBadge").className = `document-file-badge ${visual.className}`;
  $("documentDrawerStatus").textContent = hasFile ? documentStatusLabel(file.status) : "未选择";
  $("documentDrawerTitle").textContent = file?.original_name || "请选择文档";
  $("documentDrawerMeta").textContent = hasFile
    ? ` ${file.parser || "-"} / ${formatDate(file.updated_at || file.created_at)}`
    : "未选择文档";
  $("documentDetailType").textContent = file?.file_type ? file.file_type.toUpperCase() : "-";
  $("documentDetailUploadedAt").textContent = hasFile ? formatDate(file.created_at) : "-";
  $("documentDetailParser").textContent = file?.parser || "-";
  $("documentDetailParsedAt").textContent = hasFile ? formatDate(file.updated_at || file.created_at) : "-";
  $("documentDetailChunks").textContent = String(chunkCount);
  $("parseDocumentButton").textContent =
    chunkCount || file?.status === "failed" ? "重新解析" : isParsing ? "解析中" : "开始解析";
  $("parseDocumentButton").disabled = !hasFile || file.status === "unsupported" || isParsing;
  $("sendDocumentToFaqButton").disabled = !hasFile || chunkCount === 0;
  $("downloadDocumentButton").disabled = !hasFile;
  $("deleteDocumentButton").disabled = !hasFile;
  $("documentErrorText").textContent = file?.error || "";
  $("documentErrorText").classList.toggle("hidden", !file?.error);
  renderDocumentProgress({ state: progress.state || file?.status, progress, percent: documentProgressPercent(progress) });
}

async function loadDocumentChunks(fileId) {
  // 载入指定文档的解析切片，供详情抽屉直接预览来源内容。
  try {
    const data = await requestJson(`/api/import/files/${encodeURIComponent(fileId)}/chunks`);
    state.documentChunks = data.items || [];
    renderDocumentChunks(state.documentChunks);
    renderDocumentDrawer(state.currentDocumentFile);
  } catch (error) {
    state.documentChunks = [];
    renderDocumentChunks([]);
    showToast(error.message);
  }
}

function renderDocumentChunks(chunks = state.documentChunks) {
  // 切片预览采用左侧索引和右侧正文，FAQ 生成动作留到 FAQ 管理中处理。
  $("documentChunkSummary").textContent = chunks.length ? `共 ${chunks.length} 个切片` : "暂无切片";
  if (!chunks.length) {
    $("documentChunkIndex").innerHTML = "";
    $("documentChunkContent").innerHTML =
      '<div class="document-empty">当前文档还没有切片。</div>';
    renderDocumentFailedChunks([]);
    return;
  }
  if (state.currentDocumentChunkIndex >= chunks.length) state.currentDocumentChunkIndex = 0;
  $("documentChunkIndex").innerHTML = chunks
    .map((chunk, index) => `
      <button class="${index === state.currentDocumentChunkIndex ? "active" : ""}" type="button" data-document-chunk-index="${index}">
        ${escapeHtml(chunkDisplayName(chunk.id))}
      </button>
    `)
    .join("");
  renderDocumentChunkContent(chunks[state.currentDocumentChunkIndex]);
  renderDocumentFailedChunks(chunks);
}

function renderDocumentChunkContent(chunk) {
  // 右侧查看框只显示切片原文，所有辅助信息留在列表和标题区。
  if (!chunk) {
    $("documentChunkContent").innerHTML = '<div class="document-empty">当前文档还没有切片。</div>';
    return;
  }
  $("documentChunkContent").innerHTML = `
    <div class="document-chunk-text">${escapeHtml(chunk.source_text || "当前切片没有可展示内容")}</div>
  `;
}

function renderDocumentFailedChunks(chunks) {
  // MinerU 通常只返回文件级失败；只有本地切片带失败状态时才展示异常切片区。
  const failed = chunks.filter((chunk) => chunk.status === "failed");
  if (!failed.length) {
    $("documentFailedChunks").classList.add("hidden");
    $("documentFailedChunks").innerHTML = "";
    return;
  }
  $("documentFailedChunks").classList.remove("hidden");
  $("documentFailedChunks").innerHTML = `
    <strong>异常切片</strong>
    ${failed.map((chunk) => `<p>${escapeHtml(chunkDisplayName(chunk.id))}：${escapeHtml(chunk.error || "解析失败")}</p>`).join("")}
  `;
}

async function openDocumentDrawer(fileId) {
  // 文件行点击后打开固定定位侧拉详情，避免改变文档列表初始布局。
  const file = state.documentFiles.find((item) => item.id === fileId) || { id: fileId };
  state.currentDocumentFile = file;
  state.documentChunks = [];
  state.currentDocumentChunkIndex = 0;
  renderDocumentDrawer(file);
  renderDocumentChunks([]);
  $("documentDrawer").classList.add("open");
  $("documentDrawer").setAttribute("aria-hidden", "false");
  $("documentDrawerBackdrop").classList.add("open");
  $("documentDrawerBackdrop").setAttribute("aria-hidden", "false");
  await loadDocumentChunks(fileId);
}

function closeDocumentDrawer() {
  // 关闭文档详情抽屉，不清空列表筛选条件。
  stopDocumentParsePolling();
  $("documentDrawer").classList.remove("open");
  $("documentDrawer").setAttribute("aria-hidden", "true");
  $("documentDrawerBackdrop").classList.remove("open");
  $("documentDrawerBackdrop").setAttribute("aria-hidden", "true");
  state.currentDocumentFile = null;
  state.documentChunks = [];
  state.currentDocumentChunkIndex = 0;
}

async function parseCurrentDocumentFile() {
  // 用户显式触发文档解析；上传动作本身不再自动调用 MinerU。
  const file = state.currentDocumentFile;
  if (!file) {
    showToast("请先选择文档");
    return;
  }
  $("parseDocumentButton").disabled = true;
  renderDocumentProgress({ state: "waiting-file", progress: { state: "waiting-file" }, percent: 0 });
  try {
    const payload = await requestJson(`/api/import/files/${encodeURIComponent(file.id)}/parse-jobs`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    applyDocumentParseStatus(payload);
    showToast("文档解析任务已提交");
    await loadDocumentFiles();
    state.currentDocumentFile = state.documentFiles.find((item) => item.id === file.id) || payload.file || file;
    renderDocumentDrawer(state.currentDocumentFile);
    pollDocumentParseStatus(file.id);
  } catch (error) {
    showToast(error.message);
    renderDocumentDrawer(file);
  } finally {
    if (state.currentDocumentFile?.status !== "processing") $("parseDocumentButton").disabled = false;
  }
}

function downloadCurrentDocumentFile() {
  // 通过后端下载已登记的本地原件，避免前端直接暴露文件系统路径。
  const file = state.currentDocumentFile;
  if (!file) return;
  window.location.href = `/api/import/files/${encodeURIComponent(file.id)}/download`;
}

async function deleteCurrentDocumentFile(fileId = state.currentDocumentFile?.id) {
  // 删除文档记录和本地原件，成功后关闭详情抽屉并刷新列表。
  if (!fileId) return;
  try {
    await requestJson(`/api/import/files/${encodeURIComponent(fileId)}`, { method: "DELETE" });
    showToast("文档已删除");
    if (state.currentDocumentFile?.id === fileId) closeDocumentDrawer();
    await loadDocumentFiles();
  } catch (error) {
    showToast(error.message);
  }
}

function normalizeDocumentProgress(value) {
  // 兼容后端 progress 和 MinerU 原始 extract_progress 字段。
  if (!value) return {};
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch (error) {
      return { state: value };
    }
  }
  if (typeof value === "object") return { ...value };
  return {};
}

function documentProgressPercent(progress = {}, payload = {}) {
  // 优先使用后端百分比，缺少时按 extract_progress 页数计算。
  if (typeof payload.percent === "number") return Math.max(0, Math.min(100, payload.percent));
  const total = Number(progress.total_pages || 0);
  const extracted = Number(progress.extracted_pages || 0);
  if (total > 0) return Math.max(0, Math.min(100, Math.round((extracted / total) * 100)));
  if (["done", "finished", "success", "completed"].includes(String(progress.state || ""))) return 100;
  return 0;
}

function renderDocumentProgress(payload = {}) {
  // 渲染 MinerU 动态解析状态，非解析中且无进度时隐藏。
  const progress = normalizeDocumentProgress(payload.progress || payload.extract_progress);
  const stateText = payload.state || progress.state || "pending";
  const percent = documentProgressPercent(progress, payload);
  const visible = ["waiting-file", "pending", "running", "converting", "processing"].includes(stateText);
  $("documentParseProgress").classList.toggle("hidden", !visible);
  $("documentParseProgressText").textContent = `解析进度 ${percent}%`;
  const pageText = progress.total_pages
    ? `${progress.extracted_pages || 0} / ${progress.total_pages} 页`
    : documentStatusLabel(stateText === "processing" ? "processing" : stateText);
  $("documentParseProgressMeta").textContent = pageText;
  $("documentParseProgressBar").style.width = `${percent}%`;
}

function applyDocumentParseStatus(payload) {
  // 轮询响应会覆盖当前文件状态，并在结束时刷新切片。
  if (!payload) return;
  const file = payload.file || state.currentDocumentFile;
  if (file) {
    file.parse_progress = payload.progress || file.parse_progress;
    file.status = payload.status || file.status;
    file.error = payload.error || file.error;
    state.currentDocumentFile = file;
  }
  renderDocumentProgress(payload);
  renderDocumentDrawer(state.currentDocumentFile);
}

async function pollDocumentParseStatus(fileId) {
  // 按 MinerU 动态状态轮询，done/failed 后停止并刷新切片列表。
  stopDocumentParsePolling();
  const tick = async () => {
    try {
      const payload = await requestJson(`/api/import/files/${encodeURIComponent(fileId)}/parse-status`);
      applyDocumentParseStatus(payload);
      if (["done", "finished", "success", "completed"].includes(payload.state)) {
        stopDocumentParsePolling();
        await loadDocumentFiles();
        state.currentDocumentFile =
          state.documentFiles.find((item) => item.id === fileId) || payload.file || state.currentDocumentFile;
        await loadDocumentChunks(fileId);
        showToast("文档解析完成");
        return;
      }
      if (["failed", "error", "cancelled", "canceled"].includes(payload.state)) {
        stopDocumentParsePolling();
        await loadDocumentFiles();
        showToast(payload.error || "文档解析失败");
        return;
      }
      state.documentParsePollTimer = window.setTimeout(tick, 2500);
    } catch (error) {
      stopDocumentParsePolling();
      showToast(error.message);
    }
  };
  state.documentParsePollTimer = window.setTimeout(tick, 800);
}

function stopDocumentParsePolling() {
  // 抽屉关闭或任务结束时清理轮询定时器，避免重复请求。
  if (state.documentParsePollTimer) {
    window.clearTimeout(state.documentParsePollTimer);
    state.documentParsePollTimer = null;
  }
}

async function sendCurrentDocumentToFaq() {
  // 将已解析文档交给 FAQ 自动生成视图，保持上传和解析仍由文档管理负责。
  const file = state.currentDocumentFile;
  if (!file) return;
  closeDocumentDrawer();
  await switchFaqSubview("generate");
  await selectImportFile(file.id);
}

function updateKnowledgeImportSummary(data = {}) {
  // 将文档文件状态汇总到轻量知识库主页，不强制打开文档管理页。
  const counts = data.status_counts || {};
  if ($("homeDocumentCount")) $("homeDocumentCount").textContent = data.total || 0;
  if ($("homeParsedDocumentCount")) {
    $("homeParsedDocumentCount").textContent =
      (counts.needs_review || 0) + (counts.completed || 0);
  }
  if ($("homeParseFailedCount")) $("homeParseFailedCount").textContent = counts.failed || 0;
}

async function loadKnowledgeImportSummary() {
  // 首页只读取文件统计，不改变当前选中文档，避免入口页变成重型工作台。
  if (!$("homeDocumentCount")) return;
  try {
    const data = await requestJson("/api/import/files?limit=100");
    updateKnowledgeImportSummary(data);
  } catch {
    updateKnowledgeImportSummary({});
  }
}

function renderKnowledgeFaqSummary(data = {}) {
  // 首页只展示 FAQ 待处理数字，让用户知道下一步该去哪里。
  const statusCounts = data.status_counts || {};
  const embeddingCounts = data.embedding_counts || {};
  if ($("homePendingFaqCount")) {
    $("homePendingFaqCount").textContent = statusCounts.needs_review || 0;
  }
  if ($("homePendingEmbeddingCount")) {
    $("homePendingEmbeddingCount").textContent =
      (embeddingCounts.pending || 0) + (embeddingCounts.stale || 0) + (embeddingCounts.failed || 0);
  }
  if ($("homeUsableFaqCount")) $("homeUsableFaqCount").textContent = statusCounts.usable || 0;
}

function runKnowledgeSearch() {
  // 首页搜索默认进入 FAQ 管理，后续可扩展到跨文档和切片检索。
  const query = $("knowledgeSearchInput").value.trim();
  state.query = query;
  $("searchInput").value = query;
  state.page = 1;
  switchWorkspace("faq");
  loadFaqs();
}

function updateFaqSubviewTabs() {
  // 同步 FAQ 管理三个子视图按钮状态，列表页和生成/审核页共用同一组入口。
  document.querySelectorAll("[data-faq-subview]").forEach((button) => {
    button.classList.toggle("active", button.dataset.faqSubview === state.faqSubview);
  });
}

function faqSubviewDirection(fromSubview, toSubview) {
  // 按列表、自动生成、审核的顺序判断翻页方向，保证切换动效符合空间关系。
  const fromIndex = faqSubviewOrder.indexOf(fromSubview);
  const toIndex = faqSubviewOrder.indexOf(toSubview);
  return toIndex >= fromIndex ? "right" : "left";
}

function startFaqSubviewAnimation(target, direction) {
  // 重新触发轻量左右滑入动画，只影响当前工作区容器，不改变布局尺寸。
  if (!target) return;
  const className = direction === "left" ? "faq-view-enter-from-left" : "faq-view-enter-from-right";
  target.classList.remove("faq-view-enter-from-left", "faq-view-enter-from-right");
  void target.offsetWidth;
  target.classList.add(className);
  target.addEventListener("animationend", () => target.classList.remove(className), { once: true });
}

function faqSubviewAnimationTarget(subview) {
  // 子页滑动只作用在右侧主内容，避免外层 grid 平移撑出临时横向滚动条。
  if (subview === "list") return document.querySelector("#faqWorkspace .content");
  return document.querySelector("#importWorkspace .import-chunks-panel");
}

function animateFaqSubviewTransition(subview, direction, options = {}) {
  // 跨列表/生成/审核切换时做页面级滑入；生成和审核内部切换时只动画内容面板。
  if (options.panelOnly) {
    startFaqSubviewAnimation(subview === "review" ? $("candidateWorkspace") : $("chunkWorkspace"), direction);
    return;
  }
  startFaqSubviewAnimation(faqSubviewAnimationTarget(subview), direction);
}

async function switchFaqSubview(subview) {
  // FAQ 管理子视图只切换职责入口，自动生成和审核继续复用现有导入审核数据流。
  const direction = faqSubviewDirection(state.faqSubview, subview);
  state.faqSubview = subview;
  updateFaqSubviewTabs();
  if (subview === "list") {
    switchWorkspace("faq");
    animateFaqSubviewTransition(subview, direction);
    return;
  }
  switchWorkspace("import", { skipLoad: true });
  await loadImportFiles();
  await switchImportView(subview === "review" ? "candidates" : "chunks", { suppressAnimation: true });
  animateFaqSubviewTransition(subview, direction);
}

function switchWorkspace(workspace, options = {}) {
  // 切换知识库主页、FAQ 管理、文档管理和智能问答工作区。
  closeDrawer({ force: true });
  closeCandidateDrawer();
  closeDocumentDrawer();
  state.workspace = workspace;
  if (workspace === "faq") state.faqSubview = "list";
  if (workspace === "import" && state.faqSubview === "list") {
    state.faqSubview = state.importView === "candidates" ? "review" : "generate";
  }
  state.expandedKnowledgeEntry = null;
  renderKnowledgeEntryState();
  $("knowledgeWorkspace").classList.toggle("hidden", workspace !== "knowledge");
  $("faqWorkspace").classList.toggle("hidden", workspace !== "faq");
  $("documentWorkspace").classList.toggle("hidden", workspace !== "documents");
  $("importWorkspace").classList.toggle("hidden", workspace !== "import");
  $("assistantWorkspace").classList.toggle("hidden", workspace !== "assistant");
  $("workspaceTitle").textContent = workspaceLabels[workspace] || "主页";
  $("workspaceTitle").classList.toggle("hidden", workspace === "knowledge");
  $("workspaceChevron").classList.toggle("hidden", workspace === "knowledge");
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.workspace === workspace);
  });
  updateFaqSubviewTabs();
  if (!options.skipLoad && workspace === "faq") loadFaqs();
  if (!options.skipLoad && workspace === "import") loadImportFiles();
  if (!options.skipLoad && workspace === "documents") loadDocumentFiles();
  if (!options.skipLoad && workspace === "knowledge") loadKnowledgeImportSummary();
}

async function switchImportView(view, options = {}) {
  // 在导入审核内切换解析块和候选 FAQ 两个工作阶段。
  const changed = state.importView !== view;
  const previousSubview = state.faqSubview;
  state.importView = view;
  state.faqSubview = view === "candidates" ? "review" : "generate";
  updateFaqSubviewTabs();
  if (changed) {
    state.progressResetOnNextRender = true;
    state.overviewAnimateOnNextRender = true;
    state.progressCardsAnimateOnNextRender = true;
  }
  if (view === "candidates" && !options.keepCandidateChunkFilter) {
    setCandidateChunkFilter(null);
  }
  $("chunkWorkspace").classList.toggle("hidden", view !== "chunks");
  $("candidateWorkspace").classList.toggle("hidden", view !== "candidates");
  if (view === "candidates" && state.currentImportFile) {
    await loadImportFileCandidates(state.currentImportFile.id);
  } else {
    renderImportOverview(state.currentImportFile, state.importChunks);
    renderGenerationProgress();
  }
  if (changed && !options.suppressAnimation) {
    animateFaqSubviewTransition(state.faqSubview, faqSubviewDirection(previousSubview, state.faqSubview), {
      panelOnly: true,
    });
  }
}

function filterItem(group, value, label, count, activeValue) {
  const checked = activeValue === value ? "checked" : "";
  return `
    <label class="filter-item">
      <input type="radio" name="${group}" value="${value}" ${checked}>
      <span>${label}</span>
      <span class="count">${count || 0}</span>
    </label>
  `;
}

function renderImportPlaceholder() {
  // 第一屏先渲染空状态，真实数据由后续导入 API 接入。
  if (!$("importFiles")) return;
  $("importFiles").innerHTML =
    '<div class="import-empty">暂无已解析文件，请先在文档管理页上传并解析。</div>';
  renderImportFileSelect([]);
  $("importChunks").innerHTML =
    '<tr><td colspan="8" class="empty">请选择左侧文件查看解析块</td></tr>';
  $("fileCandidateList").innerHTML =
    '<tr><td colspan="9" class="empty">请选择文件后查看候选 FAQ</td></tr>';
  $("candidateList").innerHTML = "";
  $("candidateListSummary").textContent = "请选择文件后查看候选 FAQ";
  setCandidateChunkFilter(null);
  renderImportOverview(null, []);
  renderChunkPreview(null);
  updateSelectedChunkCount();
  updateSelectedCandidateCount();
  closeCandidateDrawer();
  resetGenerationProgress();
}

function isParsedImportFile(file) {
  // FAQ 自动生成只允许选择已经解析出切片的文件，避免在此入口重新上传原件。
  return ["needs_review", "completed"].includes(file?.status) || Number(file?.chunk_count || 0) > 0;
}

function resetGenerationProgress() {
  // 切换文件或空状态时清理上一轮生成进度，避免旧任务状态误导当前文件。
  state.generationEvents = [];
  state.generationJob = null;
  state.generationItems = {};
  state.generationFocusText = "当前：-";
  if (!$("generationProgress")) return;
  $("generationProgress").classList.remove("running");
  $("generationProgressText").textContent = "等待任务开始";
  setProgressPercent(0);
  $("generationProgressRatio").textContent = "0%";
  $("generationCurrentIndex").textContent = "-";
  $("generationCurrentChunk").textContent = "请选择解析块或按需识别候选 FAQ";
  $("generationCurrentBar").style.width = "0%";
  $("generationEstimate").textContent = "--";
  $("generationLastUpdated").textContent = "--";
  $("generationCurrentEta").textContent = "预计剩余 --";
  renderGenerationProgress();
}

function resetCandidateFilters() {
  // 切换导入文件时重置候选审核筛选，避免上一个文件的条件影响当前文件。
  state.candidateQuery = "";
  state.candidateStatus = "";
  state.candidateCategory = "";
  state.candidateConfidence = "";
  state.candidateDuplicate = "";
  state.candidateOnlyPending = false;
  setCandidateChunkFilter(null);
  if (!$("candidateSearchInput")) return;
  $("candidateSearchInput").value = "";
  $("candidateStatusSelect").value = "";
  $("candidateCategorySelect").value = "";
  $("candidateConfidenceSelect").value = "";
  $("candidateDuplicateSelect").value = "";
  $("onlyPendingCandidates").checked = false;
}

async function loadImportFiles() {
  // 载入已解析文件列表，驱动 FAQ 自动生成的文件选择器和左侧文件栏。
  const params = new URLSearchParams({ limit: "100" });
  if (state.importQuery) params.set("query", state.importQuery);
  if (state.importStatus) params.set("status", state.importStatus);
  try {
    const data = await requestJson(`/api/import/files?${params.toString()}`);
    state.importFiles = (data.items || []).filter(isParsedImportFile);
    updateKnowledgeImportSummary(data);
    renderImportFileCounts({ ...data, total: state.importFiles.length });
    renderImportFiles(state.importFiles);
    const currentStillVisible = state.importFiles.some(
      (item) => item.id === state.currentImportFile?.id,
    );
    if (!currentStillVisible) {
      state.currentImportFile = null;
      state.currentImportChunk = null;
      state.importCandidates = [];
      state.importChunks = [];
      state.selectedImportChunks.clear();
      state.selectedImportCandidates.clear();
      state.chunkPage = 1;
      renderImportChunks([]);
      renderImportCandidateList();
    }
    if (!state.currentImportFile && state.importFiles.length) {
      await selectImportFile(state.importFiles[0].id);
    }
  } catch (error) {
    showToast(error.message);
  }
}

function renderImportFileCounts(data) {
  // 刷新已解析文件选择区的状态数量和列表汇总。
  const counts = data.status_counts || {};
  $("importCountAll").textContent = data.total || 0;
  $("importCountPending").textContent = counts.pending || 0;
  $("importCountProcessing").textContent = counts.processing || 0;
  $("importCountReview").textContent = counts.needs_review || 0;
  $("importCountCompleted").textContent = counts.completed || 0;
  $("importCountUnsupported").textContent = counts.unsupported || 0;
  $("importCountFailed").textContent = counts.failed || 0;
  $("importFailedCount").textContent = counts.failed || 0;
  $("importFileSummary").textContent = `共 ${data.total || 0} 个`;
}

function renderImportOverview(file, chunks = state.importChunks) {
  // 汇总当前文件的解析块和候选数量，作为导入审核工作台的顶部上下文。
  $("overviewFileName").textContent = file?.original_name || "请选择导入文件";
  $("overviewFileMeta").textContent = file
    ? `来源：${file.file_type || "-"} / ${file.parser || "-"} · 共 ${file.chunk_count || 0} 块`
    : "选择文件后查看解析块和候选 FAQ。";
  $("overviewParserTag").textContent = file?.parser || "-";
  $("overviewStatusTag").textContent = file?.status || "-";
  if (state.importView === "candidates") {
    const candidates = candidateScopeItems();
    $("overviewMetric1Label").textContent = "候选 FAQ 总数";
    $("overviewMetric2Label").textContent = "待审核";
    $("overviewMetric3Label").textContent = "已保存";
    $("overviewMetric4Label").textContent = "已忽略";
    $("overviewMetric5Label").textContent = "低置信度";
    $("overviewChunkCount").textContent = String(candidates.length || file?.candidate_count || 0);
    $("overviewPendingChunkCount").textContent = String(
      candidates.filter((item) => item.status === "pending").length,
    );
    $("overviewCandidateCount").textContent = String(
      candidates.filter((item) => item.status === "saved").length,
    );
    $("overviewFailedChunkCount").textContent = String(
      candidates.filter((item) => item.status === "ignored").length,
    );
    $("overviewLowConfidenceCount").textContent = String(
      candidates.filter((item) => item.confidence === "low").length,
    );
    $("overviewExtraMetric").classList.remove("hidden");
    if (state.overviewAnimateOnNextRender) {
      animateOverviewMetrics();
      state.overviewAnimateOnNextRender = false;
    }
    return;
  }
  $("overviewMetric1Label").textContent = "总解析块";
  $("overviewMetric2Label").textContent = "待审核块";
  $("overviewMetric3Label").textContent = "生成候选 FAQ";
  $("overviewMetric4Label").textContent = "解析失败块";
  $("overviewExtraMetric").classList.add("hidden");
  $("overviewChunkCount").textContent = String(chunks.length || file?.chunk_count || 0);
  $("overviewPendingChunkCount").textContent = String(
    chunks.filter((item) => item.status !== "generated").length || 0,
  );
  $("overviewCandidateCount").textContent = String(
    state.importCandidates.length || file?.candidate_count || 0,
  );
  $("overviewFailedChunkCount").textContent = String(
    chunks.filter((item) => item.status === "failed").length || 0,
  );
  if (state.overviewAnimateOnNextRender) {
    animateOverviewMetrics();
    state.overviewAnimateOnNextRender = false;
  }
}

function renderImportFiles(items) {
  // 渲染左侧导入文件列表，展示识别类型和解析状态。
  if (!items.length) {
    renderImportPlaceholder();
    return;
  }
  renderImportFileSelect(items);
  $("importFiles").innerHTML = items
    .map((item) => {
      const active = state.currentImportFile?.id === item.id ? "active" : "";
      return `
        <button class="import-file-item ${active}" type="button" data-import-file-id="${escapeHtml(item.id)}">
          <span class="file-icon">▧</span>
          <span class="file-main">
            <strong>${escapeHtml(item.original_name)}</strong>
            <em>${escapeHtml(item.file_type)} / ${escapeHtml(item.parser)}</em>
            <small>${item.chunk_count || 0} 块 / ${item.candidate_count || 0} 条候选</small>
          </span>
          ${statusPill(item.status)}
        </button>
      `;
    })
    .join("");
}

function renderImportFileSelect(items) {
  // 文件选择器只列出已解析文件，和下方列表保持同一数据范围。
  const select = $("importFileSelect");
  if (!select) return;
  select.disabled = !items.length;
  select.innerHTML = [
    '<option value="">请选择已解析文件</option>',
    ...items.map((item) => `
      <option value="${escapeHtml(item.id)}">${escapeHtml(item.original_name || "未命名文件")}</option>
    `),
  ].join("");
  const currentVisible = items.some((item) => item.id === state.currentImportFile?.id);
  select.value = currentVisible ? state.currentImportFile.id : "";
}

async function uploadImportFile(file) {
  // 使用通用上传入口提交文件，由后端自动识别格式。
  const formData = new FormData();
  formData.append("file", file);
  try {
    const saved = await requestJson("/api/import/files", {
      method: "POST",
      body: formData,
    });
    showToast(saved.status === "unsupported" ? "文件已保存，当前格式暂不支持解析" : "文件已解析");
    await loadImportFiles();
    selectImportFile(saved.id);
  } catch (error) {
    showToast(error.message);
  }
}

async function selectImportFile(fileId) {
  // 选择导入文件后加载对应解析块，并重置上一文件的切片预览。
  const file = state.importFiles.find((item) => item.id === fileId) || { id: fileId };
  state.currentImportFile = file;
  state.currentImportChunk = null;
  state.importCandidates = [];
  state.selectedImportChunks.clear();
  state.selectedImportCandidates.clear();
  resetCandidateFilters();
  renderChunkPreview(null);
  state.currentCandidateIndex = 0;
  state.chunkPage = 1;
  renderImportFiles(state.importFiles);
  if ($("importFileSelect")) $("importFileSelect").value = file.id || "";
  renderImportCandidateList();
  closeCandidateDrawer();
  resetGenerationProgress();
  $("currentImportFileName").textContent = file.original_name || "导入文件";
  $("currentImportMeta").textContent = `${file.file_type || "-"} / ${file.parser || "-"} / ${file.status || "-"}`;
  renderImportOverview(file, []);
  if (file.status === "unsupported") {
    $("importChunks").innerHTML =
      '<tr><td colspan="8" class="empty">当前文件类型已识别，但第一期暂不支持解析</td></tr>';
    renderChunkPreview(null);
    renderImportCandidateList("当前文件类型暂不支持解析");
    return;
  }
  await loadImportChunks(fileId);
  if (state.importView === "candidates") await loadImportFileCandidates(fileId);
}

async function loadImportChunks(fileId) {
  // 载入中间栏解析块，兼容聊天记录与 MinerU 文档解析结果。
  try {
    const data = await requestJson(`/api/import/files/${encodeURIComponent(fileId)}/chunks`);
    state.importChunks = data.items || [];
    if (state.currentImportChunk) {
      state.currentImportChunk =
        state.importChunks.find((item) => item.id === state.currentImportChunk.id) || null;
    }
    renderImportOverview(state.currentImportFile, state.importChunks);
    renderImportChunks(state.importChunks);
  } catch (error) {
    showToast(error.message);
  }
}

function renderImportChunks(items) {
  // 渲染切块表格，保留来源范围、内容量、关键词和候选数。
  const filteredItems = filteredImportChunks(items);
  const visibleItems = visibleImportChunks(items);
  const totalPages = Math.max(Math.ceil(filteredItems.length / state.chunkPageSize), 1);
  state.chunkPage = Math.min(Math.max(state.chunkPage, 1), totalPages);
  $("chunkSummary").textContent = `共 ${filteredItems.length} 块`;
  $("chunkRangeStart").value = filteredItems.length ? "1" : "0";
  $("chunkRangeEnd").value = String(filteredItems.length);
  $("chunkPageNumber").textContent = String(state.chunkPage);
  $("prevChunkPage").disabled = state.chunkPage <= 1;
  $("nextChunkPage").disabled = state.chunkPage >= totalPages;
  updateSelectedChunkCount();
  renderGenerationProgress();
  if (!visibleItems.length) {
    $("importChunks").innerHTML = '<tr><td colspan="8" class="empty">暂无解析块</td></tr>';
    renderChunkPreview(state.currentImportChunk);
    return;
  }
  const focusChunk = progressFocusChunk(visibleItems);
  $("importChunks").innerHTML = visibleItems
    .map((item) => {
      const active = state.currentImportChunk?.id === item.id
        ? "selected"
        : !state.currentImportChunk && focusChunk?.id === item.id
          ? "visual-current"
          : "";
      const checked = state.selectedImportChunks.has(item.id) ? "checked" : "";
      const keywords = Array.isArray(item.keywords) ? item.keywords.join(" / ") : "";
      return `
        <tr class="${active}" data-import-chunk-id="${escapeHtml(item.id)}">
          <td><input type="checkbox" class="chunk-check" data-id="${escapeHtml(item.id)}" ${checked}></td>
          <td class="chunk-index-cell">#${escapeHtml(item.chunk_index || "-")}</td>
          <td>${formatDate(item.start_at)} - ${formatDate(item.end_at).slice(11) || "-"}</td>
          <td>${contentUnitLabel(item.message_count || 0)}</td>
          <td>${escapeHtml(keywords || "-")}</td>
          <td>${importChunkStatusPill(item.status)}</td>
          <td>${item.candidate_count || 0} 条候选</td>
          <td><button class="candidate-review-button" type="button">查看内容</button></td>
        </tr>
      `;
    })
    .join("");
  updateSelectedChunkCount();
  renderChunkPreview(state.currentImportChunk);
}

function contentUnitLabel(count) {
  // 文档切片和聊天记录共用字段，前端按解析器显示更准确的单位。
  return state.currentImportFile?.parser === "markdown_chat"
    ? `${count} 条消息`
    : `${count} 段内容`;
}

function filteredImportChunks(items = state.importChunks) {
  // 根据“仅查看待审核”筛选切块，分页前保留完整集合。
  if (!$("onlyReviewChunks")?.checked) return items;
  return items.filter((item) => item.status !== "generated");
}

function visibleImportChunks(items = state.importChunks) {
  // 返回当前页实际展示的切块，表头全选只作用于当前页。
  const filteredItems = filteredImportChunks(items);
  const totalPages = Math.max(Math.ceil(filteredItems.length / state.chunkPageSize), 1);
  state.chunkPage = Math.min(Math.max(state.chunkPage, 1), totalPages);
  const start = (state.chunkPage - 1) * state.chunkPageSize;
  return filteredItems.slice(start, start + state.chunkPageSize);
}

function updateSelectedChunkCount() {
  // 维护切块勾选数量和表头全选状态。
  if (!$("selectedChunkCount")) return;
  const visibleIds = visibleImportChunks().map((item) => item.id);
  const selectedVisibleCount = visibleIds.filter((id) => state.selectedImportChunks.has(id)).length;
  $("selectedChunkCount").textContent = `已选择 ${state.selectedImportChunks.size} 块`;
  const selectAll = $("selectAllChunks");
  if (!selectAll) return;
  selectAll.checked = visibleIds.length > 0 && selectedVisibleCount === visibleIds.length;
  selectAll.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleIds.length;
}

function renderChunkPreview(chunk = state.currentImportChunk) {
  // 选择切块后展示原始切片内容，先让用户判断是否值得生成 FAQ。
  if (!$("chunkPreviewPanel")) return;
  const hasChunk = Boolean(chunk);
  $("chunkPreviewTitle").textContent = hasChunk
    ? `解析块 ${chunkDisplayName(chunk.id)}`
    : "请选择解析块";
  $("chunkPreviewMeta").textContent = hasChunk
    ? `${contentUnitLabel(chunk.message_count || 0)} / ${chunk.candidate_count || 0} 条候选 / ${importChunkStatusText(chunk.status)}`
    : "点击上方解析块后查看原始切片内容。";
  $("chunkPreviewText").textContent = hasChunk
    ? (chunk.source_text || "当前切片没有可展示内容")
    : "解析块内容将在这里展示。不是每个切片都需要生成 FAQ，请先阅读内容再决定是否识别。";
  $("generateCurrentChunkButton").disabled = !hasChunk;
  $("viewChunkCandidatesButton").disabled = !hasChunk;
}

function importChunkStatusText(status) {
  // 原始切片预览里展示短状态文案，避免把状态色块放进正文区域。
  const labels = {
    pending: "待识别",
    processing: "识别中",
    generated: "已生成",
    failed: "失败",
  };
  return labels[status] || status || "待识别";
}

function selectImportChunk(chunkId) {
  // 选择切块后展示原始切片内容，候选 FAQ 跳转由用户显式触发。
  state.currentImportChunk = state.importChunks.find((item) => item.id === chunkId) || null;
  state.currentCandidateIndex = 0;
  renderImportChunks(state.importChunks);
  renderChunkPreview(state.currentImportChunk);
  renderGenerationProgress();
}

async function viewCurrentChunkCandidates() {
  // 用户确认要看当前切片候选时，再切到候选 FAQ 视图并按来源筛选。
  if (!state.currentImportChunk) {
    showToast("请先选择解析块");
    return;
  }
  setCandidateChunkFilter(state.currentImportChunk);
  closeCandidateDrawer();
  await switchImportView("candidates", { keepCandidateChunkFilter: true });
}

async function loadImportCandidates(chunkId, options = {}) {
  // 载入切块下的候选 FAQ。
  try {
    const data = await requestJson(`/api/import/chunks/${encodeURIComponent(chunkId)}/candidates`);
    state.importCandidates = data.items || [];
    const requestedIndex = options.index ?? 0;
    state.currentCandidateIndex = Math.min(
      requestedIndex,
      Math.max(state.importCandidates.length - 1, 0),
    );
    renderImportCandidateList();
    if ($("candidateDrawer").classList.contains("open")) renderCurrentCandidate();
  } catch (error) {
    showToast(error.message);
  }
}

async function loadImportFileCandidates(fileId, options = {}) {
  // 载入当前文件下全部候选 FAQ，支撑候选 FAQ 审核工作台。
  try {
    const data = await requestJson(`/api/import/files/${encodeURIComponent(fileId)}/candidates`);
    state.importCandidates = data.items || [];
    state.selectedImportCandidates.clear();
    const requestedIndex = options.index ?? state.currentCandidateIndex ?? 0;
    state.currentCandidateIndex = Math.min(
      requestedIndex,
      Math.max(state.importCandidates.length - 1, 0),
    );
    renderImportOverview(state.currentImportFile, state.importChunks);
    renderImportCandidateList();
    if ($("candidateDrawer").classList.contains("open")) renderCurrentCandidate();
  } catch (error) {
    showToast(error.message);
  }
}

function candidateStatusPill(value) {
  // 候选状态使用中文标签，保持审核语义比数据库值更直观。
  const labels = { pending: "待审核", saved: "已保存", ignored: "已忽略" };
  const classes = { pending: "needs_review", saved: "ready", ignored: "disabled" };
  const status = value || "pending";
  return `<span class="status-pill ${classes[status] || "pending"}">${labels[status] || escapeHtml(status)}</span>`;
}

function duplicateLevelLabel(value) {
  // 将查重级别转成审核人员能直接判断的中文标签。
  const labels = { high: "高度重复", medium: "疑似重复", low: "低重复", none: "未重复" };
  return labels[value || "none"] || "未重复";
}

function candidateScopeItems() {
  // 候选审核范围优先受来源块约束，未指定来源块时才查看当前文件全部候选。
  if (!state.candidateChunkFilter) return state.importCandidates;
  return state.importCandidates.filter((item) => item.chunk_id === state.candidateChunkFilter.id);
}

function renderCandidateFilterOptions() {
  // 根据当前来源范围刷新候选筛选项，避免下拉中出现无结果分类。
  const select = $("candidateCategorySelect");
  if (!select) return;
  const categories = Array.from(
    new Set(candidateScopeItems().map((item) => item.category).filter(Boolean)),
  );
  select.innerHTML = [
    '<option value="">全部</option>',
    ...categories.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`),
  ].join("");
  if (!categories.includes(state.candidateCategory)) state.candidateCategory = "";
  select.value = state.candidateCategory;
}

function filteredImportCandidates() {
  // 候选 FAQ 视图只做轻量搜索和状态筛选，避免小团队审核入口过重。
  return candidateScopeItems().filter((item) => {
    const query = state.candidateQuery.trim();
    const matchesQuery =
      !query ||
      String(item.question || "").includes(query) ||
      String(item.answer || "").includes(query) ||
      String(item.category || "").includes(query);
    const matchesStatus = !state.candidateStatus || item.status === state.candidateStatus;
    const matchesCategory = !state.candidateCategory || item.category === state.candidateCategory;
    const matchesConfidence =
      !state.candidateConfidence || (item.confidence || "medium") === state.candidateConfidence;
    const matchesDuplicate =
      !state.candidateDuplicate || (item.duplicate_level || "none") === state.candidateDuplicate;
    const matchesPending = !state.candidateOnlyPending || item.status === "pending";
    return matchesQuery
      && matchesStatus
      && matchesCategory
      && matchesConfidence
      && matchesDuplicate
      && matchesPending;
  });
}

function updateSelectedCandidateCount() {
  // 维护候选 FAQ 批量操作选择数量和按钮可用状态。
  if (!$("selectedCandidateCount")) return;
  const visibleIds = filteredImportCandidates().map((item) => item.id);
  const selectedVisibleCount = visibleIds.filter((id) => state.selectedImportCandidates.has(id)).length;
  const selectedCount = state.selectedImportCandidates.size;
  $("selectedCandidateCount").textContent = `已选择 ${selectedCount} 条`;
  $("batchSaveCandidatesButton").disabled = selectedCount === 0;
  $("batchIgnoreCandidatesButton").disabled = selectedCount === 0;
  const selectAll = $("selectAllCandidates");
  if (!selectAll) return;
  selectAll.checked = visibleIds.length > 0 && selectedVisibleCount === visibleIds.length;
  selectAll.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleIds.length;
}

function renderCandidateCounts() {
  // 统一刷新候选列表和审核抽屉使用的状态统计。
  const scopedCandidates = candidateScopeItems();
  const visibleCandidates = filteredImportCandidates();
  $("candidateIndex").textContent = visibleCandidates.length
    ? `${state.currentCandidateIndex + 1} / ${visibleCandidates.length}`
    : "0 / 0";
  $("candidatePendingCount").textContent = scopedCandidates.filter((item) => item.status === "pending").length;
  $("candidateSavedCount").textContent = scopedCandidates.filter((item) => item.status === "saved").length;
  $("candidateIgnoredCount").textContent = scopedCandidates.filter((item) => item.status === "ignored").length;
  const hasCandidate = visibleCandidates.length > 0;
  $("prevCandidate").disabled = state.currentCandidateIndex <= 0 || !hasCandidate;
  $("nextCandidate").disabled =
    !hasCandidate || state.currentCandidateIndex >= visibleCandidates.length - 1;
  $("saveCandidateButton").disabled = !hasCandidate;
  $("ignoreCandidateButton").disabled = !hasCandidate;
  $("rewriteCandidateButton").disabled = !hasCandidate;
  $("viewCandidateSourceButton").disabled = !hasCandidate;
}

function currentVisibleCandidate() {
  // 返回当前筛选范围内正在审核的候选 FAQ，所有单条动作都必须尊重来源块筛选。
  return filteredImportCandidates()[state.currentCandidateIndex] || null;
}

function renderImportCandidateList(message = "") {
  // 在主工作区显示文件级候选摘要，用户点击行或审核按钮后打开右侧抽屉。
  renderCandidateFilterOptions();
  const candidates = filteredImportCandidates();
  const scopedCandidates = candidateScopeItems();
  state.currentCandidateIndex = Math.min(
    state.currentCandidateIndex,
    Math.max(candidates.length - 1, 0),
  );
  renderCandidateCounts();
  updateSelectedCandidateCount();
  renderImportOverview(state.currentImportFile, state.importChunks);
  renderGenerationProgress();
  if (!state.currentImportFile) {
    $("candidateListSummary").textContent = message || "请选择文件后查看候选 FAQ";
    $("fileCandidateList").innerHTML =
      '<tr><td colspan="9" class="empty">请选择文件后查看候选 FAQ</td></tr>';
    $("candidateList").innerHTML = "";
    return;
  }
  const sourceCopy = state.candidateChunkFilter ? `${state.candidateChunkFilter.label} · ` : "";
  $("candidateListSummary").textContent = scopedCandidates.length
    ? `${sourceCopy}当前范围 ${scopedCandidates.length} 条候选，筛选后 ${candidates.length} 条；保存后会同步生成 embedding。`
    : message || "当前文件暂无候选 FAQ，可先在解析块中自动识别";
  if (!candidates.length) {
    $("fileCandidateList").innerHTML =
      '<tr><td colspan="9" class="empty">当前筛选下暂无候选 FAQ</td></tr>';
    $("candidateList").innerHTML = "";
    return;
  }
  const rows = candidates
    .map((item, index) => {
      const active = index === state.currentCandidateIndex ? "selected" : "";
      const checked = state.selectedImportCandidates.has(item.id) ? "checked" : "";
      return `
        <tr class="${active}" data-import-candidate-index="${index}">
          <td><input type="checkbox" class="candidate-check" data-id="${escapeHtml(item.id)}" ${checked}></td>
          <td>${candidateStatusPill(item.status)}</td>
          <td class="candidate-question-cell" title="${escapeHtml(item.question || "")}">${escapeHtml(item.question || "-")}</td>
          <td>${escapeHtml(item.category || "-")}</td>
          <td>${escapeHtml(duplicateLevelLabel(item.duplicate_level))}</td>
          <td>${escapeHtml(item.confidence || "medium")}</td>
          <td>${item.chunk_index ? `#${escapeHtml(item.chunk_index)}` : "-"}</td>
          <td>${formatDate(item.updated_at || item.created_at)}</td>
          <td><button class="candidate-review-button" type="button" data-import-candidate-index="${index}">审核</button></td>
        </tr>
      `;
    })
    .join("");
  $("fileCandidateList").innerHTML = rows;
  $("candidateList").innerHTML = rows;
  updateSelectedCandidateCount();
}

function renderCurrentCandidate() {
  // 渲染侧滑抽屉中的当前候选 FAQ 表单和状态统计。
  const current = currentVisibleCandidate();
  renderCandidateCounts();
  if (!current) {
    renderCandidateEmpty("请选择切块或生成候选 FAQ");
    return;
  }
  $("candidateQuestion").value = current.question || "";
  $("candidateAnswer").value = current.answer || "";
  $("candidateCategory").value = current.category || "";
  $("candidateInternalNote").value = current.internal_note || "";
  $("candidateSource").textContent = current.source_excerpt || state.currentImportChunk?.source_text || "";
  renderCandidateDuplicate(current);
  state.candidateVariants = current.similar_questions || [];
  state.candidateTags = current.tags || [];
  renderCandidateChips();
  renderCandidateConfidence(current.confidence || "medium");
}

function syncDrawerBackdrop() {
  // 两个详情抽屉共用一个透明遮罩，只在任一抽屉打开时接管外部点击。
  const backdrop = $("drawerBackdrop");
  const faqDrawer = $("drawer");
  const candidateDrawer = $("candidateDrawer");
  if (!backdrop) return;
  const isOpen =
    Boolean(faqDrawer?.classList.contains("open")) ||
    Boolean(candidateDrawer?.classList.contains("open"));
  backdrop.classList.toggle("open", isOpen);
  backdrop.setAttribute("aria-hidden", isOpen ? "false" : "true");
}

function openCandidateDrawer(index = state.currentCandidateIndex) {
  // 打开候选 FAQ 审核抽屉，避免详情常驻占用主工作区。
  const candidates = filteredImportCandidates();
  if (!candidates.length) {
    showToast("当前文件暂无候选 FAQ");
    return;
  }
  state.currentCandidateIndex = Math.min(index, candidates.length - 1);
  renderCurrentCandidate();
  renderImportCandidateList();
  $("candidateDrawer").classList.add("open");
  $("candidateDrawer").setAttribute("aria-hidden", "false");
  syncDrawerBackdrop();
}

function closeCandidateDrawer() {
  // 关闭候选审核抽屉，不影响当前切块和候选列表选择。
  const candidateDrawer = $("candidateDrawer");
  if (!candidateDrawer) return;
  candidateDrawer.classList.remove("open");
  candidateDrawer.setAttribute("aria-hidden", "true");
  syncDrawerBackdrop();
}

function renderCandidateEmpty(message) {
  // 清空右侧候选表单并显示当前状态。
  $("candidateQuestion").value = "";
  $("candidateAnswer").value = "";
  $("candidateCategory").value = "";
  $("candidateInternalNote").value = "";
  $("candidateSource").textContent = message;
  renderCandidateDuplicate({ duplicate_level: "none", duplicate_score: 0 });
  state.candidateVariants = [];
  state.candidateTags = [];
  renderCandidateChips();
  renderCandidateConfidence("medium");
}

function renderCandidateChips() {
  // 渲染候选 FAQ 的相似问法和标签。
  $("candidateVariantChips").innerHTML = state.candidateVariants
    .map((item) => chipHtml(item, "candidateVariants"))
    .join("");
  $("candidateTagChips").innerHTML = state.candidateTags
    .map((item) => chipHtml(item, "candidateTags"))
    .join("");
}

function renderCandidateConfidence(value) {
  // 将文本置信度映射成图中进度条样式。
  const score = value === "high" ? 86 : value === "low" ? 35 : 62;
  $("candidateConfidenceValue").textContent = value;
  $("candidateConfidenceBar").style.width = `${score}%`;
  $("candidateConfidencePercent").textContent = `${score}%`;
  $("candidateConfidenceMirror").textContent = value;
  $("candidateConfidenceMirrorBar").style.width = `${score}%`;
}

function renderCandidateDuplicate(candidate) {
  // 重复度只表示与已有知识的重复风险，不作为业务重要性评分。
  const score = Math.round((candidate?.duplicate_score || 0) * 100);
  $("candidateDuplicateLevel").textContent = `${duplicateLevelLabel(candidate?.duplicate_level)} ${score}%`;
  $("candidateDuplicatePercent").textContent = `${score}%`;
  $("candidateDuplicateBar").style.width = `${score}%`;
}

function collectCandidatePayload() {
  // 收集右侧候选 FAQ 人工编辑后的字段。
  return {
    question: $("candidateQuestion").value,
    answer: $("candidateAnswer").value,
    similar_questions: state.candidateVariants,
    category: $("candidateCategory").value,
    tags: state.candidateTags,
    confidence: $("candidateConfidenceValue").textContent || "medium",
    internal_note: $("candidateInternalNote").value,
  };
}

async function generateCandidatesForCurrentChunk() {
  // 对当前选中切块生成候选 FAQ。
  const chunk = state.currentImportChunk;
  if (!chunk) {
    showToast("请先选择解析块");
    return;
  }
  try {
    const result = await requestJson(`/api/import/chunks/${encodeURIComponent(chunk.id)}/generate`, {
      method: "POST",
      body: "{}",
    });
    state.importCandidates = result.items || [];
    state.currentCandidateIndex = 0;
    showToast(`已生成 ${state.importCandidates.length} 条候选，可点击“查看此切片候选”审核`);
    await loadImportChunks(state.currentImportFile.id);
    state.currentImportChunk = state.importChunks.find((item) => item.id === chunk.id) || chunk;
    renderImportChunks(state.importChunks);
    renderChunkPreview(state.currentImportChunk);
    renderImportCandidateList();
    closeCandidateDrawer();
  } catch (error) {
    showToast(error.message);
  }
}

async function generateCandidatesForSelectedChunks() {
  // 批量生成候选 FAQ：优先处理勾选切块，没有勾选时处理当前切块。
  const chunkIds = state.selectedImportChunks.size
    ? Array.from(state.selectedImportChunks)
    : state.currentImportChunk
      ? [state.currentImportChunk.id]
      : [];
  if (!chunkIds.length) {
    showToast("请先选择解析块");
    return;
  }
  try {
    $("generateChunkCandidatesButton").disabled = true;
    const job = await requestJson("/api/import/generation-jobs", {
      method: "POST",
      body: JSON.stringify({ chunk_ids: chunkIds }),
    });
    startGenerationJob(job);
  } catch (error) {
    $("generateChunkCandidatesButton").disabled = false;
    showToast(error.message);
  }
}

function startGenerationJob(job) {
  // 创建任务后通过 SSE 持续接收每个切块的生成状态。
  state.generationEvents = [];
  state.generationItems = {};
  state.generationJob = { id: job.id, total: (job.items || []).length, status: "running" };
  state.generationFocusText = "当前：等待开始";
  (job.items || []).forEach((item) => {
    state.generationItems[item.chunk_id] = {
      chunk_id: item.chunk_id,
      status: item.status || "queued",
      reason: item.reason || "",
      candidate_count: item.candidate_count || 0,
    };
  });
  $("generationProgress").classList.remove("hidden");
  $("generationProgress").classList.add("running");
  $("generationProgressText").textContent =
    `任务 ${job.id} 已创建，共 ${state.generationJob.total} 块，按顺序生成`;
  renderGenerationProgress();
  const source = new EventSource(`/api/import/generation-jobs/${encodeURIComponent(job.id)}/events`);
  source.addEventListener("processing", (event) => handleGenerationEvent(JSON.parse(event.data)));
  source.addEventListener("generated", (event) => handleGenerationEvent(JSON.parse(event.data)));
  source.addEventListener("skipped", (event) => handleGenerationEvent(JSON.parse(event.data)));
  source.addEventListener("failed", (event) => handleGenerationEvent(JSON.parse(event.data)));
  source.addEventListener("done", async (event) => {
    handleGenerationEvent(JSON.parse(event.data));
    source.close();
    $("generateChunkCandidatesButton").disabled = false;
    state.selectedImportChunks.clear();
    await loadImportChunks(state.currentImportFile.id);
    if (state.importView === "candidates") await loadImportFileCandidates(state.currentImportFile.id);
    else renderImportCandidateList();
    closeCandidateDrawer();
  });
  source.onerror = () => {
    source.close();
    $("generateChunkCandidatesButton").disabled = false;
    showToast("生成任务连接中断");
  };
}

function handleGenerationEvent(event) {
  // 合并服务端进度事件并刷新任务级进度，不把 done 当成切块事件重复展示。
  if (event.chunk_id) {
    const current = state.generationItems[event.chunk_id] || { chunk_id: event.chunk_id };
    state.generationItems[event.chunk_id] = {
      ...current,
      status: event.type,
      reason: event.reason || current.reason || "",
      candidate_count: event.candidate_count ?? current.candidate_count ?? 0,
      error: event.error || "",
    };
  }
  if (event.type === "processing") {
    state.generationFocusText = `当前：${chunkDisplayName(event.chunk_id)}`;
    $("generationProgressText").textContent = `正在生成 ${chunkDisplayName(event.chunk_id)}`;
    $("generationCurrentIndex").textContent = chunkDisplayName(event.chunk_id);
  } else if (event.type === "generated") {
    state.generationFocusText = `刚完成：${chunkDisplayName(event.chunk_id)}`;
    $("generationProgressText").textContent =
      `${chunkDisplayName(event.chunk_id)} 已生成 ${event.candidate_count || 0} 条候选`;
  } else if (event.type === "skipped") {
    state.generationFocusText = `已跳过：${chunkDisplayName(event.chunk_id)}`;
    $("generationProgressText").textContent =
      `${chunkDisplayName(event.chunk_id)} 已跳过：${event.reason || "-"}`;
  } else if (event.type === "failed") {
    state.generationFocusText = `失败：${chunkDisplayName(event.chunk_id)}`;
    $("generationProgressText").textContent = `${chunkDisplayName(event.chunk_id)} 生成失败`;
  } else if (event.type === "done") {
    state.generationJob = { ...(state.generationJob || {}), status: "completed" };
    state.generationFocusText = "任务完成";
    $("generationProgressText").textContent = "任务完成";
    $("generationProgress").classList.remove("running");
  }
  renderGenerationProgress();
}

function renderGenerationProgress() {
  // 用进度条和聚合卡片展示解析块处理状态。
  if (state.importView === "candidates") {
    renderCandidateAuditProgress();
    return;
  }
  $("generationProgress").classList.remove("candidate-audit-mode");
  $("progressPanelTitle").textContent = "解析与生成进度";
  $("progressMainLabel").textContent = "整体进度";
  $("progressCurrentLabel").textContent = "当前处理块";
  const jobItems = Object.values(state.generationItems);
  const chunks = state.importChunks || [];
  const focusChunk = progressFocusChunk(chunks);
  const total = state.generationJob?.total || chunks.length || jobItems.length;
  const generated = jobItems.length
    ? jobItems.filter((item) => item.status === "generated").length
    : chunks.filter((item) => item.status === "generated").length;
  const skipped = jobItems.filter((item) => item.status === "skipped").length;
  const failed = jobItems.length
    ? jobItems.filter((item) => item.status === "failed").length
    : chunks.filter((item) => item.status === "failed").length;
  const processing = jobItems.filter((item) => item.status === "processing").length;
  const pending = Math.max(total - generated - failed - processing - skipped, 0);
  const completed = generated + skipped + failed;
  const percent = total ? Math.round((completed / total) * 100) : 0;
  setProgressPercent(percent, { reset: state.progressResetOnNextRender });
  state.progressResetOnNextRender = false;
  $("generationProgressRatio").textContent = `${percent}%`;
  $("generationCurrentIndex").textContent = focusChunk ? `#${focusChunk.chunk_index || "-"}` : "-";
  const currentStatus = processing ? "processing" : focusChunk?.status || "pending";
  const statusLabels = {
    queued: "待解析",
    pending: "待审核",
    processing: "解析中",
    generated: "已完成",
    skipped: "已完成",
    failed: "解析失败",
  };
  const statusClasses = {
    queued: "queued",
    pending: "needs_review",
    processing: "processing",
    generated: "generated",
    skipped: "skipped",
    failed: "failed",
  };
  $("generationCurrentStatus").textContent = statusLabels[currentStatus] || currentStatus;
  $("generationCurrentStatus").className =
    `status-pill ${statusClasses[currentStatus] || safeCssToken(currentStatus)}`;
  $("generationCurrentChunk").textContent =
    state.generationJob?.status === "running" && state.generationFocusText
      ? state.generationFocusText
      : chunkKeywordSummary(focusChunk);
  $("generationCurrentBar").style.width = processing ? "32%" : percent ? `${percent}%` : "0%";
  $("generationEstimate").textContent = state.generationJob?.status === "running" ? "计算中" : "--";
  $("generationLastUpdated").textContent = formatDate(new Date().toISOString()).slice(11) || "--";
  $("generationCurrentEta").textContent = processing ? "预计剩余 计算中" : "预计剩余 --";
  $("generationProgressItems").innerHTML = [
    ["pending", "待解析", pending],
    ["processing", "解析中", processing],
    ["skipped", "待审核", pending + skipped],
    ["generated", "已完成", generated],
    ["failed", "失败", failed],
  ]
    .map(
      ([status, label, count]) =>
        `<span class="generation-progress-item ${statusPillClass(status)}">${escapeHtml(label)}<b>${escapeHtml(count)}</b></span>`,
    )
    .join("");
  if (state.progressCardsAnimateOnNextRender) {
    animatePanelCards(".generation-progress-item");
    state.progressCardsAnimateOnNextRender = false;
  }
}

function renderCandidateAuditProgress() {
  // 候选 FAQ 是人工审核，不展示耗时估算，只复用进度框展示审核状态。
  const scopedCandidates = candidateScopeItems();
  const visibleCandidates = filteredImportCandidates();
  const total = scopedCandidates.length;
  const saved = scopedCandidates.filter((item) => item.status === "saved").length;
  const ignored = scopedCandidates.filter((item) => item.status === "ignored").length;
  const pending = scopedCandidates.filter((item) => item.status === "pending").length;
  const lowConfidence = scopedCandidates.filter((item) => item.confidence === "low").length;
  const current = visibleCandidates[state.currentCandidateIndex] || visibleCandidates[0] || null;
  const percent = total ? Math.round(((saved + ignored) / total) * 100) : 0;
  $("generationProgress").classList.remove("running");
  $("generationProgress").classList.add("candidate-audit-mode");
  $("progressPanelTitle").textContent = "候选 FAQ 审核进度";
  $("progressMainLabel").textContent = "审核进度";
  $("progressCurrentLabel").textContent = "当前审核项";
  $("generationProgressText").textContent = "人工审核";
  setProgressPercent(percent, { reset: state.progressResetOnNextRender });
  state.progressResetOnNextRender = false;
  $("generationProgressRatio").textContent = `${percent}%`;
  $("generationCurrentIndex").textContent = current
    ? `#${current.chunk_index || state.currentCandidateIndex + 1}`
    : "-";
  const currentStatus = current?.status || "pending";
  const statusLabels = { pending: "待审核", saved: "已保存", ignored: "已忽略" };
  const statusClasses = { pending: "needs_review", saved: "generated", ignored: "skipped" };
  $("generationCurrentStatus").textContent = statusLabels[currentStatus] || currentStatus;
  $("generationCurrentStatus").className =
    `status-pill ${statusClasses[currentStatus] || safeCssToken(currentStatus)}`;
  $("generationCurrentChunk").textContent = current
    ? `${current.category || "-"}${current.question ? ` / ${current.question}` : ""}`
    : "当前筛选下暂无候选 FAQ";
  $("generationCurrentBar").style.width = `${percent}%`;
  $("generationEstimate").textContent = "--";
  $("generationLastUpdated").textContent = formatDate(new Date().toISOString()).slice(11) || "--";
  $("generationCurrentEta").textContent = "";
  $("generationProgressItems").innerHTML = [
    ["pending", "待审核", pending],
    ["processing", "审核中", current ? 1 : 0],
    ["generated", "已保存", saved],
    ["skipped", "已忽略", ignored],
    ["low", "低置信度", lowConfidence],
  ]
    .map(
      ([status, label, count]) =>
        `<span class="generation-progress-item ${statusPillClass(status)}">${escapeHtml(label)}<b>${escapeHtml(count)}</b></span>`,
    )
    .join("");
  if (state.progressCardsAnimateOnNextRender) {
    animatePanelCards(".generation-progress-item");
    state.progressCardsAnimateOnNextRender = false;
  }
}

async function reparseCurrentImportFile() {
  // 按用户选择的解析模式和天数重新切分当前文件。
  const file = state.currentImportFile;
  if (!file) {
    showToast("请先选择导入文件");
    return;
  }
  const chunkDays = Math.min(Math.max(Number($("chunkDaysInput").value || 1), 1), 7);
  $("chunkDaysInput").value = String(chunkDays);
  try {
    $("reparseImportButton").disabled = true;
    await requestJson(`/api/import/files/${encodeURIComponent(file.id)}/reparse`, {
      method: "POST",
      body: JSON.stringify({
        parse_mode: $("parseModeSelect").value,
        chunk_days: chunkDays,
      }),
    });
    showToast("已重新解析文件");
    state.selectedImportChunks.clear();
    state.chunkPage = 1;
    await loadImportFiles();
    await selectImportFile(file.id);
  } catch (error) {
    showToast(error.message);
  } finally {
    $("reparseImportButton").disabled = false;
  }
}

async function saveCurrentCandidate() {
  // 先保存人工编辑，再写入标准问答并生成 embedding。
  const current = currentVisibleCandidate();
  if (!current) return;
  const index = state.currentCandidateIndex;
  try {
    await requestJson(`/api/import/candidates/${encodeURIComponent(current.id)}`, {
      method: "POST",
      body: JSON.stringify(collectCandidatePayload()),
    });
    await requestJson(`/api/import/candidates/${encodeURIComponent(current.id)}/save`, {
      method: "POST",
      body: "{}",
    });
    showToast("已保存到标准问答并生成 embedding");
    await loadImportFileCandidates(current.file_id || state.currentImportFile.id, { index });
    openCandidateDrawer(state.currentCandidateIndex);
  } catch (error) {
    showToast(error.message);
  }
}

async function ignoreCurrentCandidate() {
  // 忽略不适合沉淀为标准问答的候选。
  const current = currentVisibleCandidate();
  if (!current) return;
  const index = state.currentCandidateIndex;
  try {
    await requestJson(`/api/import/candidates/${encodeURIComponent(current.id)}/ignore`, {
      method: "POST",
      body: "{}",
    });
    showToast("已忽略候选 FAQ");
    await loadImportFileCandidates(current.file_id || state.currentImportFile.id, { index });
    openCandidateDrawer(state.currentCandidateIndex);
  } catch (error) {
    showToast(error.message);
  }
}

async function saveSelectedCandidates() {
  // 批量保存当前选中的候选 FAQ，每条保存后由后端立即生成 embedding。
  const ids = Array.from(state.selectedImportCandidates);
  if (!ids.length) {
    showToast("请先选择候选 FAQ");
    return;
  }
  try {
    $("batchSaveCandidatesButton").disabled = true;
    for (const id of ids) {
      const candidate = state.importCandidates.find((item) => item.id === id);
      if (!candidate || candidate.status !== "pending") continue;
      await requestJson(`/api/import/candidates/${encodeURIComponent(id)}/save`, {
        method: "POST",
        body: "{}",
      });
    }
    showToast(`已处理 ${ids.length} 条候选`);
    await loadImportFileCandidates(state.currentImportFile.id);
  } catch (error) {
    showToast(error.message);
  } finally {
    $("batchSaveCandidatesButton").disabled = false;
    updateSelectedCandidateCount();
  }
}

async function ignoreSelectedCandidates() {
  // 批量忽略当前选中的候选 FAQ。
  const ids = Array.from(state.selectedImportCandidates);
  if (!ids.length) {
    showToast("请先选择候选 FAQ");
    return;
  }
  try {
    $("batchIgnoreCandidatesButton").disabled = true;
    for (const id of ids) {
      const candidate = state.importCandidates.find((item) => item.id === id);
      if (!candidate || candidate.status !== "pending") continue;
      await requestJson(`/api/import/candidates/${encodeURIComponent(id)}/ignore`, {
        method: "POST",
        body: "{}",
      });
    }
    showToast(`已忽略 ${ids.length} 条候选`);
    await loadImportFileCandidates(state.currentImportFile.id);
  } catch (error) {
    showToast(error.message);
  } finally {
    $("batchIgnoreCandidatesButton").disabled = false;
    updateSelectedCandidateCount();
  }
}

async function rewriteCurrentCandidate() {
  // 用 AI 对当前候选 FAQ 做保守改写，只回填表单，不自动保存。
  const current = currentVisibleCandidate();
  if (!current) return;
  const question = $("candidateQuestion").value.trim();
  const answer = $("candidateAnswer").value.trim();
  if (!question || !answer) {
    showToast("请先补全候选问题和答案");
    return;
  }
  try {
    $("rewriteCandidateButton").disabled = true;
    $("rewriteCandidateButton").textContent = "改写中";
    const suggestion = await requestJson("/api/ai/optimize", {
      method: "POST",
      body: JSON.stringify({ question, answer }),
    });
    $("candidateQuestion").value = suggestion.optimized_question || question;
    $("candidateAnswer").value = suggestion.optimized_answer || answer;
    state.candidateVariants = suggestion.similar_questions || state.candidateVariants;
    renderCandidateChips();
    showToast("AI 改写已回填，保存前可继续编辑");
  } catch (error) {
    showToast(error.message);
  } finally {
    $("rewriteCandidateButton").textContent = "✧ 应用 AI 改写";
    renderCandidateCounts();
  }
}

function focusCurrentCandidateSource() {
  // 将审核抽屉滚动到来源片段，并短暂高亮证据区域。
  if (!currentVisibleCandidate()) {
    showToast("请选择候选 FAQ");
    return;
  }
  const source = $("candidateSource");
  source.scrollIntoView({ block: "center", behavior: "smooth" });
  source.classList.add("source-box-highlight");
  window.setTimeout(() => source.classList.remove("source-box-highlight"), 1200);
}

function renderFilters(data) {
  $("statusFilters").innerHTML =
    filterItem("status", "", "全部", data.total, state.status) +
    statusOptions
      .map((item) => filterItem("status", item, item, data.status_counts?.[item], state.status))
      .join("");

  $("embeddingFilters").innerHTML =
    filterItem("embedding", "", "全部", data.total, state.embeddingStatus) +
    embeddingOptions
      .map((item) =>
        filterItem("embedding", item, item, data.embedding_counts?.[item], state.embeddingStatus),
      )
      .join("");

  $("failedCount").textContent = data.embedding_counts?.failed || 0;
}

function renderRows(items) {
  const rows = items
    .map((item, index) => {
      const rowNumber = (state.page - 1) * state.pageSize + index + 1;
      const selected = state.selected.has(item.id) ? "checked" : "";
      const active = state.current?.id === item.id ? "selected" : "";
      return `
        <tr class="${active}" data-id="${escapeHtml(item.id)}">
          <td><input type="checkbox" class="row-check" data-id="${escapeHtml(item.id)}" ${selected}></td>
          <td class="row-index">${rowNumber}</td>
          <td title="${escapeHtml(item.question || "")}">${escapeHtml(item.question || "")}</td>
          <td>${escapeHtml(item.category || "-")}</td>
          <td>${statusPill(item.status)}</td>
          <td>${statusPill(item.embedding_status)}</td>
          <td>${formatDate(item.updated_at)}</td>
        </tr>
      `;
    })
    .join("");
  $("faqRows").innerHTML = rows || `<tr><td colspan="7" class="empty">暂无数据</td></tr>`;
}

async function loadFaqs() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  if (state.query) params.set("query", state.query);
  if (state.status) params.set("status", state.status);
  if (state.embeddingStatus) params.set("embedding_status", state.embeddingStatus);

  try {
    const data = await requestJson(`/api/faqs?${params.toString()}`);
    renderKnowledgeFaqSummary(data);
    renderFilters(data);
    renderRows(data.items || []);
    $("totalCount").textContent = `共 ${data.total || 0} 条`;
    $("pageSummary").textContent = `共 ${data.total || 0} 条`;
    $("pageNumber").textContent = String(data.page || 1);
    $("selectAll").checked = false;
    updateSelectedCount();
  } catch (error) {
    showToast(error.message);
  }
}

function openDrawer(record = null) {
  // 打开标准问答编辑抽屉，关闭态不占页面宽度，只在 open 状态显示。
  state.current = record;
  state.dirty = false;
  state.aiSuggestion = null;
  state.variants = record?.question_variants || [];
  state.tags = record?.tags || [];

  $("drawerTitle").textContent = record ? "编辑问答" : "新建问答";
  $("faqId").value = record?.id || "";
  $("questionInput").value = record?.question || "";
  $("answerInput").value = record?.answer || "";
  $("categoryInput").value = record?.category || "";
  $("faqInternalNote").value = record?.internal_note || "";
  $("statusInput").value = record?.status || "usable";
  $("aiPanel").classList.add("hidden");
  renderChips();
  renderFaqSource(record);
  renderEmbeddingState(record?.embedding_status || "pending", record?.embedding_error || "");
  $("drawer").classList.add("open");
  $("drawer").setAttribute("aria-hidden", "false");
  syncDrawerBackdrop();
}

function closeDrawer({ force = false } = {}) {
  // 关闭标准问答抽屉；外部点击可强制关闭，按钮关闭仍保留未保存确认。
  const drawer = $("drawer");
  if (!drawer?.classList.contains("open")) {
    syncDrawerBackdrop();
    return;
  }
  if (!force && state.dirty && !window.confirm("有未保存改动，确认关闭？")) return;
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  state.current = null;
  state.dirty = false;
  syncDrawerBackdrop();
}

function renderEmbeddingState(status, error) {
  const dot = $("embeddingStatusDot");
  const text = $("embeddingStatusText");
  const hint = $("embeddingStatusHint");
  text.textContent = status;
  dot.style.background =
    status === "ready" ? "#16a34a" : status === "failed" ? "#ef4444" : "#f97316";
  hint.textContent =
    status === "ready"
      ? "可进入向量检索"
      : status === "stale"
        ? "正文已修改，需要重新生成 embedding"
        : status === "failed"
          ? error || "生成失败，可重试"
          : "未生成 embedding";
}

function renderFaqSource(record) {
  // 在标准问答编辑抽屉中展示来源证据，和候选审核保持同一信息层级。
  const evidence = record?.evidence || [];
  if (!evidence.length) {
    $("faqSourceBox").textContent = record?.source_file ? `来源文件：${record.source_file}` : "暂无来源证据";
    return;
  }
  $("faqSourceBox").textContent = evidence
    .map((item) => {
      const source = item.source_file || record?.source_file || "-";
      const chunk = item.chunk_id ? ` / ${item.chunk_id}` : "";
      const excerpt = item.excerpt ? `\n${item.excerpt}` : "";
      return `${source}${chunk}${excerpt}`;
    })
    .join("\n\n");
}

function chipHtml(value, group) {
  return `<span class="chip">${escapeHtml(value)}<button type="button" data-group="${group}" data-value="${escapeHtml(value)}">×</button></span>`;
}

function renderChips() {
  $("variantChips").innerHTML = state.variants.map((item) => chipHtml(item, "variants")).join("");
  $("tagChips").innerHTML = state.tags.map((item) => chipHtml(item, "tags")).join("");
}

function addChip(group, value) {
  const text = value.trim();
  if (!text) return;
  const target = group === "variants" ? state.variants : state.tags;
  if (!target.includes(text)) target.push(text);
  state.dirty = true;
  renderChips();
}

function addCandidateChip(group, value) {
  // 给候选 FAQ 添加相似问法或标签。
  const text = value.trim();
  if (!text) return;
  const target = group === "candidateVariants" ? state.candidateVariants : state.candidateTags;
  if (!target.includes(text)) target.push(text);
  renderCandidateChips();
}

function collectForm() {
  return {
    id: $("faqId").value || undefined,
    question: $("questionInput").value,
    answer: $("answerInput").value,
    question_variants: state.variants,
    category: $("categoryInput").value,
    tags: state.tags,
    status: $("statusInput").value,
    confidence: "high",
    internal_note: $("faqInternalNote").value,
  };
}

async function saveFaq(event) {
  // 保存 FAQ 前先判断是否真的有内容变更，避免无修改保存造成更新时间噪音。
  event.preventDefault();
  if ($("faqId").value && !state.dirty) {
    showToast("没有需要保存的改动");
    return;
  }
  try {
    const saved = await requestJson("/api/faqs", {
      method: "POST",
      body: JSON.stringify(collectForm()),
    });
    showToast("问答已保存");
    state.current = saved;
    state.dirty = false;
    $("faqId").value = saved.id;
    renderEmbeddingState(saved.embedding_status, saved.embedding_error);
    await loadFaqs();
  } catch (error) {
    showToast(error.message);
  }
}

async function generateEmbedding() {
  const id = $("faqId").value;
  if (!id) {
    showToast("请先保存问答，再生成 embedding");
    return;
  }
  try {
    $("embedButton").disabled = true;
    const saved = await requestJson(`/api/faqs/${encodeURIComponent(id)}/embed`, {
      method: "POST",
      body: "{}",
    });
    showToast(saved.embedding_status === "ready" ? "embedding 已生成" : "embedding 生成失败");
    state.current = saved;
    renderEmbeddingState(saved.embedding_status, saved.embedding_error);
    await loadFaqs();
  } catch (error) {
    showToast(error.message);
  } finally {
    $("embedButton").disabled = false;
  }
}

function renderAiSuggestion(suggestion) {
  $("aiQuestion").textContent = suggestion.optimized_question;
  $("aiAnswer").textContent = suggestion.optimized_answer;
  $("aiVariants").innerHTML = suggestion.similar_questions
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  $("aiPanel").classList.remove("hidden");
}

function resetAiSuggestionPanel(statusText) {
  // 新一轮 AI 请求开始时清空旧建议，避免用户误以为旧结果就是新结果。
  state.aiSuggestion = null;
  $("aiStatus").textContent = statusText;
  $("aiQuestion").textContent = "";
  $("aiAnswer").textContent = "";
  $("aiVariants").innerHTML = "";
  $("aiPanel").classList.remove("hidden");
}

function updateSelectedCount() {
  // 统一刷新批量选择数量，避免多个入口各自维护文案。
  $("selectedCount").textContent = `已选择 ${state.selected.size} 项`;
}

async function batchUpdateStatus(status) {
  // 批量状态更新只提交用户当前勾选的 FAQ。
  const ids = Array.from(state.selected);
  if (!ids.length) {
    showToast("请先选择 FAQ");
    return;
  }
  try {
    const result = await requestJson("/api/faqs/batch-status", {
      method: "POST",
      body: JSON.stringify({ ids, status }),
    });
    state.selected.clear();
    updateSelectedCount();
    showToast(`已更新 ${result.count} 条`);
    await loadFaqs();
  } catch (error) {
    showToast(error.message);
  }
}

async function requestAiSuggestion() {
  // 标准问答 AI 建议一次只允许一个请求，避免重复点击造成结果错位。
  const question = $("questionInput").value.trim();
  const answer = $("answerInput").value.trim();
  if (!question || !answer) {
    showToast("请先填写问题和答案");
    return;
  }
  if (state.aiRequestInFlight) {
    showToast("AI 建议正在生成中");
    return;
  }
  try {
    state.aiRequestInFlight = true;
    $("variantsButton").disabled = true;
    $("optimizeButton").disabled = true;
    resetAiSuggestionPanel("生成中");
    const suggestion = await requestJson("/api/ai/optimize", {
      method: "POST",
      body: JSON.stringify({ question, answer }),
    });
    state.aiSuggestion = suggestion;
    $("aiStatus").textContent = "已完成";
    renderAiSuggestion(suggestion);
  } catch (error) {
    $("aiStatus").textContent = "失败";
    showToast(error.message);
  } finally {
    state.aiRequestInFlight = false;
    $("variantsButton").disabled = false;
    $("optimizeButton").disabled = false;
  }
}

function applyAiSuggestion() {
  const suggestion = state.aiSuggestion;
  if (!suggestion) return;
  $("questionInput").value = suggestion.optimized_question;
  $("answerInput").value = suggestion.optimized_answer;
  state.variants = suggestion.similar_questions || [];
  state.dirty = true;
  renderChips();
  $("aiPanel").classList.add("hidden");
}

async function openSettingsModal() {
  // 打开设置中心时重新读取当前运行配置，保证密钥显隐基于最新 env。
  $("settingsOverlay").classList.remove("hidden");
  $("settingsOverlay").setAttribute("aria-hidden", "false");
  switchSettingsSection("parser");
  await loadSettingsValues();
}

function closeSettingsModal(options = {}) {
  // 设置表单有未保存内容时二次确认，避免误关丢失密钥输入。
  if (state.settingsDirty && !options.force && !window.confirm("设置尚未保存，确认关闭？")) {
    return;
  }
  $("settingsOverlay").classList.add("hidden");
  $("settingsOverlay").setAttribute("aria-hidden", "true");
}

function updateSettingsDirtyState() {
  // 未保存状态按当前表单和基线快照比较，改回原值时自动清除提示。
  const current = settingsFingerprint(collectSettingsPayload());
  state.settingsDirty = current !== state.settingsBaseline;
  $("settingsUnsaved").classList.toggle("hidden", !state.settingsDirty);
}

function clearSettingsDirty() {
  // 保存或重新加载配置后刷新设置基线，避免改回原值仍显示未保存。
  state.settingsBaseline = settingsFingerprint(collectSettingsPayload());
  state.settingsDirty = false;
  $("settingsUnsaved").classList.add("hidden");
}

async function loadSettingsValues() {
  // 设置中心打开时读取当前运行配置，避免把密钥硬编码到静态 HTML。
  try {
    const settings = await requestJson("/api/settings");
    applySettingsValues(settings);
    state.settingsBaseline = settingsFingerprint(collectSettingsPayload());
    clearSettingsDirty();
  } catch (error) {
    showToast(`设置读取失败：${error.message}`);
  }
}

function applySettingsValues(settings) {
  // 将后端设置快照回填到表单，保持保存后 UI 与运行时配置一致。
  setSecretValue("mineruApiToken", settings.mineru_api_token);
  setInputValue("mineruTimeout", settings.mineru_parse_timeout_seconds);
  setCheckboxValue("mineruKbPackager", settings.mineru_use_kb_packager);
  setInputValue("chatBaseUrl", settings.chat_base_url);
  setSecretValue("chatApiKey", settings.chat_api_key);
  setInputValue("chatModel", settings.chat_model);
  setInputValue("embeddingBaseUrl", settings.embedding_base_url);
  setSecretValue("embeddingApiKey", settings.embedding_api_key);
  setInputValue("embeddingModel", settings.embedding_model);
  setInputValue("embeddingDimensions", settings.embedding_dimensions);
  setInputValue("ragTopK", settings.rag_top_k);
  setInputValue("ragMinScore", settings.rag_min_score);
  setInputValue("uploadDir", settings.upload_dir);
  setInputValue("wechatTokenFile", settings.wechat_token_file);
  setInputValue("wechatMessageChunkSize", settings.wechat_message_chunk_size);
  setSecretValue("databaseUrl", settings.database_url);
  resetSecretVisibility();
}

function setInputValue(inputId, value) {
  // 统一写入设置字段，允许后端缺省值显示为空字符串。
  const input = $(inputId);
  if (!input) return;
  input.value = value ?? "";
}

function setSecretValue(inputId, value) {
  // 密钥字段把真实值放到 dataset，隐藏态只渲染固定长度黑点。
  const input = $(inputId);
  if (!input) return;
  input.dataset.secretValue = value ?? "";
  renderSecretInput(input, false);
}

function setCheckboxValue(inputId, value) {
  // 后端布尔值直接映射到设置弹窗开关。
  const input = $(inputId);
  if (!input) return;
  input.checked = Boolean(value);
}

function collectSettingsPayload() {
  // 收集设置弹窗当前值，保存只做本地必要校验和租户设置写回。
  return {
    database_url: readSecretValue($("databaseUrl")),
    chat_base_url: $("chatBaseUrl").value.trim(),
    chat_api_key: readSecretValue($("chatApiKey")),
    chat_model: $("chatModel").value.trim(),
    embedding_base_url: $("embeddingBaseUrl").value.trim(),
    embedding_api_key: readSecretValue($("embeddingApiKey")),
    embedding_model: $("embeddingModel").value.trim(),
    embedding_dimensions: $("embeddingDimensions").value.trim(),
    wechat_token_file: $("wechatTokenFile").value.trim(),
    wechat_message_chunk_size: $("wechatMessageChunkSize").value.trim(),
    rag_top_k: $("ragTopK").value.trim(),
    rag_min_score: $("ragMinScore").value.trim(),
    upload_dir: $("uploadDir").value.trim(),
    mineru_api_token: readSecretValue($("mineruApiToken")),
    mineru_parse_timeout_seconds: $("mineruTimeout").value.trim(),
    mineru_use_kb_packager: $("mineruKbPackager").checked,
  };
}

function settingsFingerprint(payload) {
  // 稳定序列化设置表单，供 dirty 状态和保存后基线对比使用。
  return JSON.stringify(Object.keys(payload).sort().reduce((result, key) => {
    result[key] = payload[key];
    return result;
  }, {}));
}

function validateSettingsPayload(payload) {
  // 保存前只校验必填和本地格式，不做外部 API 连通性测试。
  const requiredFields = {
    database_url: "DATABASE_URL",
    chat_base_url: "Chat Base URL",
    chat_api_key: "Chat API Key",
    chat_model: "Chat Model",
    embedding_base_url: "Embedding Base URL",
    embedding_api_key: "Embedding API Key",
    embedding_model: "Embedding Model",
    embedding_dimensions: "Embedding Dimensions",
    mineru_parse_timeout_seconds: "解析超时时间",
  };
  const missing = Object.entries(requiredFields).find(([key]) => !String(payload[key] ?? "").trim());
  if (missing) throw new Error(`${missing[1]} 不能为空`);
  if (!/^https?:\/\//.test(payload.chat_base_url)) throw new Error("Chat Base URL 必须以 http:// 或 https:// 开头");
  if (!/^https?:\/\//.test(payload.embedding_base_url)) {
    throw new Error("Embedding Base URL 必须以 http:// 或 https:// 开头");
  }
}

async function saveSettings() {
  // 保存设置只写回本地配置并刷新表单基线，连接测试由各分组按钮单独触发。
  const payload = collectSettingsPayload();
  try {
    validateSettingsPayload(payload);
    const settings = await requestJson("/api/settings", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    applySettingsValues(settings);
    state.settingsBaseline = settingsFingerprint(collectSettingsPayload());
    updateSettingsDirtyState();
    showToast("设置已保存");
  } catch (error) {
    showToast(error.message);
  }
}

function switchSettingsSection(section, options = {}) {
  // 左侧分组作为锚点导航，右侧所有设置区连续排列并可滚动查看。
  document.querySelectorAll("[data-settings-section]").forEach((button) => {
    button.classList.toggle("active", button.dataset.settingsSection === section);
  });
  document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.settingsPanel === section);
  });
  if (options.scroll) {
    document.querySelector(`[data-settings-panel="${section}"]`)?.scrollIntoView({
      block: "start",
      behavior: "smooth",
    });
  }
}

function resetSecretVisibility() {
  // 重新载入配置后统一恢复掩码状态，避免上次明文查看延续到新字段。
  document.querySelectorAll("[data-secret-toggle]").forEach((button) => {
    const input = $(button.dataset.secretToggle);
    if (!input) return;
    renderSecretInput(input, false);
  });
}

function renderSecretInput(input, visible) {
  // 用普通文本框渲染密钥，避免浏览器 password 圆点暴露真实长度。
  const hasSecret = Boolean(input.dataset.secretValue);
  input.type = "text";
  input.readOnly = !visible && hasSecret;
  input.classList.toggle("secret-mask-value", !visible && hasSecret);
  input.value = visible ? (input.dataset.secretValue || "") : (hasSecret ? SECRET_MASK : "");
  const button = document.querySelector(`[data-secret-toggle="${input.id}"]`);
  if (!button) return;
  button.dataset.secretVisible = visible ? "true" : "false";
  button.setAttribute("aria-label", `${visible ? "隐藏" : "显示"}${secretLabel(input.id)}`);
}

function secretLabel(inputId) {
  // 按字段 id 生成眼睛按钮提示，不把真实密钥写进可见文案。
  const labels = {
    mineruApiToken: " MinerU Token",
    chatApiKey: " Chat API Key",
    embeddingApiKey: " Embedding API Key",
    databaseUrl: "数据库地址",
  };
  return labels[inputId] || "密钥";
}

function readSecretValue(input) {
  // 复制或保存设置时读取真实值，隐藏态不能读取输入框里的固定黑点。
  const button = document.querySelector(`[data-secret-toggle="${input.id}"]`);
  return button?.dataset.secretVisible === "true" ? input.value : (input.dataset.secretValue || "");
}

function syncVisibleSecretInput(input) {
  // 用户在明文状态下编辑密钥时，同步回 dataset 供复制和后续隐藏使用。
  const button = document.querySelector(`[data-secret-toggle="${input.id}"]`);
  if (button?.dataset.secretVisible === "true") {
    input.dataset.secretValue = input.value;
  }
}

function toggleSecretInput(inputId, button) {
  // 密钥默认掩码展示，用户手动点击时才短暂明文查看。
  const input = $(inputId);
  const visible = button?.dataset.secretVisible !== "true";
  if (!visible) input.dataset.secretValue = input.value;
  renderSecretInput(input, visible);
}

async function copySecretInput(inputId) {
  // 复制按钮优先使用浏览器剪贴板，不支持时给出明确提示。
  const input = $(inputId);
  try {
    await navigator.clipboard.writeText(readSecretValue(input));
    showToast("已复制到剪贴板");
  } catch {
    showToast("当前浏览器不支持复制");
  }
}

function clearSecretInput(inputId) {
  // 清空只影响当前弹窗表单，保存前不会写回配置。
  const input = $(inputId);
  input.dataset.secretValue = "";
  renderSecretInput(input, true);
  updateSettingsDirtyState();
}

function bindEvents() {
  // 绑定管理后台全部可见控件，避免页面出现无反馈按钮。
  $("notificationButton").addEventListener("click", () => showToast("当前没有新的内部通知"));
  $("settingsButton").addEventListener("click", openSettingsModal);
  $("knowledgeHomeButton").addEventListener("click", () => switchWorkspace("knowledge"));
  $("assistantBackButton").addEventListener("click", () => switchWorkspace("knowledge"));
  $("knowledgeSearchInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runKnowledgeSearch();
    }
  });
  document.querySelectorAll(".knowledge-card").forEach((button) => {
    button.addEventListener("click", () =>
      handleKnowledgeEntryClick(button.dataset.knowledgeEntry, button.dataset.targetWorkspace),
    );
  });
  $("closeSettingsButton").addEventListener("click", () => closeSettingsModal());
  $("settingsCancelButton").addEventListener("click", () => closeSettingsModal());
  $("saveSettingsButton").addEventListener("click", saveSettings);
  $("settingsOverlay").addEventListener("mousedown", (event) => {
    if (event.target === $("settingsOverlay")) closeSettingsModal();
  });
  document.querySelectorAll("[data-settings-section]").forEach((button) => {
    button.addEventListener("click", () => switchSettingsSection(
      button.dataset.settingsSection,
      { scroll: true },
    ));
  });
  document.querySelectorAll("#settingsModal input, #settingsModal select").forEach((input) => {
    input.addEventListener("input", () => {
      if (input.closest(".settings-secret")) syncVisibleSecretInput(input);
      updateSettingsDirtyState();
    });
    input.addEventListener("change", () => {
      updateSettingsDirtyState();
    });
  });
  document.querySelectorAll("[data-secret-toggle]").forEach((button) => {
    button.addEventListener("click", () => toggleSecretInput(button.dataset.secretToggle, button));
  });
  document.querySelectorAll("[data-secret-copy]").forEach((button) => {
    button.addEventListener("click", () => copySecretInput(button.dataset.secretCopy));
  });
  document.querySelectorAll("[data-secret-clear]").forEach((button) => {
    button.addEventListener("click", () => clearSecretInput(button.dataset.secretClear));
  });
  document.querySelectorAll("[data-settings-test]").forEach((button) => {
    button.addEventListener("click", () => showToast("测试连接接口待接入"));
  });
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.addEventListener("click", () => switchWorkspace(button.dataset.workspace));
  });
  document.querySelectorAll("[data-faq-subview]").forEach((button) => {
    button.addEventListener("click", () => switchFaqSubview(button.dataset.faqSubview));
  });
  document.querySelectorAll(".filter-title").forEach((button) => {
    button.addEventListener("click", () => {
      const list = button.parentElement?.querySelector(".filter-list");
      if (!list) return;
      list.classList.toggle("collapsed");
      button.classList.toggle("collapsed", list.classList.contains("collapsed"));
    });
  });
  $("newFaqButton").addEventListener("click", () => openDrawer());
  $("closeDrawer").addEventListener("click", closeDrawer);
  $("drawerBackdrop").addEventListener("click", () => {
    closeDrawer({ force: true });
    closeCandidateDrawer();
  });
  $("refreshButton").addEventListener("click", loadFaqs);
  $("faqForm").addEventListener("submit", saveFaq);
  $("embedButton").addEventListener("click", generateEmbedding);
  $("variantsButton").addEventListener("click", requestAiSuggestion);
  $("optimizeButton").addEventListener("click", requestAiSuggestion);
  $("applyAiButton").addEventListener("click", applyAiSuggestion);
  $("cancelAiButton").addEventListener("click", () => $("aiPanel").classList.add("hidden"));
  $("importFileSelect").addEventListener("change", (event) => {
    if (event.target.value) selectImportFile(event.target.value);
  });
  $("documentFileInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) uploadDocumentFile(file);
    event.target.value = "";
  });
  $("documentSearchInput").addEventListener("input", (event) => {
    state.documentQuery = event.target.value.trim();
    window.clearTimeout(state.documentSearchTimer);
    state.documentSearchTimer = window.setTimeout(loadDocumentFiles, 220);
  });
  $("documentStatusTabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-document-status]");
    if (!button) return;
    state.documentStatus = button.dataset.documentStatus;
    updateDocumentStatusTabs();
    loadDocumentFiles();
  });
  $("closeDocumentDrawer").addEventListener("click", closeDocumentDrawer);
  $("documentDrawerBackdrop").addEventListener("click", closeDocumentDrawer);
  $("parseDocumentButton").addEventListener("click", parseCurrentDocumentFile);
  $("sendDocumentToFaqButton").addEventListener("click", sendCurrentDocumentToFaq);
  $("downloadDocumentButton").addEventListener("click", downloadCurrentDocumentFile);
  $("deleteDocumentButton").addEventListener("click", () => deleteCurrentDocumentFile());
  $("importSearchInput").addEventListener("input", (event) => {
    state.importQuery = event.target.value.trim();
    window.clearTimeout(state.importSearchTimer);
    state.importSearchTimer = window.setTimeout(loadImportFiles, 220);
  });
  $("showImportFailedButton").addEventListener("click", () => {
    const failedCount = Number($("importFailedCount").textContent || 0);
    if (!failedCount) {
      showToast("当前没有解析失败文件");
      return;
    }
    state.importStatus = "failed";
    const failedRadio = document.querySelector('input[name="importStatus"][value="failed"]');
    if (failedRadio) failedRadio.checked = true;
    loadImportFiles();
  });
  $("candidateSearchInput").addEventListener("input", (event) => {
    state.candidateQuery = event.target.value.trim();
    renderImportCandidateList();
  });
  $("candidateStatusSelect").addEventListener("change", (event) => {
    state.candidateStatus = event.target.value;
    renderImportCandidateList();
  });
  $("candidateCategorySelect").addEventListener("change", (event) => {
    state.candidateCategory = event.target.value;
    renderImportCandidateList();
  });
  $("candidateConfidenceSelect").addEventListener("change", (event) => {
    state.candidateConfidence = event.target.value;
    renderImportCandidateList();
  });
  $("candidateDuplicateSelect").addEventListener("change", (event) => {
    state.candidateDuplicate = event.target.value;
    renderImportCandidateList();
  });
  $("onlyPendingCandidates").addEventListener("change", (event) => {
    state.candidateOnlyPending = event.target.checked;
    renderImportCandidateList();
  });
  $("clearCandidateChunkFilterButton").addEventListener("click", () => {
    setCandidateChunkFilter(null);
    renderImportCandidateList();
  });
  $("selectAllCandidates").addEventListener("change", (event) => {
    filteredImportCandidates().forEach((candidate) => {
      if (event.target.checked) state.selectedImportCandidates.add(candidate.id);
      else state.selectedImportCandidates.delete(candidate.id);
    });
    renderImportCandidateList();
  });
  $("batchSaveCandidatesButton").addEventListener("click", saveSelectedCandidates);
  $("batchIgnoreCandidatesButton").addEventListener("click", ignoreSelectedCandidates);
  $("batchRewriteCandidatesButton").addEventListener("click", () =>
    showToast("请打开单条候选后使用 AI 保守改写"),
  );
  $("generateChunkCandidatesButton").addEventListener("click", generateCandidatesForSelectedChunks);
  $("generateCurrentChunkButton").addEventListener("click", generateCandidatesForCurrentChunk);
  $("viewChunkCandidatesButton").addEventListener("click", viewCurrentChunkCandidates);
  $("reparseImportButton").addEventListener("click", reparseCurrentImportFile);
  $("selectAllChunks").addEventListener("change", (event) => {
    visibleImportChunks().forEach((chunk) => {
      if (event.target.checked) state.selectedImportChunks.add(chunk.id);
      else state.selectedImportChunks.delete(chunk.id);
    });
    renderImportChunks(state.importChunks);
  });
  $("onlyReviewChunks").addEventListener("change", () => {
    state.chunkPage = 1;
    renderImportChunks(state.importChunks);
  });
  $("prevChunkPage").addEventListener("click", () => {
    state.chunkPage = Math.max(state.chunkPage - 1, 1);
    renderImportChunks(state.importChunks);
  });
  $("nextChunkPage").addEventListener("click", () => {
    state.chunkPage += 1;
    renderImportChunks(state.importChunks);
  });
  $("chunkPageSize").addEventListener("change", (event) => {
    state.chunkPageSize = Number(event.target.value);
    state.chunkPage = 1;
    renderImportChunks(state.importChunks);
  });
  $("closeCandidateDrawer").addEventListener("click", closeCandidateDrawer);
  $("saveCandidateButton").addEventListener("click", saveCurrentCandidate);
  $("ignoreCandidateButton").addEventListener("click", ignoreCurrentCandidate);
  $("rewriteCandidateButton").addEventListener("click", rewriteCurrentCandidate);
  $("viewCandidateSourceButton").addEventListener("click", focusCurrentCandidateSource);
  $("prevCandidate").addEventListener("click", () => {
    state.currentCandidateIndex = Math.max(state.currentCandidateIndex - 1, 0);
    renderCurrentCandidate();
    renderImportCandidateList();
  });
  $("nextCandidate").addEventListener("click", () => {
    state.currentCandidateIndex = Math.min(
      state.currentCandidateIndex + 1,
      Math.max(filteredImportCandidates().length - 1, 0),
    );
    renderCurrentCandidate();
    renderImportCandidateList();
  });
  $("selectAll").addEventListener("change", (event) => {
    document.querySelectorAll(".row-check").forEach((checkbox) => {
      checkbox.checked = event.target.checked;
      if (checkbox.checked) state.selected.add(checkbox.dataset.id);
      else state.selected.delete(checkbox.dataset.id);
    });
    updateSelectedCount();
  });
  $("showFailedButton").addEventListener("click", () => {
    state.embeddingStatus = "failed";
    state.page = 1;
    loadFaqs();
  });
  document.querySelectorAll(".batch-button[data-status]").forEach((button) => {
    button.addEventListener("click", () => batchUpdateStatus(button.dataset.status));
  });

  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    state.page = 1;
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(loadFaqs, 220);
  });

  $("pageSize").addEventListener("change", (event) => {
    state.pageSize = Number(event.target.value);
    state.page = 1;
    loadFaqs();
  });

  $("prevPage").addEventListener("click", () => {
    state.page = Math.max(state.page - 1, 1);
    loadFaqs();
  });

  $("nextPage").addEventListener("click", () => {
    state.page += 1;
    loadFaqs();
  });

  $("batchEmbedButton").addEventListener("click", async () => {
    try {
      const result = await requestJson("/api/faqs/embed-pending", {
        method: "POST",
        body: JSON.stringify({ limit: 50 }),
      });
      showToast(`已处理 ${result.count} 条`);
      await loadFaqs();
    } catch (error) {
      showToast(error.message);
    }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (state.workspace === "knowledge") $("knowledgeSearchInput").focus();
      else if (state.workspace === "faq") $("searchInput").focus();
      else if (state.workspace === "documents") $("documentSearchInput").focus();
      else if (state.workspace === "import") $("importSearchInput").focus();
      return;
    }
    if (event.key !== "Escape") return;
    if (state.workspace === "knowledge" && state.expandedKnowledgeEntry) {
      state.expandedKnowledgeEntry = null;
      renderKnowledgeEntryState();
      return;
    }
    if ($("candidateDrawer").classList.contains("open")) {
      closeCandidateDrawer();
      return;
    }
    if ($("documentDrawer").classList.contains("open")) {
      closeDocumentDrawer();
      return;
    }
    if ($("drawer").classList.contains("open")) closeDrawer();
  });

  document.addEventListener("input", (event) => {
    if ($("drawer").contains(event.target)) state.dirty = true;
  });

  document.addEventListener("change", (event) => {
    if (event.target.name === "status") {
      state.status = event.target.value;
      state.page = 1;
      loadFaqs();
    }
    if (event.target.name === "embedding") {
      state.embeddingStatus = event.target.value;
      state.page = 1;
      loadFaqs();
    }
    if (event.target.name === "importStatus") {
      state.importStatus = event.target.value;
      loadImportFiles();
    }
  });

  document.addEventListener("click", async (event) => {
    if (state.workspace === "knowledge" && !event.target.closest(".knowledge-entry")) {
      state.expandedKnowledgeEntry = null;
      renderKnowledgeEntryState();
    }
    const row = event.target.closest("tr[data-id]");
    const documentFile = event.target.closest("[data-document-file-id]");
    const documentParseButton = event.target.closest("[data-parse-document-id]");
    const documentChunkButton = event.target.closest("[data-document-chunk-index]");
    const importFile = event.target.closest("[data-import-file-id]");
    const importChunk = event.target.closest("[data-import-chunk-id]");
    const importCandidate = event.target.closest("[data-import-candidate-index]");
    const documentDeleteButton = event.target.closest("[data-delete-document-id]");
    if (documentDeleteButton) {
      await deleteCurrentDocumentFile(documentDeleteButton.dataset.deleteDocumentId);
      return;
    }
    if (documentParseButton) {
      const fileId = documentParseButton.dataset.parseDocumentId;
      await openDocumentDrawer(fileId);
      await parseCurrentDocumentFile();
      return;
    }
    if (documentChunkButton) {
      state.currentDocumentChunkIndex = Number(documentChunkButton.dataset.documentChunkIndex || 0);
      renderDocumentChunks(state.documentChunks);
      return;
    }
    if (event.target.classList.contains("row-check")) {
      const id = event.target.dataset.id;
      if (event.target.checked) state.selected.add(id);
      else state.selected.delete(id);
      updateSelectedCount();
      return;
    }
    if (event.target.classList.contains("candidate-check")) {
      const id = event.target.dataset.id;
      if (event.target.checked) state.selectedImportCandidates.add(id);
      else state.selectedImportCandidates.delete(id);
      updateSelectedCandidateCount();
      return;
    }
    if (importCandidate) {
      openCandidateDrawer(Number(importCandidate.dataset.importCandidateIndex));
      return;
    }
    if (event.target.classList.contains("chunk-check")) {
      const id = event.target.dataset.id;
      if (event.target.checked) state.selectedImportChunks.add(id);
      else state.selectedImportChunks.delete(id);
      updateSelectedChunkCount();
      return;
    }
    if (documentFile) {
      await openDocumentDrawer(documentFile.dataset.documentFileId);
      return;
    }
    if (importFile) {
      selectImportFile(importFile.dataset.importFileId);
      return;
    }
    if (importChunk) {
      selectImportChunk(importChunk.dataset.importChunkId);
      return;
    }
    if (row) {
      try {
        const record = await requestJson(`/api/faqs/${encodeURIComponent(row.dataset.id)}`);
        openDrawer(record);
      } catch (error) {
        showToast(error.message);
      }
    }
    if (event.target.matches(".chip button")) {
      const group = event.target.dataset.group;
      const value = event.target.dataset.value;
      const targets = {
        variants: state.variants,
        tags: state.tags,
        candidateVariants: state.candidateVariants,
        candidateTags: state.candidateTags,
      };
      const target = targets[group];
      if (!target) return;
      const index = target.indexOf(value);
      if (index >= 0) target.splice(index, 1);
      state.dirty = true;
      if (group.startsWith("candidate")) renderCandidateChips();
      else renderChips();
    }
  });

  $("variantInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addChip("variants", event.target.value);
      event.target.value = "";
    }
  });

  $("tagInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addChip("tags", event.target.value);
      event.target.value = "";
    }
  });

  $("candidateVariantInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addCandidateChip("candidateVariants", event.target.value);
      event.target.value = "";
    }
  });

  $("candidateTagInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addCandidateChip("candidateTags", event.target.value);
      event.target.value = "";
    }
  });
}

bindEvents();
loadFaqs();
loadKnowledgeImportSummary();
