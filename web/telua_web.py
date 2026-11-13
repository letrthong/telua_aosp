#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Contribution History:
#   - 2026-11: Thong Le <letrthong@gmail.com> (Architecture & Domain Design)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# telua_web.py - Flask Web UI backend for the Telua toolkit.
# Single source of truth for the code behind 'telua web start':
#   - Serves the static frontend (web/static/index.html + app.js + style.css)
#   - REST API to browse & edit toolkit config files (*.config / *.json):
#       GET  /api/ping     : liveness probe (used by 'telua web start/status')
#       GET  /api/status   : toolkit version, active project, profiles, ADB, RAM
#       GET  /api/files    : registry of editable config files
#       GET  /api/file     : read one config file (?name=<relative path>)
#       POST /api/file     : save one config file (backup + syntax validation)
#       POST /api/profile  : switch ACTIVE_PROJECT in apk.config (like 'telua -p')
#       GET  /api/info     : run 'build_apk.sh --info' and return its output
#
# Safety model:
#   - Only files present in the scanned registry (root/*.config|*.json and
#     config/*.config|*.json) can be read or written (whitelist, no traversal).
#   - Saves create a '<file>.bak' backup of the previous content.
#   - Bash files are validated with 'bash -n', JSON files with json.loads.
#     A failing validation rejects the save unless force=true is passed.
#   - Binds to 127.0.0.1 by default (use --host 0.0.0.0 to expose on LAN).
#
# Usage:
#   python3 web/telua_web.py [--host 127.0.0.1] [--port 8788]
#                            [--root /path/to/toolkit] [--open-browser]
#
# Requires: flask  (pip install flask  -  see requirements.txt)

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from flask import Flask, abort, jsonify, request, send_from_directory
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "[ERROR] Flask is not installed.\n"
        "        Install it with:  python3 -m pip install flask\n"
        "        (or run 'telua web start' which auto-installs it)\n"
    )
    sys.exit(1)

# ------------------------------------------------------------------------------
# Paths (resolved from this file location: <toolkit>/web/telua_web.py)
# ------------------------------------------------------------------------------
SCRIPT_FILE = Path(__file__).resolve()
WEB_DIR = SCRIPT_FILE.parent
STATIC_DIR = WEB_DIR / "static"
DEFAULT_ROOT = WEB_DIR.parent

ROOT = DEFAULT_ROOT                 # toolkit root (config registry base), set by --root
BUILD_APK_SH = ROOT / "build_apk.sh"
APK_CONFIG = (ROOT / "config" / "apk.config") if (ROOT / "config" / "apk.config").is_file() else (ROOT / "apk.config")
MY_CLI_CONFIG = ROOT / "config" / "const_my_cli.config"

START_TIME = time.time()
FLASK_VERSION = ""
try:  # Flask 3.x removed __version__
    from importlib.metadata import version as _pkg_version
    FLASK_VERSION = _pkg_version("flask")
except Exception:  # pragma: no cover
    FLASK_VERSION = "unknown"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


# ------------------------------------------------------------------------------
# Config file registry (whitelist of editable files)
# ------------------------------------------------------------------------------
def is_editable_name(name: str) -> bool:
    """True for *.config / *.json files, excluding backups & encrypted blobs."""
    if not name.endswith((".config", ".json")):
        return False
    if name.endswith(".bak") or ".bak." in name:
        return False
    if name.startswith("enc_"):        # encrypted template: never edit via UI
        return False
    return True


