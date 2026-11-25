/* ==============================================================================
   Telua Web - Pipelines Module (MY_CMD / MULTI / CAR / DUMP / SYSTEM)
   ============================================================================== */
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
  const isMirror = !$("#view-mirror")?.classList.contains("hidden");
  const isSystem = !isFiles && !isAosp && !isTerminal && !isLogcat && !isDocs && !isBi && !isMirror && (state.plSource === "system" || state.plSource === "docker");
  const isPipelines = !isFiles && !isAosp && !isTerminal && !isLogcat && !isDocs && !isBi && !isMirror && !isSystem;
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
  $("#tab-mirror")?.classList.toggle("active", isMirror);
  $("#tab-bi")?.classList.toggle("active", isBi);
  try {
    const activeTabName = isFiles ? "files" : (isAosp ? "aosp" : (isTerminal ? "terminal" : (isLogcat ? "logcat" : (isDocs ? "docs" : (isBi ? "bi" : (isMirror ? "mirror" : (isSystem ? "system" : "pipelines")))))));
    localStorage.setItem(LAST_TAB_KEY, activeTabName);
    localStorage.setItem(LAST_SOURCE_KEY, state.plSource);
  } catch { /* ignore */ }
}

function switchPipelineSource(source) {
  if (source === "docker") source = "system";
  if (source !== "system") _lastNonSystemPlSource = source;
  // Ensure Pipelines view is visible if user clicks a source while in Terminal, Files, Docs, Logcat, AOSP or Mirror
  $("#view-files")?.classList.add("hidden");
  $("#view-aosp")?.classList.add("hidden");
  $("#view-terminal")?.classList.add("hidden");
  $("#view-docs")?.classList.add("hidden");
  $("#view-logcat")?.classList.add("hidden");
  $("#view-mirror")?.classList.add("hidden");
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
  // Khi pop-out console đang mở → output chỉ hiển thị ở pop-out,
  // không hiện lại bottom panel / dialog ở tab chính.
  const popoutOpen = _popoutIsOpen();

  if (popoutOpen) {
    bottomPanel?.classList.add("hidden");
    bottomPanel.dataset.popoutHidden = "1";
    modalEl?.classList.add("hidden");
  } else if (isBottom) {
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
  const popTitle = `📟 ${cmd} ${name}`;
  const broadcastIfPopped = (html, badge) => {
    if (_popoutIsOpen()) {
      _popoutBroadcast({ type: "output", title: popTitle, html, badge });
      _popoutSnapshot(popTitle, html, badge);
    }
  };

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
          broadcastIfPopped(outEl ? outEl.innerHTML : "", { text: `⏳ Running… (${elapsed}s)`, cls: "running" });
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
      broadcastIfPopped(outEl ? outEl.innerHTML : "", { text: exitCode === 0 ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${exitCode} (${elapsed}s)`, cls: exitCode === 0 ? "ok" : "err" });
      if (badge) {
        const ok = exitCode === 0;
        badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${exitCode} (${elapsed}s)`;
        badge.className = "run-badge " + (ok ? "ok" : "err");
      }
      if (!isBottom && !popoutOpen) {
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
    broadcastIfPopped(outEl ? outEl.innerHTML : "", { text: data.exit_code === 0 ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${data.exit_code} (${elapsed}s)`, cls: data.exit_code === 0 ? "ok" : "err" });
    if (badge) {
      const ok = data.exit_code === 0;
      badge.textContent = ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${data.exit_code} (${elapsed}s)`;
      badge.className = "run-badge " + (ok ? "ok" : "err");
    }
    if (!isBottom && !popoutOpen) {
      scheduleRunAutoClose(data.exit_code === 0);
    }
  } catch (err) {
    if (_runStoppedByUser || err.name === "AbortError") {
      if (outEl) outEl.innerHTML += `\n<span style="color:#d29922;font-weight:700">^C [Stopped by user · ${elapsed}s]</span>\n`;
      if (badge) {
        badge.textContent = `⏹ Stopped (${elapsed}s)`;
        badge.className = "run-badge err";
      }
      broadcastIfPopped(outEl ? outEl.innerHTML : "", { text: `⏹ Stopped (${elapsed}s)`, cls: "err" });
    } else {
      if (outEl) outEl.textContent = `[ERROR] ${err.message}`;
      if (badge) {
        badge.textContent = "✖ Error";
        badge.className = "run-badge err";
      }
      broadcastIfPopped(outEl ? outEl.innerHTML : "", { text: "✖ Error", cls: "err" });
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
  $("#btn-pl-bottom-popout")?.addEventListener("click", () => {
    openConsolePopout("Telua Pipeline Console");
    // Gửi ngay snapshot hiện tại sang popout vừa mở
    setTimeout(() => {
      const html = $("#pl-bottom-output")?.innerHTML || "";
      const badge = $("#pl-bottom-status-badge");
      const title = $("#pl-bottom-title")?.textContent || "Pipeline Output";
      if (html) {
        _popoutBroadcast({ type: "output", title: `📟 ${title}`, html, badge: badge ? { text: badge.textContent, cls: badge.className.replace("run-badge", "").trim() } : null });
        _popoutSnapshot(`📟 ${title}`, html, badge ? { text: badge.textContent, cls: badge.className.replace("run-badge", "").trim() } : null);
      }
      // Ẩn bottom panel ở tab chính khi pop-out đã mở thành công
      if (_popoutIsOpen()) _hidePipelineBottomForPopout();
    }, 600);
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

