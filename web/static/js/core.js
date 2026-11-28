/* ==============================================================================
   Telua Web - Core & Shell Module (Vanilla JS)
   State, API helpers, Statusbar, Toast, Modals & Global Tab Router
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
}

/* ---------------- Settings: tab visibility (default: all visible) -------- */
const TABS_VISIBLE_KEY = "telua_web_tabs_visible";   // JSON { tabId: bool } — missing = visible (default)
const SETTINGS_TABS = [
  { id: "files", icon: "📄", label: "Files", desc: "Browse & edit config files" },
  { id: "pipelines", icon: "⚡", label: "Pipelines", desc: "MY_CMD_* / MULTI / CAR / DUMP" },
  { id: "system", icon: "🖥", label: "System", desc: "System & Docker CLI pipelines" },
  { id: "aosp", icon: "🤖", label: "AOSP", desc: "Build, Deploy & Test Center" },
  { id: "terminal", icon: "💻", label: "Terminal", desc: "Interactive Web CLI" },
  { id: "logcat", icon: "📱", label: "Logcat", desc: "Live logcat stream & filter" },
  { id: "mirror", icon: "🖥", label: "Mirror", desc: "Screen mirroring & control" },
  { id: "power", icon: "⚡", label: "Power", desc: "Target power controls" },
  { id: "docs", icon: "📚", label: "Docs", desc: "Sphinx Doc-as-Code" },
  { id: "bi", icon: "📊", label: "BI Studio", desc: "Excel → JSON & Dashboard" },
  { id: "ai", icon: "🤖", label: "AI Agent", desc: "LLM chat + tel/adb tools" },
  { id: "flow", icon: "🔀", label: "Flow", desc: "Requirement → Docs → Code → Build → Run → UnitTest demo" },
];

