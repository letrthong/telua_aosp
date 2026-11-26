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

  aiAppendMsg("user", esc(msg));
  _aiHistory.push({ role: "user", content: msg });
  aiSetBusy(true);

  try {
    const res = await api("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message: msg, history: _aiHistory.slice(-10) }),
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

  // ---- Provider config modal (⚙ Config) ----
  $("#btn-ai-config")?.addEventListener("click", openAIConfigModal);
  $("#btn-ai-cfg-cancel")?.addEventListener("click", () => $("#modal-ai-config")?.classList.add("hidden"));
  $("#ai-cfg-provider-select")?.addEventListener("change", () => {
    renderAIConfigModels();
  });
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
  $("#btn-ai-mcp-save-path")?.addEventListener("click", async () => {
    const pathInput = $("#ai-mcp-repo-path");
    if (!pathInput) return;
    try {
      await api("/api/ai/mcp/config", {
        method: "POST",
        body: JSON.stringify({ local_path: pathInput.value }),
      });
      toast("MCP Path Saved 💾", "Đã lưu đường dẫn telua_skill repository.", "ok", 3000);
      await loadAIMcpStatus();
    } catch (err) {
      toast("Save Path Failed", err.message, "err");
    }
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
    $("#modal-ai-config")?.classList.remove("hidden");
  } catch (err) {
    toast("AI Config", err.message, "err");
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

    const pathInput = $("#ai-mcp-repo-path");
    if (pathInput && cfgRes.config?.local_path) {
      pathInput.value = cfgRes.config.local_path;
    }

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
      info.textContent = `Repo có ${total} skills (${(cfgRes.categories || []).join(", ")}) · Lịch: ${sched} · Lần sync cuối: ${syncTime}`;
    }

    const countEl = $("#ai-mcp-count");
    if (countEl) countEl.textContent = String((skillsRes.skills || []).length);

    const listEl = $("#ai-mcp-skills-list");
    if (listEl && Array.isArray(skillsRes.skills)) {
      listEl.innerHTML = skillsRes.skills.map(s =>
        `<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.06);">
          <span style="color:var(--accent);font-weight:600;">[${esc(s.category)}]</span>
          <span class="mono">${esc(s.name)}</span>
          <span style="color:#8b949e;font-size:10px;">(${Math.round(s.size_bytes / 1024 * 10) / 10}KB)</span>
        </div>`
      ).join("") || "(chưa có file skill)";
    }
  } catch (err) {
    const info = $("#ai-mcp-sync-info");
    if (info) info.textContent = `Lỗi đọc MCP config: ${err.message}`;
  }
}
