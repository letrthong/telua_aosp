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
# Domain modules:
#   - web/telua_web_core.py      (file scanning, syntax validation & system stats)
#   - web/telua_web_terminal.py  (terminal process runner & live streaming)
#   - web/telua_web_logcat.py    (Android ADB logcat stream & filter rules)
#   - web/telua_web_pipelines.py (pipelines parsing, serialization & runner)
#   - web/telua_web_docs.py      (Sphinx Doc-as-Code & live preview server)
#   - web/telua_web_aosp.py      (AOSP & Lunch config, overlay crypto & sync)
# ==============================================================================

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
from typing import Optional

SCRIPT_FILE = Path(__file__).resolve()
WEB_DIR = SCRIPT_FILE.parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))
AI_DIR = WEB_DIR / "ai"
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

# Core toolkit helpers
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

# Domain blueprints & helpers
from telua_web_terminal import (  # noqa: E402
    terminal_bp,
    _build_terminal_bash_script,
    _kill_term_proc,
    _resolve_terminal_exec,
)
from telua_web_logcat import (  # noqa: E402
    logcat_bp,
    DEFAULT_LOGCAT_FILTERS,
    _resolve_adb_binary,
)
from telua_web_pipelines import (  # noqa: E402
    pipelines_bp,
    PIPELINE_SOURCES,
    parse_pipelines,
    rewrite_pipeline_config,
)
from telua_web_docs import (  # noqa: E402
    docs_bp,
    _DOCS_SERVER_PROC,
    scan_docs_files,
    resolve_rst_target,
    rst_to_html,
    html_to_rst,
    get_plantuml_url,
    detect_docs_project_dir,
)
from telua_web_aosp import (  # noqa: E402
    aosp_bp,
    ensure_project_apk_config,
    _parse_aosp_info,
    _upsert_bash_var,
    _project_source_dir,
)
from telua_web_bi import (  # noqa: E402
    bi_bp,
)
from telua_web_mirror import (  # noqa: E402
    mirror_bp,
)
from telua_web_power_controls import (  # noqa: E402
    power_bp,
)
try:
    from ai.telua_web_ai import (  # noqa: E402
        ai_bp,
    )
    from ai.telua_web_tasks import (  # noqa: E402
        tasks_bp,
    )
    from ai.telua_web_schedule import (  # noqa: E402
        schedule_bp,
        ensure_scheduler_started as _ensure_ai_scheduler_started,
    )
except ImportError:
    from telua_web_ai import (  # noqa: E402
        ai_bp,
    )
    from telua_web_tasks import (  # noqa: E402
        tasks_bp,
    )
    from telua_web_schedule import (  # noqa: E402
        schedule_bp,
        ensure_scheduler_started as _ensure_ai_scheduler_started,
    )

try:
    from flask import Flask, abort, jsonify, request, send_from_directory, send_file
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
LOGCAT_FILTERS_FILE = (
    (ROOT / "config" / "json" / "logcat_filters.json")
    if (ROOT / "config" / "json" / "logcat_filters.json").is_file()
    or not (ROOT / "config" / "logcat_filters.json").is_file()
    else (ROOT / "config" / "logcat_filters.json")
)

START_TIME = time.time()
FLASK_VERSION = ""
try:
    from importlib.metadata import version as _pkg_version
    FLASK_VERSION = _pkg_version("flask")
except Exception:  # pragma: no cover
    FLASK_VERSION = "unknown"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# Register domain Blueprints
