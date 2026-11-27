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
    loadAITokenUsage();
  } catch (err) {
    aiAppendMsg("assistant", `⚠️ <b>Error:</b> ${esc(err.message)}`);
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
      `<div class="ai-msg ai-msg-assistant">🧹 Conversation cleared. How can I help you with AOSP?</div>`;
  });

  // ---- Target Path (File / Folder) Quick Actions ----
  $("#btn-ai-target-read")?.addEventListener("click", () => {
    const targetInput = $("#ai-target-file");
    const targetPath = (targetInput?.value || "").trim();
    if (!targetPath) {
      toast("Target Path", "Please enter a file or directory path first.", "err");
      targetInput?.focus();
      return;
    }
    const isFolder = !targetPath.includes(".") || targetPath.endsWith("/") || targetPath.endsWith("\\");
    const input = $("#ai-input");
    if (input) {
      input.value = isFolder
        ? `Use list_files to scan directory structure '${targetPath}', inspect key files, and summarize the architecture of this component.`
        : `Read and perform a comprehensive code analysis of file: ${targetPath}`;
      aiSend();
    }
  });

  $("#btn-ai-target-code")?.addEventListener("click", () => {
    const targetInput = $("#ai-target-file");
    const targetPath = (targetInput?.value || "").trim();
    if (!targetPath) {
      toast("Target Path", "Please enter a file or directory path to code.", "err");
      targetInput?.focus();
      return;
    }
    const isFolder = !targetPath.includes(".") || targetPath.endsWith("/") || targetPath.endsWith("\\");
    const input = $("#ai-input");
    const userPrompt = (input?.value || "").trim();

    let promptText = "";
    if (isFolder) {
      promptText = userPrompt
        ? `Target Folder: '${targetPath}'. Coding request for directory: ${userPrompt}. Use list_files to inspect existing files, then create or update relevant files (using write_file/edit_file), and execute run_tel to build/verify syntax once complete.`
        : `Target Folder: '${targetPath}'. Scan this directory (using list_files), consult MCP Skills (telua_skill & claude-code-java) and implement/refactor necessary files using write_file or edit_file.`;
    } else {
      promptText = userPrompt
        ? `Implement/refactor code for file ${targetPath} based on: ${userPrompt}. Use write_file or edit_file to apply changes directly, and call run_tel to build/verify syntax if applicable.`
        : `Inspect file ${targetPath}, align with architecture patterns in MCP Skills (telua_skill & claude-code-java), and use write_file or edit_file to complete the code directly.`;
    }

    if (input) {
      input.value = promptText;
      aiSend();
    }
  });

  // ---- Provider config modal (⚙ Config) ----
  $("#btn-ai-config")?.addEventListener("click", openAIConfigModal);
  $("#ai-header-token-badge")?.addEventListener("click", openAIConfigModal);
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
      // Returns immediately; the sync runs in a background thread on the server.
      const res = await api("/api/ai/mcp/sync", { method: "POST", body: JSON.stringify({ incremental: true }) });
      if (res && res.ok) {
        if (res.already_running) toast("Sync Running", "A sync is already in progress — showing its progress.", "ok", 3000);
        renderAIMcpSyncProgress(res.progress);
        startAIMcpSyncPolling();
      } else {
        toast("Sync Error", res.error || "Failed to start sync", "err");
        setAIMcpSyncButtons(false);
      }
    } catch (err) {
      toast("Sync Error", err.message, "err");
      setAIMcpSyncButtons(false);
    }
  });
  $("#btn-ai-mcp-sync-cancel")?.addEventListener("click", async () => {
    if (!confirm("Stop the running ChromaDB sync? Already indexed batches are kept and the next sync resumes incrementally.")) return;
    try {
      const res = await api("/api/ai/mcp/sync/cancel", { method: "POST" });
      if (!res.ok) toast("Cancel", res.error || "No sync running", "err");
    } catch (err) {
      toast("Cancel Error", err.message, "err");
    }
  });
  $("#btn-ai-mcp-save-sources")?.addEventListener("click", async () => {
    try {
      await api("/api/ai/mcp/config", {
        method: "POST",
        body: JSON.stringify({ sources: _aiMcpSources }),
      });
      toast("MCP Sources Saved 💾", "Private sources saved to overlay (git-ignored), public sources saved to global config.", "ok", 4000);
      await loadAIMcpStatus();
    } catch (err) {
      toast("Save Sources Error", err.message, "err");
    }
  });

  $("#btn-ai-mcp-add-source")?.addEventListener("click", () => {
    const nameInput = $("#ai-mcp-new-name");
    const pathInput = $("#ai-mcp-new-path");
    const urlInput = $("#ai-mcp-new-url");
    const visInput = $("#ai-mcp-new-visibility");
    const projInput = $("#ai-mcp-new-project");
    const verInput = $("#ai-mcp-new-version");
    if (!pathInput || !pathInput.value.trim()) {
      toast("Missing Path", "Please enter a directory or repository path.", "err");
      return;
    }
    const path = pathInput.value.trim();
    const name = (nameInput?.value.trim()) || path.split("/").pop().split("\\").pop() || "Custom Source";
    const url = urlInput?.value.trim() || "";
    const cleanId = path.replace(/[\\/]/g, "_").toLowerCase().replace(/[^a-z0-9_]/g, "");
    const visibility = visInput?.value || "private";
    const isPrivate = (visibility === "private");
    const project = (projInput?.value.trim()) || "aosp_aaos";
    let aospVer = verInput?.value || "";
    if (aospVer === "auto" || aospVer === "__manage__" || aospVer === "custom") aospVer = "";
    const verObj = _aiAospVersions.find(v => v.id === (verInput?.value || ""));
    const apiLevel = verObj?.api_level || null;

    _aiMcpSources.push({
      id: cleanId,
      name: name,
      local_path: path,
      repo_url: url,
      project: project,
      aosp_version: aospVer,
      api_level: apiLevel,
      enabled: true,
      exists: true,
      count: 0,
      visibility: visibility,
      is_private: isPrivate,
    });

    if (nameInput) nameInput.value = "";
    if (pathInput) pathInput.value = "";
    if (urlInput) urlInput.value = "";

    renderAIMcpSourcesList();
    toast(`Added ${isPrivate ? '🔒 Private' : '🌐 Public'} source ➕`, "Click '💾 Save Sources' to persist configuration.", "ok", 3500);
  });

  // ---- AOSP Versions Manager Dialog ----
  $("#btn-ai-manage-versions")?.addEventListener("click", openAospVersionsModal);
  $("#ai-mcp-new-version")?.addEventListener("change", (e) => {
    if (e.target.value === "__manage__") {
      e.target.value = "auto";
      openAospVersionsModal();
    }
  });
  $("#btn-ai-version-close")?.addEventListener("click", () => {
    $("#modal-aosp-versions")?.classList.add("hidden");
    renderAIAospVersionsSelect();
  });
  $("#btn-ai-version-add")?.addEventListener("click", () => {
    const idInput = $("#ai-version-new-id");
    const nameInput = $("#ai-version-new-name");
    const apiInput = $("#ai-version-new-api");
    const id = (idInput?.value || "").trim().toLowerCase().replace(/[^a-z0-9_\-]/g, "_");
    if (!id) {
      toast("Invalid ID", "Please enter a valid version ID (alphanumeric, e.g. a14_qssi).", "err");
      idInput?.focus();
      return;
    }
    if (_aiAospVersions.some(v => v.id === id)) {
      toast("Duplicate ID", `AOSP version ID "${id}" already exists.`, "err");
      idInput?.focus();
      return;
    }
    const name = (nameInput?.value || "").trim() || id;
    const apiLevel = apiInput?.value ? parseInt(apiInput.value, 10) : null;

    _aiAospVersions.push({
      id: id,
      name: name,
      api_level: apiLevel,
      is_custom: true,
      is_auto: false,
    });

    if (idInput) idInput.value = "";
    if (nameInput) nameInput.value = "";
    if (apiInput) apiInput.value = "";

    renderAIAospVersionsList();
    renderAIAospVersionsSelect(id);
    toast("Version Added 🏷️", `Added "${name}" (${id}). Click "Save Versions" to persist.`, "ok", 3000);
  });

  $("#btn-ai-version-save")?.addEventListener("click", async () => {
    const btn = $("#btn-ai-version-save");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Saving...";
    }
    try {
      await api("/api/ai/mcp/config", {
        method: "POST",
        body: JSON.stringify({ aosp_versions: _aiAospVersions }),
      });
      toast("Versions Saved 💾", "AOSP target versions updated successfully.", "ok", 3500);
      $("#modal-aosp-versions")?.classList.add("hidden");
      renderAIAospVersionsSelect();
    } catch (err) {
      toast("Save Versions Error", err.message, "err");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "💾 Save Versions";
      }
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
      toast("Schedule Saved ⏱", "Updated ChromaDB sync schedule.", "ok", 3500);
      await loadAIMcpStatus();
    } catch (err) {
      toast("Save Schedule Error", err.message, "err");
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
        toast("Template Loaded 📋", "Configuration template loaded from server. Click '💾 Save JSON' to apply.", "ok", 4000);
      } else {
        toast("Load Template", "No configuration template found on server.", "err");
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
          `ℹ️ Local endpoint has no API key set — if gateway requires auth, open <b>⚙ Config</b> to enter key.`);
      }
    } else if (!st.has_api_key || st.sdk_installed === "missing") {
      aiAppendMsg("assistant",
        `⚠️ <b>Not ready:</b> ` +
        (st.sdk_installed === "missing"
          ? `missing SDK (<code>pip install ${st.provider === "openai" ? "openai" : "anthropic"}</code>) — or open <b>⚙ Config</b> to configure a custom endpoint (no SDK needed).`
          : `missing API key (set <code>TELUA_AI_API_KEY</code> or open <b>⚙ Config</b>).`));
    }
  } catch { /* status optional */ }

  loadAITokenUsage();
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
    loadAITokenUsage();
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
      toast("Guardrails Saved 🛡", `Max: ${iter} turns | Max read: ${lines} lines | Loop Breaker: ${loopBreaker ? "ON" : "OFF"}`, "ok", 3500);
    }
  } catch (err) {
    toast("Guardrails Error", err.message, "err");
  }
}

