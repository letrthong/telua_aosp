/* ==============================================================================
   Telua Web - Flowchart Demo Tab (Vanilla JS, 100% Frontend Demo)
   Interactive 5-stage pipeline visualization:
     Docs -> Code -> Build -> Run -> Unit Test (with self-healing Retry Loop)
   No AI API calls — clean hook points ready for future automation integration.
   ============================================================================== */
"use strict";

const FLOW_STAGES = [
  {
    id: "docs",
    step: 1,
    icon: "📚",
    title: "Docs (Spec)",
    subtitle: "Read Sphinx .rst & VectorDB",
    cmd: "read_file(Active_Docs_Dir) + search_knowledge(project, aosp_version)",
    inputs: "Sphinx .rst/.puml specs, VectorDB shard (A12–A16)",
    outputs: "Design constraints, API contracts, target symbols",
    hook: "Future hook: auto-load Active_Docs_Dir + shard context",
    demoLogs: [
      "[Docs] Resolving Active_Docs_Dir (/home/.../docs)...",
      "[Docs] Loaded CarAudio Architecture spec (ch1_architecture.rst)",
      "[Docs] Matched 4 design rules from VectorDB shard (aosp_aaos__a16)",
      "[Docs] ✓ Spec context ready (read-only).",
    ],
  },
  {
    id: "code",
    step: 2,
    icon: "💻",
    title: "Code",
    subtitle: "Edit & Refactor Module",
    cmd: "grep_search + AST read_file + edit_file (AOSP_ROOT_DIR)",
    inputs: "Target Path + Spec context",
    outputs: "Modified .java / .aidl / .cpp files + Git checkpoint",
    hook: "Future hook: AI coding turn with auto Git fix branch",
    demoLogs: [
      "[Code] Scanning target directory via grep_search...",
      "[Code] Extracted CarAudioService.setVolumeGroupIndex() via AST outline",
      "[Code] Applied surgical edit to CarAudioService.java (+18 / -6 lines)",
      "[Code] ✓ Code changes ready for compilation.",
    ],
  },
  {
    id: "build",
    step: 3,
    icon: "🔨",
    title: "Build",
    subtitle: "Compile via tel b -y",
    cmd: "cd <Target_Path> && tel b --start-deploy false -y",
    inputs: "AOSP_ROOT_DIR, LUNCH_TARGET, modified source files",
    outputs: "Compiled APK / binary artifact in out/target/product/...",
    hook: "Future hook: run_tel('tel b --start-deploy false -y', cwd=target_dir)",
    demoLogs: [
      "[Build] cd /home/developer/workspace/android/packages/apps/Car/OemService",
      "[Build] Running: tel b --start-deploy false -y",
      "[Build] Soong/Ninja compiling OemService.apk (my_board_in-userdebug)...",
      "[Build] ✓ Build succeeded (0 errors, OemService.apk generated).",
    ],
  },
  {
    id: "run",
    step: 4,
    icon: "🚀",
    title: "Run / Deploy",
    subtitle: "Push & Watch Logcat",
    cmd: "cd <Target_Path> && tel -y deploy && tel logcat",
    inputs: "Built APK/binary + connected ADB DUT",
    outputs: "Running service on board + clean logcat verification",
    hook: "Future hook: adb remount/push + 15s crash/ANR/SELinux monitor",
    demoLogs: [
      "[Run] Connected ADB device detected (userdebug)",
      "[Run] Pushing OemService.apk -> /system/priv-app/OemService/",
      "[Run] Restarting runtime framework & watching logcat (10s)...",
      "[Run] ✓ Service booted cleanly (0 FATAL EXCEPTION, 0 ANR).",
    ],
  },
  {
    id: "unittest",
    step: 5,
    icon: "🧪",
    title: "Unit Test",
    subtitle: "Verify via tel t",
    cmd: "cd <Target_Path> && tel t",
    inputs: "Deployed module + project test suite",
    outputs: "Test report (Pass / Fail) + ready for PR",
    hook: "Future hook: run_tel('tel t', cwd=target_dir) + parse JUnit results",
    demoLogs: [
      "[UnitTest] Running: cd <Target_Path> && tel t",
      "[UnitTest] Executing CarAudioServiceTest (14 test cases)...",
      "[UnitTest] 14/14 passed · 0 failed · 0 skipped (1.8s)",
      "[UnitTest] ✓ All unit tests passed — pipeline complete!",
    ],
  },
];

