/* ==============================================================================
   Telua Web - Config Manager UI frontend logic (vanilla JS, no dependencies)
   Talks to the Flask backend in web/telua_web.py:
     GET  /api/status   GET /api/files   GET/POST /api/file
     POST /api/profile  GET /api/info   GET/POST /api/pipelines  POST /api/pipeline/run
   Draft persistence: unsaved edits (Files editor + Pipelines) are auto-saved to
   localStorage on every change and restored after a page refresh, so work is
   never lost. Drafts are cleared automatically after a successful server save.
   ============================================================================== */
"use strict";

const $ = (sel) => document.querySelector(sel);

const state = {
  files: [],
  current: null,      // { name, content, readonly, kind, mtime }
  fileEditing: false, // locked by default until user clicks '✎ Edit'
  dirty: false,
  status: null,
  pipelines: [],      // [{ name, description, array, steps, orphan, _editing, _editingStep }]
  plDirty: false,
  plSource: "my",     // "my" (const_my_cli.config) | "multi" (const_multi_cli.config)
};

/* ---------------- Draft persistence (localStorage, survives refresh) ------- */
const DRAFT_KEY_FILES = "telua_web_draft_file";      // { name, content, saved_at }
const DRAFT_KEY_PIPES = "telua_web_draft_pipelines"; // { source, pipelines, saved_at }
const LAST_TAB_KEY = "telua_web_last_tab";           // "files" | "pipelines" | "system"
const LAST_SOURCE_KEY = "telua_web_last_source";     // "my" | "multi" | "car" | "dump" | "system"
const LAST_FILE_KEY = "telua_web_last_file";         // last opened file name in Files tab
const THEME_KEY = "telua_web_theme";                 // "dark" | "jade" | "ocean" | "amethyst" | "light"
const THEME_LABELS = {
  dark: "🌙 Dark (Default)",
  jade: "💎 Jade (Emerald)",
  ocean: "🌊 Ocean (Deep Blue)",
  amethyst: "🔮 Amethyst (Purple)",
  light: "☀️ Light",
};

function applyTheme(theme) {
  const t = THEME_LABELS[theme] ? theme : "dark";
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch { /* ignore */ }
  const sel = $("#theme-select");
  if (sel && sel.value !== t) {
    sel.value = t;
  }
}

function draftSaveFile() {
  try {
    if (!state.current || state.current.readonly || !state.dirty) {
      localStorage.removeItem(DRAFT_KEY_FILES);
      return;
    }
    localStorage.setItem(DRAFT_KEY_FILES, JSON.stringify({
      name: state.current.name,
      content: $("#editor").value,
      saved_at: new Date().toISOString(),
    }));
  } catch { /* quota / private mode: drafts are best-effort */ }
}

function draftClearFile() {
  try { localStorage.removeItem(DRAFT_KEY_FILES); } catch { /* ignore */ }
}

function draftLoadFile() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY_FILES);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function draftSavePipelines() {
  try {
    if (!state.plDirty) {
      localStorage.removeItem(DRAFT_KEY_PIPES);
      return;
    }
    const cleanPipelines = state.pipelines.map(({ _editing, _editingStep, _expanded, ...rest }) => rest);
    localStorage.setItem(DRAFT_KEY_PIPES, JSON.stringify({
      source: state.plSource,
      pipelines: cleanPipelines,
      saved_at: new Date().toISOString(),
    }));
  } catch { /* best-effort */ }
}

function draftClearPipelines() {
  try { localStorage.removeItem(DRAFT_KEY_PIPES); } catch { /* ignore */ }
}

function draftLoadPipelines() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY_PIPES);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function draftTime(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return ""; }
}

function updateDraftChip() {
  const chip = $("#chip-draft");
  const hasDraft = state.dirty || state.plDirty || !!draftLoadFile() || !!draftLoadPipelines();
  chip.classList.toggle("hidden", !hasDraft);
  if (hasDraft) {
    const parts = [];
    if (state.dirty) parts.push("file");
    if (state.plDirty) parts.push("pipelines");
    chip.textContent = `✎ draft (${parts.join(" + ") || "restored"})`;
  }
}

/* ---------------- Toast notifications ---------------- */
function toast(title, body, kind = "info", timeout = 5000) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.style.setProperty("--toast-ms", `${timeout}ms`);
  el.innerHTML = `
    <div class="t-head">
      <div class="t-title"></div>
      <button class="t-close" title="Close">✕</button>
    </div>
    <div class="t-body"></div>
    <div class="t-bar"></div>
  `;
  el.querySelector(".t-title").textContent = title;
  el.querySelector(".t-body").textContent = body || "";
  const timer = setTimeout(() => {
    el.classList.add("closing");
    setTimeout(() => el.remove(), 200);
  }, timeout);
  el.querySelector(".t-close").addEventListener("click", () => {
    clearTimeout(timer);
    el.remove();
  });
  $("#toasts").appendChild(el);
}

/* ---------------- Styled Confirm Modal ---------------- */
let _confirmResolver = null;

function confirmDialog({
  title = "Confirm Delete",
  message = "Are you sure you want to delete this item?",
  detail = "",
  hint = "💡 After deleting, remember to click '💾 Save all' to write changes to disk.",
  confirmText = "🗑 Confirm Delete",
  icon = "🗑",
} = {}) {
  const modal = $("#modal-confirm");
  if (!modal) return Promise.resolve(window.confirm(message));
  $("#confirm-icon").textContent = icon;
  $("#confirm-title").textContent = title;
  $("#confirm-msg").textContent = message;
  const detailEl = $("#confirm-detail");
  if (detail) {
    detailEl.textContent = detail;
    detailEl.classList.remove("hidden");
  } else {
    detailEl.textContent = "";
    detailEl.classList.add("hidden");
  }
  const hintEl = $("#confirm-hint");
  if (hint) {
    hintEl.textContent = hint;
    hintEl.classList.remove("hidden");
  } else {
    hintEl.classList.add("hidden");
  }
  $("#btn-confirm-ok").textContent = confirmText;
  modal.classList.remove("hidden");
  $("#btn-confirm-ok").focus();

  return new Promise((resolve) => {
    _confirmResolver = resolve;
  });
}

function resolveConfirm(result) {
  $("#modal-confirm")?.classList.add("hidden");
  if (_confirmResolver) {
    const fn = _confirmResolver;
    _confirmResolver = null;
    fn(result);
  }
}

/* ---------------- API helpers ---------------- */
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON error body */ }
  if (!res.ok) {
    const msg = data.error || data.description || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

/* ---------------- Status bar ---------------- */
function renderStatus(s) {
  state.status = s;
  $("#chip-version").innerHTML = `v<b>${esc(s.version)}</b>`;
  $("#chip-project").innerHTML = `project: <b>${esc(s.active_project || "—")}</b>`;
  const adb = s.adb_devices || [];
  const chipAdb = $("#chip-adb");
  if (adb.length === 0) {
    chipAdb.textContent = "adb: offline";
    chipAdb.className = "chip err";
  } else {
    chipAdb.innerHTML = `adb: <b>${adb.length}</b> ${adb.map(d => esc(d.serial)).join(", ")}`;
    chipAdb.className = "chip ok";
  }
  const ram = s.ram;
  const chipRam = $("#chip-ram");
  if (ram) {
    chipRam.textContent = `ram: ${ram.used_gb}/${ram.total_gb} GB (${ram.used_pct}%)`;
    chipRam.className = "chip " + (ram.used_pct > 85 ? "err" : ram.used_pct > 70 ? "warn" : "ok");
  } else {
    chipRam.textContent = "ram: n/a";
    chipRam.className = "chip";
  }
  const termCwd = $("#term-cwd");
  if (termCwd && s.root && !_termCwd) {
    _setTermCwd(s.root);
  }
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

const ANSI_COLOR_MAP = {
  30: "#8b949e", 90: "#8b949e",
  31: "#f85149", 91: "#ff7b72",
  32: "#3fb950", 92: "#56d364",
  33: "#d29922", 93: "#e3b341",
  34: "#58a6ff", 94: "#79c0ff",
  35: "#bc8cff", 95: "#d2a8ff",
  36: "#39c5cf", 96: "#56d4dd",
  37: "#e6edf3", 97: "#ffffff",
};

function ansiToHtml(text) {
  const cleaned = String(text == null ? "" : text).replace(/\x1b\[[0-9;?]*[A-LN-Za-ln-z]/g, "");
  const safe = esc(cleaned);
  let openSpans = 0;
  const html = safe.replace(/(?:\x1b\[|\[(?=(?:0|[012];[39][0-7])m))([0-9;]*)m/g, (_, codesStr) => {
    const codes = (codesStr || "0").split(";").map(Number);
    let out = "";
    if (openSpans > 0) {
      out += "</span>".repeat(openSpans);
      openSpans = 0;
    }
    if (codes.length === 1 && codes[0] === 0) return out;
    const styles = [];
    for (const c of codes) {
      if (c === 1) styles.push("font-weight:700");
      else if (c === 2) styles.push("opacity:.75");
      else if (ANSI_COLOR_MAP[c]) styles.push(`color:${ANSI_COLOR_MAP[c]}`);
    }
    if (styles.length > 0) {
      openSpans++;
      out += `<span style="${styles.join(";")}">`;
    }
    return out;
  });
  return html + (openSpans > 0 ? "</span>".repeat(openSpans) : "");
}

async function refreshStatus() {
  try {
    renderStatus(await api("/api/status"));
  } catch (err) {
    toast("Status failed", err.message, "err");
  }
}

/* ---------------- File list ---------------- */
// Files that have a dedicated Pipelines GUI view, mapped to their source key.
const PIPELINE_GUI_FILES = {
  "config/overlay/const_my_cli.config": "my",
  "config/overlay/const_my_cli.config.example": "my",
  "config/const_my_cli.config": "my",
  "config/const_my_cli.config.example": "my",
  "config/const_multi_cli.config": "multi",
  "config/const_multi_cli.config.example": "multi",
  "config/const_system_cli.config": "system",
  "config/overlay/const_system_cli.config": "system",
  "config/const_car.config": "car",
  "config/overlay/const_car.config": "car",
  "config/const_dumpsys.config": "dump",
  "config/overlay/const_dumpsys.config": "dump",
};

function renderFiles(filter = "") {
  const list = $("#file-list");
  list.innerHTML = "";
  const q = filter.trim().toLowerCase();
  const pipelinesActive = !$("#view-pipelines").classList.contains("hidden");
  const activePlFile = $("#pl-file")?.textContent || "";

  const sideTitle = document.querySelector(".side-head h2");
  if (sideTitle) {
    sideTitle.textContent = pipelinesActive ? "Pipeline Configs" : "Config Files";
  }

  const allNames = new Set(state.files.map(f => f.name));
  const files = state.files.filter(f => {
    if (q && !f.name.toLowerCase().includes(q)) return false;
    if (pipelinesActive) {
      if (!PIPELINE_GUI_FILES[f.name]) return false;
      // Hide .example in Pipelines tab if the active .config file already exists
      if (f.name.endsWith(".example") && allNames.has(f.name.slice(0, -".example".length))) {
        return false;
      }
    }
    return true;
  });

  for (const f of files) {
    const li = document.createElement("li");
    li.dataset.name = f.name;
    const guiSource = PIPELINE_GUI_FILES[f.name];
    const isOverlay = f.name.startsWith("config/overlay/") || f.name.includes("apk_overlays");
    const isDec = f.name.includes("/dec_") || f.name.startsWith("dec_");
    const isCore = f.name === "config/apk.config" || f.name === "apk.config";
    const isActive = pipelinesActive
      ? (f.name === activePlFile || guiSource === state.plSource)
      : !!(state.current && state.current.name === f.name);

    if (isActive) li.classList.add("active");
    if (f.readonly) li.classList.add("kind-ro");
    else if (isDec) li.classList.add("kind-dec");
    else if (isOverlay) li.classList.add("kind-overlay");
    else if (isCore) li.classList.add("kind-core");
    else if (guiSource) li.classList.add("kind-gui");

    const slashIdx = f.name.lastIndexOf("/");
    const dirPart = slashIdx >= 0 ? f.name.slice(0, slashIdx + 1) : "";
    const basePart = slashIdx >= 0 ? f.name.slice(slashIdx + 1) : f.name;

    const nameWrap = document.createElement("div");
    nameWrap.className = "fname-wrap";
    if (dirPart) {
      const dirSpan = document.createElement("span");
      dirSpan.className = "fdir";
      dirSpan.textContent = dirPart;
      nameWrap.appendChild(dirSpan);
    }
    const baseSpan = document.createElement("span");
    baseSpan.className = "fname";
    baseSpan.textContent = basePart;
    nameWrap.appendChild(baseSpan);

    li.title = `${f.name} · ${f.size} bytes · ${f.mtime_str}` +
      (guiSource ? ` · ⚡ GUI (${guiSource})` : "");
    li.appendChild(nameWrap);

    const right = document.createElement("span");
    right.className = "fgroup";
    if (pipelinesActive) {
      right.textContent = `⚡ ${guiSource || "gui"}`;
      right.classList.add("badge-gui");
    } else if (f.readonly) {
      right.textContent = "🔒 ro";
      right.classList.add("badge-ro");
    } else if (isDec) {
      right.textContent = "👁 dec";
      right.classList.add("badge-dec");
    } else if (isOverlay) {
      right.textContent = guiSource ? `🔐 ${guiSource}` : "🔐 priv";
      right.classList.add("badge-overlay");
    } else if (guiSource) {
      right.textContent = `⚡ ${guiSource}`;
      right.classList.add("badge-gui");
    } else {
      right.textContent = f.group;
    }
    li.appendChild(right);

    li.addEventListener("click", () => handleFileClick(f.name));
    list.appendChild(li);
  }
  if (files.length === 0) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="meta">No matching files</span>`;
    list.appendChild(li);
  }
}

// Context-aware file click:
//   - Pipelines tab active -> switch the Pipelines GUI to the clicked file's source.
//   - Files tab active     -> load the clicked file into the text editor.
function handleFileClick(name) {
  const pipelinesActive = !$("#view-pipelines").classList.contains("hidden");
  const guiSource = PIPELINE_GUI_FILES[name];
  if (pipelinesActive && guiSource) {
    switchPipelineSource(guiSource);
    renderFiles($("#search").value);
    return;
  }
  openFile(name);
}

async function refreshFiles() {
  try {
    const data = await api("/api/files");
    state.files = data.files || [];
    renderFiles($("#search").value);
  } catch (err) {
    toast("File list failed", err.message, "err");
  }
}

/* ---------------- Editor ---------------- */
function setDirty(dirty) {
  state.dirty = dirty;
  $("#editor-dirty").classList.toggle("hidden", !dirty);
  $("#btn-save").disabled = !dirty || (state.current && state.current.readonly);
  if (dirty) draftSaveFile();          // persist edit to localStorage on every keystroke
  updateDraftChip();
}

function updateStats() {
  const content = $("#editor").value;
  const lines = content ? content.split("\n").length : 0;
  const bytes = new TextEncoder().encode(content).length;
  $("#editor-stats").textContent = `${lines} lines · ${bytes} bytes`;
}

function setFileEditing(editing) {
  const c = state.current;
  const canEdit = !!(c && !c.readonly);
  state.fileEditing = canEdit && !!editing;
  const editor = $("#editor");
  editor.disabled = !c || c.readonly;
  editor.readOnly = !state.fileEditing;
  const editBtn = $("#btn-edit");
  if (editBtn) {
    editBtn.disabled = !canEdit;
    editBtn.textContent = state.fileEditing ? "✓ Done" : "✎ Edit";
    editBtn.classList.toggle("editing", state.fileEditing);
    editBtn.title = state.fileEditing
      ? "Lock editor (prevent accidental changes)"
      : "Unlock editor to modify this file";
  }
}

function setCurrentMeta() {
  const c = state.current;
  const cryptoBtn = $("#btn-file-crypto");
  if (!c) {
    $("#editor-name").textContent = "—";
    $("#editor-meta").textContent = "";
    cryptoBtn?.classList.add("hidden");
    setFileEditing(false);
    return;
  }
  $("#editor-name").textContent = c.name;
  $("#editor-meta").textContent =
    `${c.kind} · ${c.readonly ? "read-only" : (state.fileEditing ? "editing" : "locked (click ✎ Edit)")} · ${c.size} bytes · ${c.mtime_str || ""}`;
  $("#btn-reload").disabled = false;
  $("#btn-save").disabled = !state.dirty || c.readonly;
  const isOverlayFile = c.name === "config/overlay/apk_overlays.config" || c.name === "apk_overlays.config";
  const isPrivateFile = isOverlayFile || c.name === "config/overlay/const_my_cli.config" || c.name === "config/const_my_cli.config";
  cryptoBtn?.classList.toggle("hidden", !isPrivateFile);
  setFileEditing(state.fileEditing);
}

async function openFile(name, draftContent = null) {
  if (state.dirty && !confirm(`Discard unsaved changes in ${state.current?.name}?`)) return;
  // The sidebar is visible on both tabs; make sure the Files view (editor) is
  // shown, otherwise the file loads invisibly while Pipelines stays on screen.
  const filesViewHidden = $("#view-files").classList.contains("hidden");
  if (filesViewHidden) switchTab("files");
  try {
    const data = await api(`/api/file?name=${encodeURIComponent(name)}`);
    state.current = data;
    try { localStorage.setItem(LAST_FILE_KEY, name); } catch { /* ignore */ }
    if (draftContent != null && draftContent !== data.content) {
      // Restore the unsaved draft on top of the freshly loaded file.
      $("#editor").value = draftContent;
      setFileEditing(true);
      setDirty(true);
      toast("Draft restored", `Unsaved edits for ${name} recovered (last change: ${draftTime(draftContent && draftLoadFile()?.saved_at)}).`, "warn", 6000);
    } else {
      $("#editor").value = data.content;
      setFileEditing(false);
      setDirty(false);
    }
    setCurrentMeta();
    updateStats();
    renderFiles($("#search").value);
  } catch (err) {
    toast("Open failed", `${name}: ${err.message}`, "err");
  }
}

async function saveFile() {
  const c = state.current;
  if (!c || c.readonly) return;
  const payload = {
    name: c.name,
    content: $("#editor").value,
    force: $("#force-save").checked,
  };
  try {
    const data = await api("/api/file", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setDirty(false);
    setFileEditing(false);
    draftClearFile();                  // server save succeeded -> drop the draft
    c.size = data.bytes;
    c.mtime_str = data.saved_at;
    setCurrentMeta();
    toast("Saved ✓", `${data.name} (${data.bytes} bytes)` +
      (data.backup ? ` · backup: ${data.backup}` : ""), "ok", 5000);
    refreshFiles();
    if (data.name === "config/apk.config" || data.name === "apk.config") refreshStatus();
  } catch (err) {
    // Validation error -> offer force save
    if (confirm(`Validation failed:\n${err.message}\n\nSave anyway (force)?`)) {
      payload.force = true;
      try {
        const data = await api("/api/file", { method: "POST", body: JSON.stringify(payload) });
        setDirty(false);
        draftClearFile();
        toast("Saved (forced) ✓", `${data.name} · backup: ${data.backup || "none"}`, "warn");
        refreshFiles();
      } catch (err2) {
        toast("Save failed", err2.message, "err");
      }
    } else {
      toast("Not saved", err.message, "warn");
    }
  }
}

/* ---------------- Pipelines tab (MY_CMD_* editor) ---------------- */
function setPlDirty(dirty) {
  state.plDirty = dirty;
  $("#pl-dirty").classList.toggle("hidden", !dirty);
  $("#btn-pl-save").disabled = !dirty;
  if (dirty) draftSavePipelines();     // persist pipelines to localStorage on every change
  updateDraftChip();
}

async function loadPipelines(draft = null) {
  try {
    const data = await api(`/api/pipelines?source=${encodeURIComponent(state.plSource)}`);
    state.pipelines = data.pipelines || [];
    $("#pl-file").textContent = data.file || "—";
    $("#pl-label").textContent = data.label || "";
    if (draft && draft.pipelines && draft.source === state.plSource) {
      // Restore the unsaved draft (edited/added/deleted pipelines + steps).
      state.pipelines = draft.pipelines;
      setPlDirty(true);
      toast("Draft restored", `Unsaved pipeline edits recovered (last change: ${draftTime(draft.saved_at)}).`, "warn", 6000);
    } else {
      setPlDirty(false);
    }
    renderPipelines();
    renderFiles($("#search").value);
    $("#btn-pl-crypto")?.classList.toggle("hidden", state.plSource !== "my");
  } catch (err) {
    toast("Pipelines load failed", err.message, "err");
  }
}

let _lastNonSystemPlSource = "my";

function syncTopTabs() {
  const isFiles = !$("#view-files").classList.contains("hidden");
  const isAosp = !$("#view-aosp")?.classList.contains("hidden");
  const isTerminal = !$("#view-terminal")?.classList.contains("hidden");
  const isLogcat = !$("#view-logcat")?.classList.contains("hidden");
  const isDocs = !$("#view-docs")?.classList.contains("hidden");
  const isBi = !$("#view-bi")?.classList.contains("hidden");
  const isSystem = !isFiles && !isAosp && !isTerminal && !isLogcat && !isDocs && !isBi && (state.plSource === "system" || state.plSource === "docker");
  const isPipelines = !isFiles && !isAosp && !isTerminal && !isLogcat && !isDocs && !isBi && !isSystem;
  $("#tab-files")?.classList.toggle("active", isFiles);
  $("#tab-pipelines")?.classList.toggle("active", isPipelines);
  $("#tab-system")?.classList.toggle("active", isSystem);
  $("#tab-aosp")?.classList.toggle("active", isAosp);
  $("#tab-terminal")?.classList.toggle("active", isTerminal);
  const logcatTab = $("#tab-logcat");
  if (logcatTab) {
    logcatTab.classList.toggle("active", isLogcat);
    logcatTab.classList.toggle("tab-streaming", Boolean(_logcatStreaming));
  }
  $("#tab-docs")?.classList.toggle("active", isDocs);
  $("#tab-bi")?.classList.toggle("active", isBi);
  try {
    const activeTabName = isFiles ? "files" : (isAosp ? "aosp" : (isTerminal ? "terminal" : (isLogcat ? "logcat" : (isDocs ? "docs" : (isBi ? "bi" : (isSystem ? "system" : "pipelines"))))));
    localStorage.setItem(LAST_TAB_KEY, activeTabName);
    localStorage.setItem(LAST_SOURCE_KEY, state.plSource);
  } catch { /* ignore */ }
}

function switchPipelineSource(source) {
  if (source === "docker") source = "system";
  if (source !== "system") _lastNonSystemPlSource = source;
  // Ensure Pipelines view is visible if user clicks a source while in Terminal, Files, Docs, Logcat or AOSP
  $("#view-files")?.classList.add("hidden");
  $("#view-aosp")?.classList.add("hidden");
  $("#view-terminal")?.classList.add("hidden");
  $("#view-docs")?.classList.add("hidden");
  $("#view-logcat")?.classList.add("hidden");
  $("#view-pipelines")?.classList.remove("hidden");
  if (state.plSource === source) {
    syncTopTabs();
    return;
  }
  if (state.plDirty && !confirm("Switch source with unsaved pipeline edits?\n\nThe current draft is kept in browser storage and will be restored when you switch back.")) return;
  state.plSource = source;
  document.querySelectorAll("#pl-source-switch .src-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.source === source));
  syncTopTabs();
  loadPipelines(draftLoadPipelines());
}

function renderPipelines() {
  const list = $("#pipeline-list");
  list.innerHTML = "";
  const rawQuery = ($("#pl-filter")?.value || "").trim().toLowerCase();
  const terms = rawQuery ? rawQuery.split(/[\s,]+/).filter(Boolean) : [];

  const filtered = terms.length === 0
    ? state.pipelines
    : state.pipelines.filter(p => {
      const hay = [
        p.name || "",
        p.description || "",
        p.array || "",
        ...(p.steps || []),
      ].join(" ").toLowerCase();
      return terms.some(t => hay.includes(t));
    });

  for (const p of filtered) {
    list.appendChild(pipelineCard(p));
  }
  if (state.pipelines.length === 0) {
    const fileLabel = $("#pl-file")?.textContent || "config/overlay/const_my_cli.config";
    list.innerHTML = `<p class="meta">No pipelines found in ${esc(fileLabel)}.</p>`;
  } else if (filtered.length === 0) {
    list.innerHTML = `<p class="meta">No CLI pipelines match "<b>${esc(rawQuery)}</b>".</p>`;
  }
  const total = state.pipelines.reduce((n, p) => n + p.steps.length, 0);
  $("#pl-stats").textContent = terms.length > 0
    ? `Showing ${filtered.length} / ${state.pipelines.length} pipelines · ${total} steps`
    : `${state.pipelines.length} pipelines · ${total} steps`;
}

function pipelineCard(p) {
  const isCardEditing = !!p._editing;
  const isExpanded = !!(p._expanded || isCardEditing || p._editingStep != null);
  const card = document.createElement("div");
  card.className = "pl-card" +
    (p.orphan ? " orphan" : "") +
    (isCardEditing ? " editing" : "") +
    (isExpanded ? " expanded" : " collapsed");
  card.dataset.name = p.name;

  // --- header: name + description + array tag ---
  const head = document.createElement("div");
  head.className = "pl-card-head";

  const name = document.createElement("input");
  name.className = "pl-name";
  name.value = p.name;
  name.readOnly = !isCardEditing;
  name.title = isCardEditing
    ? "Pipeline name (used as: telua my <name>)"
    : "Locked — click '✎ Edit' to modify pipeline name";
  name.addEventListener("input", () => {
    if (!p._editing) return;
    const lower = name.value.toLowerCase();
    if (name.value !== lower) {
      const pos = name.selectionStart;
      name.value = lower;
      if (pos != null) name.setSelectionRange(pos, pos);
    }
    p.name = lower;
    card.dataset.name = lower;
    const prefixMap = { my: "MY_CMD_", multi: "MULTI_CMD_", docker: "SYSTEM_CMD_", system: "SYSTEM_CMD_", car: "ADB_SHELL_CAR_", dump: "DUMP_CMD_" };
    const prefix = prefixMap[state.plSource] || "MY_CMD_";
    p.array = prefix + lower.replace(/-/g, "_").toUpperCase();
    if (!p.orphan) tag.textContent = p.array;
    setPlDirty(true);
  });
  head.appendChild(name);

  const desc = document.createElement("input");
  desc.className = "pl-desc";
  desc.value = p.description || "";
  desc.readOnly = !isCardEditing;
  desc.placeholder = "Description (shown by: telua my)";
  desc.title = isCardEditing
    ? "Pipeline description"
    : "Locked — click '✎ Edit' to modify description";
  desc.addEventListener("input", () => {
    if (!p._editing) return;
    p.description = desc.value;
    setPlDirty(true);
  });
  head.appendChild(desc);

  const tag = document.createElement("span");
  tag.className = "pl-array-tag";
  tag.textContent = p.orphan ? "⚠ orphan" : p.array;
  head.appendChild(tag);
  card.appendChild(head);

  // --- steps ---
  const isSingleStep = (state.plSource === "car");
  if (isSingleStep) {
    if (p.steps.length === 0) p.steps = [""];
    else if (p.steps.length > 1) p.steps = [p.steps[0]];
  }
  const stepsBox = document.createElement("div");
  stepsBox.className = "pl-steps" + (isExpanded ? "" : " hidden");
  p.steps.forEach((step, idx) => stepsBox.appendChild(stepRow(p, step, idx, stepsBox)));
  card.appendChild(stepsBox);

  if (!isSingleStep) {
    const addStep = document.createElement("button");
    addStep.className = "pl-add-step" + (isCardEditing ? "" : " hidden");
    addStep.textContent = "＋ Add step";
    addStep.addEventListener("click", () => {
      if (!p._editing) p._editing = true;
      p._expanded = true;
      p.steps.push("");
      p._editingStep = p.steps.length - 1;
      stepsBox.classList.remove("hidden");
      stepsBox.appendChild(stepRow(p, "", p.steps.length - 1, stepsBox));
      setPlDirty(true);
      const inputs = stepsBox.querySelectorAll(".pl-step-cmd");
      inputs[inputs.length - 1]?.focus();
    });
    card.appendChild(addStep);
  }

  // --- footer: run (left / start of row) --- eye + delete + edit (right / end of row) ---
  const foot = document.createElement("div");
  foot.className = "pl-card-foot";

  const runCmdMap = { my: "telua my ", multi: "telua run ", system: "telua system ", docker: "telua system ", car: "telua car ", dump: "telua dump " };
  const runCmdPrefix = runCmdMap[state.plSource] || "telua my ";
  const runBtn = document.createElement("button");
  runBtn.className = "btn primary pl-run-btn";
  runBtn.textContent = "▶ Run";
  runBtn.title = "Execute: " + runCmdPrefix + p.name;
  runBtn.addEventListener("click", () => runPipeline(p.name));
  foot.appendChild(runBtn);

  const stepLabel = isSingleStep ? "1 cmd" : `${p.steps.length} ${p.steps.length === 1 ? "step" : "steps"}`;
  const eyeBtn = document.createElement("button");
  eyeBtn.className = "btn eye-btn" + (isExpanded ? " active" : "");
  eyeBtn.textContent = isExpanded ? `👁 Hide (${stepLabel})` : `👁 ${stepLabel}`;
  eyeBtn.title = isExpanded
    ? "Hide command list to save space"
    : "Show commands in this pipeline";
  eyeBtn.addEventListener("click", () => {
    if (p._editing) {
      toast("Editing in progress", "Click '✓ Done' to lock the card before collapsing commands.", "info", 3500);
      return;
    }
    p._expanded = !isExpanded;
    if (!p._expanded) p._editingStep = null;
    renderPipelines();
  });
  foot.appendChild(eyeBtn);

  const delBtn = document.createElement("button");
  delBtn.className = "btn danger" + (isCardEditing ? "" : " hidden");
  delBtn.textContent = "🗑 Delete";
  delBtn.title = "Delete pipeline '" + p.name + "'";
  delBtn.addEventListener("click", async () => {
    const stepPreview = p.steps.filter(Boolean).map((s, i) => `${i + 1}. ${s}`).join("\n");
    const ok = await confirmDialog({
      title: `Delete Pipeline '${p.name}'?`,
      message: `Are you sure you want to delete pipeline '${p.name}' (${p.steps.length} steps)${p.description ? " — " + p.description : ""}?`,
      detail: stepPreview || "(empty pipeline)",
      hint: "💡 After deleting in the UI, click '💾 Save all' (or Ctrl+S) to write changes to disk.",
      confirmText: "🗑 Delete Pipeline",
      icon: "🗑",
    });
    if (!ok) return;
    state.pipelines = state.pipelines.filter(x => x !== p);
    setPlDirty(true);
    renderPipelines();
    toast("Unsaved changes 💾", `Deleted pipeline '${p.name}' — click '💾 Save all' (or Ctrl+S) to save to disk!`, "warn", 5000);
  });
  foot.appendChild(delBtn);

  const editBtn = document.createElement("button");
  editBtn.className = "btn" + (isCardEditing ? " editing" : "");
  editBtn.textContent = isCardEditing ? "✓ Done" : "✎ Edit";
  editBtn.title = isCardEditing
    ? "Finish editing and lock this pipeline"
    : "Unlock this pipeline to edit name, description, and steps";
  editBtn.addEventListener("click", () => {
    const wasEditing = !!p._editing;
    p._editing = !p._editing;
    if (p._editing) {
      p._expanded = true;
    } else {
      p._editingStep = null;
    }
    renderPipelines();
    if (p._editing) {
      const targetCard = Array.from(document.querySelectorAll(".pl-card"))
        .find(el => el.dataset.name === p.name);
      targetCard?.querySelector(".pl-name")?.focus();
    } else if (wasEditing && state.plDirty) {
      toast("Unsaved changes 💾", "Finished editing — click '💾 Save all' (or Ctrl+S) to save to disk!", "warn", 5000);
    }
  });
  foot.appendChild(editBtn);

  card.appendChild(foot);

  return card;
}

function stepRow(p, step, idx, stepsBox) {
  const isSingleStep = (state.plSource === "car");
  const isStepEditing = !!(p._editing || p._editingStep === idx);
  const row = document.createElement("div");
  row.className = "pl-step";

  const no = document.createElement("span");
  no.className = "pl-step-no";
  no.textContent = isSingleStep ? "cmd:" : `${idx + 1}.`;
  row.appendChild(no);

  const input = document.createElement("input");
  input.className = "pl-step-cmd";
  input.value = step;
  input.readOnly = !isStepEditing;
  input.placeholder = isSingleStep
    ? "dumpsys car_service … | cmd car_service …"
    : "adb shell … | git … | sleep 1 | echo …";
  input.title = isStepEditing
    ? "Edit command"
    : "Locked — click '✎' on this line (or '✎ Edit' on the card) to edit";
  input.addEventListener("input", () => {
    if (!isStepEditing) return;
    p.steps[idx] = input.value;
    setPlDirty(true);
  });
  row.appendChild(input);

  const editStepBtn = document.createElement("button");
  editStepBtn.className = "pl-icon-btn edit" + (isStepEditing ? " active" : "");
  editStepBtn.textContent = isStepEditing && !p._editing ? "✓" : "✎";
  editStepBtn.title = isStepEditing
    ? (p._editing ? "Editing enabled (click to focus)" : "Lock this command")
    : "Click to edit this command";
  editStepBtn.addEventListener("click", () => {
    if (p._editing) {
      input.focus();
      return;
    }
    const wasStepEditing = (p._editingStep === idx);
    p._editingStep = wasStepEditing ? null : idx;
    rerenderSteps(p, stepsBox);
    if (p._editingStep === idx) {
      const inputs = stepsBox.querySelectorAll(".pl-step-cmd");
      inputs[idx]?.focus();
    } else if (wasStepEditing && state.plDirty) {
      toast("Unsaved changes 💾", "Step updated — click '💾 Save all' (or Ctrl+S) to save to disk!", "warn", 5000);
    }
  });
  row.appendChild(editStepBtn);

  if (!isSingleStep && isStepEditing) {
    const up = document.createElement("button");
    up.className = "pl-icon-btn";
    up.textContent = "↑";
    up.title = "Move up";
    up.disabled = idx === 0;
    up.addEventListener("click", () => {
      if (idx === 0) return;
      [p.steps[idx - 1], p.steps[idx]] = [p.steps[idx], p.steps[idx - 1]];
      if (p._editingStep === idx) p._editingStep = idx - 1;
      setPlDirty(true);
      rerenderSteps(p, stepsBox);
    });
    row.appendChild(up);

    const down = document.createElement("button");
    down.className = "pl-icon-btn";
    down.textContent = "↓";
    down.title = "Move down";
    down.disabled = idx >= p.steps.length - 1;
    down.addEventListener("click", () => {
      if (idx >= p.steps.length - 1) return;
      [p.steps[idx + 1], p.steps[idx]] = [p.steps[idx], p.steps[idx + 1]];
      if (p._editingStep === idx) p._editingStep = idx + 1;
      setPlDirty(true);
      rerenderSteps(p, stepsBox);
    });
    row.appendChild(down);

    const del = document.createElement("button");
    del.className = "pl-icon-btn del";
    del.textContent = "🗑";
    del.title = "Delete step";
    del.addEventListener("click", async () => {
      if (step && step.trim()) {
        const ok = await confirmDialog({
          title: `Delete step #${idx + 1} in '${p.name}'?`,
          message: `Are you sure you want to remove step #${idx + 1} from pipeline '${p.name}'?`,
          detail: step,
          hint: "💡 After deleting, click '💾 Save all' (or Ctrl+S) to write changes to disk.",
          confirmText: "🗑 Delete Step",
          icon: "🗑",
        });
        if (!ok) return;
      }
      p.steps.splice(idx, 1);
      if (p._editingStep === idx) p._editingStep = null;
      setPlDirty(true);
      rerenderSteps(p, stepsBox);
      toast("Unsaved changes 💾", `Deleted step #${idx + 1} — click '💾 Save all' (or Ctrl+S) to save to disk!`, "warn", 5000);
    });
    row.appendChild(del);
  }

  return row;
}

function rerenderSteps(p, stepsBox) {
  stepsBox.innerHTML = "";
  p.steps.forEach((step, idx) => stepsBox.appendChild(stepRow(p, step, idx, stepsBox)));
  const total = state.pipelines.reduce((n, x) => n + x.steps.length, 0);
  $("#pl-stats").textContent = `${state.pipelines.length} pipelines · ${total} steps`;
}

async function savePipelines() {
  // Drop empty-named pipelines before saving; normalize names to lowercase.
  const payload = state.pipelines
    .filter(p => p.name && p.name.trim())
    .map(p => ({ name: p.name.trim().toLowerCase(), description: p.description || "", steps: p.steps }));
  try {
    const data = await api("/api/pipelines", {
      method: "POST",
      body: JSON.stringify({ source: state.plSource, pipelines: payload }),
    });
    setPlDirty(false);
    draftClearPipelines();             // server save succeeded -> drop the draft
    toast("Saved all ✓", `${data.source}: saved ${data.count} pipelines · backup: ${data.backup || "none"}`, "ok", 5000);
    await loadPipelines();
  } catch (err) {
    toast("Save failed", err.message, "err");
  }
}

