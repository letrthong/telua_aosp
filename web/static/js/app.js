/* ==============================================================================
   Telua Web - Application Entry Point
   Wires all tab listeners and boots the UI on DOM ready
   ============================================================================== */
function wire() {
  try { applyTheme(localStorage.getItem(THEME_KEY) || "dark"); } catch { applyTheme("dark"); }

  // Settings modal (gear icon): theme picker + tab visibility list
  $("#btn-settings")?.addEventListener("click", openSettingsModal);
  $("#btn-settings-close")?.addEventListener("click", () => $("#modal-settings")?.classList.add("hidden"));
  $("#settings-theme-select")?.addEventListener("change", (e) => {
    const val = e.target.value;
    applyTheme(val);
    toast("Theme updated 🎨", `${THEME_LABELS[val] || val} — saved in browser.`, "info", 5000);
  });
  $("#btn-settings-reset")?.addEventListener("click", () => {
    try { localStorage.removeItem(TABS_VISIBLE_KEY); } catch { /* ignore */ }
    applyTheme("dark");
    const sel = $("#settings-theme-select");
    if (sel) sel.value = "dark";
    applyTabVisibility();
    renderSettingsTabList();
    toast("Settings reset ↺", "All tabs visible again, theme back to Dark.", "ok", 4000);
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

  // ADB Offline & Remote Script Modal actions
  $("#chip-adb")?.addEventListener("click", () => openAdbOfflineModal());
  $("#btn-adb-help-close")?.addEventListener("click", closeAdbOfflineModal);
  $("#btn-adb-help-close-top")?.addEventListener("click", closeAdbOfflineModal);
  $("#btn-adb-copy-path")?.addEventListener("click", copyAdbScriptPath);
  $("#btn-adb-copy-cmd")?.addEventListener("click", copyAdbScriptCmd);
  $("#btn-adb-help-refresh")?.addEventListener("click", refreshAdbStatusFromModal);
  $("#btn-logcat-open-adb-help")?.addEventListener("click", openAdbOfflineModal);
  $("#btn-logcat-copy-adb-path")?.addEventListener("click", copyAdbScriptPath);

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
  $("#tab-ai")?.addEventListener("click", () => switchTab("ai"));
  $("#tab-tasks")?.addEventListener("click", () => switchTab("tasks"));
  $("#tab-flow")?.addEventListener("click", () => switchTab("flow"));
  $("#tab-mirror")?.addEventListener("click", () => switchTab("mirror"));
  $("#tab-power")?.addEventListener("click", () => switchTab("power"));

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
  $("#btn-aosp-upload-apk")?.addEventListener("click", () => {
    const btn = $("#btn-aosp-upload-apk");
    btn?.classList.add("btn-clicked");
    setTimeout(() => btn?.classList.remove("btn-clicked"), 1500);
    $("#aosp-apk-file-input")?.click();
  });
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
  $("#btn-term-popout")?.addEventListener("click", () => {
    openConsolePopout("Telua Web CLI Terminal");
    setTimeout(() => {
      const html = $("#term-output")?.innerHTML || "";
      const badge = $("#term-status-badge");
      if (html) {
        _popoutBroadcast({ type: "output", title: "💻 Web CLI Terminal", html, badge: badge ? { text: badge.textContent, cls: badge.className.replace("run-badge", "").trim() } : null });
        _popoutSnapshot("💻 Web CLI Terminal", html, badge ? { text: badge.textContent, cls: badge.className.replace("run-badge", "").trim() } : null);
      }
      // Ẩn terminal view ở tab chính khi pop-out đã mở thành công
      if (_popoutIsOpen()) _hideTerminalForPopout();
    }, 600);
  });
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
      $("#modal-task-detail")?.classList.add("hidden");
      $("#modal-task-edit")?.classList.add("hidden");
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
  applyTabVisibility();
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

  if (savedTab && !isTabVisible(savedTab)) {
    savedTab = null; // tab was hidden in Settings → fall back below
  }
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
  } else if (savedTab === "ai") {
    switchTab("ai");
  } else if (savedTab === "tasks") {
    switchTab("tasks");
  } else if (savedTab === "flow") {
    switchTab("flow");
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
