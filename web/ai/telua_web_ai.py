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
# telua_web_ai.py — Flask Blueprint & Agent loop for Telua Web UI ('tel ai')
#
# Modular architecture:
#   - web/ai/llm_providers.py      : Provider registry, guardrails & LLM adapters
#   - web/ai/agent_tools.py        : Tool executors, schemas & staged write approvals
#   - web/ai/ai_notify.py          : Telegram notification config & async alerts
#   - web/ai/telua_web_tasks.py    : Task Manager (active.json + YYYY/YYYY-MM.json)
#   - web/ai/telua_web_schedule.py : Scheduled background AI triggers
# ==============================================================================

import io
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from .ai_config_paths import (
    candidates as _ai_cfg_candidates,
    overlay_file as _ai_overlay_file,
    shared_file as _ai_shared_file,
)
from .ai_notify import (  # noqa: F401
    _DEFAULT_NOTIFY_CFG,
    _NOTIFY_LOCK,
    _mask_secret,
    _notify_cfg_file,
    _notify_telegram_async,
    _send_telegram_message,
    _tool_read_telegram_messages,
    _tool_send_telegram_notify,
    ensure_telegram_poller_started,
    fetch_telegram_chat_ids,
    fetch_telegram_messages,
    get_ai_notify_config,
    save_ai_notify_config,
)
from .llm_providers import (  # noqa: F401
    AI_CONFIG_FILE_CANDIDATES,
    AI_GUARDRAILS_CANDIDATES,
    AI_PROVIDERS_JSON_CANDIDATES,
    AI_PROVIDERS_TEMPLATE_CANDIDATES,
    DEFAULT_GUARDRAILS,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_TOOL_OUTPUT,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    SYSTEM_PROMPT,
    _active_model_entry,
    _active_provider_entry,
    _ai_guardrails_path,
    _ai_providers_json_path,
    _ai_settings,
    _call_anthropic,
    _call_anthropic_http,
    _call_chat_completions,
    _call_llm,
    _call_openai,
    _read_ai_config,
    _read_providers_json,
    _read_template_json,
    _repo_root,
    _resolve_api_key,
    _write_providers_json,
    get_ai_guardrails,
    save_ai_guardrails,
)
from .agent_tools import (  # noqa: F401
    BLOCKED_CMD_PATTERNS,
    CHROMA_COLLECTION_NAME,
    CHROMA_DATA_DIR,
    TOOL_EXECUTORS,
    TOOL_SCHEMAS,
    _CHAT_CTX,
    _PENDING_WRITES,
    _PENDING_WRITES_LOCK,
    _build_chroma_where,
    _build_write_preview,
    _clean_filter_val,
    _cmd_is_blocked,
    _format_knowledge_hit,
    _get_aosp_build_info,
    _get_chroma_client,
    _get_chroma_collection,
    _parse_version_list,
    _resolve_aosp_source_dir,
    _resolve_grep_target,
    _resolve_target_project_dir,
    _resolve_workspace_or_docs_path,
    _stage_pending_write,
    _tool_add_task_comment,
    _tool_create_git_fix_branch,
    _tool_create_github_issue,
    _tool_create_task,
    _tool_edit_file,
    _tool_get_aosp_project_info,
    _tool_get_commit_diff,
    _tool_get_file_git_history,
    _tool_get_telua_skill,
    _tool_grep_search,
    _tool_list_files,
    _tool_list_tasks,
    _tool_list_telua_skills,
    _tool_read_file,
    _tool_run_tel,
    _tool_save_training_knowledge,
    _tool_search_knowledge,
    _tool_update_task,
    _tool_write_file,
)

ai_bp = Blueprint("ai", __name__)


AI_TOKEN_USAGE_PATH = "config/overlay/ai_agent/ai_token_usage.json"


def _ai_token_usage_file() -> Path:
    return _repo_root() / AI_TOKEN_USAGE_PATH


def get_ai_token_usage() -> dict:
    """Read token usage history across months."""
    p = _ai_token_usage_file()
    now_m = datetime.now().strftime("%Y-%m")
    default_state = {
        "months": {
            now_m: {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "requests": 0,
                "by_model": {},
            }
        },
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not p.is_file():
        return default_state
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_state
        if "months" not in data or not isinstance(data["months"], dict):
            data["months"] = {}
        if now_m not in data["months"]:
            data["months"][now_m] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "requests": 0,
                "by_model": {},
            }
        return data
    except Exception:
        return default_state


