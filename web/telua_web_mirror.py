#!/usr/bin/env python3
# ==============================================================================
# Telua Web - Screen Mirroring & Android Remote Control Blueprint
# Zero-dependency screen capture via `adb exec-out screencap -p` and
# touch / key input injection via `adb shell input ...`.
# ==============================================================================

import io
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from flask import Blueprint, Response, abort, jsonify, request, send_file
from telua_web_core import adb_devices

mirror_bp = Blueprint("mirror", __name__)


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


def _get_target_device_args(device_serial: str = "") -> list:
    """Build ['-s', serial] prefix for adb if a device serial is specified."""
    if device_serial:
        return ["-s", device_serial]
    devices = adb_devices()
    online = [d["serial"] for d in devices if d.get("state") == "device"]
    if online:
        return ["-s", online[0]]
    if devices:
        return ["-s", devices[0]["serial"]]
    return []


def _fetch_screen_dimensions(adb: str, dev_args: list) -> Tuple[int, int, int]:
    """Return (width, height, density) from device via `wm size` and `wm density`."""
    width, height, density = 1080, 1920, 420
    try:
        proc_size = subprocess.run([adb] + dev_args + ["shell", "wm", "size"],
                                   capture_output=True, text=True, timeout=3)
        out = proc_size.stdout or ""
        # Match "Physical size: 1080x1920" or "Override size: 1920x1080"
        m_override = re.search(r"Override size:\s*(\d+)x(\d+)", out)
        m_physical = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
        m = m_override or m_physical
        if m:
            width = int(m.group(1))
            height = int(m.group(2))
    except Exception:
        pass

    try:
        proc_dense = subprocess.run([adb] + dev_args + ["shell", "wm", "density"],
                                    capture_output=True, text=True, timeout=3)
        out_d = proc_dense.stdout or ""
        m_d = re.search(r"(?:Override|Physical) density:\s*(\d+)", out_d)
        if m_d:
            density = int(m_d.group(1))
    except Exception:
        pass

    return width, height, density


@mirror_bp.get("/api/mirror/info")
def api_mirror_info():
    """Return screen resolution, aspect ratio, density, and device connection state."""
    adb = _resolve_adb_binary()
    devices = adb_devices()
    dev_param = request.args.get("device", "").strip()
    dev_args = _get_target_device_args(dev_param)
    
    current_dev = dev_args[1] if len(dev_args) == 2 else (devices[0]["serial"] if devices else "")
    online = any(d["serial"] == current_dev and d.get("state") == "device" for d in devices)

    width, height, density = 1080, 1920, 420
    if adb and online:
        width, height, density = _fetch_screen_dimensions(adb, dev_args)

    aspect = "landscape" if width > height else "portrait"
    return jsonify({
        "ok": True,
        "adb_available": bool(adb),
        "device": current_dev,
        "connected": online,
        "devices": devices,
        "width": width,
        "height": height,
        "density": density,
        "aspect": aspect,
    })


