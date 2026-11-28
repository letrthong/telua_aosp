#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# ai_notify.py — Telegram Error Notification helpers for Telua AI Agent
# ==============================================================================

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from .ai_config_paths import overlay_file as _ai_overlay_file

# ------------------------------------------------------------------------------
# Telegram Notification (stored in config/overlay/ai_agent/ai_notify.json)
# ------------------------------------------------------------------------------

_NOTIFY_LOCK = threading.Lock()
_DEFAULT_NOTIFY_CFG = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
    "notify_on_agent_error": True,
    "notify_on_tool_error": True,
    "notify_on_guardrail_stop": False,
}


def _notify_cfg_file() -> Path:
    return _ai_overlay_file("ai_notify.json")


def get_ai_notify_config() -> dict:
    cfg = dict(_DEFAULT_NOTIFY_CFG)
    path = _notify_cfg_file()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
        except Exception:
            pass
    return cfg


def save_ai_notify_config(updates: dict) -> dict:
    with _NOTIFY_LOCK:
        cfg = get_ai_notify_config()
        if "enabled" in updates:
            cfg["enabled"] = bool(updates["enabled"])
        if updates.get("clear_token"):
            cfg["bot_token"] = ""
        elif "bot_token" in updates and str(updates["bot_token"] or "").strip():
            cfg["bot_token"] = str(updates["bot_token"]).strip()
        if "chat_id" in updates:
            cfg["chat_id"] = str(updates["chat_id"] or "").strip()
        for key in ("notify_on_agent_error", "notify_on_tool_error", "notify_on_guardrail_stop"):
            if key in updates:
                cfg[key] = bool(updates[key])

        path = _notify_cfg_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(path))
        return cfg


def _mask_secret(token: str) -> str:
    t = str(token or "").strip()
    if not t:
        return ""
    if len(t) <= 10:
        return "*" * len(t)
    return t[:6] + "..." + t[-4:]


def _send_telegram_message(text: str, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> Tuple[bool, str]:
    """Send a Telegram message via Bot API using stdlib urllib (no extra dependencies)."""
    import urllib.error
    import urllib.request

    cfg = get_ai_notify_config()
    token = (bot_token or "").strip() or str(cfg.get("bot_token") or "").strip()
    cid = (chat_id or "").strip() or str(cfg.get("chat_id") or "").strip()
    if not token:
        return False, "Missing Telegram Bot Token."
    if not cid:
        return False, "Missing Telegram Chat ID."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": cid,
        "text": str(text or "")[:3900],
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            if body.get("ok"):
                return True, "Telegram notification sent."
            return False, str(body.get("description") or "Telegram API returned ok=false")
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return False, f"HTTP {exc.code}: {err_body or exc.reason}"
    except Exception as exc:
        return False, str(exc)


def _notify_telegram_async(title: str, detail: str, category: str = "agent_error") -> None:
    """Fire-and-forget Telegram alert if enabled for the given error category."""
    try:
        cfg = get_ai_notify_config()
        if not cfg.get("enabled"):
            return
        if not cfg.get("bot_token") or not cfg.get("chat_id"):
            return
        flag_map = {
            "agent_error": "notify_on_agent_error",
            "tool_error": "notify_on_tool_error",
            "guardrail_stop": "notify_on_guardrail_stop",
        }
        flag = flag_map.get(category)
        if flag and not cfg.get(flag, False):
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"🚨 [Telua AI Agent] {title}\n🕒 {ts}\n\n{str(detail or '')[:2500]}"
        threading.Thread(
            target=_send_telegram_message,
            args=(msg,),
            daemon=True,
        ).start()
    except Exception:
        pass


def _tool_send_telegram_notify(args: dict) -> str:
    """Send a Telegram alert message using the configured Bot Token & Chat ID."""
    msg = str(args.get("message") or "").strip()
    if not msg:
        return "[ERROR] missing 'message' parameter"
    ok, info = _send_telegram_message(msg)
    return f"[SUCCESS] {info}" if ok else f"[ERROR] Telegram send failed: {info}"

