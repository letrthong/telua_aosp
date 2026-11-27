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
from datetime import datetime
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
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_MAX_TOOL_OUTPUT = 6000  # chars per tool result fed back to the LLM

DEFAULT_GUARDRAILS = {
    "max_iterations": 5,
    "max_lines_per_read": 150,
    "max_tool_output_chars": 6000,
    "loop_breaker_enabled": True,
}

AI_GUARDRAILS_CANDIDATES = [
    "config/overlay/ai_guardrails.json",
    "config/ai_guardrails.json",
]


def _ai_guardrails_path() -> Path:
    root = _repo_root()
    for cand in AI_GUARDRAILS_CANDIDATES:
        p = root / cand
        if p.is_file():
            return p
    return root / "config" / "overlay" / "ai_guardrails.json"


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
    p = _repo_root() / "config" / "overlay" / "ai_guardrails.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


AI_TOKEN_USAGE_PATH = "config/overlay/ai_token_usage.json"


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
logcat, dumpsys diagnostics, git/repo operations, analyzing source code, and autonomous coding.

Rules:
- Prefer the provided tools over guessing. Use run_tel for tel/telua/shell commands.
- Use search_knowledge to query local persistent ChromaDB documentation and training data.
- Use save_training_knowledge to persist verified solutions or architectural notes for long-term recall.
- You can create, write, and edit code files directly using write_file and edit_file.
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


CHROMA_DATA_DIR = _repo_root() / "ai_agent" / "data"
_CHROMA_CLIENT = None
CHROMA_COLLECTION_NAME = "telua_knowledge"


def _get_chroma_client():
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is not None:
        return _CHROMA_CLIENT
    try:
        import chromadb
        CHROMA_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _CHROMA_CLIENT = chromadb.PersistentClient(path=str(CHROMA_DATA_DIR))
        return _CHROMA_CLIENT
    except Exception:
        return None


