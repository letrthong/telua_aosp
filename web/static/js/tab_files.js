/* ==============================================================================
   Telua Web - Files & Config Editor Module
   ============================================================================== */
/* ---------------- File list ---------------- */
// Files that have a dedicated Pipelines GUI view, mapped to their source key.
const PIPELINE_GUI_FILES = {
  "config/overlay/cli/const_my_cli.config": "my",
  "config/overlay/cli/const_my_cli.config.example": "my",
  "config/overlay/const_my_cli.config": "my",
  "config/overlay/const_my_cli.config.example": "my",
  "config/cli/const_my_cli.config": "my",
  "config/const_my_cli.config": "my",
  "config/const_my_cli.config.example": "my",
  "config/cli/const_multi_cli.config": "multi",
  "config/cli/const_multi_cli.config.example": "multi",
  "config/const_multi_cli.config": "multi",
  "config/const_multi_cli.config.example": "multi",
  "config/cli/const_system_cli.config": "system",
  "config/overlay/cli/const_system_cli.config": "system",
  "config/const_system_cli.config": "system",
  "config/overlay/const_system_cli.config": "system",
  "config/cli/const_car.config": "car",
  "config/overlay/cli/const_car.config": "car",
  "config/const_car.config": "car",
  "config/overlay/const_car.config": "car",
  "config/cli/const_dumpsys.config": "dump",
  "config/overlay/cli/const_dumpsys.config": "dump",
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

