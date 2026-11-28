#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# llm_providers.py — LLM Provider registry, Guardrails, & HTTP/SDK adapters
# (Anthropic Claude, OpenAI, Custom OpenAI-compatible gateways)
# ==============================================================================

import json
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .ai_config_paths import (
    candidates as _ai_cfg_candidates,
    overlay_file as _ai_overlay_file,
    shared_file as _ai_shared_file,
)


def _get_tool_schemas():
    from .agent_tools import TOOL_SCHEMAS
    return TOOL_SCHEMAS


# ------------------------------------------------------------------------------

AI_CONFIG_FILE_CANDIDATES = _ai_cfg_candidates("const_ai.config")

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
AI_PROVIDERS_JSON_CANDIDATES = _ai_cfg_candidates("ai_providers.json")

AI_PROVIDERS_TEMPLATE_CANDIDATES = _ai_cfg_candidates("ai_providers.template.json")

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_MAX_TOOL_OUTPUT = 6000  # chars per tool result fed back to the LLM

DEFAULT_GUARDRAILS = {
    "max_iterations": 5,
    "max_lines_per_read": 150,
    "max_tool_output_chars": 6000,
    "loop_breaker_enabled": True,
}

AI_GUARDRAILS_CANDIDATES = _ai_cfg_candidates("ai_guardrails.json")


def _ai_guardrails_path() -> Path:
    root = _repo_root()
    for cand in AI_GUARDRAILS_CANDIDATES:
        p = root / cand
        if p.is_file():
            return p
    return _ai_overlay_file("ai_guardrails.json")


def get_ai_guardrails() -> dict:
    """Read token guardrails & loop prevention configuration."""
    cfg = dict(DEFAULT_GUARDRAILS)
    p = _ai_guardrails_path()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    return cfg


