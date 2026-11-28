/* ==============================================================================
   Telua Web - Tasks Manager Tab Module (Vanilla JS)
   Manages Today Focus, Current Sprint (1-2 Weeks), and 3-Month Roadmap.
   Default view focuses on the current active horizon (Today + 1-2w Sprint).
   Supports manual editing (status, 0-100% progress, Today pin) and AI Agent sync.
   ============================================================================== */
"use strict";

const TASKS_FILTER_KEY = "telua_web_tasks_filter";

let _tasksInitialized = false;
let _tasksScope = "current"; // "current" | "today" | "sprint_2w" | "quarter_3m" | "all"
let _tasksYear = "";         // "" (active/current) | "2026"
let _tasksMonth = "";        // "" | "2026-11"
let _tasksPeriods = { years: [], months: [] };
let _tasksHideDone = false;
let _tasksSearch = "";
let _tasksList = [];
let _tasksStats = {};
let _taskSliderTimers = new Map();
let _taskDetailId = "";

function _saveTasksFilterState() {
  try {
    localStorage.setItem(TASKS_FILTER_KEY, JSON.stringify({
      scope: _tasksScope,
      year: _tasksYear,
      month: _tasksMonth,
      hideDone: _tasksHideDone,
    }));
  } catch { /* ignore */ }
}