let _lastRunPipelineName = null;
let _lastRunPipelineSource = null;
let _runAbortController = null;
let _runStoppedByUser = false;
let _runAutoCloseTimer = null;
let _runLastActivity = 0;

// Auto-close the run modal 10s after the pipeline finishes (success only).
// User interaction (mouse move / click / scroll / key inside the dialog)
// RESETS the countdown back to 10s so the user keeps their reading time.
function cancelRunAutoClose() {
  if (_runAutoCloseTimer) {
    clearInterval(_runAutoCloseTimer);
    _runAutoCloseTimer = null;
  }
  const badge = $("#run-autoclose-badge");
  if (badge) {
    badge.classList.add("hidden");
    badge.textContent = "";
  }
}

// Record user activity inside the run modal (used by the auto-close tick).
function markRunActivity() {
  _runLastActivity = Date.now();
}

function scheduleRunAutoClose(ok) {
  cancelRunAutoClose();
  // Only auto-close on success; failures stay open so the user can read the log.
  if (!ok) return;
  const modal = $("#modal-run");
  const badge = $("#run-autoclose-badge");
  if (!modal || modal.classList.contains("hidden")) return;
  let remain = 10;
  const tick = () => {
    if (!modal || modal.classList.contains("hidden")) { cancelRunAutoClose(); return; }
    // User recently interacted with the dialog (mouse move/click/scroll/key):
    // reset the countdown back to 10s so it never closes under the cursor.
    if (Date.now() - _runLastActivity < 1500) {
      remain = 10;
      if (badge) {
        badge.classList.remove("hidden");
        badge.textContent = "⏳ Auto-close 10s";
      }
      return;
    }
    if (badge) {
      badge.classList.remove("hidden");
      badge.textContent = `⏳ Auto-close ${remain}s`;
    }
    if (remain <= 0) {
      cancelRunAutoClose();
      modal.classList.add("hidden");
      return;
    }
    remain--;
  };
  tick();
  _runAutoCloseTimer = setInterval(tick, 1000);
}

const PL_OUTPUT_MODE_KEY = "telua_pl_output_mode";
let _plOutputMode = localStorage.getItem(PL_OUTPUT_MODE_KEY) || "bottom";

function setPipelineOutputMode(mode) {
  _plOutputMode = mode === "dialog" ? "dialog" : "bottom";
  try {
    localStorage.setItem(PL_OUTPUT_MODE_KEY, _plOutputMode);
  } catch { /* ignore */ }
  const chk = $("#chk-pl-output-dock");
  if (chk) chk.checked = (_plOutputMode === "bottom");
}

async function stopPipelineRun() {
  if (!_runAbortController) return;
  _runStoppedByUser = true;
  const badge1 = $("#run-status-badge");
  const badge2 = $("#pl-bottom-status-badge");
  [badge1, badge2].forEach(b => {
    if (b) {
      b.textContent = "⏹ Stopping…";
      b.className = "run-badge err";
    }
  });
  try { await fetch("/api/terminal/stop", { method: "POST" }); } catch { /* ignore */ }
  try { _runAbortController.abort(); } catch { /* ignore */ }
}

async function runPipeline(name, explicitSource = null) {
  const source = explicitSource || state.plSource;
  _lastRunPipelineName = name;
  _lastRunPipelineSource = source;
  const cmdMap = { my: "telua my", multi: "telua run", system: "telua system", docker: "telua system", car: "telua car", dump: "telua dump" };
  const cmd = cmdMap[source] || "telua my";

  const isBottom = _plOutputMode === "bottom";
  const modalEl = $("#modal-run");
  const bottomPanel = $("#pl-bottom-panel");

  if (isBottom) {
    bottomPanel?.classList.remove("hidden");
    modalEl?.classList.add("hidden");
  } else {
    modalEl?.classList.remove("hidden");
    bottomPanel?.classList.add("hidden");
  }

  const outEl = isBottom ? $("#pl-bottom-output") : $("#run-output");
  const badge = isBottom ? $("#pl-bottom-status-badge") : $("#run-status-badge");
  const titleEl = isBottom ? $("#pl-bottom-title") : $("#run-title");
  const rerunBtn = isBottom ? $("#btn-pl-bottom-rerun") : $("#btn-run-again");
  const runStopBtn = isBottom ? $("#btn-pl-bottom-stop") : $("#btn-run-stop");

  if (titleEl) titleEl.textContent = `${cmd} ${name}`;

  const matchedPl = state.pipelines.find(p => p.name === name);
  const stepsHint = matchedPl && matchedPl.steps?.length
    ? matchedPl.steps.map((s, i) => `  [${i + 1}/${matchedPl.steps.length}] ${s}`).join("\n")
    : `  $ ${cmd} ${name}`;
  if (outEl) outEl.textContent = `⏳ Starting: ${cmd} ${name}…\n${stepsHint}\n`;

  let elapsed = 0;
  if (badge) {
    badge.textContent = "⏳ Running… (0s)";
    badge.className = "run-badge running";
  }
  let receivedStreamChunk = false;
  const timerId = setInterval(() => {
    elapsed++;
    if (badge && !_runStoppedByUser) badge.textContent = `⏳ Running… (${elapsed}s)`;
    if (!receivedStreamChunk && outEl && !_runStoppedByUser) {
      outEl.textContent =
        `⏳ Executing '${cmd} ${name}'… (${elapsed}s elapsed)\n` +
        `${stepsHint}\n\n` +
        `[Running process on host — live output will appear below…]`;
    }
  }, 1000);

  _runStoppedByUser = false;
  _runAbortController = new AbortController();
  const signal = _runAbortController.signal;
  if (rerunBtn) rerunBtn.disabled = true;
  if (runStopBtn) {
    runStopBtn.disabled = false;
    runStopBtn.classList.add("danger-solid");
  }
  if (!isBottom) {
    cancelRunAutoClose();
  }

  try {
    // Try live streaming endpoint first so output lines appear in real time
    const res = await fetch("/api/pipeline/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, source }),
      signal,
    });

    if (res.ok && res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let rawBuffer = "";
      let exitCode = 0;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value) {
          receivedStreamChunk = true;
          rawBuffer += decoder.decode(value, { stream: true });
          const cleanPreview = rawBuffer.replace(/\n?__TELUA_EXIT_CODE__:\s*-?\d+\s*$/, "");
          if (outEl) {
            outEl.innerHTML = ansiToHtml(cleanPreview || "Running…");
            outEl.scrollTop = outEl.scrollHeight;
          }
        }
      }

      const m = rawBuffer.match(/__TELUA_EXIT_CODE__:(-?\d+)/);
      if (m) exitCode = parseInt(m[1], 10);
      const finalOutput = rawBuffer.replace(/\n?__TELUA_EXIT_CODE__:\s*-?\d+\s*$/, "");
      if (outEl) {
        outEl.innerHTML = ansiToHtml(
          (finalOutput || "(no output)") +
          `\n\n[exit code: ${exitCode} · elapsed: ${elapsed}s]`
        );
        outEl.scrollTop = outEl.scrollHeight;
      }
      if (badge) {
        const ok = exitCode === 0;
        badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${exitCode} (${elapsed}s)`;
        badge.className = "run-badge " + (ok ? "ok" : "err");
      }
      if (!isBottom) {
        scheduleRunAutoClose(exitCode === 0);
      }
      return;
    }

    // Fallback to batch /api/pipeline/run if server hasn't restarted with /stream yet
    const data = await api("/api/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ name, source }),
      signal,
    });
    receivedStreamChunk = true;
    if (outEl) {
      outEl.innerHTML = ansiToHtml(
        (data.output || "(no output)") +
        `\n\n[exit code: ${data.exit_code} · elapsed: ${elapsed}s]`
      );
    }
    if (badge) {
      const ok = data.exit_code === 0;
      badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${data.exit_code} (${elapsed}s)`;
      badge.className = "run-badge " + (ok ? "ok" : "err");
    }
    if (!isBottom) {
      scheduleRunAutoClose(data.exit_code === 0);
    }
  } catch (err) {
    if (_runStoppedByUser || err.name === "AbortError") {
      if (outEl) outEl.innerHTML += `\n<span style="color:#d29922;font-weight:700">^C [Stopped by user · ${elapsed}s]</span>\n`;
      if (badge) {
        badge.textContent = `⏹ Stopped (${elapsed}s)`;
        badge.className = "run-badge err";
      }
    } else {
      if (outEl) outEl.textContent = `[ERROR] ${err.message}`;
      if (badge) {
        badge.textContent = "✖ Error";
        badge.className = "run-badge err";
      }
    }
  } finally {
    clearInterval(timerId);
    _runAbortController = null;
    if (rerunBtn) rerunBtn.disabled = false;
    if (runStopBtn) {
      runStopBtn.disabled = true;
      runStopBtn.classList.remove("danger-solid");
    }
  }
}

function addPipeline() {
  if ($("#pl-filter") && $("#pl-filter").value) {
    $("#pl-filter").value = "";
  }
  let i = 1;
  const existing = new Set(state.pipelines.map(p => p.name));
  let name = "new_pipeline";
  while (existing.has(name)) { name = `new_pipeline_${++i}`; }
  const prefixMap = { my: "MY_CMD_", multi: "MULTI_CMD_", docker: "SYSTEM_CMD_", system: "SYSTEM_CMD_", car: "ADB_SHELL_CAR_", dump: "DUMP_CMD_" };
  const prefix = prefixMap[state.plSource] || "MY_CMD_";
  state.pipelines.push({
    name,
    description: "",
    array: `${prefix}` + name.toUpperCase(),
    steps: [""],
    _editing: true,
    _expanded: true,
    _editingStep: 0,
  });
  setPlDirty(true);
  renderPipelines();
  const cards = document.querySelectorAll(".pl-card");
  cards[cards.length - 1]?.querySelector(".pl-name")?.focus();
}

/* ---------------- Profile switcher ---------------- */
function openProfileModal() {
  const s = state.status;
  const profiles = (s && s.profiles) || [];
  const list = $("#profile-list");
  list.innerHTML = "";
  if (profiles.length === 0) {
    list.innerHTML = `<p class="meta">No profiles found in apk.config.</p>`;
  }
  for (const p of profiles) {
    const item = document.createElement("div");
    item.className = "profile-item" + (p === s.active_project ? " active" : "");
    item.innerHTML = `<span>${esc(p)}</span><span class="meta">${p === s.active_project ? "● active" : "switch →"}</span>`;
    item.addEventListener("click", async () => {
      if (p === s.active_project) return;
      try {
        const data = await api("/api/profile", {
          method: "POST",
          body: JSON.stringify({ name: p }),
        });
        toast("Profile switched ✓", `ACTIVE_PROJECT="${data.active_project}" (backup: ${data.backup || "none"})`, "ok");
        $("#modal-profile").classList.add("hidden");
        refreshStatus();
        if (!$("#view-aosp")?.classList.contains("hidden")) loadAospConfig();
        if (state.current && (state.current.name === "config/apk.config" || state.current.name === "apk.config")) openFile(state.current.name);
      } catch (err) {
        toast("Switch failed", err.message, "err");
      }
    });
    list.appendChild(item);
  }
  $("#modal-profile").classList.remove("hidden");
}

/* ---------------- Info modal ---------------- */
async function showInfo() {
  $("#info-output").textContent = "Running build_apk.sh --info …";
  $("#modal-info").classList.remove("hidden");
  try {
    const data = await api("/api/info");
    $("#info-output").innerHTML = ansiToHtml(data.output || "(no output)");
  } catch (err) {
    $("#info-output").textContent = `[ERROR] ${err.message}`;
  }
}

/* ---------------- Crypto & Overlay modal ---------------- */
let _lastCryptoItems = [];

function updateCryptoButtons() {
  const target = $("#crypto-target")?.value || "all";
  const relevant = target === "all"
    ? _lastCryptoItems
    : _lastCryptoItems.filter(it => it.name === target);
  const canEncrypt = relevant.some(it => it.plain_exists);
  const canDecrypt = relevant.some(it => it.enc_exists);
  const encBtn = $("#btn-crypto-encrypt");
  const decBtn = $("#btn-crypto-decrypt");
  const decForceBtn = $("#btn-crypto-decrypt-force");
  if (encBtn) {
    encBtn.disabled = !canEncrypt;
    encBtn.title = canEncrypt
      ? "Encrypt plain .config -> enc_*.config"
      : "No plain .config file found for the selected target";
  }
  if (decBtn) {
    decBtn.disabled = !canDecrypt;
    decBtn.title = canDecrypt
      ? "Decrypt enc_*.config -> dec_*.config for inspection (does not overwrite active config)"
      : "No enc_*.config file exists yet — click '🔐 Encrypt' first";
  }
  if (decForceBtn) {
    decForceBtn.disabled = !canDecrypt;
    decForceBtn.title = canDecrypt
      ? "Decrypt enc_*.config -> *.config and OVERWRITE active config files"
      : "No enc_*.config file exists yet — click '🔐 Encrypt' first";
  }
}

function renderCryptoItems(items = []) {
  _lastCryptoItems = items;
  const list = $("#crypto-status-list");
  if (!list) return;
  list.innerHTML = "";
  let encCount = 0;
  for (const it of items) {
    if (it.enc_exists) encCount++;
    const row = document.createElement("div");
    row.className = "profile-item";
    row.style.cursor = "default";
    const plainBadge = it.plain_exists
      ? `✔ plain (${it.plain_size}B · ${it.plain_mtime || ""})`
      : "— missing plain";
    const encBadge = it.enc_exists
      ? `🔐 enc (${it.enc_size}B · ${it.enc_mtime || ""})`
      : "⚠ not encrypted";
    const decBadge = it.dec_exists
      ? ` · 👁 dec (${it.dec_size}B)`
      : "";
    const syncBadge = it.plain_exists && it.enc_exists
      ? (it.synced ? " · ✓ synced" : " · ⚠ plain newer")
      : "";
    row.innerHTML = `
      <div>
        <div><b>${esc(it.plain_rel)}</b></div>
        <div class="meta">${esc(it.enc_rel)}${it.dec_exists ? ` · <span style="color:var(--accent)">${esc(it.dec_rel)}</span>` : ""}</div>
      </div>
      <div class="meta" style="text-align:right">
        <div>${esc(plainBadge + decBadge)}</div>
        <div>${esc(encBadge + syncBadge)}</div>
      </div>
    `;
    list.appendChild(row);
  }
  const chip = $("#chip-crypto");
  if (chip) {
    chip.textContent = `🔐 enc: ${encCount}/${items.length}`;
    chip.className = "chip " + (encCount === items.length ? "ok" : encCount > 0 ? "warn" : "");
  }
  updateCryptoButtons();
}

async function refreshCryptoStatus() {
  try {
    const data = await api("/api/crypto/status");
    renderCryptoItems(data.items || []);
  } catch { /* ignore */ }
}

async function openCryptoModal(defaultTarget = "all") {
  const targetSel = $("#crypto-target");
  if (targetSel) targetSel.value = defaultTarget;
  const out = $("#crypto-output");
  if (out) {
    out.textContent = "";
    out.classList.add("hidden");
  }
  $("#modal-crypto").classList.remove("hidden");
  await refreshCryptoStatus();
  $("#crypto-password")?.focus();
}

async function runCryptoAction(action, force = false) {
  const target = $("#crypto-target")?.value || "all";
  const password = $("#crypto-password")?.value || "";
  const out = $("#crypto-output");

  if ((action === "encrypt" || action === "decrypt") && !password) {
    toast("Password required", "Please enter the password for " + action + ".", "warn");
    $("#crypto-password")?.focus();
    return;
  }

  if (action === "decrypt" && force) {
    const targetDesc = target === "all" ? "all config files in config/overlay/" : `config/overlay/${target}`;
    const ok = await confirmDialog({
      title: "⚠️ Decrypt & Override",
      message: `Are you sure you want to decrypt enc_*.config and OVERWRITE ${targetDesc}?`,
      detail: target === "all"
        ? "enc_apk_overlays.config → apk_overlays.config\nenc_const_my_cli.config → const_my_cli.config"
        : `enc_${target} → ${target}`,
      hint: "💡 To inspect decrypted content without overwriting active files, click '🔓 Decrypt' instead (creates dec_*.config).",
      confirmText: "⚠️ Confirm Override",
      icon: "⚠️",
    });
    if (!ok) return;
  }

  const label = (action === "decrypt" && force) ? "decrypt (override)" : action;
  if (out) {
    out.textContent = `Running ${label}…`;
    out.classList.remove("hidden");
  }
  try {
    const data = await api("/api/crypto/action", {
      method: "POST",
      body: JSON.stringify({ action, target, password, force }),
    });
    if ($("#crypto-password")) $("#crypto-password").value = "";
    if (out) {
      out.textContent = data.output || `${label} completed successfully.`;
      out.classList.remove("hidden");
    }
    renderCryptoItems(data.items || []);
    toast(`Crypto ${label} ✓`, data.output || "Success", "ok");
    if (action === "decrypt" && force) {
      // Discard any stale browser drafts so the freshly decrypted config takes effect immediately.
      if (target === "all" || target === "const_my_cli.config") draftClearPipelines();
      if (state.current && (target === "all" || state.current.name.endsWith(target))) draftClearFile();
    }
    await Promise.all([refreshFiles(), refreshStatus()]);
    if (action === "decrypt" || action === "apply_overlay") {
      await loadPipelines(draftLoadPipelines());
      if (state.current) openFile(state.current.name);
    }
  } catch (err) {
    if (out) {
      out.textContent = `[ERROR] ${err.message}`;
      out.classList.remove("hidden");
    }
    toast(`Crypto ${label} failed`, err.message, "err");
  }
}

/* ---------------- Terminal Tab ---------------- */
const TERM_HISTORY_KEY = "telua_web_term_history";
const TERM_CWD_KEY = "telua_web_term_cwd";
let _termHistory = [];
let _termHistoryIdx = -1;
let _termRunning = false;
let _termCwd = "";
let _termAbortController = null;
let _termStoppedByUser = false;

try {
  const savedHist = JSON.parse(localStorage.getItem(TERM_HISTORY_KEY) || "[]");
  if (Array.isArray(savedHist)) _termHistory = savedHist.slice(-50);
  _termCwd = localStorage.getItem(TERM_CWD_KEY) || "";
} catch { /* ignore */ }

function _setTermCwd(newCwd) {
  if (!newCwd) return;
  _termCwd = newCwd.trim();
  try { localStorage.setItem(TERM_CWD_KEY, _termCwd); } catch { /* ignore */ }
  const cwdEl = $("#term-cwd");
  if (cwdEl) cwdEl.textContent = `cwd: ${_termCwd}`;
  const promptEl = document.querySelector(".term-prompt");
  if (promptEl) {
    const shortDir = _termCwd === "/" ? "/" : (_termCwd.split(/[\\/]/).filter(Boolean).pop() || _termCwd);
    promptEl.textContent = `tel:${shortDir} $`;
    promptEl.title = `Working directory: ${_termCwd}`;
  }
}

function _extractAndApplyTermPwd(rawText) {
  if (!rawText) return "";
  let updatedPwd = null;
  const cleaned = String(rawText).replace(/\n?__TELUA_PWD__:([^\r\n]+)\r?\n?/g, (_, pwd) => {
    updatedPwd = pwd.trim();
    return "\n";
  });
  if (updatedPwd) _setTermCwd(updatedPwd);
  return cleaned.replace(/^\n+|\n+$/g, "") ? cleaned.replace(/\n+$/, "\n") : "";
}

function clearTerminalOutput() {
  const outEl = $("#term-output");
  if (outEl) {
    outEl.innerHTML = ansiToHtml("💻 Telua Web CLI Terminal — screen cleared.\n");
  }
  const badge = $("#term-status-badge");
  if (badge) {
    badge.textContent = "Ready";
    badge.className = "run-badge";
  }
}

async function newTerminalSession() {
  if (_termRunning) {
    await stopTerminalCommand();
  }
  try { localStorage.removeItem(TERM_CWD_KEY); } catch { /* ignore */ }
  const rootDir = (state.status && state.status.root) || "";
  if (rootDir) {
    _setTermCwd(rootDir);
  } else {
    _termCwd = "";
    const cwdEl = $("#term-cwd");
    if (cwdEl) cwdEl.textContent = "cwd: —";
    const promptEl = document.querySelector(".term-prompt");
    if (promptEl) {
      promptEl.textContent = "tel $";
      promptEl.title = "";
    }
  }
  const outEl = $("#term-output");
  if (outEl) {
    const cwdHint = _termCwd ? ` (cwd: ${_termCwd})` : "";
    outEl.innerHTML = ansiToHtml(
      `💻 Telua Web CLI Terminal — new session started${cwdHint}.\n` +
      `• Type any CLI command below (e.g. tel system ram, tel --git-help, git status -s, free -h, df -h, adb devices…) and press Enter.\n` +
      `• Shortcuts: ↑ / ↓ for command history · Ctrl+C (or ⏹ Stop) to abort a running command · type 'clear' to clear the screen.\n`
    );
  }
  const badge = $("#term-status-badge");
  if (badge) {
    badge.textContent = "Ready";
    badge.className = "run-badge";
  }
  const input = $("#term-input");
  if (input) {
    input.value = "";
    input.focus();
  }
  toast("New session started 🔄", `Terminal reset${_termCwd ? ` to ${_termCwd}` : ""}.`, "info", 2200);
}

function _stripPipelineWrapperOutput(raw) {
  if (!raw) return "";
  const lines = String(raw).split("\n");
  const filtered = lines.filter(line => {
    const plain = line.replace(/\x1b\[[0-9;]*m/g, "").trim();
    if (plain.startsWith("[INFO] ============================================================")) return false;
    if (plain.startsWith("[INFO]  Executing Pipeline: '_term_exec'")) return false;
    if (plain.startsWith("[INFO]  Description: Web Terminal")) return false;
    if (plain.startsWith("[INFO]  Total Steps:")) return false;
    if (plain.startsWith("[STEP 1/1]")) return false;
    if (plain.startsWith("[SUCCESS] Step 1/1 finished")) return false;
    if (plain.startsWith("[SUCCESS] All 1 steps of pipeline '_term_exec' completed")) return false;
    if (plain.startsWith("[ERROR] Step 1 failed with exit code")) return false;
    return true;
  });
  const stripped = filtered.join("\n").replace(/^\n+|\n+$/g, "");
  return stripped ? stripped + "\n" : "";
}

async function _fallbackTerminalViaExistingApis(cmd, signal = null) {
  const norm = cmd.trim().replace(/\s+/g, " ");
  if (norm === "tel --info" || norm === "telua --info" || norm === "./build_apk.sh --info") {
    const data = await api("/api/info", signal ? { signal } : {});
    return { ok: data.ok, exit_code: data.exit_code ?? 0, output: data.output || "" };
  }
  const helpMap = {
    "tel --git-help": "config/const_git.config",
    "telua --git-help": "config/const_git.config",
    "tel --docker-help": "config/const_docker.config",
    "telua --docker-help": "config/const_docker.config",
    "tel --network-help": "config/const_network.config",
    "telua --network-help": "config/const_network.config",
  };
  if (helpMap[norm]) {
    const data = await api(`/api/file?name=${encodeURIComponent(helpMap[norm])}`, signal ? { signal } : {});
    return { ok: true, exit_code: 0, output: data.content || "" };
  }
  const listMatch = norm.match(/^(?:tel|telua)\s+(system|docker|my|run|multi|car|dump)$/);
  if (listMatch) {
    const srcMap = { system: "system", docker: "system", my: "my", run: "multi", multi: "multi", car: "car", dump: "dump" };
    const src = srcMap[listMatch[1]];
    const data = await api(`/api/pipelines?source=${encodeURIComponent(src)}`, signal ? { signal } : {});
    const lines = (data.pipelines || []).map(p => `  • ${p.name.padEnd(18)} → ${p.description || ""}`);
    return {
      ok: true,
      exit_code: 0,
      output: `[AVAILABLE '${listMatch[1].toUpperCase()}' COMMANDS (${data.file || src})]\n` + lines.join("\n") + "\n",
    };
  }
  const runMatch = norm.match(/^(?:tel|telua)\s+(system|docker|my|run|car|dump)\s+([A-Za-z0-9_-]+)$/);
  if (runMatch) {
    const srcMap = { system: "system", docker: "system", my: "my", run: "multi", car: "car", dump: "dump" };
    const data = await api("/api/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ source: srcMap[runMatch[1]], name: runMatch[2] }),
      ...(signal ? { signal } : {}),
    });
    return { ok: data.ok, exit_code: data.exit_code ?? 0, output: data.output || "" };
  }

  // Universal fallback for ANY Linux/shell command (cd /opt, pwd, ls, git status, free -h, etc.)
  // Preserves working directory (_termCwd) across commands!
  const cdPrefix = _termCwd ? `cd ${JSON.stringify(_termCwd)} >/dev/null 2>&1 || true; ` : "";
  const wrappedCmd = `${cdPrefix}${cmd}; __telua_rc=$?; printf "\\n__TELUA_PWD__:%s\\n" "$(pwd)"; (exit $__telua_rc)`;

  const origData = await api("/api/pipelines?source=multi");
  const origList = (origData.pipelines || [])
    .filter(p => p.name && p.name !== "_term_exec")
    .map(p => ({ name: p.name, description: p.description || "", steps: p.steps || [] }));
  const tempList = [
    ...origList,
    { name: "_term_exec", description: "Web Terminal Ad-hoc Command", steps: [`eval ${JSON.stringify(wrappedCmd)}`] },
  ];
  try {
    await api("/api/pipelines", {
      method: "POST",
      body: JSON.stringify({ source: "multi", pipelines: tempList }),
    });
    const runData = await api("/api/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ source: "multi", name: "_term_exec" }),
      ...(signal ? { signal } : {}),
    });
    const stripped = _stripPipelineWrapperOutput(runData.output || "");
    const finalOut = _extractAndApplyTermPwd(stripped);
    return {
      ok: runData.ok,
      exit_code: runData.exit_code ?? 0,
      output: finalOut || (/^cd(\s|$)/.test(norm) && runData.ok ? `📂 cwd → ${_termCwd}\n` : ""),
    };
  } finally {
    try {
      await api("/api/pipelines", {
        method: "POST",
        body: JSON.stringify({ source: "multi", pipelines: origList }),
      });
    } catch { /* ignore */ }
  }
}

async function stopTerminalCommand() {
  if (!_termRunning) return;
  _termStoppedByUser = true;
  const badge = $("#term-status-badge");
  if (badge) {
    badge.textContent = "⏹ Stopping (Ctrl+C)…";
    badge.className = "run-badge err";
  }

  // Fallback abort if process does not exit after SIGINT within 900ms
  const abortTimer = setTimeout(() => {
    try { _termAbortController?.abort(); } catch { /* ignore */ }
  }, 900);

  try {
    const res = await fetch("/api/terminal/stop", { method: "POST" });
    if (res.status === 404) {
      // Old server fallback: send SIGINT via 'my' pipeline so running 'ping' / '_term_exec' exits cleanly
      const origMy = await api("/api/pipelines?source=my");
      const origMyList = (origMy.pipelines || [])
        .filter(p => p.name && p.name !== "_term_stop")
        .map(p => ({ name: p.name, description: p.description || "", steps: p.steps || [] }));
      const killCmd = "eval \"pkill -INT ping 2>/dev/null; pkill -INT -f '_term_exec' 2>/dev/null; true\"";
      try {
        await api("/api/pipelines", {
          method: "POST",
          body: JSON.stringify({
            source: "my",
            pipelines: [...origMyList, { name: "_term_stop", description: "Ctrl+C Stop", steps: [killCmd] }],
          }),
        });
        await api("/api/pipeline/run", {
          method: "POST",
          body: JSON.stringify({ source: "my", name: "_term_stop" }),
        });
      } finally {
        try {
          await api("/api/pipelines", {
            method: "POST",
            body: JSON.stringify({ source: "my", pipelines: origMyList }),
          });
        } catch { /* ignore */ }
      }
    }
  } catch { /* ignore */ } finally {
    clearTimeout(abortTimer);
    try { _termAbortController?.abort(); } catch { /* ignore */ }
  }
}

