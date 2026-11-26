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
# telua_web_ai.py — AI Agent blueprint for the Telua Web UI ('tel ai')
#
# A minimal tool-calling agent loop: the LLM decides which tel/adb/file tools
# to invoke, the backend executes them and feeds results back until the model
# produces a final answer. Supports Anthropic (Claude) and OpenAI-compatible
# endpoints (OpenAI, local Ollama/vLLM via base_url).
#
# API key resolution order:
#   1. Environment variable  TELUA_AI_API_KEY (or ANTHROPIC_API_KEY /
#      OPENAI_API_KEY depending on provider)
#   2. Decrypted via python/config_crypto.py from config/overlay/ (tel crypto)
# ==============================================================================

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request

ai_bp = Blueprint("ai", __name__)

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

AI_CONFIG_FILE_CANDIDATES = [
    "config/overlay/const_ai.config",
    "config/const_ai.config",
]

# JSON provider config (same shape as VS Code Copilot custom endpoints):
# [
#   {
#     "name": "DeepSeek (litellm)",
#     "vendor": "customendpoint",
#     "apiKey": "...",
#     "apiType": "chat-completions",
#     "models": [
#       { "id": "esc/glm-5.3-flash", "name": "litellm/esc/glm-5.3-flash",
#         "url": "https://.../v1/chat/completions", "url1": "http://.../v1/chat/completions",
#         "toolCalling": true }
#     ]
#   }
# ]
AI_PROVIDERS_JSON_CANDIDATES = [
    "config/overlay/ai_providers.json",
    "config/ai_providers.json",
]

AI_PROVIDERS_TEMPLATE_CANDIDATES = [
    "config/overlay/ai_providers.template.json",
    "config/ai_providers.template.json",
]

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_ITERATIONS = 8
DEFAULT_MAX_TOOL_OUTPUT = 8000  # chars per tool result fed back to the LLM

# Commands the agent may NOT run (destructive / dangerous guard rail).
BLOCKED_CMD_PATTERNS = [
    r"\brm\s+-rf\s+/(?!tmp|data/local/tmp)",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\{.*\};:",           # fork bomb
    r"\bflash\b.*\bbootloader\b",
    r"\bfastboot\s+flash\b",
    r"\bgit\s+push\s+.*--force\b",
    r"\bsudo\b",
    r"\bshutdown\b",
    r"\breboot\b(?!.*adb)",     # plain host reboot blocked; adb reboot allowed
]

SYSTEM_PROMPT = """You are Telua AI, an expert AOSP / Android Automotive build & debug agent \
integrated into the 'tel' (telua) toolkit.

You help developers with: building AOSP modules, deploying APKs to boards, reading
logcat, dumpsys diagnostics, git/repo operations and analyzing source code.

Rules:
- Prefer the provided tools over guessing. Use run_tel for tel/telua/shell commands.
- Keep commands short and read-only first (status, logs) before mutating anything.
- Never run destructive commands (flash, rm -rf /, force push) — they are blocked.
- When you have enough information, answer concisely with a clear conclusion and
  the exact commands the user can re-run themselves.
- ALWAYS respond in English, regardless of the language the user writes in
  (Vietnamese, Japanese, etc.). Keep technical terms and command output as-is.
"""


def _ai_providers_json_path() -> Optional[Path]:
    root = Path(__file__).resolve().parent.parent
    for cand in AI_PROVIDERS_JSON_CANDIDATES:
        path = root / cand
        if path.is_file():
            return path
    return None


