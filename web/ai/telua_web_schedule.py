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
# telua_web_schedule.py — Scheduled AI Agent triggers
#
# Stores schedules in config/overlay/ai_agent/ai_schedules.json (git-ignored)
# and runs a lightweight background daemon thread that checks due schedules
# every 20 seconds, executes the AI Agent headless, and optionally sends the
# result to Telegram (configured in AI Config -> Notify).
# ==============================================================================

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from flask import Blueprint, jsonify, request

from .ai_config_paths import overlay_file as _ai_overlay_file

schedule_bp = Blueprint("ai_schedule", __name__)

_SCHED_LOCK = threading.Lock()
_SCHED_THREAD_LOCK = threading.Lock()
_SCHED_STARTED = False
_RUNNING_IDS = set()

VALID_MODES = ("daily", "weekdays", "interval")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _schedules_file() -> Path:
    return _ai_overlay_file("ai_schedules.json")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_schedules_unlocked() -> List[dict]:
    path = _schedules_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("schedules"), list):
            return data["schedules"]
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _save_schedules_unlocked(schedules: List[dict]) -> None:
    path = _schedules_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now_iso(),
        "schedules": schedules,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def _normalize_mode(val: Optional[str]) -> str:
    s = str(val or "").strip().lower()
    return s if s in VALID_MODES else "daily"


def _normalize_time(val: Optional[str]) -> str:
    s = str(val or "").strip()
    if _TIME_RE.match(s):
        hh, mm = int(s[:2]), int(s[3:5])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    return "08:30"


def _normalize_interval(val) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        return 60
    return max(5, min(1440, n))


def list_schedules() -> List[dict]:
    with _SCHED_LOCK:
        return [dict(x) for x in _load_schedules_unlocked()]