function _restoreTasksFilterState() {
  try {
    const raw = localStorage.getItem(TASKS_FILTER_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (saved && typeof saved === "object") {
      if (saved.scope) _tasksScope = saved.scope;
      if (typeof saved.year === "string") _tasksYear = saved.year;
      if (typeof saved.month === "string") _tasksMonth = saved.month;
      if (typeof saved.hideDone === "boolean") _tasksHideDone = saved.hideDone;
    }
  } catch { /* ignore */ }
}

const TASK_HORIZON_META = {
  today: { label: "☀ Today", color: "#e3b341", bg: "rgba(227,179,65,0.16)" },
  sprint_2w: { label: "🏃 1–2w Sprint", color: "#58a6ff", bg: "rgba(88,166,255,0.15)" },
  quarter_3m: { label: "🗓 3M Roadmap", color: "#bc8cff", bg: "rgba(188,140,255,0.15)" },
};

const TASK_PRIORITY_META = {
  high: { label: "High", dot: "#f85149" },
  medium: { label: "Med", dot: "#e3b341" },
  low: { label: "Low", dot: "#58a6ff" },
};

const TASK_STATUS_LABELS = {
  todo: "Todo",
  in_progress: "In Progress",
  blocked: "Blocked",
  done: "Done",
};

function _taskBarColor(status, progress) {
  if (status === "done" || progress >= 100) return "#3fb950";
  if (status === "blocked") return "#f85149";
  if (progress > 0 || status === "in_progress") return "#58a6ff";
  return "#6e7681";
}

function renderTasksStats(stats) {
  _tasksStats = stats || {};
  const s = _tasksStats;
  const todayBadge = $("#tasks-stat-today");
  const sprintBadge = $("#tasks-stat-sprint");
  const quarterBadge = $("#tasks-stat-quarter");
  if (todayBadge) {
    todayBadge.textContent = `☀ Today: ${s.today_done || 0}/${s.today_count || 0} (${s.today_avg_progress || 0}%)`;
  }
  if (sprintBadge) {
    sprintBadge.textContent = `🏃 1–2w: ${s.sprint_done || 0}/${s.sprint_count || 0} (${s.sprint_avg_progress || 0}%)`;
  }
  if (quarterBadge) {
    quarterBadge.textContent = `🗓 3M Roadmap: ${s.quarter_count || 0}`;
  }

  // Update Today Focus summary strip
  const strip = $("#tasks-today-strip");
  if (strip) {
    const showStrip = _tasksScope === "current" || _tasksScope === "today";
    strip.classList.toggle("hidden", !showStrip);
    if (showStrip) {
      const pct = s.today_avg_progress || 0;
      const fill = $("#tasks-today-bar-fill");
      const meta = $("#tasks-today-summary-text");
      if (fill) fill.style.width = `${pct}%`;
      if (meta) {
        const cnt = s.today_count || 0;
        const done = s.today_done || 0;
        const ip = s.in_progress_count || 0;
        const blk = s.blocked_count || 0;
        meta.textContent = cnt > 0
          ? `${done}/${cnt} completed (${pct}%) · ${ip} in progress` + (blk ? ` · ${blk} blocked` : "")
          : "No tasks pinned for Today yet — pin a sprint task with ☀ Today, add one below, or click 🤖 AI Plan Today.";
      }
    }
  }
}

function renderTasksList() {
  const container = $("#tasks-list");
  if (!container) return;

  const q = _tasksSearch.trim().toLowerCase();
  const visible = (_tasksList || []).filter(t => {
    if (!q) return true;
    const hay = `${t.title || ""} ${t.notes || ""} ${t.project || ""} ${t.id || ""}`.toLowerCase();
    return hay.includes(q);
  });

  if (visible.length === 0) {
    const hiddenTotal = (_tasksStats.total || 0);
    const quarterCnt = (_tasksStats.quarter_count || 0);
    const extraBtn = (_tasksScope !== "all" && hiddenTotal > 0)
      ? `<div style="margin-top:10px;">` +
          `<button class="btn primary" id="btn-tasks-show-all-hint" style="font-size:11px;">` +
            `📋 Xem tất cả ${hiddenTotal} task` + (quarterCnt ? ` (gồm ${quarterCnt} task 3M Roadmap)` : "") +
          `</button>` +
        `</div>`
      : "";
    const scopeHint = _tasksScope === "current"
      ? "Chưa có task nào trong tuần / sprint hiện tại (1–2 tuần). Thêm nhanh ở ô trên hoặc nhờ 🤖 AI Agent tạo kế hoạch!"
      : "Không có task nào khớp bộ lọc hiện tại.";
    container.innerHTML =
      `<div class="flow-card" style="text-align:center;padding:28px 16px;opacity:0.9;">` +
        `<div style="font-size:24px;margin-bottom:6px;">📋</div>` +
        `<div class="meta">${esc(scopeHint)}</div>` +
        extraBtn +
      `</div>`;
    $("#btn-tasks-show-all-hint")?.addEventListener("click", () => {
      _tasksScope = "all";
      _tasksYear = "";
      _tasksMonth = "";
      _saveTasksFilterState();
      document.querySelectorAll("#tasks-scope-bar .src-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.scope === "all")
      );
      renderTasksPeriodSelects();
      loadTasks();
    });
    return;
  }

  container.innerHTML = visible.map(t => {
    const hm = TASK_HORIZON_META[t.horizon] || TASK_HORIZON_META.sprint_2w;
    const pm = TASK_PRIORITY_META[t.priority] || TASK_PRIORITY_META.medium;
    const prog = Math.max(0, Math.min(100, parseInt(t.progress || 0, 10)));
    const barColor = _taskBarColor(t.status, prog);
    const isDone = t.status === "done";
    const isToday = Boolean(t.is_today) || t.horizon === "today";

    const statusOpts = Object.entries(TASK_STATUS_LABELS).map(([k, lbl]) =>
      `<option value="${k}" ${t.status === k ? "selected" : ""}>${lbl}</option>`
    ).join("");

    const aiBadge = t.created_by === "ai"
      ? `<span class="chip" style="font-size:10px;padding:1px 6px;background:rgba(163,113,247,0.18);color:#d2a8ff;">🤖 AI</span>`
      : "";
    const dueChip = t.due_date
      ? `<span class="chip mono" style="font-size:10px;padding:1px 6px;" title="Due: ${esc(t.due_date)}">📅 ${esc(fmtDateTimeDM(t.due_date))}</span>`
      : "";
    const createdChip = t.created_at
      ? `<span class="chip mono" style="font-size:10px;padding:1px 6px;opacity:0.85;" title="Created: ${esc(fmtDateTimeDM(t.created_at))}${t.updated_at ? ` | Updated: ${esc(fmtDateTimeDM(t.updated_at))}` : ""}">🕒 ${esc(fmtDateTimeDM(t.created_at))}</span>`
      : "";
    const doneChip = t.completed_at
      ? `<span class="chip ok mono" style="font-size:10px;padding:1px 6px;">✓ ${esc(fmtDateTimeDM(t.completed_at))}</span>`
      : "";
    const projChip = t.project
      ? `<span class="chip mono" style="font-size:10px;padding:1px 6px;color:var(--accent);">#${esc(t.project)}</span>`
      : "";
    const cmtCount = Array.isArray(t.comments) ? t.comments.length : 0;
    const cmtChip = cmtCount > 0
      ? `<span class="chip mono" style="font-size:10px;padding:1px 6px;" title="${cmtCount} comment(s)">💬 ${cmtCount}</span>`
      : "";
    const notesHtml = t.notes
      ? `<div class="meta" style="font-size:11px;margin-top:4px;white-space:pre-wrap;line-height:1.45;">${esc(t.notes)}</div>`
      : "";

    return `
      <div class="flow-card task-card" data-task-id="${esc(t.id)}"
        style="padding:11px 14px;border-left:3px solid ${barColor};opacity:${isDone ? "0.72" : "1"};cursor:pointer;"
        title="Click to view full task details">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap;">
          <div style="flex:1;min-width:220px;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <span title="Priority: ${pm.label}" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${pm.dot};flex-shrink:0;"></span>
              <span style="font-weight:600;font-size:13px;${isDone ? "text-decoration:line-through;" : ""}">${esc(t.title)}</span>
              <span class="chip" style="font-size:10px;padding:1px 6px;background:${hm.bg};color:${hm.color};">${hm.label}</span>
              ${aiBadge}
              ${projChip}
              ${dueChip}
              ${createdChip}
              ${doneChip}
              ${cmtChip}
            </div>
            ${notesHtml}
          </div>

          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;flex-shrink:0;">
            <button class="btn task-btn-today" data-id="${esc(t.id)}" data-today="${isToday ? "1" : "0"}"
              style="font-size:11px;padding:3px 8px;${isToday ? "background:rgba(227,179,65,0.2);border-color:rgba(227,179,65,0.55);color:#e3b341;" : ""}"
              title="Pin/unpin to Today Focus">☀ Today</button>
            <select class="theme-select task-status-select" data-id="${esc(t.id)}"
              style="font-size:11px;padding:3px 6px;" title="Task status">${statusOpts}</select>
            <button class="btn ghost task-btn-edit" data-id="${esc(t.id)}" style="font-size:11px;padding:3px 7px;" title="Edit task">✎</button>
            <button class="btn ghost task-btn-del" data-id="${esc(t.id)}" style="font-size:11px;padding:3px 7px;color:#f85149;" title="Delete task">🗑</button>
          </div>
        </div>

        <!-- Progress bar & manual quick controls -->
        <div style="display:flex;align-items:center;gap:10px;margin-top:9px;flex-wrap:wrap;">
          <div style="flex:1;min-width:140px;display:flex;align-items:center;gap:8px;">
            <input type="range" min="0" max="100" step="5" value="${prog}"
              class="task-progress-slider" data-id="${esc(t.id)}"
              style="flex:1;cursor:pointer;accent-color:${barColor};">
            <span class="mono task-progress-label" style="font-size:11px;font-weight:700;min-width:36px;text-align:right;color:${barColor};">${prog}%</span>
          </div>
          <div style="display:flex;gap:4px;flex-shrink:0;">
            ${[25, 50, 75, 100].map(v =>
              `<button class="btn ghost task-btn-pct" data-id="${esc(t.id)}" data-pct="${v}"
                style="font-size:10px;padding:2px 6px;${prog === v ? "border-color:var(--accent);color:var(--accent);" : ""}">${v}%</button>`
            ).join("")}
          </div>
        </div>
      </div>
    `;
  }).join("");

  // Click anywhere on card (outside interactive controls) -> open Task Detail Dialog
  container.querySelectorAll(".task-card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest("button, select, input, a, label")) return;
      const t = _tasksList.find(x => x.id === card.dataset.taskId);
      if (t) openTaskDetailModal(t);
    });
  });

  // Wire card controls
  container.querySelectorAll(".task-status-select").forEach(sel => {
    sel.addEventListener("change", (e) => {
      patchTask(e.target.dataset.id, { status: e.target.value });
    });
  });

  container.querySelectorAll(".task-btn-today").forEach(btn => {
    btn.addEventListener("click", () => {
      const next = btn.dataset.today !== "1";
      patchTask(btn.dataset.id, { is_today: next });
    });
  });

  container.querySelectorAll(".task-progress-slider").forEach(slider => {
    slider.addEventListener("input", (e) => {
      const val = parseInt(e.target.value, 10);
      const card = e.target.closest(".task-card");
      const lbl = card?.querySelector(".task-progress-label");
      if (lbl) lbl.textContent = `${val}%`;
      const id = e.target.dataset.id;
      clearTimeout(_taskSliderTimers.get(id));
      _taskSliderTimers.set(id, setTimeout(() => {
        patchTask(id, { progress: val });
      }, 250));
    });
  });

  container.querySelectorAll(".task-btn-pct").forEach(btn => {
    btn.addEventListener("click", () => {
      patchTask(btn.dataset.id, { progress: parseInt(btn.dataset.pct, 10) });
    });
  });

  container.querySelectorAll(".task-btn-edit").forEach(btn => {
    btn.addEventListener("click", () => {
      const t = _tasksList.find(x => x.id === btn.dataset.id);
      if (t) openTaskEditModal(t);
    });
  });

  container.querySelectorAll(".task-btn-del").forEach(btn => {
    btn.addEventListener("click", async () => {
      const t = _tasksList.find(x => x.id === btn.dataset.id);
      const ok = await confirmDialog({
        title: "🗑 Delete Task",
        message: `Delete task "${t ? t.title : btn.dataset.id}"?`,
        confirmText: "🗑 Delete",
        icon: "🗑",
      });
      if (!ok) return;
      try {
        const res = await api(`/api/tasks/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
        if (res.stats) renderTasksStats(res.stats);
        await loadTasks();
        toast("Task Deleted", "Task removed.", "ok", 2200);
      } catch (err) {
        toast("Delete Failed", err.message, "err");
      }
    });
  });
}

function renderTasksPeriodSelects(periods) {
  if (periods) _tasksPeriods = periods;
  const ySel = $("#tasks-filter-year");
  const mSel = $("#tasks-filter-month");
  const years = _tasksPeriods.years || [];
  const allMonths = _tasksPeriods.months || [];

  if (ySel) {
    ySel.innerHTML = `<option value="">📅 Active (Now)</option>` +
      years.map(y => `<option value="${esc(y)}" ${y === _tasksYear ? "selected" : ""}>📆 Year ${esc(y)}</option>`).join("");
  }
  if (mSel) {
    const monthsForYear = _tasksYear ? allMonths.filter(m => m.startsWith(_tasksYear + "-")) : allMonths;
    if (_tasksMonth && !monthsForYear.includes(_tasksMonth)) _tasksMonth = "";
    mSel.innerHTML = `<option value="">All Months</option>` +
      monthsForYear.map(m => `<option value="${esc(m)}" ${m === _tasksMonth ? "selected" : ""}>🗓 ${esc(m)}</option>`).join("");
  }
}

async function loadTasks() {
  try {
    const effectiveHorizon = (_tasksYear || _tasksMonth) && _tasksScope === "current" ? "all" : _tasksScope;
    const params = new URLSearchParams({
      horizon: effectiveHorizon,
      include_done: _tasksHideDone ? "0" : "1",
      _t: String(Date.now()),
    });
    if (_tasksYear) params.set("year", _tasksYear);
    if (_tasksMonth) params.set("month", _tasksMonth);
    const res = await api(`/api/tasks?${params.toString()}`, { cache: "no-store" });
    _tasksList = res.tasks || [];
    if (res.periods) renderTasksPeriodSelects(res.periods);
    renderTasksStats(res.stats || {});
    renderTasksList();
    // Keep detail dialog in sync if it is currently open
    if (_taskDetailId && !$("#modal-task-detail")?.classList.contains("hidden")) {
      const updated = _tasksList.find(x => x.id === _taskDetailId);
      if (updated) openTaskDetailModal(updated);
    }
  } catch (err) {
    toast("Tasks Load Failed", err.message, "err");
  }
}

function openTaskDetailModal(task) {
  if (!task) return;
  _taskDetailId = task.id;
  const hm = TASK_HORIZON_META[task.horizon] || TASK_HORIZON_META.sprint_2w;
  const pm = TASK_PRIORITY_META[task.priority] || TASK_PRIORITY_META.medium;
  const prog = Math.max(0, Math.min(100, parseInt(task.progress || 0, 10)));
  const barColor = _taskBarColor(task.status, prog);
  const statusLabel = TASK_STATUS_LABELS[task.status] || task.status || "Todo";
  const isToday = Boolean(task.is_today) || task.horizon === "today";

  const titleEl = $("#task-detail-title");
  if (titleEl) titleEl.textContent = task.title || "(Untitled)";

  const badgesEl = $("#task-detail-badges");
  if (badgesEl) {
    badgesEl.innerHTML =
      `<span class="chip mono" style="font-size:10px;">${esc(task.id)}</span>` +
      `<span class="chip" style="font-size:10px;background:${hm.bg};color:${hm.color};">${hm.label}</span>` +
      `<span class="chip" style="font-size:10px;color:${barColor};">● ${esc(statusLabel)}</span>` +
      `<span class="chip" style="font-size:10px;"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${pm.dot};margin-right:4px;"></span>${pm.label}</span>` +
      (isToday ? `<span class="chip" style="font-size:10px;background:rgba(227,179,65,0.2);color:#e3b341;">☀ Today Focus</span>` : "") +
      (task.created_by === "ai"
        ? `<span class="chip" style="font-size:10px;background:rgba(163,113,247,0.18);color:#d2a8ff;">🤖 Created by AI</span>`
        : `<span class="chip" style="font-size:10px;">👤 Manual</span>`);
  }

  const pctEl = $("#task-detail-progress-pct");
  if (pctEl) {
    pctEl.textContent = `${prog}%`;
    pctEl.style.color = barColor;
  }
  const barEl = $("#task-detail-progress-bar");
  if (barEl) {
    barEl.style.width = `${prog}%`;
    barEl.style.background = barColor;
  }
  const pctBtnsEl = $("#task-detail-quick-pcts");
  if (pctBtnsEl) {
    pctBtnsEl.innerHTML = [0, 25, 50, 75, 100].map(v =>
      `<button class="btn ghost task-detail-pct-btn" data-pct="${v}" style="font-size:11px;padding:3px 9px;${prog === v ? "border-color:var(--accent);color:var(--accent);" : ""}">${v}%</button>`
    ).join("");
    pctBtnsEl.querySelectorAll(".task-detail-pct-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        patchTask(task.id, { progress: parseInt(btn.dataset.pct, 10) });
      });
    });
  }

  const metaEl = $("#task-detail-meta");
  if (metaEl) {
    const fmt = (s) => s ? esc(fmtDateTimeDM(s)) : "—";
    metaEl.innerHTML =
      `<div><span class="meta">📁 Project:</span> <code class="mono">${esc(task.project || "—")}</code></div>` +
      `<div><span class="meta">📅 Due Date:</span> <code class="mono">${esc(task.due_date || "—")}</code></div>` +
      `<div><span class="meta">🕒 Created:</span> <span class="mono">${fmt(task.created_at)}</span></div>` +
      `<div><span class="meta">🔄 Updated:</span> <span class="mono">${fmt(task.updated_at)}</span></div>` +
      (task.completed_at
        ? `<div style="grid-column:1 / -1;"><span class="meta">✅ Completed:</span> <span class="mono" style="color:#3fb950;">${fmt(task.completed_at)}</span></div>`
        : "");
  }

  const notesEl = $("#task-detail-notes");
  if (notesEl) {
    if (task.notes && task.notes.trim()) {
      notesEl.textContent = task.notes;
      notesEl.style.opacity = "1";
    } else {
      notesEl.textContent = "(No notes added yet. Click ✎ Edit to add details or checklist.)";
      notesEl.style.opacity = "0.65";
    }
  }

  renderTaskDetailComments(task);
  $("#modal-task-detail")?.classList.remove("hidden");
}

function renderTaskDetailComments(task) {
  const listEl = $("#task-detail-comments-list");
  const cntEl = $("#task-detail-comment-count");
  const comments = Array.isArray(task?.comments) ? task.comments : [];
  if (cntEl) cntEl.textContent = String(comments.length);
  if (!listEl) return;

  if (comments.length === 0) {
    listEl.innerHTML = `<div class="meta" style="font-size:11px;padding:6px 8px;opacity:0.7;">(No comments yet — post a note below or ask AI Agent to log findings.)</div>`;
    return;
  }

  listEl.innerHTML = comments.map(c => {
    const isAi = c.author === "ai";
    const badge = isAi
      ? `<span class="chip" style="font-size:10px;padding:1px 6px;background:rgba(163,113,247,0.18);color:#d2a8ff;">🤖 AI</span>`
      : `<span class="chip" style="font-size:10px;padding:1px 6px;background:rgba(88,166,255,0.16);color:#58a6ff;">👤 User</span>`;
    const ts = c.created_at ? esc(fmtDateTimeDM(c.created_at)) : "";
    return `
      <div style="background:var(--bg);border:1px solid var(--border);border-left:3px solid ${isAi ? "#bc8cff" : "#58a6ff"};border-radius:6px;padding:7px 10px;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:4px;">
          <div style="display:flex;align-items:center;gap:6px;">
            ${badge}
            <span class="meta mono" style="font-size:10px;">${ts}</span>
          </div>
          <button class="btn ghost task-cmt-del" data-cid="${esc(c.id)}" style="font-size:10px;padding:1px 5px;opacity:0.7;" title="Delete comment">✕</button>
        </div>
        <div style="font-size:12px;line-height:1.45;white-space:pre-wrap;word-break:break-word;">${esc(c.text || "")}</div>
      </div>
    `;
  }).join("");

  listEl.scrollTop = listEl.scrollHeight;
  listEl.querySelectorAll(".task-cmt-del").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!_taskDetailId) return;
      try {
        const res = await api(`/api/tasks/${encodeURIComponent(_taskDetailId)}/comments/${encodeURIComponent(btn.dataset.cid)}`, {
          method: "DELETE",
        });
        if (res.task) renderTaskDetailComments(res.task);
        await loadTasks();
      } catch (err) {
        toast("Delete Comment Failed", err.message, "err");
      }
    });
  });
}