def _read_providers_json() -> list:
    """Read the JSON provider registry (list of provider dicts)."""
    path = _ai_providers_json_path()
    if not path:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_providers_json(providers: list) -> None:
    path = _ai_providers_json_path() or (
        Path(__file__).resolve().parent.parent / "config" / "ai_providers.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(providers, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_template_json() -> list:
    """Read default provider templates from file."""
    root = Path(__file__).resolve().parent.parent
    for cand in AI_PROVIDERS_TEMPLATE_CANDIDATES:
        path = root / cand
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
    return []


def _active_provider_entry(providers: list, active_name: str = "") -> Optional[dict]:
    if not providers:
        return None
    if active_name:
        for p in providers:
            if p.get("name") == active_name:
                return p
    return providers[0]


def _active_model_entry(provider_entry: dict, active_model_id: str = "") -> Optional[dict]:
    models = provider_entry.get("models") or []
    if not models:
        return None
    if active_model_id:
        for m in models:
            if m.get("id") == active_model_id:
                return m
    return models[0]


def _read_ai_config() -> dict:
    """Read optional config/overlay/const_ai.config (KEY=VALUE lines)."""
    root = Path(__file__).resolve().parent.parent
    for cand in AI_CONFIG_FILE_CANDIDATES:
        path = root / cand
        if path.is_file():
            cfg = {}
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    cfg[key.strip()] = val.strip().strip('"').strip("'")
            except Exception:
                pass
            return cfg
    return {}


def _resolve_api_key(provider: str) -> str:
    env_names = {
        "anthropic": ["TELUA_AI_API_KEY", "ANTHROPIC_API_KEY"],
        "openai": ["TELUA_AI_API_KEY", "OPENAI_API_KEY"],
    }
    for name in env_names.get(provider, ["TELUA_AI_API_KEY"]):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    cfg = _read_ai_config()
    return cfg.get("api_key", "")


def _ai_settings():
    cfg = _read_ai_config()
    provider = (cfg.get("provider") or os.environ.get("TELUA_AI_PROVIDER") or DEFAULT_PROVIDER).lower()
    model = cfg.get("model") or os.environ.get("TELUA_AI_MODEL") or (
        DEFAULT_MODEL if provider == "anthropic" else "gpt-4o-mini")
    base_url = cfg.get("base_url") or os.environ.get("TELUA_AI_BASE_URL") or ""
    try:
        max_iter = int(cfg.get("max_iterations", DEFAULT_MAX_ITERATIONS))
    except ValueError:
        max_iter = DEFAULT_MAX_ITERATIONS
    active_name = cfg.get("active_provider", "")
    active_model = cfg.get("active_model", "")
    return provider, model, base_url, max(1, min(max_iter, 20)), active_name, active_model


# ------------------------------------------------------------------------------
# Tool registry — the agent's "hands". Reuses tel's own capabilities.
# ------------------------------------------------------------------------------

def _cmd_is_blocked(cmd: str) -> Optional[str]:
    for pattern in BLOCKED_CMD_PATTERNS:
        if re.search(pattern, cmd):
            return pattern
    return None


def _tool_run_tel(args: dict) -> str:
    cmd = str(args.get("cmd", "")).strip()
    if not cmd:
        return "[ERROR] empty command"
    blocked = _cmd_is_blocked(cmd)
    if blocked:
        return f"[BLOCKED] command matches safety rule '{blocked}' and was not executed."
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True, errors="replace", timeout=300,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return out[:DEFAULT_MAX_TOOL_OUTPUT] or f"(exit code {proc.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return "[ERROR] command timed out after 300s"
    except Exception as exc:
        return f"[ERROR] {exc}"


def _tool_read_file(args: dict) -> str:
    root = Path(__file__).resolve().parent.parent
    rel = str(args.get("path", "")).strip().lstrip("/")
    if not rel:
        return "[ERROR] missing 'path'"
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return "[ERROR] path outside toolkit root is not allowed"
    if not path.is_file():
        return f"[ERROR] file not found: {rel}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[ERROR] {exc}"
    if len(text) > DEFAULT_MAX_TOOL_OUTPUT:
        return text[:DEFAULT_MAX_TOOL_OUTPUT] + f"\n...[truncated, {len(text)} chars total]"
    return text or "(empty file)"


def _tool_list_files(args: dict) -> str:
    root = Path(__file__).resolve().parent.parent
    rel = str(args.get("path", "")).strip().lstrip("/") or "."
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return "[ERROR] path outside toolkit root is not allowed"
    if not path.is_dir():
        return f"[ERROR] not a directory: {rel}"
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = []
        for entry in entries[:200]:
            lines.append(("[D] " if entry.is_dir() else "[F] ") + entry.name)
        return "\n".join(lines) or "(empty directory)"
    except Exception as exc:
        return f"[ERROR] {exc}"


TOOL_EXECUTORS = {
    "run_tel": _tool_run_tel,
    "read_file": _tool_read_file,
    "list_files": _tool_list_files,
}

# OpenAI-style tool schemas (also converted for Anthropic).
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run_tel",
            "description": "Run a shell / tel / telua / adb command in the toolkit root "
                           "(e.g. 'tel build', 'tel dump battery', 'adb devices', 'git status').",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string", "description": "The command line to run"}},
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file inside the toolkit workspace (config, source, logs).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative path, e.g. config/apk.config"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List a directory inside the toolkit workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative directory path"}},
                "required": ["path"],
            },
        },
    },
]