def record_ai_token_usage(prompt_tokens: int, completion_tokens: int, model: str = "", provider: str = "") -> dict:
    """Record token consumption for the current month and retain past 3-6 months history."""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return get_ai_token_usage()

    state = get_ai_token_usage()
    months = state.setdefault("months", {})
    now_m = datetime.now().strftime("%Y-%m")

    cur = months.setdefault(now_m, {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
        "by_model": {},
    })

    cur["prompt_tokens"] = int(cur.get("prompt_tokens", 0)) + int(prompt_tokens)
    cur["completion_tokens"] = int(cur.get("completion_tokens", 0)) + int(completion_tokens)
    cur["total_tokens"] = int(cur.get("total_tokens", 0)) + int(prompt_tokens + completion_tokens)
    cur["requests"] = int(cur.get("requests", 0)) + 1

    if model:
        by_model = cur.setdefault("by_model", {})
        m_entry = by_model.setdefault(model, {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
        })
        m_entry["prompt_tokens"] = int(m_entry.get("prompt_tokens", 0)) + int(prompt_tokens)
        m_entry["completion_tokens"] = int(m_entry.get("completion_tokens", 0)) + int(completion_tokens)
        m_entry["total_tokens"] = int(m_entry.get("total_tokens", 0)) + int(prompt_tokens + completion_tokens)
        m_entry["requests"] = int(m_entry.get("requests", 0)) + 1

    # Retention: keep up to 6 months (current month + past 5 months; safely covers user's 2-3 months requirement)
    sorted_months = sorted(months.keys(), reverse=True)
    if len(sorted_months) > 6:
        for old_m in sorted_months[6:]:
            months.pop(old_m, None)

    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    p = _ai_token_usage_file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass

    return state


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
    The file is stored at config/ai_agent/ai_providers.json, or in the git-ignored
    config/overlay/ai_agent/ai_providers.json when it contains API keys.
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
        cfg_path = _ai_overlay_file("const_ai.config")
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
                    "path": str(_ai_providers_json_path() or "config/ai_agent/ai_providers.json")})


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


def run_ai_agent_headless(
    user_msg: str,
    project: str = "",
    aosp_version: str = "",
    auto_confirm: bool = False,
) -> dict:
    """Run one headless AI Agent turn (used by scheduled triggers without Flask request context)."""
    chat_project = _clean_filter_val(project)
    chat_version = _clean_filter_val(aosp_version)
    _CHAT_CTX.project = chat_project
    _CHAT_CTX.aosp_version = chat_version
    _CHAT_CTX.docs_dir = ""
    _CHAT_CTX.target_dir = _resolve_target_project_dir("")

    provider, model, base_url, max_iter, _active_name, _active_model = _ai_settings()
    guardrails = get_ai_guardrails()
    loop_breaker = bool(guardrails.get("loop_breaker_enabled", True))
    max_output = max(1000, min(int(guardrails.get("max_tool_output_chars", 6000)), 20000))
    seen_calls = {}
    messages = [{"role": "user", "content": str(user_msg or "").strip()}]
    turn_prompt_tokens = 0
    turn_completion_tokens = 0
    try:
        for _ in range(max_iter):
            resp = _call_llm(messages, provider, model, base_url)
            u = resp.get("usage") or {}
            turn_prompt_tokens += int(u.get("prompt_tokens") or 0)
            turn_completion_tokens += int(u.get("completion_tokens") or 0)
            if not resp["tool_calls"]:
                if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
                    record_ai_token_usage(
                        turn_prompt_tokens, turn_completion_tokens,
                        model=resp.get("model", model), provider=resp.get("provider", provider),
                    )
                return {"ok": True, "answer": resp["text"] or "(empty response)", "model": resp.get("model", model)}

            messages.append(resp["raw_assistant_message"])
            for tc in resp["tool_calls"]:
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_name = tc["name"]
                call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                call_count = seen_calls.get(call_key, 0) + 1
                seen_calls[call_key] = call_count
                if loop_breaker and call_count >= 2:
                    result = f"[LOOP BREAKER SHIELD: duplicate call to '{tool_name}'. Synthesize final response now.]"
                elif not auto_confirm and tool_name in ("write_file", "edit_file"):
                    result, _ = _stage_pending_write(tool_name, args)
                else:
                    fn = TOOL_EXECUTORS.get(tool_name)
                    if fn:
                        try:
                            result = fn(args)
                        except Exception as exc:
                            result = f"[ERROR executing {tool_name}] {exc}"
                    else:
                        result = f"[ERROR] unknown tool: {tool_name}"
                if len(result) > max_output:
                    result = result[:max_output] + f"\n... [Truncated at {max_output} chars]"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
            record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens, model=model, provider=provider)
        return {"ok": True, "answer": f"⏹ Stopped at guardrail limit ({max_iter} turns)."}
    except Exception as exc:
        if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
            record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens, model=model, provider=provider)
        return {"ok": False, "error": str(exc)}
    finally:
        _CHAT_CTX.project = ""
        _CHAT_CTX.aosp_version = ""
        _CHAT_CTX.docs_dir = ""
        _CHAT_CTX.target_dir = ""