async function postTaskDetailComment() {
  if (!_taskDetailId) return;
  const inp = $("#task-detail-comment-input");
  const text = (inp?.value || "").trim();
  if (!text) {
    inp?.focus();
    return;
  }
  const btn = $("#btn-task-detail-comment-send");
  if (btn) btn.disabled = true;
  try {
    const res = await api(`/api/tasks/${encodeURIComponent(_taskDetailId)}/comments`, {
      method: "POST",
      body: JSON.stringify({ text, author: "user" }),
    });
    if (inp) inp.value = "";
    if (res.task) renderTaskDetailComments(res.task);
    await loadTasks();
  } catch (err) {
    toast("Post Comment Failed", err.message, "err");
  } finally {
    if (btn) btn.disabled = false;
    inp?.focus();
  }
}

async function patchTask(taskId, fields) {
  try {
    const res = await api(`/api/tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    });
    if (res.stats) renderTasksStats(res.stats);
    await loadTasks();
  } catch (err) {
    toast("Update Task Failed", err.message, "err");
  }
}

async function quickAddTask() {
  const titleEl = $("#task-quick-title");
  const title = (titleEl?.value || "").trim();
  if (!title) {
    titleEl?.focus();
    return;
  }
  const horizon = $("#task-quick-horizon")?.value || "sprint_2w";
  const priority = $("#task-quick-priority")?.value || "medium";
  const dueDate = ($("#task-quick-due")?.value || "").trim();
  try {
    await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title,
        horizon,
        is_today: horizon === "today",
        priority,
        due_date: dueDate,
      }),
    });
    if (titleEl) titleEl.value = "";
    toast("Task Added ✅", title, "ok", 2200);
    await loadTasks();
  } catch (err) {
    toast("Add Task Failed", err.message, "err");
  }
}

function openTaskEditModal(task = null) {
  $("#task-edit-id").value = task ? task.id : "";
  $("#task-edit-modal-title").textContent = task ? "✎ Edit Task" : "➕ New Task";
  $("#task-edit-title").value = task ? (task.title || "") : "";
  $("#task-edit-horizon").value = task ? (task.horizon || "sprint_2w") : "sprint_2w";
  $("#task-edit-priority").value = task ? (task.priority || "medium") : "medium";
  $("#task-edit-status").value = task ? (task.status || "todo") : "todo";
  $("#task-edit-progress").value = task ? String(task.progress || 0) : "0";
  $("#task-edit-progress-val").textContent = `${$("#task-edit-progress").value}%`;
  $("#task-edit-today").checked = task ? Boolean(task.is_today) : false;
  $("#task-edit-due").value = task ? (task.due_date || "") : "";
  $("#task-edit-project").value = task ? (task.project || "") : "";
  $("#task-edit-notes").value = task ? (task.notes || "") : "";
  $("#modal-task-edit")?.classList.remove("hidden");
  setTimeout(() => $("#task-edit-title")?.focus(), 40);
}

async function saveTaskEditModal() {
  const id = ($("#task-edit-id")?.value || "").trim();
  const payload = {
    title: ($("#task-edit-title")?.value || "").trim(),
    horizon: $("#task-edit-horizon")?.value || "sprint_2w",
    priority: $("#task-edit-priority")?.value || "medium",
    status: $("#task-edit-status")?.value || "todo",
    progress: parseInt($("#task-edit-progress")?.value || "0", 10),
    is_today: Boolean($("#task-edit-today")?.checked),
    due_date: ($("#task-edit-due")?.value || "").trim(),
    project: ($("#task-edit-project")?.value || "").trim(),
    notes: ($("#task-edit-notes")?.value || "").trim(),
  };
  if (!payload.title) {
    toast("Missing Title", "Please enter a task title.", "err");
    $("#task-edit-title")?.focus();
    return;
  }
  try {
    if (id) {
      await api(`/api/tasks/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) });
      toast("Task Updated ✅", payload.title, "ok", 2200);
    } else {
      await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
      toast("Task Created ✅", payload.title, "ok", 2200);
    }
    $("#modal-task-edit")?.classList.add("hidden");
    await loadTasks();
  } catch (err) {
    toast("Save Failed", err.message, "err");
  }
}

