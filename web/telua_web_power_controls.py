#!/usr/bin/env python3
# ==============================================================================
# Telua Web - Target Power Controls Blueprint
# Persists target power state (ON / OFF) into configuration before integrating
# with actual hardware relays, smart plugs, or board GPIO/PMIC controls.
# ==============================================================================

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, abort, jsonify, request

power_bp = Blueprint("power", __name__)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = REPO_ROOT / "config"
POWER_CONFIG_FILE = CONFIG_DIR / "target_power_state.json"

DEFAULT_POWER_CONFIG: Dict[str, Any] = {
    "state": "ON",
    "voltage": 12.0,
    "current_a": 1.25,
    "mode": "config_simulation",
    "target_name": "AOSP Target Board",
    "last_changed": datetime.now().isoformat(),
    "history": [],
    "notes": "Target power state managed by telua_web_power_controls. Ready for hardware relay integration."
}


def _read_power_config() -> Dict[str, Any]:
    """Read power state from config file or return default."""
    if not POWER_CONFIG_FILE.is_file():
        return dict(DEFAULT_POWER_CONFIG)
    try:
        content = POWER_CONFIG_FILE.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            if data.get("state") not in ("ON", "OFF"):
                data["state"] = "ON"
            return data
    except Exception:
        pass
    return dict(DEFAULT_POWER_CONFIG)


def _write_power_config(data: Dict[str, Any]) -> bool:
    """Save power state configuration to disk safely."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        history = data.get("history", [])
        if not isinstance(history, list):
            history = []
        data["history"] = history[-10:]
        tmp_file = POWER_CONFIG_FILE.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_file.replace(POWER_CONFIG_FILE)
        return True
    except Exception:
        return False


@power_bp.get("/api/power/status")
def api_power_status():
    """Return current target power status, voltage, current and config metadata."""
    cfg = _read_power_config()
    is_on = cfg.get("state") == "ON"
    return jsonify({
        "ok": True,
        "state": cfg.get("state", "ON"),
        "is_on": is_on,
        "voltage": cfg.get("voltage", 12.0 if is_on else 0.0),
        "current_a": cfg.get("current_a", 1.25 if is_on else 0.0),
        "mode": cfg.get("mode", "config_simulation"),
        "target_name": cfg.get("target_name", "AOSP Target Board"),
        "last_changed": cfg.get("last_changed", ""),
        "config_file": "config/target_power_state.json",
        "history": cfg.get("history", []),
    })


@power_bp.post("/api/power/set")
def api_power_set():
    """Set target power state explicitly to ON or OFF."""
    data = request.get_json(silent=True) or {}
    raw_state = str(data.get("state", "")).strip().upper()

    # Also support boolean "power" or "on"
    if "power" in data:
        raw_state = "ON" if data.get("power") else "OFF"
    elif "on" in data:
        raw_state = "ON" if data.get("on") else "OFF"

    if raw_state not in ("ON", "OFF"):
        abort(400, description="Invalid power state. Must be 'ON' or 'OFF'.")

    cfg = _read_power_config()
    prev_state = cfg.get("state", "ON")
    now_iso = datetime.now().isoformat()

    cfg["state"] = raw_state
    cfg["last_changed"] = now_iso
    cfg["voltage"] = 12.0 if raw_state == "ON" else 0.0
    cfg["current_a"] = 1.25 if raw_state == "ON" else 0.0

    history_entry = {
        "from": prev_state,
        "to": raw_state,
        "timestamp": now_iso,
        "client_ip": request.remote_addr or "127.0.0.1",
        "reason": data.get("reason", "manual_button_click"),
    }
    history = cfg.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(history_entry)
    cfg["history"] = history

    saved = _write_power_config(cfg)
    if not saved:
        abort(500, description="Failed to persist power state to config file.")

    return jsonify({
        "ok": True,
        "state": raw_state,
        "is_on": raw_state == "ON",
        "prev_state": prev_state,
        "voltage": cfg["voltage"],
        "current_a": cfg["current_a"],
        "last_changed": now_iso,
        "message": f"Target Power successfully turned {raw_state} (persisted in config).",
    })


@power_bp.post("/api/power/toggle")
def api_power_toggle():
    """Toggle target power between ON and OFF."""
    cfg = _read_power_config()
    current = cfg.get("state", "ON")
    next_state = "OFF" if current == "ON" else "ON"

    now_iso = datetime.now().isoformat()
    cfg["state"] = next_state
    cfg["last_changed"] = now_iso
    cfg["voltage"] = 12.0 if next_state == "ON" else 0.0
    cfg["current_a"] = 1.25 if next_state == "ON" else 0.0

    history_entry = {
        "from": current,
        "to": next_state,
        "timestamp": now_iso,
        "client_ip": request.remote_addr or "127.0.0.1",
        "reason": "toggle_button_click",
    }
    history = cfg.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(history_entry)
    cfg["history"] = history

    saved = _write_power_config(cfg)
    if not saved:
        abort(500, description="Failed to persist power state to config file.")

    return jsonify({
        "ok": True,
        "state": next_state,
        "is_on": next_state == "ON",
        "prev_state": current,
        "voltage": cfg["voltage"],
        "current_a": cfg["current_a"],
        "last_changed": now_iso,
        "message": f"Target Power toggled to {next_state}.",
    })
