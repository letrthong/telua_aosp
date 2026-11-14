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
# telua_web.py — Flask backend for the Telua Web UI ('telua web start')
# Core helpers live in:
#   - web/telua_web_core.py      (file scanning, validation, system/crypto status)
#   - web/telua_web_pipelines.py (pipeline parsing, serialization & rewriting)

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

SCRIPT_FILE = Path(__file__).resolve()
WEB_DIR = SCRIPT_FILE.parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from telua_web_core import (  # noqa: E402
    PRIVATE_OVERLAY_NAMES,
    adb_devices,
    crypto_items_for_root,
    ensure_overlay_configs as _ensure_overlay_configs_for_root,
    is_editable_name,
    parse_active_project_from_file,
    parse_profiles_from_file,
    parse_version_from_file,
    ram_info,
    scan_files_in_root,
    validate_content,
)
from telua_web_pipelines import (  # noqa: E402
    CAR_ROW_RE,
    CAR_VAR_RE,
    MY_GROUP_RE,
    MY_STEP_RE,
    _bash_quote,
    _parse_cli_list_pipelines,
    _rewrite_cli_list_lines,
    parse_array_pipelines,
    rewrite_array_pipeline_lines,
    serialize_pipelines,
)

try:
    from flask import Flask, Response, abort, jsonify, request, send_from_directory, stream_with_context
    from werkzeug.exceptions import HTTPException
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "[ERROR] Flask is not installed.\n"
        "        Install it with:  python3 -m pip install flask\n"
        "        (or run 'telua web start' which auto-installs it)\n"
    )
    sys.exit(1)

STATIC_DIR = WEB_DIR / "static"
DEFAULT_ROOT = WEB_DIR.parent

ROOT = DEFAULT_ROOT                 # toolkit root (config registry base), set by --root
BUILD_APK_SH = ROOT / "build_apk.sh"
APK_CONFIG = (ROOT / "config" / "apk.config") if (ROOT / "config" / "apk.config").is_file() else (ROOT / "apk.config")
MY_CLI_CONFIG = (
    (ROOT / "config" / "overlay" / "const_my_cli.config")
    if (ROOT / "config" / "overlay" / "const_my_cli.config").is_file()
    or not (ROOT / "config" / "const_my_cli.config").is_file()
    else (ROOT / "config" / "const_my_cli.config")
)

START_TIME = time.time()
FLASK_VERSION = ""
try:
    from importlib.metadata import version as _pkg_version
    FLASK_VERSION = _pkg_version("flask")
except Exception:  # pragma: no cover
    FLASK_VERSION = "unknown"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    """Return JSON instead of HTML for all abort() errors so the Web UI shows exact messages."""
    return jsonify({
        "ok": False,
        "code": exc.code,
        "error": exc.description,
        "description": exc.description,
    }), exc.code


# ------------------------------------------------------------------------------
# Root-bound wrappers around telua_web_core helpers
# ------------------------------------------------------------------------------
def ensure_overlay_configs():
    _ensure_overlay_configs_for_root(ROOT)


def scan_files():
    return scan_files_in_root(ROOT)


def registry_names():
    return {f["name"] for f in scan_files()}


def resolve_allowed(name):
    """Resolve a registry name to an absolute path, aborting on anything else."""
    if not name or ("/" in name and ".." in name):
        abort(400, description="Invalid file name.")
    if name not in registry_names():
        abort(404, description="'%s' is not an editable config file." % name)
    full = (ROOT / name).resolve()
    root_real = ROOT.resolve()
    if root_real not in full.parents and full != root_real:
        abort(400, description="Path escapes the toolkit root.")
    return full


def parse_version():
    return parse_version_from_file(BUILD_APK_SH)


def parse_active_project():
    return parse_active_project_from_file(APK_CONFIG)


def parse_profiles():
    return parse_profiles_from_file(APK_CONFIG)


def _crypto_items():
    return crypto_items_for_root(ROOT)


# ------------------------------------------------------------------------------
# REST API — Status & Files
# ------------------------------------------------------------------------------
@app.get("/api/ping")
def api_ping():
    return jsonify({"ok": True, "tool": "telua_web", "time": int(time.time())})


