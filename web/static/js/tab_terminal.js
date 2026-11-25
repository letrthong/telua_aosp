/* ==============================================================================
   Telua Web - Terminal & Pop-out Console Module
   ============================================================================== */
/* ---------------- Terminal Tab ---------------- */
const TERM_HISTORY_KEY = "telua_web_term_history";
const TERM_CWD_KEY = "telua_web_term_cwd";
let _termHistory = [];
let _termHistoryIdx = -1;
/* ---------------- Pop-out Console (màn hình riêng) ---------------- */
// Cửa sổ pop-out (popout.html) nhận output realtime từ tab chính qua
// BroadcastChannel (fallback: localStorage 'storage' event) — cho phép kéo
// console Pipeline / Terminal sang màn hình thứ 2.
let _popoutWin = null;
let _popoutBc = null;
try { _popoutBc = new BroadcastChannel("telua_console"); } catch { /* older browser */ }

function _popoutBroadcast(msg) {
  try {
    if (_popoutBc) _popoutBc.postMessage(msg);
    localStorage.setItem("telua_console_mirror", JSON.stringify(msg));
  } catch { /* ignore */ }
}

function _popoutSnapshot(title, html, badge) {
  try {
    localStorage.setItem("telua_console_snapshot", JSON.stringify({ title, html, badge }));
  } catch { /* ignore */ }
}

function openConsolePopout(defaultTitle) {
  if (_popoutWin && !_popoutWin.closed) {
    _popoutWin.focus();
    return;
  }
  _popoutWin = window.open("/static/popout.html", "telua_popout_console",
    "width=980,height=640,left=100,top=100");
  if (_popoutWin) {
    _popoutWin.addEventListener("load", () => {
      _popoutWin.document.title = defaultTitle || "Telua Pop-out Console";
    });
    // Theo dõi đóng cửa sổ pop-out → hiện lại console ở tab chính
    _startPopoutWatchdog();
    toast("Pop-out opened 🖥", "Console đã chuyển sang cửa sổ riêng — kéo sang màn hình thứ 2. Đóng cửa sổ đó để hiện lại tại đây.", "info", 4500);
  } else {
    toast("Popup blocked", "Trình duyệt đã chặn popup — hãy cho phép popup cho trang này.", "warn", 4000);
  }
}

// ---- Hide/restore console ở tab chính khi pop-out đang mở ----
let _popoutHideTimer = null;

function _popoutIsOpen() {
  return Boolean(_popoutWin && !_popoutWin.closed);
}

function _startPopoutWatchdog() {
  if (_popoutHideTimer) return;
  _popoutHideTimer = setInterval(() => {
    if (!_popoutIsOpen()) {
      clearInterval(_popoutHideTimer);
      _popoutHideTimer = null;
      _popoutWin = null;
      _restorePoppedConsoles();
    }
  }, 500);
}

// Ẩn bottom panel pipeline khi pop-out
function _hidePipelineBottomForPopout() {
  const panel = $("#pl-bottom-panel");
  if (!panel || panel.classList.contains("hidden")) return;
  panel.dataset.popoutHidden = "1";
  panel.classList.add("hidden");
}

// Ẩn terminal view khi pop-out (thay bằng placeholder)
function _hideTerminalForPopout() {
  const view = $("#view-terminal");
  if (!view || view.classList.contains("hidden")) return;
  view.dataset.popoutHidden = "1";
  view.classList.add("hidden");
  // Nếu terminal là tab đang active → chuyển sang placeholder pipelines
  if (!$("#tab-terminal")?.classList.contains("active")) return;
  const ph = $("#view-pipelines");
  if (ph) {
    ph.classList.remove("hidden");
    ph.dataset.popoutPlaceholder = "1";
  }
  syncTopTabs();
}

// Khôi phục console khi pop-out bị đóng
function _restorePoppedConsoles() {
  const panel = $("#pl-bottom-panel");
  if (panel && panel.dataset.popoutHidden === "1") {
    delete panel.dataset.popoutHidden;
    panel.classList.remove("hidden");
  }
  const view = $("#view-terminal");
  if (view && view.dataset.popoutHidden === "1") {
    delete view.dataset.popoutHidden;
    view.classList.remove("hidden");
    // Trả lại tab terminal nếu trước đó nó đang active
    const ph = $("#view-pipelines");
    if (ph && ph.dataset.popoutPlaceholder === "1") {
      delete ph.dataset.popoutPlaceholder;
      ph.classList.add("hidden");
      syncTopTabs();
    }
  }
  toast("Console restored 💻", "Cửa sổ pop-out đã đóng — console hiện lại ở tab chính.", "info", 3000);
}

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
  const broadcastTerm = (html, badge) => {
    if (_popoutIsOpen()) {
      _popoutBroadcast({ type: "output", title: "💻 Web CLI Terminal", html, badge });
      _popoutSnapshot("💻 Web CLI Terminal", html, badge);
    }
  };
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
          broadcastTerm(outEl ? outEl.innerHTML : "", { text: `⏳ Running… (${elapsed}s)`, cls: "running" });
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
      broadcastTerm(outEl ? outEl.innerHTML : "", { text: _termStoppedByUser ? `⏹ Stopped (${elapsed}s)` : (exitCode === 0 ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${exitCode} (${elapsed}s)`), cls: _termStoppedByUser ? "err" : (exitCode === 0 ? "ok" : "err") });
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
        broadcastTerm(outEl ? outEl.innerHTML : "", { text: fb.ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${fb.exit_code} (${elapsed}s)`, cls: fb.ok ? "ok" : "err" });
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
    broadcastTerm(outEl ? outEl.innerHTML : "", { text: ok ? `✔ Exit 0 (${elapsed}s)` : `✖ Exit ${data.exit_code} (${elapsed}s)`, cls: ok ? "ok" : "err" });
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
      broadcastTerm(outEl ? outEl.innerHTML : "", { text: `⏹ Stopped (Ctrl+C · ${elapsed}s)`, cls: "err" });
      if (badge) {
        badge.textContent = `⏹ Stopped (Ctrl+C · ${elapsed}s)`;
        badge.className = "run-badge err";
      }
    } else {
      if (outEl) {
        outEl.innerHTML = baseHtml + `<span style="color:#f85149">[ERROR] ${esc(err.message)}</span>\n`;
        outEl.scrollTop = outEl.scrollHeight;
      }
      broadcastTerm(outEl ? outEl.innerHTML : "", { text: "✖ Error", cls: "err" });
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

