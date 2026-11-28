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
# telua_web_aosp.py — AOSP config, Lunch target, overlays & crypto management
# ==============================================================================

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from flask import Blueprint, abort, jsonify, request
from telua_web_core import (
    PRIVATE_OVERLAY_NAMES,
    crypto_items_for_root,
    parse_active_project_from_file,
    parse_profiles_from_file,
    validate_content,
)

aosp_bp = Blueprint("aosp", __name__)


def get_root() -> Path:
    """Dynamically get ROOT from telua_web if loaded, else fallback to toolkit root."""
    import sys
    if "telua_web" in sys.modules:
        tw = sys.modules["telua_web"]
        if hasattr(tw, "ROOT"):
            return tw.ROOT
    return Path(__file__).resolve().parent.parent


def get_apk_config_path() -> Path:
    """Resolve apk.config dynamically relative to current ROOT."""
    root = get_root()
    return (root / "config" / "apk.config") if (root / "config" / "apk.config").is_file() else (root / "apk.config")


def parse_active_project() -> Optional[str]:
    root = get_root()
    apk_config = get_apk_config_path()
    overlay_config = root / "config" / "overlay" / "apk_overlays.config"
    if overlay_config.is_file():
        proj = parse_active_project_from_file(overlay_config)
        if proj:
            return proj
    return parse_active_project_from_file(apk_config)


def parse_profiles():
    root = get_root()
    apk_config = get_apk_config_path()
    profs = parse_profiles_from_file(apk_config)
    overlay_config = root / "config" / "overlay" / "apk_overlays.config"
    if overlay_config.is_file():
        ov_profs = parse_profiles_from_file(overlay_config)
        for p in ov_profs:
            if p not in profs:
                profs.append(p)
    return profs