# ------------------------------------------------------------------------------
# Provider adapters
# ------------------------------------------------------------------------------

def _call_anthropic(messages, model, base_url):
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Python package 'anthropic' is not installed. Run: pip install anthropic")
    api_key = _resolve_api_key("anthropic")
    if not api_key:
        raise RuntimeError("No API key. Set TELUA_AI_API_KEY / ANTHROPIC_API_KEY "
                           "or add api_key=... to config/overlay/const_ai.config")
    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
    client = anthropic.Anthropic(api_key=api_key, **kwargs)

    converted = []
    for msg in messages:
        if msg["role"] == "tool":
            converted.append({
                "role": "user",
                "content": [{"type": "tool_result",
                             "tool_use_id": msg["tool_call_id"],
                             "content": msg["content"]}],
            })
        else:
            converted.append(msg)

    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=converted,
        tools=[{
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "input_schema": t["function"]["parameters"],
        } for t in TOOL_SCHEMAS],
    )

    text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    tool_calls = [{
        "id": b.id,
        "name": b.name,
        "arguments": json.dumps(b.input or {}),
    } for b in resp.content if getattr(b, "type", "") == "tool_use"]

    return {
        "text": "\n".join(text_parts).strip(),
        "tool_calls": tool_calls,
        "raw_assistant_message": {
            "role": "assistant",
            "content": [{"type": getattr(b, "type", "text"),
                         **({"text": b.text} if getattr(b, "type", "") == "text" else {}),
                         **({"id": b.id, "name": b.name, "input": b.input}
                            if getattr(b, "type", "") == "tool_use" else {})}
                        for b in resp.content],
        },
    }