def scan_files():
    """Scan toolkit root + config/ for editable config files."""
    entries = []
    seen = set()

    def add(rel: str):
        full = ROOT / rel
        if rel in seen or not full.is_file():
            return
        seen.add(rel)
        try:
            stat = full.stat()
        except OSError:
            return
        entries.append({
            "name": rel.replace(os.sep, "/"),
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "mtime_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "readonly": (not os.access(full, os.W_OK)) or rel.endswith(".example"),
            "kind": "json" if rel.endswith(".json") else "bash",
            "group": "config" if rel.startswith("config/") else "root",
        })

    # 1. Root-level configs first (apk.config, apk_overlays.config, ...)
    try:
        for name in sorted(os.listdir(ROOT)):
            if is_editable_name(name) and (ROOT / name).is_file():
                add(name)
    except OSError:
        pass

    # 2. Then the config/ directory (const_*.config cheatsheets & pipelines)
    cfg_dir = ROOT / "config"
    if cfg_dir.is_dir():
        for name in sorted(os.listdir(cfg_dir)):
            if is_editable_name(name) and (cfg_dir / name).is_file():
                add("config/" + name)

    # 2b. Personal overlay dir (git-ignored): apk_overlays.config, const_my_cli.config
    overlay_dir = ROOT / "config" / "overlay"
    if overlay_dir.is_dir():
        for name in sorted(os.listdir(overlay_dir)):
            if is_editable_name(name) and (overlay_dir / name).is_file():
                add("config/overlay/" + name)

    # Stable, human-friendly ordering: apk.config on top, then the rest.
    priority = {
        "config/apk.config": 0,
        "apk.config": 0,
        "config/overlay/apk_overlays.config": 1,
        "config/apk_overlays.config": 1,
        "apk_overlays.config": 1,
    }
    entries.sort(key=lambda f: (priority.get(f["name"], 2), f["name"]))
    return entries


def registry_names():
    return {f["name"] for f in scan_files()}


def resolve_allowed(name):
    """Resolve a registry name to an absolute path, aborting on anything else."""
    if not name or "/" in name and ".." in name:
        abort(400, description="Invalid file name.")
    if name not in registry_names():
        abort(404, description="'%s' is not an editable config file." % name)
    full = (ROOT / name).resolve()
    root_real = ROOT.resolve()
    if root_real not in full.parents and full != root_real:
        abort(400, description="Path escapes the toolkit root.")
    return full


# ------------------------------------------------------------------------------
# Validation (bash -n for .config, json.loads for .json)
# ------------------------------------------------------------------------------
def validate_content(kind: str, content: str):
    """Return None when valid, else a human-readable error string."""
    if kind == "json":
        try:
            json.loads(content)
            return None
        except ValueError as exc:
            return "Invalid JSON: %s" % exc
    # Bash-style config: syntax check with 'bash -n' when bash is available.
    bash = shutil.which("bash")
    if not bash:
        return None
    tmp = tempfile.NamedTemporaryFile("w", suffix=".config", delete=False, encoding="utf-8")
    try:
        tmp.write(content)
        tmp.close()
        proc = subprocess.run([bash, "-n", tmp.name],
                              capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            err = (proc.stderr or "syntax error").strip()
            # Strip the temp path from bash's message for readability.
            err = err.replace(tmp.name, "<buffer>")
            return "Bash syntax error: %s" % err
        return None
    except Exception as exc:  # pragma: no cover
        return "Validation failed: %s" % exc
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ------------------------------------------------------------------------------
# Toolkit status parsing (version / active project / profiles / adb / ram)
# ------------------------------------------------------------------------------
def parse_version():
    try:
        text = BUILD_APK_SH.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'SCRIPT_VERSION="([^"]+)"', text)
        return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


def parse_active_project():
    try:
        text = APK_CONFIG.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'^\s*ACTIVE_PROJECT\s*=\s*"([^"]*)"', text, re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def parse_profiles():
    """Extract profile names from the 'case "$ACTIVE_PROJECT" in ... esac' block."""
    try:
        text = APK_CONFIG.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    m = re.search(r'case\s+"\$ACTIVE_PROJECT"\s+in(.*?)\nesac', text, re.S)
    if not m:
        return []
    names = re.findall(r'^\s{4}"([^"]+)"\)', m.group(1), re.M)
    return [n for n in names if n != "*"]


