const API_BASE = ""; // same-origin
const SESSION_ID = "web-session";

const $ = (sel) => document.querySelector(sel);
const fileInput = $("#fileInput");
const dropzone = $("#dropzone");
const uploadBtn = $("#uploadBtn");
const uploadStatus = $("#uploadStatus");
const docList = $("#docList");
const chatWindow = $("#chatWindow");
const chatForm = $("#chatForm");
const questionInput = $("#questionInput");
const askBtn = $("#askBtn");
const clearBtn = $("#clearBtn");
const evalBtn = $("#evalBtn");
const evalSummaryCards = $("#evalSummaryCards");
const evalTable = $("#evalTable").querySelector("tbody");
const ingestionTable = $("#ingestionTable").querySelector("tbody");
const sourcesPanel = $("#sourcesPanel");
const settingsList = $("#settingsList");
const refreshIngestionBtn = $("#refreshIngestionBtn");
const messageTemplate = $("#messageTemplate");

let pendingFiles = [];

// ---------- Navigation (tab switching) ----------
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

function switchView(viewName) {
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === viewName));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${viewName}`));
  if (viewName === "ingestion") loadIngestionStatus();
  if (viewName === "settings") loadSettings();
}

// ---------- Upload ----------
dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", () => handleFiles(fileInput.files));

const ALLOWED_EXT = [".pdf", ".txt", ".md", ".markdown"];

function handleFiles(fileList) {
  pendingFiles = Array.from(fileList).filter((f) =>
    ALLOWED_EXT.some((ext) => f.name.toLowerCase().endsWith(ext))
  );
  uploadBtn.disabled = pendingFiles.length === 0;
  dropzone.querySelector(".dropzone-text").textContent =
    pendingFiles.length ? `${pendingFiles.length} file(s) selected` : "Click or drag PDF / TXT / Markdown files here";
}

uploadBtn.addEventListener("click", async () => {
  if (!pendingFiles.length) return;
  uploadBtn.disabled = true;
  uploadStatus.innerHTML = `<span class="status-line-text">Uploading and ingesting... this can take a minute.</span>`;

  const formData = new FormData();
  pendingFiles.forEach((f) => formData.append("files", f));

  try {
    const res = await fetch(`${API_BASE}/api/documents/upload`, { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    renderUploadResults(data);
    pendingFiles = [];
    fileInput.value = "";
    dropzone.querySelector(".dropzone-text").textContent = "Click or drag PDF / TXT / Markdown files here";
    await loadDocuments();
  } catch (err) {
    uploadStatus.innerHTML = `<span class="status-line-text error">Error: ${escapeHtml(err.message)}</span>`;
  } finally {
    uploadBtn.disabled = pendingFiles.length === 0;
  }
});

function renderUploadResults(data) {
  const icons = { ingested: "✅", duplicate: "⚠️", failed: "❌" };
  const rows = (data.file_results || []).map((r) => {
    let detail = "";
    if (r.status === "ingested") detail = `ingested, ${r.chunk_count} chunks`;
    else if (r.status === "duplicate") detail = "already in knowledge base — skipped";
    else detail = escapeHtml(r.error || "failed");
    return `<div class="upload-result-row ${r.status}">${icons[r.status] || ""} <strong>${escapeHtml(r.title)}</strong> — ${detail}</div>`;
  }).join("");
  uploadStatus.innerHTML = `<div class="status-line-text">${escapeHtml(data.message)}</div>${rows}`;
}

async function loadDocuments() {
  const res = await fetch(`${API_BASE}/api/documents`);
  const docs = await res.json();
  docList.innerHTML = "";
  if (!docs.length) {
    docList.innerHTML = `<li class="empty-hint">No documents yet.</li>`;
    return;
  }
  docs.forEach((d) => {
    const li = document.createElement("li");
    li.className = "doc-item";
    li.innerHTML = `
      <div>
        <div class="doc-title">📄 ${escapeHtml(d.title)}</div>
        <div class="doc-meta">${d.chunk_count} chunks · ${escapeHtml(d.source_type)}</div>
      </div>
      <button class="doc-remove" title="Remove" data-id="${d.id}">✕</button>
    `;
    docList.appendChild(li);
  });
  docList.querySelectorAll(".doc-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`${API_BASE}/api/documents/${btn.dataset.id}`, { method: "DELETE" });
      await loadDocuments();
    });
  });
}

// ---------- Ingestion Status view ----------
async function loadIngestionStatus() {
  ingestionTable.innerHTML = `<tr><td colspan="6" class="empty-hint">Loading...</td></tr>`;
  const res = await fetch(`${API_BASE}/api/documents`);
  const docs = await res.json();
  if (!docs.length) {
    ingestionTable.innerHTML = `<tr><td colspan="6" class="empty-hint">No documents ingested yet.</td></tr>`;
    return;
  }
  ingestionTable.innerHTML = docs.map((d) => `
    <tr>
      <td>${escapeHtml(d.title)}</td>
      <td>${escapeHtml(d.source_type)}</td>
      <td>${d.chunk_count}</td>
      <td><code>${escapeHtml(d.content_hash_prefix || "—")}</code></td>
      <td>${new Date(d.created_at).toLocaleString()}</td>
      <td><span class="status-pill">Ingested</span></td>
    </tr>
  `).join("");
}
refreshIngestionBtn.addEventListener("click", loadIngestionStatus);

// ---------- Settings view ----------
async function loadSettings() {
  settingsList.innerHTML = `<p class="empty-hint">Loading...</p>`;
  try {
    const res = await fetch(`${API_BASE}/api/settings`);
    const s = await res.json();
    const rows = [
      ["Embedding model", s.embedding_model],
      ["Embedding dimensions", s.embedding_dimensions],
      ["Generation model", s.generation_model],
      ["Judge model (evaluation only)", s.judge_model],
      ["Chunk size", s.chunk_size],
      ["Chunk overlap", s.chunk_overlap],
      ["Retrieval top-K", s.retrieval_top_k],
      ["Min similarity threshold", s.min_similarity_threshold],
      ["Max upload files per batch", s.max_upload_files],
      ["Gemini API key configured", s.api_key_configured ? "Yes" : "No"],
    ];
    settingsList.innerHTML = rows.map(([label, value]) => `
      <div class="settings-row">
        <span class="settings-label">${escapeHtml(label)}</span>
        <span class="settings-value">${escapeHtml(String(value))}</span>
      </div>
    `).join("") + `<p class="hint" style="margin-top:14px;">Secrets (API keys) are configured only via environment variables (.env) and are never exposed through this UI or API.</p>`;
  } catch (err) {
    settingsList.innerHTML = `<p class="empty-hint">Error loading settings: ${escapeHtml(err.message)}</p>`;
  }
}

// ---------- Chat ----------
let lastCitations = [];

async function loadChatHistory() {
  try {
    const res = await fetch(`${API_BASE}/api/chat/history?session_id=${SESSION_ID}`);
    if (!res.ok) return;
    const history = await res.json();
    if (!history.length) return;

    chatWindow.innerHTML = "";
    history.forEach((item) => {
      addUserMessage(item.question);
      addAssistantMessage({
        answer: item.answer,
        supported: item.supported,
        confidence: item.confidence,
        confidence_label: item.confidence_label,
        citations: item.citations || [],
        calculations: item.calculations || [],
      });
    });
    const last = history[history.length - 1];
    lastCitations = last.citations || [];
    renderSourcesPanel({
      question: last.question,
      citations: last.citations || [],
      security_flagged_sources: 0,
    });
  } catch (err) {
    // history is a nice-to-have on load — fail silently, chat still works
  }
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question) return;

  addUserMessage(question);
  questionInput.value = "";
  askBtn.disabled = true;
  const typingEl = addTypingIndicator();

  try {
    const res = await fetch(`${API_BASE}/api/chat/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: SESSION_ID }),
    });
    const data = await res.json();
    typingEl.remove();
    if (!res.ok) throw new Error(data.detail || "Request failed");
    addAssistantMessage(data);
    lastCitations = data.citations || [];
    renderSourcesPanel(data);
  } catch (err) {
    typingEl.remove();
    addAssistantMessage({
      answer: `Something went wrong: ${err.message}`,
      supported: "unsupported",
      citations: [],
    });
  } finally {
    askBtn.disabled = false;
  }
});

