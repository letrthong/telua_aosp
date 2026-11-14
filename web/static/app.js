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
  const isTerminal = !$("#view-terminal")?.classList.contains("hidden");
  const isSystem = !isFiles && !isTerminal && (state.plSource === "system" || state.plSource === "docker");
  const isPipelines = !isFiles && !isTerminal && !isSystem;
  $("#tab-files")?.classList.toggle("active", isFiles);
  $("#tab-pipelines")?.classList.toggle("active", isPipelines);
  $("#tab-system")?.classList.toggle("active", isSystem);
  $("#tab-terminal")?.classList.toggle("active", isTerminal);
  try {
    const activeTabName = isFiles ? "files" : (isTerminal ? "terminal" : (isSystem ? "system" : "pipelines"));
    localStorage.setItem(LAST_TAB_KEY, activeTabName);
    localStorage.setItem(LAST_SOURCE_KEY, state.plSource);
  } catch { /* ignore */ }
}

function switchPipelineSource(source) {
  if (source === "docker") source = "system";
  if (source !== "system") _lastNonSystemPlSource = source;
  // Ensure Pipelines view is visible if user clicks a source while in Terminal or Files
  $("#view-files")?.classList.add("hidden");
  $("#view-terminal")?.classList.add("hidden");
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
    const prefixMap = { my: "MY_CMD_", multi: "MULTI_CMD_", docker: "SYSTEM_CMD_", system: "SYSTEM_CMD_", car: "ADB_SHELL_CAR_", dump: "ADB_SHELL_DUMP_" };
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
  const isSingleStep = (state.plSource === "car" || state.plSource === "dump");
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
  const isSingleStep = (state.plSource === "car" || state.plSource === "dump");
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

async function stopPipelineRun() {
  if (!_runAbortController) return;
  _runStoppedByUser = true;
  const badge = $("#run-status-badge");
  if (badge) {
    badge.textContent = "⏹ Stopping…";
    badge.className = "run-badge err";
  }
  try { await fetch("/api/terminal/stop", { method: "POST" }); } catch { /* ignore */ }
  try { _runAbortController.abort(); } catch { /* ignore */ }
}

async function runPipeline(name, explicitSource = null) {
  const source = explicitSource || state.plSource;
  _lastRunPipelineName = name;
  _lastRunPipelineSource = source;
  const cmdMap = { my: "telua my", multi: "telua run", system: "telua system", docker: "telua system", car: "telua car", dump: "telua dump" };
  const cmd = cmdMap[source] || "telua my";
  $("#run-title").textContent = `${cmd} ${name}`;
  const outEl = $("#run-output");
  const matchedPl = state.pipelines.find(p => p.name === name);
  const stepsHint = matchedPl && matchedPl.steps?.length
    ? matchedPl.steps.map((s, i) => `  [${i + 1}/${matchedPl.steps.length}] ${s}`).join("\n")
    : `  $ ${cmd} ${name}`;
  outEl.textContent = `⏳ Starting: ${cmd} ${name}…\n${stepsHint}\n`;

  const badge = $("#run-status-badge");
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
  const rerunBtn = $("#btn-run-again");
  const runStopBtn = $("#btn-run-stop");
  if (rerunBtn) rerunBtn.disabled = true;
  if (runStopBtn) {
    runStopBtn.disabled = false;
    runStopBtn.classList.add("danger-solid");
  }
  $("#modal-run").classList.remove("hidden");

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
          outEl.innerHTML = ansiToHtml(cleanPreview || "Running…");
          outEl.scrollTop = outEl.scrollHeight;
        }
      }

      const m = rawBuffer.match(/__TELUA_EXIT_CODE__:(-?\d+)/);
      if (m) exitCode = parseInt(m[1], 10);
      const finalOutput = rawBuffer.replace(/\n?__TELUA_EXIT_CODE__:\s*-?\d+\s*$/, "");
      outEl.innerHTML = ansiToHtml(
        (finalOutput || "(no output)") +
        `\n\n[exit code: ${exitCode} · elapsed: ${elapsed}s]`
      );
      outEl.scrollTop = outEl.scrollHeight;
      if (badge) {
        const ok = exitCode === 0;
        badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${exitCode} (${elapsed}s)`;
        badge.className = "run-badge " + (ok ? "ok" : "err");
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
    outEl.innerHTML = ansiToHtml(
      (data.output || "(no output)") +
      `\n\n[exit code: ${data.exit_code} · elapsed: ${elapsed}s]`
    );
    if (badge) {
      const ok = data.exit_code === 0;
      badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${data.exit_code} (${elapsed}s)`;
      badge.className = "run-badge " + (ok ? "ok" : "err");
    }
  } catch (err) {
    if (_runStoppedByUser || err.name === "AbortError") {
      outEl.innerHTML += `\n<span style="color:#d29922;font-weight:700">^C [Stopped by user · ${elapsed}s]</span>\n`;
      if (badge) {
        badge.textContent = `⏹ Stopped (${elapsed}s)`;
        badge.className = "run-badge err";
      }
    } else {
      outEl.textContent = `[ERROR] ${err.message}`;
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
  const prefixMap = { my: "MY_CMD_", multi: "MULTI_CMD_", docker: "SYSTEM_CMD_", system: "SYSTEM_CMD_", car: "ADB_SHELL_CAR_", dump: "ADB_SHELL_DUMP_" };
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

/* ---------------- Wiring ---------------- */
function switchTab(tab) {
  const isFiles = tab === "files";
  const isTerminal = tab === "terminal";
  const isPipelinesView = !isFiles && !isTerminal;
  $("#view-files")?.classList.toggle("hidden", !isFiles);
  $("#view-pipelines")?.classList.toggle("hidden", !isPipelinesView);
  $("#view-terminal")?.classList.toggle("hidden", !isTerminal);
  if (tab === "system") {
    switchPipelineSource("system");
  } else if (tab === "pipelines" && (state.plSource === "system" || state.plSource === "docker")) {
    switchPipelineSource(_lastNonSystemPlSource || "my");
  }
  syncTopTabs();
  renderFiles($("#search")?.value || "");
  if (isTerminal) {
    setTimeout(() => $("#term-input")?.focus(), 40);
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
  $("#btn-run-close")?.addEventListener("click", () => $("#modal-run")?.classList.add("hidden"));
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
  $("#tab-terminal")?.addEventListener("click", () => { switchTab("terminal"); renderFiles($("#search")?.value || ""); });

  // Terminal wiring
  $("#btn-term-run")?.addEventListener("click", () => runTerminalCommand());
  $("#btn-term-stop")?.addEventListener("click", () => stopTerminalCommand());
  $("#btn-term-new-session")?.addEventListener("click", () => newTerminalSession());
  $("#btn-run-stop")?.addEventListener("click", () => stopPipelineRun());
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
      $("#modal-run")?.classList.add("hidden");
      $("#modal-crypto")?.classList.add("hidden");
    }
  });

  // Warn before leaving with unsaved changes
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty || state.plDirty) { e.preventDefault(); e.returnValue = ""; }
  });
}

/* ---------------- Boot ---------------- */
async function boot() {
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
}

boot();