def adb_devices():
    """Return the list of connected ADB device serials ([] when adb missing)."""
    adb = shutil.which("adb")
    if not adb:
        return []
    try:
        proc = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10)
        devices = []
        for line in (proc.stdout or "").splitlines()[1:]:
            line = line.strip()
            if line and "\t" in line:
                serial, state = line.split("\t", 1)
                devices.append({"serial": serial, "state": state.strip()})
        return devices
    except Exception:
        return []


def ram_info():
    """Parse /proc/meminfo (Linux) into GB values; None when unavailable."""
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None
    values = {}
    for key in ("MemTotal", "MemAvailable", "SwapTotal"):
        m = re.search(r"^%s:\s+(\d+)" % key, text, re.M)
        if m:
            values[key] = int(m.group(1)) / 1048576.0  # kB -> GB
    if "MemTotal" not in values:
        return None
    total = values.get("MemTotal", 0.0)
    avail = values.get("MemAvailable", 0.0)
    return {
        "total_gb": round(total, 2),
        "available_gb": round(avail, 2),
        "used_gb": round(total - avail, 2),
        "used_pct": int((total - avail) * 100 / total) if total > 0 else 0,
        "swap_total_gb": round(values.get("SwapTotal", 0.0), 2),
    }


# ------------------------------------------------------------------------------
# REST API
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
# Pipelines API (MY_GROUP_LIST/MY_CMD_* in const_my_cli.config AND
#                MULTI_GROUP_LIST/MULTI_CMD_* in const_multi_cli.config)
# ------------------------------------------------------------------------------
# A pipeline item is one entry of <PREFIX>_GROUP_LIST: "name :: description".
# Its steps live in the bash array <PREFIX>_CMD_<NAME_UPPERCASE>=( "step 1" ... ).
# The API exposes them as structured JSON so the Web UI can render one card per
# pipeline with an editable step list (add / edit / delete / reorder).
# Both config files share the same syntax; only the variable prefix differs:
#   source="my"    -> config/const_my_cli.config    (MY_GROUP_LIST / MY_CMD_*)
#   source="multi" -> config/const_multi_cli.config (MULTI_GROUP_LIST / MULTI_CMD_*)

MY_GROUP_RE = re.compile(r'^\s*"([A-Za-z0-9_-]+)\s*::\s*([^"]*)"\s*$')
MY_STEP_RE = re.compile(r'^\s*"(.*)"\s*$')

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
}


def _pipeline_source(source):
    """Resolve a pipeline source key ('my' | 'multi') to its descriptor."""
    key = (source or "my").strip().lower()
    if key not in PIPELINE_SOURCES:
        abort(400, description="Unknown pipeline source '%s' (use 'my' or 'multi')." % key)
    return key, PIPELINE_SOURCES[key]


def _pipeline_config_path(source):
    """Resolve the config file for a source (fall back to the .example)."""
    _, desc = _pipeline_source(source)
    path = desc["file"]
    if path.is_file():
        return path
    example = path.with_suffix(".config.example")
    if example.is_file():
        return example
    return None


