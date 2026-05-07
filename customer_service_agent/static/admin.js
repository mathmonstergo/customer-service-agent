const state = {
  workspace: "faq",
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
  importFiles: [],
  currentImportFile: null,
  importChunks: [],
  selectedImportChunks: new Set(),
  currentImportChunk: null,
  importCandidates: [],
  currentCandidateIndex: 0,
  candidateVariants: [],
  candidateTags: [],
};

const statusOptions = ["usable", "needs_review", "disabled"];
const embeddingOptions = ["pending", "ready", "stale", "failed"];

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

function switchWorkspace(workspace) {
  // 切换知识库下的标准问答和导入审核工作区。
  state.workspace = workspace;
  $("faqWorkspace").classList.toggle("hidden", workspace !== "faq");
  $("importWorkspace").classList.toggle("hidden", workspace !== "import");
  $("workspaceTitle").textContent = workspace === "faq" ? "标准问答" : "导入审核";
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.workspace === workspace);
  });
  if (workspace === "import") loadImportFiles();
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
    '<div class="import-empty">暂无导入文件，点击“上传文件”开始。</div>';
  $("importChunks").innerHTML =
    '<tr><td colspan="6" class="empty">请选择左侧文件查看时间切块</td></tr>';
  $("candidateList").innerHTML =
    '<tr><td colspan="5" class="empty">请选择切块后查看候选 FAQ</td></tr>';
  $("candidateListSummary").textContent = "请选择切块后生成候选 FAQ";
  $("openCurrentCandidateButton").disabled = true;
  updateSelectedChunkCount();
  closeCandidateDrawer();
}

async function loadImportFiles() {
  // 载入导入文件列表，驱动左侧文件栏和状态计数。
  const params = new URLSearchParams({ limit: "100" });
  if (state.importQuery) params.set("query", state.importQuery);
  if (state.importStatus) params.set("status", state.importStatus);
  try {
    const data = await requestJson(`/api/import/files?${params.toString()}`);
    state.importFiles = data.items || [];
    renderImportFileCounts(data);
    renderImportFiles(state.importFiles);
  } catch (error) {
    showToast(error.message);
  }
}