async function loadAITokenUsage() {
  try {
    const res = await api("/api/ai/token_usage");
    if (!res || !res.ok) return;

    const cur = res.current || {};
    const total = cur.total_tokens || 0;
    const prompt = cur.prompt_tokens || 0;
    const compl = cur.completion_tokens || 0;
    const reqs = cur.requests || 0;

    const fmt = n => Number(n || 0).toLocaleString();

    // Update Header Badge
    const headerBadge = $("#ai-header-token-badge");
    if (headerBadge) {
      headerBadge.textContent = `📊 This month: ${fmt(total)} tokens`;
      headerBadge.title = `Month ${res.current_month || ""}: Prompt ${fmt(prompt)} | Output ${fmt(compl)} | ${fmt(reqs)} queries. Click to view history.`;
    }

    // Update Modal Badge
    const modalBadge = $("#ai-token-current-month-badge");
    if (modalBadge) {
      modalBadge.textContent = `Month ${res.current_month || ""}: ${fmt(total)} tokens`;
    }

    // Update Metric Cards
    const elTot = $("#ai-metric-total-tokens");
    if (elTot) elTot.textContent = fmt(total);
    const elPrompt = $("#ai-metric-prompt-tokens");
    if (elPrompt) elPrompt.textContent = fmt(prompt);
    const elCompl = $("#ai-metric-completion-tokens");
    if (elCompl) elCompl.textContent = fmt(compl);
    const elReqs = $("#ai-metric-requests");
    if (elReqs) elReqs.textContent = fmt(reqs);

    // Update History Table
    const tbody = $("#ai-token-history-tbody");
    if (tbody) {
      const history = res.history || [];
      if (!history.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:10px;color:var(--text-muted);">No token usage recorded yet</td></tr>`;
      } else {
        tbody.innerHTML = history.map(h => {
          const isCurrent = h.month === res.current_month;
          return `
            <tr style="${isCurrent ? 'font-weight:600;background:rgba(255,255,255,0.03);' : ''}">
              <td style="padding:6px 10px;text-align:left;">
                ${esc(h.month)} ${isCurrent ? '<span class="chip ok" style="font-size:10px;padding:1px 5px;margin-left:4px;">Current</span>' : ''}
              </td>
              <td style="padding:6px 10px;text-align:right;" class="mono">${fmt(h.prompt_tokens)}</td>
              <td style="padding:6px 10px;text-align:right;" class="mono">${fmt(h.completion_tokens)}</td>
              <td style="padding:6px 10px;text-align:right;color:var(--accent);" class="mono">${fmt(h.total_tokens)}</td>
              <td style="padding:6px 10px;text-align:center;" class="mono">${fmt(h.requests)}</td>
            </tr>
          `;
        }).join("");
      }
    }
  } catch {
    /* ignore network / non-fatal */
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
    ? (entry.apiKey ? "✓ API key saved for this provider." : "✗ No API key set (local endpoints may not require one).")
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
    toast("AI config saved 💾", "Provider registry written to config/ai_agent/ (keys → config/overlay/ai_agent/)", "ok", 4000);
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
const DEFAULT_AOSP_VERSIONS = [
  { id: "auto", name: "⚡ Auto-detect (A12-A16+)", api_level: null, is_auto: true },
  { id: "a16", name: "Android 16 (Baklava / API 36)", api_level: 36 },
  { id: "a15", name: "Android 15 (VanillaIceCream / API 35)", api_level: 35 },
  { id: "a14", name: "Android 14 (UpsideDownCake / API 34)", api_level: 34 },
  { id: "a13", name: "Android 13 (Tiramisu / API 33)", api_level: 33 },
  { id: "a12", name: "Android 12 (SnowCone / API 31-32)", api_level: 32 },
];
let _aiAospVersions = [...DEFAULT_AOSP_VERSIONS];
let _aiMcpSources = [];

function renderAIAospVersionsSelect(selectedId) {
  const sel = $("#ai-mcp-new-version");
  if (!sel) return;
  const currentVal = selectedId !== undefined ? selectedId : (sel.value || "auto");
  sel.innerHTML = _aiAospVersions.map(v =>
    `<option value="${esc(v.id)}" ${v.id === currentVal ? "selected" : ""}>${esc(v.name || v.id)}</option>`
  ).join("") + `<option value="__manage__" style="color:var(--accent);font-weight:600;">➕ Manage / Add custom version...</option>`;
}

function renderAIAospVersionsList() {
  const container = $("#ai-aosp-versions-list");
  const countEl = $("#ai-version-count");
  if (countEl) countEl.textContent = String(_aiAospVersions.length);
  if (!container) return;

  container.innerHTML = _aiAospVersions.map((v, idx) => {
    const isBuiltin = !v.is_custom && ["auto", "a16", "a15", "a14", "a13", "a12"].includes(v.id);
    const tagBadge = isBuiltin
      ? `<span class="chip" style="font-size:10px;padding:1px 5px;background:rgba(255,255,255,0.06);color:#8b949e;">Standard</span>`
      : `<span class="chip ok" style="font-size:10px;padding:1px 5px;">Custom</span>`;
    const apiBadge = v.api_level
      ? `<span class="chip" style="font-size:10px;padding:1px 5px;background:rgba(74,222,128,0.12);color:#4ade80;">API ${v.api_level}</span>`
      : '';
    const delBtn = isBuiltin
      ? ''
      : `<button class="btn danger ai-ver-del" data-idx="${idx}" style="padding:1px 6px;font-size:10px;" title="Delete this custom version">🗑</button>`;

    return `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:4px 8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;">
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0;">
          <code class="mono" style="font-size:11px;color:var(--accent);font-weight:700;">${esc(v.id)}</code>
          <span style="font-size:11px;color:var(--text);">${esc(v.name || v.id)}</span>
          ${apiBadge}
          ${tagBadge}
        </div>
        ${delBtn}
      </div>
    `;
  }).join("");

  container.querySelectorAll(".ai-ver-del").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const idx = parseInt(e.target.dataset.idx, 10);
      const item = _aiAospVersions[idx];
      if (!item) return;
      if (!confirm(`Delete custom AOSP version "${item.name || item.id}"?`)) return;
      _aiAospVersions.splice(idx, 1);
      renderAIAospVersionsList();
      renderAIAospVersionsSelect();
    });
  });
}

