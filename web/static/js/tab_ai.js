/* ==============================================================================
   Telua Web - AI Agent Tab Module (Vanilla JS)
   Chat UI for the tool-calling agent backend (web/telua_web_ai.py).
   Shows the agent's tool calls (tel/adb/file) inline as it works.
   ============================================================================== */
"use strict";

let _aiInitialized = false;
let _aiBusy = false;
let _aiHistory = []; // [{ role: "user"|"assistant", content }]

function aiSetBusy(busy) {
  _aiBusy = busy;
  const btn = $("#btn-ai-send");
  const badge = $("#ai-status-badge");
  if (btn) {
    btn.disabled = busy;
    btn.textContent = busy ? "⏳ Thinking…" : "➤ Send";
  }
  if (badge) {
    badge.textContent = busy ? "Agent running" : "Idle";
    badge.className = busy ? "run-badge running" : "run-badge";
  }
}

function aiAppendMsg(role, html) {
  const log = $("#ai-chat-log");
  if (!log) return;
  const div = document.createElement("div");
  div.className = `ai-msg ai-msg-${role === "user" ? "user" : "assistant"}`;
  div.innerHTML = html;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function aiAppendToolTrace(tool, args, output) {
  const log = $("#ai-chat-log");
  if (!log) return;
  const div = document.createElement("div");
  div.className = "ai-msg ai-msg-tool";
  const argStr = Object.entries(args || {}).map(([k, v]) => `${k}=${v}`).join(" ");
  const outEsc = esc(String(output || "")).slice(0, 1200);
  div.innerHTML =
    `<div class="ai-tool-head">🔧 <b>${esc(tool)}</b> <span class="mono">${esc(argStr)}</span></div>` +
    `<pre class="ai-tool-out">${outEsc || "(no output)"}</pre>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

async function aiSend() {
  if (_aiBusy) return;
  const input = $("#ai-input");
  const msg = (input?.value || "").trim();
  if (!msg) return;
  input.value = "";

  const targetInput = $("#ai-target-file");
  const targetFile = (targetInput?.value || "").trim();
  let fullMsg = msg;
  if (targetFile && !msg.includes(targetFile)) {
    fullMsg = `[Target File: ${targetFile}]\n${msg}`;
  }

  aiAppendMsg("user", esc(msg));
  _aiHistory.push({ role: "user", content: fullMsg });
  aiSetBusy(true);

  try {
    const res = await api("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message: fullMsg, history: _aiHistory.slice(-10) }),
    });
    (res.trace || []).forEach(t => aiAppendToolTrace(t.tool, t.args, t.output));
    const answer = res.answer || res.error || "(no answer)";
    aiAppendMsg("assistant", esc(answer).replace(/\n/g, "<br>"));
    _aiHistory.push({ role: "assistant", content: answer });
  } catch (err) {
    aiAppendMsg("assistant", `⚠️ <b>Lỗi:</b> ${esc(err.message)}`);
  } finally {
    aiSetBusy(false);
    input?.focus();
  }
}

async function initAI() {
  if (_aiInitialized) return;
  _aiInitialized = true;

  $("#btn-ai-send")?.addEventListener("click", aiSend);
  $("#ai-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      aiSend();
    }
  });
  $("#btn-ai-clear")?.addEventListener("click", () => {
    _aiHistory = [];
    const log = $("#ai-chat-log");
    if (log) log.innerHTML =
      `<div class="ai-msg ai-msg-assistant">🧹 Hội thoại đã xóa. Bạn muốn AI agent làm gì?</div>`;
  });

  // ---- Target Path (File / Folder) Quick Actions ----
  $("#btn-ai-target-read")?.addEventListener("click", () => {
    const targetInput = $("#ai-target-file");
    const targetPath = (targetInput?.value || "").trim();
    if (!targetPath) {
      toast("Target Path", "Vui lòng nhập đường dẫn file hoặc thư mục trước.", "err");
      targetInput?.focus();
      return;
    }
    const isFolder = !targetPath.includes(".") || targetPath.endsWith("/") || targetPath.endsWith("\\");
    const input = $("#ai-input");
    if (input) {
      input.value = isFolder
        ? `Hãy dùng list_files quét cấu trúc thư mục '${targetPath}', đọc lướt các file chính và tóm tắt kiến trúc của thư mục này.`
        : `Hãy đọc và phân tích toàn diện mã nguồn file: ${targetPath}`;
      aiSend();
    }
  });

  $("#btn-ai-target-code")?.addEventListener("click", () => {
    const targetInput = $("#ai-target-file");
    const targetPath = (targetInput?.value || "").trim();
    if (!targetPath) {
      toast("Target Path", "Vui lòng nhập đường dẫn file hoặc thư mục cần lập trình trước.", "err");
      targetInput?.focus();
      return;
    }
    const isFolder = !targetPath.includes(".") || targetPath.endsWith("/") || targetPath.endsWith("\\");
    const input = $("#ai-input");
    const userPrompt = (input?.value || "").trim();

    let promptText = "";
    if (isFolder) {
      promptText = userPrompt
        ? `Target Folder: '${targetPath}'. Yêu cầu lập trình các file trong thư mục: ${userPrompt}. Hãy dùng list_files để kiểm tra các file hiện có, sau đó lần lượt tạo mới hoặc cập nhật các file liên quan (dùng write_file/edit_file), và dùng run_tel để build/kiểm tra cú pháp sau khi code xong.`
        : `Target Folder: '${targetPath}'. Hãy quét thư mục này (dùng list_files), đối chiếu với MCP Skills (telua_skill & claude-code-java) và lập trình/hoàn thiện các file cần thiết trong thư mục bằng write_file hoặc edit_file.`;
    } else {
      promptText = userPrompt 
        ? `Hãy lập trình/hoàn thiện code cho file ${targetPath} theo yêu cầu sau: ${userPrompt}. Hãy sử dụng công cụ write_file hoặc edit_file để cập nhật trực tiếp vào file, và gọi run_tel để build/kiểm tra cú pháp nếu cần.`
        : `Hãy kiểm tra file ${targetPath}, đối chiếu với các mẫu kiến trúc trong MCP Skills (telua_skill & claude-code-java) và sử dụng công cụ write_file hoặc edit_file để hoàn thiện code trực tiếp vào file này.`;
    }

    if (input) {
      input.value = promptText;
      aiSend();
    }
  });

  // ---- Provider config modal (⚙ Config) ----
  $("#btn-ai-config")?.addEventListener("click", openAIConfigModal);
  $("#btn-ai-cfg-cancel")?.addEventListener("click", () => $("#modal-ai-config")?.classList.add("hidden"));
  $("#ai-cfg-provider-select")?.addEventListener("change", () => {
    renderAIConfigModels();
  });
  $("#btn-ai-save-guardrails")?.addEventListener("click", saveAIGuardrails);
  $("#btn-ai-key-save")?.addEventListener("click", saveAIKey);
  $("#btn-ai-cfg-save")?.addEventListener("click", saveAIConfigJson);
  $("#btn-ai-mcp-sync")?.addEventListener("click", async () => {
    const btn = $("#btn-ai-mcp-sync");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Syncing...";
    }
    try {
      const res = await api("/api/ai/mcp/sync", { method: "POST" });
      if (res && res.ok) {
        toast("MCP Sync Thành Công 🎉", `Đã lập chỉ mục ${res.indexed} skills vào ChromaDB (${res.collection}).`, "ok", 4500);
        await loadAIMcpStatus();
      } else {
        toast("Sync Error", res.error || "Không thể đồng bộ skills", "err");
      }
    } catch (err) {
      toast("Sync Error", err.message, "err");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "🔄 Sync to ChromaDB";
      }
    }
  });
  $("#btn-ai-mcp-save-sources")?.addEventListener("click", async () => {
    try {
      await api("/api/ai/mcp/config", {
        method: "POST",
        body: JSON.stringify({ sources: _aiMcpSources }),
      });
      toast("Đã Lưu Danh Sách Nguồn 💾", "Các thư mục kỹ năng đã được lưu vào cấu hình.", "ok", 3000);
      await loadAIMcpStatus();
    } catch (err) {
      toast("Lỗi Lưu Nguồn", err.message, "err");
    }
  });

  $("#btn-ai-mcp-add-source")?.addEventListener("click", () => {
    const nameInput = $("#ai-mcp-new-name");
    const pathInput = $("#ai-mcp-new-path");
    const urlInput = $("#ai-mcp-new-url");
    if (!pathInput || !pathInput.value.trim()) {
      toast("Thiếu đường dẫn", "Vui lòng nhập đường dẫn thư mục hoặc repository.", "err");
      return;
    }
    const path = pathInput.value.trim();
    const name = (nameInput?.value.trim()) || path.split("/").pop().split("\\").pop() || "Custom Source";
    const url = urlInput?.value.trim() || "";
    const cleanId = path.replace(/[\\/]/g, "_").toLowerCase().replace(/[^a-z0-9_]/g, "");

    _aiMcpSources.push({
      id: cleanId,
      name: name,
      local_path: path,
      repo_url: url,
      enabled: true,
      exists: true,
      count: 0,
    });

    if (nameInput) nameInput.value = "";
    if (pathInput) pathInput.value = "";
    if (urlInput) urlInput.value = "";

    renderAIMcpSourcesList();
    toast("Đã thêm nguồn ➕", "Đã thêm vào danh sách tạm. Nhấn '💾 Lưu danh sách nguồn' để áp dụng.", "ok", 3500);
  });

  $("#btn-ai-mcp-save-schedule")?.addEventListener("click", async () => {
    const sel = $("#ai-mcp-schedule-select");
    if (!sel) return;
    const val = sel.value;
    let payload = {};
    if (val === "manual") {
      payload = { auto_sync_enabled: false };
    } else if (val === "startup_only") {
      payload = { auto_sync_enabled: true, sync_on_startup: true, sync_interval_hours: 0 };
    } else {
      payload = { auto_sync_enabled: true, sync_on_startup: true, sync_interval_hours: parseFloat(val) || 3 };
    }
    try {
      await api("/api/ai/mcp/config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      toast("Lịch Đã Lưu ⏱", "Đã cập nhật chu kỳ đồng bộ ChromaDB.", "ok", 3500);
      await loadAIMcpStatus();
    } catch (err) {
      toast("Lỗi Lưu Lịch", err.message, "err");
    }
  });
  $("#btn-ai-load-template")?.addEventListener("click", async () => {
    try {
      const res = await api("/api/ai/template");
      if (res && Array.isArray(res.template) && res.template.length > 0) {
        _aiProviders = res.template;
        const jsonArea = $("#ai-cfg-json");
        if (jsonArea) jsonArea.value = JSON.stringify(_aiProviders, null, 2);
        const provSel = $("#ai-cfg-provider-select");
        if (provSel) {
          provSel.innerHTML = _aiProviders.map(p =>
            `<option value="${esc(p.name)}">${esc(p.name)}</option>`
          ).join("");
          renderAIConfigModels();
        }
        toast("Template Loaded 📋", "Mẫu cấu hình JSON đã nạp từ server file. Bấm '💾 Save JSON' để áp dụng.", "ok", 4000);
      } else {
        toast("Load Template", "Không tìm thấy mẫu cấu hình trên server.", "err");
      }
    } catch (err) {
      toast("Load Template Error", err.message, "err");
    }
  });

  // Load provider/model status
  try {
    const st = await api("/api/ai/status");
    const badge = $("#ai-model-badge");
    if (badge) {
      badge.textContent = `model: ${st.model}`;
      badge.title = `provider: ${st.provider} · api key: ${st.has_api_key ? "✓ set" : "✗ missing"} · sdk: ${st.sdk_installed}`;
    }
    const isBuiltin = st.sdk_installed === "builtin"; // chat-completions via urllib, no SDK needed
    if (isBuiltin) {
      if (!st.has_api_key) {
        aiAppendMsg("assistant",
          `ℹ️ Endpoint nội bộ chưa có API key — nếu gateway yêu cầu auth, mở <b>⚙ Config</b> để nhập key.`);
      }
    } else if (!st.has_api_key || st.sdk_installed === "missing") {
      aiAppendMsg("assistant",
        `⚠️ <b>Chưa sẵn sàng:</b> ` +
        (st.sdk_installed === "missing"
          ? `thiếu SDK (<code>pip install ${st.provider === "openai" ? "openai" : "anthropic"}</code>) — hoặc dùng <b>⚙ Config</b> để thêm custom endpoint (không cần SDK).`
          : `thiếu API key (set <code>TELUA_AI_API_KEY</code> hoặc mở <b>⚙ Config</b>).`));
    }
  } catch { /* status optional */ }
}

/* ---------------- Provider config modal ---------------- */
let _aiProviders = [];
let _aiActiveProvider = "";
let _aiActiveModel = "";

async function openAIConfigModal() {
  try {
    // Fetch BOTH: status (active selection) and raw config (full JSON with
    // apiKey fields — the status endpoint strips keys for display).
    const [st, raw] = await Promise.all([
      api("/api/ai/status"),
      api("/api/ai/config"),
    ]);
    _aiProviders = raw.providers || st.providers || [];
    _aiActiveProvider = st.active_provider || (_aiProviders[0] && _aiProviders[0].name) || "";
    const entry = _aiProviders.find(p => p.name === _aiActiveProvider);
    _aiActiveModel = st.active_model || (entry && entry.models && entry.models[0] && entry.models[0].id) || "";

    const provSel = $("#ai-cfg-provider-select");
    if (provSel) {
      provSel.innerHTML = _aiProviders.map(p =>
        `<option value="${esc(p.name)}" ${p.name === _aiActiveProvider ? "selected" : ""}>${esc(p.name)}</option>`
      ).join("") || `<option value="">(no providers configured)</option>`;
    }
    renderAIConfigModels();

    const jsonArea = $("#ai-cfg-json");
    if (jsonArea) jsonArea.value = JSON.stringify(_aiProviders, null, 2);

    updateAIKeyStatus(entry);
    loadAIMcpStatus();
    loadAIGuardrails();
    $("#modal-ai-config")?.classList.remove("hidden");
  } catch (err) {
    toast("AI Config", err.message, "err");
  }
}

async function loadAIGuardrails() {
  try {
    const res = await api("/api/ai/guardrails");
    if (res && res.guardrails) {
      const g = res.guardrails;
      const iterSel = $("#ai-guard-max-iter");
      if (iterSel && g.max_iterations) iterSel.value = String(g.max_iterations);
      const linesSel = $("#ai-guard-max-lines");
      if (linesSel && g.max_lines_per_read) linesSel.value = String(g.max_lines_per_read);
      const charsSel = $("#ai-guard-max-chars");
      if (charsSel && g.max_tool_output_chars) charsSel.value = String(g.max_tool_output_chars);
      const loopCb = $("#ai-guard-loop-breaker");
      if (loopCb && g.loop_breaker_enabled !== undefined) loopCb.checked = Boolean(g.loop_breaker_enabled);
    }
  } catch {
    /* ignore */
  }
}

async function saveAIGuardrails() {
  const iter = parseInt($("#ai-guard-max-iter")?.value || "5", 10);
  const lines = parseInt($("#ai-guard-max-lines")?.value || "150", 10);
  const chars = parseInt($("#ai-guard-max-chars")?.value || "6000", 10);
  const loopBreaker = Boolean($("#ai-guard-loop-breaker")?.checked);

  try {
    const res = await api("/api/ai/guardrails", {
      method: "POST",
      body: JSON.stringify({
        max_iterations: iter,
        max_lines_per_read: lines,
        max_tool_output_chars: chars,
        loop_breaker_enabled: loopBreaker,
      }),
    });
    if (res && res.ok) {
      toast("Đã lưu Guardrails 🛡", `Max: ${iter} turns | Max read: ${lines} dòng | Loop Breaker: ${loopBreaker ? "BẬT" : "TẮT"}`, "ok", 3500);
    }
  } catch (err) {
    toast("Lỗi Guardrails", err.message, "err");
  }
}

function renderAIConfigModels() {
  const provSel = $("#ai-cfg-provider-select");
  const modelSel = $("#ai-cfg-model-select");
  if (!provSel || !modelSel) return;
  _aiActiveProvider = provSel.value;
  const entry = _aiProviders.find(p => p.name === _aiActiveProvider);
  const models = (entry && entry.models) || [];
  modelSel.innerHTML = models.map(m =>
    `<option value="${esc(m.id)}" ${m.id === _aiActiveModel ? "selected" : ""}>${esc(m.name || m.id)}</option>`
  ).join("") || `<option value="">(no models)</option>`;
  const info = $("#ai-cfg-provider-info");
  if (info) info.textContent = entry ? `apiType: ${entry.apiType || "chat-completions"}` : "";
  const minfo = $("#ai-cfg-model-info");
  const m = models.find(x => x.id === modelSel.value);
  if (minfo) minfo.textContent = m ? `url: ${m.url || "—"}${m.url1 ? "  |  fallback: " + m.url1 : ""} · toolCalling: ${m.toolCalling ? "✓" : "✗"}` : "";
  updateAIKeyStatus(entry);
}

function updateAIKeyStatus(entry) {
  const el = $("#ai-cfg-key-status");
  if (el) el.textContent = entry
    ? (entry.apiKey ? "✓ API key đã lưu cho provider này." : "✗ Chưa có API key (endpoint nội bộ có thể không cần).")
    : "";
}

async function saveAIKey() {
  const provSel = $("#ai-cfg-provider-select");
  const keyInput = $("#ai-cfg-key-input");
  if (!provSel?.value) return;
  try {
    await api("/api/ai/key", {
      method: "POST",
      body: JSON.stringify({ provider: provSel.value, apiKey: keyInput?.value || "" }),
    });
    const entry = _aiProviders.find(p => p.name === provSel.value);
    if (entry) {
      entry.apiKey = keyInput?.value || "";
      // Keep the raw JSON textarea in sync so a later 'Save JSON' keeps the key.
      const jsonArea = $("#ai-cfg-json");
      if (jsonArea) jsonArea.value = JSON.stringify(_aiProviders, null, 2);
    }
    updateAIKeyStatus(entry);
    if (keyInput) keyInput.value = "";
    toast("API key saved 🔐", `Key updated for ${provSel.value}.`, "ok", 3500);
  } catch (err) {
    toast("Save key failed", err.message, "err");
  }
}

async function saveAIConfigJson() {
  const jsonArea = $("#ai-cfg-json");
  const provSel = $("#ai-cfg-provider-select");
  const modelSel = $("#ai-cfg-model-select");
  let providers;
  try {
    providers = JSON.parse(jsonArea?.value || "[]");
  } catch (err) {
    toast("Invalid JSON", err.message, "err");
    return;
  }
  try {
    await api("/api/ai/config", {
      method: "POST",
      body: JSON.stringify({
        providers,
        activeProvider: provSel?.value || "",
        activeModel: modelSel?.value || "",
      }),
    });
    toast("AI config saved 💾", "Provider registry written to config/ai_providers.json", "ok", 4000);
    $("#modal-ai-config")?.classList.add("hidden");
    initAI._statusLoaded = false;
    // Refresh model badge
    try {
      const st = await api("/api/ai/status");
      const badge = $("#ai-model-badge");
      if (badge) badge.textContent = `model: ${st.model}`;
    } catch { /* ignore */ }
  } catch (err) {
    toast("Save failed", err.message, "err");
  }
}

/* ---------------- MCP Skill & ChromaDB Integration ---------------- */
let _aiMcpSources = [];

function renderAIMcpSourcesList() {
  const container = $("#ai-mcp-sources-list");
  if (!container) return;
  if (!_aiMcpSources.length) {
    container.innerHTML = `<div class="meta" style="padding:8px;text-align:center;">(Chưa có nguồn kỹ năng nào. Hãy nhập thông tin bên dưới và nhấn "➕ Thêm")</div>`;
    return;
  }
  container.innerHTML = _aiMcpSources.map((s, idx) => {
    const isOk = s.exists !== false;
    const statusChip = isOk 
      ? `<span class="chip ok" style="font-size:10px;padding:1px 6px;">${s.count || 0} skills</span>`
      : `<span class="chip err" style="font-size:10px;padding:1px 6px;" title="${esc(s.resolved_path || 'Không tìm thấy thư mục trên ổ cứng')}">⚠️ Thư mục không tồn tại</span>`;
    const gitLink = s.repo_url 
      ? `<a href="${esc(s.repo_url)}" target="_blank" style="color:var(--accent);font-size:11px;text-decoration:none;" title="Mở Git repo">↗ Git</a>` 
      : '';
    
    return `
      <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg);border:1px solid ${s.enabled ? 'var(--border)' : 'rgba(255,255,255,0.06)'};border-radius:6px;opacity:${s.enabled ? '1' : '0.6'};">
        <input type="checkbox" class="ai-mcp-src-toggle" data-idx="${idx}" ${s.enabled ? 'checked' : ''} title="${s.enabled ? 'Đang BẬT nguồn này' : 'Đang TẮT nguồn này'}">
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <strong style="font-size:11px;color:var(--text);">${esc(s.name || s.id)}</strong>
            ${statusChip}
            ${gitLink}
          </div>
          <div class="mono meta" style="font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px;" title="${esc(s.resolved_path || s.local_path)}">
            ${esc(s.local_path)}
          </div>
        </div>
        <button class="btn danger ai-mcp-src-del" data-idx="${idx}" style="padding:2px 7px;font-size:11px;" title="Xóa nguồn này">🗑</button>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".ai-mcp-src-toggle").forEach(cb => {
    cb.addEventListener("change", (e) => {
      const idx = parseInt(e.target.dataset.idx, 10);
      if (_aiMcpSources[idx]) {
        _aiMcpSources[idx].enabled = e.target.checked;
        renderAIMcpSourcesList();
      }
    });
  });

  container.querySelectorAll(".ai-mcp-src-del").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const idx = parseInt(e.target.dataset.idx, 10);
      const name = _aiMcpSources[idx]?.name || "nguồn này";
      if (!confirm(`Bạn có chắc muốn xóa nguồn "${name}" khỏi danh sách?`)) return;
      _aiMcpSources.splice(idx, 1);
      renderAIMcpSourcesList();
    });
  });
}