let _flowInitialized = false;
let _flowSelectedId = "docs";
let _flowStates = {};       // stageId -> "idle" | "running" | "done" | "error"
let _flowRunning = false;
let _flowCancelFlag = false;
let _flowStepCursor = 0;
let _flowRandomTimer = null;

function initFlowTab() {
  if (_flowInitialized) return;
  _flowInitialized = true;

  FLOW_STAGES.forEach(s => { _flowStates[s.id] = "idle"; });

  $("#btn-flow-random")?.addEventListener("click", toggleFlowRandomLive);
  $("#btn-flow-run-ok")?.addEventListener("click", () => { stopFlowRandomLive(); runFlowDemo(false); });
  $("#btn-flow-run-retry")?.addEventListener("click", () => { stopFlowRandomLive(); runFlowDemo(true); });
  $("#btn-flow-step")?.addEventListener("click", () => { stopFlowRandomLive(); stepFlowOnce(); });
  $("#btn-flow-reset")?.addEventListener("click", () => { stopFlowRandomLive(); resetFlowDemo(); });

  renderFlowDiagram();
  renderFlowInspector(_flowSelectedId);
  // Start random live preview automatically on first open for demo
  startFlowRandomLive();
}

function _setFlowCurrentBadge(stage, statusText = "") {
  const badge = $("#flow-status-badge");
  const tabBtn = $("#tab-flow");
  if (!badge) return;
  if (stage) {
    badge.textContent = statusText || `Running: 0${stage.step} ${stage.icon} ${stage.title}`;
    badge.className = "run-badge running";
    tabBtn?.classList.add("tab-streaming");
  } else {
    badge.textContent = statusText || "Demo Ready";
    badge.className = statusText.startsWith("✓") ? "run-badge ok" : "run-badge";
    tabBtn?.classList.remove("tab-streaming");
  }
}

function stopFlowRandomLive() {
  if (_flowRandomTimer) {
    clearTimeout(_flowRandomTimer);
    _flowRandomTimer = null;
  }
  const btn = $("#btn-flow-random");
  if (btn) btn.textContent = "🎲 Random Live";
  $("#tab-flow")?.classList.remove("tab-streaming");
}

function toggleFlowRandomLive() {
  if (_flowRandomTimer) {
    stopFlowRandomLive();
    _setFlowCurrentBadge(null, "Paused");
  } else {
    _flowCancelFlag = true;
    setFlowButtons(false);
    startFlowRandomLive();
  }
}

function startFlowRandomLive() {
  if (_flowRandomTimer) return;
  const btn = $("#btn-flow-random");
  if (btn) btn.textContent = "⏹ Stop Random";

  const tick = () => {
    // Pick a random active stage (0..4); mark earlier stages done, active stage running (or occasional retry)
    const idx = Math.floor(Math.random() * FLOW_STAGES.length);
    const active = FLOW_STAGES[idx];
    const simulateRetry = (active.id === "build" || active.id === "unittest") && Math.random() < 0.25;

    FLOW_STAGES.forEach((s, i) => {
      if (i < idx) _flowStates[s.id] = "done";
      else if (i === idx) _flowStates[s.id] = simulateRetry ? "error" : "running";
      else _flowStates[s.id] = "idle";
    });

    _flowSelectedId = active.id;
    renderFlowDiagram(simulateRetry);
    renderFlowInspector(active.id);

    if (simulateRetry) {
      _setFlowCurrentBadge(active, `Retry: 0${active.step} ${active.icon} ${active.title} ↩ Code`);
      flowLog(`[Random Demo] ${active.icon} ${active.title} failed -> looping back to 💻 Code`, "flow-log-warn");
    } else {
      _setFlowCurrentBadge(active, `Running: 0${active.step} ${active.icon} ${active.title}`);
      const sampleLine = active.demoLogs[Math.floor(Math.random() * active.demoLogs.length)];
      flowLog(sampleLine, sampleLine.includes("✓") ? "flow-log-ok" : "");
    }

    const nextDelay = 1400 + Math.floor(Math.random() * 1400);
    _flowRandomTimer = setTimeout(tick, nextDelay);
  };

  const logEl = $("#flow-demo-log");
  if (logEl) logEl.innerHTML = "";
  flowLog("Random Live Demo active — cycling through pipeline stages...");
  tick();
}