def _get_chroma_collection(name: str = CHROMA_COLLECTION_NAME):
    client = _get_chroma_client()
    if client is None:
        return None
    try:
        return client.get_or_create_collection(
            name=name,
            metadata={"description": "Telua AOSP persistent training knowledge & docs"}
        )
    except Exception:
        return None


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
    
    If any provider has an active apiKey, ALWAYS writes to config/overlay/ai_providers.json
    (which is git-ignored) to guarantee zero API key leakage into tracked public Git files.
    """
    has_any_key = any(bool(p.get("apiKey")) for p in providers if isinstance(p, dict))
    overlay_path = _repo_root() / "config" / "overlay" / "ai_providers.json"
    if has_any_key or overlay_path.is_file():
        path = overlay_path
    else:
        path = _ai_providers_json_path() or (_repo_root() / "config" / "ai_providers.json")
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
    """Read optional config/overlay/const_ai.config (KEY=VALUE lines)."""
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
    max_iter = max(1, min(int(guardrails.get("max_iterations", DEFAULT_MAX_ITERATIONS)), 20))
    active_name = cfg.get("active_provider", "")
    active_model = cfg.get("active_model", "")
    return provider, model, base_url, max_iter, active_name, active_model


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
            cwd=str(_repo_root()),
            capture_output=True, text=True, errors="replace", timeout=300,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return out[:DEFAULT_MAX_TOOL_OUTPUT] or f"(exit code {proc.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return "[ERROR] command timed out after 300s"
    except Exception as exc:
        return f"[ERROR] {exc}"


def _tool_read_file(args: dict) -> str:
    """Read file content with line numbers, constrained by guardrails to prevent token burning."""
    root = _repo_root()
    rel = str(args.get("path", "")).strip().lstrip("/")
    if not rel:
        return "[ERROR] missing 'path'"
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return "[ERROR] path outside toolkit root is not allowed"
    if not path.is_file():
        return f"[ERROR] file not found: {rel}"

    guardrails = get_ai_guardrails()
    max_lines = max(10, min(int(guardrails.get("max_lines_per_read", 150)), 500))
    max_chars = max(1000, min(int(guardrails.get("max_tool_output_chars", 6000)), 20000))

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[ERROR] {exc}"

    if not text.strip():
        return f"(empty file: {rel})"

    # Structure & AST-aware code reading
    from .code_structure_engine import CodeStructureEngine

    # Mode 1: High-level symbol outline
    if args.get("outline"):
        return CodeStructureEngine.get_outline(text, path.name, rel_path=rel)

    # Mode 2: Complete method/symbol extraction
    target_symbol = str(args.get("method") or args.get("symbol") or "").strip()
    if target_symbol:
        sym_res = CodeStructureEngine.extract_symbol(text, path.name, target_symbol, rel_path=rel)
        if sym_res:
            return sym_res["output"]
        return (
            f"[NOT FOUND] Symbol '{target_symbol}' was not found in {rel}.\n"
            f"Use read_file(path='{rel}', outline=True) to inspect available classes and methods."
        )

    # Mode 3: Line range reading with flexible length & smart boundary snapping
    guardrails = get_ai_guardrails()
    default_max_lines = int(guardrails.get("max_lines_per_read", 150))
    requested_max_lines = args.get("max_lines")
    if requested_max_lines is not None:
        try:
            max_lines = max(10, min(int(requested_max_lines), 500))
        except (ValueError, TypeError):
            max_lines = default_max_lines
    else:
        max_lines = max(10, min(default_max_lines, 500))

    max_chars = max(1000, min(int(guardrails.get("max_tool_output_chars", 6000)), 20000))

    lines = text.splitlines()
    total_lines = len(lines)

    try:
        start_line = max(1, int(args.get("start_line", 1)))
    except (ValueError, TypeError):
        start_line = 1

    try:
        if "end_line" in args and args["end_line"] is not None:
            end_line = max(start_line, int(args["end_line"]))
        else:
            end_line = start_line + max_lines - 1
    except (ValueError, TypeError):
        end_line = start_line + max_lines - 1

    if (end_line - start_line + 1) > max_lines:
        end_line = start_line + max_lines - 1

    actual_end = min(total_lines, end_line)

    # Smart Boundary Snapping: expand end_line up to 50 lines to complete the active method
    snap_note = ""
    try:
        _, s_end, note = CodeStructureEngine.snap_boundaries(
            text, path.name, start_line, actual_end, max_snap=50
        )
        if s_end != actual_end and s_end <= total_lines:
            actual_end = s_end
            snap_note = f" {note}" if note else ""
    except Exception:
        pass

    selected_lines = lines[start_line - 1 : actual_end]

    numbered_lines = []
    char_count = 0
    hit_char_limit = False

    for idx, line in enumerate(selected_lines, start=start_line):
        formatted = f"{idx:4d} | {line}"
        if char_count + len(formatted) > max_chars:
            hit_char_limit = True
            break
        numbered_lines.append(formatted)
        char_count += len(formatted) + 1

    header = f"=== FILE: {rel} (Lines {start_line}-{actual_end} of {total_lines} total lines){snap_note} ==="
    body = "\n".join(numbered_lines)

    footer = ""
    if actual_end < total_lines:
        rem = total_lines - actual_end
        footer = f"\n... [{rem} lines remaining. Use read_file with start_line={actual_end+1} to read next chunk] ..."
    elif hit_char_limit:
        footer = f"\n... [Output truncated at {max_chars} chars guardrail limit] ..."

    return f"{header}\n{body}{footer}"


def _tool_write_file(args: dict) -> str:
    """Create a new file or overwrite an existing file in the workspace."""
    root = _repo_root()
    rel = str(args.get("path", "")).strip().lstrip("/")
    if not rel:
        return "[ERROR] missing 'path'"
    content = args.get("content", "")
    if content is None:
        return "[ERROR] missing 'content'"
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return "[ERROR] path outside toolkit root is not allowed"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"[SUCCESS] wrote {len(content)} characters to {rel}"
    except Exception as exc:
        return f"[ERROR] failed to write file: {exc}"


def _tool_edit_file(args: dict) -> str:
    """Replace an exact target snippet in an existing file with replacement code."""
    root = _repo_root()
    rel = str(args.get("path", "")).strip().lstrip("/")
    if not rel:
        return "[ERROR] missing 'path'"
    target = args.get("target", "")
    replacement = args.get("replacement", "")
    if not target:
        return "[ERROR] missing 'target' snippet to replace"
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return "[ERROR] path outside toolkit root is not allowed"
    if not path.is_file():
        return f"[ERROR] file not found: {rel}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if target not in text:
            return f"[ERROR] target snippet not found in {rel}"
        new_text = text.replace(target, replacement, 1)
        path.write_text(new_text, encoding="utf-8")
        return f"[SUCCESS] updated {rel} (replaced target snippet)"
    except Exception as exc:
        return f"[ERROR] failed to edit file: {exc}"


def _tool_list_files(args: dict) -> str:
    root = _repo_root()
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


def _tool_search_knowledge(args: dict) -> str:
    """Search persistent ChromaDB knowledge base in ai_agent/data."""
    query = str(args.get("query", "")).strip()
    if not query:
        return "[ERROR] missing 'query' parameter"
    col = _get_chroma_collection()
    if col is None:
        return "[WARNING] ChromaDB is not initialized or ai_agent/data is unavailable."
    try:
        n_results = max(1, min(int(args.get("n_results", 4)), 10))
        results = col.query(query_texts=[query], n_results=n_results)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        if not docs:
            return f"(No knowledge records matched query: '{query}')"
        out = []
        for i, (doc, meta) in enumerate(zip(docs, metas)):
            topic = (meta or {}).get("topic", "general")
            src = (meta or {}).get("source", "user_train")
            out.append(f"[{i+1}] (Topic: {topic} | Source: {src})\n{doc}")
        return "\n\n---\n\n".join(out)
    except Exception as exc:
        return f"[ERROR querying ChromaDB] {exc}"


def _tool_save_training_knowledge(args: dict) -> str:
    """Save new training knowledge / notes directly to ChromaDB on disk (ai_agent/data)."""
    content = str(args.get("content", "")).strip()
    if not content:
        return "[ERROR] missing 'content' to train/save"
    topic = str(args.get("topic", "general")).strip()
    source = str(args.get("source", "agent_train")).strip()
    col = _get_chroma_collection()
    if col is None:
        return "[ERROR] ChromaDB is not initialized."
    try:
        import uuid
        import time
        doc_id = f"doc_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        meta = {
            "topic": topic,
            "source": source,
            "timestamp": int(time.time()),
        }
        col.add(documents=[content], metadatas=[meta], ids=[doc_id])
        return f"✓ Successfully persisted to ChromaDB (ai_agent/data): id={doc_id}, topic={topic}, {len(content)} chars."
    except Exception as exc:
        return f"[ERROR saving to ChromaDB] {exc}"


def _tool_get_file_git_history(args: dict) -> str:
    """Inspect git commit history (commit, author, date, message) of a specific file."""
    root = _repo_root()
    rel = str(args.get("filepath", "") or args.get("path", "")).strip().lstrip("/")
    if not rel:
        return "[ERROR] missing 'filepath'"
    try:
        limit = max(1, min(int(args.get("limit", 10)), 30))
    except (ValueError, TypeError):
        limit = 10

    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return "[ERROR] path outside toolkit root is not allowed"

    cmd = [
        "git", "-C", str(root),
        "log", f"-n{limit}",
        "--pretty=format:%h | %ad | %an | %s",
        "--date=short",
        "--", rel,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = proc.stdout.strip()
        if not out:
            return f"Không có lịch sử commit cho file '{rel}' (hoặc file mới chưa commit)."
        return f"=== Git History: {rel} (Top {limit} commits) ===\n{out}"
    except Exception as exc:
        return f"[ERROR reading git history] {exc}"


def _tool_get_commit_diff(args: dict) -> str:
    """Inspect diff and stat of a specific git commit to see lines added/removed."""
    root = _repo_root()
    commit = str(args.get("commit_hash", "") or args.get("commit", "")).strip()
    if not commit:
        return "[ERROR] missing 'commit_hash'"

    if not re.match(r"^[a-zA-Z0-9_\-\.\^~]+$", commit):
        return "[ERROR] invalid commit hash format"

    filepath = str(args.get("filepath", "") or args.get("path", "")).strip().lstrip("/")

    cmd = ["git", "-C", str(root), "show", "--stat", "-p", commit]
    if filepath:
        path = (root / filepath).resolve()
        if not str(path).startswith(str(root.resolve())):
            return "[ERROR] filepath outside toolkit root is not allowed"
        cmd.extend(["--", filepath])

    guardrails = get_ai_guardrails()
    max_output = max(1000, min(int(guardrails.get("max_tool_output_chars", 6000)), 20000))

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        out = proc.stdout
        if proc.returncode != 0:
            err = proc.stderr.strip() or f"git show exited with code {proc.returncode}"
            return f"[ERROR] {err}"
        if len(out) > max_output:
            out = out[:max_output] + f"\n... [Diff truncated at {max_output} chars to protect token budget] ..."
        return out or "(empty diff)"
    except Exception as exc:
        return f"[ERROR reading commit diff] {exc}"


def _get_github_token() -> str:
    """Resolve GitHub token from environment or config/overlay/github_token.json."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    root = _repo_root()
    overlay_path = root / "config" / "overlay" / "github_token.json"
    if overlay_path.is_file():
        try:
            data = json.loads(overlay_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return str(data.get("token") or data.get("github_token") or "").strip()
        except Exception:
            pass
    return ""


def _detect_github_repo() -> str:
    """Infer 'owner/repo' from git remote origin url."""
    root = _repo_root()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        url = proc.stdout.strip()
        m = re.search(r"github\.com[:/]([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+?)(?:\.git)?$", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return ""


def _tool_create_github_issue(args: dict) -> str:
    """Create an Issue on GitHub repository (e.g. when bugs or regressions are detected)."""
    title = str(args.get("title", "")).strip()
    body = str(args.get("body", "")).strip()
    if not title:
        return "[ERROR] missing 'title' parameter"
    if not body:
        return "[ERROR] missing 'body' parameter"

    token = _get_github_token()
    if not token:
        return (
            "[ERROR] GitHub token not found. Please set GITHUB_TOKEN environment variable "
            "or save {\"token\": \"ghp_...\"} into config/overlay/github_token.json (Git-ignored)."
        )

    repo = str(args.get("repo", "")).strip() or _detect_github_repo()
    if not repo:
        return "[ERROR] cannot infer repository name. Please provide 'repo' parameter (e.g. 'owner/repo')."

    labels = args.get("labels")
    if labels and not isinstance(labels, list):
        labels = [str(labels)]

    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = [str(l).strip() for l in labels if str(l).strip()]

    import urllib.request
    import urllib.error
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "Telua-AI-Agent",
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            issue_num = data.get("number")
            issue_url = data.get("html_url")
            return f"✓ [SUCCESS] GitHub Issue #{issue_num} created: {issue_url}"
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        return f"[ERROR creating GitHub Issue] HTTP {err.code}: {err.reason} - {err_body[:300]}"
    except Exception as exc:
        return f"[ERROR creating GitHub Issue] {exc}"


def _tool_create_git_fix_branch(args: dict) -> str:
    """Create a new git fix/feature branch, commit staged/modified changes, and optionally push to remote."""
    root = _repo_root()
    branch = str(args.get("branch_name", "") or args.get("branch", "")).strip()
    commit_msg = str(args.get("commit_msg", "") or args.get("message", "")).strip()
    should_push = bool(args.get("push", True))
    remote = str(args.get("remote", "origin")).strip() or "origin"

    if not branch:
        return "[ERROR] missing 'branch_name' parameter"
    if not commit_msg:
        return "[ERROR] missing 'commit_msg' parameter"

    # Security check: never allow committing/pushing directly to main or master
    cleaned_branch = branch.lstrip("/")
    if cleaned_branch.lower() in ("main", "master", "head", "origin/main", "origin/master"):
        return f"[BLOCKED] Direct commits to '{cleaned_branch}' are blocked for safety. Please use a fix branch (e.g. 'fix/...', 'patch/...')."

    if not re.match(r"^[a-zA-Z0-9_\-\./]+$", cleaned_branch):
        return f"[ERROR] invalid branch name format: '{cleaned_branch}'"

    # Step 1: Check status
    try:
        st_proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        status_out = st_proc.stdout.strip()
        if not status_out:
            return "[ERROR] Working tree is clean. No modified or untracked files to commit."
    except Exception as exc:
        return f"[ERROR checking git status] {exc}"

    # Step 2: Checkout / create branch
    try:
        curr_b_proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        curr_branch = curr_b_proc.stdout.strip()

        if curr_branch != cleaned_branch:
            co_proc = subprocess.run(
                ["git", "-C", str(root), "checkout", "-b", cleaned_branch],
                capture_output=True, text=True, timeout=10
            )
            if co_proc.returncode != 0:
                co_exist = subprocess.run(
                    ["git", "-C", str(root), "checkout", cleaned_branch],
                    capture_output=True, text=True, timeout=10
                )
                if co_exist.returncode != 0:
                    return f"[ERROR checkout branch {cleaned_branch}] {co_proc.stderr or co_exist.stderr}"

        # Step 3: Git add modified files
        subprocess.run(["git", "-C", str(root), "add", "-u"], capture_output=True, timeout=15)
        files = args.get("files")
        if files and isinstance(files, list):
            for f in files:
                subprocess.run(["git", "-C", str(root), "add", str(f)], capture_output=True, timeout=10)

        # Step 4: Commit
        commit_proc = subprocess.run(
            ["git", "-C", str(root), "commit", "-m", commit_msg],
            capture_output=True, text=True, timeout=20
        )
        if commit_proc.returncode != 0:
            return f"[ERROR git commit] {commit_proc.stderr.strip() or commit_proc.stdout.strip()}"

        # Step 5: Get commit hash
        hash_proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        commit_hash = hash_proc.stdout.strip()

        push_msg = ""
        if should_push:
            push_proc = subprocess.run(
                ["git", "-C", str(root), "push", "-u", remote, cleaned_branch],
                capture_output=True, text=True, timeout=30
            )
            if push_proc.returncode == 0:
                push_msg = f"\n✓ Pushed to {remote}/{cleaned_branch}"
            else:
                push_msg = f"\n⚠️ Commit created ({commit_hash}) but push failed: {push_proc.stderr.strip()[:200]}"

        return (
            f"✓ [SUCCESS] Created branch '{cleaned_branch}' with commit {commit_hash}: '{commit_msg}'.{push_msg}"
        )
    except Exception as exc:
        return f"[ERROR creating git fix branch] {exc}"


TOOL_EXECUTORS = {
    "run_tel": _tool_run_tel,
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "edit_file": _tool_edit_file,
    "list_files": _tool_list_files,
    "search_knowledge": _tool_search_knowledge,
    "save_training_knowledge": _tool_save_training_knowledge,
    "get_file_git_history": _tool_get_file_git_history,
    "get_commit_diff": _tool_get_commit_diff,
    "create_github_issue": _tool_create_github_issue,
    "create_git_fix_branch": _tool_create_git_fix_branch,
    "get_telua_skill": lambda args: _tool_get_telua_skill(args),
    "list_telua_skills": lambda args: _tool_list_telua_skills(args),
}

def _tool_get_telua_skill(args: dict) -> str:
    """Retrieve raw content of a specific Java/Android or Claude Code Java skill/pattern."""
    name = str(args.get("name") or args.get("rel_path") or "").strip()
    if not name:
        return "[ERROR] missing skill 'name' or 'rel_path'"
    from .telua_mcp_skill import get_skill_content
    res = get_skill_content(name)
    if not res:
        return f"[ERROR] skill not found: {name}"
    src_label = res.get("source_name") or res.get("source_id") or "skill"
    return f"=== SKILL: {res['name']} (Source: {src_label}, Category: {res['category']}) ===\n" + res["content"]

def _tool_list_telua_skills(args: dict) -> str:
    """List available skills in telua_skill/Java_Android and claude-code-java."""
    cat = str(args.get("category", "")).strip()
    src = str(args.get("source", "")).strip()
    from .telua_mcp_skill import scan_skills
    skills = scan_skills(source_id=src if src else None)
    if cat:
        skills = [s for s in skills if s["category"].lower() == cat.lower()]
    lines = [f"- [{s.get('source_id')}:{s['category']}] {s['name']} - {s.get('title')}: {s['summary']}" for s in skills[:45]]
    return f"Found {len(skills)} skills across configured repositories:\n" + "\n".join(lines)

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
            "name": "search_knowledge",
            "description": "Search local persistent ChromaDB knowledge base (ai_agent/data) for indexed documentation, troubleshooting guides, training data, or previous solutions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search keywords or question to look up"},
                    "n_results": {"type": "integer", "description": "Number of results to return (default 4)"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_training_knowledge",
            "description": "Persist new technical knowledge, AOSP build notes, commands, solutions or training data directly to ChromaDB on disk (ai_agent/data) for long-term recall.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The detailed knowledge, code snippet, or explanation to persist"},
                    "topic": {"type": "string", "description": "Short topic label (e.g. 'aosp_build', 'audio_hal', 'battery_dump', 'git_repo')"},
                    "source": {"type": "string", "description": "Source reference, document path or author"}
                },
                "required": ["content", "topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_telua_skill",
            "description": "Fetch a specific Java, Android Automotive (AAOS), or Claude Code Java skill/pattern (e.g. 'concurrency-review', 'spring-boot-patterns', 'jpa-patterns', 'BinderServiceTemplate.java', 'thread_safety_concurrency_rule.md') by name or relative path.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Skill name, folder, or file name (e.g. 'concurrency-review', 'spring-boot-patterns', 'BinderServiceTemplate.java')"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_telua_skills",
            "description": "List available engineering skills, templates, rules, and patterns across telua_skill (Java_Android) and claude-code-java.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Optional source filter: 'telua_skill' or 'claude_code_java'"},
                    "category": {"type": "string", "description": "Optional category filter: rules, examples, design, concurrency-review, spring-boot-patterns, security-audit, etc."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a source code or text file in the workspace. Supports 3 modes: (1) outline=True to view all classes and methods with line numbers, (2) method='name' to extract a complete function body with class context, or (3) start_line/end_line range reading with automatic function boundary snapping.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path, e.g. src/MyService.java"},
                    "outline": {"type": "boolean", "description": "If true, returns a high-level symbol outline (classes, methods, line ranges) instead of reading full text. Use first on files > 150 lines."},
                    "method": {"type": "string", "description": "Optional name of a specific method or function to extract completely with its enclosing class context."},
                    "start_line": {"type": "integer", "description": "1-based line number to start reading from (default 1)"},
                    "end_line": {"type": "integer", "description": "1-based line number to end reading (default start_line + 150)"},
                    "max_lines": {"type": "integer", "description": "Maximum lines to read in one call (default 150, up to 500)"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or create a code, configuration, or documentation file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path inside the workspace (e.g. 'src/MyService.java')"},
                    "content": {"type": "string", "description": "The full text content to write into the file"}
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit an existing file by replacing an exact code target snippet with new replacement code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path inside the workspace"},
                    "target": {"type": "string", "description": "Exact text or code snippet in the file to be replaced"},
                    "replacement": {"type": "string", "description": "New replacement text or code snippet"}
                },
                "required": ["path", "target", "replacement"],
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
    {
        "type": "function",
        "function": {
            "name": "get_file_git_history",
            "description": "View git commit history (hash, author, date, subject) of a specific file to understand previous modifications and regressions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Relative file path inside the workspace (e.g. 'web/ai/telua_web_ai.py')"},
                    "limit": {"type": "integer", "description": "Maximum number of commits to list (default 10, max 30)"}
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_commit_diff",
            "description": "View details of lines added/deleted in a specific git commit (git show with diff and stat).",
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_hash": {"type": "string", "description": "Commit hash or reference (e.g. 'a1b2c3d' or 'HEAD~1')"},
                    "filepath": {"type": "string", "description": "Optional file path filter to see only changes to this file in the commit"}
                },
                "required": ["commit_hash"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_github_issue",
            "description": "Create an Issue on GitHub repository (e.g. when bugs, crashes, or regressions are detected during code analysis or build).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Issue title (e.g. '[AI-Bug] NullPointerException in CarAudioService')"},
                    "body": {"type": "string", "description": "Detailed markdown description of the bug, AST context, stack trace, and proposed fix"},
                    "labels": {"type": "array", "items": {"type": "string"}, "description": "Optional list of labels (e.g. ['bug', 'aosp', 'ai-detected'])"},
                    "repo": {"type": "string", "description": "Optional 'owner/repo' target (defaults to repository inferred from git remote origin)"}
                },
                "required": ["title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_git_fix_branch",
            "description": "Create a new git fix/feature branch, automatically stage and commit changes, and optionally push to private remote repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branch_name": {"type": "string", "description": "Name of the new branch (e.g. 'fix/audio-null-pointer' or 'feature/vhal-property')"},
                    "commit_msg": {"type": "string", "description": "Conventional commit message (e.g. 'fix(audio): handle NullPointerException in CarAudioService')"},
                    "push": {"type": "boolean", "description": "Whether to push the branch to remote repository (default true)"},
                    "remote": {"type": "string", "description": "Remote name (default 'origin')"}
                },
                "required": ["branch_name", "commit_msg"],
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
        root = _repo_root()
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
    guardrails = get_ai_guardrails()
    loop_breaker = bool(guardrails.get("loop_breaker_enabled", True))
    max_output = max(1000, min(int(guardrails.get("max_tool_output_chars", 6000)), 20000))
    seen_calls = {}

    messages = []
    for h in history[-10:]:
        role = h.get("role")
        content = str(h.get("content", ""))[:4000]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_msg})

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
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
            record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens,
                                  model=model, provider=provider)
        return jsonify({
            "ok": True,
            "answer": f"⏹ Đã dừng sau {max_iter} bước agent (Guardrail Limit: Max {max_iter} iterations). "
                      "Agent đã thực hiện các bước ở trên để tránh đốt token.",
            "trace": trace,
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
        return jsonify({"ok": False, "error": str(exc), "trace": trace}), 400
    except Exception as exc:  # pragma: no cover
        if turn_prompt_tokens > 0 or turn_completion_tokens > 0:
            record_ai_token_usage(turn_prompt_tokens, turn_completion_tokens, model=model, provider=provider)
        return jsonify({"ok": False, "error": f"Agent error: {exc}", "trace": trace}), 500


@ai_bp.get("/api/ai/guardrails")
def api_ai_guardrails_get():
    """Get current token guardrails configuration."""
    return jsonify({"ok": True, "guardrails": get_ai_guardrails()})


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
    """Return status of the persistent ChromaDB database in ai_agent/data."""
    client = _get_chroma_client()
    if client is None:
        return jsonify({
            "ok": True,
            "installed": False,
            "path": str(CHROMA_DATA_DIR),
            "doc_count": 0,
            "collections": [],
        })
    try:
        collections = client.list_collections()
        col_names = [getattr(c, "name", str(c)) for c in collections]
        col = _get_chroma_collection()
        count = col.count() if col else 0
        return jsonify({
            "ok": True,
            "installed": True,
            "path": str(CHROMA_DATA_DIR),
            "doc_count": count,
            "collections": col_names,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ------------------------------------------------------------------------------
# Model Context Protocol (MCP) Skills & Knowledge Endpoints (Java_Android)
# ------------------------------------------------------------------------------

@ai_bp.get("/api/ai/mcp/config")
def api_ai_mcp_config_get():
    """Return MCP skill configuration and local status."""
    from .telua_mcp_skill import get_mcp_skill_config, scan_skills, get_all_configured_sources
    cfg = get_mcp_skill_config()
    skills = scan_skills()
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
        "sources": [
            {
                "id": s["id"],
                "name": s["name"],
                "repo_url": s["repo_url"],
                "local_path": s["local_path"],
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
    from .telua_mcp_skill import save_mcp_skill_config
    data = request.get_json(silent=True) or {}
    updated = save_mcp_skill_config(data)
    return jsonify({"ok": True, "config": updated})


@ai_bp.post("/api/ai/mcp/sync")
def api_ai_mcp_sync():
    """Sync all skills from telua_skill/Java_Android into ChromaDB (ai_agent/data)."""
    from .telua_mcp_skill import sync_skills_to_chroma
    res = sync_skills_to_chroma()
    return jsonify(res)


@ai_bp.get("/api/ai/mcp/skills")
def api_ai_mcp_skills():
    """List all scanned skills from Java_Android."""
    from .telua_mcp_skill import scan_skills
    skills = scan_skills()
    return jsonify({"ok": True, "skills": skills, "count": len(skills)})


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
    """Query ChromaDB for relevant knowledge records."""
    data = request.get_json(silent=True) or {}
    query = str(data.get("query") or "").strip()
    n_results = int(data.get("n_results", 4))
    if not query:
        return jsonify({"ok": False, "error": "Missing 'query'."}), 400
    col = _get_chroma_collection()
    if not col:
        return jsonify({"ok": False, "error": "ChromaDB not available."}), 500
    try:
        res = col.query(query_texts=[query], n_results=n_results)
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        records = [{"text": d, "meta": m} for d, m in zip(docs, metas)]
        return jsonify({"ok": True, "records": records, "count": len(records)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500