async function loadAIMcpStatus() {
  try {
    const [st, cfgRes, skillsRes] = await Promise.all([
      api("/api/ai/chroma/status"),
      api("/api/ai/mcp/config"),
      api("/api/ai/mcp/skills"),
    ]);

    const pill = $("#ai-mcp-status-pill");
    if (pill) {
      if (st.installed) {
        pill.textContent = `ChromaDB: ${st.doc_count || 0} docs`;
        pill.className = "chip ok";
      } else {
        pill.textContent = "ChromaDB: uninitialized";
        pill.className = "chip";
      }
    }

    _aiMcpSources = cfgRes.sources || [];
    renderAIMcpSourcesList();

    const schedSel = $("#ai-mcp-schedule-select");
    if (schedSel && cfgRes.config) {
      if (!cfgRes.config.auto_sync_enabled) {
        schedSel.value = "manual";
      } else if (!cfgRes.config.sync_interval_hours) {
        schedSel.value = "startup_only";
      } else {
        schedSel.value = String(cfgRes.config.sync_interval_hours || "3");
      }
    }

    const info = $("#ai-mcp-sync-info");
    if (info) {
      const syncTime = cfgRes.config?.last_sync || "chưa đồng bộ";
      const total = cfgRes.skills_count || (skillsRes.skills && skillsRes.skills.length) || 0;
      const sched = cfgRes.config?.auto_sync_enabled ? `Mỗi ${cfgRes.config.sync_interval_hours || 3}h` : "thủ công";
      const activeCount = (_aiMcpSources || []).filter(s => s.enabled).length;
      info.textContent = `Tổng cộng ${total} skills (${activeCount}/${_aiMcpSources.length} nguồn bật) · Lịch: ${sched} · Lần sync cuối: ${syncTime}`;
    }

    const countEl = $("#ai-mcp-count");
    if (countEl) countEl.textContent = String((skillsRes.skills || []).length);

    const listEl = $("#ai-mcp-skills-list");
    if (listEl && Array.isArray(skillsRes.skills)) {
      listEl.innerHTML = skillsRes.skills.map(s =>
        `<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;justify-content:space-between;align-items:baseline;gap:8px;">
          <div>
            <span style="color:var(--accent);font-weight:600;">[${esc(s.source_id || 'skill')}:${esc(s.category)}]</span>
            <span class="mono">${esc(s.name)}</span>
            ${s.title && s.title !== s.name ? `<span style="color:var(--text);opacity:0.85;margin-left:4px;">— ${esc(s.title)}</span>` : ''}
          </div>
          <span style="color:#8b949e;font-size:10px;flex-shrink:0;">${Math.round(s.size_bytes / 1024 * 10) / 10}KB</span>
        </div>`
      ).join("") || "(chưa có file skill)";
    }
  } catch (err) {
    const info = $("#ai-mcp-sync-info");
    if (info) info.textContent = `Lỗi đọc MCP config: ${err.message}`;
  }
}