async function runTerminalCommand(explicitCmd = null) {
  const input = $("#term-input");
  const cmd = (explicitCmd != null ? explicitCmd : (input?.value || "")).trim();
  if (!cmd) {
    input?.focus();
    return;
  }
  if (_termRunning) {
    toast("Terminal busy", "Please wait for the current command to finish (or click ⏹ Stop).", "warn", 2500);
    return;
  }

  if (input && explicitCmd == null) input.value = "";
  if (_termHistory[_termHistory.length - 1] !== cmd) {
    _termHistory.push(cmd);
    if (_termHistory.length > 50) _termHistory = _termHistory.slice(-50);
    try { localStorage.setItem(TERM_HISTORY_KEY, JSON.stringify(_termHistory)); } catch { /* ignore */ }
  }
  _termHistoryIdx = _termHistory.length;

  if (cmd === "clear" || cmd === "cls") {
    clearTerminalOutput();
    input?.focus();
    return;
  }

  const outEl = $("#term-output");
  const badge = $("#term-status-badge");
  const runBtn = $("#btn-term-run");
  const stopBtn = $("#btn-term-stop");
  _termRunning = true;
  _termStoppedByUser = false;
  _termAbortController = new AbortController();
  const signal = _termAbortController.signal;
  if (runBtn) runBtn.disabled = true;
  if (stopBtn) {
    stopBtn.disabled = false;
    stopBtn.classList.add("danger-solid");
  }

  const separator = outEl && outEl.innerHTML.trim() ? "\n" : "";
  const shortDir = _termCwd ? (_termCwd === "/" ? "/" : (_termCwd.split(/[\\/]/).filter(Boolean).pop() || _termCwd)) : "";
  const promptLabel = shortDir ? `tel:${shortDir} $` : "tel $";
  const baseHtml = (outEl ? outEl.innerHTML : "") +
    `${separator}<span style="color:#3fb950;font-weight:700">${esc(promptLabel)}</span> <span style="color:#58a6ff;font-weight:700">${esc(cmd)}</span>\n`;
  if (outEl) {
    outEl.innerHTML = baseHtml + `<span style="opacity:.7">⏳ Running… (press Ctrl+C or click ⏹ Stop to abort)</span>\n`;
    outEl.scrollTop = outEl.scrollHeight;
  }

  let elapsed = 0;
  if (badge) {
    badge.textContent = "⏳ Running… (0s)";
    badge.className = "run-badge running";
  }
  const timerId = setInterval(() => {
    elapsed++;
    if (badge && !_termStoppedByUser) badge.textContent = `⏳ Running… (${elapsed}s)`;
  }, 1000);

  let streamedPreview = "";
  try {
    const res = await fetch("/api/terminal/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd, cwd: _termCwd }),
      signal,
    });

    if (res.ok && res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let rawBuffer = "";
      let exitCode = 0;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value) {
          rawBuffer += decoder.decode(value, { stream: true });
          const cleanPreview = rawBuffer
            .replace(/\n?__TELUA_EXIT_CODE__:\s*-?\d+\s*$/, "")
            .replace(/\n?__TELUA_PWD__:[^\r\n]+\r?\n?/g, "\n");
          streamedPreview = cleanPreview;
          if (outEl) {
            outEl.innerHTML = baseHtml + ansiToHtml(cleanPreview);
            outEl.scrollTop = outEl.scrollHeight;
          }
        }
      }

      const m = rawBuffer.match(/__TELUA_EXIT_CODE__:(-?\d+)/);
      if (m) exitCode = parseInt(m[1], 10);
      const withoutExit = rawBuffer.replace(/\n?__TELUA_EXIT_CODE__:\s*-?\d+\s*$/, "");
      const finalOutput = _extractAndApplyTermPwd(withoutExit) ||
        (/^cd(\s|$)/.test(cmd) && exitCode === 0 ? `📂 cwd → ${_termCwd}\n` : "(no output)\n");
      const stoppedSuffix = _termStoppedByUser ? `\n<span style="color:#d29922;font-weight:700">^C [Stopped by Ctrl+C · ${elapsed}s]</span>\n` : "";
      const statusColor = exitCode === 0 ? "#3fb950" : "#f85149";
      if (outEl) {
        outEl.innerHTML = baseHtml +
          ansiToHtml(finalOutput) +
          (stoppedSuffix || `<span style="color:${statusColor};opacity:.85">[exit code: ${exitCode} · ${elapsed}s]</span>\n`);
        outEl.scrollTop = outEl.scrollHeight;
      }
      if (badge) {
        if (_termStoppedByUser) {
          badge.textContent = `⏹ Stopped (Ctrl+C · ${elapsed}s)`;
          badge.className = "run-badge err";
        } else {
          const ok = exitCode === 0;
          badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${exitCode} (${elapsed}s)`;
          badge.className = "run-badge " + (ok ? "ok" : "err");
        }
      }
      return;
    }

    if (res.status === 404) {
      const fb = await _fallbackTerminalViaExistingApis(cmd, signal);
      if (fb) {
        const statusColor = fb.ok ? "#3fb950" : "#f85149";
        const stoppedSuffix = _termStoppedByUser ? `<span style="color:#d29922;font-weight:700">^C [Stopped by Ctrl+C · ${elapsed}s]</span>\n` : "";
        if (outEl) {
          outEl.innerHTML = baseHtml +
            ansiToHtml(fb.output || "(no output)\n") +
            (stoppedSuffix || `<span style="color:${statusColor};opacity:.85">[exit code: ${fb.exit_code} · ${elapsed}s]</span>\n`);
          outEl.scrollTop = outEl.scrollHeight;
        }
        if (badge) {
          if (_termStoppedByUser) {
            badge.textContent = `⏹ Stopped (Ctrl+C · ${elapsed}s)`;
            badge.className = "run-badge err";
          } else {
            badge.textContent = fb.ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${fb.exit_code} (${elapsed}s)`;
            badge.className = "run-badge " + (fb.ok ? "ok" : "err");
          }
        }
        return;
      }
      throw new Error(
        "Web server is running an older in-memory process (missing /api/terminal/*).\n" +
        "👉 Run 'tel web restart' on the host to enable full terminal streaming!"
      );
    }

    const data = await api("/api/terminal/run", {
      method: "POST",
      body: JSON.stringify({ command: cmd, cwd: _termCwd }),
      signal,
    });
    const ok = data.exit_code === 0;
    const statusColor = ok ? "#3fb950" : "#f85149";
    const cleanedOut = _extractAndApplyTermPwd(data.output || "") ||
      (/^cd(\s|$)/.test(cmd) && ok ? `📂 cwd → ${_termCwd}\n` : "(no output)\n");
    if (outEl) {
      outEl.innerHTML = baseHtml +
        ansiToHtml(cleanedOut) +
        `<span style="color:${statusColor};opacity:.85">[exit code: ${data.exit_code} · ${elapsed}s]</span>\n`;
      outEl.scrollTop = outEl.scrollHeight;
    }
    if (badge) {
      badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${data.exit_code} (${elapsed}s)`;
      badge.className = "run-badge " + (ok ? "ok" : "err");
    }
  } catch (err) {
    if (_termStoppedByUser || err.name === "AbortError") {
      if (outEl) {
        outEl.innerHTML = baseHtml +
          (streamedPreview ? ansiToHtml(streamedPreview) : "") +
          `<span style="color:#d29922;font-weight:700">^C [Stopped by Ctrl+C · ${elapsed}s]</span>\n`;
        outEl.scrollTop = outEl.scrollHeight;
      }
      if (badge) {
        badge.textContent = `⏹ Stopped (Ctrl+C · ${elapsed}s)`;
        badge.className = "run-badge err";
      }
    } else {
      if (outEl) {
        outEl.innerHTML = baseHtml + `<span style="color:#f85149">[ERROR] ${esc(err.message)}</span>\n`;
        outEl.scrollTop = outEl.scrollHeight;
      }
      if (badge) {
        badge.textContent = "✖ Error";
        badge.className = "run-badge err";
      }
    }
  } finally {
    clearInterval(timerId);
    _termRunning = false;
    _termAbortController = null;
    if (runBtn) runBtn.disabled = false;
    if (stopBtn) {
      stopBtn.disabled = true;
      stopBtn.classList.remove("danger-solid");
    }
    input?.focus();
  }
}

/* ---------------- Sphinx Docs & Quill.js ---------------- */
let _quill = null;
let _docsFiles = [];
let _currentDoc = null; // { name, rst, html, mtime, readonly }
let _docsEditorType = localStorage.getItem("telua_web_docs_editor") || (localStorage.getItem("telua_web_docs_mode") === "raw" ? "raw" : "wysiwyg"); // "wysiwyg" | "raw"
let _docsSplit = localStorage.getItem("telua_web_docs_split") === "true" || localStorage.getItem("telua_web_docs_mode") === "split";
let _docsMode = _docsSplit ? "split" : _docsEditorType; // legacy sync
let _docsDirty = false;
let _docsCustomDir = localStorage.getItem("telua_web_docs_dir") || "";
let _docsActiveDir = "";
let _docsSyncScroll = localStorage.getItem("telua_web_docs_sync_scroll") !== "false"; // default true
let _syncScrollSource = null;
let _syncScrollTimer = null;

let _mermaidCounter = 0;

const PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_";

function getPlantumlUrl(text) {
  if (!text || !text.trim()) return "";
  let clean = text.trim();
  if (!clean.startsWith("@startuml")) {
    clean = `@startuml\n${clean}\n@enduml`;
  }
  return `/api/docs/plantuml/svg?code=${encodeURIComponent(clean)}`;
}

function autoResizeDiagramTextarea(el) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.max(120, Math.min(el.scrollHeight + 8, 600)) + "px";
}

function registerQuillDiagramBlots() {
  if (!window.Quill || window._quillDiagramBlotsRegistered) return;
  try {
    const BlockEmbed = Quill.import("blots/block/embed");
    if (!BlockEmbed) return;

    class MermaidBlot extends BlockEmbed {
      static blotName = "mermaidBlock";
      static tagName = "div";
      static className = "mermaid-block";

      static create(value) {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        let code = "";
        if (typeof value === "string") {
          code = value;
        } else if (value && typeof value === "object") {
          code = value.getAttribute ? (value.getAttribute("data-mermaid") || value.querySelector("textarea")?.value || value.querySelector("pre")?.textContent || "") : (value.code || "");
        }
        node.setAttribute("data-mermaid", code);
        const safeCode = (code || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");

        node.innerHTML = `
          <div class="mermaid-header" contenteditable="false">
            <div class="mermaid-title-wrap">
              <span class="mermaid-label">📊 Mermaid Architecture Diagram</span>
              <span class="mermaid-chip">.. mermaid::</span>
            </div>
            <div class="mermaid-actions">
              <button type="button" class="mermaid-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
              <button type="button" class="mermaid-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
              <button type="button" class="mermaid-btn btn-copy-code" title="Copy Diagram Syntax">📋 Copy</button>
              <button type="button" class="mermaid-btn btn-del-diag danger" title="Delete Diagram">🗑</button>
            </div>
          </div>
          <div class="mermaid-diagram-wrap" contenteditable="false">
            <span class="mermaid-loading" style="color:var(--text-dim);font-size:12px;">⏳ Rendering Mermaid diagram graphic…</span>
          </div>
          <textarea class="mermaid-code-input" spellcheck="false" style="display:none;" title="Click to edit diagram syntax" placeholder="Type Mermaid syntax here…">${safeCode}</textarea>
        `;
        return node;
      }

      static value(node) {
        return node.getAttribute("data-mermaid") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      }
    }

    class PlantumlBlot extends BlockEmbed {
      static blotName = "plantumlBlock";
      static tagName = "div";
      static className = "plantuml-block";

      static create(value) {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        let code = "";
        if (typeof value === "string") {
          code = value;
        } else if (value && typeof value === "object") {
          code = value.getAttribute ? (value.getAttribute("data-plantuml") || value.querySelector("textarea")?.value || value.querySelector("pre")?.textContent || "") : (value.code || "");
        }
        node.setAttribute("data-plantuml", code);
        const safeCode = (code || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");

        const umlUrl = getPlantumlUrl(code);

        node.innerHTML = `
          <div class="plantuml-header" contenteditable="false">
            <div class="plantuml-title-wrap">
              <span class="plantuml-label">📐 PlantUML Architecture Diagram</span>
              <span class="plantuml-chip">.. uml::</span>
            </div>
            <div class="plantuml-actions">
              <button type="button" class="plantuml-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
              <button type="button" class="plantuml-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
              <button type="button" class="plantuml-btn btn-copy-uml" title="Copy PlantUML Syntax">📋 Copy</button>
              <button type="button" class="plantuml-btn btn-del-uml danger" title="Delete Diagram">🗑</button>
            </div>
          </div>
          <div class="plantuml-diagram-wrap" contenteditable="false">
            <img class="plantuml-svg-img" src="${umlUrl}" alt="PlantUML Diagram" loading="lazy" />
          </div>
          <textarea class="plantuml-code-input" spellcheck="false" style="display:none;" title="Click to edit diagram syntax" placeholder="Type PlantUML syntax here…">${safeCode}</textarea>
        `;
        return node;
      }

      static value(node) {
        return node.getAttribute("data-plantuml") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      }
    }

    class TableBlockBlot extends BlockEmbed {
      static blotName = "tableBlock";
      static tagName = "div";
      static className = "doc-table-block";

      static create(value) {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        const tableHtml = typeof value === "string" ? value : (value?.tableHtml || "");
        buildTableBlockCard(node, tableHtml);
        return node;
      }

      static value(node) {
        const table = node.querySelector("table");
        return table ? table.outerHTML : "";
      }
    }

    Quill.register(MermaidBlot);
    Quill.register(PlantumlBlot);
    Quill.register(TableBlockBlot);
    window._quillDiagramBlotsRegistered = true;
  } catch (err) {
    console.warn("Custom Quill Blots registration skipped:", err);
  }
}

function buildTableBlockCard(node, tableHtml) {
  let tempDiv = document.createElement("div");
  tempDiv.innerHTML = tableHtml || "";
  let table = tempDiv.querySelector("table");
  if (!table) {
    table = document.createElement("table");
    table.className = "doc-table-grid";
    table.innerHTML = `
      <thead>
        <tr><th>Header 1</th><th>Header 2</th><th>Header 3</th></tr>
      </thead>
      <tbody>
        <tr><td>Data 1</td><td>Data 2</td><td>Data 3</td></tr>
      </tbody>
    `;
  }
  table.classList.add("doc-table-grid");

  let captionText = "";
  const cap = table.querySelector("caption");
  if (cap) {
    captionText = cap.textContent.trim();
    cap.remove();
  }

  node.setAttribute("contenteditable", "false");
  node.innerHTML = `
    <div class="doc-table-header" contenteditable="false">
      <div class="doc-table-title-wrap">
        <span class="doc-table-label">▦ List Table</span>
        <span class="doc-table-chip">.. list-table::</span>
        <input type="text" class="doc-table-caption-input" placeholder="Table Title / Caption (optional)" value="${captionText.replace(/"/g, '&quot;')}">
      </div>
      <div class="doc-table-actions">
        <button type="button" class="doc-table-btn btn-table-add-row" title="Add Row at bottom">+ Row</button>
        <button type="button" class="doc-table-btn btn-table-add-col" title="Add Column at right">+ Col</button>
        <button type="button" class="doc-table-btn btn-table-del-row" title="Remove Last Row">- Row</button>
        <button type="button" class="doc-table-btn btn-table-del-col" title="Remove Last Column">- Col</button>
        <button type="button" class="doc-table-btn btn-table-del danger" title="Delete Table">🗑</button>
      </div>
    </div>
    <div class="doc-table-scroll" contenteditable="false"></div>
  `;

  const scrollWrap = node.querySelector(".doc-table-scroll");
  scrollWrap.appendChild(table);

  wireSingleTableBlock(node);
}

function wireSingleTableBlock(blockNode) {
  if (!blockNode || blockNode.dataset.wired) return;
  blockNode.dataset.wired = "true";

  const table = blockNode.querySelector("table");
  const captionInput = blockNode.querySelector(".doc-table-caption-input");

  if (captionInput) {
    captionInput.addEventListener("input", () => setDocsDirty(true));
    captionInput.addEventListener("keydown", (e) => e.stopPropagation());
    captionInput.addEventListener("paste", (e) => e.stopPropagation());
    captionInput.addEventListener("copy", (e) => e.stopPropagation());
    captionInput.addEventListener("cut", (e) => e.stopPropagation());
    captionInput.addEventListener("mousedown", (e) => e.stopPropagation());
  }

  function wireCells() {
    if (!table) return;
    const cells = table.querySelectorAll("th, td");
    for (const cell of cells) {
      if (cell.dataset.wired) continue;
      cell.dataset.wired = "true";
      cell.setAttribute("contenteditable", "true");
      cell.setAttribute("spellcheck", "false");

      cell.addEventListener("input", () => setDocsDirty(true));
      cell.addEventListener("mousedown", (e) => e.stopPropagation());
      cell.addEventListener("mouseup", (e) => e.stopPropagation());
      cell.addEventListener("click", (e) => e.stopPropagation());
      cell.addEventListener("copy", (e) => e.stopPropagation());
      cell.addEventListener("cut", (e) => {
        e.stopPropagation();
        setTimeout(() => setDocsDirty(true), 0);
      });
      cell.addEventListener("paste", (e) => {
        e.stopPropagation();
        setTimeout(() => setDocsDirty(true), 0);
      });
      cell.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Tab") {
          e.preventDefault();
          const allCells = Array.from(table.querySelectorAll("th, td"));
          const idx = allCells.indexOf(cell);
          if (e.shiftKey) {
            if (idx > 0) allCells[idx - 1].focus();
          } else {
            if (idx < allCells.length - 1) {
              allCells[idx + 1].focus();
            } else {
              addRow();
              const newCells = table.querySelectorAll("th, td");
              if (newCells.length > allCells.length) {
                newCells[allCells.length].focus();
              }
            }
          }
        }
      });
    }
  }

  function addRow() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    const numCols = rows.length > 0 ? rows[0].querySelectorAll("th, td").length : 3;
    const newTr = document.createElement("tr");
    for (let i = 0; i < numCols; i++) {
      const td = document.createElement("td");
      td.textContent = "";
      newTr.appendChild(td);
    }
    const tbody = table.querySelector("tbody") || table;
    tbody.appendChild(newTr);
    wireCells();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    const firstTd = newTr.querySelector("td");
    if (firstTd) firstTd.focus();
  }

  function addCol() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    for (let r = 0; r < rows.length; r++) {
      const row = rows[r];
      const isHeader = row.parentElement && row.parentElement.tagName.toLowerCase() === "thead" || (r === 0 && row.querySelector("th"));
      const cell = document.createElement(isHeader ? "th" : "td");
      cell.textContent = isHeader ? `Header ${row.children.length + 1}` : "";
      row.appendChild(cell);
    }
    wireCells();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
  }

  function delRow() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    if (rows.length > 2) {
      rows[rows.length - 1].remove();
      setDocsDirty(true);
      if (_docsSplit) updateDocsPreview();
    }
  }

  function delCol() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    if (rows.length > 0 && rows[0].children.length > 1) {
      for (const row of rows) {
        if (row.lastElementChild) row.lastElementChild.remove();
      }
      setDocsDirty(true);
      if (_docsSplit) updateDocsPreview();
    }
  }

  blockNode.querySelector(".btn-table-add-row")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    addRow();
  });

  blockNode.querySelector(".btn-table-add-col")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    addCol();
  });

  blockNode.querySelector(".btn-table-del-row")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    delRow();
  });

  blockNode.querySelector(".btn-table-del-col")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    delCol();
  });

  blockNode.querySelector(".btn-table-del")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (confirm("Delete this table?")) {
      blockNode.remove();
      setDocsDirty(true);
      if (_docsSplit) updateDocsPreview();
    }
  });

  wireCells();
}

function wireDocTableBlocks(container) {
  if (!container) return;
  const rawTables = container.querySelectorAll("table:not(.doc-table-grid)");
  for (const tbl of rawTables) {
    if (tbl.closest(".doc-table-block")) continue;
    const wrapper = document.createElement("div");
    wrapper.className = "doc-table-block";
    tbl.parentNode.insertBefore(wrapper, tbl);
    buildTableBlockCard(wrapper, tbl.outerHTML);
    tbl.remove();
  }
  const blocks = container.querySelectorAll(".doc-table-block");
  for (const block of blocks) {
    wireSingleTableBlock(block);
  }
}

function wirePlantumlBlocks(container) {
  if (!container) return;
  const blocks = container.querySelectorAll(".plantuml-block");
  for (const block of blocks) {
    let ta = block.querySelector("textarea.plantuml-code-input, textarea");
    const pre = block.querySelector("pre.plantuml, pre.plantuml-code, pre");
    const rawCode = block.getAttribute("data-plantuml") || (ta ? ta.value : (pre ? pre.textContent : ""));
    const trimmedCode = (rawCode || "").trim();

    if (trimmedCode) {
      block.setAttribute("data-plantuml", trimmedCode);
    }

    if (!ta) {
      ta = document.createElement("textarea");
      ta.className = "plantuml-code-input";
      ta.spellcheck = false;
      ta.style.display = "none";
      ta.placeholder = "Type PlantUML syntax here…";
      if (pre) {
        block.replaceChild(ta, pre);
      } else {
        block.appendChild(ta);
      }
    } else if (pre) {
      pre.remove();
    }
    if (trimmedCode) ta.value = trimmedCode;

    // Ensure diagWrap exists
    let diagWrap = block.querySelector(".plantuml-diagram-wrap");
    if (!diagWrap) {
      diagWrap = document.createElement("div");
      diagWrap.className = "plantuml-diagram-wrap";
      diagWrap.setAttribute("contenteditable", "false");
      block.insertBefore(diagWrap, ta);
    }

    // Ensure img exists inside diagWrap
    let img = diagWrap.querySelector("img.plantuml-svg-img, img");
    const expectedUrl = getPlantumlUrl(trimmedCode);
    if (!img) {
      img = document.createElement("img");
      img.className = "plantuml-svg-img";
      img.alt = "PlantUML Diagram";
      img.loading = "lazy";
      if (expectedUrl) img.src = expectedUrl;
      diagWrap.appendChild(img);
    } else if (expectedUrl && img.getAttribute("src") !== expectedUrl) {
      img.src = expectedUrl;
    }

    if (img && !img.dataset.wired) {
      img.dataset.wired = "true";
      img.onload = () => {
        img.style.display = "block";
        diagWrap.querySelector(".plantuml-offline-notice")?.remove();
      };
    }

    // Ensure header exists
    let header = block.querySelector(".plantuml-header");
    if (!header) {
      const origLabel = block.querySelector(".plantuml-label");
      header = document.createElement("div");
      header.className = "plantuml-header";
      header.setAttribute("contenteditable", "false");
      header.innerHTML = `
        <div class="plantuml-title-wrap">
          <span class="plantuml-label">📐 PlantUML Architecture Diagram</span>
          <span class="plantuml-chip">.. uml::</span>
        </div>
        <div class="plantuml-actions">
          <button type="button" class="plantuml-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
          <button type="button" class="plantuml-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
          <button type="button" class="plantuml-btn btn-copy-uml" title="Copy PlantUML Syntax">📋 Copy</button>
          <button type="button" class="plantuml-btn btn-del-uml danger" title="Delete Diagram">🗑</button>
        </div>
      `;
      if (origLabel) {
        block.replaceChild(header, origLabel);
      } else {
        block.insertBefore(header, diagWrap);
      }
    }

    const btnDiag = header.querySelector(".btn-view-diag");
    const btnCode = header.querySelector(".btn-view-code");
    const btnCopy = header.querySelector(".btn-copy-uml");
    const btnDel = header.querySelector(".btn-del-uml");

    if (btnDel && !btnDel.dataset.wired) {
      btnDel.dataset.wired = "true";
      btnDel.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (confirm("Delete this PlantUML diagram?")) {
          block.remove();
          setDocsDirty(true);
          if (_docsSplit) updateDocsPreview();
        }
      });
    }

    if (btnCopy && !btnCopy.dataset.wired) {
      btnCopy.dataset.wired = "true";
      btnCopy.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const codeText = block.getAttribute("data-plantuml") || (ta ? ta.value : "");
        try {
          await navigator.clipboard.writeText(codeText);
          btnCopy.textContent = "✓ Copied!";
          setTimeout(() => { btnCopy.textContent = "📋 Copy"; }, 1500);
        } catch {
          if (typeof toast === "function") toast("Copied to clipboard", codeText, "ok");
        }
      });
    }

    if (btnDiag && btnCode && !header.dataset.wired) {
      header.dataset.wired = "true";

      btnDiag.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnDiag.classList.add("active");
        btnCode.classList.remove("active");
        ta.style.display = "none";
        diagWrap.style.display = "flex";

        const currentCode = (ta ? ta.value.trim() : "") || block.getAttribute("data-plantuml") || "";
        if (currentCode && currentCode !== block.getAttribute("data-plantuml-rendered")) {
          block.setAttribute("data-plantuml", currentCode);
          block.setAttribute("data-plantuml-rendered", currentCode);
          const newUrl = getPlantumlUrl(currentCode);
          if (img) img.src = newUrl;
        }
      });

      btnCode.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnCode.classList.add("active");
        btnDiag.classList.remove("active");
        diagWrap.style.display = "none";
        ta.style.display = "block";
        autoResizeDiagramTextarea(ta);
        ta.focus();
      });
    }

    if (trimmedCode && !block.getAttribute("data-plantuml-rendered")) {
      block.setAttribute("data-plantuml-rendered", trimmedCode);
    }

    if (ta && !ta.dataset.wired) {
      ta.dataset.wired = "true";

      ta.addEventListener("paste", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-plantuml", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });
      ta.addEventListener("copy", (e) => e.stopPropagation());
      ta.addEventListener("cut", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-plantuml", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });
      ta.addEventListener("mousedown", (e) => e.stopPropagation());
      ta.addEventListener("mouseup", (e) => e.stopPropagation());
      ta.addEventListener("click", (e) => e.stopPropagation());
      ta.addEventListener("keyup", (e) => e.stopPropagation());

      ta.addEventListener("input", () => {
        block.setAttribute("data-plantuml", ta.value);
        setDocsDirty(true);
        autoResizeDiagramTextarea(ta);
      });

      ta.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Tab") {
          e.preventDefault();
          const start = ta.selectionStart;
          const end = ta.selectionEnd;
          ta.value = ta.value.substring(0, start) + "    " + ta.value.substring(end);
          ta.selectionStart = ta.selectionEnd = start + 4;
          block.setAttribute("data-plantuml", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          btnDiag?.click();
        }
      });
    }
  }
}

async function renderAllMermaidBlocks(container) {
  if (!window.mermaid || !container) return;
  const blocks = container.querySelectorAll(".mermaid-block");
  if (!blocks || blocks.length === 0) return;

  const isDark = document.documentElement.getAttribute("data-theme") !== "light";
  try {
    mermaid.initialize({
      startOnLoad: false,
      theme: isDark ? "dark" : "default",
      securityLevel: "loose",
    });
  } catch (e) { }

  for (const block of blocks) {
    let ta = block.querySelector("textarea.mermaid-code-input, textarea");
    const pre = block.querySelector("pre.mermaid, pre.mermaid-code, pre");
    const rawCode = block.getAttribute("data-mermaid") || (ta ? ta.value : (pre ? pre.textContent : ""));
    if (!rawCode || !rawCode.trim()) continue;

    const trimmedCode = rawCode.trim();
    block.setAttribute("data-mermaid", trimmedCode);

    // Convert or ensure textarea element exists
    if (!ta) {
      ta = document.createElement("textarea");
      ta.className = "mermaid-code-input";
      ta.spellcheck = false;
      ta.style.display = "none";
      ta.placeholder = "Type Mermaid syntax here…";
      if (pre) {
        block.replaceChild(ta, pre);
      } else {
        block.appendChild(ta);
      }
    } else if (pre) {
      pre.remove();
    }
    ta.value = trimmedCode;

    // Ensure diagWrap exists
    let diagWrap = block.querySelector(".mermaid-diagram-wrap");
    if (!diagWrap) {
      diagWrap = document.createElement("div");
      diagWrap.className = "mermaid-diagram-wrap";
      diagWrap.setAttribute("contenteditable", "false");
      block.insertBefore(diagWrap, ta);
    }

    // Ensure header exists
    let header = block.querySelector(".mermaid-header");
    if (!header) {
      const origLabel = block.querySelector(".mermaid-label");
      header = document.createElement("div");
      header.className = "mermaid-header";
      header.setAttribute("contenteditable", "false");
      header.innerHTML = `
        <div class="mermaid-title-wrap">
          <span class="mermaid-label">📊 Mermaid Architecture Diagram</span>
          <span class="mermaid-chip">.. mermaid::</span>
        </div>
        <div class="mermaid-actions">
          <button type="button" class="mermaid-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
          <button type="button" class="mermaid-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
          <button type="button" class="mermaid-btn btn-copy-code" title="Copy Diagram Syntax">📋 Copy</button>
          <button type="button" class="mermaid-btn btn-del-diag danger" title="Delete Diagram">🗑</button>
        </div>
      `;
      if (origLabel) {
        block.replaceChild(header, origLabel);
      } else {
        block.insertBefore(header, diagWrap);
      }
    }

    const btnDiag = header.querySelector(".btn-view-diag");
    const btnCode = header.querySelector(".btn-view-code");
    const btnCopy = header.querySelector(".btn-copy-code");
    const btnDel = header.querySelector(".btn-del-diag");

    if (btnDel && !btnDel.dataset.wired) {
      btnDel.dataset.wired = "true";
      btnDel.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (confirm("Delete this Mermaid diagram?")) {
          block.remove();
          setDocsDirty(true);
          if (_docsSplit) updateDocsPreview();
        }
      });
    }

    if (btnCopy && !btnCopy.dataset.wired) {
      btnCopy.dataset.wired = "true";
      btnCopy.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const codeText = block.getAttribute("data-mermaid") || ta.value;
        try {
          await navigator.clipboard.writeText(codeText);
          btnCopy.textContent = "✓ Copied!";
          setTimeout(() => { btnCopy.textContent = "📋 Copy"; }, 1500);
        } catch {
          if (typeof toast === "function") toast("Copied to clipboard", codeText, "ok");
        }
      });
    }

    if (btnDiag && btnCode && !header.dataset.wired) {
      header.dataset.wired = "true";

      btnDiag.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnDiag.classList.add("active");
        btnCode.classList.remove("active");
        ta.style.display = "none";
        diagWrap.style.display = "flex";

        // Re-render diagram if code was edited
        const currentCode = ta.value.trim() || block.getAttribute("data-mermaid") || "";
        if (currentCode && currentCode !== block.getAttribute("data-mermaid-rendered")) {
          block.setAttribute("data-mermaid", currentCode);
          try {
            _mermaidCounter++;
            const id = `mermaid_dyn_${Date.now()}_${_mermaidCounter}`;
            const { svg } = await mermaid.render(id, currentCode);
            diagWrap.innerHTML = svg;
            block.setAttribute("data-mermaid-rendered", currentCode);
          } catch (renderErr) {
            console.warn("Mermaid re-render error:", renderErr);
            diagWrap.innerHTML = `<div style="color:var(--danger, #f87171); padding:10px; font-size:12px;">⚠️ Mermaid Render Error: ${renderErr.message || renderErr}</div>`;
          }
        }
      });

      btnCode.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnCode.classList.add("active");
        btnDiag.classList.remove("active");
        diagWrap.style.display = "none";

        ta.value = block.getAttribute("data-mermaid") || trimmedCode;
        ta.style.display = "block";
        autoResizeDiagramTextarea(ta);
        setTimeout(() => {
          try { ta.focus(); } catch (err) { }
        }, 15);
      });
    }

    // Keep textarea synchronized when user types
    if (ta && !ta.dataset.wired) {
      ta.dataset.wired = "true";

      // Stop propagation of clipboard events so Quill doesn't cancel or hijack paste/copy/cut
      ta.addEventListener("paste", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-mermaid", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });
      ta.addEventListener("copy", (e) => e.stopPropagation());
      ta.addEventListener("cut", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-mermaid", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });

      // Stop mouse and keyboard bubbling to Quill
      ta.addEventListener("mousedown", (e) => e.stopPropagation());
      ta.addEventListener("mouseup", (e) => e.stopPropagation());
      ta.addEventListener("click", (e) => e.stopPropagation());
      ta.addEventListener("keyup", (e) => e.stopPropagation());

      ta.addEventListener("input", () => {
        block.setAttribute("data-mermaid", ta.value);
        setDocsDirty(true);
        autoResizeDiagramTextarea(ta);
      });

      ta.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Tab") {
          e.preventDefault();
          const start = ta.selectionStart;
          const end = ta.selectionEnd;
          ta.value = ta.value.substring(0, start) + "    " + ta.value.substring(end);
          ta.selectionStart = ta.selectionEnd = start + 4;
          block.setAttribute("data-mermaid", ta.value);
          setDocsDirty(true);
        }
      });

      ta.addEventListener("blur", async () => {
        const updated = ta.value.trim();
        block.setAttribute("data-mermaid", updated);
        setDocsDirty(true);
        if (updated && updated !== block.getAttribute("data-mermaid-rendered")) {
          try {
            _mermaidCounter++;
            const id = `mermaid_blur_${Date.now()}_${_mermaidCounter}`;
            const { svg } = await mermaid.render(id, updated);
            diagWrap.innerHTML = svg;
            block.setAttribute("data-mermaid-rendered", updated);
          } catch (e) {
            console.warn("Re-render failed:", e);
          }
        }
      });
    }

    // Initial render of SVG diagram
    try {
      _mermaidCounter++;
      const id = `mermaid_diag_${Date.now()}_${_mermaidCounter}`;
      const { svg } = await mermaid.render(id, trimmedCode);
      diagWrap.innerHTML = svg;
      block.setAttribute("data-mermaid-rendered", trimmedCode);
      ta.style.display = "none";
      diagWrap.style.display = "flex";
    } catch (renderErr) {
      console.warn("Mermaid render error:", renderErr);
      diagWrap.innerHTML = `<div style="color:var(--danger, #f87171); padding:8px; font-size:12px;">⚠️ Mermaid Render Error: ${renderErr.message || renderErr}</div>`;
      ta.style.display = "block";
      autoResizeTextarea(ta);
      btnCode?.classList.add("active");
      btnDiag?.classList.remove("active");
    }
  }
}

function initQuill() {
  if (_quill || !window.Quill || !$("#quill-editor")) return;
  registerQuillDiagramBlots();
  _quill = new Quill("#quill-editor", {
    theme: "snow",
    placeholder: "Write Sphinx documentation here… Format headings, bold, italic, code blocks visually.",
    modules: {
      toolbar: [
        [{ header: [1, 2, 3, 4, false] }],
        ["bold", "italic", "underline", "strike"],
        ["blockquote", "code-block"],
        [{ list: "ordered" }, { list: "bullet" }],
        ["link", "clean"],
      ],
    },
  });

  const Delta = Quill.import("delta");
  if (Delta && _quill.clipboard) {
    _quill.clipboard.addMatcher(".mermaid-block", function (node, delta) {
      const code = node.getAttribute("data-mermaid") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      return new Delta().insert({ mermaidBlock: code });
    });
    _quill.clipboard.addMatcher(".plantuml-block", function (node, delta) {
      const code = node.getAttribute("data-plantuml") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      return new Delta().insert({ plantumlBlock: code });
    });
    _quill.clipboard.addMatcher(".doc-table-block", function (node, delta) {
      const tbl = node.querySelector("table");
      return new Delta().insert({ tableBlock: tbl ? tbl.outerHTML : node.innerHTML });
    });
    _quill.clipboard.addMatcher("table", function (node, delta) {
      if (node.closest(".doc-table-block")) return delta;
      return new Delta().insert({ tableBlock: node.outerHTML });
    });
  }

  _quill.on("text-change", (delta, oldDelta, source) => {
    if (source === "user") {
      setDocsDirty(true);
      if (_docsSplit && _docsEditorType === "wysiwyg") {
        updateDocsPreview();
      }
    }
  });

  initSyncScroll();
}

const MERMAID_TEMPLATES = {
  flowchart: {
    title: "Flowchart / Block Diagram",
    code: `graph TD\n    Client["Client / User"] --> Gateway["API Gateway"]\n    Gateway --> Service["Core Service"]\n    Service --> Database[("Database Storage")]`
  },
  sequence: {
    title: "Sequence Diagram",
    code: `sequenceDiagram\n    autonumber\n    actor User\n    participant UI as Frontend App\n    participant API as Backend Service\n    participant DB as Database\n\n    User->>UI: Submit Request\n    UI->>API: POST /api/v1/action\n    API->>DB: Query / Update Records\n    DB-->>API: Return Result Set\n    API-->>UI: 200 OK (JSON Data)\n    UI-->>User: Render Success View`
  },
  class: {
    title: "Class Diagram",
    code: `classDiagram\n    class CarAudioManager {\n        +int volume\n        +requestAudioFocus()\n    }\n    class CarAudioService {\n        -List zones\n        +handleVolumeChange()\n    }\n    class IAudioControlHAL {\n        <<interface>>\n        +setAudioPortConfig()\n    }\n    CarAudioManager --> CarAudioService : AIDL IPC\n    CarAudioService ..|> IAudioControlHAL : Controls Hardware`
  },
  usecase: {
    title: "Use Case Diagram",
    code: `flowchart LR\n    User["👤 Driver / Passenger"]\n    ADAS["🚨 ADAS Safety System"]\n\n    subgraph System ["Car Audio Management"]\n        UC1(["Media & Radio Playback"])\n        UC2(["Arbitrate Audio Focus"])\n        UC3(["Adjust Volume Groups"])\n        UC4(["Emergency Chime Playback"])\n    end\n\n    User --> UC1\n    User --> UC3\n    ADAS --> UC4\n    UC4 -.->|include| UC2\n    UC1 -.->|include| UC2`
  },
  activity: {
    title: "Activity / Workflow Diagram",
    code: `flowchart TD\n    Start([● Start]) --> Req["Receive Audio Focus Request"]\n    Req --> Check{"Is Emergency / ADAS?"}\n\n    Check -->|Yes| Preempt["Preempt Current Focus"]\n    Preempt --> Duck["Apply Dynamic Ducking (-20dB)"]\n    Duck --> Route["Route Audio to Driver Speakers"]\n\n    Check -->|No| CheckZone{"Target Zone Available?"}\n    CheckZone -->|Yes| Grant["Grant Audio Focus"]\n    Grant --> Route\n    CheckZone -->|No| Reject["Reject Focus Request"]\n\n    Route --> Finish([◉ Finish])\n    Reject --> Finish`
  },
  state: {
    title: "State Machine Diagram",
    code: `stateDiagram-v2\n    [*] --> Idle\n    Idle --> Active : Start Event\n    state Active {\n        [*] --> Initializing\n        Initializing --> Running : Ready\n        Running --> Paused : Interrupt\n        Paused --> Running : Resume\n    }\n    Active --> Terminated : Shutdown\n    Terminated --> [*]`
  }
};

const PLANTUML_TEMPLATES = {
  sequence: {
    title: "Sequence Diagram",
    code: `@startuml\nautonumber\nactor User\nparticipant "Frontend" as UI\nparticipant "Backend" as API\ndatabase "Database" as DB\n\nUser -> UI : Submit Action / Request\nactivate UI\nUI -> API : REST / GraphQL API Call\nactivate API\nAPI -> DB : SQL Query / Transaction\nactivate DB\nDB --> API : Result Set\ndeactivate DB\nAPI --> UI : JSON Response (HTTP 200)\ndeactivate API\nUI --> User : Render Success View\ndeactivate UI\n@enduml`
  },
  class: {
    title: "Class Diagram",
    code: `@startuml\nclass CarAudioManager {\n    -int mVolume\n    +requestAudioFocus()\n    +setGroupVolume(int groupId, int volume)\n}\n\nclass CarAudioService {\n    -List<CarAudioZone> mZones\n    +initialize()\n    +handleVolumeChange()\n}\n\ninterface IAudioControlHAL {\n    +setAudioPortConfig()\n    +onVolumeChange(int bus, float gain)\n}\n\nCarAudioManager --> CarAudioService : Binds via AIDL\nCarAudioService ..|> IAudioControlHAL : Controls Hardware\n@enduml`
  },
  usecase: {
    title: "Use Case Diagram",
    code: `@startuml\nleft to right direction\nactor "Driver / User" as Driver\nactor "ADAS System" as ADAS\n\nrectangle "Audio Management Subsystem" {\n    usecase "Stream Media Playback" as UC1\n    usecase "Arbitrate Audio Focus" as UC2\n    usecase "Adjust Volume Group" as UC3\n    usecase "Broadcast ADAS Warning" as UC4\n}\n\nDriver --> UC1\nDriver --> UC3\nADAS --> UC4\nUC4 ..> UC2 : <<include>>\nUC1 ..> UC2 : <<include>>\n@enduml`
  },
  activity: {
    title: "Activity / Workflow Diagram",
    code: `@startuml\nstart\n:Receive Audio Focus Request;\n\nif (Is Emergency / ADAS Stream?) then (yes)\n    :Preempt Current Focus;\n    :Apply Dynamic Ducking (-20dB);\n    :Route Audio to Driver Speakers;\nelse (no)\n    if (Target Audio Zone Available?) then (yes)\n        :Grant AUDIOFOCUS_REQUEST_GRANTED;\n        :Activate Media Audio Bus;\n    else (no)\n        :Reject AUDIOFOCUS_REQUEST_FAILED;\n        stop\n    endif\nendif\n\n:Notify AudioFocusChange Callback;\nstop\n@enduml`
  },
  component: {
    title: "Component / Block Diagram",
    code: `@startuml\npackage "Application Layer" {\n    [Media Player App] as Media\n    [Navigation System] as Nav\n}\n\npackage "Car Framework Services" {\n    [CarAudioService] as AudioSvc\n    [CarPowerManagement] as PowerSvc\n}\n\nnode "Hardware Abstraction (HAL)" {\n    [AudioControl HAL] as AudioHAL\n    [Vehicle HAL] as VHAL\n}\n\nMedia --> AudioSvc : AIDL IPC\nNav --> AudioSvc : AIDL IPC\nAudioSvc --> AudioHAL : Audio Routing\nPowerSvc --> VHAL : Power State\n@enduml`
  },
  state: {
    title: "State Machine Diagram",
    code: `@startuml\n[*] --> Idle\n\nIdle --> Active : Start Request\nstate Active {\n    [*] --> Initializing\n    Initializing --> Running : Ready\n    Running --> Paused : Interrupt\n    Paused --> Running : Resume\n}\n\nActive --> Stopped : Complete / Abort\nStopped --> [*]\n@enduml`
  }
};

function insertMermaidDiagram(diagramType = "flowchart") {
  // JSON → Chart: open the import modal instead of inserting a template
  if (diagramType === "json-chart") {
    openJsonChartModal();
    return;
  }
  const tmpl = MERMAID_TEMPLATES[diagramType] || MERMAID_TEMPLATES.flowchart;
  const defaultCode = tmpl.code;

  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const insertText = `\n.. mermaid::\n\n    ${defaultCode.replace(/\n/g, "\n    ")}\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + insertText + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + insertText.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${tmpl.title} into RST source.`, "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "mermaidBlock", defaultCode, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    renderAllMermaidBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${tmpl.title} into Visual editor.`, "ok");
  }
}

// ===== JSON → Mermaid Chart converter (mirrors sphinx/scripts/json_to_chart.py) =====
const JSON_CHART_SAMPLES = {
  combo: {
    title: "Audio Latency (Bar) vs Drops (Line)",
    type: "combo",
    json: {
      x: ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"],
      bar: [45, 60, 95, 110, 80, 50],
      line: [40, 55, 85, 105, 75, 45],
      y_label: "Latency (ms) / Drops"
    }
  },
  bar: {
    title: "AOSP Module Build Duration (Seconds)",
    type: "bar",
    json: {
      x: ["OemService", "CarAudio", "VehicleSvc", "dlt-daemon", "Settings"],
      y: [35, 75, 48, 22, 60]
    }
  },
  line: {
    title: "CarAudioService RAM Trend (MB)",
    type: "line",
    json: {
      x: ["10m", "20m", "30m", "40m", "50m", "60m"],
      y: [120, 145, 190, 185, 210, 215]
    }
  },
  pie: {
    title: "Audio Routing Context Distribution",
    type: "pie",
    json: {
      media: 45, navigation: 25, phone_call: 15, assistant: 10, chime: 5
    }
  },
  timeline: {
    title: "Automotive Platform Milestones",
    type: "timeline",
    json: {
      "2024 Q3": ["AOSP 13 Baseline", "CarAudio Initial Bringup"],
      "2024 Q4": ["Qualcomm SA8155 BSP", "Vehicle HAL v2.0"],
      "2025 Q1": ["COVESA DLT Logging", "Audio Zone Routing"],
      "2025 Q2": ["Production Release", "OTA Firmware Update"]
    }
  },
  flow: {
    title: "AOSP Audio HAL & CarService Flow",
    type: "flow",
    json: {
      nodes: [
        "CarAudioService", "OemCarService", "AudioControl HAL", "Audio HW HAL", "DSP Driver"
      ],
      edges: [
        ["CarAudioService", "OemCarService", "AIDL evaluate"],
        ["CarAudioService", "AudioControl HAL", "IAudioControl/default"],
        ["AudioControl HAL", "Audio HW HAL", "setParameters()"],
        ["Audio HW HAL", "DSP Driver", "ALSA / TinyALSA"]
      ]
    }
  }
};