function renderSourcesPanel(data) {
  if (!data.citations || !data.citations.length) {
    sourcesPanel.innerHTML = `<p class="empty-hint">No sources were retrieved for the last question — the assistant said it could not confirm an answer.</p>`;
    return;
  }
  let html = `<p class="hint">Sources used for: <strong>${escapeHtml(data.question || "")}</strong></p>`;
  if (data.security_flagged_sources) {
    html += `<div class="security-notice">⚠ ${data.security_flagged_sources} retrieved chunk(s) were excluded as suspected prompt-injection content and not used.</div>`;
  }
  html += data.citations.map((c) => `
    <div class="citation-card citation-card-large">
      <div class="citation-head">
        <span>[${c.source_number}] ${escapeHtml(c.document_title)}${c.page ? ", p. " + c.page : ", chunk " + c.chunk_index}</span>
        <span class="citation-score">match ${(c.similarity * 100).toFixed(0)}%</span>
      </div>
      <div class="citation-preview">${escapeHtml(c.text_preview)}</div>
    </div>
  `).join("");
  sourcesPanel.innerHTML = html;
}

function addUserMessage(text) {
  const node = messageTemplate.content.cloneNode(true);
  const msg = node.querySelector(".message");
  msg.classList.add("user");
  msg.querySelector(".message-bubble").textContent = text;
  msg.querySelector(".citations").remove();
  chatWindow.appendChild(msg);
  scrollToBottom();
}