function flowLog(line, cls = "") {
  const el = $("#flow-demo-log");
  if (!el) return;
  const ts = new Date().toTimeString().slice(0, 8);
  const row = document.createElement("div");
  if (cls) row.className = cls;
  row.textContent = `[${ts}] ${line}`;
  el.appendChild(row);
  el.scrollTop = el.scrollHeight;
}

function setFlowButtons(running) {
  _flowRunning = running;
  const ids = ["#btn-flow-run-ok", "#btn-flow-run-retry", "#btn-flow-step"];
  ids.forEach(sel => {
    const b = $(sel);
    if (b) b.disabled = running;
  });
  const badge = $("#flow-status-badge");
  if (badge) {
    badge.textContent = running ? "Running Demo..." : "Demo Ready";
    badge.className = running ? "run-badge running" : "run-badge";
  }
}

function renderFlowDiagram(retryActive = false) {
  const canvas = $("#flow-canvas");
  if (!canvas) return;

  const badgeMap = {
    idle: `<span class="flow-pill idle">Idle</span>`,
    running: `<span class="flow-pill running">⏳ Running</span>`,
    done: `<span class="flow-pill done">✓ Done</span>`,
    error: `<span class="flow-pill error">✗ Failed</span>`,
  };

  canvas.innerHTML = FLOW_STAGES.map((st, idx) => {
    const state = _flowStates[st.id] || "idle";
    const isSelected = st.id === _flowSelectedId;
    const arrow = idx < FLOW_STAGES.length - 1
      ? `<div class="flow-arrow ${state === "done" ? "done" : ""}" aria-hidden="true">➜</div>`
      : "";
    return `
      <div class="flow-node state-${state} ${isSelected ? "selected" : ""}" data-stage-id="${st.id}" tabindex="0" role="button">
        <div class="flow-node-top">
          <span class="flow-step-num">0${st.step}</span>
          ${badgeMap[state] || badgeMap.idle}
        </div>
        <div class="flow-node-icon">${st.icon}</div>
        <div class="flow-node-title">${esc(st.title)}</div>
        <div class="flow-node-sub">${esc(st.subtitle)}</div>
      </div>
      ${arrow}
    `;
  }).join("");

  const loopBar = $("#flow-retry-loop");
  if (loopBar) {
    loopBar.classList.toggle("active", Boolean(retryActive));
  }

  canvas.querySelectorAll(".flow-node").forEach(node => {
    node.addEventListener("click", () => {
      _flowSelectedId = node.dataset.stageId;
      renderFlowDiagram(retryActive);
      renderFlowInspector(_flowSelectedId);
    });
  });
}