@app.get("/api/status")
def api_status():
    return jsonify({
        "ok": True,
        "version": parse_version(),
        "flask_version": FLASK_VERSION,
        "root": str(ROOT),
        "active_project": parse_active_project(),
        "profiles": parse_profiles(),
        "adb_devices": adb_devices(),
        "ram": ram_info(),
        "uptime_s": int(time.time() - START_TIME),
        "python": sys.version.split()[0],
    })


@app.get("/api/files")
def api_files():
    return jsonify({"ok": True, "files": scan_files()})


@app.get("/api/file")
def api_file_read():
    name = request.args.get("name", "")
    full = resolve_allowed(name)
    try:
        content = full.read_text(encoding="utf-8", errors="replace")
        stat = full.stat()
    except OSError as exc:
        abort(400, description="Cannot read '%s': %s" % (name, exc))
    return jsonify({
        "ok": True,
        "name": name,
        "content": content,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "readonly": (not os.access(full, os.W_OK)) or name.endswith(".example"),
        "kind": "json" if name.endswith(".json") else "bash",
    })


@app.post("/api/file")
def api_file_write():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    content = data.get("content")
    force = bool(data.get("force", False))
    if content is None or not isinstance(content, str):
        abort(400, description="Missing 'content' string in request body.")

    full = resolve_allowed(name)
    if name.endswith(".example") or not os.access(full, os.W_OK):
        abort(403, description="File '%s' is read-only." % name)

    kind = "json" if name.endswith(".json") else "bash"
    error = validate_content(kind, content)
    if error and not force:
        return jsonify({"ok": False, "validated": True, "error": error}), 400

    backup = None
    if full.exists():
        backup_path = full.with_suffix(full.suffix + ".bak")
        try:
            shutil.copy2(full, backup_path)
            backup = str(backup_path.relative_to(ROOT))
        except OSError:
            backup = None

    try:
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
    except OSError as exc:
        abort(500, description="Cannot write '%s': %s" % (name, exc))

    return jsonify({
        "ok": True,
        "name": name,
        "backup": backup,
        "bytes": len(content.encode("utf-8")),
        "forced": force and error is not None,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.post("/api/profile")
def api_profile():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        abort(400, description="Missing 'name' (profile) in request body.")
    profiles = parse_profiles()
    if name not in profiles:
        abort(400, description="Unknown profile '%s'. Available: %s"
                              % (name, ", ".join(profiles) or "none"))
    if not APK_CONFIG.is_file():
        abort(404, description="apk.config not found in %s" % ROOT)

    text = APK_CONFIG.read_text(encoding="utf-8", errors="ignore")
    new_text, count = re.subn(
        r'(?m)^(\s*ACTIVE_PROJECT\s*=\s*)"[^"]*"',
        lambda m: '%s"%s"' % (m.group(1), name),
        text, count=1)
    if count == 0:
        abort(400, description="ACTIVE_PROJECT line not found in apk.config.")

    backup = None
    try:
        backup_path = APK_CONFIG.with_suffix(".config.bak")
        shutil.copy2(APK_CONFIG, backup_path)
        backup = str(backup_path.relative_to(ROOT))
    except OSError:
        backup = None
    APK_CONFIG.write_text(new_text, encoding="utf-8")
    return jsonify({"ok": True, "active_project": name, "backup": backup})


@app.get("/api/info")
def api_info():
    """Run 'build_apk.sh --info' (read-only diagnostics) and return its output."""
    if not BUILD_APK_SH.is_file():
        abort(404, description="build_apk.sh not found in %s" % ROOT)
    try:
        proc = subprocess.run(
            ["bash", str(BUILD_APK_SH), "--info"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "[ERROR] 'build_apk.sh --info' timed out after 60s.", 124
    except Exception as exc:  # pragma: no cover
        output, code = "[ERROR] Failed to run build_apk.sh: %s" % exc, 1
    return jsonify({"ok": code == 0, "exit_code": code, "output": output})


# ------------------------------------------------------------------------------
# Crypto & Overlay API
# ------------------------------------------------------------------------------
@app.get("/api/crypto/status")
def api_crypto_status():
    return jsonify({
        "ok": True,
        "overlay_dir": "config/overlay",
        "items": _crypto_items(),
    })


@app.post("/api/crypto/action")
def api_crypto_action():
    """Encrypt/decrypt private overlay configs or apply apk_overlays.config -> apk.config."""
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "")).strip().lower()
    target = str(data.get("target", "all")).strip()
    password = str(data.get("password", ""))
    apply_overlay = bool(data.get("apply_overlay", False))
    force = bool(data.get("force", False))
    if action == "decrypt_force":
        action = "decrypt"
        force = True

    if action not in ("encrypt", "decrypt", "apply_overlay"):
        abort(400, description="Invalid action '%s' (use 'encrypt', 'decrypt', 'decrypt_force', or 'apply_overlay')." % action)
    if target not in ("all", "apk_overlays.config", "const_my_cli.config"):
        abort(400, description="Invalid target '%s'." % target)

    overlay_dir = ROOT / "config" / "overlay"
    crypto_script = ROOT / "python" / "config_crypto.py"
    overlay_script = ROOT / "python" / "config_overlay.py"
    logs = []

    if action in ("encrypt", "decrypt"):
        if not password:
            abort(400, description="Password must not be empty.")
        if not crypto_script.is_file():
            abort(404, description="python/config_crypto.py not found.")

        try:
            import cryptography  # noqa: F401
        except ImportError:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "cryptography"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            )

        force_args = ["--force"] if (action == "encrypt" or force) else []

        if target == "all":
            if action == "decrypt":
                has_any_enc = any((overlay_dir / ("enc_" + n)).is_file() for n in PRIVATE_OVERLAY_NAMES)
                if not has_any_enc:
                    abort(400, description="No encrypted files (enc_*.config) found in config/overlay/ to decrypt. Click '🔐 Encrypt' first.")
            cmd = [sys.executable, str(crypto_script), action, "-", "-d", str(overlay_dir)] + force_args
        else:
            plain_file = overlay_dir / target
            enc_file = overlay_dir / ("enc_" + target)
            dec_file = overlay_dir / ("dec_" + target)
            if action == "encrypt":
                if not plain_file.is_file():
                    abort(404, description="config/overlay/%s does not exist." % target)
                cmd = [sys.executable, str(crypto_script), "encrypt", "-", "-i", str(plain_file), "-o", str(enc_file), "--force"]
            else:
                if not enc_file.is_file():
                    abort(404, description="config/overlay/enc_%s does not exist yet (click '🔐 Encrypt' first)." % target)
                out_file = plain_file if force else dec_file
                cmd = [sys.executable, str(crypto_script), "decrypt", "-", "-i", str(enc_file), "-o", str(out_file)] + force_args

        try:
            proc = subprocess.run(
                cmd,
                input=password + "\n",
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if proc.returncode != 0:
                abort(400, description=out or ("Crypto %s failed (exit %d)." % (action, proc.returncode)))
            if out:
                logs.append(out)
        except subprocess.TimeoutExpired:
            abort(504, description="Crypto command timed out.")

    if action == "apply_overlay" or (action == "decrypt" and force and apply_overlay):
        ov_file = overlay_dir / "apk_overlays.config"
        if not ov_file.is_file():
            if action == "apply_overlay":
                abort(404, description="config/overlay/apk_overlays.config not found (decrypt or create it first).")
        elif APK_CONFIG.is_file() and overlay_script.is_file():
            proc = subprocess.run(
                [sys.executable, str(overlay_script), str(APK_CONFIG), str(ov_file)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if proc.returncode != 0:
                abort(400, description=out or "Failed to apply apk_overlays.config.")
            if out:
                logs.append(out)

    return jsonify({
        "ok": True,
        "action": action,
        "target": target,
        "output": "\n".join(logs),
        "items": _crypto_items(),
    })


# ------------------------------------------------------------------------------
# Pipelines API
# ------------------------------------------------------------------------------
PIPELINE_SOURCES = {
    "my": {
        "file": MY_CLI_CONFIG,
        "prefix": "MY",
        "label": "Personal pipelines (telua my <name>)",
    },
    "multi": {
        "file": ROOT / "config" / "const_multi_cli.config",
        "prefix": "MULTI",
        "label": "Multi-CLI pipelines (telua run <group>)",
    },
    "docker": {
        "file": ROOT / "config" / "const_system_cli.config",
        "prefix": "SYSTEM",
        "label": "System & Docker CLI pipelines (telua system <action>)",
    },
    "system": {
        "file": ROOT / "config" / "const_system_cli.config",
        "prefix": "SYSTEM",
        "label": "System & Docker CLI pipelines (telua system <action>)",
    },
    "car": {
        "file": ROOT / "config" / "const_car.config",
        "prefix": "CAR",
        "list_var": "CAR_CLI_LIST",
        "var_prefix": "ADB_SHELL_CAR_",
        "label": "AAOS Car control commands (telua car <action>)",
    },
    "dump": {
        "file": ROOT / "config" / "const_dumpsys.config",
        "prefix": "DUMP",
        "list_var": "DUMP_CLI_LIST",
        "var_prefix": "ADB_SHELL_DUMP_",
        "label": "Dumpsys diagnostics commands (telua dump <target>)",
    },
}


def _pipeline_source(source):
    """Resolve a pipeline source key ('my' | 'multi' | 'system' | 'docker' | 'car' | 'dump') to its descriptor."""
    key = (source or "my").strip().lower()
    if key not in PIPELINE_SOURCES:
        abort(400, description="Unknown pipeline source '%s' (use 'my', 'multi', 'system', 'car', or 'dump')." % key)
    return key, PIPELINE_SOURCES[key]


def _pipeline_config_path(source):
    """Resolve the config file for a source (fall back to the .example)."""
    key, _ = _pipeline_source(source)
    if key == "my":
        candidates = [
            ROOT / "config" / "overlay" / "const_my_cli.config",
            ROOT / "config" / "const_my_cli.config",
            ROOT / "config" / "overlay" / "const_my_cli.config.example",
            ROOT / "config" / "const_my_cli.config.example",
        ]
    elif key in ("docker", "system"):
        candidates = [
            ROOT / "config" / "overlay" / "const_system_cli.config",
            ROOT / "config" / "const_system_cli.config",
            ROOT / "const_system_cli.config",
        ]
    elif key == "car":
        candidates = [
            ROOT / "config" / "overlay" / "const_car.config",
            ROOT / "config" / "const_car.config",
            ROOT / "const_car.config",
        ]
    elif key == "dump":
        candidates = [
            ROOT / "config" / "overlay" / "const_dumpsys.config",
            ROOT / "config" / "const_dumpsys.config",
            ROOT / "const_dumpsys.config",
        ]
    else:
        path = ROOT / "config" / "const_multi_cli.config"
        candidates = [path, path.with_suffix(".config.example")]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def parse_pipelines(source="my"):
    """Parse <PREFIX>_GROUP_LIST + <PREFIX>_CMD_* arrays (or CAR_CLI_LIST / DUMP_CLI_LIST) into pipeline dicts."""
    key, desc = _pipeline_source(source)
    path = _pipeline_config_path(source)
    if not path:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    if key in ("car", "dump"):
        return _parse_cli_list_pipelines(lines, desc["list_var"], desc["var_prefix"])
    return parse_array_pipelines(lines, desc["prefix"])


def rewrite_pipeline_config(pipelines, source="my"):
    """Rewrite <PREFIX>_GROUP_LIST and every <PREFIX>_CMD_* array in the file."""
    key, desc = _pipeline_source(source)
    path = _pipeline_config_path(source)
    if not path:
        abort(404, description="Pipeline config for '%s' not found (run 'telua init' first)." % source)
    if not os.access(path, os.W_OK):
        abort(403, description="%s is read-only." % path.name)

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    if key in ("car", "dump"):
        out = _rewrite_cli_list_lines(lines, pipelines, desc["list_var"], desc["var_prefix"])
    else:
        out = rewrite_array_pipeline_lines(lines, pipelines, desc["prefix"])

    new_text = "\n".join(out)
    if text.endswith("\n") or not text:
        new_text += "\n"

    error = validate_content("bash", new_text)
    if error:
        abort(400, description="Rewrite would break bash syntax: %s" % error)

    backup = None
    try:
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        backup = str(backup_path.relative_to(ROOT)).replace(os.sep, "/")
    except OSError:
        backup = None

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_text)
    return backup


@app.get("/api/pipelines")
def api_pipelines():
    source = request.args.get("source", "my")
    _, desc = _pipeline_source(source)
    path = _pipeline_config_path(source)
    return jsonify({
        "ok": True,
        "source": _pipeline_source(source)[0],
        "label": desc["label"],
        "file": str(path.relative_to(ROOT)).replace(os.sep, "/") if path else None,
        "pipelines": parse_pipelines(source),
    })


@app.post("/api/pipelines")
def api_pipelines_save():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "my")
    pipelines = data.get("pipelines")
    if not isinstance(pipelines, list):
        abort(400, description="Missing 'pipelines' list in request body.")

    cleaned = []
    names = set()
    for p in pipelines:
        if not isinstance(p, dict):
            abort(400, description="Each pipeline must be an object.")
        name = str(p.get("name", "")).strip().lower()
        if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            abort(400, description="Invalid pipeline name '%s' (use letters, digits, - _)." % name)
        if name in names:
            abort(400, description="Duplicate pipeline name '%s'." % name)
        names.add(name)
        steps = p.get("steps", [])
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            abort(400, description="Pipeline '%s': 'steps' must be a list of strings." % name)
        cleaned.append({
            "name": name,
            "description": str(p.get("description", "")).strip(),
            "steps": steps,
            "orphan": bool(p.get("orphan", False)),
        })

    backup = rewrite_pipeline_config(cleaned, source)
    return jsonify({
        "ok": True,
        "source": _pipeline_source(source)[0],
        "count": len(cleaned),
        "backup": backup,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.post("/api/pipeline/run")
def api_pipeline_run():
    """Execute one pipeline via 'telua my <name>' or 'telua run <group>'."""
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    source = data.get("source", "my")
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        abort(400, description="Invalid pipeline name.")
    key, _ = _pipeline_source(source)
    known = {p["name"] for p in parse_pipelines(key)}
    if name not in known:
        group_var = {
            "my": "MY_GROUP_LIST",
            "multi": "MULTI_GROUP_LIST",
            "docker": "SYSTEM_GROUP_LIST",
            "system": "SYSTEM_GROUP_LIST",
            "car": "CAR_CLI_LIST",
            "dump": "DUMP_CLI_LIST",
        }[key]
        abort(404, description="Pipeline '%s' not found in %s." % (name, group_var))
    script = BUILD_APK_SH
    if not script.is_file():
        abort(404, description="build_apk.sh not found in %s" % ROOT)
    subcommand = {"my": "my", "multi": "run", "docker": "system", "system": "system", "car": "car", "dump": "dump"}[key]
    try:
        proc = subprocess.run(
            ["bash", str(script), subcommand, name],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "[ERROR] Pipeline '%s' timed out after 300s." % name, 124
    except Exception as exc:  # pragma: no cover
        output, code = "[ERROR] Failed to run pipeline: %s" % exc, 1
    return jsonify({"ok": code == 0, "exit_code": code, "output": output})


@app.post("/api/pipeline/stream")
def api_pipeline_stream():
    """Stream pipeline execution output line-by-line in real time."""
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    source = data.get("source", "my")
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        abort(400, description="Invalid pipeline name.")
    key, _ = _pipeline_source(source)
    known = {p["name"] for p in parse_pipelines(key)}
    if name not in known:
        group_var = {
            "my": "MY_GROUP_LIST",
            "multi": "MULTI_GROUP_LIST",
            "docker": "SYSTEM_GROUP_LIST",
            "system": "SYSTEM_GROUP_LIST",
            "car": "CAR_CLI_LIST",
            "dump": "DUMP_CLI_LIST",
        }[key]
        abort(404, description="Pipeline '%s' not found in %s." % (name, group_var))
    script = BUILD_APK_SH
    if not script.is_file():
        abort(404, description="build_apk.sh not found in %s" % ROOT)
    subcommand = {"my": "my", "multi": "run", "docker": "system", "system": "system", "car": "car", "dump": "dump"}[key]

    def generate():
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = subprocess.Popen(
                ["bash", str(script), subcommand, name],
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            if proc.stdout is not None:
                for line in iter(proc.stdout.readline, ""):
                    yield line
                proc.stdout.close()
            code = proc.wait(timeout=300)
        except Exception as exc:  # pragma: no cover
            yield "\n[ERROR] Failed to stream pipeline: %s\n" % exc
            code = 1
        yield "\n__TELUA_EXIT_CODE__:%d\n" % code

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


import signal

_ACTIVE_TERM_LOCK = threading.Lock()
_ACTIVE_TERM_PROCS = set()


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
    script_path = str(BUILD_APK_SH).replace("\\", "/")
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


@app.post("/api/terminal/run")
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
    try:
        proc = subprocess.run(
            exec_args,
            shell=use_shell,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "[ERROR] Command timed out after 300s.", 124
    except Exception as exc:  # pragma: no cover
        output, code = "[ERROR] Failed to execute command: %s" % exc, 1
    return jsonify({"ok": code == 0, "exit_code": code, "output": output, "cwd": str(ROOT)})


@app.post("/api/terminal/stream")
def api_terminal_stream():
    """Stream ad-hoc shell / telua CLI command output line-by-line in real time."""
    data = request.get_json(silent=True) or {}
    cmd = str(data.get("command", "")).strip()
    cwd = str(data.get("cwd", "")).strip()
    if not cmd:
        abort(400, description="Missing 'command' in request body.")
    exec_args, use_shell = _resolve_terminal_exec(cmd, cwd)

    def generate():
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = None
        try:
            proc = subprocess.Popen(
                exec_args,
                shell=use_shell,
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
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


@app.post("/api/terminal/stop")
def api_terminal_stop():
    """Stop (SIGINT/SIGTERM) any currently running terminal command."""
    with _ACTIVE_TERM_LOCK:
        procs = list(_ACTIVE_TERM_PROCS)
        _ACTIVE_TERM_PROCS.clear()
    for p in procs:
        _kill_term_proc(p)
    return jsonify({"ok": True, "stopped": len(procs)})


# ------------------------------------------------------------------------------
# Static frontend & entry point
# ------------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html", max_age=0)


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


def open_browser(url: str):
    """Best-effort launch of the default browser (Linux / Windows / macOS)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(url)  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def print_banner(host: str, port: int):
    url = "http://%s:%d" % ("127.0.0.1" if host in ("0.0.0.0", "::") else host, port)
    print("")
    print("=" * 64)
    print("  TELUA WEB - Config Manager UI (Flask backend)")
    print("=" * 64)
    print("  Toolkit root : %s" % ROOT)
    print("  Static assets: %s" % STATIC_DIR)
    print("  Local URL    : %s" % url)
    if host in ("0.0.0.0", "::"):
        print("  LAN access   : http://<host-ip>:%d" % port)
    print("  Stop server  : telua web stop   (or Ctrl+C here)")
    print("=" * 64)
    print("")


def main():
    global ROOT, BUILD_APK_SH, APK_CONFIG, MY_CLI_CONFIG

    parser = argparse.ArgumentParser(
        prog="telua_web.py",
        description="Telua Web UI - Flask backend for browsing & editing toolkit configs")
    parser.add_argument("--host", default=os.environ.get("TELUA_WEB_HOST", "127.0.0.1"),
                        help="bind address (default: 127.0.0.1, use 0.0.0.0 for LAN)")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("TELUA_WEB_PORT", "8788")),
                        help="TCP port (default: 8788)")
    parser.add_argument("--root", default=None,
                        help="toolkit root directory (default: parent of web/)")
    parser.add_argument("--open-browser", action="store_true",
                        help="open the UI in the default browser after startup")
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).resolve()
        if not root.is_dir():
            sys.stderr.write("[ERROR] Root directory not found: %s\n" % root)
            sys.exit(1)
        ROOT = root
        BUILD_APK_SH = ROOT / "build_apk.sh"
        APK_CONFIG = (ROOT / "config" / "apk.config") if (ROOT / "config" / "apk.config").is_file() else (ROOT / "apk.config")
        MY_CLI_CONFIG = (
            (ROOT / "config" / "overlay" / "const_my_cli.config")
            if (ROOT / "config" / "overlay" / "const_my_cli.config").is_file()
            or not (ROOT / "config" / "const_my_cli.config").is_file()
            else (ROOT / "config" / "const_my_cli.config")
        )
        PIPELINE_SOURCES["my"]["file"] = MY_CLI_CONFIG
        PIPELINE_SOURCES["multi"]["file"] = ROOT / "config" / "const_multi_cli.config"
        PIPELINE_SOURCES["docker"]["file"] = ROOT / "config" / "const_system_cli.config"
        PIPELINE_SOURCES["system"]["file"] = ROOT / "config" / "const_system_cli.config"

    if not STATIC_DIR.is_dir():
        sys.stderr.write("[ERROR] Static assets directory not found: %s\n" % STATIC_DIR)
        sys.exit(1)

    ensure_overlay_configs()

    if args.open_browser:
        url = "http://127.0.0.1:%d" % args.port
        threading.Timer(1.2, open_browser, args=(url,)).start()

    print_banner(args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
