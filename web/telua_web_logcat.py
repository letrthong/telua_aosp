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
# telua_web_logcat.py — Android ADB Logcat live streaming, circular buffer & filter rules
# ==============================================================================

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from flask import Blueprint, Response, abort, jsonify, request, stream_with_context
from telua_web_core import adb_devices
from telua_web_terminal import _kill_term_proc

logcat_bp = Blueprint("logcat", __name__)

_ACTIVE_LOGCAT_PROCS = set()
_ACTIVE_LOGCAT_LOCK = threading.Lock()

DEFAULT_LOGCAT_FILTERS = [
    {
        "id": "rule-fatal",
        "name": "Fatal & Crashes",
        "enabled": True,
        "level": "E",
        "tag": "AndroidRuntime|DEBUG",
        "text": "FATAL|CRASH|Exception",
        "pid": "",
    },
    {
        "id": "rule-caraudio",
        "name": "Car Audio",
        "enabled": False,
        "level": "D",
        "tag": "CarAudio.*|AudioFlinger",
        "text": "",
        "pid": "",
    },
    {
        "id": "rule-carservice",
        "name": "Car Service",
        "enabled": False,
        "level": "I",
        "tag": "CarService|CarProperty.*",
        "text": "",
        "pid": "",
    },
    {
        "id": "rule-oem",
        "name": "OEM Service",
        "enabled": False,
        "level": "D",
        "tag": "Oem.*",
        "text": "",
        "pid": "",
    },
    {
        "id": "rule-am",
        "name": "Activity Manager",
        "enabled": False,
        "level": "I",
        "tag": "ActivityManager|ActivityTaskManager",
        "text": "",
        "pid": "",
    },
]


def get_root() -> Path:
    """Dynamically get ROOT from telua_web if loaded, else fallback to toolkit root."""
    import sys
    if "telua_web" in sys.modules:
        tw = sys.modules["telua_web"]
        if hasattr(tw, "ROOT"):
            return tw.ROOT
    return Path(__file__).resolve().parent.parent


def get_filters_file() -> Path:
    """Dynamically resolve config/logcat_filters.json based on current ROOT."""
    return get_root() / "config" / "logcat_filters.json"


def _resolve_adb_binary() -> Optional[str]:
    """Find the adb executable in PATH or standard Android SDK locations."""
    adb = shutil.which("adb")
    if adb:
        return adb
    candidates = []
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidates.append(os.path.join(local_app, "Android", "Sdk", "platform-tools", "adb.exe"))
        user_profile = os.environ.get("USERPROFILE", "")
        if user_profile:
            candidates.append(os.path.join(user_profile, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"))
        candidates.extend([
            r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
            r"C:\Android\platform-tools\adb.exe",
        ])
    else:
        home = os.path.expanduser("~")
        candidates.extend([
            os.path.join(home, "Android/Sdk/platform-tools/adb"),
            "/usr/bin/adb",
            "/usr/local/bin/adb",
        ])
    for cand in candidates:
        if os.path.isfile(cand) and (os.access(cand, os.X_OK) or os.name == "nt"):
            return cand
    return None


@logcat_bp.get("/api/logcat/status")
def api_logcat_status():
    """Return status of ADB binary, connected devices, and streaming state."""
    adb = _resolve_adb_binary()
    devices = adb_devices()
    with _ACTIVE_LOGCAT_LOCK:
        streaming = len(_ACTIVE_LOGCAT_PROCS) > 0
    return jsonify({
        "ok": True,
        "adb_available": bool(adb),
        "adb_path": adb or "",
        "devices": devices,
        "streaming": streaming,
    })


@logcat_bp.post("/api/logcat/stream")
def api_logcat_stream():
    """Stream live Android adb logcat output line-by-line."""
    adb = _resolve_adb_binary()
    if not adb:
        return jsonify({"ok": False, "error": "ADB executable not found in PATH or Android SDK locations."}), 400

    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "")).strip()
    buffer = str(data.get("buffer", "")).strip()

    exec_args = [adb]
    if device:
        exec_args.extend(["-s", device])
    exec_args.extend(["logcat", "-v", "threadtime"])
    if buffer and buffer not in ("all", "default"):
        exec_args.extend(["-b", buffer])

    root = get_root()

    def generate():
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = None
        try:
            proc = subprocess.Popen(
                exec_args,
                shell=False,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                env=env,
                start_new_session=(os.name != "nt"),
            )
            with _ACTIVE_LOGCAT_LOCK:
                _ACTIVE_LOGCAT_PROCS.add(proc)
            if proc.stdout is not None:
                for line in iter(proc.stdout.readline, ""):
                    yield line
                proc.stdout.close()
            code = proc.wait()
        except Exception as exc:
            yield "\n[ERROR] Logcat streaming failed: %s\n" % exc
            code = 1
        finally:
            if proc is not None:
                with _ACTIVE_LOGCAT_LOCK:
                    _ACTIVE_LOGCAT_PROCS.discard(proc)
                if proc.poll() is None:
                    _kill_term_proc(proc)
        yield "\n__TELUA_LOGCAT_DONE__:%d\n" % (code or 0)

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@logcat_bp.post("/api/logcat/stop")
def api_logcat_stop():
    """Stop active logcat streaming process."""
    with _ACTIVE_LOGCAT_LOCK:
        procs = list(_ACTIVE_LOGCAT_PROCS)
        _ACTIVE_LOGCAT_PROCS.clear()
    for p in procs:
        _kill_term_proc(p)
    return jsonify({"ok": True, "stopped": len(procs)})


@logcat_bp.post("/api/logcat/clear")
def api_logcat_clear():
    """Clear device circular logcat buffer via `adb logcat -c`."""
    adb = _resolve_adb_binary()
    if not adb:
        return jsonify({"ok": False, "error": "ADB binary not found."}), 400
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "")).strip()
    cmd = [adb]
    if device:
        cmd.extend(["-s", device])
    cmd.extend(["logcat", "-c"])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return jsonify({
            "ok": res.returncode == 0,
            "exit_code": res.returncode,
            "output": (res.stdout or "") + (res.stderr or ""),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@logcat_bp.get("/api/logcat/filters")
def api_logcat_filters_get():
    """Retrieve saved Logcat filter rule array from config/logcat_filters.json."""
    filters_file = get_filters_file()
    if filters_file.is_file():
        try:
            with open(filters_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return jsonify({"ok": True, "filters": data, "path": "config/logcat_filters.json"})
        except Exception:
            pass
    return jsonify({"ok": True, "filters": DEFAULT_LOGCAT_FILTERS, "path": "config/logcat_filters.json", "default": True})


@logcat_bp.post("/api/logcat/filters")
def api_logcat_filters_post():
    """Save Logcat filter rule array to config/logcat_filters.json."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400
    filters = data if isinstance(data, list) else data.get("filters")
    if not isinstance(filters, list):
        return jsonify({"ok": False, "error": "'filters' must be a JSON array"}), 400

    filters_file = get_filters_file()
    filters_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(filters_file, "w", encoding="utf-8") as f:
            json.dump(filters, f, indent=2, ensure_ascii=False)
        return jsonify({"ok": True, "count": len(filters), "path": "config/logcat_filters.json"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