function renderFlowInspector(stageId) {
  const st = FLOW_STAGES.find(s => s.id === stageId) || FLOW_STAGES[0];
  const box = $("#flow-inspector");
  if (!box || !st) return;
  const state = _flowStates[st.id] || "idle";
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
      <div style="font-size:14px;font-weight:700;color:var(--text);">
        ${st.icon} Step 0${st.step}: ${esc(st.title)}
        <span class="meta" style="font-weight:400;margin-left:6px;">— ${esc(st.subtitle)}</span>
      </div>
      <span class="chip">${esc(state.toUpperCase())}</span>
    </div>
    <div class="flow-insp-grid">
      <div>
        <div class="meta" style="font-size:10px;text-transform:uppercase;letter-spacing:.4px;">Inputs</div>
        <div style="font-size:12px;margin-top:2px;">${esc(st.inputs)}</div>
      </div>
      <div>
        <div class="meta" style="font-size:10px;text-transform:uppercase;letter-spacing:.4px;">Outputs</div>
        <div style="font-size:12px;margin-top:2px;">${esc(st.outputs)}</div>
      </div>
      <div>
        <div class="meta" style="font-size:10px;text-transform:uppercase;letter-spacing:.4px;">Command / Action</div>
        <code class="mono" style="font-size:11px;color:var(--accent);display:block;margin-top:2px;">${esc(st.cmd)}</code>
      </div>
      <div>
        <div class="meta" style="font-size:10px;text-transform:uppercase;letter-spacing:.4px;">Future Integration Hook</div>
        <div class="meta" style="font-size:11px;margin-top:2px;">🔌 ${esc(st.hook)}</div>
      </div>
    </div>
  `;
}

function _sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function resetFlowDemo() {
  _flowCancelFlag = true;
  _flowStepCursor = 0;
  FLOW_STAGES.forEach(s => { _flowStates[s.id] = "idle"; });
  setFlowButtons(false);
  const logEl = $("#flow-demo-log");
  if (logEl) logEl.innerHTML = `<div class="meta">(Demo log cleared. Click ▶ Run Demo or ⏭ Step Next.)</div>`;
  renderFlowDiagram(false);
  renderFlowInspector(_flowSelectedId);
}

async function stepFlowOnce() {
  if (_flowRunning) return;
  if (_flowStepCursor >= FLOW_STAGES.length) {
    resetFlowDemo();
  }
  const st = FLOW_STAGES[_flowStepCursor];
  _flowSelectedId = st.id;
  _flowStates[st.id] = "running";
  renderFlowDiagram(false);
  renderFlowInspector(st.id);
  const logEl = $("#flow-demo-log");
  if (_flowStepCursor === 0 && logEl) logEl.innerHTML = "";
  for (const line of st.demoLogs) {
    flowLog(line);
  }
  await _sleep(350);
  _flowStates[st.id] = "done";
  _flowStepCursor += 1;
  renderFlowDiagram(false);
  renderFlowInspector(st.id);
}

async function runFlowDemo(withRetry = false) {
  if (_flowRunning) return;
  _flowCancelFlag = false;
  _flowStepCursor = 0;
  FLOW_STAGES.forEach(s => { _flowStates[s.id] = "idle"; });
  const logEl = $("#flow-demo-log");
  if (logEl) logEl.innerHTML = "";

  setFlowButtons(true);
  flowLog(withRetry
    ? "Starting Flowchart Demo (with Build Fail -> Auto-Fix Retry Loop)..."
    : "Starting Flowchart Demo (Docs -> Code -> Build -> Run -> Unit Test)...");

  const sequence = withRetry
    ? ["docs", "code", "build:fail", "code:fix", "build", "run", "unittest"]
    : ["docs", "code", "build", "run", "unittest"];

  for (const token of sequence) {
    if (_flowCancelFlag) break;
    const [id, mode] = token.split(":");
    const st = FLOW_STAGES.find(s => s.id === id);
    if (!st) continue;

    _flowSelectedId = id;
    _flowStates[id] = "running";
    renderFlowDiagram(mode === "fix");
    renderFlowInspector(id);

    if (mode === "fail") {
      flowLog("[Build] Running: tel b --start-deploy false -y");
      await _sleep(550);
      if (_flowCancelFlag) break;
      _flowStates[id] = "error";
      flowLog("[Build] ✗ Compile error: cannot find symbol method getAudioZoneId()", "flow-log-err");
      flowLog("[Retry Loop] ↩ Looping back to 💻 Code to auto-fix compile error...", "flow-log-warn");
      renderFlowDiagram(true);
      renderFlowInspector(id);
      await _sleep(900);
      continue;
    }

    if (mode === "fix") {
      flowLog("[Code] Inspecting compile error & fixing method signature...", "flow-log-warn");
      await _sleep(650);
      if (_flowCancelFlag) break;
      _flowStates[id] = "done";
      flowLog("[Code] ✓ Patch applied — re-triggering Build.", "flow-log-ok");
      renderFlowDiagram(true);
      renderFlowInspector(id);
      await _sleep(450);
      continue;
    }

    for (const line of st.demoLogs) {
      if (_flowCancelFlag) break;
      flowLog(line, line.includes("✓") ? "flow-log-ok" : "");
      await _sleep(320);
    }
    if (_flowCancelFlag) break;
    _flowStates[id] = "done";
    renderFlowDiagram(false);
    renderFlowInspector(id);
    await _sleep(250);
  }

  _flowStepCursor = FLOW_STAGES.length;
  setFlowButtons(false);
  if (!_flowCancelFlag) {
    const badge = $("#flow-status-badge");
    if (badge) {
      badge.textContent = "✓ Demo Passed";
      badge.className = "run-badge ok";
    }
  }
}