function askAIAboutTasks(prompt) {
  switchTab("ai");
  setTimeout(() => {
    const inp = $("#ai-input");
    if (inp) {
      inp.value = prompt;
      if (typeof aiSend === "function") aiSend();
    }
  }, 80);
}

function initTasksTab() {
  if (!_tasksInitialized) {
    _tasksInitialized = true;
    _restoreTasksFilterState();

    // Sync restored scope & hide-done UI
    document.querySelectorAll("#tasks-scope-bar .src-btn").forEach(b =>
      b.classList.toggle("active", b.dataset.scope === _tasksScope)
    );
    const hideCb = $("#tasks-hide-done");
    if (hideCb) hideCb.checked = _tasksHideDone;

    // Scope tabs (default: current = Today + 1-2w Sprint)
    document.querySelectorAll("#tasks-scope-bar .src-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        _tasksScope = btn.dataset.scope || "current";
        _saveTasksFilterState();
        document.querySelectorAll("#tasks-scope-bar .src-btn").forEach(b =>
          b.classList.toggle("active", b === btn)
        );
        loadTasks();
      });
    });

    $("#tasks-filter-year")?.addEventListener("change", (e) => {
      _tasksYear = e.target.value || "";
      if (!_tasksYear) _tasksMonth = "";
      _saveTasksFilterState();
      renderTasksPeriodSelects();
      loadTasks();
    });
    $("#tasks-filter-month")?.addEventListener("change", (e) => {
      _tasksMonth = e.target.value || "";
      if (_tasksMonth && !_tasksYear) {
        _tasksYear = _tasksMonth.slice(0, 4);
        renderTasksPeriodSelects();
      }
      _saveTasksFilterState();
      loadTasks();
    });
    $("#tasks-hide-done")?.addEventListener("change", (e) => {
      _tasksHideDone = e.target.checked;
      _saveTasksFilterState();
      loadTasks();
    });
    $("#tasks-search")?.addEventListener("input", (e) => {
      _tasksSearch = e.target.value || "";
      renderTasksList();
    });

    $("#btn-task-quick-add")?.addEventListener("click", quickAddTask);
    $("#task-quick-title")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        quickAddTask();
      }
    });

    $("#btn-tasks-new")?.addEventListener("click", () => openTaskEditModal(null));
    $("#btn-tasks-refresh")?.addEventListener("click", loadTasks);
    $("#btn-tasks-ai-today")?.addEventListener("click", () => {
      askAIAboutTasks(
        "Dùng tool list_tasks(horizon='current') xem các task hiện tại (Today & 1-2 tuần), sau đó đề xuất kế hoạch hôm nay (Today) nên làm những việc nào trước theo thứ tự ưu tiên và giúp pin các task quan trọng vào Today nếu cần."
      );
    });
    $("#btn-tasks-ai-report")?.addEventListener("click", () => {
      askAIAboutTasks(
        "Dùng tool list_tasks(horizon='all') tổng hợp tiến độ hiện tại: Today xong bao nhiêu %, Sprint 1-2 tuần tới đâu, Roadmap 3 tháng còn gì, có task nào bị blocked không và bước tiếp theo nên làm gì."
      );
    });

    $("#task-edit-progress")?.addEventListener("input", (e) => {
      const lbl = $("#task-edit-progress-val");
      if (lbl) lbl.textContent = `${e.target.value}%`;
    });
    $("#btn-task-edit-cancel")?.addEventListener("click", () => $("#modal-task-edit")?.classList.add("hidden"));
    $("#btn-task-edit-save")?.addEventListener("click", saveTaskEditModal);

    // Task Detail Dialog actions
    const closeDetail = () => {
      _taskDetailId = "";
      $("#modal-task-detail")?.classList.add("hidden");
    };
    $("#btn-task-detail-close")?.addEventListener("click", closeDetail);
    $("#btn-task-detail-close-x")?.addEventListener("click", closeDetail);
    $("#btn-task-detail-comment-send")?.addEventListener("click", postTaskDetailComment);
    $("#task-detail-comment-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        postTaskDetailComment();
      }
    });
    $("#modal-task-detail")?.addEventListener("click", (e) => {
      if (e.target && e.target.id === "modal-task-detail") closeDetail();
    });
    $("#btn-task-detail-edit")?.addEventListener("click", () => {
      const t = _tasksList.find(x => x.id === _taskDetailId);
      closeDetail();
      if (t) openTaskEditModal(t);
    });
    $("#btn-task-detail-ask-ai")?.addEventListener("click", () => {
      const t = _tasksList.find(x => x.id === _taskDetailId);
      closeDetail();
      if (t) {
        askAIAboutTasks(
          `Hãy hỗ trợ mình thực hiện task [${t.id}] "${t.title}" (status: ${t.status}, progress: ${t.progress}%). ` +
          (t.notes ? `Ghi chú: ${t.notes}` : "Đề xuất các bước cụ thể tiếp theo.")
        );
      }
    });
    $("#btn-task-detail-delete")?.addEventListener("click", async () => {
      const t = _tasksList.find(x => x.id === _taskDetailId);
      if (!t) return;
      const ok = await confirmDialog({
        title: "🗑 Delete Task",
        message: `Delete task "${t.title}"?`,
        confirmText: "🗑 Delete",
        icon: "🗑",
      });
      if (!ok) return;
      try {
        await api(`/api/tasks/${encodeURIComponent(t.id)}`, { method: "DELETE" });
        closeDetail();
        await loadTasks();
        toast("Task Deleted", "Task removed.", "ok", 2200);
      } catch (err) {
        toast("Delete Failed", err.message, "err");
      }
    });
  }

  // Always refresh on tab focus so tasks created/updated by AI Agent show up immediately
  loadTasks();
}
