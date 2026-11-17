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
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

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
from telua_web_docs import (  # noqa: E402
    detect_docs_project_dir,
    get_plantuml_url,
    html_to_rst,
    resolve_rst_target,
    rst_to_html,
    scan_docs_files,
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
LOGCAT_FILTERS_FILE = ROOT / "config" / "logcat_filters.json"
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
    overlay_config = ROOT / "config" / "overlay" / "apk_overlays.config"
    if overlay_config.is_file():
        proj = parse_active_project_from_file(overlay_config)
        if proj:
            return proj
    return parse_active_project_from_file(APK_CONFIG)


def parse_profiles():
    profs = parse_profiles_from_file(APK_CONFIG)
    overlay_config = ROOT / "config" / "overlay" / "apk_overlays.config"
    if overlay_config.is_file():
        ov_profs = parse_profiles_from_file(overlay_config)
        for p in ov_profs:
            if p not in profs:
                profs.append(p)
    return profs


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

    overlay_config = ROOT / "config" / "overlay" / "apk_overlays.config"
    if overlay_config.is_file():
        try:
            otext = overlay_config.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)"[^"]*"', otext):
                new_otext = re.sub(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)"[^"]*"', r'\g<1>"%s"' % name, otext, count=1)
                overlay_config.write_text(new_otext, encoding="utf-8")
        except OSError:
            pass

    # Keep the project source dir's apk.config in sync (create it when missing)
    # so 'tel b' run from that directory uses the newly selected profile.
    project_cfg = ensure_project_apk_config(name)

    return jsonify({"ok": True, "active_project": name, "backup": backup,
                    "project_apk_config": project_cfg})


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
# REST API — AOSP Configuration & Build Control
# ------------------------------------------------------------------------------
def _upsert_bash_var(text: str, var_name: str, value: str) -> str:
    """Updates an existing bash variable (including uncommenting it if commented), or appends it."""
    pattern = re.compile(r'^[ \t]*#?[ \t]*' + re.escape(var_name) + r'\s*=.*$', re.M)
    new_line = f'{var_name}="{value}"'
    if pattern.search(text):
        return pattern.sub(new_line, text, count=1)
    else:
        text = text.rstrip()
        return f'{text}\n{new_line}\n'


def _project_source_dir(info=None):
    """Absolute Path of the active project's source dir (<AOSP_TOP>/<SOURCE_CODE_RELATIVE_PATH>).

    'tel b' discovers apk.config from the current working directory upwards,
    so commands must run from this directory for the project to pick up its
    own apk.config. Returns None when the AOSP root or source path is unknown.
    """
    info = info if info is not None else _parse_aosp_info()
    root = (info.get("aosp_root_dir") or "").strip()
    src_rel = (info.get("source_path") or "").strip().strip("/")
    if not root or not src_rel:
        return None
    aosp_root = Path(root)
    top_rel = (info.get("aosp_top_rel_path") or "").strip().strip("/")
    if top_rel:
        aosp_top = aosp_root / top_rel
    else:
        # Mirror build_apk.sh auto-detection: prefer android/qssi, then qssi, then android.
        aosp_top = aosp_root
        for rel in ("android/qssi", "qssi", "android"):
            if (aosp_root / rel).is_dir():
                aosp_top = aosp_root / rel
                break
    return aosp_top / src_rel


