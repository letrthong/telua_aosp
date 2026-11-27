#!/usr/bin/env python3
# ==============================================================================
# Telua Web - Target Power Controls Blueprint
# Persists target dual power switches (Ngõ ra 1: Main Power & Ngõ ra 2: ACC / IGN)
# into configuration before integrating with actual hardware relays or GPIO.
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
_POWER_JSON_NEW = CONFIG_DIR / "json" / "target_power_state.json"
_POWER_JSON_LEGACY = CONFIG_DIR / "target_power_state.json"
POWER_CONFIG_FILE = _POWER_JSON_NEW if (_POWER_JSON_NEW.is_file() or not _POWER_JSON_LEGACY.is_file()) else _POWER_JSON_LEGACY

DEFAULT_OUTPUTS: Dict[str, Any] = {
    "out1": {
        "id": "out1",
        "name": "Ngõ ra 1: Main Power (BATT+ / 12V)",
        "state": "ON",
        "voltage": 12.0,
        "current_a": 1.25,
        "channel": "RELAY_CH1",
        "desc": "Nguồn chính cấp điện áp 12V nuôi board mạch AOSP / IVI",
    },
    "out2": {
        "id": "out2",
        "name": "Ngõ ra 2: ACC / Ignition (IGN)",
        "state": "ON",
        "voltage": 12.0,
        "current_a": 0.08,
        "channel": "RELAY_CH2",
        "desc": "Tín hiệu bật khóa điện ô tô (ACC/Ignition) điều khiển trạng thái thức/ngủ",
    },
}

DEFAULT_POWER_CONFIG: Dict[str, Any] = {
    "state": "ON",
    "voltage": 12.0,
    "current_a": 1.33,
    "mode": "config_simulation",
    "target_name": "AOSP Automotive Target Board",
    "last_changed": datetime.now().isoformat(),
    "outputs": DEFAULT_OUTPUTS,
    "history": [],
    "notes": "Target dual power switches managed by telua_web_power_controls. Ready for hardware relay."
}


def _read_power_config() -> Dict[str, Any]:
    """Read power state from config file, ensuring dual outputs exist."""
    if not POWER_CONFIG_FILE.is_file():
        return dict(DEFAULT_POWER_CONFIG)
    try:
        content = POWER_CONFIG_FILE.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            # Ensure outputs dict exists
            outputs = data.get("outputs")
            if not isinstance(outputs, dict) or "out1" not in outputs or "out2" not in outputs:
                state_val = data.get("state", "ON")
                data["outputs"] = {
                    "out1": dict(DEFAULT_OUTPUTS["out1"], state=state_val),
                    "out2": dict(DEFAULT_OUTPUTS["out2"], state=state_val),
                }
            # Compute aggregate state
            out1_on = data["outputs"]["out1"].get("state") == "ON"
            out2_on = data["outputs"]["out2"].get("state") == "ON"
            data["state"] = "ON" if (out1_on or out2_on) else "OFF"
            data["voltage"] = 12.0 if out1_on else 0.0
            data["current_a"] = round((1.25 if out1_on else 0.0) + (0.08 if out2_on else 0.0), 2)
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
        data["history"] = history[-15:]
        tmp_file = POWER_CONFIG_FILE.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_file.replace(POWER_CONFIG_FILE)
        return True
    except Exception:
        return False


@power_bp.get("/api/power/status")
def api_power_status():
    """Return current target power status, dual outputs, voltage, current and metadata."""
    cfg = _read_power_config()
    out1 = cfg["outputs"]["out1"]
    out2 = cfg["outputs"]["out2"]
    is_on = cfg.get("state") == "ON"

    return jsonify({
        "ok": True,
        "state": cfg.get("state", "ON"),
        "is_on": is_on,
        "voltage": cfg.get("voltage", 12.0 if is_on else 0.0),
        "current_a": cfg.get("current_a", 1.33 if is_on else 0.0),
        "mode": cfg.get("mode", "config_simulation"),
        "target_name": cfg.get("target_name", "AOSP Automotive Target Board"),
        "last_changed": cfg.get("last_changed", ""),
        "config_file": "config/json/target_power_state.json",
        "outputs": {
            "out1": out1,
            "out2": out2,
        },
        "history": cfg.get("history", []),
    })