def _call_openai(messages, model, base_url):
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("Python package 'openai' is not installed. Run: pip install openai")
    api_key = _resolve_api_key("openai") or "sk-no-key"
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)

    converted = []
    for msg in messages:
        if msg["role"] == "tool":
            converted.append({"role": "tool", "tool_call_id": msg["tool_call_id"], "content": msg["content"]})
        elif msg["role"] == "assistant" and msg.get("tool_calls"):
            converted_tc = []
            for tc in msg["tool_calls"]:
                tc_item = {
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name") if isinstance(tc.get("function"), dict) else tc.get("name"),
                        "arguments": tc.get("function", {}).get("arguments") if isinstance(tc.get("function"), dict) else tc.get("arguments", "{}"),
                    },
                }
                if tc.get("extra_content"):
                    tc_item["extra_content"] = tc["extra_content"]
                converted_tc.append(tc_item)

            ast_msg = {
                "role": "assistant",
                "content": msg.get("content") or None,
                "tool_calls": converted_tc,
            }
            if msg.get("extra_content"):
                ast_msg["extra_content"] = msg["extra_content"]
            converted.append(ast_msg)
        else:
            converted.append({"role": msg["role"], "content": msg["content"]})

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + converted,
        tools=TOOL_SCHEMAS,
    )
    choice = resp.choices[0]
    msg = choice.message
    tool_calls = [{
        "id": tc.id,
        "name": tc.function.name,
        "arguments": tc.function.arguments or "{}",
    } for tc in (msg.tool_calls or [])]

    raw = {"role": "assistant", "content": msg.content or ""}
    if tool_calls:
        raw["tool_calls"] = [{"id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
                             for tc in tool_calls]
    return {
        "text": (msg.content or "").strip(),
        "tool_calls": tool_calls,
        "raw_assistant_message": raw,
    }


def _call_llm(messages, provider, model, base_url):
    # JSON provider registry takes precedence (custom endpoints, e.g. Bosch
    # internal litellm / EMC AI gateways using the chat-completions API).
    providers = _read_providers_json()
    if providers:
        cfg = _read_ai_config()
        entry = _active_provider_entry(providers, cfg.get("active_provider", ""))
        model_entry = _active_model_entry(entry or {}, cfg.get("active_model", ""))
        if entry and model_entry:
            res = _call_chat_completions(messages, entry, model_entry)
            res["model"] = model_entry.get("id") or model_entry.get("name")
            res["provider"] = entry.get("name")
            return res
    if provider == "openai":
        return _call_openai(messages, model, base_url)
    return _call_anthropic(messages, model, base_url)


def _call_chat_completions(messages, provider_entry, model_entry):
    """Generic OpenAI chat-completions call for custom endpoints.

    Tries each URL defined on the model entry in order (url, url1, ...) —
    useful when an internal gateway has multiple mirrors (VPN vs LAN).
    """
    urls = [model_entry.get(k) for k in ("url", "url1", "url2") if model_entry.get(k)]
    if not urls:
        raise RuntimeError(f"Provider '{provider_entry.get('name')}' model has no url")
    api_key = provider_entry.get("apiKey") or ""
    # Expand ${input:...} style secret placeholders from environment.
    m = re.match(r"\$\{input:([^}]+)\}", api_key)
    if m:
        api_key = os.environ.get(m.group(1), "")
    model_id = model_entry.get("id") or model_entry.get("name")

    converted = []
    for msg in messages:
        if msg["role"] == "tool":
            converted.append({"role": "tool", "tool_call_id": msg["tool_call_id"], "content": msg["content"]})
        elif msg["role"] == "assistant" and msg.get("tool_calls"):
            converted_tc = []
            for tc in msg["tool_calls"]:
                tc_item = {
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name") if isinstance(tc.get("function"), dict) else tc.get("name"),
                        "arguments": tc.get("function", {}).get("arguments") if isinstance(tc.get("function"), dict) else tc.get("arguments", "{}"),
                    },
                }
                if tc.get("extra_content"):
                    tc_item["extra_content"] = tc["extra_content"]
                converted_tc.append(tc_item)

            ast_msg = {
                "role": "assistant",
                "content": msg.get("content") or None,
                "tool_calls": converted_tc,
            }
            if msg.get("extra_content"):
                ast_msg["extra_content"] = msg["extra_content"]
            converted.append(ast_msg)
        else:
            converted.append({"role": msg["role"], "content": msg["content"]})

    payload = {
        "model": model_id,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + converted,
        "tools": TOOL_SCHEMAS,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    import urllib.request
    import urllib.error
    last_err = None
    for url in urls:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            err_detail = str(exc)
            if hasattr(exc, "read"):
                try:
                    raw_body = exc.read().decode("utf-8", errors="replace")
                    err_json = json.loads(raw_body)
                    if isinstance(err_json, dict) and "error" in err_json:
                        err_obj = err_json["error"]
                        if isinstance(err_obj, dict) and "message" in err_obj:
                            err_detail = f"{getattr(exc, 'code', 'HTTP Error')}: {err_obj['message']}"
                        elif isinstance(err_obj, str):
                            err_detail = f"{getattr(exc, 'code', 'HTTP Error')}: {err_obj}"
                    elif isinstance(err_json, list) and len(err_json) > 0 and "error" in err_json[0]:
                        err_detail = f"{getattr(exc, 'code', 'HTTP Error')}: {err_json[0]['error'].get('message', str(exc))}"
                except Exception:
                    pass
            last_err = err_detail
            continue
    else:
        raise RuntimeError(f"All endpoints failed for {model_id}: {last_err}")

    msg = (data.get("choices") or [{}])[0].get("message") or {}
    tool_calls = [{
        "id": tc.get("id", f"call_{i}"),
        "name": tc.get("function", {}).get("name", ""),
        "arguments": tc.get("function", {}).get("arguments") or "{}",
        **({"extra_content": tc["extra_content"]} if tc.get("extra_content") else {})
    } for i, tc in enumerate(msg.get("tool_calls") or [])]

    raw = {"role": "assistant", "content": msg.get("content") or ""}
    if tool_calls:
        raw["tool_calls"] = tool_calls
    if msg.get("extra_content"):
        raw["extra_content"] = msg["extra_content"]
    return {
        "text": (msg.get("content") or "").strip(),
        "tool_calls": tool_calls,
        "raw_assistant_message": raw,
    }


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@ai_bp.get("/api/ai/status")
def api_ai_status():
    provider, model, base_url, max_iter, active_name, active_model = _ai_settings()
    providers = _read_providers_json()
    entry = _active_provider_entry(providers, active_name)
    model_entry = _active_model_entry(entry or {}, active_model)
    if entry and model_entry:
        provider = entry.get("name", provider)
        model = model_entry.get("id") or model_entry.get("name") or model
        has_key = bool(entry.get("apiKey"))
        sdk = "builtin"  # chat-completions uses urllib, no SDK needed
    else:
        has_key = bool(_resolve_api_key(provider))
        try:
            import importlib
            sdk = "ok" if importlib.import_module(
                "anthropic" if provider == "anthropic" else "openai") else "missing"
        except ImportError:
            sdk = "missing"
    return jsonify({
        "ok": True,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "max_iterations": max_iter,
        "has_api_key": has_key,
        "sdk_installed": sdk,
        "tools": [t["function"]["name"] for t in TOOL_SCHEMAS],
        "providers": [{
            "name": p.get("name", ""),
            "apiType": p.get("apiType", ""),
            "has_key": bool(p.get("apiKey")),
            "models": [{
                "id": m.get("id", ""),
                "name": m.get("name", ""),
                "url": m.get("url", ""),
                "toolCalling": bool(m.get("toolCalling")),
            } for m in (p.get("models") or [])],
        } for p in providers],
        "active_provider": (entry or {}).get("name", ""),
        "active_model": (model_entry or {}).get("id", ""),
    })


@ai_bp.get("/api/ai/config")
def api_ai_config_get():
    """Return the RAW provider registry JSON (including apiKey field so the
    settings dialog can round-trip the file without wiping stored keys)."""
    return jsonify({"ok": True, "providers": _read_providers_json()})


@ai_bp.get("/api/ai/template")
def api_ai_template():
    """Return standard provider templates loaded from configuration file."""
    tpl = _read_template_json()
    return jsonify({"ok": True, "template": tpl, "count": len(tpl)})


@ai_bp.post("/api/ai/config")
def api_ai_config():
    """Save the AI provider config from the Web UI settings dialog.

    Accepts the full provider registry JSON (same shape as VS Code Copilot
    custom endpoints) plus optional activeProvider/activeModel selection.
    The file is stored at config/ai_providers.json (or the overlay path if it
    already exists there).
    """
    data = request.get_json(silent=True) or {}
    providers = data.get("providers")
    if not isinstance(providers, list):
        return jsonify({"ok": False, "error": "Missing 'providers' list."}), 400
    # Basic sanity validation
    for p in providers:
        if not isinstance(p, dict) or not p.get("name"):
            return jsonify({"ok": False, "error": "Each provider needs a 'name'."}), 400
        for m in p.get("models") or []:
            if not isinstance(m, dict) or not (m.get("id") or m.get("name")):
                return jsonify({"ok": False,
                                "error": f"Provider '{p.get('name')}' has a model without 'id'."}), 400

    # Preserve stored apiKey when the submitted JSON omits it (the Web UI
    # never displays keys, so an edited JSON may arrive without them).
    existing = {p.get("name"): p for p in _read_providers_json() if isinstance(p, dict)}
    for p in providers:
        if not p.get("apiKey"):
            prev = existing.get(p.get("name")) or {}
            if prev.get("apiKey"):
                p["apiKey"] = prev["apiKey"]
    try:
        _write_providers_json(providers)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Failed to save config: {exc}"}), 500

    # Optionally persist active selection into const_ai.config overlay
    active_provider = str(data.get("activeProvider", "")).strip()
    active_model = str(data.get("activeModel", "")).strip()
    if active_provider or active_model:
        root = Path(__file__).resolve().parent.parent
        cfg_path = root / "config" / "overlay" / "const_ai.config"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if cfg_path.is_file():
            lines = [l for l in cfg_path.read_text(encoding="utf-8", errors="replace").splitlines()
                     if not l.strip().startswith(("active_provider=", "active_model="))]
        if active_provider:
            lines.append(f"active_provider={active_provider}")
        if active_model:
            lines.append(f"active_model={active_model}")
        cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return jsonify({"ok": True, "saved": len(providers),
                    "path": str(_ai_providers_json_path() or "config/ai_providers.json")})


@ai_bp.post("/api/ai/key")
def api_ai_key():
    """Set (or clear with empty string) the API key of one provider by name."""
    data = request.get_json(silent=True) or {}
    name = str(data.get("provider", "")).strip()
    key = str(data.get("apiKey", ""))
    if not name:
        return jsonify({"ok": False, "error": "Missing 'provider'."}), 400
    providers = _read_providers_json()
    entry = _active_provider_entry(providers, name)
    if not entry:
        return jsonify({"ok": False, "error": f"Provider '{name}' not found."}), 404
    entry["apiKey"] = key  # empty string clears the key
    try:
        _write_providers_json(providers)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Failed to save key: {exc}"}), 500
    return jsonify({"ok": True, "provider": name, "has_key": bool(key)})


@ai_bp.post("/api/ai/chat")
def api_ai_chat():
    """Run the agent loop for one user message. Returns the final answer plus a
    trace of every tool call so the Web UI can display what the agent did."""
    data = request.get_json(silent=True) or {}
    user_msg = str(data.get("message", "")).strip()
    history = data.get("history") or []
    if not user_msg:
        return jsonify({"ok": False, "error": "Missing 'message'."}), 400

    provider, model, base_url, max_iter, _active_name, _active_model = _ai_settings()

    messages = []
    for h in history[-10:]:
        role = h.get("role")
        content = str(h.get("content", ""))[:4000]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_msg})

    trace = []
    try:
        for _ in range(max_iter):
            resp = _call_llm(messages, provider, model, base_url)

            if not resp["tool_calls"]:
                return jsonify({
                    "ok": True,
                    "answer": resp["text"] or "(empty response)",
                    "trace": trace,
                    "model": resp.get("model", model),
                    "provider": resp.get("provider", provider),
                })

            # Record assistant tool-call message and execute each tool.
            messages.append(resp["raw_assistant_message"])
            for tc in resp["tool_calls"]:
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = TOOL_EXECUTORS.get(tc["name"], lambda a: "[ERROR] unknown tool")(args)
                trace.append({
                    "tool": tc["name"],
                    "args": args,
                    "output": result[:2000],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        return jsonify({
            "ok": True,
            "answer": "⏹ Dừng sau " + str(max_iter) + " bước agent (max iterations). "
                      "Kết quả trung gian xem ở phần trace.",
            "trace": trace,
            "model": model,
            "provider": provider,
        })
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc), "trace": trace}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"ok": False, "error": f"Agent error: {exc}", "trace": trace}), 500