function _jsonChartSanitize(text, fallback = "item") {
  if (text === null || text === undefined) text = fallback;
  return String(text).replace(/"/g, "'").replace(/\n/g, " ").trim() || fallback;
}

function _jsonChartPairs(data) {
  if (Array.isArray(data)) {
    return data.map(item => {
      if (!Array.isArray(item) || item.length !== 2) {
        throw new Error("Array form must be [[label, value], ...] pairs");
      }
      return item;
    });
  }
  if (data && typeof data === "object") {
    if (Array.isArray(data.x) && Array.isArray(data.y)) {
      if (data.x.length !== data.y.length) {
        throw new Error("'x' and 'y' arrays must have the same length");
      }
      return data.x.map((x, i) => [x, data.y[i]]);
    }
    return Object.entries(data);
  }
  throw new Error("Unsupported JSON shape for pie/bar/line charts");
}

function jsonToMermaid(data, type, title) {
  const t = type || _jsonChartDetectType(data);

  // 1. Combo chart (Bar + Line together in xychart-beta)
  if (t === "combo") {
    if (!data || typeof data !== "object") {
      throw new Error("Combo chart JSON must be {\"x\": [...], \"bar\": [...], \"line\": [...]}");
    }
    const xLabels = (data.x || []).map(x => `"${_jsonChartSanitize(x)}"`).join(", ");
    const barVals = (data.bar || []).map(v => Number(v) || 0);
    const lineVals = (data.line || []).map(v => Number(v) || 0);
    if (!barVals.length && !lineVals.length) {
      throw new Error("Combo chart must provide 'bar' and/or 'line' numeric arrays");
    }
    const allVals = [...barVals, ...lineVals];
    const yMax = Math.max(...allVals, 1);
    const yMin = Math.min(0, ...allVals);
    const lines = ["xychart-beta"];
    if (title) lines.push(`    title "${_jsonChartSanitize(title)}"`);
    lines.push(`    x-axis [${xLabels}]`);
    lines.push(`    y-axis "${_jsonChartSanitize(data.y_label || 'Value')}" ${yMin} --> ${yMax}`);
    if (barVals.length) lines.push(`    bar [${barVals.join(", ")}]`);
    if (lineVals.length) lines.push(`    line [${lineVals.join(", ")}]`);
    return lines;
  }

  // 2. Timeline Roadmap
  if (t === "timeline") {
    const lines = ["timeline"];
    if (title) lines.push(`    title ${_jsonChartSanitize(title)}`);
    if (Array.isArray(data)) {
      data.forEach(item => {
        if (typeof item === "object") {
          Object.entries(item).forEach(([period, events]) => {
            lines.push(`    section ${_jsonChartSanitize(period)}`);
            const evs = Array.isArray(events) ? events : [events];
            evs.forEach(ev => lines.push(`        ${_jsonChartSanitize(ev)}`));
          });
        }
      });
    } else if (data && typeof data === "object") {
      Object.entries(data).forEach(([period, events]) => {
        lines.push(`    section ${_jsonChartSanitize(period)}`);
        const evs = Array.isArray(events) ? events : [events];
        evs.forEach(ev => lines.push(`        ${_jsonChartSanitize(ev)}`));
      });
    }
    return lines;
  }

  // 3. Flowchart
  if (t === "flow") {
    if (!data || typeof data !== "object" || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) {
      throw new Error("Flow chart JSON must be {\"nodes\": [...], \"edges\": [[src, dst, label?], ...]}");
    }
    const lines = ["flowchart LR"];
    if (title) lines.push(`    %% ${_jsonChartSanitize(title)}`);
    const idByLabel = {};
    data.nodes.forEach((node, idx) => {
      const id = `N${idx}`;
      idByLabel[String(node)] = id;
      lines.push(`    ${id}["${_jsonChartSanitize(node)}"]`);
    });
    data.edges.forEach(edge => {
      if (!Array.isArray(edge) || edge.length < 2) {
        throw new Error(`Edge must be [src, dst] or [src, dst, label]: ${JSON.stringify(edge)}`);
      }
      const srcId = idByLabel[String(edge[0])];
      const dstId = idByLabel[String(edge[1])];
      if (srcId === undefined || dstId === undefined) {
        throw new Error(`Edge references unknown node: ${JSON.stringify(edge)}. All endpoints must be listed in 'nodes'.`);
      }
      if (edge.length >= 3 && edge[2]) {
        lines.push(`    ${srcId} -->|"${_jsonChartSanitize(edge[2])}"| ${dstId}`);
      } else {
        lines.push(`    ${srcId} --> ${dstId}`);
      }
    });
    return lines;
  }

  // 4. Pie chart
  const pairs = _jsonChartPairs(data).map(([label, value]) => {
    const num = Number(value);
    if (value === null || value === "" || Number.isNaN(num)) {
      throw new Error(`Expected numeric value for key '${label}', got: ${JSON.stringify(value)}`);
    }
    return [_jsonChartSanitize(label), num];
  });
  if (t === "pie") {
    const lines = ["pie showData"];
    if (title) lines.push(`    title ${_jsonChartSanitize(title)}`);
    pairs.forEach(([label, value]) => lines.push(`    "${label}" : ${value}`));
    return lines;
  }

  // 5. xychart-beta (single bar or single line)
  const labels = pairs.map(p => `"${p[0]}"`).join(", ");
  const values = pairs.map(p => p[1]);
  const yMax = Math.max(...values, 1);
  const yMin = Math.min(0, ...values);
  const lines = ["xychart-beta"];
  if (title) lines.push(`    title "${_jsonChartSanitize(title)}"`);
  lines.push(`    x-axis [${labels}]`);
  lines.push(`    y-axis "Value" ${yMin} --> ${yMax}`);
  lines.push(`    ${t} [${values.join(", ")}]`);
  return lines;
}

function _jsonChartDetectType(data) {
  if (data && typeof data === "object" && !Array.isArray(data)) {
    if (Array.isArray(data.nodes) && Array.isArray(data.edges)) return "flow";
    if (Array.isArray(data.x) && (Array.isArray(data.bar) || Array.isArray(data.line))) {
      if (Array.isArray(data.bar) && Array.isArray(data.line)) return "combo";
      if (Array.isArray(data.bar)) return "bar";
      if (Array.isArray(data.line)) return "line";
    }
    if (Array.isArray(data.x) && Array.isArray(data.y)) return "bar";
    const values = Object.values(data);
    if (values.length && values.every(v => Array.isArray(v) && v.every(item => typeof item === "string"))) {
      return "timeline";
    }
  }
  return "pie";
}

function openJsonChartModal() {
  const modal = $("#modal-json-chart");
  if (!modal) return;
  const input = $("#json-chart-input");
  const typeSel = $("#json-chart-type");
  const titleIn = $("#json-chart-title");
  const previewWrap = $("#json-chart-preview-wrap");
  if (input) input.value = "";
  if (typeSel) typeSel.value = "auto";
  if (titleIn) titleIn.value = "";
  if (previewWrap) previewWrap.style.display = "none";
  modal.classList.remove("hidden");
  setTimeout(() => input?.focus(), 40);
}

function wireJsonChartModal() {
  const modal = $("#modal-json-chart");
  if (!modal || modal.dataset.wired === "1") return;
  modal.dataset.wired = "1";

  const input = $("#json-chart-input");
  const typeSel = $("#json-chart-type");
  const titleIn = $("#json-chart-title");
  const previewWrap = $("#json-chart-preview-wrap");
  const previewPre = $("#json-chart-preview");

  function buildLines() {
    const raw = input?.value.trim() || "";
    if (!raw) throw new Error("JSON input is empty");
    let data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      throw new Error("Invalid JSON: " + e.message);
    }
    const type = typeSel?.value === "auto" ? null : typeSel?.value;
    return jsonToMermaid(data, type, titleIn?.value.trim() || null);
  }

  $("#btn-json-chart-cancel")?.addEventListener("click", () => modal.classList.add("hidden"));
  $("#btn-json-chart-preview")?.addEventListener("click", () => {
    try {
      const lines = buildLines();
      if (previewPre) previewPre.textContent = lines.join("\n");
      if (previewWrap) previewWrap.style.display = "block";
    } catch (e) {
      toast("JSON Chart Error ⚠️", e.message, "err");
    }
  });
  $("#btn-json-chart-insert")?.addEventListener("click", () => {
    let lines;
    try {
      lines = buildLines();
    } catch (e) {
      toast("JSON Chart Error ⚠️", e.message, "err");
      return;
    }
    modal.classList.add("hidden");
    insertMermaidCode(lines.join("\n"), "JSON Chart");
  });

  // Ctrl+Enter in textarea inserts directly
  input?.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      $("#btn-json-chart-insert")?.click();
    }
  });

  // Sample chips: load predefined JSON into the textarea
  modal.querySelectorAll(".btn-json-sample").forEach(chip => {
    chip.addEventListener("click", (e) => {
      e.stopPropagation();
      const key = chip.dataset.sample;
      const sample = JSON_CHART_SAMPLES[key];
      if (!sample || !input) return;
      input.value = JSON.stringify(sample.json, null, 2);
      if (typeSel) typeSel.value = sample.type;
      if (titleIn) titleIn.value = sample.title;
      // Auto-preview so the user immediately sees the mermaid output
      try {
        const lines = jsonToMermaid(sample.json, sample.type, sample.title);
        if (previewPre) previewPre.textContent = lines.join("\n");
        if (previewWrap) previewWrap.style.display = "block";
      } catch { /* ignore preview errors */ }
    });
  });
}

function insertMermaidCode(code, label = "Mermaid Diagram") {
  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const insertText = `\n.. mermaid::\n\n    ${code.replace(/\n/g, "\n    ")}\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + insertText + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + insertText.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${label} into RST source.`, "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "mermaidBlock", code, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    renderAllMermaidBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${label} into Visual editor.`, "ok");
  }
}

function insertPlantumlDiagram(diagramType = "sequence") {
  const tmpl = PLANTUML_TEMPLATES[diagramType] || PLANTUML_TEMPLATES.sequence;
  const defaultCode = tmpl.code;

  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const insertText = `\n.. uml::\n\n    ${defaultCode.replace(/\n/g, "\n    ")}\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + insertText + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + insertText.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("PlantUML Diagram Added 📐", `Inserted ${tmpl.title} into RST source.`, "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "plantumlBlock", defaultCode, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    wirePlantumlBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("PlantUML Diagram Added 📐", `Inserted ${tmpl.title} into Visual editor.`, "ok");
  }
}

function insertTableBlock() {
  const defaultTableHtml = `
    <table class="doc-table-grid">
      <caption>Table Title</caption>
      <thead>
        <tr><th>Header 1</th><th>Header 2</th><th>Header 3</th></tr>
      </thead>
      <tbody>
        <tr><td>Data 1</td><td>Data 2</td><td>Data 3</td></tr>
        <tr><td>Data 4</td><td>Data 5</td><td>Data 6</td></tr>
      </tbody>
    </table>
  `;

  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const rstTable = `\n.. list-table:: Table Title\n   :widths: 30 35 35\n   :header-rows: 1\n\n   * - Header 1\n     - Header 2\n     - Header 3\n   * - Data 1\n     - Data 2\n     - Data 3\n   * - Data 4\n     - Data 5\n     - Data 6\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + rstTable + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + rstTable.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Table Added ▦", "Inserted .. list-table:: template into RST source.", "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "tableBlock", defaultTableHtml, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    wireDocTableBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Table Added ▦", "Inserted interactive Table into Visual editor.", "ok");
  }
}

function setDocsDirty(val) {
  _docsDirty = Boolean(val);
  const badge = $("#docs-dirty-badge");
  if (badge) badge.style.display = _docsDirty ? "inline" : "none";
}

async function loadDocsFiles(customDir = _docsCustomDir) {
  const sel = $("#docs-file-select");
  if (sel) sel.innerHTML = '<option value="">Loading .rst files…</option>';
  try {
    const url = `/api/docs/files?dir=${encodeURIComponent(customDir || "")}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Failed to scan docs files");
    _docsFiles = data.files || [];
    const activeDir = data.dir || _docsCustomDir || "";
    _docsActiveDir = data.dir || _docsCustomDir || "";
    const dirLabel = $("#docs-dir-label");
    if (dirLabel) {
      if (data.dir) {
        const parts = data.dir.replace(/\\/g, "/").split("/").filter(Boolean);
        dirLabel.textContent = parts.length > 1 ? parts.slice(-2).join("/") : (parts[0] || "docs");
        dirLabel.parentElement.title = `Docs Root: ${data.dir} (Click to change)`;
      } else {
        dirLabel.textContent = "docs";
        dirLabel.parentElement.title = "Default docs root (Click to change)";
      }
      dirLabel.textContent = "docs";
      dirLabel.parentElement.title = data.dir ? `Docs Root: ${data.dir} (Click to change)` : "Default docs root (Click to change)";
    }
    const dirBadge = $("#docs-active-dir-badge");
    if (dirBadge) {
      if (activeDir) {
        dirBadge.style.display = "inline-flex";
        dirBadge.textContent = activeDir;
        dirBadge.title = `Active Docs Root: ${activeDir} (Click to change)`;
      } else {
        dirBadge.style.display = "none";
      }
    }
    renderDocsFileSelect();
    if (_docsFiles.length > 0 && (!_currentDoc || !_docsFiles.some(f => f.name === _currentDoc.name))) {
      const savedDoc = localStorage.getItem("telua_web_docs_last_file");
      const matched = savedDoc ? _docsFiles.find(f => f.name === savedDoc) : null;
      const arch = matched || _docsFiles.find(f => f.name.includes("chapter3_section1") || f.name.includes("chapter1_section1") || f.name.includes("index.rst")) || _docsFiles[0];
      loadDocFile(arch.name);
    }
  } catch (err) {
    if (sel) sel.innerHTML = `<option value="">Error loading docs (${err.message})</option>`;
    toast("Docs Scan Failed", String(err.message || err), "danger");
  }
}

function renderDocsFileSelect() {
  const sel = $("#docs-file-select");
  if (!sel) return;
  if (_docsFiles.length === 0) {
    sel.innerHTML = '<option value="">No .rst files found</option>';
    return;
  }
  const groups = {};
  for (const f of _docsFiles) {
    const cat = f.category || "other";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(f);
  }
  let html = '<option value="">— Select an .rst file to edit —</option>';
  for (const [cat, files] of Object.entries(groups)) {
    const label = cat.charAt(0).toUpperCase() + cat.slice(1);
    html += `<optgroup label="Template: ${label}">`;
    for (const f of files) {
      const selected = _currentDoc && _currentDoc.name === f.name ? "selected" : "";
      html += `<option value="${f.name}" ${selected}>${f.title || f.name} (${f.name})</option>`;
    }
    html += `</optgroup>`;
  }
  sel.innerHTML = html;
}

async function loadDocFile(name) {
  if (!name) return;
  if (_docsDirty && !confirm("You have unsaved changes in the current document. Discard and switch file?")) {
    renderDocsFileSelect();
    return;
  }
  initQuill();
  const badge = $("#docs-status-badge");
  if (badge) badge.textContent = "Loading…";
  try {
    const url = `/api/docs/file?name=${encodeURIComponent(name)}&dir=${encodeURIComponent(_docsCustomDir || _docsActiveDir || "")}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Failed to read file");
    _currentDoc = data;
    setDocsDirty(false);

    if (_quill) {
      _quill.setText("");
      if (data.html) {
        _quill.clipboard.dangerouslyPasteHTML(0, data.html);
      }
      renderAllMermaidBlocks(_quill.root);
      wirePlantumlBlocks(_quill.root);
      wireDocTableBlocks(_quill.root);
    }
    const rawTa = $("#docs-raw-rst");
    if (rawTa) rawTa.value = data.rst || "";

    const meta = $("#docs-file-meta");
    if (meta) {
      const fullPath = data.full_path || data.name;
      meta.textContent = `📄 ${fullPath} · ${data.rst.length} chars · format: RST`;
      meta.title = `Full path: ${fullPath}`;
    }
    if (badge) badge.textContent = data.readonly ? "Read-only" : "Ready";
    renderDocsFileSelect();
    try {
      localStorage.setItem("telua_web_docs_last_file", name);
    } catch (e) { }
    applyDocsModeUI();
    if (_docsSplit) updateDocsPreview();
  } catch (err) {
    toast("Failed to open doc", String(err.message || err), "danger");
    if (badge) badge.textContent = "Error";
  }
}

function applyDocsModeUI() {
  const wysiwygPane = $("#docs-pane-wysiwyg");
  const rawPane = $("#docs-pane-raw");
  const previewPane = $("#docs-pane-preview");

  $("#btn-docs-mode-wysiwyg")?.classList.toggle("active", _docsEditorType === "wysiwyg");
  $("#btn-docs-mode-raw")?.classList.toggle("active", _docsEditorType === "raw");
  $("#btn-docs-mode-split")?.classList.toggle("active", _docsSplit);

  if (_docsSplit) {
    previewPane?.classList.remove("hidden");
    if (_docsEditorType === "raw") {
      wysiwygPane?.classList.add("hidden");
      wysiwygPane?.classList.remove("split-left");
      rawPane?.classList.remove("hidden");
      rawPane?.classList.add("split-left");
    } else {
      rawPane?.classList.add("hidden");
      rawPane?.classList.remove("split-left");
      wysiwygPane?.classList.remove("hidden");
      wysiwygPane?.classList.add("split-left");
    }
    updateDocsPreview();
  } else {
    previewPane?.classList.add("hidden");
    if (_docsEditorType === "raw") {
      wysiwygPane?.classList.add("hidden");
      wysiwygPane?.classList.remove("split-left");
      rawPane?.classList.remove("hidden");
      rawPane?.classList.remove("split-left");
    } else {
      rawPane?.classList.add("hidden");
      rawPane?.classList.remove("split-left");
      wysiwygPane?.classList.remove("hidden");
      wysiwygPane?.classList.remove("split-left");
    }
  }

  try {
    localStorage.setItem("telua_web_docs_editor", _docsEditorType);
    localStorage.setItem("telua_web_docs_split", String(_docsSplit));
    localStorage.setItem("telua_web_docs_mode", _docsSplit ? "split" : _docsEditorType);
  } catch (e) { }

  initSyncScroll();
}

function getActiveDocsEditorElement() {
  if (_docsEditorType === "raw") {
    return $("#docs-raw-rst");
  }
  const root = _quill ? _quill.root : $("#quill-editor .ql-editor");
  if (root) return root;
  return $("#quill-editor");
}

function syncScroll(sourceElem, targetElem) {
  if (!_docsSplit || !_docsSyncScroll || !sourceElem || !targetElem) return;
  if (_syncScrollSource && _syncScrollSource !== sourceElem) return;

  _syncScrollSource = sourceElem;
  clearTimeout(_syncScrollTimer);

  const maxSource = sourceElem.scrollHeight - sourceElem.clientHeight;
  const maxTarget = targetElem.scrollHeight - targetElem.clientHeight;

  if (maxSource <= 0 || maxTarget <= 0) {
    if (maxTarget <= 0) targetElem.scrollTop = 0;
  } else {
    if (sourceElem.scrollTop <= 4) {
      targetElem.scrollTop = 0;
    } else if (sourceElem.scrollTop >= maxSource - 4) {
      targetElem.scrollTop = maxTarget;
    } else {
      const ratio = sourceElem.scrollTop / maxSource;
      targetElem.scrollTop = Math.round(ratio * maxTarget);
    }
  }

  _syncScrollTimer = setTimeout(() => {
    _syncScrollSource = null;
  }, 60);
}

function updateSyncScrollButtonUI() {
  const btn = $("#btn-docs-sync-scroll");
  if (!btn) return;
  btn.classList.toggle("active", Boolean(_docsSyncScroll));
  btn.textContent = _docsSyncScroll ? "🔗 Sync On" : "🔓 Sync Off";
  btn.title = _docsSyncScroll
    ? "Synchronized scrolling is ON (Editor & Preview scroll together). Click to toggle."
    : "Synchronized scrolling is OFF. Click to toggle.";
}

function initSyncScroll() {
  updateSyncScrollButtonUI();

  const preview = $("#docs-preview-content");
  if (preview && !preview.dataset.syncBound) {
    preview.dataset.syncBound = "1";
    preview.addEventListener("scroll", () => {
      const target = getActiveDocsEditorElement();
      if (target) syncScroll(preview, target);
    }, { passive: true });
  }

  const rawTa = $("#docs-raw-rst");
  if (rawTa && !rawTa.dataset.syncBound) {
    rawTa.dataset.syncBound = "1";
    rawTa.addEventListener("scroll", () => {
      if (_docsEditorType === "raw" && preview) {
        syncScroll(rawTa, preview);
      }
    }, { passive: true });
  }

  const qlEditor = (_quill && _quill.root) || $("#quill-editor .ql-editor");
  if (qlEditor && !qlEditor.dataset.syncBound) {
    qlEditor.dataset.syncBound = "1";
    qlEditor.addEventListener("scroll", () => {
      if (_docsEditorType === "wysiwyg" && preview) {
        syncScroll(qlEditor, preview);
      }
    }, { passive: true });
  }

  const qlContainer = $("#quill-editor");
  if (qlContainer && !qlContainer.dataset.syncBound) {
    qlContainer.dataset.syncBound = "1";
    qlContainer.addEventListener("scroll", () => {
      if (_docsEditorType === "wysiwyg" && preview) {
        syncScroll(qlContainer, preview);
      }
    }, { passive: true });
  }
}

async function switchToEditorType(type) {
  if (type === _docsEditorType) return;
  initQuill();
  const badge = $("#docs-status-badge");

  if (_docsEditorType === "wysiwyg" && type === "raw") {
    // Convert current Quill HTML to RST
    if (_quill && _docsDirty) {
      if (badge) badge.textContent = "Converting HTML → RST…";
      try {
        const res = await fetch("/api/docs/convert", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: _quill.root.innerHTML, direction: "html2rst" }),
        });
        const data = await res.json();
        if (data.ok && $("#docs-raw-rst")) {
          $("#docs-raw-rst").value = data.rst;
        }
      } catch (err) {
        console.error("HTML2RST conversion failed:", err);
      }
      if (badge) badge.textContent = "Ready";
    }
  } else if (_docsEditorType === "raw" && type === "wysiwyg") {
    // Convert current raw RST to HTML for Quill
    const rst = $("#docs-raw-rst")?.value || "";
    if (badge) badge.textContent = "Converting RST → HTML…";
    try {
      const res = await fetch("/api/docs/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: rst, direction: "rst2html" }),
      });
      const data = await res.json();
      if (data.ok && _quill) {
        _quill.setText("");
        _quill.clipboard.dangerouslyPasteHTML(0, data.html || "<p></p>");
        renderAllMermaidBlocks(_quill.root);
        wirePlantumlBlocks(_quill.root);
        wireDocTableBlocks(_quill.root);
      }
    } catch (err) {
      console.error("RST2HTML conversion failed:", err);
    }
    if (badge) badge.textContent = "Ready";
  }

  _docsEditorType = type;
  _docsMode = _docsSplit ? "split" : _docsEditorType;
  applyDocsModeUI();
}

function toggleDocsSplit() {
  _docsSplit = !_docsSplit;
  _docsMode = _docsSplit ? "split" : _docsEditorType;
  applyDocsModeUI();
}

async function setDocsMode(mode) {
  if (mode === "wysiwyg") {
    await switchToEditorType("wysiwyg");
  } else if (mode === "raw") {
    await switchToEditorType("raw");
  } else if (mode === "split") {
    toggleDocsSplit();
  }
}

let _previewDebounceTimer = null;
async function updateDocsPreview() {
  const preview = $("#docs-preview-content");
  if (!preview) return;

  const editorElem = getActiveDocsEditorElement();
  let prevRatio = 0;
  if (editorElem) {
    const maxSource = editorElem.scrollHeight - editorElem.clientHeight;
    if (maxSource > 0) {
      prevRatio = editorElem.scrollTop / maxSource;
    }
  }

  if (_docsEditorType === "raw") {
    const rawTa = $("#docs-raw-rst");
    if (!rawTa) return;
    clearTimeout(_previewDebounceTimer);
    _previewDebounceTimer = setTimeout(async () => {
      try {
        const res = await fetch("/api/docs/convert", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: rawTa.value, direction: "rst2html" }),
        });
        const data = await res.json();
        if (data.ok && data.html) {
          preview.innerHTML = data.html;
          await renderAllMermaidBlocks(preview);
          wirePlantumlBlocks(preview);
          wireDocTableBlocks(preview);
          if (_docsSyncScroll) {
            const maxTarget = preview.scrollHeight - preview.clientHeight;
            if (maxTarget > 0 && prevRatio > 0) {
              preview.scrollTop = Math.round(prevRatio * maxTarget);
            }
          }
        }
      } catch (err) {
        console.warn("Live preview convert error:", err);
      }
    }, 200);
    return;
  }

  if (_quill) {
    preview.innerHTML = _quill.root.innerHTML;
    await renderAllMermaidBlocks(preview);
    wirePlantumlBlocks(preview);
    wireDocTableBlocks(preview);
    if (_docsSyncScroll) {
      const maxTarget = preview.scrollHeight - preview.clientHeight;
      if (maxTarget > 0 && prevRatio > 0) {
        preview.scrollTop = Math.round(prevRatio * maxTarget);
      }
    }
  }
}

async function saveCurrentDoc() {
  if (!_currentDoc || !_currentDoc.name) {
    toast("No file open", "Please select a documentation file first.", "warn");
    return;
  }
  const badge = $("#docs-status-badge");
  if (badge) badge.textContent = "Saving…";

  let content = "";
  let format = "rst";
  if (_docsEditorType === "raw") {
    content = $("#docs-raw-rst")?.value || "";
    format = "rst";
  } else {
    content = _quill ? _quill.root.innerHTML : "";
    format = "html";
  }

  try {
    const res = await fetch("/api/docs/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: _currentDoc.name,
        dir: _docsCustomDir || _docsActiveDir || "",
        content: content,
        format: format,
      }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Save failed");
    _currentDoc.rst = data.rst;
    _currentDoc.html = data.html;
    if ($("#docs-raw-rst")) $("#docs-raw-rst").value = data.rst;
    setDocsDirty(false);
    if (badge) badge.textContent = "Saved ✔";
    toast("Saved Successfully 💾", `${_currentDoc.name} written (backup .rst.bak created).`, "ok", 3000);
  } catch (err) {
    if (badge) badge.textContent = "Save Failed";
    toast("Save Failed", String(err.message || err), "danger");
  }
}

function getActiveDocsDirHint() {
  if (_docsCustomDir) return _docsCustomDir;
  const badgeText = $("#docs-active-dir-badge")?.textContent;
  if (badgeText) return badgeText;
  if (_docsActiveDir) return _docsActiveDir;
  if (_currentDoc?.full_path) {
    return _currentDoc.full_path.replace(/[\\/][^\\/]+$/, "");
  }
  return "sphinx/templates/architecture";
}

async function buildSphinxDocs() {
  const badge = $("#docs-status-badge");
  const targetDirHint = getActiveDocsDirHint();
  if (badge) {
    badge.textContent = "Building Sphinx…";
    badge.title = `Building docs in: ${targetDirHint}`;
  }
  toast("Building Docs 🔨", `Directory: ${targetDirHint}\nCompiling Sphinx HTML in background…`, "info", 4000);
  try {
    const res = await fetch("/api/docs/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir: _docsCustomDir || _docsActiveDir || "",
        current_file: _currentDoc?.full_path || _currentDoc?.name || "",
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (badge) {
        badge.textContent = "Build Success ✔";
        badge.title = `Built: ${data.target_dir}\nOutput: ${data.html_dir}`;
      }
      if (data.target_dir) _docsActiveDir = data.target_dir;
      toast("Sphinx Build Succeeded 🎉", `Source: ${data.target_dir}\nOutput: ${data.html_dir}`, "ok", 6000);
    } else {
      if (badge) badge.textContent = "Build Warning";
      const errDetail = data.stderr || data.error || "Build returned non-zero code";
      toast("Sphinx Build Warning", `Directory: ${data.target_dir || targetDirHint}\n${errDetail.slice(0, 160)}`, "warn", 6000);
    }
  } catch (err) {
    if (badge) badge.textContent = "Build Error";
    toast("Build Error", `Directory: ${targetDirHint}\n${String(err.message || err)}`, "danger");
  }
}

async function startSphinxDocs() {
  const badge = $("#docs-status-badge");
  const targetDirHint = getActiveDocsDirHint();
  if (badge) {
    badge.textContent = "Starting Docs Server…";
    badge.title = `Starting HTTP preview server for: ${targetDirHint}`;
  }
  toast("Launching Docs 🚀", `Directory: ${targetDirHint}\nStarting HTTP preview server & opening browser…`, "info", 4000);
  try {
    const res = await fetch("/api/docs/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir: _docsCustomDir || _docsActiveDir || "",
        current_file: _currentDoc?.full_path || _currentDoc?.name || "",
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (badge) {
        badge.textContent = `Live :${data.port || 8789} ✔`;
        badge.title = `Directory: ${data.target_dir}\nServing: ${data.html_dir}\nURL: ${data.url}`;
      }
      if (data.target_dir) _docsActiveDir = data.target_dir;
      toast("Docs Server Live 🌐", `Source: ${data.target_dir}\nServing: ${data.html_dir}\nURL: ${data.url}`, "ok", 6000);
      try {
        const previewUrl = data.cache_bust_url || `${data.url}/?_t=${Date.now()}`;
        window.open(previewUrl, "_blank");
      } catch { /* browser popup blocker */ }
    } else {
      if (badge) badge.textContent = "Server Error";
      toast("Failed to start docs server", `Directory: ${data.target_dir || targetDirHint}\n${data.error || "Unknown error"}`, "danger");
    }
  } catch (err) {
    if (badge) badge.textContent = "Server Error";
    toast("Server Error", `Directory: ${targetDirHint}\n${String(err.message || err)}`, "danger");
  }
}

async function cleanSphinxDocs() {
  const badge = $("#docs-status-badge");
  const targetDirHint = getActiveDocsDirHint();
  if (badge) badge.textContent = "Cleaning…";
  toast("Cleaning Cache 🧹", `Removing _build cache in: ${targetDirHint}…`, "info", 3000);
  try {
    const res = await fetch("/api/docs/clean", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir: _docsCustomDir || _docsActiveDir || "",
        current_file: _currentDoc?.full_path || _currentDoc?.name || "",
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (badge) badge.textContent = "Cleaned ✔";
      toast("Cache Cleaned 🧹", `Removed build cache: ${data.cleaned_dir}\nReady for fresh compile.`, "ok", 4000);
    } else {
      if (badge) badge.textContent = "Clean Error";
      toast("Clean Error", data.error || "Failed to remove cache", "danger");
    }
  } catch (err) {
    if (badge) badge.textContent = "Clean Error";
    toast("Clean Error", String(err.message || err), "danger");
  }
}

async function handleDocsFileUpload(file) {
  if (!file) return;
  initQuill();
  const badge = $("#docs-status-badge");
  if (badge) badge.textContent = "Importing…";

  try {
    const rawText = await file.text();
    const fname = file.name.toLowerCase();
    let rstContent = "";
    let htmlContent = "";

    if (fname.endsWith(".html") || fname.endsWith(".htm")) {
      htmlContent = rawText;
      const res = await fetch("/api/docs/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: rawText, direction: "html2rst" }),
      });
      const data = await res.json();
      rstContent = data.ok ? data.rst : rawText;
    } else {
      rstContent = rawText;
      const res = await fetch("/api/docs/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: rawText, direction: "rst2html" }),
      });
      const data = await res.json();
      htmlContent = data.ok ? data.html : `<p>${rawText}</p>`;
    }

    let saveName = file.name;
    if (!saveName.endsWith(".rst")) {
      saveName = saveName.replace(/\.[^.]+$/, "") + ".rst";
    }
    if (!saveName.includes("/")) {
      saveName = `docs/${saveName}`;
    }

    _currentDoc = {
      name: saveName,
      rst: rstContent,
      html: htmlContent,
      mtime: Math.floor(Date.now() / 1000),
      readonly: false,
    };

    if (_quill) {
      if (htmlContent) {
        _quill.clipboard.dangerouslyPasteHTML(0, htmlContent);
      } else {
        _quill.setText("");
      }
      renderAllMermaidBlocks(_quill.root);
      wirePlantumlBlocks(_quill.root);
      wireDocTableBlocks(_quill.root);
    }
    const rawTa = $("#docs-raw-rst");
    if (rawTa) rawTa.value = rstContent;

    const meta = $("#docs-file-meta");
    if (meta) {
      meta.textContent = `Imported: ${saveName} (${(file.size / 1024).toFixed(1)} KB) · Click '💾 Save RST' to write to disk.`;
    }

    setDocsDirty(true);
    if (badge) badge.textContent = "Imported (Unsaved)";
    toast("File Imported 📤", `${file.name} loaded into editor. Ready to edit and save.`, "ok", 4000);
    if (_docsSplit) updateDocsPreview();
  } catch (err) {
    if (badge) badge.textContent = "Import Failed";
    toast("Import Failed", String(err.message || err), "danger");
  }
}

/* ==============================================================================
   AOSP Command Center & Environment Module
   ============================================================================== */
let _aospRunning = false;
let _aospAbortController = null;
let _aospLoadedData = null;

async function loadAospConfig() {
  try {
    const res = await fetch("/api/aosp/config");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!data.ok) return;

    _aospLoadedData = data;

    // Compact bar: AOSP Root Path & Status
    const barRoot = $("#aosp-bar-root");
    const pathStatus = $("#aosp-path-status");
    if (barRoot) {
      if (data.aosp_root_dir) {
        barRoot.textContent = data.aosp_root_dir;
        barRoot.title = `AOSP Root Directory: ${data.aosp_root_dir}`;
        if (pathStatus) {
          pathStatus.innerHTML = data.aosp_exists
            ? '<span style="color:#3fb950;font-weight:700;" title="Directory exists on disk">✔</span>'
            : '<span style="color:#f85149;font-weight:700;" title="Directory not found on disk">⚠️</span>';
        }
      } else {
        barRoot.textContent = "Auto-detect (ancestor search)";
        barRoot.title = "Searching parent directories for 'android/'";
        if (pathStatus) pathStatus.innerHTML = "";
      }
    }

    // Compact bar: Active Project Select
    const projSel = $("#aosp-project-select");
    if (projSel) {
      projSel.innerHTML = "";
      (data.profiles || []).forEach(p => {
        const opt = document.createElement("option");
        opt.value = p;
        opt.textContent = p;
        if (p === data.active_project) opt.selected = true;
        projSel.appendChild(opt);
      });
    }

    // Compact bar: Lunch Target (Product & Variant combined)
    const barTarget = $("#aosp-bar-target");
    if (barTarget) {
      const targetStr = (data.target_product && data.target_variant)
        ? `${data.target_product}-${data.target_variant}`
        : "lunch: —";
      barTarget.textContent = targetStr;
    }

    // Compact bar: Meta pills
    if ($("#aosp-meta-module")) $("#aosp-meta-module").textContent = data.module_name || "—";
    if ($("#aosp-meta-apk")) $("#aosp-meta-apk").textContent = data.apk_name || "—";
    if ($("#aosp-meta-source")) {
      const srcEl = $("#aosp-meta-source");
      srcEl.textContent = data.source_path || "—";
      srcEl.title = data.source_dir
        ? `Source dir: ${data.source_dir}${data.apk_config_in_source ? " (apk.config ✔)" : " (apk.config missing — auto-created on project switch)"}`
        : "";
    }
    if ($("#aosp-meta-deploy")) $("#aosp-meta-deploy").textContent = data.deploy_path || "—";
  } catch (err) {
    console.error("Failed to load AOSP config:", err);
  }
}

function openAospConfigModal() {
  const d = _aospLoadedData || {};
  if ($("#aosp-modal-root-input")) $("#aosp-modal-root-input").value = d.aosp_root_dir || "";
  if ($("#aosp-modal-cfg-file")) $("#aosp-modal-cfg-file").textContent = d.config_file || "config/apk.config";

  const modalPathStatus = $("#aosp-modal-path-status");
  if (modalPathStatus) {
    if (d.aosp_root_dir) {
      modalPathStatus.innerHTML = d.aosp_exists
        ? '<span style="color:#3fb950;font-weight:600;">✔ Directory exists on disk</span>'
        : '<span style="color:#f85149;font-weight:600;">⚠️ Directory not found on disk</span>';
    } else {
      modalPathStatus.innerHTML = '<span style="color:var(--text-dim);font-style:italic;">Auto-detect from ancestors</span>';
    }
  }

  const modalProjSel = $("#aosp-modal-project-select");
  if (modalProjSel) {
    modalProjSel.innerHTML = "";
    (d.profiles || []).forEach(p => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      if (p === d.active_project) opt.selected = true;
      modalProjSel.appendChild(opt);
    });
  }

  if ($("#aosp-modal-target-product")) $("#aosp-modal-target-product").value = d.target_product || "";
  const variantSel = $("#aosp-modal-target-variant");
  if (variantSel) {
    const val = d.target_variant || "userdebug";
    if (![...variantSel.options].some(o => o.value === val)) {
      const opt = document.createElement("option");
      opt.value = val;
      opt.textContent = val;
      variantSel.appendChild(opt);
    }
    variantSel.value = val;
  }

  $("#modal-aosp-config")?.classList.remove("hidden");
  setTimeout(() => $("#aosp-modal-root-input")?.focus(), 50);
}

function closeAospConfigModal() {
  $("#modal-aosp-config")?.classList.add("hidden");
}