@ai_bp.post("/api/ai/chat")
def api_ai_chat():
    """Run the agent loop for one user message. Returns the final answer plus a
    trace of every tool call so the Web UI can display what the agent did."""
    data = request.get_json(silent=True) or {}
    user_msg = str(data.get("message", "")).strip()
    history = data.get("history") or []
    chat_project = _clean_filter_val(data.get("project"))
    chat_version = _clean_filter_val(data.get("aosp_version"))
    if not user_msg:
        return jsonify({"ok": False, "error": "Missing 'message'."}), 400

    # Expose active project / AOSP version / Docs dir to tools during this turn.
    # Priority: Sphinx Docs tab's active dir (docs_dir from UI) -> Project's docs_path -> ./docs
    active_docs_dir = str(data.get("docs_dir") or "").strip()
    if not active_docs_dir:
        try:
            from .telua_mcp_skill import resolve_project_docs_dir
            dd = resolve_project_docs_dir(chat_project)
            if dd is not None:
                active_docs_dir = str(dd)
        except Exception:
            pass
    _CHAT_CTX.project = chat_project
    _CHAT_CTX.aosp_version = chat_version
    _CHAT_CTX.docs_dir = active_docs_dir
    # Resolve Target Path; if the given dir doesn't exist, fall back to the
    # AOSP tab's resolved source dir (auto-detects android/qssi like tel CLI).
    raw_target = str(data.get("target_path", "") or "").strip()
    resolved_target = _resolve_target_project_dir(raw_target)
    if raw_target and (not resolved_target or not Path(resolved_target).is_dir()):
        aosp_dir = _resolve_aosp_source_dir()
        if aosp_dir and Path(aosp_dir).is_dir():
            resolved_target = aosp_dir
    _CHAT_CTX.target_dir = resolved_target

    provider, model, base_url, max_iter, _active_name, _active_model = _ai_settings()
    guardrails = get_ai_guardrails()
    loop_breaker = bool(guardrails.get("loop_breaker_enabled", True))
    max_output = max(1000, min(int(guardrails.get("max_tool_output_chars", 6000)), 20000))
    auto_confirm = bool(data.get("auto_confirm", False))
    seen_calls = {}
    pending_approvals = []

    messages = []
    for h in history[-10:]:
        role = h.get("role")
        content = str(h.get("content", ""))[:4000]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    ctx_parts = [f"Current_DateTime={datetime.now().strftime('%Y-%m-%d %H:%M:%S (%A)')}"]
    if chat_project:
        ctx_parts.append(f"Project={chat_project}")
    if chat_version:
        ctx_parts.append(f"AOSP_Version={chat_version}")
    if active_docs_dir:
        ctx_parts.append(f"Active_Docs_Dir={active_docs_dir}")
    aosp_info = _get_aosp_build_info()
    if aosp_info and aosp_info.get("active_project"):
        ap = aosp_info["active_project"]
        mod = aosp_info.get("module_name") or ""
        prod = aosp_info.get("target_product") or ""
        var = aosp_info.get("target_variant") or ""
        lunch = f"{prod}-{var}" if prod and var else prod
        src_p = aosp_info.get("source_path") or ""
        dep_p = aosp_info.get("deploy_path") or ""
        details = ", ".join(x for x in [
            f"module={mod}" if mod else "",
            f"target={lunch}" if lunch else "",
            f"src={src_p}" if src_p else "",
            f"deploy={dep_p}" if dep_p else "",
        ] if x)
        ctx_parts.append(f"AOSP_Tab_Profile={ap}({details})" if details else f"AOSP_Tab_Profile={ap}")
    effective_msg = f"[Active Context: {' | '.join(ctx_parts)}]\n{user_msg}" if ctx_parts else user_msg
    messages.append({"role": "user", "content": effective_msg})

    trace = []
    turn_prompt_tokens = 0
    turn_completion_tokens = 0
    try:
        for _ in range(max_iter):
            resp = _call_llm(messages, provider, model, base_url)
            u = resp.get("usage") or {}
            turn_prompt_tokens += int(u.get("prompt_tokens") or 0)
            turn_completion_tokens += int(u.get("completion_tokens") or 0)

            if not resp["tool_calls"]:
                if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
                    record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens,
                                          model=resp.get("model", model),
                                          provider=resp.get("provider", provider))
                return jsonify({
                    "ok": True,
                    "answer": resp["text"] or "(empty response)",
                    "trace": trace,
                    "pending_approvals": pending_approvals,
                    "model": resp.get("model", model),
                    "provider": resp.get("provider", provider),
                    "usage": {
                        "prompt_tokens": turn_prompt_tokens,
                        "completion_tokens": turn_completion_tokens,
                        "total_tokens": turn_prompt_tokens + turn_completion_tokens,
                    },
                })

            # Record assistant tool-call message and execute each tool.
            messages.append(resp["raw_assistant_message"])
            for tc in resp["tool_calls"]:
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                tool_name = tc["name"]
                call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                call_count = seen_calls.get(call_key, 0) + 1
                seen_calls[call_key] = call_count

                # Loop Breaker Guardrail: intercept identical duplicate calls
                if loop_breaker and call_count >= 2:
                    result = (
                        f"[LOOP BREAKER SHIELD: You have executed '{tool_name}' with the exact same arguments "
                        f"{call_count} times in this turn. To protect token limits and prevent infinite loops, "
                        f"do not repeat this tool call. Please synthesize your final response now.]"
                    )
                elif not auto_confirm and tool_name in ("write_file", "edit_file"):
                    try:
                        result, approval_item = _stage_pending_write(tool_name, args)
                        if approval_item is not None:
                            pending_approvals.append(approval_item)
                    except Exception as exc:
                        result = f"[ERROR staging {tool_name}] {exc}"
                else:
                    fn = TOOL_EXECUTORS.get(tool_name)
                    if fn:
                        try:
                            result = fn(args)
                        except Exception as exc:
                            result = f"[ERROR executing {tool_name}] {exc}"
                    else:
                        result = f"[ERROR] unknown tool: {tool_name}"

                # Enforce output length limit
                if len(result) > max_output:
                    result = result[:max_output] + f"\n... [Truncated at {max_output} chars to protect token budget]"

                trace.append({
                    "tool": tc["name"],
                    "args": args,
                    "output": result[:2000],
                })
                if isinstance(result, str) and result.startswith("[ERROR"):
                    _notify_telegram_async(
                        f"Tool Error: {tool_name}",
                        f"Model: {model}\nTool: {tool_name}\nOutput: {result[:1200]}",
                        category="tool_error",
                    )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
            record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens,
                                  model=model, provider=provider)
        _notify_telegram_async(
            f"Guardrail Stop ({max_iter} turns)",
            f"Model: {model}\nUser prompt: {user_msg[:400]}",
            category="guardrail_stop",
        )
        return jsonify({
            "ok": True,
            "answer": f"⏹ Đã dừng sau {max_iter} bước agent (Guardrail Limit: Max {max_iter} iterations). "
                      "Agent đã thực hiện các bước ở trên để tránh đốt token.",
            "trace": trace,
            "pending_approvals": pending_approvals,
            "model": model,
            "provider": provider,
            "usage": {
                "prompt_tokens": turn_prompt_tokens,
                "completion_tokens": turn_completion_tokens,
                "total_tokens": turn_prompt_tokens + turn_completion_tokens,
            },
        })
    except RuntimeError as exc:
        if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
            record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens, model=model, provider=provider)
        _notify_telegram_async(
            "Agent Runtime Error",
            f"Provider: {provider} | Model: {model}\nError: {exc}\nPrompt: {user_msg[:400]}",
            category="agent_error",
        )
        return jsonify({"ok": False, "error": str(exc), "trace": trace}), 400
    except Exception as exc:  # pragma: no cover
        if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
            record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens, model=model, provider=provider)
        _notify_telegram_async(
            "Agent Unexpected Error",
            f"Provider: {provider} | Model: {model}\nError: {exc}\nPrompt: {user_msg[:400]}",
            category="agent_error",
        )
        return jsonify({"ok": False, "error": f"Agent error: {exc}", "trace": trace}), 500
    finally:
        _CHAT_CTX.project = ""
        _CHAT_CTX.aosp_version = ""
        _CHAT_CTX.docs_dir = ""
        _CHAT_CTX.target_dir = ""


