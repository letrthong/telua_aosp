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
  dirty: false,
  status: null,
  pipelines: [],      // [{ name, description, array, steps, orphan }]
  plDirty: false,
  plSource: "my",     // "my" (const_my_cli.config) | "multi" (const_multi_cli.config)
};

/* ---------------- Draft persistence (localStorage, survives refresh) ------- */
const DRAFT_KEY_FILES = "telua_web_draft_file";      // { name, content, saved_at }
const DRAFT_KEY_PIPES = "telua_web_draft_pipelines"; // { source, pipelines, saved_at }

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
    localStorage.setItem(DRAFT_KEY_PIPES, JSON.stringify({
      source: state.plSource,
      pipelines: state.pipelines,
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
function toast(title, body, kind = "info", timeout = 4200) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<div class="t-title"></div><div class="t-body"></div>`;
  el.querySelector(".t-title").textContent = title;
  el.querySelector(".t-body").textContent = body || "";
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), timeout);
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
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
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
};

function renderFiles(filter = "") {
  const list = $("#file-list");
  list.innerHTML = "";
  const q = filter.trim().toLowerCase();
  const files = state.files.filter(f => !q || f.name.toLowerCase().includes(q));

  for (const f of files) {
    const li = document.createElement("li");
    li.dataset.name = f.name;
    if (state.current && state.current.name === f.name) li.classList.add("active");

    const name = document.createElement("span");
    name.className = "fname";
    name.textContent = f.name;
    li.title = `${f.name} · ${f.size} bytes · ${f.mtime_str}` +
      (PIPELINE_GUI_FILES[f.name] ? " · ⚡ has Pipelines GUI" : "");
    li.appendChild(name);

    const right = document.createElement("span");
    right.className = "fgroup";
    right.textContent = f.readonly ? "🔒 ro" : f.group;
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
//   - Files tab active  -> load the file into the editor (classic behavior).
//   - Pipelines tab active AND the file has a Pipelines GUI (const_my_cli /
//     const_multi_cli) -> show the Pipelines GUI with the matching source.
//   - Otherwise -> fall back to the editor.
function handleFileClick(name) {
  const pipelinesActive = !$("#view-pipelines").classList.contains("hidden");
  const guiSource = PIPELINE_GUI_FILES[name];
  if (pipelinesActive && guiSource && state.plSource !== guiSource) {
    switchPipelineSource(guiSource);
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

function setCurrentMeta() {
  const c = state.current;
  if (!c) {
    $("#editor-name").textContent = "—";
    $("#editor-meta").textContent = "";
    return;
  }
  $("#editor-name").textContent = c.name;
  $("#editor-meta").textContent =
    `${c.kind} · ${c.readonly ? "read-only" : "editable"} · ${c.size} bytes · ${c.mtime_str || ""}`;
  $("#btn-reload").disabled = false;
  $("#btn-save").disabled = c.readonly;
  $("#editor").disabled = c.readonly;
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
    if (draftContent != null && draftContent !== data.content) {
      // Restore the unsaved draft on top of the freshly loaded file.
      $("#editor").value = draftContent;
      setDirty(true);
      toast("Draft restored", `Unsaved edits for ${name} recovered (last change: ${draftTime(draftContent && draftLoadFile()?.saved_at)}).`, "warn", 6000);
    } else {
      $("#editor").value = data.content;
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
    draftClearFile();                  // server save succeeded -> drop the draft
    c.size = data.bytes;
    c.mtime_str = data.saved_at;
    setCurrentMeta();
    toast("Saved ✓", `${data.name} (${data.bytes} bytes)` +
          (data.backup ? ` · backup: ${data.backup}` : ""), "ok");
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
  } catch (err) {
    toast("Pipelines load failed", err.message, "err");
  }
}

function switchPipelineSource(source) {
  if (state.plSource === source) return;
  if (state.plDirty && !confirm("Switch source with unsaved pipeline edits?\n\nThe current draft is kept in browser storage and will be restored when you switch back.")) return;
  state.plSource = source;
  document.querySelectorAll("#pl-source-switch .src-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.source === source));
  loadPipelines(draftLoadPipelines());
}

function renderPipelines() {
  const list = $("#pipeline-list");
  list.innerHTML = "";
  for (const p of state.pipelines) {
    list.appendChild(pipelineCard(p));
  }
  if (state.pipelines.length === 0) {
    const fileLabel = $("#pl-file")?.textContent || "config/overlay/const_my_cli.config";
    list.innerHTML = `<p class="meta">No pipelines found in ${escapeHtml(fileLabel)}.</p>`;
  }
  const total = state.pipelines.reduce((n, p) => n + p.steps.length, 0);
  $("#pl-stats").textContent =
    `${state.pipelines.length} pipelines · ${total} steps`;
}

function pipelineCard(p) {
  const card = document.createElement("div");
  card.className = "pl-card" + (p.orphan ? " orphan" : "");
  card.dataset.name = p.name;

  // --- header: name + description + array tag ---
  const head = document.createElement("div");
  head.className = "pl-card-head";

  const name = document.createElement("input");
  name.className = "pl-name";
  name.value = p.name;
  name.title = "Pipeline name (used as: telua my <name>)";
  name.addEventListener("input", () => { p.name = name.value; setPlDirty(true); });
  head.appendChild(name);

  const desc = document.createElement("input");
  desc.className = "pl-desc";
  desc.value = p.description || "";
  desc.placeholder = "Description (shown by: telua my)";
  desc.addEventListener("input", () => { p.description = desc.value; setPlDirty(true); });
  head.appendChild(desc);

  const tag = document.createElement("span");
  tag.className = "pl-array-tag";
  tag.textContent = p.orphan ? "⚠ orphan" : p.array;
  head.appendChild(tag);
  card.appendChild(head);

  // --- steps ---
  const stepsBox = document.createElement("div");
  stepsBox.className = "pl-steps";
  p.steps.forEach((step, idx) => stepsBox.appendChild(stepRow(p, step, idx, stepsBox)));
  card.appendChild(stepsBox);

  const addStep = document.createElement("button");
  addStep.className = "pl-add-step";
  addStep.textContent = "＋ Add step";
  addStep.addEventListener("click", () => {
    p.steps.push("");
    stepsBox.appendChild(stepRow(p, "", p.steps.length - 1, stepsBox));
    setPlDirty(true);
    const inputs = stepsBox.querySelectorAll(".pl-step-cmd");
    inputs[inputs.length - 1]?.focus();
  });
  card.appendChild(addStep);

  // --- footer: run + delete pipeline ---
  const foot = document.createElement("div");
  foot.className = "pl-card-foot";

  const runBtn = document.createElement("button");
  runBtn.className = "btn";
  runBtn.textContent = "▶ Run";
  runBtn.title = "Execute: telua my " + p.name;
  runBtn.addEventListener("click", () => runPipeline(p.name));
  foot.appendChild(runBtn);

  const delBtn = document.createElement("button");
  delBtn.className = "btn danger";
  delBtn.textContent = "🗑 Delete";
  delBtn.addEventListener("click", () => {
    if (!confirm(`Delete pipeline '${p.name}' (${p.steps.length} steps)?`)) return;
    state.pipelines = state.pipelines.filter(x => x !== p);
    setPlDirty(true);
    renderPipelines();
  });
  foot.appendChild(delBtn);
  card.appendChild(foot);

  return card;
}

function stepRow(p, step, idx, stepsBox) {
  const row = document.createElement("div");
  row.className = "pl-step";

  const no = document.createElement("span");
  no.className = "pl-step-no";
  no.textContent = `${idx + 1}.`;
  row.appendChild(no);

  const input = document.createElement("input");
  input.className = "pl-step-cmd";
  input.value = step;
  input.placeholder = "adb shell … | git … | sleep 1 | echo …";
  input.addEventListener("input", () => { p.steps[idx] = input.value; setPlDirty(true); });
  row.appendChild(input);

  const up = document.createElement("button");
  up.className = "pl-icon-btn";
  up.textContent = "↑";
  up.title = "Move up";
  up.addEventListener("click", () => {
    if (idx === 0) return;
    [p.steps[idx - 1], p.steps[idx]] = [p.steps[idx], p.steps[idx - 1]];
    setPlDirty(true);
    rerenderSteps(p, stepsBox);
  });
  row.appendChild(up);

  const down = document.createElement("button");
  down.className = "pl-icon-btn";
  down.textContent = "↓";
  down.title = "Move down";
  down.addEventListener("click", () => {
    if (idx >= p.steps.length - 1) return;
    [p.steps[idx + 1], p.steps[idx]] = [p.steps[idx], p.steps[idx + 1]];
    setPlDirty(true);
    rerenderSteps(p, stepsBox);
  });
  row.appendChild(down);

  const del = document.createElement("button");
  del.className = "pl-icon-btn del";
  del.textContent = "✕";
  del.title = "Delete step";
  del.addEventListener("click", () => {
    p.steps.splice(idx, 1);
    setPlDirty(true);
    rerenderSteps(p, stepsBox);
  });
  row.appendChild(del);

  return row;
}

function rerenderSteps(p, stepsBox) {
  stepsBox.innerHTML = "";
  p.steps.forEach((step, idx) => stepsBox.appendChild(stepRow(p, step, idx, stepsBox)));
  const total = state.pipelines.reduce((n, x) => n + x.steps.length, 0);
  $("#pl-stats").textContent = `${state.pipelines.length} pipelines · ${total} steps`;
}

async function savePipelines() {
  // Drop empty-named pipelines before saving.
  const payload = state.pipelines
    .filter(p => p.name && p.name.trim())
    .map(p => ({ name: p.name.trim(), description: p.description || "", steps: p.steps }));
  try {
    const data = await api("/api/pipelines", {
      method: "POST",
      body: JSON.stringify({ source: state.plSource, pipelines: payload }),
    });
    setPlDirty(false);
    draftClearPipelines();             // server save succeeded -> drop the draft
    toast("Pipelines saved ✓", `${data.source}: ${data.count} pipelines · backup: ${data.backup || "none"}`, "ok");
    await loadPipelines();
  } catch (err) {
    toast("Save failed", err.message, "err");
  }
}

async function runPipeline(name) {
  const cmd = state.plSource === "multi" ? "telua run" : "telua my";
  $("#run-title").textContent = `${cmd} ${name}`;
  $("#run-output").textContent = "Running…";
  $("#modal-run").classList.remove("hidden");
  try {
    const data = await api("/api/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ name, source: state.plSource }),
    });
    $("#run-output").textContent =
      (data.output || "(no output)") +
      `\n\n[exit code: ${data.exit_code}]`;
  } catch (err) {
    $("#run-output").textContent = `[ERROR] ${err.message}`;
  }
}

function addPipeline() {
  let i = 1;
  const existing = new Set(state.pipelines.map(p => p.name));
  let name = "new_pipeline";
  while (existing.has(name)) { name = `new_pipeline_${++i}`; }
  state.pipelines.push({ name, description: "", array: "MY_CMD_" + name.toUpperCase(), steps: [] });
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
    $("#info-output").textContent = data.output || "(no output)";
  } catch (err) {
    $("#info-output").textContent = `[ERROR] ${err.message}`;
  }
}

/* ---------------- Wiring ---------------- */
function switchTab(tab) {
  const isFiles = tab === "files";
  $("#tab-files").classList.toggle("active", isFiles);
  $("#tab-pipelines").classList.toggle("active", !isFiles);
  $("#view-files").classList.toggle("hidden", !isFiles);
  $("#view-pipelines").classList.toggle("hidden", isFiles);
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
  $("#search").addEventListener("input", (e) => renderFiles(e.target.value));
  $("#btn-refresh").addEventListener("click", () => { refreshStatus(); refreshFiles(); });
  $("#btn-reload").addEventListener("click", () => state.current && openFile(state.current.name));
  $("#btn-save").addEventListener("click", saveFile);
  $("#btn-info").addEventListener("click", showInfo);
  $("#btn-info-close").addEventListener("click", () => $("#modal-info").classList.add("hidden"));
  $("#btn-profile-close").addEventListener("click", () => $("#modal-profile").classList.add("hidden"));
  $("#btn-run-close").addEventListener("click", () => $("#modal-run").classList.add("hidden"));

  // Tab switching
  $("#tab-files").addEventListener("click", () => switchTab("files"));
  $("#tab-pipelines").addEventListener("click", () => switchTab("pipelines"));
  $("#btn-pl-refresh").addEventListener("click", () => loadPipelines(draftLoadPipelines()));
  $("#btn-pl-add").addEventListener("click", addPipeline);
  $("#btn-pl-save").addEventListener("click", savePipelines);

  // Pipeline source switch (my <-> multi)
  document.querySelectorAll("#pl-source-switch .src-btn").forEach(btn =>
    btn.addEventListener("click", () => switchPipelineSource(btn.dataset.source)));

  // Click on the project chip opens the profile switcher
  $("#chip-project").addEventListener("click", openProfileModal);
  $("#chip-project").style.cursor = "pointer";
  $("#chip-project").title = "Click to switch ACTIVE_PROJECT";

  // Click on the draft chip discards the browser draft (keeps server files intact)
  $("#chip-draft").addEventListener("click", () => {
    if (!confirm("Discard the browser draft?\n\nUnsaved edits will be lost (files on disk are NOT affected).")) return;
    draftClearFile();
    draftClearPipelines();
    state.dirty = false;
    state.plDirty = false;
    $("#editor-dirty").classList.add("hidden");
    $("#pl-dirty").classList.add("hidden");
    $("#btn-save").disabled = true;
    $("#btn-pl-save").disabled = true;
    if (state.current) openFile(state.current.name);
    loadPipelines();
    updateDraftChip();
    toast("Draft discarded", "Unsaved edits removed from browser storage.", "info");
  });
  $("#chip-draft").style.cursor = "pointer";

  $("#editor").addEventListener("input", () => { setDirty(true); updateStats(); });

  // Ctrl+S / Cmd+S to save (works in both tabs)
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (!$("#view-pipelines").classList.contains("hidden")) {
        if (state.plDirty) savePipelines();
      } else if (state.dirty && state.current && !state.current.readonly) {
        saveFile();
      }
    }
    if (e.key === "Escape") {
      $("#modal-profile").classList.add("hidden");
      $("#modal-info").classList.add("hidden");
      $("#modal-run").classList.add("hidden");
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
  await Promise.all([refreshStatus(), refreshFiles()]);

  // Pipelines is the default tab: load it (with draft) immediately.
  // Restore the last-used source from the draft if present.
  const pipeDraft = draftLoadPipelines();
  if (pipeDraft && pipeDraft.source) {
    state.plSource = pipeDraft.source;
    document.querySelectorAll("#pl-source-switch .src-btn").forEach(b =>
      b.classList.toggle("active", b.dataset.source === state.plSource));
  }
  await loadPipelines(pipeDraft);
  updateDraftChip();

  // The Files tab is lazy-loaded on first switch (see switchTab).
}

boot();
