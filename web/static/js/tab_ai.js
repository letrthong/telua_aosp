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