function addAssistantMessage(data) {
  const node = messageTemplate.content.cloneNode(true);
  const msg = node.querySelector(".message");
  msg.classList.add("assistant");

  const bubble = msg.querySelector(".message-bubble");
  const badge = document.createElement("span");
  badge.className = `badge ${data.supported === "supported" ? "supported" : "unsupported"}`;
  badge.textContent = data.supported === "supported" ? "Grounded answer" : "Cannot confirm";
  bubble.appendChild(badge);

  if (data.confidence_label) {
    const confBadge = document.createElement("span");
    confBadge.className = `badge confidence-${data.confidence_label.toLowerCase()}`;
    const pct = data.confidence != null ? ` (${Math.round(data.confidence * 100)}%)` : "";
    confBadge.textContent = `Confidence: ${data.confidence_label}${pct}`;
    bubble.appendChild(confBadge);
  }

  bubble.appendChild(document.createElement("br"));
  bubble.appendChild(document.createTextNode(data.answer));
  if (data.supported !== "supported") bubble.classList.add("unsupported");
  if (data.is_followup) {
    const note = document.createElement("div");
    note.style.fontSize = "11px";
    note.style.opacity = "0.65";
    note.style.marginTop = "6px";
    note.textContent = `Interpreted as follow-up: "${data.search_query}"`;
    bubble.appendChild(note);
  }

  if (data.calculations && data.calculations.length) {
    const calcWrap = document.createElement("div");
    calcWrap.className = "calc-wrap";
    data.calculations.forEach((c) => {
      const chip = document.createElement("div");
      chip.className = `calc-chip ${c.verified ? "verified" : "failed"}`;
      chip.innerHTML = c.verified
        ? `<span class="calc-icon">✓</span> ${escapeHtml(c.expression)} = <b>${escapeHtml(c.result)}</b>`
        : `<span class="calc-icon">⚠</span> could not verify: ${escapeHtml(c.expression)}`;
      calcWrap.appendChild(chip);
    });
    bubble.appendChild(calcWrap);
  }

  const citationsWrap = msg.querySelector(".citations");
  if (data.citations && data.citations.length) {
    data.citations.forEach((c) => {
      const card = document.createElement("div");
      card.className = "citation-card";
      card.innerHTML = `
        <div class="citation-head">
          <span>[${c.source_number}] ${escapeHtml(c.document_title)}${c.page ? ", p. " + c.page : ", chunk " + c.chunk_index}</span>
          <span class="citation-score">match ${(c.similarity * 100).toFixed(0)}%</span>
        </div>
        <div class="citation-preview">${escapeHtml(c.text_preview)}</div>
      `;
      citationsWrap.appendChild(card);
    });
  } else {
    const noSrc = document.createElement("div");
    noSrc.className = "no-sources";
    noSrc.textContent = "No supporting source found in the knowledge base.";
    citationsWrap.appendChild(noSrc);
  }

  chatWindow.appendChild(msg);
  renderMathIn(bubble);
  scrollToBottom();
}