def parse_pipelines(source="my"):
    """Parse <PREFIX>_GROUP_LIST + <PREFIX>_CMD_* arrays into pipeline dicts."""
    _, desc = _pipeline_source(source)
    prefix = desc["prefix"]
    group_list_re = re.compile(r'^\s*%s_GROUP_LIST\s*=\s*\(' % prefix)
    cmd_re = re.compile(r'^\s*%s_CMD_([A-Z0-9_]+)\s*=\s*\(\s*$' % prefix)

    path = _pipeline_config_path(source)
    if not path:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    # 1. Registry entries from <PREFIX>_GROUP_LIST=( ... )
    registry = []
    in_group_list = False
    for line in lines:
        if group_list_re.match(line):
            in_group_list = True
            continue
        if in_group_list:
            if line.strip().startswith(")"):
                in_group_list = False
                continue
            m = MY_GROUP_RE.match(line)
            if m:
                registry.append({"name": m.group(1).strip(), "description": m.group(2).strip()})

    # 2. Step arrays: <PREFIX>_CMD_<SUFFIX>=( "step" ... ) possibly spanning lines.
    arrays = {}
    current_suffix = None
    current_steps = []
    for line in lines:
        stripped = line.strip()
        if current_suffix is None:
            m = cmd_re.match(line)
            if m:
                current_suffix = m.group(1)
                current_steps = []
            continue
        # Inside an array definition
        if stripped.startswith(")"):
            arrays[current_suffix] = current_steps
            current_suffix = None
            current_steps = []
            continue
        m = MY_STEP_RE.match(stripped)
        if m:
            current_steps.append(m.group(1))

    # 3. Merge: one pipeline per registry entry (steps may be missing).
    pipelines = []
    seen = set()
    for item in registry:
        name = item["name"]
        suffix = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
        seen.add(suffix)
        pipelines.append({
            "name": name,
            "description": item["description"],
            "array": "%s_CMD_%s" % (prefix, suffix),
            "steps": arrays.get(suffix, []),
        })

    # 4. Orphan arrays (defined but not registered) are still shown, flagged.
    for suffix, steps in arrays.items():
        if suffix not in seen:
            pipelines.append({
                "name": suffix.lower(),
                "description": "(not registered in %s_GROUP_LIST)" % prefix,
                "array": "%s_CMD_%s" % (prefix, suffix),
                "steps": steps,
                "orphan": True,
            })
    return pipelines


def _bash_quote(step: str) -> str:
    """Quote a step for safe embedding in a double-quoted bash array element."""
    return step.replace("\\", "\\\\").replace('"', '\\"')


def serialize_pipelines(pipelines, prefix="MY"):
    """Rebuild the <PREFIX>_GROUP_LIST block and all <PREFIX>_CMD_* arrays.

    Returns (group_list_lines, cmd_blocks) where cmd_blocks is a list of
    (comment_hint, [array lines]) preserving the original array order.
    """
    group_lines = ["%s_GROUP_LIST=(" % prefix]
    for p in pipelines:
        if p.get("orphan"):
            continue
        group_lines.append('    "%s :: %s"' % (p["name"], p.get("description", "")))
    group_lines.append(")")

    cmd_blocks = []
    for p in pipelines:
        suffix = re.sub(r"[^A-Za-z0-9]", "_", p["name"]).upper()
        block = ["%s_CMD_%s=(" % (prefix, suffix)]
        for step in p.get("steps", []):
            block.append('    "%s"' % _bash_quote(step))
        block.append(")")
        cmd_blocks.append((p["name"], block))
    return group_lines, cmd_blocks