function loadTabsVisible() {
  try {
    const raw = localStorage.getItem(TABS_VISIBLE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveTabsVisible(map) {
  try { localStorage.setItem(TABS_VISIBLE_KEY, JSON.stringify(map)); } catch { /* ignore */ }
}

function isTabVisible(tabId) {
  const map = loadTabsVisible();
  return map[tabId] !== false; // default: visible
}

function applyTabVisibility() {
  const map = loadTabsVisible();
  SETTINGS_TABS.forEach(t => {
    const btn = $(`#tab-${t.id}`);
    if (btn) btn.classList.toggle("hidden", map[t.id] === false);
  });
}

function renderSettingsTabList() {
  const list = $("#settings-tab-list");
  if (!list) return;
  const map = loadTabsVisible();
  list.innerHTML = "";
  SETTINGS_TABS.forEach(t => {
    const visible = map[t.id] !== false;
    const item = document.createElement("label");
    item.className = "settings-tab-item";
    item.innerHTML =
      `<input type="checkbox" data-tab="${t.id}" ${visible ? "checked" : ""}>` +
      `<span class="settings-tab-icon">${t.icon}</span>` +
      `<span>${t.label}</span>` +
      `<span class="settings-tab-desc">${t.desc}</span>`;
    item.querySelector("input").addEventListener("change", (e) => {
      const m = loadTabsVisible();
      m[t.id] = e.target.checked;
      saveTabsVisible(m);
      applyTabVisibility();
      // If the active tab was just hidden, fall back to the first visible tab.
      if (!e.target.checked) {
        const activeBtn = document.querySelector(".tabs .tab.active");
        if (activeBtn && activeBtn.id === `tab-${t.id}`) {
          const firstVisible = SETTINGS_TABS.find(x => isTabVisible(x.id));
          if (firstVisible) switchTab(firstVisible.id);
        }
      }
    });
    list.appendChild(item);
  });
}

function openSettingsModal() {
  const sel = $("#settings-theme-select");
  if (sel) {
    let cur = "dark";
    try { cur = localStorage.getItem(THEME_KEY) || "dark"; } catch { /* ignore */ }
    sel.value = THEME_LABELS[cur] ? cur : "dark";
  }
  renderSettingsTabList();
  $("#modal-settings")?.classList.remove("hidden");
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
  cancelText = "Cancel",
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
  const cancelBtn = $("#btn-confirm-cancel");
  if (cancelBtn) cancelBtn.textContent = cancelText;
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
  const verEl = $("#settings-version");
  if (verEl) verEl.innerHTML = `v<b>${esc(s.version)}</b>`;
  $("#chip-project").innerHTML = `project: <b>${esc(s.active_project || "—")}</b>`;
  const adb = s.adb_devices || [];
  const chipAdb = $("#chip-adb");
  const isAdbOffline = adb.length === 0 || adb.some(d => d.state === "offline");
  if (chipAdb) {
    chipAdb.classList.add("clickable");
    chipAdb.style.cursor = "pointer";
    if (adb.length === 0) {
      chipAdb.innerHTML = `adb: <b>offline</b> <span class="adb-chip-btn" title="Click for Windows Remote PC bat helper">⚡ .bat</span>`;
      chipAdb.className = "chip err clickable";
      chipAdb.title = "No ADB devices connected. Click to view Windows Remote PC helper (adb_remote_pc.bat).";
    } else if (adb.some(d => d.state === "offline")) {
      chipAdb.innerHTML = `adb: <b>${adb.length} (offline)</b> <span class="adb-chip-btn" title="Click for Windows Remote PC bat helper">⚡ .bat</span>`;
      chipAdb.className = "chip warn clickable";
      chipAdb.title = "ADB device is offline. Click to view Windows Remote PC helper (adb_remote_pc.bat).";
    } else {
      chipAdb.innerHTML = `adb: <b>${adb.length}</b> ${adb.map(d => esc(d.serial)).join(", ")}`;
      chipAdb.className = "chip ok clickable";
      chipAdb.title = `Connected ADB devices: ${adb.map(d => d.serial).join(", ")}. Click to view ADB Remote Helper.`;
    }
  }

  // Update Logcat offline suggestion banner if present
  const logcatOfflineBanner = $("#logcat-adb-offline-banner");
  if (logcatOfflineBanner) {
    logcatOfflineBanner.classList.toggle("hidden", !isAdbOffline);
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

/* ---------------- ADB Offline & Remote Script Helper ---------------- */
const DEFAULT_ADB_REMOTE_BAT_PATH = "D:\\wmshare\\telua_aosp\\scripts\\windows\\adb_remote_pc.bat";

function getAdbRemoteScriptPath() {
  return state.status?.adb_remote_script?.path || DEFAULT_ADB_REMOTE_BAT_PATH;
}

function openAdbOfflineModal() {
  const modal = $("#modal-adb-offline-help");
  if (!modal) return;
  const pathEl = $("#adb-help-script-path");
  const fullPath = getAdbRemoteScriptPath();
  if (pathEl) pathEl.textContent = fullPath;

  const metaEl = $("#adb-help-status-meta");
  const adb = state.status?.adb_devices || [];
  if (metaEl) {
    if (adb.length === 0) {
      metaEl.innerHTML = `Status: <span style="color:var(--red,#f85149);font-weight:600;">● No devices connected (0 devices)</span>`;
    } else if (adb.some(d => d.state === "offline")) {
      metaEl.innerHTML = `Status: <span style="color:var(--yellow,#d29922);font-weight:600;">● Device is Offline (${adb.map(d => d.serial).join(", ")})</span>`;
    } else {
      metaEl.innerHTML = `Status: <span style="color:var(--green,#3fb950);font-weight:600;">● Online (${adb.map(d => d.serial).join(", ")})</span>`;
    }
  }
  modal.classList.remove("hidden");
}

function closeAdbOfflineModal() {
  $("#modal-adb-offline-help")?.classList.add("hidden");
}

async function copyAdbScriptPath() {
  const p = getAdbRemoteScriptPath();
  try {
    await navigator.clipboard.writeText(p);
    toast("Path Copied", p, "info", 3000);
  } catch {
    toast("Copy Failed", "Please select the path text manually and press Ctrl+C.", "warn");
  }
}

async function copyAdbScriptCmd() {
  const cmd = $("#adb-help-cmd-text")?.textContent || "ssh -R 5037:127.0.0.1:5037 %USERNAME%@10.184.129.24 -p 22";
  try {
    await navigator.clipboard.writeText(cmd.trim());
    toast("SSH Command Copied", cmd.trim(), "info", 3000);
  } catch {
    toast("Copy Failed", "Please select the command text and press Ctrl+C.", "warn");
  }
}

async function refreshAdbStatusFromModal() {
  const metaEl = $("#adb-help-status-meta");
  if (metaEl) metaEl.textContent = "Checking device connection...";
  try {
    const s = await api("/api/status");
    renderStatus(s);
    const adb = s.adb_devices || [];
    if (metaEl) {
      if (adb.length === 0) {
        metaEl.innerHTML = `Status: <span style="color:var(--red,#f85149);font-weight:600;">● Still no devices found (0 devices)</span>`;
        toast("ADB Still Offline", "No device detected. Make sure you ran the .bat script on Windows and the CMD window remains open.", "warn");
      } else if (adb.some(d => d.state === "offline")) {
        metaEl.innerHTML = `Status: <span style="color:var(--yellow,#d29922);font-weight:600;">● Device detected but Offline</span>`;
        toast("Device Offline", "Device is detected but offline. Please unlock device screen and accept USB Debugging authorization.", "warn");
      } else {
        metaEl.innerHTML = `Status: <span style="color:var(--green,#3fb950);font-weight:600;">● Connected successfully! (${adb.map(d => d.serial).join(", ")})</span>`;
        toast("ADB Connected! ✓", `Detected: ${adb.map(d => d.serial).join(", ")}`, "ok");
      }
    }
  } catch (err) {
    if (metaEl) metaEl.textContent = "Check error: " + err.message;
    toast("ADB Check Error", err.message, "err");
  }
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


/* ---------------- Wiring ---------------- */
function switchTab(tab) {
  const isFiles = tab === "files";
  const isAosp = tab === "aosp";
  const isTerminal = tab === "terminal";
  const isLogcat = tab === "logcat";
  const isDocs = tab === "docs";
  const isBi = tab === "bi";
  const isAi = tab === "ai";
  const isFlow = tab === "flow";
  const isMirror = tab === "mirror";
  const isPower = tab === "power";
  const isPipelinesView = !isFiles && !isAosp && !isTerminal && !isLogcat && !isDocs && !isBi && !isAi && !isFlow && !isMirror && !isPower;

  // Collapse Config Files sidebar in Docs, AOSP, Terminal, Logcat, BI, Mirror, Power & Flow views to give maximum full-width canvas
  $(".layout")?.classList.toggle("no-sidebar", isDocs || isAosp || isTerminal || isLogcat || isBi || isAi || isFlow || isMirror || isPower);

  $("#view-files")?.classList.toggle("hidden", !isFiles);
  $("#view-aosp")?.classList.toggle("hidden", !isAosp);
  $("#view-pipelines")?.classList.toggle("hidden", !isPipelinesView);
  $("#view-terminal")?.classList.toggle("hidden", !isTerminal);
  $("#view-logcat")?.classList.toggle("hidden", !isLogcat);
  $("#view-docs")?.classList.toggle("hidden", !isDocs);
  $("#view-bi")?.classList.toggle("hidden", !isBi);
  $("#view-ai")?.classList.toggle("hidden", !isAi);
  $("#view-flow")?.classList.toggle("hidden", !isFlow);
  $("#view-mirror")?.classList.toggle("hidden", !isMirror);
  $("#view-power")?.classList.toggle("hidden", !isPower);
  if (!isMirror && typeof _mirrorKeepInBackground !== "undefined" && !_mirrorKeepInBackground) {
    if (typeof stopMirrorStream === "function") stopMirrorStream();
  }
  if (tab === "system") {
    switchPipelineSource("system");
  } else if (tab === "pipelines" && (state.plSource === "system" || state.plSource === "docker")) {
    switchPipelineSource(_lastNonSystemPlSource || "my");
  }
  syncTopTabs();
  renderFiles($("#search")?.value || "");
  if (isPower) {
    if (typeof initPowerTab === "function") initPowerTab();
    return;
  }
  if (isMirror) {
    if (typeof initMirror === "function") initMirror();
    return;
  }
  if (isBi) {
    initBIDashboard();
  }
  if (isAi) {
    initAI();
    setTimeout(() => $("#ai-input")?.focus(), 40);
    return;
  }
  if (isFlow) {
    if (typeof initFlowTab === "function") initFlowTab();
    return;
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

