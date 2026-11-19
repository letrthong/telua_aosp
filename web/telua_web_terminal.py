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
# telua_web_terminal.py — Terminal process management, command execution & live streaming
# ==============================================================================

import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import Tuple

from flask import Blueprint, Response, abort, jsonify, request, stream_with_context

terminal_bp = Blueprint("terminal", __name__)

_ACTIVE_TERM_LOCK = threading.Lock()
_ACTIVE_TERM_PROCS = set()


def get_root() -> Path:
    """Dynamically get ROOT from telua_web if loaded, else fallback to toolkit root."""
    import sys
    if "telua_web" in sys.modules:
        tw = sys.modules["telua_web"]
        if hasattr(tw, "ROOT"):
            return tw.ROOT
    return Path(__file__).resolve().parent.parent


def _kill_term_proc(proc):
    """Terminate a running terminal Popen process and its entire process group."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            if os.name != "nt" and hasattr(os, "killpg"):
                try:
                    os.killpg(proc.pid, signal.SIGINT)
                except OSError:
                    pass
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except OSError:
                    pass
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                if os.name != "nt" and hasattr(os, "killpg"):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except OSError:
                        pass
                proc.kill()
    except Exception:
        pass


def _build_terminal_bash_script(cmd: str, cwd: str = "") -> str:
    """Wrap a user command with tel/telua shell functions and persistent cwd tracking."""
    root = get_root()
    script_path = str(root / "build_apk.sh").replace("\\", "/")
    cd_line = ""
    if cwd:
        safe_cwd = cwd.replace('"', '\\"')
        cd_line = 'cd "%s" >/dev/null 2>&1 || true\n' % safe_cwd
    return (
        'tel() { bash "%s" "$@"; }\n'
        'telua() { bash "%s" "$@"; }\n'
        "%s"
        "%s\n"
        "__telua_rc=$?\n"
        'printf "\\n__TELUA_PWD__:%%s\\n" "$(pwd)"\n'
        "exit $__telua_rc\n"
    ) % (script_path, script_path, cd_line, cmd)


def _resolve_terminal_exec(cmd: str, cwd: str = ""):
    """Return (args, use_shell) using bash when available, or native shell fallback."""
    bash_bin = shutil.which("bash")
    if not bash_bin and os.name == "nt":
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if os.path.isfile(candidate):
                bash_bin = candidate
                break
    if bash_bin:
        return [bash_bin, "-c", _build_terminal_bash_script(cmd, cwd)], False
    return cmd, True


@terminal_bp.post("/api/terminal/run")
def api_terminal_run():
    """Execute an ad-hoc shell / telua CLI command from the Web UI Terminal tab."""
    data = request.get_json(silent=True) or {}
    cmd = str(data.get("command", "")).strip()
    cwd = str(data.get("cwd", "")).strip()
    if not cmd:
        abort(400, description="Missing 'command' in request body.")
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    exec_args, use_shell = _resolve_terminal_exec(cmd, cwd)
    root = get_root()
    try:
        proc = subprocess.run(
            exec_args,
            shell=use_shell,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=300,
            env=env,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "[ERROR] Command timed out after 300s.", 124
    except Exception as exc:  # pragma: no cover
        output, code = "[ERROR] Failed to execute command: %s" % exc, 1
    return jsonify({"ok": code == 0, "exit_code": code, "output": output, "cwd": str(root)})


@terminal_bp.post("/api/terminal/stream")
def api_terminal_stream():
    """Stream ad-hoc shell / telua CLI command output line-by-line in real time."""
    data = request.get_json(silent=True) or {}
    cmd = str(data.get("command", "")).strip()
    cwd = str(data.get("cwd", "")).strip()
    if not cmd:
        abort(400, description="Missing 'command' in request body.")
    exec_args, use_shell = _resolve_terminal_exec(cmd, cwd)
    root = get_root()

    def generate():
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = None
        try:
            proc = subprocess.Popen(
                exec_args,
                shell=use_shell,
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
            with _ACTIVE_TERM_LOCK:
                _ACTIVE_TERM_PROCS.add(proc)
            if proc.stdout is not None:
                for line in iter(proc.stdout.readline, ""):
                    yield line
                proc.stdout.close()
            code = proc.wait(timeout=300)
        except Exception as exc:  # pragma: no cover
            yield "\n[ERROR] Failed to execute command: %s\n" % exc
            code = 1
        finally:
            if proc is not None:
                with _ACTIVE_TERM_LOCK:
                    _ACTIVE_TERM_PROCS.discard(proc)
                if proc.poll() is None:
                    _kill_term_proc(proc)
        yield "\n__TELUA_EXIT_CODE__:%d\n" % code

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@terminal_bp.post("/api/terminal/stop")
def api_terminal_stop():
    """Stop (SIGINT/SIGTERM) any currently running terminal command."""
    with _ACTIVE_TERM_LOCK:
        procs = list(_ACTIVE_TERM_PROCS)
        _ACTIVE_TERM_PROCS.clear()
    for p in procs:
        _kill_term_proc(p)
    return jsonify({"ok": True, "stopped": len(procs)})