app.register_blueprint(terminal_bp)
app.register_blueprint(logcat_bp)
app.register_blueprint(pipelines_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(aosp_bp)
app.register_blueprint(bi_bp)
app.register_blueprint(mirror_bp)
app.register_blueprint(power_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(schedule_bp)
_ensure_ai_scheduler_started()


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
    return parse_version_from_file(ROOT / "build_apk.sh")


def parse_active_project():
    overlay_config = ROOT / "config" / "overlay" / "apk_overlays.config"
    apk_config = (ROOT / "config" / "apk.config") if (ROOT / "config" / "apk.config").is_file() else (ROOT / "apk.config")
    if overlay_config.is_file():
        proj = parse_active_project_from_file(overlay_config)
        if proj:
            return proj
    return parse_active_project_from_file(apk_config)


def parse_profiles():
    apk_config = (ROOT / "config" / "apk.config") if (ROOT / "config" / "apk.config").is_file() else (ROOT / "apk.config")
    profs = parse_profiles_from_file(apk_config)
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
    remote_bat = ROOT / "scripts" / "windows" / "adb_remote_pc.bat"
    return jsonify({
        "ok": True,
        "version": parse_version(),
        "flask_version": FLASK_VERSION,
        "root": str(ROOT),
        "active_project": parse_active_project(),
        "profiles": parse_profiles(),
        "adb_devices": adb_devices(),
        "adb_remote_script": {
            "name": "adb_remote_pc.bat",
            "path": str(remote_bat),
            "exists": remote_bat.is_file(),
            "download_url": "/api/adb/remote-script",
        },
        "ram": ram_info(),
        "uptime_s": int(time.time() - START_TIME),
        "python": sys.version.split()[0],
    })


@app.get("/api/adb/remote-script")
def api_adb_remote_script():
    """Download adb_remote_pc.bat script for Windows SSH reverse ADB tunnel."""
    bat_path = ROOT / "scripts" / "windows" / "adb_remote_pc.bat"
    if not bat_path.is_file():
        abort(404, description="adb_remote_pc.bat not found at %s" % bat_path)
    try:
        return send_file(
            str(bat_path),
            as_attachment=True,
            download_name="adb_remote_pc.bat",
            mimetype="application/x-bat",
        )
    except TypeError:  # pragma: no cover (fallback for Flask < 2.0)
        return send_file(
            str(bat_path),
            as_attachment=True,
            attachment_filename="adb_remote_pc.bat",
            mimetype="application/x-bat",
        )


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
    apk_config = (ROOT / "config" / "apk.config") if (ROOT / "config" / "apk.config").is_file() else (ROOT / "apk.config")
    if not apk_config.is_file():
        abort(404, description="apk.config not found in %s" % ROOT)

    text = apk_config.read_text(encoding="utf-8", errors="ignore")
    new_text, count = re.subn(
        r'(?m)^(\s*ACTIVE_PROJECT\s*=\s*)"[^"]*"',
        lambda m: '%s"%s"' % (m.group(1), name),
        text, count=1)
    if count == 0:
        abort(400, description="ACTIVE_PROJECT line not found in apk.config.")

    backup = None
    try:
        backup_path = apk_config.with_suffix(".config.bak")
        shutil.copy2(apk_config, backup_path)
        backup = str(backup_path.relative_to(ROOT))
    except OSError:
        backup = None
    apk_config.write_text(new_text, encoding="utf-8")

    overlay_config = ROOT / "config" / "overlay" / "apk_overlays.config"
    if overlay_config.is_file():
        try:
            otext = overlay_config.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)"[^"]*"', otext):
                new_otext = re.sub(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)"[^"]*"', r'\g<1>"%s"' % name, otext, count=1)
                overlay_config.write_text(new_otext, encoding="utf-8")
        except OSError:
            pass

    project_cfg = ensure_project_apk_config(name)
    return jsonify({"ok": True, "active_project": name, "backup": backup,
                    "project_apk_config": project_cfg})


@app.get("/api/info")
def api_info():
    """Run 'build_apk.sh --info' (read-only diagnostics) and return its output."""
    build_sh = ROOT / "build_apk.sh"
    if not build_sh.is_file():
        abort(404, description="build_apk.sh not found in %s" % ROOT)
    try:
        proc = subprocess.run(
            ["bash", str(build_sh), "--info"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "[ERROR] 'build_apk.sh --info' timed out after 60s.", 124
    except Exception as exc:  # pragma: no cover
        output, code = "[ERROR] Failed to run build_apk.sh: %s" % exc, 1
    return jsonify({"ok": code == 0, "exit_code": code, "output": output})


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

    if not STATIC_DIR.is_dir():
        sys.stderr.write("[ERROR] Static assets directory not found: %s\n" % STATIC_DIR)
        sys.exit(1)

    ensure_overlay_configs()

    if args.open_browser:
        url = "http://127.0.0.1:%d" % args.port
        threading.Timer(1.2, open_browser, args=(url,)).start()

    print_banner(args.host, args.port)
    try:
        from ai.telua_mcp_skill import start_mcp_background_scheduler
        start_mcp_background_scheduler()
    except Exception:
        pass
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