function renderImportFileCounts(data) {
  // 刷新导入文件状态筛选数量。
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

function renderImportFiles(items) {
  // 渲染左侧导入文件列表，展示识别类型和解析状态。
  if (!items.length) {
    renderImportPlaceholder();
    return;
  }
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
  // 选择导入文件后加载对应时间切块。
  const file = state.importFiles.find((item) => item.id === fileId) || { id: fileId };
  state.currentImportFile = file;
  state.currentImportChunk = null;
  state.importCandidates = [];
  state.selectedImportChunks.clear();
  state.currentCandidateIndex = 0;
  renderImportFiles(state.importFiles);
  renderImportCandidateList();
  closeCandidateDrawer();
  $("currentImportFileName").textContent = file.original_name || "导入文件";
  $("currentImportMeta").textContent = `${file.file_type || "-"} / ${file.parser || "-"} / ${file.status || "-"}`;
  if (file.status === "unsupported") {
    $("importChunks").innerHTML =
      '<tr><td colspan="6" class="empty">当前文件类型已识别，但第一期暂不支持解析</td></tr>';
    renderImportCandidateList("当前文件类型暂不支持解析");
    return;
  }
  await loadImportChunks(fileId);
}

async function loadImportChunks(fileId) {
  // 载入中间栏时间切块。
  try {
    const data = await requestJson(`/api/import/files/${encodeURIComponent(fileId)}/chunks`);
    state.importChunks = data.items || [];
    renderImportChunks(state.importChunks);
  } catch (error) {
    showToast(error.message);
  }
}

function renderImportChunks(items) {
  // 渲染切块表格，保留时间范围、消息数、关键词和候选数。
  const visibleItems = visibleImportChunks(items);
  $("chunkSummary").textContent = `共 ${items.length} 块`;
  updateSelectedChunkCount();
  if (!visibleItems.length) {
    $("importChunks").innerHTML = '<tr><td colspan="6" class="empty">暂无切块</td></tr>';
    renderImportCandidateList("当前文件暂无可审核切块");
    return;
  }
  $("importChunks").innerHTML = visibleItems
    .map((item) => {
      const active = state.currentImportChunk?.id === item.id ? "selected" : "";
      const checked = state.selectedImportChunks.has(item.id) ? "checked" : "";
      const keywords = Array.isArray(item.keywords) ? item.keywords.join(" / ") : "";
      return `
        <tr class="${active}" data-import-chunk-id="${escapeHtml(item.id)}">
          <td><input type="checkbox" class="chunk-check" data-id="${escapeHtml(item.id)}" ${checked}></td>
          <td>${formatDate(item.start_at)} - ${formatDate(item.end_at).slice(11) || "-"}</td>
          <td>${item.message_count || 0} 条消息</td>
          <td>${escapeHtml(keywords || "-")}</td>
          <td>${statusPill(item.status)}</td>
          <td>${item.candidate_count || 0} 条候选</td>
        </tr>
      `;
    })
    .join("");
  updateSelectedChunkCount();
}

function visibleImportChunks(items = state.importChunks) {
  // 根据当前筛选返回可见切块，供渲染和全选共用。
  if (!$("onlyReviewChunks")?.checked) return items;
  return items.filter((item) => item.status !== "generated");
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

async function selectImportChunk(chunkId) {
  // 选择切块后只载入候选列表，详细审核由侧滑抽屉承载。
  state.currentImportChunk = state.importChunks.find((item) => item.id === chunkId) || null;
  state.currentCandidateIndex = 0;
  renderImportChunks(state.importChunks);
  closeCandidateDrawer();
  await loadImportCandidates(chunkId);
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

function candidateStatusPill(value) {
  // 候选状态使用中文标签，保持审核语义比数据库值更直观。
  const labels = { pending: "待审核", saved: "已保存", ignored: "已忽略" };
  const classes = { pending: "needs_review", saved: "ready", ignored: "disabled" };
  const status = value || "pending";
  return `<span class="status-pill ${classes[status] || "pending"}">${labels[status] || escapeHtml(status)}</span>`;
}

function renderCandidateCounts() {
  // 统一刷新候选列表和审核抽屉使用的状态统计。
  const candidates = state.importCandidates;
  $("candidateIndex").textContent = candidates.length
    ? `${state.currentCandidateIndex + 1} / ${candidates.length}`
    : "0 / 0";
  $("candidatePendingCount").textContent = candidates.filter((item) => item.status === "pending").length;
  $("candidateSavedCount").textContent = candidates.filter((item) => item.status === "saved").length;
  $("candidateIgnoredCount").textContent = candidates.filter((item) => item.status === "ignored").length;
  $("openCurrentCandidateButton").disabled = !candidates.length;
}

function renderImportCandidateList(message = "") {
  // 在主工作区显示候选摘要，用户点击行或审核按钮后才打开右侧抽屉。
  const candidates = state.importCandidates;
  renderCandidateCounts();
  if (!state.currentImportChunk) {
    $("candidateListSummary").textContent = message || "请选择切块后生成候选 FAQ";
    $("candidateList").innerHTML =
      '<tr><td colspan="5" class="empty">请选择切块后查看候选 FAQ</td></tr>';
    return;
  }
  $("candidateListSummary").textContent = candidates.length
    ? `当前切块 ${candidates.length} 条候选，点击行进入审核`
    : message || "当前切块暂无候选 FAQ，可先批量生成";
  if (!candidates.length) {
    $("candidateList").innerHTML =
      '<tr><td colspan="5" class="empty">当前切块暂无候选 FAQ</td></tr>';
    return;
  }
  $("candidateList").innerHTML = candidates
    .map((item, index) => {
      const active = index === state.currentCandidateIndex ? "selected" : "";
      return `
        <tr class="${active}" data-import-candidate-index="${index}">
          <td>${candidateStatusPill(item.status)}</td>
          <td class="candidate-question-cell" title="${escapeHtml(item.question || "")}">${escapeHtml(item.question || "-")}</td>
          <td>${escapeHtml(item.category || "-")}</td>
          <td>${escapeHtml(item.confidence || "medium")}</td>
          <td><button class="candidate-review-button" type="button" data-import-candidate-index="${index}">审核</button></td>
        </tr>
      `;
    })
    .join("");
}

function renderCurrentCandidate() {
  // 渲染侧滑抽屉中的当前候选 FAQ 表单和状态统计。
  const candidates = state.importCandidates;
  const current = candidates[state.currentCandidateIndex];
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
  state.candidateVariants = current.similar_questions || [];
  state.candidateTags = current.tags || [];
  renderCandidateChips();
  renderCandidateConfidence(current.confidence || "medium");
}

function openCandidateDrawer(index = state.currentCandidateIndex) {
  // 打开候选 FAQ 审核抽屉，避免详情常驻占用主工作区。
  if (!state.importCandidates.length) {
    showToast("当前切块暂无候选 FAQ");
    return;
  }
  state.currentCandidateIndex = Math.min(index, state.importCandidates.length - 1);
  renderCurrentCandidate();
  renderImportCandidateList();
  $("candidateDrawer").classList.add("open");
  $("candidateDrawer").setAttribute("aria-hidden", "false");
}

function closeCandidateDrawer() {
  // 关闭候选审核抽屉，不影响当前切块和候选列表选择。
  if (!$("candidateDrawer")) return;
  $("candidateDrawer").classList.remove("open");
  $("candidateDrawer").setAttribute("aria-hidden", "true");
}

function renderCandidateEmpty(message) {
  // 清空右侧候选表单并显示当前状态。
  $("candidateQuestion").value = "";
  $("candidateAnswer").value = "";
  $("candidateCategory").value = "";
  $("candidateInternalNote").value = "";
  $("candidateSource").textContent = message;
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
    showToast("请先选择时间切块");
    return;
  }
  try {
    const result = await requestJson(`/api/import/chunks/${encodeURIComponent(chunk.id)}/generate`, {
      method: "POST",
      body: "{}",
    });
    state.importCandidates = result.items || [];
    state.currentCandidateIndex = 0;
    showToast(`已生成 ${state.importCandidates.length} 条候选`);
    await loadImportChunks(state.currentImportFile.id);
    state.currentImportChunk = state.importChunks.find((item) => item.id === chunk.id) || chunk;
    renderImportChunks(state.importChunks);
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
    showToast("请先选择时间切块");
    return;
  }
  try {
    $("generateChunkCandidatesButton").disabled = true;
    let generatedCount = 0;
    for (const chunkId of chunkIds) {
      const result = await requestJson(`/api/import/chunks/${encodeURIComponent(chunkId)}/generate`, {
        method: "POST",
        body: "{}",
      });
      generatedCount += (result.items || []).length;
    }
    showToast(`已生成 ${generatedCount} 条候选`);
    state.selectedImportChunks.clear();
    await loadImportChunks(state.currentImportFile.id);
    if (state.currentImportChunk) await loadImportCandidates(state.currentImportChunk.id);
    else renderImportCandidateList();
    closeCandidateDrawer();
  } catch (error) {
    showToast(error.message);
  } finally {
    $("generateChunkCandidatesButton").disabled = false;
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
    await loadImportFiles();
    await selectImportFile(file.id);
  } catch (error) {
    showToast(error.message);
  } finally {
    $("reparseImportButton").disabled = false;
  }
}

async function saveCurrentCandidate() {
  // 先保存人工编辑，再写入标准问答。
  const current = state.importCandidates[state.currentCandidateIndex];
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
    showToast("已保存到标准问答");
    await loadImportCandidates(current.chunk_id, { index });
    openCandidateDrawer(state.currentCandidateIndex);
  } catch (error) {
    showToast(error.message);
  }
}

async function ignoreCurrentCandidate() {
  // 忽略不适合沉淀为标准问答的候选。
  const current = state.importCandidates[state.currentCandidateIndex];
  if (!current) return;
  const index = state.currentCandidateIndex;
  try {
    await requestJson(`/api/import/candidates/${encodeURIComponent(current.id)}/ignore`, {
      method: "POST",
      body: "{}",
    });
    showToast("已忽略候选 FAQ");
    await loadImportCandidates(current.chunk_id, { index });
    openCandidateDrawer(state.currentCandidateIndex);
  } catch (error) {
    showToast(error.message);
  }
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
  $("statusInput").value = record?.status || "usable";
  $("aiPanel").classList.add("hidden");
  renderChips();
  renderEmbeddingState(record?.embedding_status || "pending", record?.embedding_error || "");
  $("drawer").classList.add("open");
  $("drawer").setAttribute("aria-hidden", "false");
}

function closeDrawer() {
  if (state.dirty && !window.confirm("有未保存改动，确认关闭？")) return;
  $("drawer").classList.remove("open");
  $("drawer").setAttribute("aria-hidden", "true");
  state.current = null;
  state.dirty = false;
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
  };
}

