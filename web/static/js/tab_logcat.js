/* ==============================================================================
   Telua Web - Logcat Controller & Realtime Filtering Module
   ============================================================================== */
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
      const adb = state.status?.adb_devices || [];
      if (adb.length === 0 || adb.some(d => d.state === "offline")) {
        $("#logcat-adb-offline-banner")?.classList.remove("hidden");
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