def save_ai_guardrails(data: dict) -> dict:
    """Save token guardrails to overlay file."""
    cfg = get_ai_guardrails()
    for k in DEFAULT_GUARDRAILS:
        if k in data:
            if isinstance(DEFAULT_GUARDRAILS[k], bool):
                cfg[k] = bool(data[k])
            elif isinstance(DEFAULT_GUARDRAILS[k], int):
                try:
                    cfg[k] = int(data[k])
                except (ValueError, TypeError):
                    pass
    p = _ai_overlay_file("ai_guardrails.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


SYSTEM_PROMPT = """You are Telua AI, an expert AOSP / Android Automotive build & debug agent \
integrated into the 'tel' (telua) toolkit.

You help developers with: building AOSP modules, deploying APKs to boards, reading
logcat, dumpsys diagnostics, git/repo operations, analyzing source code, and autonomous coding.

Rules:
- Prefer the provided tools over guessing. Use run_tel for tel/telua/shell commands.
- For exact `tel`/`telua` CLI syntax, subcommands, and non-interactive flags (`-y`), consult `AI.md` via `grep_search(query, path="AI.md")` or `search_knowledge` instead of guessing flags.
- Before running `tel b` (build) or `tel t` (test), always `cd` into the target project directory (Target Path folder, or `AOSP_ROOT_DIR/<SOURCE_PATH>`) — or pass `cwd` to `run_tel`.
- Use search_knowledge to query local persistent ChromaDB documentation and training data.
- Use save_training_knowledge to persist verified solutions or architectural notes for long-term recall.
- You can create, write, and edit code files directly using write_file and edit_file.
- Use grep_search to quickly find symbol definitions, callers, strings, or regex matches across files and directories before reading full files.
- Use get_aosp_project_info to inspect the active AOSP tab configuration (ACTIVE_PROJECT, AOSP_ROOT_DIR, lunch target, module name, source path, deploy path, and build/deploy commands) before running `tel build` / `tel deploy` / `tel logcat`.
- For Sphinx documentation (`.rst`, `.puml`, `.mmd`, `metadata.json` in `Active_Docs_Dir`): treat docs as READ-ONLY reference context — consult existing docs via search_knowledge, grep_search, or read_file before coding, and NEVER modify or overwrite `.rst` documentation files automatically unless the user explicitly instructs you to update docs.
- Use get_file_git_history to inspect commit history (hash, author, date, message) of a specific file.
- Use get_commit_diff to inspect lines added/removed in a specific commit when investigating regressions, bug causes, or historical changes.
- When a bug, crash, or regression is discovered during inspection or build, use create_github_issue to report an issue with stack traces and AST context.
- When code fixes or features are completed and verified, use create_git_fix_branch to commit changes and push a fix branch to remote for review. Never push directly to main.
- When inspecting or debugging source code files (> 150 lines):
  1. Call read_file with outline=True first to see classes, methods, and line ranges without token bloat.
  2. Call read_file with method="<name>" to read the exact complete function body with class context.
  3. Or use read_file with start_line and end_line; the tool automatically snaps boundaries to the closing brace so functions are never chopped in half.
- When a target file is specified, read it first with read_file (if it exists), consult relevant MCP skills (get_telua_skill or search_knowledge), write or edit the code directly with write_file or edit_file, and run verification commands via run_tel (e.g. 'tel build' or compilation checks).
- Keep commands short and read-only first (status, logs) before mutating anything.
- Never run destructive commands (flash, rm -rf /, force push) — they are blocked.
- When you have enough information, answer concisely with a clear conclusion and
  the exact commands the user can re-run themselves.
- ALWAYS respond in English, regardless of the language the user writes in
  (Vietnamese, Japanese, etc.). Keep technical terms and command output as-is.
"""


def _repo_root() -> Path:
    """Return repository root: web/ai/telua_web_ai.py -> repo root."""
    return Path(__file__).resolve().parent.parent.parent



def _ai_providers_json_path() -> Optional[Path]:
    root = _repo_root()
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
    """Write provider configuration.
    
    If any provider has an active apiKey, ALWAYS writes to config/overlay/ai_agent/ai_providers.json
    (which is git-ignored) to guarantee zero API key leakage into tracked public Git files.
    """
    has_any_key = any(bool(p.get("apiKey")) for p in providers if isinstance(p, dict))
    overlay_path = _ai_overlay_file("ai_providers.json")
    if has_any_key or overlay_path.is_file():
        path = overlay_path
    else:
        path = _ai_providers_json_path() or _ai_shared_file("ai_providers.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(providers, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_template_json() -> list:
    """Read default provider templates from file."""
    root = _repo_root()
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
    """Read optional config/overlay/ai_agent/const_ai.config (KEY=VALUE lines)."""
    root = _repo_root()
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
    guardrails = get_ai_guardrails()
    max_iter = max(1, min(int(guardrails.get("max_iterations", DEFAULT_MAX_ITERATIONS)), 1024))
    active_name = cfg.get("active_provider", "")
    active_model = cfg.get("active_model", "")
    return provider, model, base_url, max_iter, active_name, active_model



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
                           "or add api_key=... to config/overlay/ai_agent/const_ai.config")
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
        } for t in _get_tool_schemas()],
    )

    text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    tool_calls = [{
        "id": b.id,
        "name": b.name,
        "arguments": json.dumps(b.input or {}),
    } for b in resp.content if getattr(b, "type", "") == "tool_use"]

    usage_data = getattr(resp, "usage", None)
    input_tokens = int(getattr(usage_data, "input_tokens", 0) if usage_data else 0)
    output_tokens = int(getattr(usage_data, "output_tokens", 0) if usage_data else 0)

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
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
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
        tools=_get_tool_schemas(),
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

    usage_data = getattr(resp, "usage", None)
    pt = int(getattr(usage_data, "prompt_tokens", 0) if usage_data else 0)
    ct = int(getattr(usage_data, "completion_tokens", 0) if usage_data else 0)

    return {
        "text": (msg.content or "").strip(),
        "tool_calls": tool_calls,
        "raw_assistant_message": raw,
        "usage": {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
        },
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
            api_type = str(entry.get("apiType") or "").strip().lower()
            primary_url = str(model_entry.get("url") or "").strip().lower()
            if api_type == "anthropic" or primary_url.endswith("/v1/messages"):
                res = _call_anthropic_http(messages, entry, model_entry)
            else:
                res = _call_chat_completions(messages, entry, model_entry)
            res["model"] = model_entry.get("id") or model_entry.get("name")
            res["provider"] = entry.get("name")
            return res
    if provider == "openai":
        return _call_openai(messages, model, base_url)
    return _call_anthropic(messages, model, base_url)


def _call_anthropic_http(messages, provider_entry, model_entry):
    """Direct Anthropic Messages API call via urllib (zero external SDK required).

    Supports Claude Sonnet / Opus with full tool_use & tool_result multi-turn loops.
    """
    urls = [model_entry.get(k) for k in ("url", "url1", "url2") if model_entry.get(k)]
    if not urls:
        urls = ["https://api.anthropic.com/v1/messages"]
    api_key = provider_entry.get("apiKey") or ""
    m = re.match(r"\$\{input:([^}]+)\}", api_key)
    if m:
        api_key = os.environ.get(m.group(1), "")
    if not api_key:
        api_key = _resolve_api_key("anthropic")
    if not api_key:
        raise RuntimeError(
            "Missing Anthropic API key. Paste your key in ⚙ Config -> API Key & Provider, "
            "or set ANTHROPIC_API_KEY / TELUA_AI_API_KEY."
        )
    model_id = model_entry.get("id") or model_entry.get("name") or "claude-sonnet-4-5-20250929"

    # Convert OpenAI-style tool schemas -> Anthropic tools format
    anthropic_tools = [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "input_schema": t["function"]["parameters"],
        }
        for t in _get_tool_schemas()
    ]

    # Convert message history -> Anthropic Messages format (group consecutive tool results into one user turn)
    converted = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id") or "",
                "content": str(msg.get("content") or ""),
            }
            if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
                converted[-1]["content"].append(block)
            else:
                converted.append({"role": "user", "content": [block]})
        elif role == "assistant" and msg.get("tool_calls"):
            blocks = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": str(msg["content"])})
            for tc in msg["tool_calls"]:
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                name = fn.get("name") or tc.get("name") or ""
                raw_args = fn.get("arguments") if fn else tc.get("arguments", "{}")
                try:
                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    parsed_args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id") or f"toolu_{len(blocks)}",
                    "name": name,
                    "input": parsed_args,
                })
            converted.append({"role": "assistant", "content": blocks})
        else:
            converted.append({"role": role if role in ("user", "assistant") else "user", "content": str(msg.get("content") or "")})

    payload = {
        "model": model_id,
        "max_tokens": int(model_entry.get("max_tokens") or 8192),
        "system": SYSTEM_PROMPT,
        "tools": anthropic_tools,
        "messages": converted,
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    import urllib.request
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
                    if isinstance(err_json, dict) and isinstance(err_json.get("error"), dict):
                        err_detail = f"{getattr(exc, 'code', 'HTTP Error')}: {err_json['error'].get('message', raw_body)}"
                except Exception:
                    pass
            last_err = err_detail
            continue
    else:
        raise RuntimeError(f"Anthropic endpoint failed for {model_id}: {last_err}")

    text_parts = []
    tool_calls = []
    for block in (data.get("content") or []):
        btype = block.get("type")
        if btype == "text" and block.get("text"):
            text_parts.append(block["text"])
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", f"toolu_{len(tool_calls)}"),
                "name": block.get("name", ""),
                "arguments": json.dumps(block.get("input") or {}),
            })

    text = "\n".join(text_parts).strip()
    raw_msg = {"role": "assistant", "content": text}
    if tool_calls:
        raw_msg["tool_calls"] = [
            {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
            for tc in tool_calls
        ]

    u = data.get("usage") or {}
    return {
        "text": text,
        "tool_calls": tool_calls,
        "raw_assistant_message": raw_msg,
        "usage": {
            "prompt_tokens": int(u.get("input_tokens") or 0),
            "completion_tokens": int(u.get("output_tokens") or 0),
        },
    }


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
        "tools": _get_tool_schemas(),
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

    u = data.get("usage") or {}
    pt = int(u.get("prompt_tokens") or 0)
    ct = int(u.get("completion_tokens") or 0)
    if pt == 0 and ct == 0:
        pt = max(1, sum(len(str(m.get("content", ""))) for m in messages) // 4)
        ct = max(1, len(str(msg.get("content", ""))) // 4)

    return {
        "text": (msg.get("content") or "").strip(),
        "tool_calls": tool_calls,
        "raw_assistant_message": raw,
        "usage": {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
        },
    }


# ------------------------------------------------------------------------------
