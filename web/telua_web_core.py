#!/usr/bin/env python3
# ==============================================================================
# telua_web_core.py — File registry, syntax validation & system status helpers
# ==============================================================================

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

PRIVATE_OVERLAY_NAMES = ("apk_overlays.config", "const_my_cli.config")


def is_editable_name(name: str) -> bool:
    """True for *.config / *.json files, excluding backups & encrypted blobs."""
    if not name.endswith((".config", ".json")):
        return False
    if name.endswith(".bak") or ".bak." in name:
        return False
    if name.startswith("enc_"):        # encrypted template: never edit via UI
        return False
    return True


def ensure_overlay_configs(root: Path):
    """Auto-create missing personal configs in config/overlay/ from .example templates (never overwrites)."""
    overlay_dir = root / "config" / "overlay"
    if not overlay_dir.is_dir():
        return
    for base in PRIVATE_OVERLAY_NAMES:
        dst = overlay_dir / base
        src = overlay_dir / (base + ".example")
        if not dst.exists() and src.is_file():
            try:
                shutil.copyfile(str(src), str(dst))
            except OSError:
                pass


def scan_files_in_root(root: Path):
    """Scan toolkit root + config/ + config/overlay/ for editable config files."""
    ensure_overlay_configs(root)
    entries = []
    seen = set()

    def add(rel: str):
        full = root / rel
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
        for name in sorted(os.listdir(root)):
            if is_editable_name(name) and (root / name).is_file():
                add(name)
    except OSError:
        pass

    # 2. Then the config/ directory (const_*.config cheatsheets & pipelines)
    cfg_dir = root / "config"
    if cfg_dir.is_dir():
        for name in sorted(os.listdir(cfg_dir)):
            if is_editable_name(name) and (cfg_dir / name).is_file():
                add("config/" + name)

    # 2b. Personal overlay dir (git-ignored): apk_overlays.config, const_my_cli.config
    overlay_dir = root / "config" / "overlay"
    if overlay_dir.is_dir():
        for name in sorted(os.listdir(overlay_dir)):
            if is_editable_name(name) and (overlay_dir / name).is_file():
                add("config/overlay/" + name)

    priority = {
        "config/apk.config": 0,
        "apk.config": 0,
        "config/overlay/apk_overlays.config": 1,
        "config/apk_overlays.config": 1,
        "apk_overlays.config": 1,
        "config/overlay/const_my_cli.config": 1,
        "config/const_my_cli.config": 1,
        "config/const_multi_cli.config": 2,
        "config/const_system_cli.config": 2,
        "config/const_car.config": 2,
        "config/const_dumpsys.config": 2,
    }
    entries.sort(key=lambda f: (priority.get(f["name"], 3), f["name"]))
    return entries


def validate_content(kind: str, content: str):
    """Return None when valid, else a human-readable error string."""
    if kind == "json":
        try:
            json.loads(content)
            return None
        except ValueError as exc:
            return "Invalid JSON: %s" % exc
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


def parse_version_from_file(build_apk_sh: Path):
    try:
        text = build_apk_sh.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'SCRIPT_VERSION="([^"]+)"', text)
        return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


def parse_active_project_from_file(apk_config: Path):
    try:
        text = apk_config.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'^\s*ACTIVE_PROJECT\s*=\s*"([^"]*)"', text, re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def parse_profiles_from_file(apk_config: Path):
    """Extract profile names from the 'case "$ACTIVE_PROJECT" in ... esac' block."""
    try:
        text = apk_config.read_text(encoding="utf-8", errors="ignore")
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


def ram_info(meminfo_path: Path = Path("/proc/meminfo")):
    """Parse /proc/meminfo (Linux) into GB values; None when unavailable."""
    try:
        text = meminfo_path.read_text(encoding="utf-8")
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


def crypto_items_for_root(root: Path):
    overlay_dir = root / "config" / "overlay"
    items = []
    for name in PRIVATE_OVERLAY_NAMES:
        plain_path = overlay_dir / name
        enc_path = overlay_dir / ("enc_" + name)
        dec_path = overlay_dir / ("dec_" + name)
        p_exists = plain_path.is_file()
        e_exists = enc_path.is_file()
        d_exists = dec_path.is_file()
        p_stat = plain_path.stat() if p_exists else None
        e_stat = enc_path.stat() if e_exists else None
        d_stat = dec_path.stat() if d_exists else None
        items.append({
            "name": name,
            "plain_rel": "config/overlay/%s" % name,
            "enc_rel": "config/overlay/enc_%s" % name,
            "dec_rel": "config/overlay/dec_%s" % name,
            "plain_exists": p_exists,
            "plain_size": p_stat.st_size if p_stat else 0,
            "plain_mtime": datetime.fromtimestamp(p_stat.st_mtime).strftime("%Y-%m-%d %H:%M") if p_stat else None,
            "enc_exists": e_exists,
            "enc_size": e_stat.st_size if e_stat else 0,
            "enc_mtime": datetime.fromtimestamp(e_stat.st_mtime).strftime("%Y-%m-%d %H:%M") if e_stat else None,
            "dec_exists": d_exists,
            "dec_size": d_stat.st_size if d_stat else 0,
            "dec_mtime": datetime.fromtimestamp(d_stat.st_mtime).strftime("%Y-%m-%d %H:%M") if d_stat else None,
            "synced": bool(p_stat and e_stat and int(e_stat.st_mtime) >= int(p_stat.st_mtime)),
        })
    return items
