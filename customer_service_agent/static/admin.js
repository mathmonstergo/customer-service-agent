const state = {
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
};

const statusOptions = ["usable", "needs_review", "disabled"];
const embeddingOptions = ["pending", "ready", "stale", "failed"];

const $ = (id) => document.getElementById(id);

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
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
  return `<span class="status-pill ${status}">${status}</span>`;
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
        <tr class="${active}" data-id="${item.id}">
          <td><input type="checkbox" class="row-check" data-id="${item.id}" ${selected}></td>
          <td class="row-index">${rowNumber}</td>
          <td title="${item.question || ""}">${item.question || ""}</td>
          <td>${item.category || "-"}</td>
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
    $("selectedCount").textContent = `已选择 ${state.selected.size} 项`;
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
  return `<span class="chip">${value}<button type="button" data-group="${group}" data-value="${value}">×</button></span>`;
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
    .map((item) => `<li>${item}</li>`)
    .join("");
  $("aiPanel").classList.remove("hidden");
}

async function requestAiSuggestion() {
  const question = $("questionInput").value.trim();
  const answer = $("answerInput").value.trim();
  if (!question || !answer) {
    showToast("请先填写问题和答案");
    return;
  }
  try {
    $("aiStatus").textContent = "生成中";
    $("aiPanel").classList.remove("hidden");
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
  $("newFaqButton").addEventListener("click", () => openDrawer());
  $("closeDrawer").addEventListener("click", closeDrawer);
  $("refreshButton").addEventListener("click", loadFaqs);
  $("faqForm").addEventListener("submit", saveFaq);
  $("embedButton").addEventListener("click", generateEmbedding);
  $("variantsButton").addEventListener("click", requestAiSuggestion);
  $("optimizeButton").addEventListener("click", requestAiSuggestion);
  $("applyAiButton").addEventListener("click", applyAiSuggestion);
  $("cancelAiButton").addEventListener("click", () => $("aiPanel").classList.add("hidden"));

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
    if (event.key === "Escape" && $("drawer").classList.contains("open")) closeDrawer();
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
  });

  document.addEventListener("click", async (event) => {
    const row = event.target.closest("tr[data-id]");
    if (event.target.classList.contains("row-check")) {
      const id = event.target.dataset.id;
      if (event.target.checked) state.selected.add(id);
      else state.selected.delete(id);
      $("selectedCount").textContent = `已选择 ${state.selected.size} 项`;
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
      const target = group === "variants" ? state.variants : state.tags;
      const index = target.indexOf(value);
      if (index >= 0) target.splice(index, 1);
      state.dirty = true;
      renderChips();
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
}

bindEvents();
loadFaqs();
