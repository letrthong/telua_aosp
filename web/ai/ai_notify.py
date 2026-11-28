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
_POLLER_LOCK = threading.Lock()
_POLLER_STARTED = False
_DEFAULT_NOTIFY_CFG = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
    "safe_mode": True,
    "bot_listen_enabled": False,
    "last_update_id": 0,
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
        for key in ("safe_mode", "bot_listen_enabled", "notify_on_agent_error", "notify_on_tool_error", "notify_on_guardrail_stop"):
            if key in updates:
                cfg[key] = bool(updates[key])
        if "last_update_id" in updates:
            try:
                cfg["last_update_id"] = int(updates["last_update_id"])
            except (TypeError, ValueError):
                pass

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


def _sanitize_for_safe_mode(text: str) -> str:
    """Strip code blocks, file paths, and long log lines when Telegram Safe Mode is ON."""
    import re
    s = str(text or "")
    s = re.sub(r"```[\s\S]*?```", "[code omitted]", s)
    s = re.sub(r"(?:[A-Za-z]:\\|/(?:home|usr|var|opt|etc|packages|frameworks|vendor|device)/)[^\s\"'<>]+", "[path]", s)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip() and not ln.lstrip().startswith(("at ", "File ", "Traceback"))]
    summary = " | ".join(lines)[:240]
    return summary or "(status update)"


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
        if cfg.get("safe_mode", True):
            msg = (
                f"🚨 [Telua AI Agent] {title}\n"
                f"🕒 {ts}\n"
                f"🛡 Safe Mode: log & code details are hidden — open Telua Web to inspect."
            )
        else:
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
    cfg = get_ai_notify_config()
    if cfg.get("safe_mode", True):
        msg = f"🔔 [Telua AI] {_sanitize_for_safe_mode(msg)}\n(🛡 Safe Mode: code/paths redacted)"
    ok, info = _send_telegram_message(msg)
    return f"[SUCCESS] {info}" if ok else f"[ERROR] Telegram send failed: {info}"


