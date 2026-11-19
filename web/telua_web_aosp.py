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
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.config", target_name):
            abort(400, description="Invalid overlay file name '%s'. Allowed: %s" % (target_name, ", ".join(allowed_targets)))

    if content_str is None:
        abort(400, description="Empty file content.")

    err = validate_content("bash", content_str)
    if err:
        abort(400, description="File contains invalid bash syntax: %s" % err)

    dest_path = overlay_dir / target_name
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
        "path": f"config/overlay/{target_name}",
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