def create_schedule(payload: dict) -> Tuple[Optional[dict], str]:
    name = str(payload.get("name") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if not name:
        return None, "Missing schedule 'name'."
    if not prompt:
        return None, "Missing schedule 'prompt'."

    item = {
        "id": "sch_" + uuid.uuid4().hex[:8],
        "name": name[:120],
        "prompt": prompt[:3000],
        "mode": _normalize_mode(payload.get("mode")),
        "time_of_day": _normalize_time(payload.get("time_of_day")),
        "interval_minutes": _normalize_interval(payload.get("interval_minutes", 60)),
        "enabled": bool(payload.get("enabled", True)),
        "notify_telegram": bool(payload.get("notify_telegram", True)),
        "auto_confirm": bool(payload.get("auto_confirm", False)),
        "project": str(payload.get("project") or "").strip()[:60],
        "aosp_version": str(payload.get("aosp_version") or "").strip()[:40],
        "last_run_at": "",
        "last_status": "",
        "last_output": "",
        "created_at": _now_iso(),
    }
    with _SCHED_LOCK:
        items = _load_schedules_unlocked()
        items.append(item)
        _save_schedules_unlocked(items)
    ensure_scheduler_started()
    return item, ""


def update_schedule(sid: str, payload: dict) -> Tuple[Optional[dict], str]:
    key = str(sid or "").strip()
    if not key:
        return None, "Missing schedule id."
    with _SCHED_LOCK:
        items = _load_schedules_unlocked()
        target = next((x for x in items if x.get("id") == key), None)
        if target is None:
            return None, f"Schedule not found: {key}"
        if "name" in payload and str(payload["name"]).strip():
            target["name"] = str(payload["name"]).strip()[:120]
        if "prompt" in payload and str(payload["prompt"]).strip():
            target["prompt"] = str(payload["prompt"]).strip()[:3000]
        if "mode" in payload and payload["mode"] is not None:
            target["mode"] = _normalize_mode(payload["mode"])
        if "time_of_day" in payload and payload["time_of_day"] is not None:
            target["time_of_day"] = _normalize_time(payload["time_of_day"])
        if "interval_minutes" in payload and payload["interval_minutes"] is not None:
            target["interval_minutes"] = _normalize_interval(payload["interval_minutes"])
        for flag in ("enabled", "notify_telegram", "auto_confirm"):
            if flag in payload and payload[flag] is not None:
                target[flag] = bool(payload[flag])
        if "project" in payload and payload["project"] is not None:
            target["project"] = str(payload["project"]).strip()[:60]
        if "aosp_version" in payload and payload["aosp_version"] is not None:
            target["aosp_version"] = str(payload["aosp_version"]).strip()[:40]
        _save_schedules_unlocked(items)
        return dict(target), ""


def delete_schedule(sid: str) -> Tuple[bool, str]:
    key = str(sid or "").strip()
    with _SCHED_LOCK:
        items = _load_schedules_unlocked()
        new_items = [x for x in items if x.get("id") != key]
        if len(new_items) == len(items):
            return False, f"Schedule not found: {key}"
        _save_schedules_unlocked(new_items)
    return True, ""


def is_schedule_due(item: dict, now: datetime) -> bool:
    """Return True if an enabled schedule should fire at `now`."""
    if not item.get("enabled"):
        return False
    mode = item.get("mode") or "daily"
    last_run = str(item.get("last_run_at") or "").strip()

    if mode in ("daily", "weekdays"):
        if mode == "weekdays" and now.weekday() >= 5:
            return False
        target_hm = _normalize_time(item.get("time_of_day"))
        if now.strftime("%H:%M") != target_hm:
            return False
        # Already ran today?
        if last_run.startswith(now.strftime("%Y-%m-%d")):
            return False
        return True

    if mode == "interval":
        mins = _normalize_interval(item.get("interval_minutes", 60))
        if not last_run:
            return True
        try:
            last_dt = datetime.fromisoformat(last_run)
        except ValueError:
            return True
        return (now - last_dt).total_seconds() >= mins * 60

    return False


def _set_schedule_run_state(sid: str, status: str, output: str = "", run_at: Optional[str] = None) -> None:
    with _SCHED_LOCK:
        items = _load_schedules_unlocked()
        for it in items:
            if it.get("id") == sid:
                if run_at is not None:
                    it["last_run_at"] = run_at
                it["last_status"] = status
                if output is not None:
                    it["last_output"] = str(output)[:1500]
                break
        _save_schedules_unlocked(items)


def _execute_schedule_worker(item: dict) -> None:
    sid = item["id"]
    try:
        from .telua_web_ai import run_ai_agent_headless, _send_telegram_message, get_ai_notify_config
        res = run_ai_agent_headless(
            user_msg=item["prompt"],
            project=item.get("project", ""),
            aosp_version=item.get("aosp_version", ""),
            auto_confirm=bool(item.get("auto_confirm", False)),
        )
        safe_mode = bool(get_ai_notify_config().get("safe_mode", True))
        if res.get("ok"):
            ans = str(res.get("answer") or "(empty response)")
            _set_schedule_run_state(sid, "ok", ans)
            if item.get("notify_telegram"):
                ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                if safe_mode:
                    _send_telegram_message(
                        f"⏰ [Telua AI Schedule] {item['name']}: ✅ Completed\n"
                        f"🕒 {ts}\n🛡 Safe Mode: open Telua Web → Schedule to view details."
                    )
                else:
                    _send_telegram_message(f"⏰ [Telua AI Schedule: {item['name']}]\n🕒 {ts}\n\n{ans[:3200]}")
        else:
            err = str(res.get("error") or "Unknown error")
            _set_schedule_run_state(sid, "error", err)
            if item.get("notify_telegram"):
                ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                if safe_mode:
                    _send_telegram_message(
                        f"🚨 [Telua AI Schedule] {item['name']}: ❌ Failed\n"
                        f"🕒 {ts}\n🛡 Safe Mode: error log hidden — open Telua Web → Schedule to inspect."
                    )
                else:
                    _send_telegram_message(f"🚨 [Telua AI Schedule FAILED: {item['name']}]\n🕒 {ts}\n\n{err[:2000]}")
    except Exception as exc:
        _set_schedule_run_state(sid, "error", str(exc))
    finally:
        with _SCHED_LOCK:
            _RUNNING_IDS.discard(sid)


def trigger_schedule_async(sid: str) -> Tuple[bool, str]:
    """Start a scheduled AI job in a background worker thread."""
    with _SCHED_LOCK:
        if sid in _RUNNING_IDS:
            return False, "Schedule is already running."
        items = _load_schedules_unlocked()
        target = next((dict(x) for x in items if x.get("id") == sid), None)
        if target is None:
            return False, f"Schedule not found: {sid}"
        _RUNNING_IDS.add(sid)
        now_str = _now_iso()
        for it in items:
            if it.get("id") == sid:
                it["last_run_at"] = now_str
                it["last_status"] = "running"
                break
        _save_schedules_unlocked(items)

    threading.Thread(target=_execute_schedule_worker, args=(target,), daemon=True).start()
    return True, "Started"


def _scheduler_loop() -> None:
    while True:
        try:
            now = datetime.now()
            items = list_schedules()
            for it in items:
                if is_schedule_due(it, now):
                    trigger_schedule_async(it["id"])
        except Exception:
            pass
        time.sleep(20)


def ensure_scheduler_started() -> None:
    global _SCHED_STARTED
    with _SCHED_THREAD_LOCK:
        if _SCHED_STARTED:
            return
        _SCHED_STARTED = True
        threading.Thread(target=_scheduler_loop, name="telua-ai-scheduler", daemon=True).start()


# ------------------------------------------------------------------------------
# REST API endpoints
# ------------------------------------------------------------------------------

@schedule_bp.get("/api/ai/schedules")
def api_ai_schedules_list():
    ensure_scheduler_started()
    return jsonify({
        "ok": True,
        "schedules": list_schedules(),
        "server_time": datetime.now().strftime("%d/%m %H:%M:%S"),
    })


@schedule_bp.post("/api/ai/schedules")
def api_ai_schedules_create():
    data = request.get_json(silent=True) or {}
    item, err = create_schedule(data)
    if err or item is None:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "schedule": item}), 201


@schedule_bp.patch("/api/ai/schedules/<sid>")
def api_ai_schedules_update(sid: str):
    data = request.get_json(silent=True) or {}
    item, err = update_schedule(sid, data)
    if err or item is None:
        return jsonify({"ok": False, "error": err}), 404
    return jsonify({"ok": True, "schedule": item})


@schedule_bp.delete("/api/ai/schedules/<sid>")
def api_ai_schedules_delete(sid: str):
    ok, err = delete_schedule(sid)
    if not ok:
        return jsonify({"ok": False, "error": err}), 404
    return jsonify({"ok": True, "deleted": sid})


@schedule_bp.post("/api/ai/schedules/<sid>/run")
def api_ai_schedules_run(sid: str):
    ok, msg = trigger_schedule_async(sid)
    if not ok:
        code = 409 if "already running" in msg.lower() else 404
        return jsonify({"ok": False, "error": msg}), code
    return jsonify({"ok": True, "status": "running", "id": sid})