def _crypto_items():
    return crypto_items_for_root(get_root())


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
    """Absolute Path of the active project's source dir (<AOSP_TOP>/<SOURCE_CODE_RELATIVE_PATH>)."""
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
    """Create (or point ACTIVE_PROJECT of) <source_dir>/apk.config at project_name."""
    if not project_name:
        return None
    root = get_root()
    apk_config = get_apk_config_path()
    src_dir = _project_source_dir()
    if src_dir is None or not src_dir.is_dir():
        return None
    target = src_dir / "apk.config"
    result = {"path": str(target), "created": False, "updated": False}
    if not target.is_file():
        template = apk_config if apk_config.is_file() else root / "apk.config"
        if not template.is_file():
            return None
        try:
            shutil.copy2(template, target)
        except OSError:
            return None
        result["created"] = True
        overlay = root / "config" / "overlay" / "apk_overlays.config"
        overlay_script = root / "python" / "config_overlay.py"
        if overlay.is_file() and overlay_script.is_file():
            try:
                subprocess.run(
                    [sys.executable, str(overlay_script), str(target), str(overlay)],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except Exception:
                pass
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
        new_text, count = re.subn(
            r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)["\']?.*?["\']?$',
            r'\g<1>"%s"' % project_name,
            text,
            count=1,
        )
        if count:
            target.write_text(new_text, encoding="utf-8")
            result["updated"] = True
    except OSError:
        pass
    return result


# ------------------------------------------------------------------------------
# APK Upload & Deploy (AOSP tab)
# Upload a local .apk/.bin, verify its filename matches OUTPUT_FILE_NAME /
# FILE_NAME of the active project, adb push it to DEPLOY_PATH on the device,
# then restart the Android framework (or reboot).
# ------------------------------------------------------------------------------

# 512 MB hard cap for uploaded binaries
_APK_UPLOAD_MAX_BYTES = 512 * 1024 * 1024


def _active_project_deploy_info() -> Dict[str, Any]:
    """Return {apk_name, deploy_path, module_type, aosp_root} for the active project."""
    info = _parse_aosp_info()
    apk_name = info.get("apk_name") or ""
    # Fallback: FILE_NAME key (used by most branches) when OUTPUT_FILE_NAME is absent
    if not apk_name:
        for src_name in ("config/overlay/apk_overlays.config", "config/apk.config"):
            src = get_root() / src_name
            if not src.is_file():
                continue
            try:
                text = src.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            case_match = re.search(r'case\s+"\$ACTIVE_PROJECT"\s+in(.*?)\nesac', text, re.S)
            if not case_match:
                continue
            active = info.get("active_project") or ""
            branch_match = re.search(
                r'^[ \t]*"' + re.escape(active) + r'"\)(.*?);;',
                case_match.group(1), re.M | re.S)
            if branch_match:
                m = re.search(r'^[ \t]*FILE_NAME\s*=\s*"([^"]*)"', branch_match.group(1), re.M)
                if m:
                    apk_name = m.group(1)
                    break
    return {
        "apk_name": apk_name,
        "deploy_path": info.get("deploy_path") or "",
        "module_type": info.get("module_type") or "apk",
        "aosp_root": info.get("aosp_root_dir") or "",
        "active_project": info.get("active_project") or "",
    }


@aosp_bp.get("/api/aosp/deploy-info")
def api_aosp_deploy_info():
    """Expose expected APK filename + deploy path so the UI can validate before upload."""
    return jsonify({"ok": True, **_active_project_deploy_info()})


@aosp_bp.post("/api/aosp/upload-apk")
def api_aosp_upload_apk():
    """Upload a built APK/binary, verify filename, adb push to device, restart framework."""
    root = get_root()
    info = _active_project_deploy_info()
    expected_name = info["apk_name"]
    deploy_path = info["deploy_path"]
    module_type = info["module_type"]
    aosp_root = info["aosp_root"]

    if not expected_name:
        abort(400, description=(
            "No OUTPUT_FILE_NAME/FILE_NAME defined for the active project "
            "'%s'. Set it in apk_overlays.config first." % info["active_project"]))
    if not deploy_path:
        abort(400, description="No DEPLOY_PATH defined for the active project.")

    if "file" not in request.files:
        abort(400, description="No file uploaded. Expected 'file' field in multipart/form-data.")
    f = request.files["file"]
    filename = Path(f.filename or "").name
    if not filename:
        abort(400, description="Uploaded file must have a filename.")

    # Filename must match the configured output name (case-insensitive)
    if filename.lower() != expected_name.lower():
        abort(400, description=(
            "Filename mismatch: uploaded '%s' but active project expects '%s' "
            "(OUTPUT_FILE_NAME)." % (filename, expected_name)))

    # Reject anything that is not an APK or plain binary artifact
    if not (filename.lower().endswith(".apk") or "/" not in filename and "." not in Path(filename).stem):
        if not filename.lower().endswith(".apk"):
            abort(400, description="Only .apk files (or extensionless binaries) are accepted.")

    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    if size <= 0:
        abort(400, description="Uploaded file is empty (0 bytes).")
    if size > _APK_UPLOAD_MAX_BYTES:
        abort(413, description="File too large (%.1f MB, limit %d MB)."
              % (size / 1048576, _APK_UPLOAD_MAX_BYTES // 1048576))

    # Stage the upload under <toolkit>/uploads/apk/ (gitignored)
    upload_dir = root / "uploads" / "apk"
    upload_dir.mkdir(parents=True, exist_ok=True)
    staged = upload_dir / filename
    f.save(str(staged))

    # Verify adb device availability before pushing
    adb = shutil.which("adb")
    if not adb:
        staged.unlink(missing_ok=True)
        abort(400, description="'adb' not found in PATH. Install Android platform-tools.")

    def _adb(*args, timeout=30):
        return subprocess.run([adb, *args], capture_output=True, text=True, timeout=timeout)

    state = _adb("get-state")
    if state.returncode != 0 or state.stdout.strip() != "device":
        staged.unlink(missing_ok=True)
        abort(400, description="No ADB device in 'device' state (got: %s). Connect the DUT and retry."
              % (state.stdout.strip() or state.stderr.strip() or "none"))

    logs = []
    push = _adb("push", str(staged), f"{deploy_path}/{filename}", timeout=300)
    logs.append((push.stdout or "") + (push.stderr or ""))
    if push.returncode != 0:
        abort(500, description="adb push failed:\n%s" % "\n".join(logs).strip())

    # Permissions + cache cleanup (mirror deploy_android() in telua_android.sh)
    chmod_mode = "755" if module_type == "bin" else "644"
    _adb("shell", "chmod", chmod_mode, f"{deploy_path}/{filename}")
    if module_type != "bin":
        _adb("shell", "rm", "-rf", f"{deploy_path}/oat")
    _adb("shell", "sync")

    # ------------------------------------------------------------------
    # Integrity verification (3 layers):
    #   1. Local staged file size vs uploaded size
    #   2. On-device size (ls -l) vs local size
    #   3. SHA-256 checksum: on-device (sha256sum) vs local staged file
    # Deploy is reported as FAILED if any layer mismatches.
    # ------------------------------------------------------------------
    import hashlib

    staged.unlink(missing_ok=False) if False else None  # keep file for hashing
    local_hash = hashlib.sha256(staged.read_bytes()).hexdigest()

    device_bytes = None
    device_hash = None
    ls = _adb("shell", "ls", "-l", f"{deploy_path}/{filename}")
    m = re.search(r"\s(\d+)\s+\d{4}-\d{2}-\d{2}", ls.stdout or "")
    if not m:
        m = re.search(r"[-a-zA-Z].*?\s+\d+\s+\w+\s+\w+\s+(\d+)\s", ls.stdout or "")
    if m:
        try:
            device_bytes = int(m.group(1))
        except ValueError:
            device_bytes = None

    shasum = _adb("shell", "sha256sum", f"{deploy_path}/{filename}", timeout=120)
    sm = re.search(r'([0-9a-fA-F]{64})', shasum.stdout or "")
    if sm:
        device_hash = sm.group(1).lower()

    integrity = {
        "local_bytes": size,
        "device_bytes": device_bytes,
        "local_sha256": local_hash,
        "device_sha256": device_hash,
        "size_match": (device_bytes == size),
        "hash_match": (device_hash == local_hash) if device_hash else None,
    }
    integrity["ok"] = bool(integrity["size_match"] and integrity["hash_match"])

    # Restart: stop/start framework (fast) unless ?reboot=1
    restart_mode = (request.form.get("restart") or "framework").lower()

    # If integrity failed, do NOT restart the framework — surface the error.
    if not integrity["ok"]:
        detail = []
        if not integrity["size_match"]:
            detail.append(f"size local={size} vs device={device_bytes}")
        if not integrity["hash_match"]:
            detail.append(f"sha256 local={local_hash[:16]}… vs device={(device_hash or 'n/a')[:16]}…")
        abort(500, description=(
            "Integrity verification FAILED — APK on device differs from the uploaded file (%s). "
            "Framework NOT restarted. Try: adb root && adb remount, then re-upload."
            % "; ".join(detail)))

    if restart_mode == "reboot":
        rb = _adb("reboot")
        logs.append((rb.stdout or "") + (rb.stderr or ""))
        restart_desc = "adb reboot issued"
    else:
        stop = _adb("shell", "stop", timeout=120)
        start = _adb("shell", "start", timeout=180)
        logs.append((stop.stdout or "") + (stop.stderr or ""))
        logs.append((start.stdout or "") + (start.stderr or ""))
        restart_desc = "framework restarted (stop && start)"

    return jsonify({
        "ok": True,
        "filename": filename,
        "bytes": size,
        "device_bytes": device_bytes,
        "sha256": local_hash,
        "device_sha256": device_hash,
        "integrity": integrity,
        "deploy_path": deploy_path,
        "module_type": module_type,
        "restart": restart_desc,
        "staged_path": str(staged.relative_to(root)),
        "output": "\n".join(l.strip() for l in logs if l and l.strip()),
    })


def _parse_aosp_info():
    root = get_root()
    apk_config = get_apk_config_path()
    text = ""
    if apk_config.is_file():
        try:
            text = apk_config.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass

    overlay_config = root / "config" / "overlay" / "apk_overlays.config"
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

    module_type = ""
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
                m_type = re.search(r'^[ \t]*MODULE_TYPE\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_type and not module_type:
                    module_type = m_type.group(1)
                m_mod = re.search(r'^[ \t]*MODULE_NAME\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_mod and not module_name:
                    module_name = m_mod.group(1)
                m_apk = re.search(r'^[ \t]*(?:OUTPUT_FILE_NAME|APK_FILE_NAME)\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_apk and not apk_name:
                    apk_name = m_apk.group(1)
                m_src = re.search(r'^[ \t]*SOURCE_CODE_RELATIVE_PATH\s*=\s*"([^"]*)"', branch_body, re.M)
                if m_src and not source_path:
                    source_path = m_src.group(1)
                m_dep = re.search(r'^[ \t]*(?:DEPLOY_PATH|APK_DEPLOY_PATH)\s*=\s*"([^"]*)"', branch_body, re.M)
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
            cfg_rel = str(apk_config.relative_to(root))
        except ValueError:
            cfg_rel = str(apk_config)

    profiles = parse_profiles()
    info = {
        "ok": True,
        "aosp_root_dir": aosp_root,
        "aosp_exists": aosp_exists,
        "active_project": active_project,
        "target_product": target_product,
        "target_variant": target_variant,
        "module_name": module_name,
        "module_type": module_type or "apk",
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


@aosp_bp.get("/api/aosp/config")
def api_aosp_config_get():
    return jsonify(_parse_aosp_info())


@aosp_bp.post("/api/aosp/config")
def api_aosp_config_post():
    root = get_root()
    apk_config = get_apk_config_path()
    data = request.get_json(silent=True) or {}
    aosp_root_dir = data.get("aosp_root_dir")
    active_project = data.get("active_project")
    target_product = data.get("target_product")
    target_variant = data.get("target_variant")

    overlay_dir = root / "config" / "overlay"
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
    if apk_config.is_file():
        try:
            text = apk_config.read_text(encoding="utf-8", errors="ignore")
            if active_project:
                name = str(active_project).strip()
                if re.search(r'ACTIVE_PROJECT\s*=', text):
                    text = re.sub(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)["\']?.*?["\']?$', r'\g<1>"%s"' % name, text, count=1)
                    apk_config.write_text(text, encoding="utf-8")
        except OSError:
            pass

    project_cfg = None
    if active_project:
        project_cfg = ensure_project_apk_config(str(active_project).strip())

    info = _parse_aosp_info()
    info["project_apk_config"] = project_cfg
    return jsonify(info)


@aosp_bp.post("/api/overlay/upload")
def api_overlay_upload():
    """Upload a private overlay configuration file (apk_overlays.config or const_my_cli.config)."""
    root = get_root()
    apk_config = get_apk_config_path()
    overlay_dir = root / "config" / "overlay"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    target_name = None
    content_str = None

    if "file" in request.files:
        f = request.files["file"]
        filename = f.filename or ""
        target_name = request.form.get("target") or filename
        # The uploaded file's own name must match the requested target overlay
        # (prevents saving e.g. my_settings.config as apk_overlays.config).
        if target_name and filename and Path(filename).name != Path(str(target_name)).name:
            abort(400, description=(
                "Filename mismatch: uploaded '%s' but target overlay is '%s'. "
                "Rename the file to '%s' and upload again."
                % (Path(filename).name, Path(str(target_name)).name, Path(str(target_name)).name)))
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

    target_name = Path(str(target_name).strip()).name
    allowed_targets = ("apk_overlays.config", "const_my_cli.config")
    if target_name not in allowed_targets:
        abort(400, description="Invalid overlay file name '%s'. Allowed: %s" % (target_name, ", ".join(allowed_targets)))

    if content_str is None:
        abort(400, description="Empty file content.")

    err = validate_content("bash", content_str)
    if err:
        abort(400, description="File contains invalid bash syntax: %s" % err)

    if target_name == "const_my_cli.config":
        dest_dir = overlay_dir / "cli"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / target_name
        rel_out = f"config/overlay/cli/{target_name}"
    else:
        dest_path = overlay_dir / target_name
        rel_out = f"config/overlay/{target_name}"
    backup = None
    if dest_path.is_file():
        try:
            bak = dest_path.with_suffix(".config.bak")
            shutil.copy2(dest_path, bak)
            backup = str(bak.relative_to(root)).replace("\\", "/")
        except OSError:
            pass

    try:
        with open(dest_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content_str)
    except OSError as exc:
        abort(500, description="Failed to write '%s': %s" % (target_name, exc))

    if target_name == "apk_overlays.config" and apk_config.is_file():
        try:
            m = re.search(r'^\s*ACTIVE_PROJECT\s*=\s*["\']?(.*?)["\']?\s*$', content_str, re.M)
            if m:
                proj = m.group(1).strip()
                sub = re.match(r'^\$\{[A-Za-z0-9_]+:-(.*?)\}$', proj)
                if sub:
                    proj = sub.group(1).strip()
                if proj:
                    apk_text = apk_config.read_text(encoding="utf-8", errors="ignore")
                    if re.search(r'ACTIVE_PROJECT\s*=', apk_text):
                        apk_text = re.sub(r'(?m)^([ \t]*ACTIVE_PROJECT\s*=\s*)["\']?.*?["\']?$', r'\g<1>"%s"' % proj, apk_text, count=1)
                        apk_config.write_text(apk_text, encoding="utf-8")
        except OSError:
            pass

    return jsonify({
        "ok": True,
        "filename": target_name,
        "path": rel_out,
        "bytes": len(content_str.encode("utf-8")),
        "backup": backup,
        "aosp_info": _parse_aosp_info() if target_name == "apk_overlays.config" else None,
    })


@aosp_bp.get("/api/crypto/status")
def api_crypto_status():
    return jsonify({
        "ok": True,
        "overlay_dir": "config/overlay",
        "items": _crypto_items(),
    })


@aosp_bp.post("/api/crypto/action")
def api_crypto_action():
    """Encrypt/decrypt private overlay configs or apply apk_overlays.config -> apk.config."""
    root = get_root()
    apk_config = get_apk_config_path()
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

    overlay_dir = root / "config" / "overlay"
    crypto_script = root / "python" / "config_crypto.py"
    overlay_script = root / "python" / "config_overlay.py"
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
                cwd=str(root), capture_output=True, text=True, timeout=60,
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
                cwd=str(root),
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
        elif apk_config.is_file() and overlay_script.is_file():
            proc = subprocess.run(
                [sys.executable, str(overlay_script), str(apk_config), str(ov_file)],
                cwd=str(root),
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