def ensure_project_apk_config(project_name):
    """Create (or point ACTIVE_PROJECT of) <source_dir>/apk.config at project_name.

    A missing config is seeded from the toolkit template (config/apk.config) and
    merged with the personal overlay (config/overlay/apk_overlays.config via
    python/config_overlay.py) so every custom profile branch is available, then
    ACTIVE_PROJECT is set to project_name.

    Returns {"path": str, "created": bool, "updated": bool} or None when the
    source directory cannot be resolved (nothing is written in that case).
    """
    if not project_name:
        return None
    src_dir = _project_source_dir()
    if src_dir is None or not src_dir.is_dir():
        return None
    target = src_dir / "apk.config"
    result = {"path": str(target), "created": False, "updated": False}
    if not target.is_file():
        template = APK_CONFIG if APK_CONFIG.is_file() else ROOT / "apk.config"
        if not template.is_file():
            return None
        try:
            shutil.copy2(template, target)
        except OSError:
            return None
        result["created"] = True
        overlay = ROOT / "config" / "overlay" / "apk_overlays.config"
        overlay_script = ROOT / "python" / "config_overlay.py"
        if overlay.is_file() and overlay_script.is_file():
            try:
                subprocess.run(
                    [sys.executable, str(overlay_script), str(target), str(overlay)],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            except Exception:
                pass
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
        new_text, count = re.subn(
            r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)["\']?.*?["\']?[ \t]*$',
            lambda m: '%s"%s"' % (m.group(1), project_name),
            text, count=1)
        if count:
            target.write_text(new_text, encoding="utf-8")
            result["updated"] = True
    except OSError:
        pass
    return result


def _parse_aosp_info():
    text = ""
    if APK_CONFIG.is_file():
        try:
            text = APK_CONFIG.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass

    overlay_config = ROOT / "config" / "overlay" / "apk_overlays.config"
    overlay_text = ""
    if overlay_config.is_file():
        try:
            overlay_text = overlay_config.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass

    def get_var(name: str, default: str = "") -> str:
        if overlay_text:
            m = re.search(r'^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*["\']?(.*?)["\']?[ \t]*$', overlay_text, re.M)
            if m and not m.group(0).strip().startswith("#"):
                return m.group(1).strip()
        m = re.search(r'^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*["\']?(.*?)["\']?[ \t]*$', text, re.M)
        if m:
            val = m.group(1).strip()
            sub = re.match(r'^\$\{[A-Za-z0-9_]+:-(.*?)\}$', val)
            if sub:
                val = sub.group(1).strip()
            return val
        return default

    aosp_root = get_var("AOSP_ROOT_DIR", "")
    active_project = get_var("ACTIVE_PROJECT", "") or parse_active_project() or "oem_service"
    target_product = get_var("CONFIG_TARGET_PRODUCT", "")
    target_variant = get_var("CONFIG_TARGET_BUILD_VARIANT", "")
    aosp_top_rel = get_var("AOSP_TOP_REL_PATH", "")

    module_name = ""
    apk_name = ""
    source_path = ""
    deploy_path = ""
    for src in (overlay_text, text):
        if not src:
            continue
        case_match = re.search(r'case\s+"\$ACTIVE_PROJECT"\s+in(.*?)\nesac', src, re.S)
        if case_match:
            case_block = case_match.group(1)
            branch_match = re.search(r'^[ \t]*"' + re.escape(active_project) + r'"\)(.*?);;', case_block, re.M | re.S)
            if branch_match:
                branch_body = branch_match.group(1)
                m_mod = re.search(r'^[ \t]*MODULE_NAME\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_mod and not module_name:
                    module_name = m_mod.group(1)
                m_apk = re.search(r'^[ \t]*APK_FILE_NAME\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_apk and not apk_name:
                    apk_name = m_apk.group(1)
                m_src = re.search(r'^[ \t]*SOURCE_CODE_RELATIVE_PATH\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_src and not source_path:
                    source_path = m_src.group(1)
                m_dep = re.search(r'^[ \t]*APK_DEPLOY_PATH\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_dep and not deploy_path:
                    deploy_path = m_dep.group(1)
        if module_name and apk_name:
            break

    aosp_exists = False
    if aosp_root:
        try:
            aosp_exists = Path(aosp_root).is_dir()
        except Exception:
            aosp_exists = False

    if overlay_config.is_file():
        cfg_rel = "config/overlay/apk_overlays.config"
    else:
        try:
            cfg_rel = str(APK_CONFIG.relative_to(ROOT))
        except ValueError:
            cfg_rel = str(APK_CONFIG)

    profiles = parse_profiles()
    info = {
        "ok": True,
        "aosp_root_dir": aosp_root,
        "aosp_exists": aosp_exists,
        "active_project": active_project,
        "target_product": target_product,
        "target_variant": target_variant,
        "module_name": module_name,
        "apk_name": apk_name,
        "source_path": source_path,
        "deploy_path": deploy_path,
        "profiles": profiles,
        "config_file": cfg_rel,
        "aosp_top_rel_path": aosp_top_rel,
    }
    src_dir = _project_source_dir(info)
    info["source_dir"] = str(src_dir) if src_dir else ""
    info["source_dir_exists"] = bool(src_dir is not None and src_dir.is_dir())
    info["apk_config_in_source"] = bool(src_dir is not None and (src_dir / "apk.config").is_file())
    return info


@app.get("/api/aosp/config")
def api_aosp_config_get():
    return jsonify(_parse_aosp_info())


@app.post("/api/aosp/config")
def api_aosp_config_post():
    data = request.get_json(silent=True) or {}
    aosp_root_dir = data.get("aosp_root_dir")
    active_project = data.get("active_project")
    target_product = data.get("target_product")
    target_variant = data.get("target_variant")

    overlay_dir = ROOT / "config" / "overlay"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay_config = overlay_dir / "apk_overlays.config"
    if not overlay_config.is_file():
        example = overlay_dir / "apk_overlays.config.example"
        if example.is_file():
            shutil.copy2(example, overlay_config)
        else:
            overlay_config.write_text("#!/bin/bash\n# Personal AOSP & Lunch Overrides\n", encoding="utf-8")

    try:
        otext = overlay_config.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        otext = "#!/bin/bash\n"

    if aosp_root_dir is not None:
        clean_root = str(aosp_root_dir).strip().replace("\\", "/")
        otext = _upsert_bash_var(otext, "AOSP_ROOT_DIR", clean_root)

    if active_project:
        name = str(active_project).strip()
        otext = _upsert_bash_var(otext, "ACTIVE_PROJECT", name)

    if target_product is not None:
        tp = str(target_product).strip()
        otext = _upsert_bash_var(otext, "CONFIG_TARGET_PRODUCT", tp)

    if target_variant is not None:
        tv = str(target_variant).strip()
        otext = _upsert_bash_var(otext, "CONFIG_TARGET_BUILD_VARIANT", tv)

    overlay_config.write_text(otext, encoding="utf-8")

    # Also keep ACTIVE_PROJECT in apk.config synced as baseline fallback
    if APK_CONFIG.is_file():
        try:
            text = APK_CONFIG.read_text(encoding="utf-8", errors="ignore")
            if active_project:
                name = str(active_project).strip()
                if re.search(r'ACTIVE_PROJECT\s*=', text):
                    text = re.sub(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)["\']?.*?["\']?$', r'\g<1>"%s"' % name, text, count=1)
                    APK_CONFIG.write_text(text, encoding="utf-8")
        except OSError:
            pass

    # Seed <source_dir>/apk.config for the selected project so that 'tel b' run
    # from the project source directory (the Web UI AOSP Center does this
    # automatically) picks up the right profile instead of falling back to the
    # toolkit template config.
    project_cfg = None
    if active_project:
        project_cfg = ensure_project_apk_config(str(active_project).strip())

    info = _parse_aosp_info()
    info["project_apk_config"] = project_cfg
    return jsonify(info)


# ------------------------------------------------------------------------------
# Crypto & Overlay API
# ------------------------------------------------------------------------------
@app.post("/api/overlay/upload")
def api_overlay_upload():
    """Upload a private overlay configuration file (apk_overlays.config or const_my_cli.config)."""
    overlay_dir = ROOT / "config" / "overlay"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    target_name = None
    content_str = None

    if "file" in request.files:
        f = request.files["file"]
        filename = f.filename or ""
        target_name = request.form.get("target") or filename
        raw_bytes = f.read()
        try:
            content_str = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content_str = raw_bytes.decode("latin-1")
    else:
        data = request.get_json(silent=True) or {}
        target_name = data.get("target") or data.get("filename")
        content_str = data.get("content")

    if not target_name:
        abort(400, description="Missing file or target overlay name.")

    # Sanitize target name
    target_name = Path(str(target_name).strip()).name
    allowed_targets = ("apk_overlays.config", "const_my_cli.config")
    if target_name not in allowed_targets:
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.config", target_name):
            abort(400, description="Invalid overlay file name '%s'. Allowed: %s" % (target_name, ", ".join(allowed_targets)))

    if content_str is None:
        abort(400, description="Empty file content.")

    # Validate bash syntax
    err = validate_content("bash", content_str)
    if err:
        abort(400, description="File contains invalid bash syntax: %s" % err)

    dest_path = overlay_dir / target_name
    backup = None
    if dest_path.is_file():
        try:
            bak = dest_path.with_suffix(".config.bak")
            shutil.copy2(dest_path, bak)
            backup = str(bak.relative_to(ROOT)).replace("\\", "/")
        except OSError:
            pass

    try:
        with open(dest_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content_str)
    except OSError as exc:
        abort(500, description="Failed to write '%s': %s" % (target_name, exc))

    # If apk_overlays.config was uploaded, also sync ACTIVE_PROJECT in apk.config if present
    if target_name == "apk_overlays.config" and APK_CONFIG.is_file():
        try:
            m = re.search(r'^\s*ACTIVE_PROJECT\s*=\s*["\']?(.*?)["\']?\s*$', content_str, re.M)
            if m:
                proj = m.group(1).strip()
                sub = re.match(r'^\$\{[A-Za-z0-9_]+:-(.*?)\}$', proj)
                if sub:
                    proj = sub.group(1).strip()
                if proj:
                    apk_text = APK_CONFIG.read_text(encoding="utf-8", errors="ignore")
                    if re.search(r'ACTIVE_PROJECT\s*=', apk_text):
                        apk_text = re.sub(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)["\']?.*?["\']?$', r'\g<1>"%s"' % proj, apk_text, count=1)
                        APK_CONFIG.write_text(apk_text, encoding="utf-8")
        except OSError:
            pass

    return jsonify({
        "ok": True,
        "filename": target_name,
        "path": f"config/overlay/{target_name}",
        "bytes": len(content_str.encode("utf-8")),
        "backup": backup,
        "aosp_info": _parse_aosp_info() if target_name == "apk_overlays.config" else None,
    })


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
        "label": "Dumpsys diagnostics pipelines (telua dump <target>)",
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

    if key == "car":
        return _parse_cli_list_pipelines(lines, desc["list_var"], desc["var_prefix"])
    if key == "dump":
        has_group = any(re.match(r'^\s*DUMP_GROUP_LIST\s*=', l) for l in lines)
        has_cmd = any(re.match(r'^\s*DUMP_CMD_', l) for l in lines)
        if has_group or has_cmd:
            return parse_array_pipelines(lines, "DUMP")
        return _parse_cli_list_pipelines(lines, "DUMP_CLI_LIST", "ADB_SHELL_DUMP_")
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

    if key == "car":
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
            "dump": "DUMP_GROUP_LIST",
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
            "dump": "DUMP_GROUP_LIST",
        }[key]
        abort(404, description="Pipeline '%s' not found in %s." % (name, group_var))
    script = BUILD_APK_SH
    if not script.is_file():
        abort(404, description="build_apk.sh not found in %s" % ROOT)
    subcommand = {"my": "my", "multi": "run", "docker": "system", "system": "system", "car": "car", "dump": "dump"}[key]

    def generate():
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = None
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
            yield "\n[ERROR] Failed to stream pipeline: %s\n" % exc
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
# REST API — Android Logcat Streaming & Filtering
# ------------------------------------------------------------------------------
_ACTIVE_LOGCAT_PROCS = set()
_ACTIVE_LOGCAT_LOCK = threading.Lock()


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


@app.get("/api/logcat/status")
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


@app.post("/api/logcat/stream")
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

    def generate():
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = None
        try:
            proc = subprocess.Popen(
                exec_args,
                shell=False,
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
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


@app.post("/api/logcat/stop")
def api_logcat_stop():
    """Stop active logcat streaming process."""
    with _ACTIVE_LOGCAT_LOCK:
        procs = list(_ACTIVE_LOGCAT_PROCS)
        _ACTIVE_LOGCAT_PROCS.clear()
    for p in procs:
        _kill_term_proc(p)
    return jsonify({"ok": True, "stopped": len(procs)})


@app.post("/api/logcat/clear")
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


@app.get("/api/logcat/filters")
def api_logcat_filters_get():
    """Retrieve saved Logcat filter rule array from config/logcat_filters.json."""
    if LOGCAT_FILTERS_FILE.is_file():
        try:
            with open(LOGCAT_FILTERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return jsonify({"ok": True, "filters": data, "path": "config/logcat_filters.json"})
        except Exception:
            pass
    return jsonify({"ok": True, "filters": DEFAULT_LOGCAT_FILTERS, "path": "config/logcat_filters.json", "default": True})


@app.post("/api/logcat/filters")
def api_logcat_filters_post():
    """Save Logcat filter rule array to config/logcat_filters.json."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"ok": False, "error": "Invalid JSON body"}), 400
    filters = data if isinstance(data, list) else data.get("filters")
    if not isinstance(filters, list):
        return jsonify({"ok": False, "error": "'filters' must be a JSON array"}), 400

    LOGCAT_FILTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOGCAT_FILTERS_FILE, "w", encoding="utf-8") as f:
            json.dump(filters, f, indent=2, ensure_ascii=False)
        return jsonify({"ok": True, "count": len(filters), "path": "config/logcat_filters.json"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ------------------------------------------------------------------------------
# REST API — Sphinx Docs & RST <-> HTML Conversion (Quill.js integration)
# ------------------------------------------------------------------------------
@app.get("/api/docs/files")
def api_docs_files():
    """List all discoverable .rst documentation files."""
    custom_dir = request.args.get("dir", "").strip()
    files, effective_dir = scan_docs_files(ROOT, custom_dir=custom_dir or None)
    return jsonify({"ok": True, "files": files, "dir": effective_dir})


@app.get("/api/docs/file")
def api_docs_file_read():
    """Read a specific .rst file, returning both raw RST and converted HTML."""
    name = request.args.get("name", "").strip()
    custom_dir = request.args.get("dir", "").strip()
    if not name or ".." in name or not name.endswith(".rst"):
        abort(400, description="Invalid .rst file name.")
    target, full_name = resolve_rst_target(name, ROOT, custom_dir=custom_dir or None)
    if not target.is_file():
        abort(404, description=f"File '{name}' not found.")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        stat = target.stat()
        mtime = int(stat.st_mtime)
    except OSError as exc:
        abort(500, description=f"Failed to read file: {exc}")

    return jsonify({
        "ok": True,
        "name": name,
        "full_path": full_name,
        "rst": content,
        "html": rst_to_html(content),
        "mtime": mtime,
        "readonly": not os.access(str(target), os.W_OK),
    })


@app.post("/api/docs/file")
def api_docs_file_write():
    """Write/save a .rst file from either raw RST or Quill.js HTML."""
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    custom_dir = payload.get("dir", "").strip()
    content = payload.get("content", "")
    fmt = payload.get("format", "rst").lower()

    if not name or ".." in name or not name.endswith(".rst"):
        abort(400, description="Invalid .rst file name.")
    target, full_name = resolve_rst_target(name, ROOT, custom_dir=custom_dir or None)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        abort(500, description=f"Failed to create directory: {exc}")

    # If incoming format is HTML, convert to RST first
    if fmt == "html":
        rst_content = html_to_rst(content, file_name=name)
    else:
        rst_content = content

    # Create backup .bak if target exists
    if target.is_file():
        try:
            bak = target.with_suffix(".rst.bak")
            shutil.copyfile(str(target), str(bak))
        except OSError:
            pass

    try:
        target.write_text(rst_content, encoding="utf-8")
        stat = target.stat()
    except OSError as exc:
        abort(500, description=f"Failed to write file: {exc}")

    return jsonify({
        "ok": True,
        "name": name,
        "full_path": full_name,
        "rst": rst_content,
        "html": rst_to_html(rst_content),
        "mtime": int(stat.st_mtime),
    })


@app.post("/api/docs/convert")
def api_docs_convert():
    """Convert on-the-fly between RST and HTML."""
    payload = request.get_json(silent=True) or {}
    content = payload.get("content", "")
    direction = payload.get("direction", "rst2html").lower()

    if direction in ("rst2html", "rst_to_html"):
        return jsonify({"ok": True, "html": rst_to_html(content)})
    elif direction in ("html2rst", "html_to_rst"):
        file_name = payload.get("name", "")
        return jsonify({"ok": True, "rst": html_to_rst(content, file_name=file_name)})
    abort(400, description="Unknown conversion direction. Use 'rst2html' or 'html2rst'.")


_PLANTUML_CACHE = {}


@app.route("/api/docs/plantuml/svg", methods=["GET", "POST"])
def api_docs_plantuml_svg():
    """Render PlantUML code to SVG using local plantuml, jar, or server proxy with cache."""
    import urllib.request

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        code = payload.get("code", "")
    else:
        code = request.args.get("code", "")

    code = (code or "").strip()
    if not code:
        return Response('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="30"></svg>', mimetype="image/svg+xml")

    if code in _PLANTUML_CACHE:
        return Response(_PLANTUML_CACHE[code], mimetype="image/svg+xml")

    # 1. Local plantuml or jar if available
    plantuml_bin = shutil.which("plantuml")
    if plantuml_bin:
        try:
            p = subprocess.run([plantuml_bin, "-tsvg", "-pipe"], input=code.encode("utf-8"), capture_output=True, timeout=10)
            if p.returncode == 0 and p.stdout and b"<svg" in p.stdout:
                svg_text = p.stdout.decode("utf-8", errors="replace")
                _PLANTUML_CACHE[code] = svg_text
                return Response(svg_text, mimetype="image/svg+xml")
        except Exception:
            pass

    # 2. Online plantuml server via backend proxy (avoids client-side hotlink/referer blocking)
    try:
        url = get_plantuml_url(code)
        if url:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/svg+xml,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                svg_data = resp.read().decode("utf-8", errors="replace")
                if "<svg" in svg_data and "HUFFMAN" not in svg_data and "bad URL" not in svg_data:
                    _PLANTUML_CACHE[code] = svg_data
                    return Response(svg_data, mimetype="image/svg+xml")
    except Exception:
        pass

    # 3. Fallback SVG: generate clean vector diagram
    lines = [l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith("@")]
    h = max(120, 60 + len(lines) * 24)
    escaped_lines = "\n".join(
        f'<text x="24" y="{45 + idx * 24}" fill="#e2e8f0" font-family="monospace" font-size="12">{l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</text>'
        for idx, l in enumerate(lines[:20])
    )
    fallback_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="{h}">'
        f'<rect width="100%" height="100%" fill="#1e1e2e" stroke="#a855f7" stroke-width="2" rx="8"/>'
        f'<rect x="0" y="0" width="100%" height="28" fill="#2d1b4e" rx="8"/>'
        f'<text x="14" y="19" fill="#c084fc" font-family="sans-serif" font-size="12" font-weight="bold">📐 PlantUML Architecture Diagram</text>'
        f'{escaped_lines}'
        f'</svg>'
    )
    return Response(fallback_svg, mimetype="image/svg+xml")


@app.route("/api/docs/plantuml/url", methods=["GET", "POST"])
def api_docs_plantuml_url():
    """Generate PlantUML SVG URL from code."""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        code = payload.get("code", "")
    else:
        code = request.args.get("code", "")
    if not code:
        return jsonify({"ok": False, "error": "No PlantUML code provided"}), 400
    url = get_plantuml_url(code)
    return jsonify({"ok": True, "url": url})


_DOCS_SERVER_PROC = None
_DOCS_SERVER_DIR = None
_DOCS_SERVER_PORT = None


def _build_sphinx_docs_py(target_dir: Path):
    """Compile Sphinx documentation into target_dir/_build/html with staging, merge, and fallbacks."""
    import shutil
    out_html = target_dir / "_build" / "html"
    staging_dir = target_dir / "_build" / ".staging"
    merge_script = ROOT / "sphinx" / "scripts" / "merge_docs.py"

    if staging_dir.is_dir():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for item in target_dir.iterdir():
        if item.name not in ("_build", ".git"):
            dest = staging_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # Fallback conf.py if missing in staging
    if not (staging_dir / "conf.py").is_file():
        for candidate in [
            ROOT / "sphinx" / "templates" / "basic" / "conf.py",
            ROOT / "sphinx" / "templates" / "architecture" / "conf.py",
            ROOT / "sphinx" / "conf.py",
        ]:
            if candidate.is_file():
                shutil.copy2(candidate, staging_dir / "conf.py")
                break

    # Fallback _static if missing in staging
    if not (staging_dir / "_static").is_dir():
        for candidate in [
            ROOT / "sphinx" / "templates" / "basic" / "_static",
            ROOT / "sphinx" / "templates" / "architecture" / "_static",
        ]:
            if candidate.is_dir():
                shutil.copytree(candidate, staging_dir / "_static", dirs_exist_ok=True)
                break

    # Fallback asset directory if missing in staging
    if not (staging_dir / "asset").is_dir():
        for candidate in [
            ROOT / "sphinx" / "templates" / "basic" / "asset",
            ROOT / "sphinx" / "templates" / "architecture" / "asset",
        ]:
            if candidate.is_dir():
                shutil.copytree(candidate, staging_dir / "asset", dirs_exist_ok=True)
                break

    # Ensure PlantUML support in staging (auto-upgrades legacy conf.py; source untouched)
    inject_script = ROOT / "sphinx" / "scripts" / "inject_plantuml.py"
    if inject_script.is_file():
        subprocess.run([sys.executable, str(inject_script), str(staging_dir)], capture_output=True, timeout=30)

    if (staging_dir / "metadata.json").is_file() and merge_script.is_file():
        subprocess.run([sys.executable, str(merge_script), str(staging_dir)], capture_output=True, timeout=30)

    cmd = [sys.executable, "-m", "sphinx", "-E", "-a", "-b", "html", str(staging_dir), str(out_html)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    return (proc.returncode == 0, proc.returncode, proc.stdout, proc.stderr, target_dir, out_html)


@app.post("/api/docs/build")
def api_docs_build():
    """Trigger Sphinx build for target docs directory."""
    payload = request.get_json(silent=True) or {}
    custom_dir = payload.get("dir", "").strip()
    current_file = payload.get("current_file", "").strip()

    target_dir = detect_docs_project_dir(current_file=current_file, custom_dir=custom_dir, root=ROOT)

    if not target_dir.is_dir():
        return jsonify({"ok": False, "error": f"Documentation directory '{target_dir}' does not exist"}), 404

    # On Linux/macOS with build_apk.sh, delegate to bash build_apk.sh docs build <target_dir>
    if (ROOT / "build_apk.sh").is_file() and not sys.platform.startswith("win"):
        cmd = ["bash", "build_apk.sh", "docs", "build", str(target_dir)]
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            return jsonify({
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "target_dir": str(target_dir),
                "html_dir": str(target_dir / "_build" / "html"),
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    # Cross-platform / Windows fallback
    try:
        ok, ret, stdout, stderr, tdir, ohtml = _build_sphinx_docs_py(target_dir)
        return jsonify({
            "ok": ok,
            "exit_code": ret,
            "stdout": stdout,
            "stderr": stderr,
            "target_dir": str(tdir),
            "html_dir": str(ohtml),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/docs/clean")
def api_docs_clean():
    """Remove _build directory and cached doctrees for target docs project."""
    import shutil
    payload = request.get_json(silent=True) or {}
    custom_dir = payload.get("dir", "").strip()
    current_file = payload.get("current_file", "").strip()

    target_dir = detect_docs_project_dir(current_file=current_file, custom_dir=custom_dir, root=ROOT)
    if not target_dir.is_dir():
        return jsonify({"ok": False, "error": f"Documentation directory '{target_dir}' does not exist"}), 404

    build_dir = target_dir / "_build"
    cleaned = False
    if build_dir.is_dir():
        try:
            shutil.rmtree(build_dir, ignore_errors=True)
            cleaned = True
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Failed to clean _build: {exc}"}), 500

    return jsonify({
        "ok": True,
        "target_dir": str(target_dir),
        "cleaned_dir": str(build_dir),
        "was_present": cleaned,
    })


def _kill_docs_server(target_dir: Optional[Path] = None, port: int = 8789):
    """Ensure any running docs preview server is terminated before restart."""
    global _DOCS_SERVER_PROC
    if _DOCS_SERVER_PROC is not None:
        try:
            if _DOCS_SERVER_PROC.poll() is None:
                _DOCS_SERVER_PROC.terminate()
                _DOCS_SERVER_PROC.wait(timeout=2)
        except Exception:
            pass
        _DOCS_SERVER_PROC = None

    if target_dir is not None:
        pid_file = target_dir / ".telua_docs.pid"
        if pid_file.is_file():
            try:
                raw_pid = pid_file.read_text(encoding="utf-8").strip()
                pid = int(raw_pid)
                if pid > 0 and pid != os.getpid():
                    if sys.platform.startswith("win"):
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    else:
                        os.kill(pid, 9)
            except Exception:
                pass
            try:
                pid_file.unlink(missing_ok=True)
            except Exception:
                pass

    if sys.platform.startswith("win"):
        try:
            out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, errors="ignore")
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = int(parts[-1])
                    if pid > 0 and pid != os.getpid():
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        except Exception:
            pass
    else:
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
        except Exception:
            pass


@app.post("/api/docs/start")
def api_docs_start():
    """Launch Sphinx HTTP preview server (telua docs start) and open in browser."""
    import time
    import shutil
    global _DOCS_SERVER_PROC, _DOCS_SERVER_DIR, _DOCS_SERVER_PORT
    payload = request.get_json(silent=True) or {}
    custom_dir = payload.get("dir", "").strip()
    current_file = payload.get("current_file", "").strip()
    port = int(payload.get("port", 8789))
    clean_requested = bool(payload.get("clean", False))

    target_dir = detect_docs_project_dir(current_file=current_file, custom_dir=custom_dir, root=ROOT)
    if not target_dir.is_dir():
        return jsonify({"ok": False, "error": f"Documentation directory '{target_dir}' does not exist"}), 404
    html_dir = target_dir / "_build" / "html"

    # If clean requested, wipe _build completely
    if clean_requested:
        build_dir = target_dir / "_build"
        if build_dir.is_dir():
            shutil.rmtree(build_dir, ignore_errors=True)

    # Always restart: terminate running server process or port occupier
    _kill_docs_server(target_dir=target_dir, port=port)

    # Always re-compile docs to ensure http://localhost:8789 serves 100% fresh content
    if (ROOT / "build_apk.sh").is_file() and not sys.platform.startswith("win"):
        try:
            subprocess.run(["bash", "build_apk.sh", "docs", "build", str(target_dir)], cwd=str(ROOT), capture_output=True, timeout=60)
        except Exception:
            pass
    else:
        try:
            _build_sphinx_docs_py(target_dir)
        except Exception:
            pass

    if not html_dir.is_dir():
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<h1>Sphinx Docs Preview</h1><p>Ready to build.</p>", encoding="utf-8")

    url = f"http://localhost:{port}"

    try:
        server_script = (
            "import http.server, sys, os, mimetypes\n"
            "mimetypes.add_type('image/svg+xml', '.svg')\n"
            "port = int(sys.argv[1])\n"
            "directory = os.path.abspath(sys.argv[2])\n"
            "class NoCacheHandler(http.server.SimpleHTTPRequestHandler):\n"
            "    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.svg': 'image/svg+xml'}\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        super().__init__(*args, directory=directory, **kwargs)\n"
            "    def end_headers(self):\n"
            "        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0')\n"
            "        self.send_header('Pragma', 'no-cache')\n"
            "        self.send_header('Expires', '0')\n"
            "        super().end_headers()\n"
            "    def send_head(self):\n"
            "        if 'If-Modified-Since' in self.headers:\n"
            "            del self.headers['If-Modified-Since']\n"
            "        if 'If-None-Match' in self.headers:\n"
            "            del self.headers['If-None-Match']\n"
            "        return super().send_head()\n"
            "server = http.server.ThreadingHTTPServer(('', port), NoCacheHandler)\n"
            "server.serve_forever()\n"
        )
        _DOCS_SERVER_PROC = subprocess.Popen(
            [sys.executable, "-c", server_script, str(port), str(html_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _DOCS_SERVER_DIR = str(html_dir)
        _DOCS_SERVER_PORT = port
    except Exception as exc:
        abort(500, description=f"Failed to start docs server: {exc}")

    cache_bust_url = f"{url}/?_t={int(time.time())}"
    open_browser(cache_bust_url)

    return jsonify({
        "ok": True,
        "url": url,
        "cache_bust_url": cache_bust_url,
        "port": port,
        "pid": _DOCS_SERVER_PROC.pid if _DOCS_SERVER_PROC else None,
        "target_dir": str(target_dir),
        "html_dir": str(html_dir),
    })


# ------------------------------------------------------------------------------
# Static frontend & entry point
# ------------------------------------------------------------------------------
@app.after_request
def _disable_static_cache(response):
    """Prevent stale 304 caching of index.html / app.js / style.css during live edits."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html", max_age=0, conditional=False)


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