def rewrite_pipeline_config(pipelines, source="my"):
    """Rewrite <PREFIX>_GROUP_LIST and every <PREFIX>_CMD_* array in the file.

    Strategy: replace the existing <PREFIX>_GROUP_LIST=( ... ) block in place,
    then replace each existing <PREFIX>_CMD_<SUFFIX>=( ... ) block in place,
    and append any brand-new arrays at the end of the file. Comments and all
    other content are preserved untouched.
    """
    _, desc = _pipeline_source(source)
    prefix = desc["prefix"]
    group_list_re = re.compile(r"^\s*%s_GROUP_LIST\s*=\s*\(" % prefix)
    cmd_re = re.compile(r'^\s*%s_CMD_([A-Z0-9_]+)\s*=\s*\(\s*$' % prefix)

    path = _pipeline_config_path(source)
    if not path:
        abort(404, description="%s not found (run 'telua init' first)." % path.name)
    if not os.access(path, os.W_OK):
        abort(403, description="%s is read-only." % path.name)

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    group_lines, cmd_blocks = serialize_pipelines(pipelines, prefix)

    out = []
    i = 0
    n = len(lines)
    replaced_groups = False
    replaced_arrays = set()

    while i < n:
        line = lines[i]

        # Replace the whole <PREFIX>_GROUP_LIST=( ... ) block
        if not replaced_groups and group_list_re.match(line):
            j = i
            while j < n and not lines[j].strip().startswith(")"):
                j += 1
            out.extend(group_lines)
            replaced_groups = True
            i = j + 1
            continue

        # Replace a whole <PREFIX>_CMD_<SUFFIX>=( ... ) block
        m = cmd_re.match(line)
        if m:
            suffix = m.group(1)
            j = i
            while j < n and not lines[j].strip().startswith(")"):
                j += 1
            for name_hint, block in cmd_blocks:
                block_suffix = re.sub(r"[^A-Za-z0-9]", "_", name_hint).upper()
                if block_suffix == suffix:
                    out.extend(block)
                    replaced_arrays.add(suffix)
                    break
            else:
                # Array removed in the new set: drop it entirely.
                pass
            i = j + 1
            continue

        out.append(line)
        i += 1

    # Append arrays that did not exist before (new pipelines).
    for name_hint, block in cmd_blocks:
        suffix = re.sub(r"[^A-Za-z0-9]", "_", name_hint).upper()
        if suffix not in replaced_arrays:
            if out and out[-1].strip() != "":
                out.append("")
            out.extend(block)

    new_text = "\n".join(out)
    if text.endswith("\n") or not text:
        new_text += "\n"

    # Safety: the rewritten file must still be valid bash.
    error = validate_content("bash", new_text)
    if error:
        abort(400, description="Rewrite would break bash syntax: %s" % error)

    backup = None
    try:
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        backup = str(backup_path.relative_to(ROOT))
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
        "file": str(path.relative_to(ROOT)) if path else None,
        "pipelines": parse_pipelines(source),
    })


@app.post("/api/pipelines")
def api_pipelines_save():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "my")
    pipelines = data.get("pipelines")
    if not isinstance(pipelines, list):
        abort(400, description="Missing 'pipelines' list in request body.")

    # Basic shape validation before touching the file.
    cleaned = []
    names = set()
    for p in pipelines:
        if not isinstance(p, dict):
            abort(400, description="Each pipeline must be an object.")
        name = str(p.get("name", "")).strip()
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
        group_var = "MY_GROUP_LIST" if key == "my" else "MULTI_GROUP_LIST"
        abort(404, description="Pipeline '%s' not found in %s." % (name, group_var))
    script = BUILD_APK_SH
    if not script.is_file():
        abort(404, description="build_apk.sh not found in %s" % ROOT)
    # 'my' pipelines run via 'telua my <name>', multi pipelines via 'telua run <group>'.
    subcommand = "my" if key == "my" else "run"
    try:
        proc = subprocess.run(
            ["bash", str(script), subcommand, name],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "[ERROR] Pipeline '%s' timed out after 300s." % name, 124
    except Exception as exc:  # pragma: no cover
        output, code = "[ERROR] Failed to run pipeline: %s" % exc, 1
    return jsonify({"ok": code == 0, "exit_code": code, "output": output})


# ------------------------------------------------------------------------------
# Static frontend
# ------------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html", max_age=0)


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


# ------------------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------------------
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
    global ROOT, BUILD_APK_SH, APK_CONFIG

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
        MY_CLI_CONFIG = ROOT / "config" / "const_my_cli.config"

    if not STATIC_DIR.is_dir():
        sys.stderr.write("[ERROR] Static assets directory not found: %s\n" % STATIC_DIR)
        sys.exit(1)

    if args.open_browser:
        url = "http://127.0.0.1:%d" % args.port
        threading.Timer(1.2, open_browser, args=(url,)).start()

    print_banner(args.host, args.port)
    # threaded=True: concurrent static + API requests; debug off (production-ish).
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