@ai_bp.get("/api/ai/guardrails")
def api_ai_guardrails_get():
    """Get current token guardrails configuration."""
    return jsonify({"ok": True, "guardrails": get_ai_guardrails()})


@ai_bp.get("/api/ai/notify")
def api_ai_notify_get():
    """Get Telegram notification configuration (bot token masked)."""
    cfg = get_ai_notify_config()
    tok = str(cfg.get("bot_token") or "")
    return jsonify({
        "ok": True,
        "notify": {
            "enabled": bool(cfg.get("enabled", False)),
            "has_token": bool(tok),
            "bot_token_masked": _mask_secret(tok),
            "chat_id": str(cfg.get("chat_id") or ""),
            "safe_mode": bool(cfg.get("safe_mode", True)),
            "bot_listen_enabled": bool(cfg.get("bot_listen_enabled", False)),
            "notify_on_agent_error": bool(cfg.get("notify_on_agent_error", True)),
            "notify_on_tool_error": bool(cfg.get("notify_on_tool_error", True)),
            "notify_on_guardrail_stop": bool(cfg.get("notify_on_guardrail_stop", False)),
        },
    })


@ai_bp.post("/api/ai/notify")
def api_ai_notify_post():
    """Save Telegram notification configuration into config/overlay/ai_agent/ai_notify.json."""
    data = request.get_json(silent=True) or {}
    try:
        cfg = save_ai_notify_config(data)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Failed to save notify config: {exc}"}), 500
    tok = str(cfg.get("bot_token") or "")
    return jsonify({
        "ok": True,
        "notify": {
            "enabled": bool(cfg.get("enabled", False)),
            "has_token": bool(tok),
            "bot_token_masked": _mask_secret(tok),
            "chat_id": str(cfg.get("chat_id") or ""),
            "safe_mode": bool(cfg.get("safe_mode", True)),
            "bot_listen_enabled": bool(cfg.get("bot_listen_enabled", False)),
            "notify_on_agent_error": bool(cfg.get("notify_on_agent_error", True)),
            "notify_on_tool_error": bool(cfg.get("notify_on_tool_error", True)),
            "notify_on_guardrail_stop": bool(cfg.get("notify_on_guardrail_stop", False)),
        },
    })


@ai_bp.post("/api/ai/notify/test")
def api_ai_notify_test():
    """Send a test Telegram notification using submitted or saved Bot Token & Chat ID."""
    data = request.get_json(silent=True) or {}
    bot_token = str(data.get("bot_token") or "").strip()
    chat_id = str(data.get("chat_id") or "").strip()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"✅ [Telua AI Agent] Test Telegram notification successful!\n🕒 {ts}"
    ok, info = _send_telegram_message(text, bot_token=bot_token or None, chat_id=chat_id or None)
    if not ok:
        return jsonify({"ok": False, "error": info}), 400
    return jsonify({"ok": True, "message": info})