function renderMathIn(el) {
  if (typeof renderMathInElement !== "function") return;
  try {
    renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
    });
  } catch (e) {
    // ignore — raw text is still readable
  }
}

function addTypingIndicator() {
  const el = document.createElement("div");
  el.className = "message assistant";
  el.innerHTML = `<div class="message-bubble"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`;
  chatWindow.appendChild(el);
  scrollToBottom();
  return el;
}

function scrollToBottom() {
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

clearBtn.addEventListener("click", async () => {
  await fetch(`${API_BASE}/api/chat/history?session_id=${SESSION_ID}`, { method: "DELETE" });
  chatWindow.innerHTML = `
    <div class="welcome-card">
    <img src="C.png" alt="Welcome to ChemRAG">
    </div>`;
  lastCitations = [];
  sourcesPanel.innerHTML = `<p class="empty-hint">Ask a question in the Chat view first — the sources it used will appear here.</p>`;
});

// ---------- Evaluation ----------
evalBtn.addEventListener("click", async () => {
  evalBtn.disabled = true;
  evalSummaryCards.innerHTML = `<p class="empty-hint">Running benchmark against Gemini judge... this can take a minute for many questions.</p>`;
  evalTable.innerHTML = `<tr><td colspan="7" class="empty-hint">Running...</td></tr>`;
  try {
    const res = await fetch(`${API_BASE}/api/eval/run`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Evaluation failed");
    const s = data.summary;
    evalSummaryCards.innerHTML = `
      <div class="eval-card"><span class="eval-card-value">${s.total_cases}</span><span class="eval-card-label">Cases run</span></div>
      <div class="eval-card"><span class="eval-card-value">${(s.rule_pass_rate * 100).toFixed(0)}%</span><span class="eval-card-label">Rule pass rate</span></div>
      <div class="eval-card"><span class="eval-card-value">${s.retrieval_hit_rate != null ? (s.retrieval_hit_rate * 100).toFixed(0) + "%" : "—"}</span><span class="eval-card-label">Retrieval hit rate</span></div>
      <div class="eval-card"><span class="eval-card-value">${s.avg_correctness_0_2}/2</span><span class="eval-card-label">Correctness</span></div>
      <div class="eval-card"><span class="eval-card-value">${s.avg_relevance_0_2}/2</span><span class="eval-card-label">Relevance</span></div>
      <div class="eval-card"><span class="eval-card-value">${s.avg_groundedness_0_2}/2</span><span class="eval-card-label">Groundedness</span></div>
    `;
    evalTable.innerHTML = data.results.map((r) => `
      <tr>
        <td>${escapeHtml(r.question)}</td>
        <td>${escapeHtml(r.expected_source || "—")}</td>
        <td>${r.rule_passed ? "✅" : "❌"}</td>
        <td>${r.retrieval_hit === null ? "—" : (r.retrieval_hit ? "✅" : "❌")}</td>
        <td>${r.judge_scores.correctness}/2</td>
        <td>${r.judge_scores.relevance}/2</td>
        <td>${r.judge_scores.groundedness}/2</td>
      </tr>
    `).join("");
  } catch (err) {
    evalSummaryCards.innerHTML = `<p class="empty-hint">Error: ${escapeHtml(err.message)}</p>`;
    evalTable.innerHTML = `<tr><td colspan="7" class="empty-hint">Run failed.</td></tr>`;
  } finally {
    evalBtn.disabled = false;
  }
});

// ---------- Init ----------
loadDocuments();
loadChatHistory();