@power_bp.post("/api/power/set")
def api_power_set():
    """Set power state for a specific output ('out1', 'out2') or master ('all')."""
    data = request.get_json(silent=True) or {}
    raw_state = str(data.get("state", "")).strip().upper()
    target_out = str(data.get("output", "")).strip().lower()

    if "power" in data:
        raw_state = "ON" if data.get("power") else "OFF"
    elif "on" in data:
        raw_state = "ON" if data.get("on") else "OFF"

    if raw_state not in ("ON", "OFF"):
        abort(400, description="Invalid power state. Must be 'ON' or 'OFF'.")

    cfg = _read_power_config()
    now_iso = datetime.now().isoformat()
    client_ip = request.remote_addr or "127.0.0.1"

    history_entry = {
        "output": target_out or "all",
        "to": raw_state,
        "timestamp": now_iso,
        "client_ip": client_ip,
        "reason": data.get("reason", "switch_toggle"),
    }

    if target_out in ("out1", "out2"):
        prev_sub = cfg["outputs"][target_out].get("state", "ON")
        cfg["outputs"][target_out]["state"] = raw_state
        cfg["outputs"][target_out]["voltage"] = 12.0 if raw_state == "ON" else 0.0
        history_entry["from"] = prev_sub
    else:
        # Master set for both outputs
        for k in ("out1", "out2"):
            cfg["outputs"][k]["state"] = raw_state
            cfg["outputs"][k]["voltage"] = 12.0 if raw_state == "ON" else 0.0
        history_entry["from"] = cfg.get("state", "ON")

    # Recompute aggregate state
    out1_on = cfg["outputs"]["out1"]["state"] == "ON"
    out2_on = cfg["outputs"]["out2"]["state"] == "ON"
    cfg["state"] = "ON" if (out1_on or out2_on) else "OFF"
    cfg["voltage"] = 12.0 if out1_on else 0.0
    cfg["current_a"] = round((1.25 if out1_on else 0.0) + (0.08 if out2_on else 0.0), 2)
    cfg["last_changed"] = now_iso

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
        "state": cfg["state"],
        "is_on": cfg["state"] == "ON",
        "output": target_out or "all",
        "target_state": raw_state,
        "outputs": cfg["outputs"],
        "voltage": cfg["voltage"],
        "current_a": cfg["current_a"],
        "last_changed": now_iso,
        "message": f"Power output '{target_out or 'all'}' switched {raw_state} (persisted in config).",
    })


@power_bp.post("/api/power/output/<out_id>")
def api_power_set_output(out_id: str):
    """Convenience endpoint to control a specific output switch (out1 or out2)."""
    out_id = out_id.lower().strip()
    if out_id not in ("out1", "out2"):
        abort(404, description=f"Output channel '{out_id}' not found. Use 'out1' or 'out2'.")

    data = request.get_json(silent=True) or {}
    raw_state = str(data.get("state", "")).strip().upper()
    if not raw_state:
        # If no state passed, toggle it
        cfg = _read_power_config()
        curr = cfg["outputs"][out_id].get("state", "ON")
        raw_state = "OFF" if curr == "ON" else "ON"

    if raw_state not in ("ON", "OFF"):
        abort(400, description="Invalid power state. Must be 'ON' or 'OFF'.")

    cfg = _read_power_config()
    now_iso = datetime.now().isoformat()
    prev_state = cfg["outputs"][out_id].get("state", "ON")

    cfg["outputs"][out_id]["state"] = raw_state
    cfg["outputs"][out_id]["voltage"] = 12.0 if raw_state == "ON" else 0.0

    out1_on = cfg["outputs"]["out1"]["state"] == "ON"
    out2_on = cfg["outputs"]["out2"]["state"] == "ON"
    cfg["state"] = "ON" if (out1_on or out2_on) else "OFF"
    cfg["voltage"] = 12.0 if out1_on else 0.0
    cfg["current_a"] = round((1.25 if out1_on else 0.0) + (0.08 if out2_on else 0.0), 2)
    cfg["last_changed"] = now_iso

    history = cfg.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append({
        "output": out_id,
        "from": prev_state,
        "to": raw_state,
        "timestamp": now_iso,
        "client_ip": request.remote_addr or "127.0.0.1",
        "reason": data.get("reason", "output_switch_click"),
    })
    cfg["history"] = history

    saved = _write_power_config(cfg)
    if not saved:
        abort(500, description="Failed to persist power state to config file.")

    return jsonify({
        "ok": True,
        "output": out_id,
        "state": raw_state,
        "is_on": raw_state == "ON",
        "outputs": cfg["outputs"],
        "voltage": cfg["voltage"],
        "current_a": cfg["current_a"],
        "last_changed": now_iso,
    })


@power_bp.post("/api/power/toggle")
def api_power_toggle():
    """Toggle target power output (out1, out2, or master)."""
    data = request.get_json(silent=True) or {}
    target_out = str(data.get("output", "out1")).strip().lower()
    if target_out not in ("out1", "out2", "all"):
        target_out = "out1"

    cfg = _read_power_config()
    if target_out in ("out1", "out2"):
        current = cfg["outputs"][target_out].get("state", "ON")
        next_state = "OFF" if current == "ON" else "ON"
        return api_power_set_output(target_out)
    else:
        current = cfg.get("state", "ON")
        next_state = "OFF" if current == "ON" else "ON"
        data["state"] = next_state
        return api_power_set()