@ai_bp.get("/api/ai/notify/messages")
def api_ai_notify_messages():
    """Read recent incoming Telegram messages from the authorized Chat ID."""
    limit = max(1, min(int(request.args.get("limit", 10) or 10), 30))
    ok, msgs, err, _ = fetch_telegram_messages(limit=limit)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "messages": msgs, "count": len(msgs)})


@ai_bp.post("/api/ai/notify/get-chat-id")
def api_ai_notify_get_chat_id():
    """Call Telegram getUpdates using submitted or saved Bot Token to detect Chat ID(s) and return raw JSON."""
    data = request.get_json(silent=True) or {}
    bot_token = str(data.get("bot_token") or "").strip()
    ok, result, err = fetch_telegram_chat_ids(bot_token=bot_token or None)
    if not ok:
        return jsonify({"ok": False, "error": err, "raw": result.get("raw") if isinstance(result, dict) else None}), 400
    return jsonify({
        "ok": True,
        "chats": result.get("chats", []),
        "raw": result.get("raw", {}),
    })


@ai_bp.post("/api/ai/guardrails")
def api_ai_guardrails_post():
    """Update token guardrails configuration."""
    data = request.get_json(silent=True) or {}
    updated = save_ai_guardrails(data)
    return jsonify({"ok": True, "guardrails": updated})


@ai_bp.get("/api/ai/token_usage")
def api_ai_token_usage():
    """Return token usage statistics for the current month and past months."""
    state = get_ai_token_usage()
    now_m = datetime.now().strftime("%Y-%m")
    months = state.get("months", {})
    cur = months.get(now_m, {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
        "by_model": {},
    })

    history = []
    for m in sorted(months.keys(), reverse=True):
        m_data = months[m]
        history.append({
            "month": m,
            "prompt_tokens": m_data.get("prompt_tokens", 0),
            "completion_tokens": m_data.get("completion_tokens", 0),
            "total_tokens": m_data.get("total_tokens", 0),
            "requests": m_data.get("requests", 0),
            "by_model": m_data.get("by_model", {}),
        })

    return jsonify({
        "ok": True,
        "current_month": now_m,
        "current": cur,
        "history": history,
        "months": months,
        "last_updated": state.get("last_updated", ""),
    })


# ------------------------------------------------------------------------------
# ChromaDB Persistent Training & Knowledge Endpoints (ai_agent/data)
# ------------------------------------------------------------------------------

@ai_bp.get("/api/ai/chroma/status")
def api_ai_chroma_status():
    """Return aggregated status across all sharded VectorDB databases."""
    try:
        from .db import get_vector_db
        vdb = get_vector_db(base_dir=CHROMA_DATA_DIR)
        return jsonify(vdb.status(collection_name=CHROMA_COLLECTION_NAME))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ------------------------------------------------------------------------------
# Model Context Protocol (MCP) Skills & Knowledge Endpoints (Java_Android)
# ------------------------------------------------------------------------------

@ai_bp.get("/api/ai/mcp/config")
def api_ai_mcp_config_get():
    """Return MCP skill configuration and local status."""
    from .telua_mcp_skill import get_mcp_skill_config, scan_skills, get_all_configured_sources, DEFAULT_AOSP_VERSIONS, DEFAULT_PROJECTS
    cfg = get_mcp_skill_config()
    skills = scan_skills(with_meta=False)  # cached listing; no file reads
    categories = sorted(set(s["category"] for s in skills))
    sources = get_all_configured_sources()
    by_src = {}
    for s in skills:
        by_src[s["source_id"]] = by_src.get(s["source_id"], 0) + 1
    return jsonify({
        "ok": True,
        "config": cfg,
        "skills_count": len(skills),
        "categories": categories,
        "aosp_versions": cfg.get("aosp_versions") or [dict(v) for v in DEFAULT_AOSP_VERSIONS],
        "projects": cfg.get("projects") or [dict(p) for p in DEFAULT_PROJECTS],
        "sources": [
            {
                "id": s["id"],
                "name": s["name"],
                "repo_url": s["repo_url"],
                "local_path": s["local_path"],
                "project": s.get("project", "aosp_aaos"),
                "aosp_version": s.get("aosp_version", ""),
                "api_level": s.get("api_level"),
                "branch": s.get("branch", ""),
                "enabled": s.get("enabled", True),
                "visibility": s.get("visibility", "public"),
                "is_private": bool(s.get("visibility") == "private" or s.get("is_private")),
                "exists": s.get("exists", False),
                "resolved_path": s.get("resolved_path", ""),
                "count": by_src.get(s["id"], 0),
            }
            for s in sources
        ],
    })


@ai_bp.post("/api/ai/mcp/config")
def api_ai_mcp_config_post():
    """Save updated MCP skill configuration."""
    from .telua_mcp_skill import save_mcp_skill_config, invalidate_skill_scan_cache
    data = request.get_json(silent=True) or {}
    updated = save_mcp_skill_config(data)
    invalidate_skill_scan_cache()
    return jsonify({"ok": True, "config": updated})