async function saveAospConfigFromModal() {
  const saveBtn = $("#btn-aosp-modal-save");
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";
  }
  try {
    const payload = {
      aosp_root_dir: $("#aosp-modal-root-input")?.value || "",
      active_project: $("#aosp-modal-project-select")?.value || "",
      target_product: $("#aosp-modal-target-product")?.value || "",
      target_variant: $("#aosp-modal-target-variant")?.value || "",
    };
    const res = await fetch("/api/aosp/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    closeAospConfigModal();
    await loadAospConfig();
    refreshStatus();
    toast("AOSP Configuration Saved", "Updated apk.config successfully.", "ok", 3000);
  } catch (err) {
    toast("Save Failed", String(err.message || err), "danger");
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = "💾 Save Configuration";
    }
  }
}

async function uploadOverlayFile(file, targetName) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  if (targetName) formData.append("target", targetName);

  try {
    const res = await fetch("/api/overlay/upload", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.description || "Upload failed");
    }
    toast("Overlay Uploaded 💾", `Saved ${data.filename} to config/overlay/!`, "ok", 4000);
    if (data.filename === "apk_overlays.config") {
      await loadAospConfig();
      openAospConfigModal();
      refreshStatus();
    } else if (data.filename === "const_my_cli.config") {
      if (state.plSource === "my") {
        await loadPipelines("my");
      }
    }
  } catch (err) {
    toast("Upload Failed ❌", String(err.message || err), "danger", 5000);
  }
}

async function quickSwitchAospProject(projectName) {
  if (!projectName) return;
  try {
    const res = await fetch("/api/aosp/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_project: projectName }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    await loadAospConfig();
    refreshStatus();
    toast("Project Switched", `ACTIVE_PROJECT="${projectName}"`, "ok", 2500);
  } catch (err) {
    toast("Switch Failed", String(err.message || err), "danger");
  }
}

/**
 * Upload a locally-built APK to the connected device via the Web backend.
 * Flow: validate filename vs OUTPUT_FILE_NAME -> POST /api/aosp/upload-apk
 *       (backend adb push to DEPLOY_PATH + chmod + rm oat cache) -> framework restart.
 * restartMode: "framework" (stop && start, fast) or "reboot" (full device reboot).
 */
async function uploadAospApk(file, restartMode = "framework") {
  if (_aospRunning) {
    toast("AOSP busy", "Please wait for current command to complete or click ⏹ Stop.", "warn");
    return;
  }
  const outEl = $("#aosp-output");
  const badge = $("#aosp-status-badge");
  const stopBtn = $("#btn-aosp-stop");
  const uploadBtn = $("#btn-aosp-upload-apk");
  const actionBtns = document.querySelectorAll(".aosp-action-btn");

  const appendOut = (html) => {
    if (!outEl) return;
    outEl.innerHTML += html + "\n";
    outEl.scrollTop = outEl.scrollHeight;
  };

  // Client-side pre-check against the loaded AOSP meta (OUTPUT_FILE_NAME)
  const expected = (_aospLoadedData && _aospLoadedData.apk_name) || "";
  if (expected && file.name.toLowerCase() !== expected.toLowerCase()) {
    appendOut(`<span style="color:#f85149;font-weight:700">✕ Filename mismatch:</span> uploaded <b>${esc(file.name)}</b> but active project expects <b>${esc(expected)}</b> (OUTPUT_FILE_NAME).`);
    toast("Filename mismatch", `Expected "${expected}", got "${file.name}".`, "danger", 5000);
    return;
  }

  _aospRunning = true;
  actionBtns.forEach(b => b.disabled = true);
  if (uploadBtn) uploadBtn.classList.add("running-active");
  if (stopBtn) { stopBtn.disabled = false; stopBtn.classList.add("danger-solid"); }
  if (badge) { badge.textContent = "📤 Uploading…"; badge.className = "run-badge running"; }

  appendOut(`<span style="color:#3fb950;font-weight:700">tel:aosp $</span> <span style="color:#c4b5fd;font-weight:700">📤 upload-apk ${esc(file.name)} (${(file.size / 1048576).toFixed(1)} MB) → deploy + ${restartMode === "reboot" ? "reboot" : "restart framework"}</span>`);

  const startedAt = Date.now();
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("restart", restartMode);
    const res = await fetch("/api/aosp/upload-apk", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    const secs = ((Date.now() - startedAt) / 1000).toFixed(1);

    if (res.ok && data.ok) {
      const sizeMb = data.bytes ? (data.bytes / 1048576).toFixed(2) : null;
      const devMb = data.device_bytes ? (data.device_bytes / 1048576).toFixed(2) : null;
      const ig = data.integrity || {};
      let sizeStr = sizeMb ? ` · 📦 ${sizeMb} MB` : "";
      if (devMb && sizeMb && devMb !== sizeMb) {
        sizeStr += ` <span style="color:#f0883e">(⚠️ on-device: ${devMb} MB)</span>`;
      } else if (devMb) {
        sizeStr += ` <span style="opacity:.75">(on-device ✔ ${devMb} MB)</span>`;
      }
      // Integrity: SHA-256 local vs on-device
      let integrityStr = "";
      if (ig.hash_match === true) {
        const short = (data.sha256 || "").slice(0, 12);
        integrityStr = ` · 🔒 SHA-256 <span style="opacity:.75;font-family:monospace">${esc(short)}…</span> <span style="color:#3fb950">verified ✔</span>`;
      } else if (ig.hash_match === false) {
        integrityStr = ` · 🔒 <span style="color:#f85149">SHA-256 MISMATCH</span>`;
      }
      appendOut(`<pre style="margin:4px 0;white-space:pre-wrap;color:#9aa4b2">${esc(data.output || "")}</pre>`);
      appendOut(`<span style="color:#3fb950;font-weight:700">✔ Deployed in ${secs}s:</span> ${esc(data.filename)}${sizeStr}${integrityStr} → <b>${esc(data.deploy_path)}/</b> · ${esc(data.restart)}`);
      if (badge) { badge.textContent = `✔ Deployed ${sizeMb ? sizeMb + "MB · " : ""}(${secs}s)`; badge.className = "run-badge done"; }
      toast("APK Deployed ✓", `${data.filename}${sizeMb ? " (" + sizeMb + " MB" + (devMb && devMb !== sizeMb ? " → device " + devMb + " MB" : "") + ")" : ""} · SHA-256 verified & ${data.restart}.`, "ok", 4500);
    } else {
      const msg = data.error || data.description || `HTTP ${res.status}`;
      appendOut(`<span style="color:#f85149;font-weight:700">✕ Upload failed:</span> ${esc(msg)}`);
      if (badge) { badge.textContent = "✕ Failed"; badge.className = "run-badge error"; }
      toast("Upload failed", msg, "danger", 6000);
    }
  } catch (err) {
    appendOut(`<span style="color:#f85149;font-weight:700">✕ Upload error:</span> ${esc(String(err.message || err))}`);
    if (badge) { badge.textContent = "✕ Failed"; badge.className = "run-badge error"; }
    toast("Upload error", String(err.message || err), "danger");
  } finally {
    _aospRunning = false;
    actionBtns.forEach(b => b.disabled = false);
    if (uploadBtn) uploadBtn.classList.remove("running-active");
    if (stopBtn) { stopBtn.disabled = true; stopBtn.classList.remove("danger-solid"); }
  }
}

async function runAospCommand(cmd, sourceBtn) {
  cmd = (cmd || "").trim();
  if (!cmd) return;
  if (_aospRunning) {
    toast("AOSP busy", "Please wait for current command to complete or click ⏹ Stop.", "warn");
    return;
  }

  const outEl = $("#aosp-output");
  const badge = $("#aosp-status-badge");
  const stopBtn = $("#btn-aosp-stop");
  const actionBtns = document.querySelectorAll(".aosp-action-btn");

  _aospRunning = true;
  _aospAbortController = new AbortController();
  const signal = _aospAbortController.signal;

  actionBtns.forEach(b => b.disabled = true);
  if (stopBtn) {
    stopBtn.disabled = false;
    stopBtn.classList.add("danger-solid");
  }

  // Highlight the clicked button/chip (amber pulsing glow) so the user can
  // always see WHICH command is currently running.
  let activeBtn = sourceBtn instanceof Element ? sourceBtn : null;
  if (!activeBtn) {
    const sel = `.aosp-action-btn[data-cmd="${CSS.escape(cmd)}"], .aosp-chip[data-cmd="${CSS.escape(cmd)}"]`;
    activeBtn = document.querySelector(sel);
  }
  if (activeBtn) activeBtn.classList.add("running-active");

  const separator = outEl && outEl.innerHTML.trim() ? "\n" : "";
  const runDir = (_aospLoadedData && _aospLoadedData.source_dir_exists && _aospLoadedData.source_dir)
    ? _aospLoadedData.source_dir : "";
  const dirHint = runDir ? `<span style="opacity:.65"> (cd ${esc(runDir)})</span>` : "";
  const headerHtml = `${separator}<span style="color:#3fb950;font-weight:700">tel:aosp $</span> <span style="color:#58a6ff;font-weight:700">${esc(cmd)}</span>${dirHint}\n`;
  if (outEl) {
    outEl.innerHTML += headerHtml + `<span style="opacity:.7">⏳ Running… (click ⏹ Stop to abort)</span>\n`;
    outEl.scrollTop = outEl.scrollHeight;
  }

  let elapsed = 0;
  if (badge) {
    badge.textContent = `⏳ Running… (0s)`;
    badge.className = "run-badge running";
  }
  const timerId = setInterval(() => {
    elapsed++;
    if (badge && _aospRunning) badge.textContent = `⏳ Running… (${elapsed}s)`;
  }, 1000);

  let streamedPreview = "";
  try {
    // Run from the project source directory (<AOSP_TOP>/<SOURCE_CODE_RELATIVE_PATH>)
    // so build_apk.sh discovers the project's own apk.config (profiles,
    // TEST_BUILD_SCRIPT, ...). Falls back to the AOSP root, then the toolkit root.
    const d = _aospLoadedData || {};
    const aospCwd = (d.source_dir_exists && d.source_dir) ? d.source_dir
      : (d.aosp_exists && d.aosp_root_dir) ? d.aosp_root_dir : "";
    const res = await fetch("/api/terminal/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd, cwd: aospCwd }),
      signal,
    });

    if (res.ok && res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let rawBuffer = "";
      let exitCode = 0;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        rawBuffer += chunk;

        const lines = rawBuffer.split("\n");
        rawBuffer = lines.pop() || "";
        for (const line of lines) {
          const mExit = line.match(/^__TELUA_EXIT_CODE__:(\d+)/);
          if (mExit) {
            exitCode = parseInt(mExit[1], 10);
            continue;
          }
          if (line.startsWith("__TELUA_PWD__:")) continue;
          streamedPreview += line + "\n";
          if (streamedPreview.length > 150000) {
            streamedPreview = streamedPreview.slice(-120000);
          }
        }
        if (outEl) {
          outEl.innerHTML = headerHtml + ansiToHtml(streamedPreview);
          outEl.scrollTop = outEl.scrollHeight;
        }
      }

      if (rawBuffer) {
        const mExit = rawBuffer.match(/^__TELUA_EXIT_CODE__:(\d+)/);
        if (mExit) {
          exitCode = parseInt(mExit[1], 10);
        } else if (!rawBuffer.startsWith("__TELUA_PWD__:")) {
          streamedPreview += rawBuffer;
          if (outEl) {
            outEl.innerHTML = headerHtml + ansiToHtml(streamedPreview);
            outEl.scrollTop = outEl.scrollHeight;
          }
        }
      }

      clearInterval(timerId);
      if (badge) {
        if (exitCode === 0) {
          badge.textContent = `✔ Finished (${elapsed}s)`;
          badge.className = "run-badge ok";
          toast("AOSP Command Succeeded", `'${cmd}' completed successfully.`, "ok", 3000);
        } else {
          badge.textContent = `❌ Exit ${exitCode} (${elapsed}s)`;
          badge.className = "run-badge error";
          toast("AOSP Command Failed", `'${cmd}' exited with code ${exitCode}.`, "danger", 4000);
        }
      }
    } else {
      throw new Error("HTTP " + res.status);
    }
  } catch (err) {
    clearInterval(timerId);
    if (signal.aborted) {
      if (badge) {
        badge.textContent = `⏹ Stopped (${elapsed}s)`;
        badge.className = "run-badge warn";
      }
      if (outEl) {
        outEl.innerHTML += `<span style="color:#d29922">\n[INTERRUPTED] Command aborted by user.\n</span>`;
      }
    } else {
      if (badge) {
        badge.textContent = `❌ Error (${elapsed}s)`;
        badge.className = "run-badge error";
      }
      if (outEl) {
        outEl.innerHTML += `<span style="color:#f85149">\n[ERROR] ${esc(String(err.message || err))}\n</span>`;
      }
    }
  } finally {
    clearInterval(timerId);
    _aospRunning = false;
    _aospAbortController = null;
    actionBtns.forEach(b => b.disabled = false);
    if (stopBtn) {
      stopBtn.disabled = true;
      stopBtn.classList.remove("danger-solid");
    }
    if (activeBtn) activeBtn.classList.remove("running-active");
    if (outEl) outEl.scrollTop = outEl.scrollHeight;
  }
}

async function stopAospCommand() {
  if (!_aospRunning) return;
  if (_aospAbortController) {
    try { _aospAbortController.abort(); } catch { /* ignore */ }
  }
  try {
    await fetch("/api/terminal/stop", { method: "POST" });
  } catch { /* ignore */ }
}

