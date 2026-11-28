#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ==============================================================================
#
# telua_web_tasks.py — Task Manager blueprint & AI Agent task helpers
#
# Storage layout under ai_agent/data/task/ (git-ignored):
#   ai_agent/data/task/
#   ├── active.json           # Open tasks (today / sprint_2w / quarter_3m)
#   └── <YYYY>/
#       └── <YYYY-MM>.json    # Completed (done) tasks archived by completion month
#
# Manages personal engineering tasks across horizons:
#   - today      : Today's focus ("Hôm nay làm gì")
#   - sprint_2w  : Current 1-2 week sprint
#   - quarter_3m : 3-month roadmap / backlog
# ==============================================================================

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from .ai_config_paths import REPO_ROOT, overlay_file as _ai_overlay_file

tasks_bp = Blueprint("tasks", __name__)

TASKS_DATA_DIR = REPO_ROOT / "ai_agent" / "data" / "task"

_TASKS_LOCK = threading.Lock()
VALID_HORIZONS = ("today", "sprint_2w", "quarter_3m")
VALID_STATUSES = ("todo", "in_progress", "blocked", "done")
VALID_PRIORITIES = ("high", "medium", "low")

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
_STATUS_RANK = {"in_progress": 0, "blocked": 1, "todo": 2, "done": 3}
_YEAR_RE = re.compile(r"^\d{4}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _tasks_root() -> Path:
    return TASKS_DATA_DIR


def _active_file() -> Path:
    return _tasks_root() / "active.json"


def _archive_file(ym: str) -> Path:
    year = ym[:4]
    return _tasks_root() / year / f"{ym}.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _current_ym() -> str:
    return datetime.now().strftime("%Y-%m")


def _task_ym(task: dict) -> str:
    for key in ("completed_at", "updated_at", "created_at"):
        val = str(task.get(key) or "").strip()
        if len(val) >= 7 and _MONTH_RE.match(val[:7]):
            return val[:7]
    return _current_ym()


def _read_json_list(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            return data["tasks"]
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _write_json_list(path: Path, tasks: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now_iso(),
        "tasks": tasks,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def _migrate_legacy_unlocked() -> None:
    """One-time split of legacy single tasks.json into active.json + YYYY/YYYY-MM.json."""
    root = _tasks_root()
    candidates = [root / "tasks.json", _ai_overlay_file("tasks.json")]
    for legacy in candidates:
        if not legacy.is_file():
            continue
        items = _read_json_list(legacy)
        if items:
            active = _read_json_list(_active_file())
            active_ids = {t.get("id") for t in active}
            by_month: Dict[str, List[dict]] = {}
            for t in items:
                tid = t.get("id")
                if t.get("status") == "done":
                    ym = _task_ym(t)
                    if not t.get("completed_at"):
                        t["completed_at"] = t.get("updated_at") or t.get("created_at") or _now_iso()
                    by_month.setdefault(ym, []).append(t)
                elif tid not in active_ids:
                    active.append(t)
                    active_ids.add(tid)
            _write_json_list(_active_file(), active)
            for ym, m_tasks in by_month.items():
                af = _archive_file(ym)
                existing = _read_json_list(af)
                existing_ids = {x.get("id") for x in existing}
                for t in m_tasks:
                    if t.get("id") not in existing_ids:
                        existing.append(t)
                        existing_ids.add(t.get("id"))
                _write_json_list(af, existing)
        try:
            legacy.unlink()
        except OSError:
            pass


def _iter_archive_files_unlocked(year: str = "", month: str = "") -> List[Path]:
    """Return archive files matching optional year ('2026') or month ('2026-11'), newest first."""
    root = _tasks_root()
    if month and _MONTH_RE.match(month):
        p = _archive_file(month)
        return [p] if p.is_file() else []
    if not root.is_dir():
        return []
    files: List[Path] = []
    year_dirs = []
    if year and _YEAR_RE.match(year):
        yd = root / year
        if yd.is_dir():
            year_dirs = [yd]
    else:
        for entry in root.iterdir():
            if entry.is_dir() and _YEAR_RE.match(entry.name):
                year_dirs.append(entry)
    for yd in sorted(year_dirs, key=lambda d: d.name, reverse=True):
        for f in sorted(yd.glob("*.json"), key=lambda x: x.name, reverse=True):
            if _MONTH_RE.match(f.stem):
                files.append(f)
    return files


def list_available_periods() -> dict:
    """List available archive years & months (newest first, always including current period)."""
    with _TASKS_LOCK:
        _migrate_legacy_unlocked()
        files = _iter_archive_files_unlocked()
    cur_ym = _current_ym()
    cur_y = cur_ym[:4]
    years = {cur_y}
    months = {cur_ym}
    for f in files:
        if _MONTH_RE.match(f.stem):
            months.add(f.stem)
            years.add(f.stem[:4])
    return {
        "years": sorted(years, reverse=True),
        "months": sorted(months, reverse=True),
        "current_year": cur_y,
        "current_month": cur_ym,
    }


def _clamp_progress(val, default: int = 0) -> int:
    try:
        n = int(round(float(val)))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, n))


def _normalize_horizon(val: Optional[str], default: str = "sprint_2w") -> str:
    s = str(val or "").strip().lower()
    aliases = {
        "today": "today",
        "day": "today",
        "sprint": "sprint_2w",
        "sprint_2w": "sprint_2w",
        "week": "sprint_2w",
        "1w": "sprint_2w",
        "2w": "sprint_2w",
        "1-2w": "sprint_2w",
        "quarter": "quarter_3m",
        "quarter_3m": "quarter_3m",
        "3m": "quarter_3m",
        "roadmap": "quarter_3m",
    }
    return aliases.get(s, default if default in VALID_HORIZONS else "sprint_2w")


def _normalize_status(val: Optional[str], default: str = "todo") -> str:
    s = str(val or "").strip().lower().replace(" ", "_").replace("-", "_")
    if s in VALID_STATUSES:
        return s
    if s in ("wip", "doing", "active"):
        return "in_progress"
    if s in ("completed", "complete", "finished"):
        return "done"
    return default if default in VALID_STATUSES else "todo"


def _normalize_priority(val: Optional[str], default: str = "medium") -> str:
    s = str(val or "").strip().lower()
    if s in VALID_PRIORITIES:
        return s
    if s in ("p0", "p1", "urgent", "critical"):
        return "high"
    if s in ("p3", "minor"):
        return "low"
    return default if default in VALID_PRIORITIES else "medium"


def _sync_status_and_progress(task: dict, status_explicit: bool, progress_explicit: bool) -> None:
    """Keep status, progress, and completed_at consistent."""
    prog = _clamp_progress(task.get("progress", 0))
    status = _normalize_status(task.get("status", "todo"))

    if progress_explicit and not status_explicit:
        if prog >= 100:
            status = "done"
            prog = 100
        elif prog > 0 and status in ("todo", "done"):
            status = "in_progress"
        elif prog == 0 and status == "done":
            status = "todo"
    elif status_explicit and not progress_explicit:
        if status == "done":
            prog = 100
        elif status == "todo" and prog == 100:
            prog = 0
    else:
        if status == "done" and prog < 100:
            prog = 100
        elif prog >= 100 and status != "done":
            status = "done"

    task["status"] = status
    task["progress"] = prog
    if status == "done":
        if not task.get("completed_at"):
            task["completed_at"] = _now_iso()
    else:
        task["completed_at"] = ""


def _sort_tasks(tasks: List[dict]) -> List[dict]:
    return sorted(
        tasks,
        key=lambda t: (
            _STATUS_RANK.get(t.get("status", "todo"), 2),
            0 if t.get("is_today") else 1,
            _PRIORITY_RANK.get(t.get("priority", "medium"), 1),
            t.get("due_date") or "9999-99-99",
            t.get("created_at") or "",
        ),
    )


def compute_task_stats(tasks: List[dict]) -> dict:
    today_tasks = [t for t in tasks if t.get("is_today") or t.get("horizon") == "today"]
    sprint_tasks = [t for t in tasks if t.get("horizon") in ("today", "sprint_2w")]
    quarter_tasks = [t for t in tasks if t.get("horizon") == "quarter_3m"]

    def _avg(lst: List[dict]) -> int:
        if not lst:
            return 0
        return int(round(sum(_clamp_progress(x.get("progress", 0)) for x in lst) / len(lst)))

    return {
        "total": len(tasks),
        "today_count": len(today_tasks),
        "today_done": sum(1 for t in today_tasks if t.get("status") == "done"),
        "today_avg_progress": _avg(today_tasks),
        "sprint_count": len(sprint_tasks),
        "sprint_done": sum(1 for t in sprint_tasks if t.get("status") == "done"),
        "sprint_avg_progress": _avg(sprint_tasks),
        "quarter_count": len(quarter_tasks),
        "quarter_done": sum(1 for t in quarter_tasks if t.get("status") == "done"),
        "quarter_avg_progress": _avg(quarter_tasks),
        "in_progress_count": sum(1 for t in tasks if t.get("status") == "in_progress"),
        "blocked_count": sum(1 for t in tasks if t.get("status") == "blocked"),
    }


def _load_scope_tasks_unlocked(year: str = "", month: str = "", include_done: bool = True) -> Tuple[List[dict], List[dict]]:
    """Return (pool_for_filter, stats_pool).

    - Default (no year/month): active.json + current month's archive (fast daily view).
    - Month ('YYYY-MM') or Year ('YYYY'): matching archive files + active tasks matching that period.
    """
    _migrate_legacy_unlocked()
    active = _read_json_list(_active_file())
    cur_archive = _read_json_list(_archive_file(_current_ym()))
    stats_pool = active + cur_archive

    y = str(year or "").strip()
    m = str(month or "").strip()
    if m and _MONTH_RE.match(m):
        archived = _read_json_list(_archive_file(m))
        active_in_month = [
            t for t in active
            if str(t.get("created_at") or "").startswith(m)
            or str(t.get("due_date") or "").startswith(m)
        ]
        pool = active_in_month + (archived if include_done else [])
        return pool, active_in_month + archived

    if y and _YEAR_RE.match(y):
        archived = []
        for af in _iter_archive_files_unlocked(year=y):
            archived.extend(_read_json_list(af))
        active_in_year = [
            t for t in active
            if str(t.get("created_at") or "").startswith(y)
            or str(t.get("due_date") or "").startswith(y)
        ]
        pool = active_in_year + (archived if include_done else [])
        return pool, active_in_year + archived

    # Default current working set: active.json + current month completed tasks
    pool = active + (cur_archive if include_done else [])
    return pool, stats_pool


def list_tasks(
    horizon: str = "",
    status: str = "",
    today_only: bool = False,
    include_done: bool = True,
    year: str = "",
    month: str = "",
) -> Tuple[List[dict], dict]:
    with _TASKS_LOCK:
        pool, stats_pool = _load_scope_tasks_unlocked(year=year, month=month, include_done=include_done)
    stats = compute_task_stats(stats_pool)

    h = str(horizon or "").strip().lower()
    st = str(status or "").strip().lower()
    filtered = []
    for t in pool:
        if not include_done and t.get("status") == "done":
            continue
        if today_only and not (t.get("is_today") or t.get("horizon") == "today"):
            continue
        if h and h != "all":
            if h == "current":
                if t.get("horizon") not in ("today", "sprint_2w") and not t.get("is_today"):
                    continue
            elif h == "today":
                if not (t.get("is_today") or t.get("horizon") == "today"):
                    continue
            else:
                norm_h = _normalize_horizon(h, default=h)
                if t.get("horizon") != norm_h:
                    continue
        if st and st != "all":
            if t.get("status") != _normalize_status(st, default=st):
                continue
        filtered.append(t)

    return _sort_tasks(filtered), stats


def create_task(payload: dict, created_by: str = "user") -> Tuple[Optional[dict], str, dict]:
    title = str(payload.get("title") or "").strip()
    if not title:
        return None, "Missing task 'title'.", {}

    horizon = _normalize_horizon(payload.get("horizon"), default="sprint_2w")
    is_today = bool(payload.get("is_today", False)) or (horizon == "today")
    status_explicit = "status" in payload and payload.get("status") is not None
    progress_explicit = "progress" in payload and payload.get("progress") is not None

    now = _now_iso()
    task = {
        "id": "tsk_" + uuid.uuid4().hex[:8],
        "title": title[:240],
        "horizon": horizon,
        "is_today": is_today,
        "status": _normalize_status(payload.get("status"), default="todo"),
        "progress": _clamp_progress(payload.get("progress", 0)),
        "priority": _normalize_priority(payload.get("priority"), default="medium"),
        "due_date": str(payload.get("due_date") or "").strip()[:20],
        "project": str(payload.get("project") or "").strip()[:60],
        "notes": str(payload.get("notes") or "").strip()[:2000],
        "created_by": "ai" if created_by == "ai" else "user",
        "created_at": now,
        "updated_at": now,
        "completed_at": "",
        "comments": [],
    }
    _sync_status_and_progress(task, status_explicit, progress_explicit)

    with _TASKS_LOCK:
        _migrate_legacy_unlocked()
        if task["status"] == "done":
            af = _archive_file(_task_ym(task))
            archived = _read_json_list(af)
            archived.append(task)
            _write_json_list(af, archived)
        else:
            active = _read_json_list(_active_file())
            active.append(task)
            _write_json_list(_active_file(), active)
        _, stats_pool = _load_scope_tasks_unlocked()
        stats = compute_task_stats(stats_pool)
    return task, "", stats


def _find_task_location_unlocked(tid: str) -> Tuple[Optional[Path], List[dict], int]:
    """Locate a task in active.json or any YYYY/YYYY-MM.json archive."""
    af = _active_file()
    active = _read_json_list(af)
    for idx, t in enumerate(active):
        if t.get("id") == tid:
            return af, active, idx
    for path in _iter_archive_files_unlocked():
        items = _read_json_list(path)
        for idx, t in enumerate(items):
            if t.get("id") == tid:
                return path, items, idx
    return None, [], -1


def update_task(task_id: str, payload: dict) -> Tuple[Optional[dict], str, dict]:
    tid = str(task_id or "").strip()
    if not tid:
        return None, "Missing 'task_id'.", {}

    with _TASKS_LOCK:
        _migrate_legacy_unlocked()
        src_path, src_list, idx = _find_task_location_unlocked(tid)
        if src_path is None or idx < 0:
            return None, f"Task not found: {tid}", {}

        target = dict(src_list[idx])
        if "title" in payload and str(payload["title"]).strip():
            target["title"] = str(payload["title"]).strip()[:240]
        if "horizon" in payload and payload["horizon"] is not None:
            target["horizon"] = _normalize_horizon(payload["horizon"], default=target.get("horizon", "sprint_2w"))
            if target["horizon"] == "today" and "is_today" not in payload:
                target["is_today"] = True
        if "is_today" in payload and payload["is_today"] is not None:
            target["is_today"] = bool(payload["is_today"])
        if "priority" in payload and payload["priority"] is not None:
            target["priority"] = _normalize_priority(payload["priority"], default=target.get("priority", "medium"))
        if "due_date" in payload and payload["due_date"] is not None:
            target["due_date"] = str(payload["due_date"]).strip()[:20]
        if "project" in payload and payload["project"] is not None:
            target["project"] = str(payload["project"]).strip()[:60]
        if "notes" in payload and payload["notes"] is not None:
            target["notes"] = str(payload["notes"]).strip()[:2000]

        status_explicit = "status" in payload and payload.get("status") is not None
        progress_explicit = "progress" in payload and payload.get("progress") is not None
        if status_explicit:
            target["status"] = _normalize_status(payload["status"], default=target.get("status", "todo"))
        if progress_explicit:
            target["progress"] = _clamp_progress(payload["progress"], default=target.get("progress", 0))
        if status_explicit or progress_explicit:
            _sync_status_and_progress(target, status_explicit, progress_explicit)

        target["updated_at"] = _now_iso()
        dst_path = _archive_file(_task_ym(target)) if target["status"] == "done" else _active_file()

        if dst_path == src_path:
            src_list[idx] = target
            _write_json_list(src_path, src_list)
        else:
            # Move seamlessly between active.json and YYYY/YYYY-MM.json
            src_list.pop(idx)
            _write_json_list(src_path, src_list)
            dst_list = _read_json_list(dst_path)
            dst_list.append(target)
            _write_json_list(dst_path, dst_list)

        _, stats_pool = _load_scope_tasks_unlocked()
        stats = compute_task_stats(stats_pool)
        return dict(target), "", stats


def delete_task(task_id: str) -> Tuple[bool, str, dict]:
    tid = str(task_id or "").strip()
    if not tid:
        return False, "Missing 'task_id'.", {}
    with _TASKS_LOCK:
        _migrate_legacy_unlocked()
        src_path, src_list, idx = _find_task_location_unlocked(tid)
        if src_path is None or idx < 0:
            return False, f"Task not found: {tid}", {}
        src_list.pop(idx)
        _write_json_list(src_path, src_list)
        _, stats_pool = _load_scope_tasks_unlocked()
        stats = compute_task_stats(stats_pool)
    return True, "", stats


def add_task_comment(task_id: str, text: str, author: str = "user") -> Tuple[Optional[dict], Optional[dict], str]:
    """Append a comment (tagged author='user' or 'ai') to a task in active.json or archive."""
    tid = str(task_id or "").strip()
    body = str(text or "").strip()
    if not tid:
        return None, None, "Missing 'task_id'."
    if not body:
        return None, None, "Missing comment 'text'."
    norm_author = "ai" if str(author or "").strip().lower() == "ai" else "user"

    with _TASKS_LOCK:
        _migrate_legacy_unlocked()
        src_path, src_list, idx = _find_task_location_unlocked(tid)
        if src_path is None or idx < 0:
            return None, None, f"Task not found: {tid}"
        target = dict(src_list[idx])
        comments = list(target.get("comments") or [])
        now = _now_iso()
        comment = {
            "id": "cmt_" + uuid.uuid4().hex[:8],
            "author": norm_author,
            "text": body[:2000],
            "created_at": now,
        }
        comments.append(comment)
        target["comments"] = comments
        target["updated_at"] = now
        src_list[idx] = target
        _write_json_list(src_path, src_list)
        return comment, dict(target), ""


def delete_task_comment(task_id: str, comment_id: str) -> Tuple[Optional[dict], str]:
    tid = str(task_id or "").strip()
    cid = str(comment_id or "").strip()
    if not tid or not cid:
        return None, "Missing 'task_id' or 'comment_id'."
    with _TASKS_LOCK:
        _migrate_legacy_unlocked()
        src_path, src_list, idx = _find_task_location_unlocked(tid)
        if src_path is None or idx < 0:
            return None, f"Task not found: {tid}"
        target = dict(src_list[idx])
        comments = list(target.get("comments") or [])
        new_comments = [c for c in comments if c.get("id") != cid]
        if len(new_comments) == len(comments):
            return None, f"Comment not found: {cid}"
        target["comments"] = new_comments
        target["updated_at"] = _now_iso()
        src_list[idx] = target
        _write_json_list(src_path, src_list)
        return dict(target), ""


# ------------------------------------------------------------------------------
# REST API endpoints
# ------------------------------------------------------------------------------

@tasks_bp.get("/api/tasks")
def api_tasks_list():
    horizon = request.args.get("horizon", "current")
    status = request.args.get("status", "")
    year = request.args.get("year", "").strip()
    month = request.args.get("month", "").strip()
    today_only = request.args.get("today_only", "").lower() in ("1", "true", "yes")
    include_done = request.args.get("include_done", "1").lower() not in ("0", "false", "no")
    tasks, stats = list_tasks(
        horizon=horizon,
        status=status,
        today_only=today_only,
        include_done=include_done,
        year=year,
        month=month,
    )
    periods = list_available_periods()
    resp = jsonify({"ok": True, "tasks": tasks, "stats": stats, "periods": periods})
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@tasks_bp.post("/api/tasks")
def api_tasks_create():
    data = request.get_json(silent=True) or {}
    task, err, stats = create_task(data, created_by=str(data.get("created_by") or "user"))
    if err or task is None:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "task": task, "stats": stats, "periods": list_available_periods()}), 201