@ai_bp.post("/api/ai/mcp/config/import")
def api_ai_mcp_config_import():
    """Import knowledge sources from an uploaded JSON file (export format).

    Accepts multipart 'file' upload or a JSON body. The JSON may be:
      - {"sources": [...]} (export format), or
      - a bare list of source objects.
    Imported entries are merged by id (existing sources with the same id are
    updated, new ones appended); nothing is deleted.
    """
    from .telua_mcp_skill import (
        save_mcp_skill_config,
        invalidate_skill_scan_cache,
        get_all_configured_sources,
    )

    if "file" in request.files:
        raw = request.files["file"].read()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            return jsonify({"ok": False, "error": f"Invalid JSON file: {exc}"}), 400
    else:
        data = request.get_json(silent=True)
    if isinstance(data, list):
        data = {"sources": data}
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list) or not data["sources"]:
        return jsonify({"ok": False, "error": "JSON must contain a non-empty 'sources' list."}), 400

    def _clean(s, i):
        is_priv = bool(s.get("visibility") == "private" or s.get("is_private"))
        local_path = str(s.get("local_path", "")).strip()
        return {
            "id": str(s.get("id", "")).strip() or f"imported_{i + 1}",
            "name": str(s.get("name", "")).strip() or f"Imported source {i + 1}",
            "local_path": local_path,
            "repo_url": str(s.get("repo_url", "")).strip(),
            "project": str(s.get("project", "")).strip() or "aosp_aaos",
            "aosp_version": str(s.get("aosp_version", "")).strip(),
            "api_level": int(s["api_level"]) if s.get("api_level") else None,
            "branch": str(s.get("branch", "")).strip(),
            "enabled": bool(s.get("enabled", True)),
            "visibility": "private" if is_priv else "public",
            "is_private": is_priv,
        }

    incoming = {}
    order = []
    for i, s in enumerate(data["sources"]):
        if not isinstance(s, dict):
            continue
        entry = _clean(s, i)
        if not entry["local_path"]:
            continue
        key = entry["id"].lower()
        if key not in incoming:
            order.append(key)
        incoming[key] = entry
    if not incoming:
        return jsonify({"ok": False, "error": "No valid sources (with 'local_path') found in the uploaded file."}), 400

    # Merge with existing sources: imported overrides same-id, others appended.
    merged = {}
    merged_order = []
    for s in get_all_configured_sources():
        key = str(s.get("id", "")).strip().lower()
        if not key or key in merged:
            continue
        merged[key] = _clean(s, len(merged_order))
        merged_order.append(key)
    for key in order:
        if key in merged:
            merged_order.remove(key)
        merged[key] = incoming[key]
        merged_order.append(key)

    updated = save_mcp_skill_config({"sources": [merged[k] for k in merged_order]})
    invalidate_skill_scan_cache()
    return jsonify({
        "ok": True,
        "imported": len(incoming),
        "total": len(merged_order),
        "config": updated,
    })


@ai_bp.post("/api/ai/mcp/sync")
def api_ai_mcp_sync():
    """Start a background sync of all enabled sources into ChromaDB (ai_agent/data).

    Returns immediately (202); poll GET /api/ai/mcp/sync/status for progress.
    Body (optional): {"incremental": true}
    """
    from .telua_mcp_skill import start_sync_job
    data = request.get_json(silent=True) or {}
    res = start_sync_job(incremental=bool(data.get("incremental", True)), trigger="web")
    return jsonify(res), (202 if res.get("started") else 200)


@ai_bp.get("/api/ai/mcp/sync/status")
def api_ai_mcp_sync_status():
    """Live progress snapshot of the running / last ChromaDB sync job."""
    from .telua_mcp_skill import get_sync_progress
    return jsonify({"ok": True, "progress": get_sync_progress()})


@ai_bp.post("/api/ai/mcp/sync/cancel")
def api_ai_mcp_sync_cancel():
    """Request cancellation of the running ChromaDB sync job."""
    from .telua_mcp_skill import cancel_sync_job
    return jsonify(cancel_sync_job())


# ------------------------------------------------------------------------------
# Knowledge Bundle (ZIP) export / import
#
# One .zip containing up to 3 files:
#   knowledge_sources.json  — MCP knowledge sources (public + private)
#   ai_providers.json       — AI provider/model config (API keys included)
#   mcp_state.json          — last sync / indexed count runtime state
# ------------------------------------------------------------------------------

@ai_bp.get("/api/ai/mcp/bundle/export")
def api_ai_mcp_bundle_export():
    """Download a single .zip bundling knowledge sources + AI provider config + MCP state."""
    from .telua_mcp_skill import get_all_configured_sources, get_mcp_skill_state

    def _clean_src(s):
        is_priv = bool(s.get("visibility") == "private" or s.get("is_private"))
        return {
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "local_path": s.get("local_path", ""),
            "repo_url": s.get("repo_url", ""),
            "project": s.get("project", "aosp_aaos"),
            "aosp_version": s.get("aosp_version", ""),
            "api_level": s.get("api_level"),
            "branch": s.get("branch", ""),
            "enabled": bool(s.get("enabled", True)),
            "visibility": "private" if is_priv else "public",
        }

    sources = [_clean_src(s) for s in get_all_configured_sources()]
    providers = _read_providers_json()
    state = get_mcp_skill_state()

    manifest = {
        "bundle": "telua_knowledge_bundle",
        "version": 1,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": ["knowledge_sources.json", "ai_providers.json", "mcp_state.json"],
        "counts": {"sources": len(sources), "providers": len(providers)},
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr("knowledge_sources.json", json.dumps({"sources": sources}, indent=2, ensure_ascii=False))
        zf.writestr("ai_providers.json", json.dumps(providers, indent=2, ensure_ascii=False))
        zf.writestr("mcp_state.json", json.dumps(state, indent=2, ensure_ascii=False))
    buf.seek(0)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"telua_knowledge_bundle_{stamp}.zip",
    )