def fetch_telegram_messages(
    limit: int = 10,
    offset: Optional[int] = None,
    timeout: int = 0,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Tuple[bool, list, str, int]:
    """Read recent incoming messages from Telegram Bot API (getUpdates),
    strictly filtered to the configured authorized `chat_id`.

    Returns: (ok, messages_list, error_msg, max_update_id)
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    cfg = get_ai_notify_config()
    token = (bot_token or "").strip() or str(cfg.get("bot_token") or "").strip()
    allowed_cid = (chat_id or "").strip() or str(cfg.get("chat_id") or "").strip()
    if not token:
        return False, [], "Missing Telegram Bot Token.", 0

    params = {"limit": max(1, min(int(limit or 10), 50))}
    if offset is not None and int(offset) > 0:
        params["offset"] = int(offset)
    if timeout and int(timeout) > 0:
        params["timeout"] = max(1, min(int(timeout), 30))

    url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    http_timeout = (int(timeout) + 8) if timeout else 10
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return False, [], f"HTTP {exc.code}: {err_body or exc.reason}", 0
    except Exception as exc:
        return False, [], str(exc), 0

    if not body.get("ok"):
        return False, [], str(body.get("description") or "Telegram getUpdates failed"), 0

    updates = body.get("result") or []
    messages = []
    max_uid = 0
    for upd in updates:
        uid = int(upd.get("update_id") or 0)
        if uid > max_uid:
            max_uid = uid
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or {}
        if not msg:
            continue
        chat = msg.get("chat") or {}
        cid = str(chat.get("id") or "")
        # Strict allowlist: if chat_id is configured, ignore messages from other chats
        if allowed_cid and cid != allowed_cid:
            continue
        text = str(msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            continue
        sender = msg.get("from") or {}
        sender_name = sender.get("username") or sender.get("first_name") or "user"
        ts_unix = int(msg.get("date") or 0)
        ts_str = datetime.fromtimestamp(ts_unix).strftime("%Y-%m-%d %H:%M:%S") if ts_unix else ""
        messages.append({
            "update_id": uid,
            "message_id": msg.get("message_id"),
            "chat_id": cid,
            "from": sender_name,
            "date": ts_str,
            "text": text,
        })
    return True, messages[-limit:], "", max_uid


def _tool_read_telegram_messages(args: dict) -> str:
    """AI Agent tool: read recent Telegram messages from the authorized chat."""
    limit = max(1, min(int(args.get("limit", 10) or 10), 30))
    ok, msgs, err, _ = fetch_telegram_messages(limit=limit)
    if not ok:
        return f"[ERROR] Failed to read Telegram messages: {err}"
    if not msgs:
        return "(No recent Telegram messages found for the configured chat_id.)"
    lines = [f"=== RECENT TELEGRAM MESSAGES ({len(msgs)}) ==="]
    for m in msgs:
        lines.append(f"- [{m['date']}] @{m['from']} (chat {m['chat_id']}): {m['text']}")
    return "\n".join(lines)


def _handle_incoming_telegram_message(msg: dict) -> None:
    """Execute one incoming Telegram message via headless AI Agent and reply back."""
    text = str(msg.get("text") or "").strip()
    if not text:
        return
    try:
        from .telua_web_ai import run_ai_agent_headless
        cfg = get_ai_notify_config()
        _send_telegram_message("⏳ [Telua AI] Đã nhận lệnh từ Telegram — đang xử lý…")
        prompt = (
            "[Source: Telegram Remote Command while user is away. "
            "Execute the request concisely using available tools (tasks, tel, code, knowledge) "
            "and summarize the outcome clearly.]\n" + text
        )
        res = run_ai_agent_headless(user_msg=prompt, auto_confirm=False)
        if res.get("ok"):
            ans = str(res.get("answer") or "(empty response)")
            if cfg.get("safe_mode", True):
                reply = f"🤖 [Telua AI]\n{_sanitize_for_safe_mode(ans)}\n(🛡 Safe Mode: code/paths redacted)"
            else:
                reply = f"🤖 [Telua AI]\n{ans[:3500]}"
        else:
            err = str(res.get("error") or "Unknown error")
            reply = (
                "🚨 [Telua AI] Error processing request (🛡 Safe Mode: check Telua Web)."
                if cfg.get("safe_mode", True)
                else f"🚨 [Telua AI Error]\n{err[:1500]}"
            )
        _send_telegram_message(reply)
    except Exception:
        pass


def _telegram_poller_loop() -> None:
    """Background long-polling loop when bot_listen_enabled=True."""
    import time
    while True:
        try:
            cfg = get_ai_notify_config()
            if not (cfg.get("bot_listen_enabled") and cfg.get("bot_token") and cfg.get("chat_id")):
                time.sleep(5)
                continue
            last_uid = int(cfg.get("last_update_id") or 0)
            offset = (last_uid + 1) if last_uid > 0 else None
            ok, msgs, _err, max_uid = fetch_telegram_messages(limit=10, offset=offset, timeout=15)
            if ok and max_uid > last_uid:
                save_ai_notify_config({"last_update_id": max_uid})
                # Only process messages if we already had a baseline (prevents replaying old backlog on first enable)
                if last_uid > 0:
                    for m in msgs:
                        threading.Thread(
                            target=_handle_incoming_telegram_message,
                            args=(m,),
                            daemon=True,
                        ).start()
            elif not ok:
                time.sleep(8)
        except Exception:
            time.sleep(8)


def ensure_telegram_poller_started() -> None:
    global _POLLER_STARTED
    with _POLLER_LOCK:
        if _POLLER_STARTED:
            return
        _POLLER_STARTED = True
        threading.Thread(target=_telegram_poller_loop, name="telua-tg-poller", daemon=True).start()


def fetch_telegram_messages(
    limit: int = 10,
    offset: Optional[int] = None,
    timeout: int = 0,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Tuple[bool, list, str, int]:
    """Read recent incoming messages from Telegram Bot API (getUpdates),
    strictly filtered to the configured authorized `chat_id`.

    Returns: (ok, messages_list, error_msg, max_update_id)
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    cfg = get_ai_notify_config()
    token = (bot_token or "").strip() or str(cfg.get("bot_token") or "").strip()
    allowed_cid = (chat_id or "").strip() or str(cfg.get("chat_id") or "").strip()
    if not token:
        return False, [], "Missing Telegram Bot Token.", 0

    params = {"limit": max(1, min(int(limit or 10), 50))}
    if offset is not None and int(offset) > 0:
        params["offset"] = int(offset)
    if timeout and int(timeout) > 0:
        params["timeout"] = max(1, min(int(timeout), 30))

    url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    http_timeout = (int(timeout) + 8) if timeout else 10
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return False, [], f"HTTP {exc.code}: {err_body or exc.reason}", 0
    except Exception as exc:
        return False, [], str(exc), 0

    if not body.get("ok"):
        return False, [], str(body.get("description") or "Telegram getUpdates failed"), 0

    updates = body.get("result") or []
    messages = []
    max_uid = 0
    for upd in updates:
        uid = int(upd.get("update_id") or 0)
        if uid > max_uid:
            max_uid = uid
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or {}
        if not msg:
            continue
        chat = msg.get("chat") or {}
        cid = str(chat.get("id") or "")
        # Strict allowlist: if chat_id is configured, ignore messages from other chats
        if allowed_cid and cid != allowed_cid:
            continue
        text = str(msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            continue
        sender = msg.get("from") or {}
        sender_name = sender.get("username") or sender.get("first_name") or "user"
        ts_unix = int(msg.get("date") or 0)
        ts_str = datetime.fromtimestamp(ts_unix).strftime("%Y-%m-%d %H:%M:%S") if ts_unix else ""
        messages.append({
            "update_id": uid,
            "message_id": msg.get("message_id"),
            "chat_id": cid,
            "from": sender_name,
            "date": ts_str,
            "text": text,
        })
    return True, messages[-limit:], "", max_uid


def _tool_read_telegram_messages(args: dict) -> str:
    """AI Agent tool: read recent Telegram messages from the authorized chat."""
    limit = max(1, min(int(args.get("limit", 10) or 10), 30))
    ok, msgs, err, _ = fetch_telegram_messages(limit=limit)
    if not ok:
        return f"[ERROR] Failed to read Telegram messages: {err}"
    if not msgs:
        return "(No recent Telegram messages found for the configured chat_id.)"
    lines = [f"=== RECENT TELEGRAM MESSAGES ({len(msgs)}) ==="]
    for m in msgs:
        lines.append(f"- [{m['date']}] @{m['from']} (chat {m['chat_id']}): {m['text']}")
    return "\n".join(lines)


def _handle_incoming_telegram_message(msg: dict) -> None:
    """Execute one incoming Telegram message via headless AI Agent and reply back."""
    text = str(msg.get("text") or "").strip()
    if not text:
        return
    try:
        from .telua_web_ai import run_ai_agent_headless
        cfg = get_ai_notify_config()
        _send_telegram_message("⏳ [Telua AI] Đã nhận lệnh từ Telegram — đang xử lý…")
        prompt = (
            "[Source: Telegram Remote Command while user is away. "
            "Execute the request concisely using available tools (tasks, tel, code, knowledge) "
            "and summarize the outcome clearly.]\n" + text
        )
        res = run_ai_agent_headless(user_msg=prompt, auto_confirm=False)
        if res.get("ok"):
            ans = str(res.get("answer") or "(empty response)")
            if cfg.get("safe_mode", True):
                reply = f"🤖 [Telua AI]\n{_sanitize_for_safe_mode(ans)}\n(🛡 Safe Mode: code/paths redacted)"
            else:
                reply = f"🤖 [Telua AI]\n{ans[:3500]}"
        else:
            err = str(res.get("error") or "Unknown error")
            reply = (
                "🚨 [Telua AI] Error processing request (🛡 Safe Mode: check Telua Web)."
                if cfg.get("safe_mode", True)
                else f"🚨 [Telua AI Error]\n{err[:1500]}"
            )
        _send_telegram_message(reply)
    except Exception:
        pass


def _telegram_poller_loop() -> None:
    """Background long-polling loop when bot_listen_enabled=True."""
    import time
    while True:
        try:
            cfg = get_ai_notify_config()
            if not (cfg.get("bot_listen_enabled") and cfg.get("bot_token") and cfg.get("chat_id")):
                time.sleep(5)
                continue
            last_uid = int(cfg.get("last_update_id") or 0)
            offset = (last_uid + 1) if last_uid > 0 else None
            ok, msgs, _err, max_uid = fetch_telegram_messages(limit=10, offset=offset, timeout=15)
            if ok and max_uid > last_uid:
                save_ai_notify_config({"last_update_id": max_uid})
                # Only process messages if we already had a baseline (prevents replaying old backlog on first enable)
                if last_uid > 0:
                    for m in msgs:
                        threading.Thread(
                            target=_handle_incoming_telegram_message,
                            args=(m,),
                            daemon=True,
                        ).start()
            elif not ok:
                time.sleep(8)
        except Exception:
            time.sleep(8)


def ensure_telegram_poller_started() -> None:
    global _POLLER_STARTED
    with _POLLER_LOCK:
        if _POLLER_STARTED:
            return
        _POLLER_STARTED = True
        threading.Thread(target=_telegram_poller_loop, name="telua-tg-poller", daemon=True).start()


def fetch_telegram_chat_ids(bot_token: Optional[str] = None, limit: int = 30) -> Tuple[bool, dict, str]:
    """Call Telegram getUpdates using submitted or saved bot_token and return
    both extracted unique chats and the raw JSON response for inspection.

    Returns: (ok, {"chats": [...], "raw": body}, error_msg)
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    cfg = get_ai_notify_config()
    token = (bot_token or "").strip() or str(cfg.get("bot_token") or "").strip()
    if not token:
        return False, {}, "Missing Telegram Bot Token. Paste your Bot Token first."

    params = {"limit": max(1, min(int(limit or 30), 100))}
    url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        return False, {}, f"HTTP {exc.code}: {err_body or exc.reason}"
    except Exception as exc:
        return False, {}, str(exc)

    if not body.get("ok"):
        return False, {"raw": body}, str(body.get("description") or "Telegram getUpdates failed")

    chats_map = {}
    for upd in (body.get("result") or []):
        msg = (
            upd.get("message")
            or upd.get("edited_message")
            or upd.get("channel_post")
            or (upd.get("callback_query") or {}).get("message")
            or {}
        )
        chat = msg.get("chat") or (upd.get("my_chat_member") or {}).get("chat") or {}
        cid = str(chat.get("id") or "").strip()
        if not cid:
            continue
        first = str(chat.get("first_name") or "").strip()
        last = str(chat.get("last_name") or "").strip()
        full_name = f"{first} {last}".strip()
        title = str(chat.get("title") or full_name or chat.get("username") or cid).strip()
        username = str(chat.get("username") or "").strip()
        text = str(msg.get("text") or msg.get("caption") or "").strip()
        chats_map[cid] = {
            "chat_id": cid,
            "type": str(chat.get("type") or ""),
            "title": title,
            "username": username,
            "last_text": text[:80],
        }

    # Most recently seen chat first
    chats = list(reversed(list(chats_map.values())))
    return True, {"chats": chats, "raw": body}, ""