/* ---------------- Logcat Controller & Realtime Filtering ---------------- */
// ~5 minutes of history at a typical 120 lines/s device log rate.
// Ring-buffer eviction (shift) is what makes old logs disappear after a
// while, so this cap directly controls how long logs stay on screen.
const LOGCAT_MAX_LINES = 36000;
const LOG_LEVEL_SCORES = { V: 1, D: 2, I: 3, W: 4, E: 5, F: 6 };
const THREADTIME_RE = /^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([^:]+):\s*(.*)$/;
const BRIEF_RE = /^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+([VDIWEF])\/([^(]+)\(\s*(\d+)\):\s*(.*)$/;

let _logcatEntries = [];
let _logcatStreaming = false;
let _logcatAbortController = null;
let _logcatRenderPending = false;
let _logcatAutoScroll = true;
let _logcatInitialized = false;

const LOGCAT_RULES_STORAGE_KEY = "telua_logcat_filters";
// Remembers an active logcat stream across page refreshes (session-scoped,
// so a fresh browser tab always starts idle).
const LOGCAT_AUTOSTART_KEY = "telua_logcat_was_streaming";
// Persists the top toolbar quick filters (message/regex, level, tag, PID)
// across page refreshes so the user doesn't have to retype them.
const LOGCAT_TOOLBAR_KEY = "telua_logcat_toolbar_filters";
let _logcatRules = [];
// Bumped every time filter rules change. Log entries parsed before the bump
// are never hidden by rules, so enabling a rule keeps already-shown logs.
let _logcatRuleEpoch = 0;
// Monotonic count of entries ever parsed. Unlike _logcatEntries.length, it
// keeps growing when the ring buffer is full (push+shift), letting the
// renderer know how many new entries arrived since the last paint.
let _logcatSeenCount = 0;
// Max DOM rows kept on screen; older rows are trimmed (the buffer still
// holds them for Copy/Export, which read _logcatEntries directly).
const LOGCAT_DOM_MAX_ROWS = 15000;

// Regex cache for logcat rules: compiling a RegExp per entry (36k lines x
// multiple rules) is extremely expensive and freezes the UI when toggling
// filters. Cache compiled regexes keyed by pattern string.
const _logcatRuleRegexCache = new Map();
function getLogcatRuleRegex(pattern) {
  let re = _logcatRuleRegexCache.get(pattern);
  if (re === undefined) {
    try { re = new RegExp(pattern, "i"); } catch { re = null; }
    _logcatRuleRegexCache.set(pattern, re);
  }
  return re;
}

function matchLogcatRule(entry, rule) {
  if (!rule || !rule.enabled) return false;
  if (rule.level && rule.level !== "ALL") {
    const minScore = LOG_LEVEL_SCORES[rule.level] || 1;
    if (entry.levelScore < minScore) return false;
  }
  if (rule.tag) {
    const re = getLogcatRuleRegex(rule.tag);
    if (re) {
      if (!re.test(entry.tag)) return false;
    } else if (!entry.tag.toLowerCase().includes(rule.tag.toLowerCase())) {
      return false;
    }
  }
  if (rule.pid) {
    if (!String(entry.pid).includes(String(rule.pid).trim())) return false;
  }
  if (rule.text) {
    const re = getLogcatRuleRegex(rule.text);
    if (re) {
      if (!re.test(entry.msg) && !re.test(entry.tag) && !re.test(entry.raw)) return false;
    } else if (!entry.raw.toLowerCase().includes(rule.text.toLowerCase())) {
      return false;
    }
  }
  return true;
}

function parseLogcatLine(raw) {
  const line = raw.replace(/\r?\n$/, "");
  if (!line.trim()) return null;

  let m = THREADTIME_RE.exec(line);
  if (m) {
    return {
      time: m[1],
      pid: m[2],
      tid: m[3],
      level: m[4],
      levelScore: LOG_LEVEL_SCORES[m[4]] || 1,
      tag: m[5].trim(),
      msg: m[6],
      raw: line,
      epoch: _logcatRuleEpoch,
    };
  }
  m = BRIEF_RE.exec(line);
  if (m) {
    return {
      time: m[1],
      pid: m[4],
      tid: "",
      level: m[2],
      levelScore: LOG_LEVEL_SCORES[m[2]] || 1,
      tag: m[3].trim(),
      msg: m[5],
      raw: line,
      epoch: _logcatRuleEpoch,
    };
  }

  let lvl = "I";
  if (/\b(FATAL|CRASH)\b/i.test(line)) lvl = "F";
  else if (/\b(ERROR|Exception|Error:)\b/i.test(line)) lvl = "E";
  else if (/\b(WARN|Warning)\b/i.test(line)) lvl = "W";
  else if (/\bDEBUG\b/i.test(line)) lvl = "D";

  return {
    time: "",
    pid: "",
    tid: "",
    level: lvl,
    levelScore: LOG_LEVEL_SCORES[lvl] || 1,
    tag: "",
    msg: line,
    raw: line,
    epoch: _logcatRuleEpoch,
  };
}

function getLogcatFilters() {
  const rawText = ($("#logcat-filter-text")?.value || "").trim();
  const rawLevel = $("#logcat-filter-level")?.value || "I";
  const rawTag = ($("#logcat-filter-tag")?.value || "").trim().toLowerCase();
  const rawPid = ($("#logcat-filter-pid")?.value || "").trim();

  let minLevelScore = 1;
  if (rawLevel !== "ALL") {
    minLevelScore = LOG_LEVEL_SCORES[rawLevel] || 1;
  }

  let isRegex = false;
  let regexObj = null;
  if (rawText && (rawText.includes("|") || rawText.includes(".*") || rawText.startsWith("^") || rawText.endsWith("$"))) {
    try {
      regexObj = new RegExp(rawText, "i");
      isRegex = true;
    } catch {
      isRegex = false;
    }
  }

  return {
    text: rawText.toLowerCase(),
    isRegex,
    regexObj,
    minLevelScore,
    tag: rawTag,
    pid: rawPid,
  };
}

function isLogcatEntryVisible(entry, filters) {
  if (!entry) return false;

  const activeRules = _logcatRules.filter(r => r.enabled);
  if (activeRules.length > 0) {
    // Rules only filter logs that arrived AFTER the last rule change, so
    // enabling/disabling a rule never hides the logs already on screen.
    const entryEpoch = entry.epoch ?? _logcatRuleEpoch;
    if (entryEpoch >= _logcatRuleEpoch) {
      // Entry must match at least ONE enabled rule
      const matched = activeRules.some(r => matchLogcatRule(entry, r));
      if (!matched) return false;
    }
  } else {
    // Fall back to top toolbar level, tag, and pid
    if (entry.levelScore < filters.minLevelScore) return false;
    if (filters.tag && !entry.tag.toLowerCase().includes(filters.tag)) return false;
    if (filters.pid && !entry.pid.includes(filters.pid)) return false;
  }

  // Quick text filter applies across visible results
  if (filters.text) {
    if (filters.isRegex) {
      try {
        if (!filters.regexObj.test(entry.raw)) return false;
      } catch {
        return false;
      }
    } else {
      if (!entry.raw.toLowerCase().includes(filters.text)) return false;
    }
  }
  return true;
}

function createLogcatRowEl(entry) {
  const row = document.createElement("div");
  row.className = `logcat-row level-${entry.level}`;

  if (entry.time) {
    const timeEl = document.createElement("span");
    timeEl.className = "log-time";
    timeEl.textContent = entry.time;
    row.appendChild(timeEl);
  }
  if (entry.pid) {
    const pidEl = document.createElement("span");
    pidEl.className = "log-pid";
    pidEl.textContent = entry.tid ? `${entry.pid}/${entry.tid}` : entry.pid;
    row.appendChild(pidEl);
  }
  const badge = document.createElement("span");
  badge.className = `log-badge level-${entry.level}`;
  badge.textContent = entry.level;
  row.appendChild(badge);

  if (entry.tag) {
    const tagEl = document.createElement("span");
    tagEl.className = "log-tag";
    tagEl.textContent = entry.tag + ":";
    tagEl.title = `Click to filter by tag: ${entry.tag}`;
    tagEl.addEventListener("click", () => {
      const tagInput = $("#logcat-filter-tag");
      if (tagInput) {
        tagInput.value = entry.tag;
        saveLogcatToolbarFilters();
        renderLogcat();
      }
    });
    row.appendChild(tagEl);
  }

  const msgEl = document.createElement("span");
  msgEl.className = "log-msg";
  msgEl.textContent = entry.msg;
  row.appendChild(msgEl);

  return row;
}

function renderLogcat() {
  const screen = $("#logcat-screen");
  if (!screen) return;
  const filters = getLogcatFilters();

  const filterKey = `${filters.text}|${filters.minLevelScore}|${filters.tag}|${filters.pid}|${_logcatRuleEpoch}|${_logcatRules.filter(r => r.enabled).map(r => r.id + (r.enabled ? 1 : 0)).join(",")}`;

  // Fast path: streaming tick with unchanged filters — append only entries
  // that arrived since the last render. Uses the monotonic seen-counter so
  // ring-buffer shifts (which keep _logcatEntries.length constant once full)
  // never stall rendering of new logs.
  const renderedCount = parseInt(screen.dataset.renderedCount || "-1", 10);
  const pending = _logcatSeenCount - renderedCount;
  if (screen.dataset.filterKey === filterKey
    && pending >= 0 && pending <= _logcatEntries.length
    && _logcatEntries.length > 0) {
    let visibleCount = parseInt(screen.dataset.visibleCount || "0", 10);
    if (pending > 0) {
      screen.querySelector(".logcat-empty-msg")?.remove();
      const frag = document.createDocumentFragment();
      for (let i = _logcatEntries.length - pending; i < _logcatEntries.length; i++) {
        const entry = _logcatEntries[i];
        if (isLogcatEntryVisible(entry, filters)) {
          frag.appendChild(createLogcatRowEl(entry));
          visibleCount++;
        }
      }
      if (frag.childElementCount > 0) screen.appendChild(frag);
    }
    // Cap DOM rows so long sessions don't grow the DOM unbounded
    if (screen.childElementCount > LOGCAT_DOM_MAX_ROWS) {
      const removeCount = screen.childElementCount - LOGCAT_DOM_MAX_ROWS;
      for (let i = 0; i < removeCount && screen.firstChild; i++) {
        screen.removeChild(screen.firstChild);
        visibleCount = Math.max(0, visibleCount - 1);
      }
    }
    screen.dataset.visibleCount = String(visibleCount);
    screen.dataset.renderedCount = String(_logcatSeenCount);
    const statsEl = $("#logcat-stats");
    if (statsEl) {
      statsEl.textContent = `${_logcatEntries.length} lines (${visibleCount} visible)`;
    }
    if (_logcatAutoScroll) {
      screen.scrollTop = screen.scrollHeight;
    }
    return;
  }

  // Full rebuild (filter changed, tab switch, first render, or after clear)
  screen.dataset.filterKey = filterKey;
  const frag = document.createDocumentFragment();
  let visibleCount = 0;

  for (let i = 0; i < _logcatEntries.length; i++) {
    const entry = _logcatEntries[i];
    if (isLogcatEntryVisible(entry, filters)) {
      frag.appendChild(createLogcatRowEl(entry));
      visibleCount++;
      if (frag.childElementCount > LOGCAT_DOM_MAX_ROWS) {
        frag.removeChild(frag.firstChild);
      }
    }
  }

  screen.innerHTML = "";
  if (visibleCount === 0) {
    const empty = document.createElement("div");
    empty.className = "logcat-empty-msg";
    empty.innerHTML = `<span>${_logcatEntries.length === 0 ? "No logs yet. Click '▶ Start' to connect to device." : "No logs match current filter criteria."}</span>`;
    screen.appendChild(empty);
  } else {
    screen.appendChild(frag);
  }
  screen.dataset.renderedCount = String(_logcatSeenCount);
  screen.dataset.visibleCount = String(visibleCount);

  const statsEl = $("#logcat-stats");
  if (statsEl) {
    statsEl.textContent = `${_logcatEntries.length} lines (${visibleCount} visible)`;
  }

  const clearBtn = $("#btn-logcat-clear-text");
  if (clearBtn) {
    clearBtn.classList.toggle("hidden", !filters.text);
  }

  if (_logcatAutoScroll) {
    screen.scrollTop = screen.scrollHeight;
  }
}

async function startLogcatStream() {
  if (_logcatStreaming) return;
  _logcatStreaming = true;
  try { sessionStorage.setItem(LOGCAT_AUTOSTART_KEY, "1"); } catch { /* ignore */ }
  updateLogcatControls();
  syncTopTabs();

  const badge = $("#logcat-status-badge");
  if (badge) {
    badge.textContent = "Streaming";
    badge.className = "run-badge ok";
  }

  _logcatAbortController = new AbortController();
  const screen = $("#logcat-screen");

  try {
    const res = await fetch("/api/logcat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      signal: _logcatAbortController.signal,
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.error || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();

      let added = false;
      for (const line of lines) {
        if (!line.trim()) continue;
        if (line.includes("__TELUA_LOGCAT_DONE__")) break;
        const entry = parseLogcatLine(line);
        if (entry) {
          _logcatEntries.push(entry);
          if (_logcatEntries.length > LOGCAT_MAX_LINES) {
            _logcatEntries.shift();
          }
          _logcatSeenCount++;
          added = true;
        }
      }

      if (added && !_logcatRenderPending) {
        _logcatRenderPending = true;
        requestAnimationFrame(() => {
          _logcatRenderPending = false;
          const viewLogcat = $("#view-logcat");
          if (viewLogcat && !viewLogcat.classList.contains("hidden")) {
            renderLogcat();
          }
        });
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      toast("Logcat Stream Error", err.message, "err");
      if (screen) {
        const errRow = document.createElement("div");
        errRow.className = "logcat-row level-E";
        errRow.textContent = `[ERROR] ${err.message}`;
        screen.appendChild(errRow);
      }
    }
  } finally {
    _logcatStreaming = false;
    _logcatAbortController = null;
    // NOTE: do NOT clear LOGCAT_AUTOSTART_KEY here. When the user refreshes
    // the page, the browser aborts this fetch, which lands in this finally
    // block — clearing the flag here would erase the resume marker before
    // the new page's boot() reads it. The flag is cleared only by an
    // explicit user stop (stopLogcatStream).
    updateLogcatControls();
    syncTopTabs();
    if (badge) {
      badge.textContent = "Idle";
      badge.className = "run-badge";
    }
  }
}

async function stopLogcatStream() {
  if (_logcatAbortController) {
    try { _logcatAbortController.abort(); } catch { /* ignore */ }
  }
  _logcatStreaming = false;
  // Explicit user stop: clear the resume marker so a refresh stays idle.
  try { sessionStorage.removeItem(LOGCAT_AUTOSTART_KEY); } catch { /* ignore */ }
  try {
    await fetch("/api/logcat/stop", { method: "POST" });
  } catch { /* ignore */ }
  updateLogcatControls();
  syncTopTabs();
}

function updateLogcatControls() {
  const toggleBtn = $("#btn-logcat-toggle");
  if (toggleBtn) {
    if (_logcatStreaming) {
      toggleBtn.textContent = "⏸ Pause";
      toggleBtn.className = "btn jade-btn";
    } else {
      toggleBtn.textContent = "▶ Start";
      toggleBtn.className = "btn primary";
    }
  }
}

function clearLogcatView() {
  _logcatEntries = [];
  const screen = $("#logcat-screen");
  if (screen) {
    screen.innerHTML = "";
    delete screen.dataset.filterKey;
    delete screen.dataset.renderedCount;
    delete screen.dataset.visibleCount;
  }
  renderLogcat();
  toast("Logcat View Cleared", "Cleared browser display buffer.", "info", 2000);
}

async function clearLogcatDevice() {
  if (!confirm("Clear device circular log buffer (adb logcat -c)?")) return;
  try {
    const res = await fetch("/api/logcat/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (data.ok) {
      toast("Device Buffer Cleared", "adb logcat -c completed successfully.", "ok", 3000);
      _logcatEntries = [];
      const screen = $("#logcat-screen");
      if (screen) {
        screen.innerHTML = "";
        delete screen.dataset.filterKey;
        delete screen.dataset.renderedCount;
        delete screen.dataset.visibleCount;
      }
      renderLogcat();
    } else {
      throw new Error(data.error || "Failed to clear device buffer");
    }
  } catch (err) {
    toast("Clear Device Failed", err.message, "err");
  }
}

function copyLogcat() {
  const filters = getLogcatFilters();
  const visibleLines = _logcatEntries
    .filter(e => isLogcatEntryVisible(e, filters))
    .map(e => e.raw);
  if (visibleLines.length === 0) {
    toast("Nothing to copy", "No visible logs match filter.", "warn");
    return;
  }
  navigator.clipboard.writeText(visibleLines.join("\n"))
    .then(() => toast("Copied ✓", `Copied ${visibleLines.length} log lines to clipboard.`, "ok", 2500))
    .catch(err => toast("Copy failed", err.message, "err"));
}

function exportLogcat() {
  const filters = getLogcatFilters();
  const visibleLines = _logcatEntries
    .filter(e => isLogcatEntryVisible(e, filters))
    .map(e => e.raw);
  if (visibleLines.length === 0) {
    toast("Nothing to export", "No visible logs match filter.", "warn");
    return;
  }
  const blob = new Blob([visibleLines.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  a.href = url;
  a.download = `logcat_${stamp}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast("Exported ✓", `Downloaded ${visibleLines.length} log lines.`, "ok", 2500);
}

/* ---------------- Logcat Filter Rules Management (Dialog & JSON Config) ---------------- */
async function loadLogcatFilters() {
  try {
    const res = await fetch("/api/logcat/filters");
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.filters) && data.filters.length > 0) {
        _logcatRules = data.filters;
        updateLogcatFilterBadge();
        renderLogcat();
        return;
      }
    }
  } catch { /* ignore fallback */ }

  if (!_logcatRules || _logcatRules.length === 0) {
    try {
      const saved = localStorage.getItem(LOGCAT_RULES_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          _logcatRules = parsed;
        }
      }
    } catch { /* ignore */ }
  }

  if (!_logcatRules || _logcatRules.length === 0) {
    _logcatRules = [
      { id: "rule-fatal", name: "Fatal & Crashes", enabled: true, level: "E", tag: "AndroidRuntime|DEBUG", text: "FATAL|CRASH|Exception", pid: "" },
      { id: "rule-caraudio", name: "Car Audio", enabled: false, level: "D", tag: "CarAudio.*|AudioFlinger", text: "", pid: "" },
      { id: "rule-carservice", name: "Car Service", enabled: false, level: "I", tag: "CarService|CarProperty.*", text: "", pid: "" },
      { id: "rule-oem", name: "OEM Service", enabled: false, level: "D", tag: "Oem.*", text: "", pid: "" },
      { id: "rule-am", name: "Activity Manager", enabled: false, level: "I", tag: "ActivityManager|ActivityTaskManager", text: "", pid: "" },
    ];
  }

  updateLogcatFilterBadge();
  renderLogcat();
}

function updateLogcatFilterBadge() {
  const activeCount = _logcatRules.filter(r => r.enabled).length;
  const badge = $("#logcat-filter-badge");
  if (badge) {
    badge.textContent = `${activeCount}`;
    badge.className = activeCount > 0 ? "chip ok" : "chip";
  }
  const modalCount = $("#logcat-modal-rules-count");
  if (modalCount) {
    modalCount.textContent = `${activeCount} active / ${_logcatRules.length} total`;
    modalCount.className = activeCount > 0 ? "chip ok" : "chip";
  }
}

function stripRuleInternal(r) {
  const { _editing, _isNew, ...clean } = r;
  return clean;
}

function isLogcatRuleLocked(rule) {
  // Locked rules (from the shared template) can only be enabled/disabled,
  // never edited or deleted. New user-created rules are never locked.
  return Boolean(rule && rule.locked && !rule._isNew);
}

function renderLogcatModalItems() {
  const container = $("#logcat-modal-items-container");
  if (!container) return;
  container.innerHTML = "";
  updateLogcatFilterBadge();

  if (_logcatRules.length === 0) {
    const emptyDiv = document.createElement("div");
    emptyDiv.className = "meta";
    emptyDiv.style.cssText = "text-align:center;padding:30px 10px;font-size:12px;";
    emptyDiv.innerHTML = "No filter rules configured. Click <b>+ Add Rule</b> or <b>⬆ Upload</b> to get started.";
    container.appendChild(emptyDiv);
    return;
  }

  _logcatRules.forEach((rule, idx) => {
    const card = document.createElement("div");
    card.className = `logcat-item-card ${rule._editing ? "editing" : (rule.enabled ? "active" : "disabled")}`;
    card.dataset.id = rule.id;

    if (rule._editing) {
      // ---------------- Inline Editing Form ----------------
      const gridTop = document.createElement("div");
      gridTop.style.cssText = "display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px;";

      // Name input
      const nameCol = document.createElement("div");
      const nameLbl = document.createElement("label");
      nameLbl.className = "meta";
      nameLbl.style.fontSize = "10px";
      nameLbl.textContent = "Rule Name *:";
      const nameIn = document.createElement("input");
      nameIn.type = "text";
      nameIn.className = "term-input mono";
      nameIn.style.cssText = "width:100%;height:28px;font-size:12px;box-sizing:border-box;";
      nameIn.value = rule.name || "";
      nameIn.placeholder = "e.g. Car Audio";
      nameCol.appendChild(nameLbl);
      nameCol.appendChild(nameIn);

      // Level select
      const lvlCol = document.createElement("div");
      const lvlLbl = document.createElement("label");
      lvlLbl.className = "meta";
      lvlLbl.style.fontSize = "10px";
      lvlLbl.textContent = "Min Level:";
      const lvlSel = document.createElement("select");
      lvlSel.className = "theme-select mono";
      lvlSel.style.cssText = "width:100%;height:28px;font-size:12px;box-sizing:border-box;";
      const levels = [
        { v: "ALL", l: "ALL Levels" },
        { v: "V", l: "V · Verbose +" },
        { v: "D", l: "D · Debug +" },
        { v: "I", l: "I · Info +" },
        { v: "W", l: "W · Warn +" },
        { v: "E", l: "E · Error +" },
        { v: "F", l: "F · Fatal only" },
      ];
      levels.forEach(lv => {
        const opt = document.createElement("option");
        opt.value = lv.v;
        opt.textContent = lv.l;
        if ((rule.level || "I") === lv.v) opt.selected = true;
        lvlSel.appendChild(opt);
      });
      lvlCol.appendChild(lvlLbl);
      lvlCol.appendChild(lvlSel);

      // PID input
      const pidCol = document.createElement("div");
      const pidLbl = document.createElement("label");
      pidLbl.className = "meta";
      pidLbl.style.fontSize = "10px";
      pidLbl.textContent = "PID (optional):";
      const pidIn = document.createElement("input");
      pidIn.type = "text";
      pidIn.className = "term-input mono";
      pidIn.style.cssText = "width:100%;height:28px;font-size:12px;box-sizing:border-box;";
      pidIn.value = rule.pid || "";
      pidIn.placeholder = "e.g. 1842";
      pidCol.appendChild(pidLbl);
      pidCol.appendChild(pidIn);

      gridTop.appendChild(nameCol);
      gridTop.appendChild(lvlCol);
      gridTop.appendChild(pidCol);

      // Grid Middle: Tag and Pattern
      const gridMid = document.createElement("div");
      gridMid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;";

      const tagCol = document.createElement("div");
      const tagLbl = document.createElement("label");
      tagLbl.className = "meta";
      tagLbl.style.fontSize = "10px";
      tagLbl.textContent = "Tag (string or regex):";
      const tagIn = document.createElement("input");
      tagIn.type = "text";
      tagIn.className = "term-input mono";
      tagIn.style.cssText = "width:100%;height:28px;font-size:12px;box-sizing:border-box;";
      tagIn.value = rule.tag || "";
      tagIn.placeholder = "e.g. CarAudio.* or AudioFlinger";
      tagCol.appendChild(tagLbl);
      tagCol.appendChild(tagIn);

      const textCol = document.createElement("div");
      const textLbl = document.createElement("label");
      textLbl.className = "meta";
      textLbl.style.fontSize = "10px";
      textLbl.textContent = "Message Pattern / Regex:";
      const textIn = document.createElement("input");
      textIn.type = "text";
      textIn.className = "term-input mono";
      textIn.style.cssText = "width:100%;height:28px;font-size:12px;box-sizing:border-box;";
      textIn.value = rule.text || "";
      textIn.placeholder = "e.g. FATAL|CRASH|Exception";
      textCol.appendChild(textLbl);
      textCol.appendChild(textIn);

      gridMid.appendChild(tagCol);
      gridMid.appendChild(textCol);

      // Bottom Row: Enabled toggle + Done / Cancel buttons
      const botRow = document.createElement("div");
      botRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;";

      const enableLbl = document.createElement("label");
      enableLbl.className = "chk";
      enableLbl.style.cssText = "cursor:pointer;font-size:11px;display:flex;align-items:center;gap:6px;";
      const enableChk = document.createElement("input");
      enableChk.type = "checkbox";
      enableChk.checked = rule.enabled ?? true;
      enableLbl.appendChild(enableChk);
      const enableText = document.createElement("span");
      enableText.textContent = "Enable this filter rule";
      enableLbl.appendChild(enableText);

      const btnGroup = document.createElement("div");
      btnGroup.style.cssText = "display:flex;gap:6px;";

      const cancelBtn = document.createElement("button");
      cancelBtn.className = "btn btn-xs";
      cancelBtn.textContent = "Cancel";
      cancelBtn.addEventListener("click", () => {
        if (rule._isNew) {
          _logcatRules = _logcatRules.filter(r => r.id !== rule.id);
        } else {
          delete rule._editing;
        }
        renderLogcatModalItems();
      });

      const doneBtn = document.createElement("button");
      doneBtn.className = "btn btn-xs primary";
      doneBtn.textContent = "✓ Done";
      doneBtn.addEventListener("click", () => {
        const valName = nameIn.value.trim();
        if (!valName) {
          toast("Name Required", "Please enter a rule name.", "warn");
          nameIn.focus();
          return;
        }
        rule.name = valName;
        rule.level = lvlSel.value;
        rule.tag = tagIn.value.trim();
        rule.text = textIn.value.trim();
        rule.pid = pidIn.value.trim();
        rule.enabled = enableChk.checked;
        delete rule._editing;
        delete rule._isNew;
        renderLogcatModalItems();
        updateLogcatFilterBadge();
        saveLogcatFilters(false);
      });

      btnGroup.appendChild(cancelBtn);
      btnGroup.appendChild(doneBtn);

      botRow.appendChild(enableLbl);
      botRow.appendChild(btnGroup);

      card.appendChild(gridTop);
      card.appendChild(gridMid);
      card.appendChild(botRow);

      container.appendChild(card);
      setTimeout(() => nameIn.focus(), 30);
    } else {
      // ---------------- Display Card View ----------------
      const head = document.createElement("div");
      head.className = "logcat-item-head";

      // Left: Checkbox + Rule Name
      const checkWrap = document.createElement("label");
      checkWrap.className = "logcat-item-check-wrap";
      checkWrap.title = rule.enabled ? "Rule is active (click to disable)" : "Rule is disabled (click to enable)";

      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.className = "logcat-item-toggle";
      chk.checked = Boolean(rule.enabled);
      chk.addEventListener("change", (e) => {
        rule.enabled = e.target.checked;
        card.className = `logcat-item-card ${rule.enabled ? "active" : "disabled"}`;
        updateLogcatFilterBadge();
        saveLogcatFilters(false);
      });
      checkWrap.appendChild(chk);

      const nameEl = document.createElement("span");
      nameEl.className = "logcat-item-name";
      nameEl.textContent = rule.name || "Untitled Rule";
      checkWrap.appendChild(nameEl);
      head.appendChild(checkWrap);

      // Middle: Badges
      const badges = document.createElement("div");
      badges.className = "logcat-item-badges";

      const lvlBadge = document.createElement("span");
      lvlBadge.className = "logcat-rule-badge";
      lvlBadge.textContent = rule.level ? `${rule.level}+` : "ALL";
      badges.appendChild(lvlBadge);

      if (rule.tag) {
        const tagEl = document.createElement("span");
        tagEl.className = "logcat-rule-tag";
        tagEl.textContent = `🏷 ${rule.tag}`;
        tagEl.title = `Tag: ${rule.tag}`;
        badges.appendChild(tagEl);
      }

      if (rule.text) {
        const textEl = document.createElement("span");
        textEl.className = "logcat-rule-text";
        textEl.textContent = `🔍 ${rule.text}`;
        textEl.title = `Pattern: ${rule.text}`;
        badges.appendChild(textEl);
      }

      if (rule.pid) {
        const pidEl = document.createElement("span");
        pidEl.className = "logcat-rule-pid";
        pidEl.textContent = `PID: ${rule.pid}`;
        badges.appendChild(pidEl);
      }
      head.appendChild(badges);

      // Right: Actions (Edit & Delete — locked rules: enable/disable only)
      const actions = document.createElement("div");
      actions.className = "logcat-item-actions";

      const isLocked = isLogcatRuleLocked(rule);

      const editBtn = document.createElement("button");
      editBtn.className = "btn btn-xs ghost";
      editBtn.textContent = isLocked ? "🔒 Locked" : "✎ Edit";
      editBtn.title = isLocked
        ? "Template rule: only enable/disable is allowed (edit & delete disabled)"
        : "Edit this filter rule";
      if (isLocked) {
        editBtn.disabled = true;
      } else {
        editBtn.addEventListener("click", () => {
          rule._editing = true;
          renderLogcatModalItems();
        });
      }

      if (!isLocked) {
        const delBtn = document.createElement("button");
        delBtn.className = "btn btn-xs danger ghost";
        delBtn.textContent = "🗑 Delete";
        delBtn.title = "Delete this filter rule";
        delBtn.addEventListener("click", () => {
          if (!confirm(`Delete filter rule '${rule.name}'?`)) return;
          _logcatRules = _logcatRules.filter(r => r.id !== rule.id);
          renderLogcatModalItems();
          updateLogcatFilterBadge();
          saveLogcatFilters(false);
          toast("Rule Deleted", `Removed '${rule.name}'.`, "info", 2000);
        });
        actions.appendChild(delBtn);
      }

      actions.appendChild(editBtn);
      head.appendChild(actions);

      card.appendChild(head);
      container.appendChild(card);
    }
  });
}

function openLogcatFiltersModal() {
  const modal = $("#modal-logcat-filters");
  if (!modal) return;

  // Ensure default item view mode
  $("#logcat-modal-items-container")?.classList.remove("hidden");
  $("#logcat-modal-raw-container")?.classList.add("hidden");
  const toggleBtn = $("#btn-logcat-modal-toggle-raw");
  if (toggleBtn) toggleBtn.textContent = "{} Raw JSON";

  _logcatRules.forEach(r => {
    delete r._editing;
    delete r._isNew;
  });

  renderLogcatModalItems();
  updateLogcatFilterBadge();
  modal.classList.remove("hidden");
}

function closeLogcatFiltersModal() {
  _logcatRules.forEach(r => {
    delete r._editing;
    delete r._isNew;
  });
  $("#modal-logcat-filters")?.classList.add("hidden");
}

function toggleLogcatModalRawView() {
  const itemsContainer = $("#logcat-modal-items-container");
  const rawContainer = $("#logcat-modal-raw-container");
  const textarea = $("#logcat-modal-raw-textarea");
  const toggleBtn = $("#btn-logcat-modal-toggle-raw");
  if (!itemsContainer || !rawContainer || !textarea) return;

  const isShowingRaw = !rawContainer.classList.contains("hidden");
  if (isShowingRaw) {
    // Switch from Raw JSON to Items
    try {
      const parsed = JSON.parse(textarea.value);
      if (!Array.isArray(parsed)) throw new Error("JSON must be an array of rule objects: [ { ... } ]");
      _logcatRules = parsed.map((r, i) => ({
        id: r.id || `rule-${Date.now()}-${i}`,
        name: r.name || `Rule ${i + 1}`,
        enabled: r.enabled ?? true,
        level: r.level || "I",
        tag: r.tag || "",
        text: r.text || "",
        pid: r.pid || "",
        locked: r.locked ?? false,
      }));
      rawContainer.classList.add("hidden");
      itemsContainer.classList.remove("hidden");
      if (toggleBtn) toggleBtn.textContent = "{} Raw JSON";
      renderLogcatModalItems();
      renderLogcat();
    } catch (err) {
      toast("Invalid JSON", err.message, "err", 4000);
    }
  } else {
    // Switch from Items to Raw JSON
    const cleanList = _logcatRules.map(stripRuleInternal);
    textarea.value = JSON.stringify(cleanList, null, 2);
    itemsContainer.classList.add("hidden");
    rawContainer.classList.remove("hidden");
    if (toggleBtn) toggleBtn.textContent = "📋 Item View";
    setTimeout(() => textarea.focus(), 30);
  }
}

// Debounce state for filter-rule persistence: toggling a checkbox triggers a
// POST + full re-render; rapid toggles (or many rules) would queue multiple
// heavy rebuilds and freeze the tab.
let _logcatSaveTimer = null;

async function saveLogcatFilters(notify = false) {
  // Rules changed: bump epoch first and re-render so logs already on screen
  // stay visible; only newly arriving lines follow the updated rules.
  _logcatRuleEpoch++;
  // Defer the heavy full rebuild to the next frame so the checkbox toggles
  // instantly instead of blocking on a 36k-line re-render.
  if (!_logcatRenderPending) {
    _logcatRenderPending = true;
    requestAnimationFrame(() => {
      _logcatRenderPending = false;
      renderLogcat();
    });
  }
  const cleanList = _logcatRules.map(stripRuleInternal);
  try {
    localStorage.setItem(LOGCAT_RULES_STORAGE_KEY, JSON.stringify(cleanList));
  } catch { /* ignore */ }
  // Debounce the network POST: coalesce bursts of toggles into one request.
  if (_logcatSaveTimer) clearTimeout(_logcatSaveTimer);
  if (notify) {
    // Explicit save (Save button / modal apply): flush immediately.
    await _postLogcatFilters(cleanList, true);
    return;
  }
  _logcatSaveTimer = setTimeout(async () => {
    _logcatSaveTimer = null;
    await _postLogcatFilters(_logcatRules.map(stripRuleInternal), false);
  }, 500);
}

async function _postLogcatFilters(cleanList, notify) {
  try {
    const res = await fetch("/api/logcat/filters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filters: cleanList }),
    });
    const data = await res.json();
    if (data.ok && notify) {
      const savedPath = data.path || "config/overlay/logcat_filters.json";
      toast("Filters Saved ✓", `Saved ${cleanList.length} rules to ${savedPath}${data.personal ? " (personal, git-ignored)" : ""}`, "ok", 3000);
    }
  } catch (err) {
    if (notify) toast("Save Failed", err.message, "err");
  }
}

async function saveLogcatModalAndApply() {
  const rawContainer = $("#logcat-modal-raw-container");
  const textarea = $("#logcat-modal-raw-textarea");
  if (rawContainer && !rawContainer.classList.contains("hidden") && textarea) {
    try {
      const parsed = JSON.parse(textarea.value);
      if (!Array.isArray(parsed)) throw new Error("JSON must be an array of rule objects: [ { ... } ]");
      _logcatRules = parsed.map((r, i) => ({
        id: r.id || `rule-${Date.now()}-${i}`,
        name: r.name || `Rule ${i + 1}`,
        enabled: r.enabled ?? true,
        level: r.level || "I",
        tag: r.tag || "",
        text: r.text || "",
        pid: r.pid || "",
        locked: r.locked ?? false,
      }));
    } catch (err) {
      toast("Invalid JSON", err.message, "err", 4000);
      return;
    }
  }

  closeLogcatFiltersModal();
  updateLogcatFilterBadge();
  renderLogcat();
  await saveLogcatFilters(true);
}

function addLogcatRuleItem() {
  // If in raw mode, switch back to items mode
  const rawContainer = $("#logcat-modal-raw-container");
  if (rawContainer && !rawContainer.classList.contains("hidden")) {
    toggleLogcatModalRawView();
  }

  const newRule = {
    id: `rule-${Date.now()}`,
    name: `Rule ${_logcatRules.length + 1}`,
    enabled: true,
    level: "I",
    tag: "",
    text: "",
    pid: "",
    locked: false,
    _editing: true,
    _isNew: true,
  };
  _logcatRules.unshift(newRule);
  renderLogcatModalItems();
}

function downloadLogcatFilters() {
  const cleanList = _logcatRules.map(stripRuleInternal);
  const jsonStr = JSON.stringify(cleanList, null, 2);
  const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "logcat_filters.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast("Filters Downloaded ✓", `Exported ${_logcatRules.length} rules as logcat_filters.json`, "ok", 2500);
}

function uploadLogcatFilters(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const parsed = JSON.parse(e.target.result);
      if (!Array.isArray(parsed)) {
        throw new Error("JSON file must be an array of rule objects: [ { ... } ]");
      }
      _logcatRules = parsed.map((r, i) => ({
        id: r.id || `rule-${Date.now()}-${i}`,
        name: r.name || `Rule ${i + 1}`,
        enabled: r.enabled ?? true,
        level: r.level || "I",
        tag: r.tag || "",
        text: r.text || "",
        pid: r.pid || "",
        locked: r.locked ?? false,
      }));
      renderLogcatModalItems();
      updateLogcatFilterBadge();
      renderLogcat();
      saveLogcatFilters(true);
      toast("Filters Uploaded ✓", `Imported ${_logcatRules.length} filter rules from ${file.name}.`, "ok", 3500);
    } catch (err) {
      toast("Upload Failed", err.message, "err", 4000);
    }
  };
  reader.readAsText(file);
}

// Save/restore the quick filter toolbar so a page refresh keeps whatever the
// user typed (message/regex, level, tag, PID). Best-effort: private mode or a
// full localStorage simply skips persistence.
function saveLogcatToolbarFilters() {
  try {
    localStorage.setItem(LOGCAT_TOOLBAR_KEY, JSON.stringify({
      text: $("#logcat-filter-text")?.value || "",
      level: $("#logcat-filter-level")?.value || "I",
      tag: $("#logcat-filter-tag")?.value || "",
      pid: $("#logcat-filter-pid")?.value || "",
    }));
  } catch { /* best-effort */ }
}

function restoreLogcatToolbarFilters() {
  try {
    const raw = localStorage.getItem(LOGCAT_TOOLBAR_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (!saved || typeof saved !== "object") return;
    const textInput = $("#logcat-filter-text");
    const levelSel = $("#logcat-filter-level");
    const tagInput = $("#logcat-filter-tag");
    const pidInput = $("#logcat-filter-pid");
    if (textInput && typeof saved.text === "string") textInput.value = saved.text;
    if (levelSel && saved.level && levelSel.querySelector(`option[value="${saved.level}"]`)) {
      levelSel.value = saved.level;
    }
    if (tagInput && typeof saved.tag === "string") tagInput.value = saved.tag;
    if (pidInput && typeof saved.pid === "string") pidInput.value = saved.pid;
  } catch { /* ignore corrupt saved data */ }
}

function initLogcat() {
  if (_logcatInitialized) return;
  _logcatInitialized = true;

  const screen = $("#logcat-screen");
  const scrollPill = $("#logcat-scroll-pill");
  const autoScrollChk = $("#logcat-autoscroll");

  // Restore previously typed filters BEFORE wiring listeners / first render
  restoreLogcatToolbarFilters();

  // Filtering listeners (also persist on every change)
  $("#logcat-filter-text")?.addEventListener("input", () => { saveLogcatToolbarFilters(); renderLogcat(); });
  $("#logcat-filter-level")?.addEventListener("change", () => { saveLogcatToolbarFilters(); renderLogcat(); });
  $("#logcat-filter-tag")?.addEventListener("input", () => { saveLogcatToolbarFilters(); renderLogcat(); });
  $("#logcat-filter-pid")?.addEventListener("input", () => { saveLogcatToolbarFilters(); renderLogcat(); });

  $("#btn-logcat-clear-text")?.addEventListener("click", () => {
    const textInput = $("#logcat-filter-text");
    if (textInput) {
      textInput.value = "";
      saveLogcatToolbarFilters();
      renderLogcat();
    }
  });

  // Action buttons
  $("#btn-logcat-toggle")?.addEventListener("click", () => {
    if (_logcatStreaming) {
      stopLogcatStream();
    } else {
      startLogcatStream();
    }
  });
  $("#btn-logcat-clear-view")?.addEventListener("click", clearLogcatView);
  $("#btn-logcat-clear-device")?.addEventListener("click", clearLogcatDevice);
  $("#btn-logcat-copy")?.addEventListener("click", copyLogcat);
  $("#btn-logcat-export")?.addEventListener("click", exportLogcat);

  // Filter Rules Button on main toolbar
  $("#btn-open-logcat-filters")?.addEventListener("click", openLogcatFiltersModal);

  // Filter Rules Modal buttons
  $("#btn-logcat-modal-add-item")?.addEventListener("click", addLogcatRuleItem);
  $("#btn-logcat-modal-toggle-raw")?.addEventListener("click", toggleLogcatModalRawView);
  $("#btn-logcat-modal-download")?.addEventListener("click", downloadLogcatFilters);
  $("#btn-logcat-modal-upload")?.addEventListener("click", () => $("#input-logcat-modal-upload-file")?.click());
  $("#input-logcat-modal-upload-file")?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      uploadLogcatFilters(e.target.files[0]);
      e.target.value = "";
    }
  });
  $("#btn-logcat-modal-close")?.addEventListener("click", closeLogcatFiltersModal);
  $("#btn-logcat-modal-save")?.addEventListener("click", saveLogcatModalAndApply);
  $("#btn-logcat-modal-format-json")?.addEventListener("click", () => {
    const ta = $("#logcat-modal-raw-textarea");
    if (!ta) return;
    try {
      const p = JSON.parse(ta.value);
      ta.value = JSON.stringify(p, null, 2);
    } catch (err) {
      toast("Invalid JSON", err.message, "err");
    }
  });

  // Load saved rules from server / local storage
  loadLogcatFilters();

  // Auto-scroll management
  autoScrollChk?.addEventListener("change", (e) => {
    _logcatAutoScroll = e.target.checked;
    if (_logcatAutoScroll && screen) {
      screen.scrollTop = screen.scrollHeight;
      scrollPill?.classList.add("hidden");
    }
  });

  screen?.addEventListener("scroll", () => {
    const distanceFromBottom = screen.scrollHeight - screen.scrollTop - screen.clientHeight;
    if (distanceFromBottom > 50) {
      if (_logcatAutoScroll) {
        _logcatAutoScroll = false;
        if (autoScrollChk) autoScrollChk.checked = false;
        scrollPill?.classList.remove("hidden");
      }
    } else {
      if (!_logcatAutoScroll) {
        _logcatAutoScroll = true;
        if (autoScrollChk) autoScrollChk.checked = true;
        scrollPill?.classList.add("hidden");
      }
    }
  });

  scrollPill?.addEventListener("click", () => {
    _logcatAutoScroll = true;
    if (autoScrollChk) autoScrollChk.checked = true;
    if (screen) screen.scrollTop = screen.scrollHeight;
    scrollPill.classList.add("hidden");
  });

  renderLogcat();
}

/* ---------------- Wiring ---------------- */
function switchTab(tab) {
  const isFiles = tab === "files";
  const isAosp = tab === "aosp";
  const isTerminal = tab === "terminal";
  const isLogcat = tab === "logcat";
  const isDocs = tab === "docs";
  const isBi = tab === "bi";
  const isPipelinesView = !isFiles && !isAosp && !isTerminal && !isLogcat && !isDocs && !isBi;

  // Collapse Config Files sidebar in Docs, AOSP, Terminal, Logcat & BI views to give maximum full-width canvas
  $(".layout")?.classList.toggle("no-sidebar", isDocs || isAosp || isTerminal || isLogcat || isBi);

  $("#view-files")?.classList.toggle("hidden", !isFiles);
  $("#view-aosp")?.classList.toggle("hidden", !isAosp);
  $("#view-pipelines")?.classList.toggle("hidden", !isPipelinesView);
  $("#view-terminal")?.classList.toggle("hidden", !isTerminal);
  $("#view-logcat")?.classList.toggle("hidden", !isLogcat);
  $("#view-docs")?.classList.toggle("hidden", !isDocs);
  $("#view-bi")?.classList.toggle("hidden", !isBi);
  if (tab === "system") {
    switchPipelineSource("system");
  } else if (tab === "pipelines" && (state.plSource === "system" || state.plSource === "docker")) {
    switchPipelineSource(_lastNonSystemPlSource || "my");
  }
  syncTopTabs();
  renderFiles($("#search")?.value || "");
  if (isBi) {
    initBIDashboard();
  }
  if (isLogcat) {
    initLogcat();
    renderLogcat();
    updateLogcatControls();
    const badge = $("#logcat-status-badge");
    if (badge) {
      if (_logcatStreaming) {
        badge.textContent = "Streaming";
        badge.className = "run-badge ok";
      } else {
        badge.textContent = "Idle";
        badge.className = "run-badge";
      }
    }
    if (_logcatAutoScroll) {
      const screen = $("#logcat-screen");
      if (screen) screen.scrollTop = screen.scrollHeight;
    }
    return;
  }
  if (isAosp) {
    loadAospConfig();
    return;
  }
  if (isTerminal) {
    setTimeout(() => $("#term-input")?.focus(), 40);
    return;
  }
  if (isDocs) {
    initQuill();
    applyDocsModeUI();
    if (_docsFiles.length === 0) {
      loadDocsFiles();
    }
    return;
  }
  // Files tab is lazy: open the draft file (or apk.config) on first visit.
  if (isFiles && !state.current) {
    const fileDraft = draftLoadFile();
    if (fileDraft && fileDraft.name && fileDraft.content != null &&
      state.files.some(f => f.name === fileDraft.name)) {
      openFile(fileDraft.name, fileDraft.content);
    } else if (state.files.some(f => f.name === "config/apk.config")) {
      openFile("config/apk.config");
    } else if (state.files.some(f => f.name === "apk.config")) {
      openFile("apk.config");
    }
  }
}

function initPipelineBottomPanel() {
  const chk = $("#chk-pl-output-dock");
  chk?.addEventListener("change", () => {
    setPipelineOutputMode(chk.checked ? "bottom" : "dialog");
  });
  setPipelineOutputMode(_plOutputMode);

  $("#btn-pl-bottom-stop")?.addEventListener("click", stopPipelineRun);
  $("#btn-pl-bottom-rerun")?.addEventListener("click", () => {
    if (_lastRunPipelineName) runPipeline(_lastRunPipelineName, _lastRunPipelineSource);
  });
  $("#btn-pl-bottom-copy")?.addEventListener("click", async () => {
    const text = $("#pl-bottom-output")?.innerText || "";
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied ✓", "Pipeline output copied to clipboard.", "ok", 2200);
    } catch (err) {
      toast("Copy Failed", err.message, "err");
    }
  });
  $("#btn-pl-bottom-clear")?.addEventListener("click", () => {
    const out = $("#pl-bottom-output");
    if (out) out.textContent = "Cleared.";
    const badge = $("#pl-bottom-status-badge");
    if (badge) {
      badge.textContent = "Ready";
      badge.className = "run-badge";
    }
  });
  $("#btn-pl-bottom-toggle-height")?.addEventListener("click", () => {
    $("#pl-bottom-panel")?.classList.toggle("maximized");
  });
  $("#btn-pl-bottom-close")?.addEventListener("click", () => {
    $("#pl-bottom-panel")?.classList.add("hidden");
  });

  // Resizer drag handler
  const resizer = $("#pl-bottom-resizer");
  const panel = $("#pl-bottom-panel");
  if (resizer && panel) {
    let startY = 0;
    let startH = 0;
    const onMouseMove = (e) => {
      const delta = startY - e.clientY;
      const newH = Math.max(100, Math.min(window.innerHeight * 0.75, startH + delta));
      panel.style.height = `${newH}px`;
      panel.classList.remove("maximized");
    };
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      resizer.classList.remove("dragging");
      try {
        localStorage.setItem("telua_pl_bottom_height", panel.style.height);
      } catch { /* ignore */ }
    };
    resizer.addEventListener("mousedown", (e) => {
      startY = e.clientY;
      startH = panel.getBoundingClientRect().height;
      resizer.classList.add("dragging");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    try {
      const savedH = localStorage.getItem("telua_pl_bottom_height");
      if (savedH) panel.style.height = savedH;
    } catch { /* ignore */ }
  }
}

function wire() {
  try { applyTheme(localStorage.getItem(THEME_KEY) || "dark"); } catch { applyTheme("dark"); }
  $("#theme-select")?.addEventListener("change", (e) => {
    const val = e.target.value;
    applyTheme(val);
    toast("Theme updated 🎨", `${THEME_LABELS[val] || val} — saved in browser.`, "info", 5000);
  });
  $("#search")?.addEventListener("input", (e) => renderFiles(e.target.value));
  $("#btn-refresh")?.addEventListener("click", () => { refreshStatus(); refreshFiles(); });
  $("#btn-edit")?.addEventListener("click", () => {
    if (!state.current || state.current.readonly) return;
    const wasEditing = state.fileEditing;
    setFileEditing(!state.fileEditing);
    setCurrentMeta();
    if (state.fileEditing) {
      $("#editor")?.focus();
    } else if (wasEditing && state.dirty) {
      toast("Unsaved changes 💾", "Finished editing — click '💾 Save' (or Ctrl+S) to save the file!", "warn", 5000);
    }
  });
  $("#btn-reload")?.addEventListener("click", () => state.current && openFile(state.current.name));
  $("#btn-save")?.addEventListener("click", saveFile);
  $("#btn-info")?.addEventListener("click", showInfo);
  $("#btn-unittest")?.addEventListener("click", () => runPipeline("unittest", "multi"));
  $("#btn-info-close")?.addEventListener("click", () => $("#modal-info")?.classList.add("hidden"));
  $("#btn-profile-close")?.addEventListener("click", () => $("#modal-profile")?.classList.add("hidden"));
  $("#btn-run-close")?.addEventListener("click", () => {
    cancelRunAutoClose();
    $("#modal-run")?.classList.add("hidden");
  });
  $("#btn-run-again")?.addEventListener("click", () => {
    if (_lastRunPipelineName) runPipeline(_lastRunPipelineName, _lastRunPipelineSource);
  });
  $("#btn-run-copy")?.addEventListener("click", async () => {
    const text = $("#run-output")?.innerText || "";
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied ✓", "Command output copied to clipboard.", "ok", 2200);
    } catch {
      toast("Copy failed", "Select text manually to copy.", "warn");
    }
  });
  $("#btn-crypto-close")?.addEventListener("click", () => $("#modal-crypto")?.classList.add("hidden"));
  $("#btn-confirm-cancel")?.addEventListener("click", () => resolveConfirm(false));
  $("#btn-confirm-ok")?.addEventListener("click", () => resolveConfirm(true));

  // Crypto & Overlay actions
  $("#chip-crypto")?.addEventListener("click", () => openCryptoModal("all"));
  if ($("#chip-crypto")) $("#chip-crypto").style.cursor = "pointer";
  $("#btn-pl-crypto")?.addEventListener("click", () => openCryptoModal("const_my_cli.config"));
  $("#btn-file-crypto")?.addEventListener("click", () => {
    const cur = state.current?.name || "";
    const defTarget = cur.endsWith("apk_overlays.config")
      ? "apk_overlays.config"
      : cur.endsWith("const_my_cli.config") ? "const_my_cli.config" : "all";
    openCryptoModal(defTarget);
  });
  $("#crypto-target")?.addEventListener("change", updateCryptoButtons);
  $("#btn-crypto-encrypt")?.addEventListener("click", () => runCryptoAction("encrypt", false));
  $("#btn-crypto-decrypt")?.addEventListener("click", () => runCryptoAction("decrypt", false));
  $("#btn-crypto-decrypt-force")?.addEventListener("click", () => runCryptoAction("decrypt", true));

  // Tab switching
  $("#tab-files")?.addEventListener("click", () => switchTab("files"));
  $("#tab-pipelines")?.addEventListener("click", () => { switchTab("pipelines"); renderFiles($("#search")?.value || ""); });
  $("#tab-system")?.addEventListener("click", () => { switchTab("system"); renderFiles($("#search")?.value || ""); });
  $("#tab-aosp")?.addEventListener("click", () => switchTab("aosp"));
  $("#tab-terminal")?.addEventListener("click", () => { switchTab("terminal"); renderFiles($("#search")?.value || ""); });
  $("#tab-logcat")?.addEventListener("click", () => switchTab("logcat"));
  $("#tab-docs")?.addEventListener("click", () => switchTab("docs"));
  $("#tab-bi")?.addEventListener("click", () => switchTab("bi"));

  // AOSP Center wiring
  $("#btn-aosp-reload")?.addEventListener("click", () => loadAospConfig());
  $("#btn-aosp-open-dialog")?.addEventListener("click", () => openAospConfigModal());
  $("#btn-aosp-edit-dialog")?.addEventListener("click", () => openAospConfigModal());
  $("#btn-aosp-modal-cancel")?.addEventListener("click", () => closeAospConfigModal());
  $("#btn-aosp-modal-save")?.addEventListener("click", () => saveAospConfigFromModal());
  $("#upload-apk-overlays")?.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) uploadOverlayFile(f, "apk_overlays.config");
    e.target.value = "";
  });
  $("#upload-const-my-cli")?.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) uploadOverlayFile(f, "const_my_cli.config");
    e.target.value = "";
  });
  $("#modal-aosp-config")?.addEventListener("click", (e) => {
    if (e.target === $("#modal-aosp-config")) closeAospConfigModal();
  });
  $("#aosp-project-select")?.addEventListener("change", (e) => quickSwitchAospProject(e.target.value));
  ["#aosp-modal-root-input", "#aosp-modal-target-product", "#aosp-modal-target-variant"].forEach(sel => {
    $(sel)?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        saveAospConfigFromModal();
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeAospConfigModal();
      }
    });
  });
  $("#btn-aosp-clear")?.addEventListener("click", () => { if ($("#aosp-output")) $("#aosp-output").innerHTML = ""; });
  $("#btn-aosp-copy")?.addEventListener("click", () => {
    try {
      navigator.clipboard.writeText($("#aosp-output")?.textContent || "");
      toast("Copied ✓", "AOSP console output copied to clipboard.", "ok", 2200);
    } catch {
      toast("Copy failed", "Select text manually to copy.", "warn");
    }
  });
  $("#btn-aosp-stop")?.addEventListener("click", () => stopAospCommand());
  // Upload APK: pick file -> validate name vs OUTPUT_FILE_NAME -> push + restart
  $("#btn-aosp-upload-apk")?.addEventListener("click", () => $("#aosp-apk-file-input")?.click());
  $("#aosp-apk-file-input")?.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) uploadAospApk(f);
    e.target.value = "";
  });
  document.querySelectorAll(".aosp-action-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const cmd = btn.dataset.cmd;
      if (cmd) runAospCommand(cmd, btn);
    });
  });
  document.querySelectorAll(".aosp-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const cmd = chip.dataset.cmd;
      if (cmd) runAospCommand(cmd, chip);
    });
  });

  // Sphinx Docs wiring
  $("#docs-file-select")?.addEventListener("change", (e) => loadDocFile(e.target.value));
  $("#btn-docs-mode-wysiwyg")?.addEventListener("click", () => switchToEditorType("wysiwyg"));
  $("#btn-docs-mode-raw")?.addEventListener("click", () => switchToEditorType("raw"));
  $("#btn-docs-mode-split")?.addEventListener("click", () => toggleDocsSplit());
  $("#btn-docs-sync-scroll")?.addEventListener("click", () => {
    _docsSyncScroll = !_docsSyncScroll;
    try {
      localStorage.setItem("telua_web_docs_sync_scroll", String(_docsSyncScroll));
    } catch (e) { }
    updateSyncScrollButtonUI();
    if (_docsSyncScroll) {
      const ed = getActiveDocsEditorElement();
      const prev = $("#docs-preview-content");
      if (ed && prev) syncScroll(ed, prev);
    }
  });
  // Diagram Dropdown Menu Wiring (Mermaid & PlantUML)
  const btnMermaid = $("#btn-docs-add-mermaid");
  const menuMermaid = $("#menu-docs-mermaid");
  const wrapMermaid = $("#wrap-docs-mermaid");

  const btnPlantuml = $("#btn-docs-add-plantuml");
  const menuPlantuml = $("#menu-docs-plantuml");
  const wrapPlantuml = $("#wrap-docs-plantuml");

  function closeAllDiagramMenus() {
    menuMermaid?.classList.remove("show");
    wrapMermaid?.classList.remove("open");
    menuPlantuml?.classList.remove("show");
    wrapPlantuml?.classList.remove("open");
  }

  btnMermaid?.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = menuMermaid?.classList.contains("show");
    closeAllDiagramMenus();
    if (!isOpen) {
      menuMermaid?.classList.add("show");
      wrapMermaid?.classList.add("open");
    }
  });

  menuMermaid?.querySelectorAll(".dropdown-item")?.forEach(item => {
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      const type = item.getAttribute("data-type") || "flowchart";
      closeAllDiagramMenus();
      insertMermaidDiagram(type);
    });
  });

  // JSON → Chart modal wiring (one-time)
  wireJsonChartModal();

  btnPlantuml?.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = menuPlantuml?.classList.contains("show");
    closeAllDiagramMenus();
    if (!isOpen) {
      menuPlantuml?.classList.add("show");
      wrapPlantuml?.classList.add("open");
    }
  });

  menuPlantuml?.querySelectorAll(".dropdown-item")?.forEach(item => {
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      const type = item.getAttribute("data-type") || "sequence";
      closeAllDiagramMenus();
      insertPlantumlDiagram(type);
    });
  });

  document.addEventListener("click", () => {
    closeAllDiagramMenus();
  });

  $("#btn-docs-add-table")?.addEventListener("click", () => insertTableBlock());
  $("#btn-docs-save")?.addEventListener("click", () => saveCurrentDoc());
  $("#btn-docs-build")?.addEventListener("click", () => buildSphinxDocs());
  $("#btn-docs-start")?.addEventListener("click", () => startSphinxDocs());
  $("#docs-raw-rst")?.addEventListener("input", () => {
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
  });

  const docsWs = $("#docs-workspace");
  if (docsWs) {
    docsWs.addEventListener("dragover", (e) => {
      e.preventDefault();
      docsWs.classList.add("drag-over");
    });
    docsWs.addEventListener("dragleave", (e) => {
      e.preventDefault();
      docsWs.classList.remove("drag-over");
    });
    docsWs.addEventListener("drop", (e) => {
      e.preventDefault();
      docsWs.classList.remove("drag-over");
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) handleDocsFileUpload(file);
    });
  }

  function saveRecentDocsDir(dir) {
    if (!dir) return;
    try {
      let recent = JSON.parse(localStorage.getItem("telua_web_docs_recent_dirs") || "[]");
      recent = [dir, ...recent.filter(d => d !== dir)].slice(0, 6);
      localStorage.setItem("telua_web_docs_recent_dirs", JSON.stringify(recent));
    } catch { /* ignore */ }
  }

  function renderRecentDocsChips() {
    const container = $("#docs-recent-dirs-container");
    const listEl = $("#docs-recent-dirs-list");
    if (!container || !listEl) return;
    try {
      const recent = JSON.parse(localStorage.getItem("telua_web_docs_recent_dirs") || "[]");
      if (!recent || !recent.length) {
        container.style.display = "none";
        return;
      }
      container.style.display = "block";
      listEl.innerHTML = "";
      recent.forEach(dir => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "term-chip btn-docs-dir-chip";
        btn.dataset.dir = dir;
        btn.textContent = dir;
        btn.addEventListener("click", () => {
          const input = $("#input-docs-dir");
          if (input) input.value = dir;
        });
        listEl.appendChild(btn);
      });
    } catch { /* ignore */ }
  }

  // Change Docs Root Directory Modal wiring
  $("#docs-active-dir-badge")?.addEventListener("click", () => {
    $("#btn-docs-change-dir")?.click();
  });
  $("#btn-docs-change-dir")?.addEventListener("click", () => {
    const modal = $("#modal-docs-dir");
    const input = $("#input-docs-dir");
    const activeDir = _docsCustomDir || _docsActiveDir || localStorage.getItem("telua_web_docs_dir") || "";
    if (input) input.value = activeDir;
    renderRecentDocsChips();
    modal?.classList.remove("hidden");
    setTimeout(() => input?.focus(), 40);
  });
  $("#btn-docs-dir-cancel")?.addEventListener("click", () => {
    $("#modal-docs-dir")?.classList.add("hidden");
  });
  $("#btn-docs-dir-apply")?.addEventListener("click", () => {
    const input = $("#input-docs-dir");
    const val = input ? input.value.trim() : "";
    _docsCustomDir = val;
    try {
      if (val) {
        localStorage.setItem("telua_web_docs_dir", _docsCustomDir);
        saveRecentDocsDir(_docsCustomDir);
      } else {
        localStorage.removeItem("telua_web_docs_dir");
      }
    } catch { /* ignore */ }
    $("#modal-docs-dir")?.classList.add("hidden");
    loadDocsFiles(_docsCustomDir);
    toast("Docs Root Updated 📁", val ? `Scanning: ${val}` : "Restored to default docs & templates.", "info", 3500);
  });
  document.querySelectorAll(".btn-docs-dir-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const dir = chip.dataset.dir || "";
      const input = $("#input-docs-dir");
      if (input) input.value = dir;
    });
  });

  // Terminal wiring
  $("#btn-term-run")?.addEventListener("click", () => runTerminalCommand());
  $("#btn-term-stop")?.addEventListener("click", () => stopTerminalCommand());
  $("#btn-term-new-session")?.addEventListener("click", () => newTerminalSession());
  $("#btn-run-stop")?.addEventListener("click", () => stopPipelineRun());
  // Reset the auto-close countdown whenever the user interacts with the run
  // dialog (mouse move, click, scroll, key press, touch) so the modal only
  // closes 10s after the user STOPS interacting with it.
  const runModalEl = $("#modal-run");
  if (runModalEl) {
    ["mousemove", "mousedown", "click", "wheel", "keydown", "touchstart"].forEach(evt => {
      runModalEl.addEventListener(evt, markRunActivity, { passive: true });
    });
  }
  $("#btn-term-clear")?.addEventListener("click", clearTerminalOutput);
  $("#btn-term-copy")?.addEventListener("click", async () => {
    const text = $("#term-output")?.innerText || "";
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied ✓", "Terminal output copied to clipboard.", "ok", 2200);
    } catch {
      toast("Copy failed", "Select text manually to copy.", "warn");
    }
  });
  $("#term-input")?.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "c" && _termRunning) {
      const hasSel = e.target.selectionStart !== e.target.selectionEnd;
      if (!hasSel) {
        e.preventDefault();
        stopTerminalCommand();
        return;
      }
    }
    if (e.key === "Enter") {
      e.preventDefault();
      runTerminalCommand();
    } else if (e.key === "ArrowUp") {
      if (_termHistory.length === 0) return;
      e.preventDefault();
      if (_termHistoryIdx > 0) _termHistoryIdx--;
      else _termHistoryIdx = 0;
      e.target.value = _termHistory[_termHistoryIdx] || "";
    } else if (e.key === "ArrowDown") {
      if (_termHistory.length === 0) return;
      e.preventDefault();
      if (_termHistoryIdx < _termHistory.length - 1) {
        _termHistoryIdx++;
        e.target.value = _termHistory[_termHistoryIdx] || "";
      } else {
        _termHistoryIdx = _termHistory.length;
        e.target.value = "";
      }
    }
  });
  document.querySelectorAll("#term-quick-bar .term-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const cmd = chip.dataset.cmd || "";
      if ($("#term-input")) $("#term-input").value = cmd;
      runTerminalCommand(cmd);
    });
  });
  $("#btn-pl-raw")?.addEventListener("click", () => {
    const currentPlFile = $("#pl-file")?.textContent;
    if (currentPlFile && currentPlFile !== "—") openFile(currentPlFile);
  });
  $("#pl-filter")?.addEventListener("input", () => renderPipelines());
  $("#btn-pl-refresh")?.addEventListener("click", () => loadPipelines(draftLoadPipelines()));
  $("#btn-pl-add")?.addEventListener("click", addPipeline);
  $("#btn-pl-save")?.addEventListener("click", savePipelines);

  // Pipeline source switch (my <-> multi)
  document.querySelectorAll("#pl-source-switch .src-btn").forEach(btn =>
    btn.addEventListener("click", () => switchPipelineSource(btn.dataset.source)));

  // Pipeline / System output destination (Bottom Docked Console vs Dialog)
  initPipelineBottomPanel();

  // Click on the project chip opens the profile switcher
  $("#chip-project")?.addEventListener("click", openProfileModal);
  if ($("#chip-project")) {
    $("#chip-project").style.cursor = "pointer";
    $("#chip-project").title = "Click to switch ACTIVE_PROJECT";
  }

  // Click on the draft chip discards the browser draft (keeps server files intact)
  $("#chip-draft")?.addEventListener("click", async () => {
    const ok = await confirmDialog({
      title: "Discard Unsaved Draft?",
      message: "Are you sure you want to discard unsaved browser edits and restore the original file content from disk?",
      detail: "",
      hint: "💡 Config files on disk are not modified.",
      confirmText: "↺ Restore Original",
      icon: "↺",
    });
    if (!ok) return;
    draftClearFile();
    draftClearPipelines();
    state.dirty = false;
    state.plDirty = false;
    $("#editor-dirty")?.classList.add("hidden");
    $("#pl-dirty")?.classList.add("hidden");
    if ($("#btn-save")) $("#btn-save").disabled = true;
    if ($("#btn-pl-save")) $("#btn-pl-save").disabled = true;
    if (state.current) openFile(state.current.name);
    loadPipelines();
    updateDraftChip();
    toast("Original restored", "Unsaved draft changes have been discarded.", "info", 5000);
  });
  if ($("#chip-draft")) $("#chip-draft").style.cursor = "pointer";

  $("#editor")?.addEventListener("input", () => { setDirty(true); updateStats(); });

  // Ctrl+S / Cmd+S to save (works in both tabs); Ctrl+C to stop running Terminal command
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "c" && _termRunning && !$("#view-terminal")?.classList.contains("hidden")) {
      const sel = window.getSelection ? String(window.getSelection()) : "";
      if (!sel) {
        e.preventDefault();
        stopTerminalCommand();
        return;
      }
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (!$("#view-pipelines")?.classList.contains("hidden")) {
        if (state.plDirty) savePipelines();
      } else if (state.dirty && state.current && !state.current.readonly) {
        saveFile();
      }
    }
    if (e.key === "Escape") {
      if (_confirmResolver) {
        resolveConfirm(false);
        return;
      }
      $("#modal-profile")?.classList.add("hidden");
      $("#modal-info")?.classList.add("hidden");
      if ($("#modal-run") && !$("#modal-run").classList.contains("hidden")) cancelRunAutoClose();
      $("#modal-run")?.classList.add("hidden");
      $("#modal-crypto")?.classList.add("hidden");
    }
  });

  // Warn before leaving with unsaved changes
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty || state.plDirty) { e.preventDefault(); e.returnValue = ""; }
  });
}

/* ==============================================================================
   Power BI Studio & Excel Interactive Dashboard Engine
   ============================================================================== */

const biState = {
  filename: "",
  sheets: [],
  activeSheet: "",
  allSheets: {},
  columns: [],
  rawData: [],
  filteredData: [],
  activeSlicers: {}, // { colName: Set of selected string values }
  searchQuery: "",
  visuals: [],
  selectedField: null,
  isInitialized: false,
  tooltipEl: null,
};

const BI_PALETTES = [
  "#1ea7fd", "#3fb950", "#f85149", "#a371f7", "#e3b341", "#38bdf8",
  "#f472b6", "#2dd4bf", "#fb923c", "#818cf8", "#4ade80", "#facc15"
];

function biFormatNumber(num) {
  if (num === null || num === undefined || isNaN(num)) return "0";
  const abs = Math.abs(num);
  if (abs >= 1e9) return (num / 1e9).toFixed(1) + "B";
  if (abs >= 1e6) return (num / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (num / 1e3).toFixed(1) + "k";
  return Number.isInteger(num) ? num.toLocaleString() : num.toFixed(2);
}

function initBIDashboard() {
  if (biState.isInitialized) return;
  biState.isInitialized = true;

  // Tooltip DOM element
  if (!biState.tooltipEl) {
    let tip = $("#bi-chart-tooltip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "bi-chart-tooltip";
      tip.className = "bi-chart-tooltip";
      document.body.appendChild(tip);
    }
    biState.tooltipEl = tip;
  }

  // Upload handlers
  const onFileSelected = (e) => {
    const file = e.target.files?.[0];
    if (file) biUploadFile(file);
    e.target.value = "";
  };
  $("#bi-file-input")?.addEventListener("change", onFileSelected);
  $("#bi-file-input-hero")?.addEventListener("change", onFileSelected);

  // Drag & drop support
  const dropzone = $("#bi-empty-dropzone");
  const container = $("#bi-canvas-container");
  [dropzone, container].forEach((el) => {
    if (!el) return;
    el.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone?.classList.add("dragover");
    });
    el.addEventListener("dragleave", (e) => {
      if (!el.contains(e.relatedTarget)) dropzone?.classList.remove("dragover");
    });
    el.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone?.classList.remove("dragover");
      const file = e.dataTransfer?.files?.[0];
      if (file) biUploadFile(file);
    });
  });

  // Sample dataset dropdown
  $("#bi-sample-select")?.addEventListener("change", (e) => {
    const key = e.target.value;
    if (key) biLoadSample(key);
  });

  // Sheet switcher
  $("#bi-sheet-select")?.addEventListener("change", (e) => {
    const sheet = e.target.value;
    if (sheet && biState.allSheets[sheet]) {
      biSwitchSheet(sheet);
    }
  });

  // Search input
  $("#bi-search-input")?.addEventListener("input", (e) => {
    biState.searchQuery = (e.target.value || "").trim().toLowerCase();
    biApplyFilters();
  });

  // Fields filter search
  $("#bi-fields-search")?.addEventListener("input", (e) => {
    biRenderFieldsList(e.target.value || "");
  });

  // Toggle fields pane
  $("#btn-bi-fields-toggle")?.addEventListener("click", () => {
    const pane = $("#bi-fields-pane");
    if (pane) {
      pane.classList.toggle("collapsed");
      const isCollapsed = pane.classList.contains("collapsed");
      $("#btn-bi-fields-toggle").textContent = isCollapsed ? "▶" : "◀";
    }
  });

  // Reset filters
  $("#btn-bi-reset-filters")?.addEventListener("click", () => {
    biState.activeSlicers = {};
    biState.searchQuery = "";
    if ($("#bi-search-input")) $("#bi-search-input").value = "";
    biApplyFilters();
    toast("Filters reset", "All Power BI slicers and filters cleared.", "info", 2000);
  });

  // Paste table modal handlers
  const openPasteModal = () => {
    const modal = $("#modal-bi-paste");
    if (modal) {
      if (!$("#bi-paste-name")?.value) {
        $("#bi-paste-name").value = "vehicle_fleet_market.csv";
      }
      modal.classList.remove("hidden");
      $("#bi-paste-input")?.focus();
    }
  };
  $("#btn-bi-paste-open")?.addEventListener("click", openPasteModal);
  $("#btn-bi-paste-hero")?.addEventListener("click", openPasteModal);
  $("#btn-bi-paste-cancel")?.addEventListener("click", () => $("#modal-bi-paste")?.classList.add("hidden"));
  $("#btn-bi-paste-submit")?.addEventListener("click", () => biSubmitPaste());

  // Cross-Tab Report modal handlers
  $("#btn-bi-cross-report")?.addEventListener("click", () => biOpenCrossTabReport());
  $("#btn-bi-report-close")?.addEventListener("click", () => $("#modal-bi-cross-report")?.classList.add("hidden"));
  $("#btn-bi-report-copy-md")?.addEventListener("click", () => {
    if (biState._lastCrossReport?.markdown_report) {
      navigator.clipboard.writeText(biState._lastCrossReport.markdown_report).then(() => {
        toast("Report Copied", "Markdown report copied to clipboard.", "ok", 2500);
      });
    }
  });
  $("#btn-bi-report-to-docs")?.addEventListener("click", async () => {
    if (!biState._lastCrossReport?.rst_report) return;
    toast("Saving to Docs…", "Writing report to docs/cross_sheet_report.rst…", "info", 2000);
    try {
      const res = await fetch("/api/bi/save-doc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "docs/cross_sheet_report.rst",
          content: biState._lastCrossReport.rst_report,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Failed to save doc");
      $("#modal-bi-cross-report")?.classList.add("hidden");
      toast("Saved to Docs", "Report saved to docs/cross_sheet_report.rst. Switching to Docs…", "ok", 3000);
      switchTab("docs");
      refreshDocsFiles("docs/cross_sheet_report.rst");
    } catch (err) {
      toast("Save Error", err.message, "err", 5000);
    }
  });

  // Export filtered Excel
  $("#btn-bi-export-excel")?.addEventListener("click", () => biExportExcel());

  // JSON viewer modal
  $("#btn-bi-view-json")?.addEventListener("click", () => biOpenJsonModal());
  $("#btn-bi-json-close")?.addEventListener("click", () => $("#modal-bi-json")?.classList.add("hidden"));
  $("#btn-bi-json-copy")?.addEventListener("click", () => {
    const content = $("#bi-json-viewer-content")?.textContent || "";
    navigator.clipboard.writeText(content).then(() => {
      toast("JSON Copied", "Dataset JSON copied to clipboard.", "ok", 2500);
    });
  });
  $("#btn-bi-json-download")?.addEventListener("click", () => {
    const content = $("#bi-json-viewer-content")?.textContent || "";
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (biState.filename ? biState.filename.replace(/\.[^/.]+$/, "") : "dataset") + ".json";
    a.click();
    URL.revokeObjectURL(url);
    toast("JSON Downloaded", "JSON file saved to Downloads.", "ok", 2500);
  });
  $("#btn-bi-json-to-mermaid")?.addEventListener("click", () => {
    $("#modal-bi-json")?.classList.add("hidden");
    switchTab("docs");
    openJsonChartModal();
    const input = $("#json-chart-input");
    if (input && biState.filteredData.length) {
      // Pick top numerical and categorical column for auto mermaid sample
      const numCols = biState.columns.filter((c) => c.type === "number");
      const strCols = biState.columns.filter((c) => c.type !== "number");
      if (strCols.length && numCols.length) {
        const xCol = strCols[0].name;
        const yCol = numCols[0].name;
        const sampleRecords = biState.filteredData.slice(0, 8);
        const jsonPayload = {
          x: sampleRecords.map((r) => String(r[xCol] || "—")),
          y: sampleRecords.map((r) => Number(r[yCol]) || 0),
        };
        input.value = JSON.stringify(jsonPayload, null, 2);
      }
    }
  });

  // Visual Builder modal
  $("#btn-bi-add-visual")?.addEventListener("click", () => biOpenAddVisualModal());
  $("#btn-bi-visual-cancel")?.addEventListener("click", () => $("#modal-bi-add-visual")?.classList.add("hidden"));
  $("#btn-bi-visual-save")?.addEventListener("click", () => biSaveNewVisual());

  // Calculated Column / Measure modal (Mini-DAX)
  $("#btn-bi-calc-col-open")?.addEventListener("click", () => biOpenCalcColModal());
  $("#btn-bi-calc-col-fields")?.addEventListener("click", () => biOpenCalcColModal());
  $("#btn-bi-calc-cancel")?.addEventListener("click", () => $("#modal-bi-calc-col")?.classList.add("hidden"));
  $("#btn-bi-calc-submit")?.addEventListener("click", () => biCreateCalculatedColumn());

  // Visual type chip picker in modal
  document.querySelectorAll("#bi-visual-type-select .term-chip").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll("#bi-visual-type-select .term-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const vtype = btn.dataset.vtype;
      const y2Group = $("#bi-visual-y2-group");
      if (y2Group) y2Group.style.display = vtype === "combo" ? "block" : "none";
    });
  });

  // Dynamically load available datasets from bi_studio directory
  biFetchAvailableDatasets();
}

async function biFetchAvailableDatasets() {
  const sel = $("#bi-sample-select");
  if (!sel) return;
  try {
    const res = await fetch("/api/bi/samples");
    const data = await res.json();
    if (!res.ok || !data.ok) return;

    // Reset dropdown to only placeholder
    sel.innerHTML = '<option value="">📁 Select Excel Dataset…</option>';

    const samples = data.samples || [];
    samples.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = `ws:${s.filename}`;
      const cleanTitle = s.title.replace(/\.[^/.]+$/, "").replace(/_/g, " ");
      const sheetsCount = s.sheets_count || 1;
      const rowsCount = s.rows_count || 0;
      opt.textContent = `📊 ${cleanTitle} (${sheetsCount} Sheets · ${rowsCount} Rows)`;
      sel.appendChild(opt);
    });

    // Auto-load first dataset if none is loaded yet
    if ((!biState.rawData || biState.rawData.length === 0) && samples.length > 0) {
      biLoadSample(`ws:${samples[0].filename}`);
    }
  } catch (err) {
    console.warn("Failed to fetch available datasets from bi_studio:", err);
  }
}

async function biUploadFile(file) {
  const form = new FormData();
  form.append("file", file);

  toast("Converting Excel…", `Uploading & parsing '${file.name}' into JSON…`, "info", 3000);

  try {
    const res = await fetch("/api/bi/convert", {
      method: "POST",
      body: form,
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.description || "Upload failed");
    }
    toast("Excel Converted", `Successfully converted '${file.name}' (${data.rows_count} records).`, "ok", 3500);
    biSetDataset(data);
  } catch (err) {
    toast("Conversion Error", err.message, "err", 6000);
  }
}

async function biSubmitPaste() {
  const text = $("#bi-paste-input")?.value || "";
  const name = $("#bi-paste-name")?.value.trim() || "pasted_data.csv";

  if (!text.trim()) {
    toast("Empty Input", "Please paste CSV or tab-separated text first.", "warn", 3000);
    return;
  }

  toast("Parsing Table Data…", "Converting table text into structured JSON…", "info", 2000);

  try {
    const res = await fetch("/api/bi/paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, filename: name }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.description || "Failed to parse pasted data");
    }
    $("#modal-bi-paste")?.classList.add("hidden");
    toast("Table Converted", `Loaded ${data.rows_count} rows across ${data.sheets.length} sheet(s).`, "ok", 3500);
    biSetDataset(data);
  } catch (err) {
    toast("Parse Error", err.message, "err", 6000);
  }
}

async function biOpenCrossTabReport() {
  const modal = $("#modal-bi-cross-report");
  const body = $("#bi-cross-report-body");
  if (!modal || !body) return;

  toast("Generating Report…", "Analyzing relationships and cross-sheet metrics…", "info", 2000);

  try {
    const res = await fetch("/api/bi/cross-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        all_sheets: biState.allSheets,
        filename: biState.filename,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Failed to generate cross report");

    biState._lastCrossReport = data;
    $("#bi-report-sheets-badge").textContent = `${data.total_sheets} Tabs Analyzed · ${data.total_records.toLocaleString()} Records`;

    let html = `
      <div class="bi-kpi-row" style="margin-bottom:10px;">
        <div class="bi-kpi-card" style="border-top-color:#1ea7fd;">
          <div class="bi-kpi-label">Analyzed Worksheets</div>
          <div class="bi-kpi-val">${data.total_sheets}</div>
          <div class="bi-kpi-sub">${data.filename}</div>
        </div>
        <div class="bi-kpi-card" style="border-top-color:#3fb950;">
          <div class="bi-kpi-label">Total Combined Records</div>
          <div class="bi-kpi-val">${data.total_records.toLocaleString()}</div>
          <div class="bi-kpi-sub">Across all related tabs</div>
        </div>
        <div class="bi-kpi-card" style="border-top-color:#a371f7;">
          <div class="bi-kpi-label">Shared Common Keys</div>
          <div class="bi-kpi-val">${data.shared_keys.length}</div>
          <div class="bi-kpi-sub">${data.shared_keys.slice(0, 3).join(", ") || "No shared keys"}</div>
        </div>
      </div>

      <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
        <h4 style="margin:0 0 8px 0;font-size:13px;color:var(--accent);">📊 Cross-Tab Comparison Matrix</h4>
        <div class="bi-table-wrap">
          <table class="bi-table">
            <thead>
              <tr>
                <th>Tab Name</th>
                <th>Records</th>
                <th>Columns</th>
                <th>Primary Measure</th>
                <th>Total Value</th>
                <th>Top Categories</th>
              </tr>
            </thead>
            <tbody>
              ${data.matrix.map((m) => `
                <tr>
                  <td><b>${m.sheet_name}</b></td>
                  <td>${m.rows_count.toLocaleString()}</td>
                  <td>${m.columns_count}</td>
                  <td>${m.primary_metric || "—"}</td>
                  <td><b>${m.primary_sum ? biFormatNumber(m.primary_sum) : "—"}</b></td>
                  <td><span class="meta">${m.top_categories.join(", ") || "—"}</span></td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>

      <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
        <h4 style="margin:0 0 6px 0;font-size:13px;color:var(--accent);">🔗 Common Dimensions &amp; Relational Keys</h4>
        <p class="meta" style="margin:0 0 8px 0;">The following keys link records across multiple worksheets:</p>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${data.shared_keys.map((k) => `<span class="chip" style="font-size:11px;">🔑 ${k}</span>`).join("")}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
          <h4 style="margin:0 0 6px 0;font-size:12px;">🥧 Record Share by Tab</h4>
          <pre class="mono" style="background:var(--bg-soft,#1e1e2e);padding:8px;font-size:10.5px;border-radius:6px;max-height:160px;overflow:auto;">${data.mermaid_pie}</pre>
        </div>
        <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
          <h4 style="margin:0 0 6px 0;font-size:12px;">📶 Grouped Comparison (xychart)</h4>
          <pre class="mono" style="background:var(--bg-soft,#1e1e2e);padding:8px;font-size:10.5px;border-radius:6px;max-height:160px;overflow:auto;">${data.mermaid_bar}</pre>
        </div>
      </div>
    `;

    body.innerHTML = html;
    modal.classList.remove("hidden");
  } catch (err) {
    toast("Report Error", err.message, "err", 5000);
  }
}

async function biLoadSample(key) {
  if (key.startsWith("ws:")) {
    const relPath = key.slice(3);
    toast("Loading Workspace File…", `Parsing '${relPath}' directly from workspace…`, "info", 2000);
    try {
      const res = await fetch("/api/bi/load-workspace-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: relPath }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || data.description || "Failed to load workspace file");
      }
      toast("Workspace File Loaded", `Loaded '${relPath}' (${data.rows_count} rows, ${data.sheets.length} sheets).`, "ok", 3500);
      biSetDataset(data);
    } catch (err) {
      toast("Load Error", err.message, "err", 6000);
    }
    return;
  }

  toast("Loading Sample…", `Fetching sample dataset '${key}'…`, "info", 2000);
  try {
    const res = await fetch(`/api/bi/samples?key=${encodeURIComponent(key)}`);
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Failed to load sample dataset");
    }
    toast("Sample Loaded", `Loaded '${data.title}' (${data.rows_count} rows).`, "ok", 3000);
    biSetDataset(data);
  } catch (err) {
    toast("Load Error", err.message, "err", 5000);
  }
}

function biSetDataset(payload) {
  biState.filename = payload.filename || "dataset.xlsx";
  biState.sheets = payload.sheets || ["Sheet1"];
  biState.activeSheet = payload.active_sheet || biState.sheets[0] || "Sheet1";
  biState.allSheets = payload.all_sheets || {};
  biState.columns = payload.columns || [];
  biState.rawData = payload.data || [];
  biState.filteredData = [...biState.rawData];
  biState.activeSlicers = {};
  biState.searchQuery = "";
  biState.selectedField = null;

  // Update UI header
  const badge = $("#bi-active-file-badge");
  if (badge) {
    badge.textContent = `${biState.filename} (${biState.rawData.length} rows)`;
    badge.title = `Active worksheet: ${biState.activeSheet}`;
  }

  // Update sheets dropdown & tabs bar
  const sheetSelect = $("#bi-sheet-select");
  if (sheetSelect) {
    if (biState.sheets.length > 1) {
      sheetSelect.classList.remove("hidden");
      sheetSelect.innerHTML = biState.sheets
        .map((s) => `<option value="${s}" ${s === biState.activeSheet ? "selected" : ""}>📄 ${s}</option>`)
        .join("");
    } else {
      sheetSelect.classList.add("hidden");
    }
  }

  // Render Power BI Sheet Tabs bar
  const tabsBar = $("#bi-sheet-tabs-bar");
  const tabsList = $("#bi-sheet-tabs-list");
  if (tabsBar && tabsList) {
    if (biState.sheets.length > 1) {
      tabsBar.classList.remove("hidden");
      tabsList.innerHTML = biState.sheets
        .map((s) => {
          const rowCount = biState.allSheets[s]?.rows_count ?? (s === biState.activeSheet ? biState.rawData.length : 0);
          const isActive = s === biState.activeSheet;
          return `
            <button type="button" class="bi-sheet-tab-btn ${isActive ? "active" : ""}" data-sheet="${s}" title="Switch to worksheet '${s}'">
              <span>📄 ${s}</span>
              <span class="bi-sheet-tab-count">${rowCount}</span>
            </button>
          `;
        })
        .join("");

      tabsList.querySelectorAll(".bi-sheet-tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const s = btn.dataset.sheet;
          if (s && s !== biState.activeSheet) {
            biSwitchSheet(s);
          }
        });
      });
    } else {
      tabsBar.classList.add("hidden");
    }
  }

  // Toggle empty dropzone vs dashboard
  $("#bi-empty-dropzone")?.classList.add("hidden");
  $("#bi-active-dashboard")?.classList.remove("hidden");

  // Render fields list
  biRenderFieldsList();

  // Auto-generate visuals (or use default_visuals from payload)
  if (payload.default_visuals && payload.default_visuals.length > 0) {
    biState.visuals = payload.default_visuals.map((v, idx) => ({ ...v, id: `vis_${idx + 1}` }));
  } else {
    biAutoGenerateVisuals();
  }

  // Render Slicers
  biRenderSlicers();

  // Apply filters and render KPIs + Visuals
  biApplyFilters();
}

function biSwitchSheet(sheetName) {
  if (!biState.allSheets[sheetName]) return;
  const sheetPayload = biState.allSheets[sheetName];
  biState.activeSheet = sheetName;
  biState.columns = sheetPayload.columns || [];
  biState.rawData = sheetPayload.data || [];
  biState.filteredData = [...biState.rawData];
  biState.activeSlicers = {};
  biState.searchQuery = "";

  const badge = $("#bi-active-file-badge");
  if (badge) {
    badge.textContent = `${biState.filename} [${sheetName}] (${biState.rawData.length} rows)`;
  }

  // Sync dropdown and tab buttons
  const sheetSelect = $("#bi-sheet-select");
  if (sheetSelect) sheetSelect.value = sheetName;
  document.querySelectorAll("#bi-sheet-tabs-list .bi-sheet-tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.sheet === sheetName);
  });

  biRenderFieldsList();
  biAutoGenerateVisuals();
  biRenderSlicers();
  biApplyFilters();
  toast("Sheet Switched", `Viewing worksheet '${sheetName}'.`, "info", 2000);
}