function openAospVersionsModal() {
  renderAIAospVersionsList();
  $("#modal-aosp-versions")?.classList.remove("hidden");
}

function renderAIMcpSourcesList() {
  const container = $("#ai-mcp-sources-list");
  if (!container) return;
  if (!_aiMcpSources.length) {
    container.innerHTML = `<div class="meta" style="padding:8px;text-align:center;">(No knowledge sources configured yet. Enter details below and click "➕ Add Source")</div>`;
    return;
  }
  container.innerHTML = _aiMcpSources.map((s, idx) => {
    const isOk = s.exists !== false;
    const isPriv = (s.visibility === "private" || s.is_private === true);
    const visBadge = `
      <span class="chip ai-mcp-src-vis-toggle" data-idx="${idx}" style="font-size:10px;padding:1px 6px;cursor:pointer;border:1px solid ${isPriv ? 'rgba(255,165,0,0.3)' : 'rgba(56,139,253,0.3)'};background:${isPriv ? 'rgba(255,165,0,0.12)' : 'rgba(56,139,253,0.12)'};color:${isPriv ? '#f0883e' : '#58a6ff'};" title="Click to toggle between Private (stored in overlay, git-ignored) and Public (shared via git)">
        ${isPriv ? '🔒 Private' : '🌐 Public'}
      </span>
    `;
    const statusChip = isOk
      ? `<span class="chip ok" style="font-size:10px;padding:1px 6px;">${s.count || 0} skills</span>`
      : `<span class="chip err" style="font-size:10px;padding:1px 6px;" title="${esc(s.resolved_path || 'Directory not found on disk')}">⚠️ Directory not found</span>`;
    const gitLink = s.repo_url
      ? `<a href="${esc(s.repo_url)}" target="_blank" style="color:var(--accent);font-size:11px;text-decoration:none;" title="Open Git repo">↗ Git</a>`
      : '';

    return `
      <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg);border:1px solid ${s.enabled ? 'var(--border)' : 'rgba(255,255,255,0.06)'};border-radius:6px;opacity:${s.enabled ? '1' : '0.6'};">
        <input type="checkbox" class="ai-mcp-src-toggle" data-idx="${idx}" ${s.enabled ? 'checked' : ''} title="${s.enabled ? 'Source enabled' : 'Source disabled'}">
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <strong style="font-size:11px;color:var(--text);">${esc(s.name || s.id)}</strong>
            ${visBadge}
            ${s.project ? `<span class="chip" style="font-size:10px;padding:1px 6px;background:rgba(255,255,255,0.06);color:var(--accent);" title="Project: ${esc(s.project)}">🏷️ ${esc(s.project)}</span>` : ''}
            ${s.aosp_version ? `<span class="chip" style="font-size:10px;padding:1px 6px;background:rgba(74,222,128,0.12);color:#4ade80;border:1px solid rgba(74,222,128,0.3);" title="AOSP Version: ${esc(s.aosp_version.toUpperCase())}${s.api_level ? ` (API ${s.api_level})` : ''}">🤖 ${esc(s.aosp_version.toUpperCase())}${s.api_level ? ` (API ${s.api_level})` : ''}</span>` : ''}
            ${statusChip}
            ${gitLink}
          </div>
          <div class="mono meta" style="font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px;" title="${esc(s.resolved_path || s.local_path)}">
            ${esc(s.local_path)}
          </div>
        </div>
        <button class="btn danger ai-mcp-src-del" data-idx="${idx}" style="padding:2px 7px;font-size:11px;" title="Delete this source">🗑</button>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".ai-mcp-src-vis-toggle").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const idx = parseInt(e.target.dataset.idx, 10);
      if (_aiMcpSources[idx]) {
        const wasPriv = (_aiMcpSources[idx].visibility === "private" || _aiMcpSources[idx].is_private === true);
        _aiMcpSources[idx].visibility = wasPriv ? "public" : "private";
        _aiMcpSources[idx].is_private = !wasPriv;
        renderAIMcpSourcesList();
      }
    });
  });

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
      const name = _aiMcpSources[idx]?.name || "this source";
      if (!confirm(`Are you sure you want to remove source "${name}"?`)) return;
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

    if (cfgRes.aosp_versions || cfgRes.config?.aosp_versions) {
      _aiAospVersions = cfgRes.aosp_versions || cfgRes.config?.aosp_versions || DEFAULT_AOSP_VERSIONS;
    }
    renderAIAospVersionsSelect();

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
      const syncTime = cfgRes.config?.last_sync || "never synced";
      const total = cfgRes.skills_count || (skillsRes.skills && skillsRes.skills.length) || 0;
      const sched = cfgRes.config?.auto_sync_enabled ? `Every ${cfgRes.config.sync_interval_hours || 3}h` : "manual";
      const activeCount = (_aiMcpSources || []).filter(s => s.enabled).length;
      info.textContent = `Total ${total} skills (${activeCount}/${_aiMcpSources.length} sources enabled) · Schedule: ${sched} · Last sync: ${syncTime}`;
    }

    const countEl = $("#ai-mcp-count");
    if (countEl) countEl.textContent = String(skillsRes.count ?? (skillsRes.skills || []).length);

    const listEl = $("#ai-mcp-skills-list");
    if (listEl && Array.isArray(skillsRes.skills)) {
      const more = skillsRes.truncated
        ? `<div class="meta" style="padding:4px 0;">… showing first ${skillsRes.skills.length} of ${skillsRes.count} files</div>`
        : "";
      listEl.innerHTML = (skillsRes.skills.map(s =>
        `<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;justify-content:space-between;align-items:baseline;gap:8px;">
          <div>
            <span style="color:var(--accent);font-weight:600;">[${esc(s.source_id || 'skill')}:${esc(s.category)}]</span>
            <span class="mono">${esc(s.name)}</span>
            ${s.title && s.title !== s.name ? `<span style="color:var(--text);opacity:0.85;margin-left:4px;">— ${esc(s.title)}</span>` : ''}
          </div>
          <span style="color:#8b949e;font-size:10px;flex-shrink:0;">${Math.round(s.size_bytes / 1024 * 10) / 10}KB</span>
        </div>`
      ).join("") + more) || "(no skill files found)";
    }
  } catch (err) {
    const info = $("#ai-mcp-sync-info");
    if (info) info.textContent = `Error reading MCP config: ${err.message}`;
  }
  // If a sync is running (started earlier, by the scheduler, or before a page
  // reload) re-attach the live progress view.
  resumeAIMcpSyncProgress();
}

/* ---------------- ChromaDB sync live progress ---------------- */
let _aiMcpSyncTimer = null;

function _fmtBytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

function _fmtDuration(s) {
  if (s == null) return "—";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}h${String(m).padStart(2, "0")}m` : m ? `${m}m${String(sec).padStart(2, "0")}s` : `${sec}s`;
}

function setAIMcpSyncButtons(running) {
  const btn = $("#btn-ai-mcp-sync");
  if (btn) {
    btn.disabled = !!running;
    btn.textContent = running ? "⏳ Syncing..." : "🔄 Sync to ChromaDB";
  }
  $("#btn-ai-mcp-sync-cancel")?.classList.toggle("hidden", !running);
}

function renderAIMcpSyncProgress(p) {
  const box = $("#ai-mcp-sync-progress");
  if (!box || !p || p.phase === "idle") return;
  box.classList.remove("hidden");
  setAIMcpSyncButtons(p.running);

  const n = (v) => Number(v || 0).toLocaleString();
  const titles = {
    starting: "⏳ Starting…",
    indexing: p.scan_done ? "⚙️ Indexing into ChromaDB…" : "🔍 Scanning folders + indexing…",
    cancelling: "⏹ Cancelling…",
    done: "✅ Sync complete",
    cancelled: "⏹ Sync cancelled",
    error: "❌ Sync failed",
  };
  const title = $("#ai-mcp-sync-progress-title");
  if (title) title.textContent = `${titles[p.phase] || p.phase}${p.current_source && p.running ? ` — ${p.current_source}` : ""}`;

  const bar = $("#ai-mcp-sync-progress-bar");
  const pctEl = $("#ai-mcp-sync-progress-pct");
  let pct = p.percent;
  if (!p.running && p.phase === "done") pct = 100;
  if (bar) {
    bar.style.width = `${pct != null ? pct : 0}%`;
    bar.style.background = p.phase === "error" ? "var(--err, #f85149)" : "var(--accent)";
  }
  if (pctEl) {
    pctEl.textContent = pct != null
      ? `${pct}%${p.running && p.eta_s != null ? ` · ETA ${_fmtDuration(p.eta_s)}` : ""}`
      : `${n(p.files_discovered)} files found…`;
  }

  const stats = $("#ai-mcp-sync-progress-stats");
  if (stats) {
    stats.textContent =
      `Files ${n(p.files_processed)}/${n(p.files_discovered)}${p.scan_done ? "" : "+"}` +
      ` · ${_fmtBytes(p.bytes_processed)}/${_fmtBytes(p.bytes_discovered)}` +
      ` · indexed ${n(p.files_indexed)} (${n(p.chunks_written)} chunks)` +
      ` · cached ${n(p.files_skipped)}` +
      (p.files_too_large ? ` · too large ${n(p.files_too_large)}` : "") +
      (p.files_failed ? ` · failed ${n(p.files_failed)}` : "") +
      ` · ${p.files_per_s || 0} files/s, ${p.mb_per_s || 0} MB/s` +
      ` · ${p.reader_threads || 0} readers + 1 writer` +
      ` · elapsed ${_fmtDuration(p.elapsed_s)}`;
  }
  const fileEl = $("#ai-mcp-sync-progress-file");
  if (fileEl) {
    fileEl.textContent = p.running
      ? (p.current_file ? `→ ${p.current_file}` : "")
      : (p.last_error ? `Last error: ${p.last_error}` : "");
    fileEl.title = fileEl.textContent;
  }
}

function startAIMcpSyncPolling() {
  if (_aiMcpSyncTimer) return;
  const tick = async () => {
    let p = null;
    try {
      const res = await api("/api/ai/mcp/sync/status");
      p = res.progress;
      renderAIMcpSyncProgress(p);
    } catch (_) { /* transient network error: keep polling */ }
    if (p && !p.running) {
      _aiMcpSyncTimer = null;
      setAIMcpSyncButtons(false);
      const r = p.result || {};
      if (p.phase === "done") {
        toast("MCP Sync Success 🎉", `Indexed ${r.indexed ?? 0} files (${r.chunks ?? 0} chunks), ${r.skipped ?? 0} cached, in ${_fmtDuration(r.elapsed_s)}.`, "ok", 6000);
      } else if (p.phase === "cancelled") {
        toast("Sync Cancelled", `Indexed ${r.indexed ?? 0} files before stopping.`, "ok", 4500);
      } else {
        toast("Sync Error", r.error || p.last_error || "Sync failed", "err");
      }
      loadAIMcpStatus();
      return;
    }
    _aiMcpSyncTimer = setTimeout(tick, 1000);
  };
  _aiMcpSyncTimer = setTimeout(tick, 300);
}

async function resumeAIMcpSyncProgress() {
  if (_aiMcpSyncTimer) return;
  try {
    const res = await api("/api/ai/mcp/sync/status");
    if (res.progress && res.progress.running) {
      renderAIMcpSyncProgress(res.progress);
      startAIMcpSyncPolling();
    }
  } catch (_) { /* ignore */ }
}