@ai_bp.post("/api/ai/mcp/bundle/import")
def api_ai_mcp_bundle_import():
    """Upload a knowledge bundle .zip (or a single JSON) and merge its contents.

    - knowledge_sources.json -> merged into MCP sources by id (nothing deleted)
    - ai_providers.json      -> merged by provider name (existing apiKey kept when omitted)
    - mcp_state.json         -> last_sync / indexed_count restored
    """
    from .telua_mcp_skill import (
        save_mcp_skill_config,
        save_mcp_skill_state,
        invalidate_skill_scan_cache,
        get_all_configured_sources,
    )

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded."}), 400
    f = request.files["file"]
    fname = (f.filename or "").lower()
    raw = f.read()

    parts = {}  # name -> parsed JSON
    if fname.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in zf.namelist():
                    base = os.path.basename(name).lower()
                    if base.endswith(".json") and not base.startswith("."):
                        try:
                            parts[base] = json.loads(zf.read(name).decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
        except zipfile.BadZipFile:
            return jsonify({"ok": False, "error": "Invalid ZIP file."}), 400
    elif fname.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            return jsonify({"ok": False, "error": f"Invalid JSON file: {exc}"}), 400
        if isinstance(data, dict) and isinstance(data.get("sources"), list):
            parts["knowledge_sources.json"] = data
        elif isinstance(data, list):
            parts["ai_providers.json"] = data
        else:
            return jsonify({"ok": False, "error": "Unrecognized JSON content."}), 400
    else:
        return jsonify({"ok": False, "error": "Expected a .zip bundle or .json file."}), 400

    if not parts:
        return jsonify({"ok": False, "error": "No usable JSON files found in the bundle."}), 400

    summary = {"imported_sources": 0, "imported_providers": 0, "state_restored": False}

    def _clean_src(s, i):
        is_priv = bool(s.get("visibility") == "private" or s.get("is_private"))
        local_path = str(s.get("local_path", "")).strip()
        return {
            "id": str(s.get("id", "")).strip() or f"imported_{i + 1}",
            "name": str(s.get("name", "")).strip() or f"Imported source {i + 1}",
            "local_path": local_path,
            "repo_url": str(s.get("repo_url", "")).strip(),
            "project": str(s.get("project", "")).strip() or "aosp_aaos",
            "aosp_version": str(s.get("aosp_version", "")).strip(),
            "api_level": int(s["api_level"]) if s.get("api_level") else None,
            "branch": str(s.get("branch", "")).strip(),
            "enabled": bool(s.get("enabled", True)),
            "visibility": "private" if is_priv else "public",
            "is_private": is_priv,
        }

    # 1. Knowledge sources (merge by id, nothing deleted)
    src_data = parts.get("knowledge_sources.json")
    if isinstance(src_data, dict) and isinstance(src_data.get("sources"), list):
        incoming = {}
        order = []
        for i, s in enumerate(src_data["sources"]):
            if not isinstance(s, dict):
                continue
            entry = _clean_src(s, i)
            if not entry["local_path"]:
                continue
            key = entry["id"].lower()
            if key not in incoming:
                order.append(key)
            incoming[key] = entry
        if incoming:
            merged = {}
            merged_order = []
            for s in get_all_configured_sources():
                key = str(s.get("id", "")).strip().lower()
                if not key or key in merged:
                    continue
                merged[key] = _clean_src(s, len(merged_order))
                merged_order.append(key)
            for key in order:
                if key in merged:
                    merged_order.remove(key)
                merged[key] = incoming[key]
                merged_order.append(key)
            save_mcp_skill_config({"sources": [merged[k] for k in merged_order]})
            summary["imported_sources"] = len(incoming)

    # 2. AI providers (merge by name; keep stored apiKey when omitted)
    prov_data = parts.get("ai_providers.json")
    if isinstance(prov_data, list) and prov_data:
        existing = {p.get("name"): dict(p) for p in _read_providers_json() if isinstance(p, dict) and p.get("name")}
        merged_provs = []
        seen = set()
        for p in prov_data:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            name = p["name"]
            prev = existing.get(name) or {}
            if not p.get("apiKey") and prev.get("apiKey"):
                p["apiKey"] = prev["apiKey"]
            merged_provs.append(p)
            seen.add(name)
        for name, p in existing.items():
            if name not in seen:
                merged_provs.append(p)
        if merged_provs:
            try:
                _write_providers_json(merged_provs)
                summary["imported_providers"] = len(merged_provs)
            except Exception as exc:
                summary["providers_error"] = str(exc)

    # 3. MCP runtime state (last_sync / indexed_count)
    st_data = parts.get("mcp_state.json")
    if isinstance(st_data, dict) and ("last_sync" in st_data or "indexed_count" in st_data):
        try:
            save_mcp_skill_state({
                "last_sync": str(st_data.get("last_sync", "")),
                "indexed_count": int(st_data.get("indexed_count") or 0),
            })
            summary["state_restored"] = True
        except Exception:
            pass

    invalidate_skill_scan_cache()
    summary["ok"] = True
    return jsonify(summary)


@ai_bp.get("/api/ai/mcp/skills")
def api_ai_mcp_skills():
    """List scanned skills (capped by ?limit=, default 500; 'count' is the full total)."""
    from .telua_mcp_skill import scan_skills
    try:
        limit = max(0, min(int(request.args.get("limit", 500)), 20000))
    except (TypeError, ValueError):
        limit = 500
    total = len(scan_skills(with_meta=False))
    skills = scan_skills(limit=limit)
    return jsonify({"ok": True, "skills": skills, "count": total, "truncated": total > len(skills)})


@ai_bp.get("/api/ai/mcp/skill")
def api_ai_mcp_skill():
    """Get raw content of one skill file."""
    path = request.args.get("path") or request.args.get("name") or ""
    if not path:
        return jsonify({"ok": False, "error": "Missing 'path' or 'name'."}), 400
    from .telua_mcp_skill import get_skill_content
    res = get_skill_content(path)
    if not res:
        return jsonify({"ok": False, "error": f"Skill not found: {path}"}), 404
    return jsonify({"ok": True, "skill": res})



@ai_bp.post("/api/ai/chroma/train")
def api_ai_chroma_train():
    """Add a new document/snippet to the ChromaDB training knowledge collection."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or data.get("content") or "").strip()
    topic = str(data.get("topic") or "user_trained").strip()
    source = str(data.get("source") or "web_ui").strip()
    if not text:
        return jsonify({"ok": False, "error": "Missing 'text' content to train."}), 400
    res = _tool_save_training_knowledge({"content": text, "topic": topic, "source": source})
    if res.startswith("[ERROR"):
        return jsonify({"ok": False, "error": res}), 500
    return jsonify({"ok": True, "result": res})


@ai_bp.post("/api/ai/chroma/query")
def api_ai_chroma_query():
    """Query sharded VectorDB databases (supports optional project, aosp_version, source_id filters)."""
    data = request.get_json(silent=True) or {}
    query = str(data.get("query") or "").strip()
    n_results = max(1, min(int(data.get("n_results", 4)), 25))
    if not query:
        return jsonify({"ok": False, "error": "Missing 'query'."}), 400
    try:
        from .db import get_vector_db
        vdb = get_vector_db(base_dir=CHROMA_DATA_DIR)
        project = _clean_filter_val(data.get("project"))
        source_id = _clean_filter_val(data.get("source_id"))
        versions = _parse_version_list(data.get("aosp_versions"))
        if len(versions) >= 2:
            by_version = {}
            all_records = []
            queried = []
            for ver in versions[:6]:
                recs, q = vdb.query(
                    query_text=query,
                    n_results=n_results,
                    project=project,
                    aosp_version=ver,
                    source_id=source_id,
                    collection_name=CHROMA_COLLECTION_NAME,
                )
                by_version[ver] = recs
                all_records.extend(recs)
                queried.extend(q)
            return jsonify({
                "ok": True,
                "backend": vdb.backend_name,
                "records": all_records,
                "by_version": by_version,
                "count": len(all_records),
                "shards_queried": list(dict.fromkeys(queried)),
                "filter": {"project": project, "aosp_versions": versions, "source_id": source_id},
            })

        aosp_version = (versions[0] if len(versions) == 1 else "") or _clean_filter_val(data.get("aosp_version"))
        where = _build_chroma_where(project=project, aosp_version=aosp_version, source_id=source_id)
        records, queried = vdb.query(
            query_text=query,
            n_results=n_results,
            project=project,
            aosp_version=aosp_version,
            source_id=source_id,
            collection_name=CHROMA_COLLECTION_NAME,
        )
        return jsonify({
            "ok": True,
            "backend": vdb.backend_name,
            "records": records,
            "count": len(records),
            "shards_queried": queried,
            "filter": where,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@ai_bp.post("/api/ai/approvals/<approval_id>/approve")
def api_ai_approval_approve(approval_id: str):
    """Execute a staged write_file / edit_file change after user confirmation."""
    with _PENDING_WRITES_LOCK:
        item = _PENDING_WRITES.pop(approval_id, None)
    if not item:
        return jsonify({"ok": False, "error": "Pending approval not found or already handled."}), 404
    tool_name = item["tool"]
    fn = _tool_write_file if tool_name == "write_file" else _tool_edit_file
    result = fn(item["args"])
    if result.startswith("[ERROR"):
        return jsonify({"ok": False, "error": result, "path": item["path"]}), 400
    return jsonify({"ok": True, "result": result, "path": item["path"], "tool": tool_name})


@ai_bp.post("/api/ai/approvals/<approval_id>/reject")
def api_ai_approval_reject(approval_id: str):
    """Discard a staged write_file / edit_file change without modifying disk."""
    with _PENDING_WRITES_LOCK:
        item = _PENDING_WRITES.pop(approval_id, None)
    if not item:
        return jsonify({"ok": False, "error": "Pending approval not found or already handled."}), 404
    return jsonify({"ok": True, "rejected": True, "path": item["path"], "tool": item["tool"]})