function biAutoGenerateVisuals() {
  const numCols = biState.columns.filter((c) => c.type === "number");
  const strCols = biState.columns.filter((c) => c.type === "string" || c.type === "boolean");
  const dateCols = biState.columns.filter((c) => c.type === "date");

  const visuals = [];
  let visId = 1;

  // Primary category column
  const catCol = strCols.length > 0 ? strCols[0].name : (biState.columns[0]?.name || "Item");

  // Visual 1: Combo Chart (or Bar) if at least 2 numbers exist
  if (numCols.length >= 2) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "combo",
      title: `${numCols[0].name} (Bar) vs ${numCols[1].name} (Line) by ${catCol}`,
      x: catCol,
      y: numCols[0].name,
      y2: numCols[1].name,
      agg: "sum",
    });
  } else if (numCols.length === 1) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "bar",
      title: `Total ${numCols[0].name} by ${catCol}`,
      x: catCol,
      y: numCols[0].name,
      agg: "sum",
    });
  }

  // Visual 2: Donut / Pie distribution
  if (strCols.length > 0) {
    const pieCat = strCols.length > 1 ? strCols[1].name : strCols[0].name;
    visuals.push({
      id: `vis_${visId++}`,
      type: "pie",
      title: `Distribution by ${pieCat}`,
      x: pieCat,
      y: numCols[0]?.name || pieCat,
      agg: numCols.length > 0 ? "sum" : "count",
    });
  }

  // Visual 3: Horizontal Ranked Bar
  if (numCols.length > 0) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "hbar",
      title: `Top Rankings: ${numCols[0].name} by ${catCol}`,
      x: catCol,
      y: numCols[0].name,
      agg: "sum",
    });
  }

  // Visual 4: Line Trend Chart
  if (dateCols.length > 0 && numCols.length > 0) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "line",
      title: `${numCols[0].name} Trend Over Time`,
      x: dateCols[0].name,
      y: numCols[0].name,
      agg: "avg",
    });
  } else if (numCols.length > 0) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "line",
      title: `${numCols[0].name} Value Curve`,
      x: catCol,
      y: numCols[0].name,
      agg: "avg",
    });
  }

  // Visual 5: Interactive Data Table
  visuals.push({
    id: `vis_${visId++}`,
    type: "table",
    title: `Raw Records Grid (${biState.activeSheet})`,
    limit: 15,
  });

  biState.visuals = visuals;
}

function biApplyFilters() {
  let filtered = [...biState.rawData];

  // 1. Text search across all fields
  if (biState.searchQuery) {
    const q = biState.searchQuery;
    filtered = filtered.filter((row) =>
      Object.values(row).some((val) => val !== null && val !== undefined && String(val).toLowerCase().includes(q))
    );
  }

  // 2. Slicers
  for (const [col, selectedSet] of Object.entries(biState.activeSlicers)) {
    if (selectedSet && selectedSet.size > 0) {
      filtered = filtered.filter((row) => selectedSet.has(String(row[col] ?? "")));
    }
  }

  biState.filteredData = filtered;

  // Filter indicator badge
  const isFiltered = filtered.length !== biState.rawData.length;
  const ind = $("#bi-active-filter-indicator");
  if (ind) {
    ind.classList.toggle("hidden", !isFiltered);
    ind.textContent = isFiltered ? `${filtered.length} / ${biState.rawData.length}` : "";
  }

  biRenderKPICards();
  biRenderVisuals();
}

function biRenderFieldsList(filterText = "") {
  const container = $("#bi-fields-list");
  if (!container) return;
  const countEl = $("#bi-fields-count");
  if (countEl) countEl.textContent = `${biState.columns.length} fields`;

  const q = filterText.toLowerCase();
  const cols = biState.columns.filter((c) => !q || c.name.toLowerCase().includes(q));

  if (cols.length === 0) {
    container.innerHTML = `<div class="meta" style="padding:12px;text-align:center;">No matching fields found.</div>`;
    return;
  }

  container.innerHTML = cols
    .map((c) => {
      let icon = "🔤";
      let badgeText = "TXT";
      if (c.isCustom) { icon = "fx"; badgeText = "CALC"; }
      else if (c.type === "number") { icon = "🔢"; badgeText = "NUM"; }
      else if (c.type === "date") { icon = "📅"; badgeText = "DATE"; }
      else if (c.type === "boolean") { icon = "🔘"; badgeText = "BOOL"; }

      const isSelected = biState.selectedField === c.name;
      return `
        <div class="bi-field-item ${isSelected ? "active" : ""}" data-field="${c.name}">
          <span class="bi-field-badge">${icon} ${badgeText}</span>
          <span class="bi-field-name" title="${c.name}">${c.name}</span>
        </div>
      `;
    })
    .join("");

  // Click on field to see stats
  container.querySelectorAll(".bi-field-item").forEach((el) => {
    el.addEventListener("click", () => {
      const fieldName = el.dataset.field;
      biState.selectedField = fieldName;
      container.querySelectorAll(".bi-field-item").forEach((b) => b.classList.remove("active"));
      el.classList.add("active");
      biShowFieldDetails(fieldName);
    });
  });
}

function biShowFieldDetails(fieldName) {
  const col = biState.columns.find((c) => c.name === fieldName);
  const card = $("#bi-field-details");
  if (!col || !card) return;

  card.classList.remove("hidden");
  $("#bi-field-details-name").textContent = `${col.name} (${col.type.toUpperCase()})`;

  let statsHtml = `<div>Count: <b>${col.count}</b> (Non-null: ${col.non_null_count})</div>`;
  if (col.type === "number") {
    statsHtml += `
      <div>Sum: <b>${col.sum !== undefined ? biFormatNumber(col.sum) : "—"}</b></div>
      <div>Average: <b>${col.avg !== undefined ? biFormatNumber(col.avg) : "—"}</b></div>
      <div>Min: <b>${col.min !== undefined ? col.min : "—"}</b> | Max: <b>${col.max !== undefined ? col.max : "—"}</b></div>
    `;
  } else if (col.distinct_count !== undefined) {
    statsHtml += `<div>Distinct values: <b>${col.distinct_count}</b></div>`;
    if (col.sample_values && col.sample_values.length > 0) {
      statsHtml += `<div style="font-size:10.5px;color:var(--text-dim);margin-top:2px;">Samples: ${col.sample_values.slice(0, 3).join(", ")}</div>`;
    }
  }
  $("#bi-field-details-stats").innerHTML = statsHtml;
}

function biRenderSlicers() {
  const container = $("#bi-slicers-container");
  if (!container) return;

  // Pick categorical columns with 2 to 12 distinct values, OR columns with an active filter
  const slicerCols = biState.columns.filter((c) => {
    if (biState.activeSlicers[c.name] && biState.activeSlicers[c.name].size > 0) return true;
    if (c.type !== "string" && c.type !== "boolean") return false;
    const distinctVals = new Set(biState.rawData.map((r) => String(r[c.name] ?? ""))).size;
    return distinctVals >= 2 && distinctVals <= 12;
  }).slice(0, 4);

  if (slicerCols.length === 0) {
    container.innerHTML = `<span class="meta" style="font-size:11px;">No categorical slicer fields available for this sheet.</span>`;
    return;
  }

  let html = "";
  slicerCols.forEach((col) => {
    const uniqueVals = Array.from(new Set(biState.rawData.map((r) => String(r[col.name] ?? "")))).filter(Boolean);
    const activeSet = biState.activeSlicers[col.name] || new Set();

    html += `
      <div style="display:flex;align-items:center;gap:4px;background:rgba(255,255,255,0.03);padding:2px 8px;border-radius:6px;border:1px solid var(--border);">
        <span class="meta" style="font-size:11px;font-weight:600;color:var(--accent);">${col.name}:</span>
    `;

    uniqueVals.forEach((val) => {
      const isSelected = activeSet.has(val);
      html += `
        <button type="button" class="bi-slicer-chip ${isSelected ? "active" : ""}" data-col="${col.name}" data-val="${val}">
          ${val}
        </button>
      `;
    });

    html += `</div>`;
  });

  container.innerHTML = html;

  // Slicer chip click toggle
  container.querySelectorAll(".bi-slicer-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const col = btn.dataset.col;
      const val = btn.dataset.val;
      if (!biState.activeSlicers[col]) {
        biState.activeSlicers[col] = new Set();
      }
      const set = biState.activeSlicers[col];
      if (set.has(val)) {
        set.delete(val);
      } else {
        set.add(val);
      }
      btn.classList.toggle("active", set.has(val));
      biApplyFilters();
    });
  });
}

function biRenderKPICards() {
  const container = $("#bi-kpi-row");
  if (!container) return;

  const data = biState.filteredData;
  const numCols = biState.columns.filter((c) => c.type === "number");
  const strCols = biState.columns.filter((c) => c.type === "string");

  // KPI 1: Total records
  const totalRecords = data.length;
  const isFiltered = totalRecords !== biState.rawData.length;

  // KPI 2: Primary measure SUM
  let kpi2Label = "Primary Metric";
  let kpi2Val = "—";
  let kpi2Sub = "";
  if (numCols.length > 0) {
    const colName = numCols[0].name;
    const sum = data.reduce((acc, r) => acc + (Number(r[colName]) || 0), 0);
    kpi2Label = `Total ${colName}`;
    kpi2Val = biFormatNumber(sum);
    kpi2Sub = `Aggregated SUM across ${totalRecords} records`;
  }

  // KPI 3: Average measure
  let kpi3Label = "Average Metric";
  let kpi3Val = "—";
  let kpi3Sub = "";
  if (numCols.length > 0) {
    const colName = numCols[1] ? numCols[1].name : numCols[0].name;
    const sum = data.reduce((acc, r) => acc + (Number(r[colName]) || 0), 0);
    const avg = totalRecords > 0 ? sum / totalRecords : 0;
    kpi3Label = `Avg ${colName}`;
    kpi3Val = biFormatNumber(avg);
    kpi3Sub = `Average per record`;
  }

  // KPI 4: Top Category / Peak
  let kpi4Label = "Category Peak";
  let kpi4Val = "—";
  let kpi4Sub = "";
  if (strCols.length > 0 && numCols.length > 0) {
    const catCol = strCols[0].name;
    const valCol = numCols[0].name;
    const map = {};
    data.forEach((r) => {
      const c = String(r[catCol] || "Unknown");
      map[c] = (map[c] || 0) + (Number(r[valCol]) || 0);
    });
    let topCat = "—";
    let maxVal = -Infinity;
    for (const [k, v] of Object.entries(map)) {
      if (v > maxVal) { maxVal = v; topCat = k; }
    }
    kpi4Label = `Top ${catCol}`;
    kpi4Val = topCat;
    kpi4Sub = maxVal !== -Infinity ? `Peak: ${biFormatNumber(maxVal)} (${valCol})` : "";
  } else if (strCols.length > 0) {
    const catCol = strCols[0].name;
    const distinct = new Set(data.map((r) => String(r[catCol]))).size;
    kpi4Label = `Unique ${catCol}`;
    kpi4Val = String(distinct);
    kpi4Sub = `Distinct categories`;
  }

  container.innerHTML = `
    <div class="bi-kpi-card" style="border-top-color:#1ea7fd;">
      <div class="bi-kpi-label">Records Count</div>
      <div class="bi-kpi-val">${totalRecords.toLocaleString()}</div>
      <div class="bi-kpi-sub">${isFiltered ? `Filtered from ${biState.rawData.length} total rows` : "Total active records"}</div>
    </div>
    <div class="bi-kpi-card" style="border-top-color:#3fb950;">
      <div class="bi-kpi-label">${kpi2Label}</div>
      <div class="bi-kpi-val">${kpi2Val}</div>
      <div class="bi-kpi-sub">${kpi2Sub}</div>
    </div>
    <div class="bi-kpi-card" style="border-top-color:#a371f7;">
      <div class="bi-kpi-label">${kpi3Label}</div>
      <div class="bi-kpi-val">${kpi3Val}</div>
      <div class="bi-kpi-sub">${kpi3Sub}</div>
    </div>
    <div class="bi-kpi-card" style="border-top-color:#e3b341;">
      <div class="bi-kpi-label">${kpi4Label}</div>
      <div class="bi-kpi-val" style="font-size:20px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${kpi4Val}</div>
      <div class="bi-kpi-sub">${kpi4Sub}</div>
    </div>
  `;
}