async function saveFaq(event) {
  event.preventDefault();
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
  const question = $("questionInput").value.trim();
  const answer = $("answerInput").value.trim();
  if (!question || !answer) {
    showToast("请先填写问题和答案");
    return;
  }
  try {
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

function bindEvents() {
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.addEventListener("click", () => switchWorkspace(button.dataset.workspace));
  });
  $("newFaqButton").addEventListener("click", () => openDrawer());
  $("closeDrawer").addEventListener("click", closeDrawer);
  $("refreshButton").addEventListener("click", loadFaqs);
  $("faqForm").addEventListener("submit", saveFaq);
  $("embedButton").addEventListener("click", generateEmbedding);
  $("variantsButton").addEventListener("click", requestAiSuggestion);
  $("optimizeButton").addEventListener("click", requestAiSuggestion);
  $("applyAiButton").addEventListener("click", applyAiSuggestion);
  $("cancelAiButton").addEventListener("click", () => $("aiPanel").classList.add("hidden"));
  $("importFileInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) uploadImportFile(file);
    event.target.value = "";
  });
  $("importSearchInput").addEventListener("input", (event) => {
    state.importQuery = event.target.value.trim();
    window.clearTimeout(state.importSearchTimer);
    state.importSearchTimer = window.setTimeout(loadImportFiles, 220);
  });
  $("showImportFailedButton").addEventListener("click", () => {
    state.importStatus = "failed";
    loadImportFiles();
  });
  $("generateChunkCandidatesButton").addEventListener("click", generateCandidatesForSelectedChunks);
  $("reparseImportButton").addEventListener("click", reparseCurrentImportFile);
  $("selectAllChunks").addEventListener("change", (event) => {
    visibleImportChunks().forEach((chunk) => {
      if (event.target.checked) state.selectedImportChunks.add(chunk.id);
      else state.selectedImportChunks.delete(chunk.id);
    });
    renderImportChunks(state.importChunks);
  });
  $("onlyReviewChunks").addEventListener("change", () => renderImportChunks(state.importChunks));
  $("openCurrentCandidateButton").addEventListener("click", () => openCandidateDrawer());
  $("closeCandidateDrawer").addEventListener("click", closeCandidateDrawer);
  $("saveCandidateButton").addEventListener("click", saveCurrentCandidate);
  $("ignoreCandidateButton").addEventListener("click", ignoreCurrentCandidate);
  $("prevCandidate").addEventListener("click", () => {
    state.currentCandidateIndex = Math.max(state.currentCandidateIndex - 1, 0);
    renderCurrentCandidate();
    renderImportCandidateList();
  });
  $("nextCandidate").addEventListener("click", () => {
    state.currentCandidateIndex = Math.min(
      state.currentCandidateIndex + 1,
      Math.max(state.importCandidates.length - 1, 0),
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
    if (event.key !== "Escape") return;
    if ($("candidateDrawer").classList.contains("open")) {
      closeCandidateDrawer();
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
    const row = event.target.closest("tr[data-id]");
    const importFile = event.target.closest("[data-import-file-id]");
    const importChunk = event.target.closest("[data-import-chunk-id]");
    const importCandidate = event.target.closest("[data-import-candidate-index]");
    if (event.target.classList.contains("row-check")) {
      const id = event.target.dataset.id;
      if (event.target.checked) state.selected.add(id);
      else state.selected.delete(id);
      updateSelectedCount();
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