@mirror_bp.get("/api/mirror/frame")
def api_mirror_frame():
    """Capture a single live screen frame as PNG via `adb exec-out screencap -p`."""
    adb = _resolve_adb_binary()
    if not adb:
        abort(400, description="ADB binary not found.")

    dev_param = request.args.get("device", "").strip()
    dev_args = _get_target_device_args(dev_param)

    try:
        proc = subprocess.run(
            [adb] + dev_args + ["exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=5,
        )
        if proc.returncode != 0 or not proc.stdout:
            err = proc.stderr.decode("utf-8", errors="ignore").strip() or "Device offline or capture failed"
            abort(400, description=f"screencap failed: {err}")

        img_bytes = proc.stdout
        # Ensure PNG magic header: \x89PNG\r\n\x1a\n
        if not img_bytes.startswith(b"\x89PNG"):
            abort(500, description="Invalid image data returned from screencap.")

        return Response(
            img_bytes,
            mimetype="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except subprocess.TimeoutExpired:
        abort(504, description="screencap timed out after 5s.")
    except Exception as exc:
        abort(500, description=f"Capture error: {exc}")


@mirror_bp.post("/api/mirror/touch")
def api_mirror_touch():
    """Inject touch / tap event via `adb shell input tap <x> <y>`."""
    adb = _resolve_adb_binary()
    if not adb:
        abort(400, description="ADB binary not found.")

    data = request.get_json(silent=True) or {}
    dev_param = str(data.get("device", "")).strip()
    dev_args = _get_target_device_args(dev_param)

    try:
        x = int(data.get("x", 0))
        y = int(data.get("y", 0))
    except (ValueError, TypeError):
        abort(400, description="Invalid x, y coordinates.")

    try:
        subprocess.run([adb] + dev_args + ["shell", "input", "tap", str(x), str(y)],
                       capture_output=True, timeout=3)
        return jsonify({"ok": True, "action": "tap", "x": x, "y": y})
    except Exception as exc:
        abort(500, description=f"Touch injection failed: {exc}")


@mirror_bp.post("/api/mirror/swipe")
def api_mirror_swipe():
    """Inject swipe / scroll event via `adb shell input swipe <x1> <y1> <x2> <y2> [duration]`."""
    adb = _resolve_adb_binary()
    if not adb:
        abort(400, description="ADB binary not found.")

    data = request.get_json(silent=True) or {}
    dev_param = str(data.get("device", "")).strip()
    dev_args = _get_target_device_args(dev_param)

    try:
        x1 = int(data.get("x1", 0))
        y1 = int(data.get("y1", 0))
        x2 = int(data.get("x2", 0))
        y2 = int(data.get("y2", 0))
        duration = max(50, min(3000, int(data.get("duration", 250))))
    except (ValueError, TypeError):
        abort(400, description="Invalid swipe parameters.")

    try:
        subprocess.run(
            [adb] + dev_args + ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)],
            capture_output=True, timeout=4)
        return jsonify({"ok": True, "action": "swipe", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration})
    except Exception as exc:
        abort(500, description=f"Swipe injection failed: {exc}")


@mirror_bp.post("/api/mirror/key")
def api_mirror_key():
    """Inject Android hardware / navigation key via `adb shell input keyevent <key>`."""
    adb = _resolve_adb_binary()
    if not adb:
        abort(400, description="ADB binary not found.")

    data = request.get_json(silent=True) or {}
    dev_param = str(data.get("device", "")).strip()
    dev_args = _get_target_device_args(dev_param)

    key = str(data.get("key", "")).strip()
    if not key or not re.match(r"^[A-Za-z0-9_]+$", key):
        abort(400, description="Invalid key identifier.")

    try:
        subprocess.run([adb] + dev_args + ["shell", "input", "keyevent", key],
                       capture_output=True, timeout=3)
        return jsonify({"ok": True, "action": "key", "key": key})
    except Exception as exc:
        abort(500, description=f"Key event injection failed: {exc}")


@mirror_bp.post("/api/mirror/text")
def api_mirror_text():
    """Inject text into current focused input field via `adb shell input text '<escaped>'`."""
    adb = _resolve_adb_binary()
    if not adb:
        abort(400, description="ADB binary not found.")

    data = request.get_json(silent=True) or {}
    dev_param = str(data.get("device", "")).strip()
    dev_args = _get_target_device_args(dev_param)

    text = str(data.get("text", ""))
    if not text:
        return jsonify({"ok": True, "action": "text", "injected": ""})

    # In `adb shell input text`, spaces must be %s or escaped
    safe_text = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>")

    try:
        subprocess.run([adb] + dev_args + ["shell", "input", "text", safe_text],
                       capture_output=True, timeout=4)
        return jsonify({"ok": True, "action": "text", "length": len(text)})
    except Exception as exc:
        abort(500, description=f"Text injection failed: {exc}")


@mirror_bp.get("/api/mirror/screenshot")
def api_mirror_screenshot():
    """Capture full resolution screenshot and return as downloadable PNG file."""
    adb = _resolve_adb_binary()
    if not adb:
        abort(400, description="ADB binary not found.")

    dev_param = request.args.get("device", "").strip()
    dev_args = _get_target_device_args(dev_param)

    try:
        proc = subprocess.run(
            [adb] + dev_args + ["exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=6,
        )
        if proc.returncode != 0 or not proc.stdout:
            abort(400, description="Screenshot capture failed.")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"

        return send_file(
            io.BytesIO(proc.stdout),
            mimetype="image/png",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as exc:
        abort(500, description=f"Screenshot error: {exc}")