function biAggregate(data, xCol, yCol, agg = "sum") {
  const map = {};
  data.forEach((r) => {
    const key = String(r[xCol] ?? "—");
    const num = Number(r[yCol]) || 0;
    if (!map[key]) map[key] = { key, count: 0, sum: 0, min: Infinity, max: -Infinity };
    map[key].count += 1;
    map[key].sum += num;
    if (num < map[key].min) map[key].min = num;
    if (num > map[key].max) map[key].max = num;
  });

  return Object.values(map).map((g) => {
    let val = 0;
    if (agg === "sum") val = g.sum;
    else if (agg === "avg") val = g.count > 0 ? g.sum / g.count : 0;
    else if (agg === "count") val = g.count;
    else if (agg === "min") val = g.min !== Infinity ? g.min : 0;
    else if (agg === "max") val = g.max !== -Infinity ? g.max : 0;
    return { key: g.key, val: Math.round(val * 100) / 100, count: g.count };
  });
}

function biToggleChartFilter(colName, value) {
  if (!colName || value === undefined || value === null) return;
  const strVal = String(value);

  if (!biState.activeSlicers[colName]) {
    biState.activeSlicers[colName] = new Set();
  }
  const set = biState.activeSlicers[colName];
  if (set.has(strVal)) {
    set.delete(strVal);
    if (set.size === 0) delete biState.activeSlicers[colName];
    toast("Filter Cleared", `Cleared filter on '${colName}'.`, "info", 1800);
  } else {
    // Power BI behavior: clicking a category isolates that category
    set.clear();
    set.add(strVal);
    toast("Cross-Filtered", `Filtered dashboard by ${colName} = "${strVal}"`, "ok", 2200);
  }

  biRenderSlicers();
  biApplyFilters();
}

function biOpenCalcColModal() {
  const modal = $("#modal-bi-calc-col");
  if (!modal) return;
  const nameInput = $("#bi-calc-name");
  const exprInput = $("#bi-calc-expr");
  const chipsContainer = $("#bi-calc-columns-chips");
  if (nameInput) nameInput.value = "";
  if (exprInput) exprInput.value = "";

  if (chipsContainer) {
    chipsContainer.innerHTML = biState.columns.map((c) => {
      const isNum = c.type === "number";
      return `
        <span class="chip" data-col="${c.name}" style="cursor:pointer;font-size:11px;background:${isNum ? 'rgba(30,167,253,0.15)' : 'rgba(255,255,255,0.06)'};color:${isNum ? 'var(--accent)' : 'var(--text)'};">
          ${isNum ? '🔢' : '🔤'} [${c.name}]
        </span>
      `;
    }).join("");

    chipsContainer.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const col = chip.dataset.col;
        if (exprInput) {
          exprInput.value += `[${col}]`;
          exprInput.focus();
        }
      });
    });
  }

  // Quick formula template buttons
  $("#bi-calc-templates")?.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      const numCols = biState.columns.filter((c) => c.type === "number").map((c) => c.name);
      const colA = numCols[0] || "ColA";
      const colB = numCols[1] || numCols[0] || "ColB";
      let tmpl = btn.dataset.template.replace(/\[A\]/g, `[${colA}]`).replace(/\[B\]/g, `[${colB}]`);
      if (exprInput) {
        exprInput.value = tmpl;
        exprInput.focus();
      }
    };
  });

  modal.classList.remove("hidden");
}

function biCreateCalculatedColumn() {
  const nameInput = $("#bi-calc-name");
  const exprInput = $("#bi-calc-expr");
  const colName = (nameInput?.value || "").trim().replace(/\s+/g, "_");
  const expr = (exprInput?.value || "").trim();

  if (!colName) {
    toast("Column Name Required", "Please enter a name for the calculated measure/column.", "err", 3000);
    return;
  }
  if (!expr) {
    toast("Formula Expression Required", "Please enter a valid formula expression (e.g. ([Revenue] - [Cost])).", "err", 3000);
    return;
  }

  // Parse [Column_Name] references
  const usedCols = [];
  const colPattern = /\[([^\]]+)\]/g;
  let match;
  while ((match = colPattern.exec(expr)) !== null) {
    usedCols.push(match[1]);
  }

  if (usedCols.length === 0) {
    toast("Invalid Expression", "Expression must reference at least one [Column_Name].", "err", 3000);
    return;
  }

  for (const c of usedCols) {
    if (!biState.columns.some((col) => col.name === c)) {
      toast("Column Not Found", `Referenced column '[${c}]' does not exist in dataset.`, "err", 3500);
      return;
    }
  }

  const evalRow = (row) => {
    let sanitized = expr;
    for (const c of usedCols) {
      const rawVal = row[c];
      const numVal = (typeof rawVal === "number") ? rawVal : (parseFloat(rawVal) || 0);
      sanitized = sanitized.split(`[${c}]`).join(String(numVal));
    }
    if (!/^[0-9\.\+\-\*\/\(\)\s]+$/.test(sanitized)) {
      throw new Error("Formula contains invalid characters. Only math operators allowed (+, -, *, /, ()).");
    }
    try {
      const res = Function(`"use strict"; return (${sanitized});`)();
      if (!isFinite(res) || isNaN(res)) return 0;
      return Number(res.toFixed(2));
    } catch {
      return 0;
    }
  };

  try {
    let successCount = 0;
    biState.rawData.forEach((row) => {
      row[colName] = evalRow(row);
      successCount++;
    });

    if (biState.activeSheet && biState.allSheets[biState.activeSheet]) {
      const sheetData = biState.allSheets[biState.activeSheet].data || [];
      sheetData.forEach((row) => {
        row[colName] = evalRow(row);
      });
    }

    if (!biState.columns.some((c) => c.name === colName)) {
      biState.columns.push({ name: colName, type: "number", isCustom: true, count: successCount, non_null_count: successCount });
    }

    $("#modal-bi-calc-col")?.classList.add("hidden");
    toast("Measure Created", `Calculated column '${colName}' computed for ${successCount} records.`, "ok", 3500);

    biRenderFieldsList();
    biApplyFilters();
  } catch (err) {
    toast("Calculation Error", err.message, "err", 4000);
  }
}

function biRenderVisuals() {
  const grid = $("#bi-visuals-grid");
  if (!grid) return;

  if (biState.visuals.length === 0) {
    grid.innerHTML = `<div class="meta" style="grid-column:1/-1;text-align:center;padding:40px;">Click '＋ Add Visual' to create dashboard widgets.</div>`;
    return;
  }

  grid.innerHTML = biState.visuals.map((vis, idx) => {
    let typeIcon = "📊";
    if (vis.type === "combo") typeIcon = "📊📈";
    else if (vis.type === "hbar") typeIcon = "📶";
    else if (vis.type === "line") typeIcon = "📈";
    else if (vis.type === "pie") typeIcon = "🍩";
    else if (vis.type === "table") typeIcon = "▦";

    const isWide = !!vis.isWide;
    return `
      <div class="bi-visual-card ${isWide ? 'wide' : ''}" id="card-${vis.id}" data-id="${vis.id}" data-idx="${idx}" draggable="true">
        <div class="bi-visual-head">
          <div class="bi-visual-title">
            <span class="bi-drag-handle" title="Drag to reorder card">⋮⋮</span>
            <span>${typeIcon}</span>
            <span>${vis.title || "Visual"}</span>
          </div>
          <div class="bi-visual-actions">
            <button class="btn btn-xs ghost btn-vis-focus" title="Toggle 1-column / 2-column width" data-id="${vis.id}">⤢</button>
            <button class="btn btn-xs ghost btn-vis-del" title="Remove visual" data-id="${vis.id}">✕</button>
          </div>
        </div>
        <div class="bi-visual-body" id="body-${vis.id}">
          <!-- Chart SVG or Table dynamically injected -->
        </div>
        <div class="bi-visual-foot">
          <span>${vis.type.toUpperCase()} · ${vis.agg ? vis.agg.toUpperCase() : "GRID"}</span>
          <span class="meta">${biState.filteredData.length} active records</span>
        </div>
      </div>
    `;
  }).join("");

  // Attach card header actions: toggle 1x / 2x width
  grid.querySelectorAll(".btn-vis-focus").forEach((b) => {
    b.addEventListener("click", () => {
      const vis = biState.visuals.find((v) => v.id === b.dataset.id);
      if (vis) {
        vis.isWide = !vis.isWide;
        const card = $(`#card-${b.dataset.id}`);
        card?.classList.toggle("wide", vis.isWide);
        toast("Card Resized", vis.isWide ? "Expanded visual to full width (2 columns)." : "Collapsed visual to standard width (1 column).", "info", 1500);
      }
    });
  });

  // Delete card
  grid.querySelectorAll(".btn-vis-del").forEach((b) => {
    b.addEventListener("click", () => {
      biState.visuals = biState.visuals.filter((v) => v.id !== b.dataset.id);
      biRenderVisuals();
    });
  });

  // Drag and Drop card reordering
  let draggedCardId = null;
  grid.querySelectorAll(".bi-visual-card").forEach((card) => {
    card.addEventListener("dragstart", (e) => {
      draggedCardId = card.dataset.id;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", draggedCardId);
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      grid.querySelectorAll(".bi-visual-card").forEach((c) => c.classList.remove("drag-over"));
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      card.classList.add("drag-over");
    });

    card.addEventListener("dragleave", () => {
      card.classList.remove("drag-over");
    });

    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      const targetId = card.dataset.id;
      if (!draggedCardId || draggedCardId === targetId) return;

      const fromIdx = biState.visuals.findIndex((v) => v.id === draggedCardId);
      const toIdx = biState.visuals.findIndex((v) => v.id === targetId);
      if (fromIdx !== -1 && toIdx !== -1) {
        const [moved] = biState.visuals.splice(fromIdx, 1);
        biState.visuals.splice(toIdx, 0, moved);
        biRenderVisuals();
        toast("Layout Updated", `Reordered '${moved.title}' card.`, "info", 1500);
      }
    });
  });

  // Render each visual
  biState.visuals.forEach((vis) => {
    const el = $(`#body-${vis.id}`);
    if (!el) return;

    if (vis.type === "combo") {
      biRenderComboChart(el, vis);
    } else if (vis.type === "bar") {
      biRenderBarChart(el, vis, false);
    } else if (vis.type === "hbar") {
      biRenderBarChart(el, vis, true);
    } else if (vis.type === "line") {
      biRenderLineChart(el, vis);
    } else if (vis.type === "pie") {
      biRenderDonutChart(el, vis);
    } else if (vis.type === "table") {
      biRenderTable(el, vis);
    }
  });
}

function biShowTooltip(e, title, val1, val2 = null) {
  const tip = biState.tooltipEl;
  if (!tip) return;
  let html = `<div style="font-weight:700;margin-bottom:2px;">${title}</div><div>${val1}</div>`;
  if (val2) html += `<div>${val2}</div>`;
  tip.innerHTML = html;
  tip.style.display = "block";
  tip.style.left = `${e.clientX + 12}px`;
  tip.style.top = `${e.clientY + 12}px`;
}

function biHideTooltip() {
  if (biState.tooltipEl) biState.tooltipEl.style.display = "none";
}

function biRenderComboChart(container, vis) {
  const data = biState.filteredData;
  const groups1 = biAggregate(data, vis.x, vis.y, vis.agg);
  const groups2 = vis.y2 ? biAggregate(data, vis.x, vis.y2, vis.agg) : [];
  const map2 = {};
  groups2.forEach((g) => { map2[g.key] = g.val; });

  const categories = groups1.slice(0, 10);
  if (categories.length === 0) {
    container.innerHTML = `<span class="meta">No data matching active filters.</span>`;
    return;
  }

  const maxBar = Math.max(...categories.map((c) => c.val), 1);
  const maxLine = Math.max(...categories.map((c) => map2[c.key] || 0), 1);

  const w = 500;
  const h = 260;
  const pad = { top: 30, right: 40, bottom: 50, left: 50 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;
  const barW = Math.max(12, Math.min(32, (chartW / categories.length) * 0.55));

  let svg = `<svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">`;

  // Gridlines
  for (let i = 0; i <= 4; i++) {
    const yPos = pad.top + (chartH / 4) * i;
    const valBar = Math.round(maxBar * (1 - i / 4));
    svg += `
      <line x1="${pad.left}" y1="${yPos}" x2="${w - pad.right}" y2="${yPos}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3"/>
      <text x="${pad.left - 8}" y="${yPos + 4}" fill="var(--text-dim)" font-size="10" text-anchor="end">${biFormatNumber(valBar)}</text>
    `;
  }

  // Bars (Measure 1)
  const linePoints = [];
  const activeFilterSet = biState.activeSlicers[vis.x];
  const isFiltered = activeFilterSet && activeFilterSet.size > 0;

  categories.forEach((cat, idx) => {
    const xCenter = pad.left + (chartW / categories.length) * (idx + 0.5);
    const bHeight = (cat.val / maxBar) * chartH;
    const yTop = pad.top + chartH - bHeight;
    const xBar = xCenter - barW / 2;
    const isSelected = isFiltered && activeFilterSet.has(cat.key);
    const opacity = isFiltered ? (isSelected ? "1.0" : "0.25") : "0.85";
    const strokeAttr = isSelected ? `stroke="#ffffff" stroke-width="2.5"` : "";

    svg += `
      <rect class="bi-bar-rect" x="${xBar}" y="${yTop}" width="${barW}" height="${bHeight}" fill="${BI_PALETTES[0]}" rx="3"
        ${strokeAttr}
        data-cat="${cat.key}" data-val1="${cat.val}" data-val2="${map2[cat.key] || 0}" style="cursor:pointer;transition:all 0.15s;opacity:${opacity};">
      </rect>
      <text x="${xCenter}" y="${h - pad.bottom + 16}" fill="${isSelected ? 'var(--text)' : 'var(--text-dim)'}" font-size="10" font-weight="${isSelected ? '700' : '400'}" text-anchor="middle"
        transform="rotate(0, ${xCenter}, ${h - pad.bottom + 16})">${cat.key.length > 9 ? cat.key.substring(0, 8) + '…' : cat.key}</text>
    `;

    // Measure 2 (Line point)
    const val2 = map2[cat.key] || 0;
    const yLine = pad.top + chartH - (val2 / maxBar) * chartH; // or scale to maxLine
    linePoints.push({ x: xCenter, y: yLine, val2, cat: cat.key });
  });

  // Polyline for Measure 2
  if (linePoints.length > 1) {
    const ptsStr = linePoints.map((p) => `${p.x},${p.y}`).join(" ");
    svg += `<polyline points="${ptsStr}" fill="none" stroke="${BI_PALETTES[2]}" stroke-width="3" stroke-linecap="round"/>`;
  }

  // Circles for line points
  linePoints.forEach((p) => {
    svg += `
      <circle cx="${p.x}" cy="${p.y}" r="4" fill="${BI_PALETTES[2]}" stroke="#fff" stroke-width="1.5"
        data-cat="${p.cat}" data-val2="${p.val2}" style="cursor:pointer;"></circle>
    `;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  // Tooltip & Cross-Filter click wiring
  container.querySelectorAll(".bi-bar-rect, circle").forEach((el) => {
    el.addEventListener("click", () => {
      if (el.dataset.cat) biToggleChartFilter(vis.x, el.dataset.cat);
    });
    el.addEventListener("mouseenter", (e) => {
      const cat = el.dataset.cat;
      const v1 = el.dataset.val1 ? `${vis.y}: <b>${biFormatNumber(Number(el.dataset.val1))}</b>` : "";
      const v2 = el.dataset.val2 ? `${vis.y2 || "Metric 2"}: <b>${biFormatNumber(Number(el.dataset.val2))}</b>` : "";
      biShowTooltip(e, cat, v1, v2);
    });
    el.addEventListener("mousemove", (e) => {
      if (biState.tooltipEl) {
        biState.tooltipEl.style.left = `${e.clientX + 12}px`;
        biState.tooltipEl.style.top = `${e.clientY + 12}px`;
      }
    });
    el.addEventListener("mouseleave", () => biHideTooltip());
  });
}

function biRenderBarChart(container, vis, isHorizontal = false) {
  const data = biState.filteredData;
  const groups = biAggregate(data, vis.x, vis.y, vis.agg);
  groups.sort((a, b) => b.val - a.val);
  const items = groups.slice(0, isHorizontal ? 8 : 10);

  if (items.length === 0) {
    container.innerHTML = `<span class="meta">No data available.</span>`;
    return;
  }

  const maxVal = Math.max(...items.map((i) => i.val), 1);
  const w = 500;
  const h = 260;

  const activeFilterSet = biState.activeSlicers[vis.x];
  const isFiltered = activeFilterSet && activeFilterSet.size > 0;

  if (isHorizontal) {
    const pad = { top: 20, right: 50, bottom: 20, left: 110 };
    const chartW = w - pad.left - pad.right;
    const barH = Math.max(14, Math.min(24, ((h - pad.top - pad.bottom) / items.length) * 0.7));

    let svg = `<svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">`;
    items.forEach((item, idx) => {
      const yCenter = pad.top + ((h - pad.top - pad.bottom) / items.length) * (idx + 0.5);
      const bWidth = (item.val / maxVal) * chartW;
      const color = BI_PALETTES[idx % BI_PALETTES.length];
      const isSelected = isFiltered && activeFilterSet.has(item.key);
      const opacity = isFiltered ? (isSelected ? "1.0" : "0.25") : "0.9";
      const strokeAttr = isSelected ? `stroke="#ffffff" stroke-width="2.5"` : "";

      svg += `
        <text x="${pad.left - 8}" y="${yCenter + 4}" fill="${isSelected ? 'var(--text)' : 'var(--text-dim)'}" font-size="10.5" font-weight="${isSelected ? '700' : '400'}" text-anchor="end">${item.key.length > 14 ? item.key.slice(0, 13) + '…' : item.key}</text>
        <rect class="bi-bar-rect" x="${pad.left}" y="${yCenter - barH / 2}" width="${bWidth}" height="${barH}" fill="${color}" rx="3"
          ${strokeAttr}
          data-cat="${item.key}" data-val="${item.val}" style="cursor:pointer;opacity:${opacity};transition:all 0.15s;"></rect>
        <text x="${pad.left + bWidth + 6}" y="${yCenter + 4}" fill="var(--text)" font-size="10" font-weight="600">${biFormatNumber(item.val)}</text>
      `;
    });
    svg += `</svg>`;
    container.innerHTML = svg;
  } else {
    // Vertical Column
    const pad = { top: 30, right: 30, bottom: 50, left: 50 };
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;
    const barW = Math.max(12, Math.min(32, (chartW / items.length) * 0.6));

    let svg = `<svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">`;
    for (let i = 0; i <= 4; i++) {
      const yPos = pad.top + (chartH / 4) * i;
      svg += `
        <line x1="${pad.left}" y1="${yPos}" x2="${w - pad.right}" y2="${yPos}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3"/>
        <text x="${pad.left - 8}" y="${yPos + 4}" fill="var(--text-dim)" font-size="10" text-anchor="end">${biFormatNumber(Math.round(maxVal * (1 - i / 4)))}</text>
      `;
    }

    items.forEach((item, idx) => {
      const xCenter = pad.left + (chartW / items.length) * (idx + 0.5);
      const bHeight = (item.val / maxVal) * chartH;
      const yTop = pad.top + chartH - bHeight;
      const color = BI_PALETTES[idx % BI_PALETTES.length];
      const isSelected = isFiltered && activeFilterSet.has(item.key);
      const opacity = isFiltered ? (isSelected ? "1.0" : "0.25") : "0.9";
      const strokeAttr = isSelected ? `stroke="#ffffff" stroke-width="2.5"` : "";

      svg += `
        <rect class="bi-bar-rect" x="${xCenter - barW / 2}" y="${yTop}" width="${barW}" height="${bHeight}" fill="${color}" rx="3"
          ${strokeAttr}
          data-cat="${item.key}" data-val="${item.val}" style="cursor:pointer;opacity:${opacity};transition:all 0.15s;"></rect>
        <text x="${xCenter}" y="${h - pad.bottom + 16}" fill="${isSelected ? 'var(--text)' : 'var(--text-dim)'}" font-size="10" font-weight="${isSelected ? '700' : '400'}" text-anchor="middle">${item.key.length > 9 ? item.key.slice(0, 8) + '…' : item.key}</text>
      `;
    });
    svg += `</svg>`;
    container.innerHTML = svg;
  }

  // Tooltip & Cross-Filter click wiring
  container.querySelectorAll(".bi-bar-rect").forEach((el) => {
    el.addEventListener("click", () => {
      if (el.dataset.cat) biToggleChartFilter(vis.x, el.dataset.cat);
    });
    el.addEventListener("mouseenter", (e) => {
      biShowTooltip(e, el.dataset.cat, `${vis.y}: <b>${biFormatNumber(Number(el.dataset.val))}</b>`);
    });
    el.addEventListener("mousemove", (e) => {
      if (biState.tooltipEl) {
        biState.tooltipEl.style.left = `${e.clientX + 12}px`;
        biState.tooltipEl.style.top = `${e.clientY + 12}px`;
      }
    });
    el.addEventListener("mouseleave", () => biHideTooltip());
  });
}

function biRenderLineChart(container, vis) {
  const data = biState.filteredData;
  const groups = biAggregate(data, vis.x, vis.y, vis.agg);
  const items = groups.slice(0, 14);

  if (items.length === 0) {
    container.innerHTML = `<span class="meta">No data available.</span>`;
    return;
  }

  const maxVal = Math.max(...items.map((i) => i.val), 1);
  const minVal = Math.min(...items.map((i) => i.val), 0);
  const range = maxVal - minVal || 1;

  const w = 500;
  const h = 260;
  const pad = { top: 30, right: 30, bottom: 50, left: 50 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  let svg = `
    <svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">
      <defs>
        <linearGradient id="lineGrad-${vis.id}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${BI_PALETTES[0]}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="${BI_PALETTES[0]}" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
  `;

  // Grid
  for (let i = 0; i <= 4; i++) {
    const yPos = pad.top + (chartH / 4) * i;
    svg += `
      <line x1="${pad.left}" y1="${yPos}" x2="${w - pad.right}" y2="${yPos}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3"/>
      <text x="${pad.left - 8}" y="${yPos + 4}" fill="var(--text-dim)" font-size="10" text-anchor="end">${biFormatNumber(Math.round(maxVal - (range / 4) * i))}</text>
    `;
  }

  const points = items.map((item, idx) => {
    const x = pad.left + (chartW / (items.length - 1 || 1)) * idx;
    const y = pad.top + chartH - ((item.val - minVal) / range) * chartH;
    return { x, y, item };
  });

  // Area under curve
  const areaPath = `M ${points[0].x} ${pad.top + chartH} ` +
    points.map((p) => `L ${p.x} ${p.y}`).join(" ") +
    ` L ${points[points.length - 1].x} ${pad.top + chartH} Z`;
  svg += `<path d="${areaPath}" fill="url(#lineGrad-${vis.id})"/>`;

  // Main line
  const linePath = `M ` + points.map((p) => `${p.x} ${p.y}`).join(" L ");
  svg += `<path d="${linePath}" fill="none" stroke="${BI_PALETTES[0]}" stroke-width="2.5" stroke-linecap="round"/>`;

  // Dots & Labels
  points.forEach((p) => {
    svg += `
      <circle class="bi-line-point" cx="${p.x}" cy="${p.y}" r="4.5" fill="${BI_PALETTES[0]}" stroke="#fff" stroke-width="1.5"
        data-cat="${p.item.key}" data-val="${p.item.val}" style="cursor:pointer;"></circle>
      <text x="${p.x}" y="${h - pad.bottom + 16}" fill="var(--text-dim)" font-size="10" text-anchor="middle">${p.item.key.length > 8 ? p.item.key.slice(0, 7) + '…' : p.item.key}</text>
    `;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  container.querySelectorAll(".bi-line-point").forEach((el) => {
    el.addEventListener("mouseenter", (e) => {
      biShowTooltip(e, el.dataset.cat, `${vis.y}: <b>${biFormatNumber(Number(el.dataset.val))}</b>`);
    });
    el.addEventListener("mousemove", (e) => {
      if (biState.tooltipEl) {
        biState.tooltipEl.style.left = `${e.clientX + 12}px`;
        biState.tooltipEl.style.top = `${e.clientY + 12}px`;
      }
    });
    el.addEventListener("mouseleave", () => biHideTooltip());
  });
}

function biRenderDonutChart(container, vis) {
  const data = biState.filteredData;
  const groups = biAggregate(data, vis.x, vis.y, vis.agg);
  groups.sort((a, b) => b.val - a.val);
  const items = groups.slice(0, 7);

  const total = items.reduce((acc, i) => acc + i.val, 0);
  if (total <= 0) {
    container.innerHTML = `<span class="meta">No distribution data available.</span>`;
    return;
  }

  const cx = 130;
  const cy = 130;
  const r = 90;
  const innerR = 55;

  const activeFilterSet = biState.activeSlicers[vis.x];
  const isFiltered = activeFilterSet && activeFilterSet.size > 0;

  let currentAngle = -Math.PI / 2;
  let svg = `<svg class="bi-chart-svg" viewBox="0 0 460 260">`;

  // Slices
  items.forEach((item, idx) => {
    const sliceAngle = (item.val / total) * (Math.PI * 2);
    const startAngle = currentAngle;
    const endAngle = currentAngle + sliceAngle;
    currentAngle = endAngle;

    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);

    const ix1 = cx + innerR * Math.cos(endAngle);
    const iy1 = cy + innerR * Math.sin(endAngle);
    const ix2 = cx + innerR * Math.cos(startAngle);
    const iy2 = cy + innerR * Math.sin(startAngle);

    const largeArc = sliceAngle > Math.PI ? 1 : 0;
    const pathData = `
      M ${x1} ${y1}
      A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}
      L ${ix1} ${iy1}
      A ${innerR} ${innerR} 0 ${largeArc} 0 ${ix2} ${iy2}
      Z
    `;

    const color = BI_PALETTES[idx % BI_PALETTES.length];
    const pct = ((item.val / total) * 100).toFixed(1);
    const isSelected = isFiltered && activeFilterSet.has(item.key);
    const opacity = isFiltered ? (isSelected ? "1.0" : "0.25") : "0.92";
    const strokeAttr = isSelected ? `stroke="#ffffff" stroke-width="3"` : `stroke="#1e1e2e" stroke-width="2"`;

    svg += `
      <path class="bi-donut-slice" d="${pathData}" fill="${color}" ${strokeAttr}
        data-cat="${item.key}" data-val="${item.val}" data-pct="${pct}" style="cursor:pointer;opacity:${opacity};transition:all 0.15s;"></path>
    `;
  });

  // Center text
  svg += `
    <text x="${cx}" y="${cy - 2}" fill="var(--text-dim)" font-size="11" text-anchor="middle">TOTAL</text>
    <text x="${cx}" y="${cy + 16}" fill="var(--text)" font-size="14" font-weight="700" text-anchor="middle">${biFormatNumber(total)}</text>
  `;

  // Legend on right
  const legendX = 250;
  items.forEach((item, idx) => {
    const ly = 40 + idx * 26;
    const color = BI_PALETTES[idx % BI_PALETTES.length];
    const pct = ((item.val / total) * 100).toFixed(1);
    const isSelected = isFiltered && activeFilterSet.has(item.key);
    const opacity = isFiltered ? (isSelected ? "1.0" : "0.35") : "1.0";

    svg += `
      <g class="bi-donut-legend-item" data-cat="${item.key}" style="cursor:pointer;opacity:${opacity};">
        <rect x="${legendX}" y="${ly - 9}" width="12" height="12" rx="3" fill="${color}"/>
        <text x="${legendX + 18}" y="${ly}" fill="var(--text)" font-size="11" font-weight="${isSelected ? '700' : '500'}">${item.key.length > 15 ? item.key.slice(0, 14) + '…' : item.key}</text>
        <text x="${legendX + 170}" y="${ly}" fill="var(--text-dim)" font-size="10.5" text-anchor="end">${pct}% (${biFormatNumber(item.val)})</text>
      </g>
    `;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  // Tooltip & Cross-Filter click wiring
  container.querySelectorAll(".bi-donut-slice, .bi-donut-legend-item").forEach((el) => {
    el.addEventListener("click", () => {
      if (el.dataset.cat) biToggleChartFilter(vis.x, el.dataset.cat);
    });
    el.addEventListener("mouseenter", (e) => {
      biShowTooltip(e, el.dataset.cat, `Value: <b>${biFormatNumber(Number(el.dataset.val))}</b>`, `Share: <b>${el.dataset.pct}%</b>`);
    });
    el.addEventListener("mousemove", (e) => {
      if (biState.tooltipEl) {
        biState.tooltipEl.style.left = `${e.clientX + 12}px`;
        biState.tooltipEl.style.top = `${e.clientY + 12}px`;
      }
    });
    el.addEventListener("mouseleave", () => biHideTooltip());
  });
}

function biRenderTable(container, vis) {
  const records = biState.filteredData.slice(0, vis.limit || 20);
  if (records.length === 0) {
    container.innerHTML = `<span class="meta">No matching records found.</span>`;
    return;
  }

  const cols = biState.columns.slice(0, 7); // show top 7 columns

  let html = `<div class="bi-table-wrap"><table class="bi-table"><thead><tr>`;
  cols.forEach((c) => {
    html += `<th>${c.name}</th>`;
  });
  html += `</tr></thead><tbody>`;

  records.forEach((row) => {
    html += `<tr>`;
    cols.forEach((c) => {
      const val = row[c.name];
      const displayVal = val !== null && val !== undefined ? String(val) : "—";
      html += `<td>${displayVal}</td>`;
    });
    html += `</tr>`;
  });

  html += `</tbody></table></div>`;
  container.innerHTML = html;
}

function biOpenJsonModal() {
  const modal = $("#modal-bi-json");
  if (!modal) return;
  const jsonStr = JSON.stringify(biState.filteredData, null, 2);
  const sizeKb = (new Blob([jsonStr]).size / 1024).toFixed(1);

  $("#bi-json-stats-badge").textContent = `${biState.filteredData.length} records · ${biState.columns.length} columns · ${sizeKb} KB`;
  $("#bi-json-viewer-content").textContent = jsonStr;
  modal.classList.remove("hidden");
}

function biOpenAddVisualModal() {
  const modal = $("#modal-bi-add-visual");
  if (!modal) return;

  const xSelect = $("#bi-visual-x-select");
  const ySelect = $("#bi-visual-y-select");
  const y2Select = $("#bi-visual-y2-select");

  const numCols = biState.columns.filter((c) => c.type === "number");
  const allCols = biState.columns;

  if (xSelect) {
    xSelect.innerHTML = allCols.map((c) => `<option value="${c.name}">${c.name} (${c.type})</option>`).join("");
  }
  if (ySelect) {
    ySelect.innerHTML = numCols.length > 0
      ? numCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("")
      : allCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("");
  }
  if (y2Select) {
    y2Select.innerHTML = `<option value="">(None)</option>` +
      numCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("");
  }

  modal.classList.remove("hidden");
}

function biSaveNewVisual() {
  const activeTypeBtn = document.querySelector("#bi-visual-type-select .term-chip.active");
  const type = activeTypeBtn ? activeTypeBtn.dataset.vtype : "bar";
  const title = $("#bi-visual-title-input")?.value.trim() || `${type.toUpperCase()} Visual`;
  const x = $("#bi-visual-x-select")?.value;
  const y = $("#bi-visual-y-select")?.value;
  const y2 = $("#bi-visual-y2-select")?.value || null;
  const agg = $("#bi-visual-agg-select")?.value || "sum";

  biState.visuals.push({
    id: `vis_${Date.now()}`,
    type,
    title,
    x,
    y,
    y2,
    agg,
  });

  $("#modal-bi-add-visual")?.classList.add("hidden");
  biRenderVisuals();
  toast("Visual Added", `Created '${title}' on dashboard canvas.`, "ok", 2500);
}

async function biExportExcel() {
  if (biState.filteredData.length === 0) {
    toast("Export Failed", "No records to export.", "warn", 2500);
    return;
  }
  toast("Exporting Excel…", "Generating .xlsx file with active filtered dataset…", "info", 2000);
  try {
    const res = await fetch("/api/bi/export-excel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data: biState.filteredData,
        sheet_name: biState.activeSheet || "FilteredData",
        filename: `telua_bi_${biState.activeSheet || "export"}.xlsx`,
      }),
    });
    if (!res.ok) throw new Error("Server returned error during Excel export.");

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `telua_bi_${biState.activeSheet || "export"}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Excel Exported", "File downloaded successfully.", "ok", 3000);
  } catch (err) {
    toast("Export Error", err.message, "err", 5000);
  }
}

/* ---------------- Boot ---------------- */
async function boot() {
  // Self-heal if browser served a stale cached index.html (304 Not Modified) missing core panes
  if (!document.querySelector("#view-pipelines") || !document.querySelector("#editor") || !document.querySelector("#btn-term-new-session")) {
    try {
      const healed = sessionStorage.getItem("telua_dom_healed");
      if (!healed) {
        sessionStorage.setItem("telua_dom_healed", "1");
        await fetch(window.location.pathname, { cache: "reload" });
        window.location.reload();
        return;
      }
    } catch { /* ignore */ }
  } else {
    try { sessionStorage.removeItem("telua_dom_healed"); } catch { /* ignore */ }
  }
  wire();
  await Promise.all([refreshStatus(), refreshFiles(), refreshCryptoStatus()]);

  // Restore the last-used source from draft or localStorage so F5 keeps the active tab/source.
  const pipeDraft = draftLoadPipelines();
  let savedSource = null;
  let savedTab = null;
  let savedFile = null;
  try {
    savedSource = localStorage.getItem(LAST_SOURCE_KEY);
    savedTab = localStorage.getItem(LAST_TAB_KEY);
    savedFile = localStorage.getItem(LAST_FILE_KEY);
  } catch { /* ignore */ }

  const validSources = new Set(["my", "multi", "car", "dump", "system", "docker"]);
  const initialSource = (pipeDraft && pipeDraft.source && validSources.has(pipeDraft.source))
    ? pipeDraft.source
    : (savedSource && validSources.has(savedSource) ? savedSource : "my");

  state.plSource = initialSource === "docker" ? "system" : initialSource;
  if (state.plSource !== "system") _lastNonSystemPlSource = state.plSource;
  document.querySelectorAll("#pl-source-switch .src-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.source === state.plSource));

  await loadPipelines(pipeDraft);
  updateDraftChip();

  if (savedTab === "terminal") {
    switchTab("terminal");
  } else if (savedTab === "aosp") {
    switchTab("aosp");
  } else if (savedTab === "logcat") {
    switchTab("logcat");
  } else if (savedTab === "docs") {
    switchTab("docs");
  } else if (savedTab === "bi") {
    switchTab("bi");
  } else if (savedTab === "files") {
    if (savedFile && state.files.some(f => f.name === savedFile)) {
      const fileDraft = draftLoadFile();
      const draftContent = (fileDraft && fileDraft.name === savedFile) ? fileDraft.content : null;
      await openFile(savedFile, draftContent);
    } else {
      switchTab("files");
    }
  } else {
    syncTopTabs();
  }

  // Auto-resume logcat streaming if it was running before the page refresh.
  // The old adb logcat process died with the page, so start a fresh one.
  try {
    if (sessionStorage.getItem(LOGCAT_AUTOSTART_KEY) === "1" && !_logcatStreaming) {
      sessionStorage.removeItem(LOGCAT_AUTOSTART_KEY);
      fetch("/api/logcat/stop", { method: "POST" }).catch(() => { }); // kill orphaned adb proc
      startLogcatStream();
      toast("Logcat Resumed", "Streaming restarted after page refresh.", "info", 2500);
    }
  } catch { /* ignore */ }
}

boot();