@tasks_bp.patch("/api/tasks/<task_id>")
def api_tasks_update(task_id: str):
    data = request.get_json(silent=True) or {}
    task, err, stats = update_task(task_id, data)
    if err or task is None:
        code = 404 if "not found" in err.lower() else 400
        return jsonify({"ok": False, "error": err}), code
    return jsonify({"ok": True, "task": task, "stats": stats, "periods": list_available_periods()})


@tasks_bp.delete("/api/tasks/<task_id>")
def api_tasks_delete(task_id: str):
    ok, err, stats = delete_task(task_id)
    if not ok:
        return jsonify({"ok": False, "error": err}), 404
    return jsonify({"ok": True, "deleted": task_id, "stats": stats, "periods": list_available_periods()})


@tasks_bp.post("/api/tasks/<task_id>/comments")
def api_tasks_add_comment(task_id: str):
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or data.get("comment") or "").strip()
    author = str(data.get("author") or "user").strip().lower()
    comment, task, err = add_task_comment(task_id, text, author=author)
    if err or comment is None:
        code = 404 if "not found" in err.lower() else 400
        return jsonify({"ok": False, "error": err}), code
    return jsonify({"ok": True, "comment": comment, "task": task}), 201


@tasks_bp.delete("/api/tasks/<task_id>/comments/<comment_id>")
def api_tasks_delete_comment(task_id: str, comment_id: str):
    task, err = delete_task_comment(task_id, comment_id)
    if err or task is None:
        return jsonify({"ok": False, "error": err}), 404
    return jsonify({"ok": True, "task": task})
