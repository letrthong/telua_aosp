#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# agent_tools.py — Tool executors, schemas, & staged write approvals for AI Agent
# ==============================================================================

import difflib
import json
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .ai_notify import _tool_read_telegram_messages, _tool_send_telegram_notify
from .llm_providers import DEFAULT_MAX_TOOL_OUTPUT, _repo_root, get_ai_guardrails

_CHAT_CTX = threading.local()

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


# ------------------------------------------------------------------------------
# Tool registry — the agent's "hands". Reuses tel's own capabilities.
# ------------------------------------------------------------------------------

def _cmd_is_blocked(cmd: str) -> Optional[str]:
    for pattern in BLOCKED_CMD_PATTERNS:
        if re.search(pattern, cmd):
            return pattern
    return None


_TEL_NEEDS_PROJECT_CWD_RE = re.compile(
    r"^\s*(?:tel|telua)\s+(?:-[a-zA-Z0-9_-]+(?:\s+[^\s-]+)?\s+)*(?:b|build|t|test)\b"
)


def _resolve_aosp_source_dir(info: dict = None) -> str:
    """Resolve the active project's full source directory from AOSP tab info.

    Prefers the pre-computed 'source_dir' (already includes AOSP_TOP_REL_PATH,
    e.g. <root>/android/qssi/vendor/...); falls back to manual composition, then
    to tel-CLI-style auto-detection (android/qssi -> qssi -> android) mirroring
    resolve_android_paths() in src/telua_android.sh.
    """
    info = info if info is not None else _get_aosp_build_info()
    # 1. Backend already resolved the full path (includes aosp_top_rel_path)
    src_dir = str(info.get("source_dir") or "").strip()
    if src_dir and Path(src_dir).is_dir():
        return src_dir.rstrip("/\\")
    # 2. Manual composition: root / aosp_top_rel_path / source_path
    aosp_root = str(info.get("aosp_root_dir") or "").strip().rstrip("/\\")
    top_rel = str(info.get("aosp_top_rel_path") or "").strip().strip("/\\")
    src_rel = str(info.get("source_path") or "").strip().strip("/\\")
    parts = [aosp_root] + [p for p in (top_rel, src_rel) if p]
    candidate = "/".join(parts) if aosp_root else ""
    if candidate and Path(candidate).is_dir():
        return candidate
    # 3. Auto-detect AOSP top like tel CLI does (android/qssi -> qssi -> android)
    if aosp_root and src_rel:
        for top in ("android/qssi", "qssi", "android"):
            cand = f"{aosp_root}/{top}/{src_rel}"
            if Path(cand).is_dir():
                return cand
        cand = f"{aosp_root}/{src_rel}"
        if Path(cand).is_dir():
            return cand
    return candidate


def _resolve_target_project_dir(raw_target: str = "") -> str:
    """Resolve the working directory for `tel b` / `tel t` from Target Path or AOSP config.

    If the given path doesn't exist on disk (e.g. missing the android/qssi
    layer), auto-detect the AOSP top like tel CLI does and re-resolve.
    """
    t = str(raw_target or "").strip()
    if t:
        p = Path(t)
        if p.is_dir():
            return str(p)
        if p.is_file():
            return str(p.parent)
        # Heuristic when path is on Linux or doesn't exist locally yet: if last segment has a dot, treat as file
        base = t.rstrip("/\\")
        last = base.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if "." in last and not last.startswith("."):
            base = base[: -(len(last) + 1)] or base
        # Path doesn't exist as-is: try inserting the AOSP top layer
        # (android/qssi -> qssi -> android) between root and source path,
        # mirroring resolve_android_paths() in src/telua_android.sh.
        info = _get_aosp_build_info()
        aosp_root = str(info.get("aosp_root_dir") or "").strip().rstrip("/\\")
        if aosp_root and base.startswith(aosp_root):
            src_rel = base[len(aosp_root):].strip("/\\")
            for top in ("android/qssi", "qssi", "android"):
                cand = f"{aosp_root}/{top}/{src_rel}"
                if Path(cand).is_dir():
                    return cand
        return base
    return _resolve_aosp_source_dir()


def _tool_run_tel(args: dict) -> str:
    cmd = str(args.get("cmd", "")).strip()
    if not cmd:
        return "[ERROR] empty command"
    blocked = _cmd_is_blocked(cmd)
    if blocked:
        return f"[BLOCKED] command matches safety rule '{blocked}' and was not executed."

    # Determine working directory: explicit `cwd` -> Target Path dir (for `tel b`/`tel t`) -> toolkit root
    run_cwd = str(_repo_root())
    req_cwd = str(args.get("cwd") or "").strip()
    if req_cwd:
        if Path(req_cwd).is_dir():
            run_cwd = req_cwd
        else:
            return f"[ERROR] cwd directory not found: {req_cwd}"
    elif _TEL_NEEDS_PROJECT_CWD_RE.match(cmd):
        # Fallback chain: active Target Path dir -> resolved AOSP source dir -> AOSP_ROOT_DIR
        info = _get_aosp_build_info()
        aosp_root = str(info.get("aosp_root_dir") or "").strip().rstrip("/\\")
        candidates = [
            str(getattr(_CHAT_CTX, "target_dir", "") or "").strip(),
            _resolve_aosp_source_dir(info),
            aosp_root,
        ]
        for cand_dir in candidates:
            if cand_dir and Path(cand_dir).is_dir():
                run_cwd = cand_dir
                break

    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
            cwd=run_cwd,
            capture_output=True, text=True, errors="replace", timeout=300,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return out[:DEFAULT_MAX_TOOL_OUTPUT] or f"(exit code {proc.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return "[ERROR] command timed out after 300s"
    except Exception as exc:
        return f"[ERROR] {exc}"


def _resolve_workspace_or_docs_path(
    raw_path: str,
    allow_sources: bool = False,
    allow_docs: bool = True,
    allow_aosp_root: bool = True,
) -> Tuple[Optional[Path], str]:
    """Resolve a path inside toolkit root, configured AOSP_ROOT_DIR, or (read-only) project docs / MCP sources."""
    root = _repo_root().resolve()
    p_str = str(raw_path or "").strip()
    if not p_str:
        return None, "[ERROR] missing 'path'"
    cand = Path(p_str)
    target = cand.resolve() if cand.is_absolute() else (root / p_str.lstrip("/\\")).resolve()

    allowed = [root]
    if allow_aosp_root:
        try:
            aosp_info = _get_aosp_build_info()
            aosp_root = str(aosp_info.get("aosp_root_dir") or "").strip()
            if aosp_root:
                p_aosp = Path(aosp_root)
                allowed.append((p_aosp if p_aosp.is_absolute() else (root / aosp_root)).resolve())
        except Exception:
            pass
    if allow_docs or allow_sources:
        try:
            from .telua_mcp_skill import get_mcp_skill_config, get_all_configured_sources
            if allow_docs:
                active_dd = str(getattr(_CHAT_CTX, "docs_dir", "") or "").strip()
                if active_dd:
                    p_dd = Path(active_dd)
                    allowed.append((p_dd if p_dd.is_absolute() else (root / active_dd)).resolve())
                cfg = get_mcp_skill_config()
                for proj in (cfg.get("projects") or []):
                    dp = str((proj or {}).get("docs_path") or "").strip()
                    if dp:
                        p_dp = Path(dp)
                        allowed.append((p_dp if p_dp.is_absolute() else (root / dp)).resolve())
            if allow_sources:
                for s in get_all_configured_sources():
                    d = s.get("dir")
                    if d and Path(d).is_dir():
                        allowed.append(Path(d).resolve())
        except Exception:
            pass

    for base in allowed:
        try:
            target.relative_to(base)
            return target, ""
        except ValueError:
            continue
    return None, "[ERROR] path outside toolkit root and configured AOSP_ROOT_DIR is not allowed"


def _tool_read_file(args: dict) -> str:
    """Read file content with line numbers, constrained by guardrails to prevent token burning."""
    rel = str(args.get("path", "")).strip()
    path, err = _resolve_workspace_or_docs_path(rel, allow_sources=True)
    if err or path is None:
        return err
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
    """Create a new file or overwrite an existing file in the workspace (project docs are read-only)."""
    rel = str(args.get("path", "")).strip()
    content = args.get("content", "")
    if content is None:
        return "[ERROR] missing 'content'"
    path, err = _resolve_workspace_or_docs_path(rel, allow_sources=False, allow_docs=False)
    if err or path is None:
        return err
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"[SUCCESS] wrote {len(content)} characters to {rel}"
    except Exception as exc:
        return f"[ERROR] failed to write file: {exc}"


def _tool_edit_file(args: dict) -> str:
    """Replace an exact target snippet in an existing workspace file (project docs are read-only)."""
    rel = str(args.get("path", "")).strip()
    target = args.get("target", "")
    replacement = args.get("replacement", "")
    if not target:
        return "[ERROR] missing 'target' snippet to replace"
    path, err = _resolve_workspace_or_docs_path(rel, allow_sources=False, allow_docs=False)
    if err or path is None:
        return err
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


# Pending file write/edit approvals (used when Auto-Confirm Coding is OFF).
_PENDING_WRITES_LOCK = threading.Lock()
_PENDING_WRITES: dict = {}
_MAX_PENDING_WRITES = 100


def _build_write_preview(rel: str, old_text: Optional[str], new_text: str) -> str:
    """Build a compact unified diff (or new-file preview) for the UI approval card."""
    if old_text is None:
        lines = new_text.splitlines()
        head = lines[:60]
        body = "\n".join(f"+ {ln}" for ln in head)
        if len(lines) > 60:
            body += f"\n... (+{len(lines) - 60} more lines)"
        return body or "(empty file)"
    diff_lines = list(difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
        lineterm="",
        n=3,
    ))
    if not diff_lines:
        return "(no textual changes)"
    if len(diff_lines) > 120:
        diff_lines = diff_lines[:120] + [f"... ({len(diff_lines) - 120} more diff lines truncated)"]
    return "\n".join(diff_lines)


def _stage_pending_write(tool_name: str, args: dict) -> Tuple[str, Optional[dict]]:
    """Validate a write_file / edit_file call and stage it for user confirmation without touching disk."""
    rel = str(args.get("path", "")).strip()
    path, err = _resolve_workspace_or_docs_path(rel, allow_sources=False, allow_docs=False)
    if err or path is None:
        return err, None

    is_new = not path.is_file()
    if tool_name == "write_file":
        content = args.get("content", "")
        if content is None:
            return "[ERROR] missing 'content'", None
        old_text = None if is_new else path.read_text(encoding="utf-8", errors="replace")
        new_text = str(content)
        summary = f"Create new file ({len(new_text)} chars)" if is_new else f"Overwrite file ({len(new_text)} chars)"
    elif tool_name == "edit_file":
        target = args.get("target", "")
        replacement = args.get("replacement", "")
        if not target:
            return "[ERROR] missing 'target' snippet to replace", None
        if is_new:
            return f"[ERROR] file not found: {rel}", None
        old_text = path.read_text(encoding="utf-8", errors="replace")
        if target not in old_text:
            return f"[ERROR] target snippet not found in {rel}", None
        new_text = old_text.replace(target, replacement, 1)
        summary = "Edit file (replace snippet)"
    else:
        return f"[ERROR] unsupported approval tool: {tool_name}", None

    preview = _build_write_preview(rel, old_text, new_text)
    approval_id = uuid.uuid4().hex[:12]
    record = {
        "id": approval_id,
        "tool": tool_name,
        "path": rel,
        "args": dict(args),
        "is_new": is_new,
        "summary": summary,
        "preview": preview,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _PENDING_WRITES_LOCK:
        if len(_PENDING_WRITES) >= _MAX_PENDING_WRITES:
            oldest_key = next(iter(_PENDING_WRITES))
            _PENDING_WRITES.pop(oldest_key, None)
        _PENDING_WRITES[approval_id] = record

    public_item = {
        "id": approval_id,
        "tool": tool_name,
        "path": rel,
        "is_new": is_new,
        "summary": summary,
        "preview": preview,
    }
    llm_msg = (
        f"[PENDING USER APPROVAL id={approval_id}] Proposed {tool_name} on '{rel}' was staged "
        f"and NOT written to disk yet because Auto-Apply Edits is OFF. "
        f"Do NOT retry writing this file; summarize your proposed change and wait for the user "
        f"to click Approve or Reject in the UI."
    )
    return llm_msg, public_item


def _tool_list_files(args: dict) -> str:
    rel = str(args.get("path", "") or ".").strip() or "."
    path, err = _resolve_workspace_or_docs_path(rel, allow_sources=True, allow_docs=True, allow_aosp_root=True)
    if err or path is None:
        return err
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


_GREP_IGNORE_DIRS = {
    ".git", ".repo", "out", "node_modules", "build", "target",
    "__pycache__", ".idea", ".gradle", "ai_agent",
}
_GREP_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".zip", ".gz",
    ".tar", ".jar", ".apk", ".dex", ".so", ".a", ".o", ".class", ".bin",
    ".sqlite3", ".db", ".exe", ".dll", ".pyc", ".woff", ".woff2", ".ttf",
}


def _resolve_grep_target(raw_path: str) -> Tuple[Optional[Path], str]:
    """Allow searching inside toolkit root, configured AOSP_ROOT_DIR, project docs, or MCP sources."""
    return _resolve_workspace_or_docs_path(
        raw_path or ".",
        allow_sources=True,
        allow_docs=True,
        allow_aosp_root=True,
    )


def _tool_grep_search(args: dict) -> str:
    """Fast recursive text/regex search across files (uses ripgrep if available,
    otherwise pruned os.scandir Python fallback)."""
    import fnmatch
    import shutil

    query = str(args.get("query", "")).strip()
    if not query:
        return "[ERROR] missing 'query' parameter"

    raw_path = str(args.get("path", ".") or ".").strip()
    target, err = _resolve_grep_target(raw_path)
    if err or target is None:
        return err
    if not target.exists():
        return f"[ERROR] path not found: {raw_path}"

    is_regex = bool(args.get("is_regex", False))
    case_sensitive = bool(args.get("case_sensitive", True))
    include_glob = str(args.get("include", "") or "").strip()
    try:
        max_results = max(1, min(int(args.get("max_results", 50)), 200))
    except (TypeError, ValueError):
        max_results = 50

    # 1. Fast path: ripgrep (rg) if installed on host
    rg_bin = shutil.which("rg")
    if rg_bin:
        cmd = [
            rg_bin, "--no-heading", "--line-number", "--color=never",
            "--max-filesize=2M", "--max-count=20",
        ]
        if not is_regex:
            cmd.append("--fixed-strings")
        if not case_sensitive:
            cmd.append("--ignore-case")
        if include_glob:
            cmd.extend(["--glob", include_glob])
        for ig in _GREP_IGNORE_DIRS:
            cmd.extend(["--glob", f"!{ig}/**"])
        cmd.extend(["--", query, str(target)])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
            lines = [l for l in proc.stdout.splitlines() if l.strip()]
            if not lines:
                return f"(No matches for '{query}' in {raw_path})"
            truncated = len(lines) > max_results
            out_lines = lines[:max_results]
            # Shorten absolute prefix relative to target when searching a directory
            prefix = str(target).rstrip("\\/") + os.sep
            cleaned = [l[len(prefix):] if l.startswith(prefix) else l for l in out_lines]
            header = f"Found {len(out_lines)}{'+' if truncated else ''} match(es) for '{query}' in {raw_path}:\n"
            return header + "\n".join(cleaned)
        except Exception:
            pass  # fall through to Python walker

    # 2. Pure-Python fallback (pruned os.scandir)
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query if is_regex else re.escape(query), flags)
    except re.error as exc:
        return f"[ERROR] invalid regex '{query}': {exc}"

    matches: List[str] = []
    files_scanned = 0
    max_file_bytes = 2 * 1024 * 1024

    def scan_file(fpath: Path, rel_label: str) -> None:
        nonlocal files_scanned
        if len(matches) >= max_results:
            return
        if fpath.suffix.lower() in _GREP_BINARY_EXTS:
            return
        if include_glob and not fnmatch.fnmatch(fpath.name, include_glob):
            return
        try:
            if fpath.stat().st_size > max_file_bytes:
                return
            files_scanned += 1
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if pattern.search(line):
                        matches.append(f"{rel_label}:{lineno}: {line.rstrip()[:240]}")
                        if len(matches) >= max_results:
                            return
        except OSError:
            return

    if target.is_file():
        scan_file(target, target.name)
    else:
        base_str = str(target)
        prefix = base_str.rstrip("\\/") + os.sep
        stack = [base_str]
        while stack and len(matches) < max_results:
            cur = stack.pop()
            try:
                it = os.scandir(cur)
            except OSError:
                continue
            with it:
                for entry in it:
                    if len(matches) >= max_results:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in _GREP_IGNORE_DIRS:
                                stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            rel = entry.path[len(prefix):] if entry.path.startswith(prefix) else entry.name
                            scan_file(Path(entry.path), rel.replace("\\", "/"))
                    except OSError:
                        continue

    if not matches:
        return f"(No matches for '{query}' in {raw_path}; scanned {files_scanned} files)"
    more = "+" if len(matches) >= max_results else ""
    return f"Found {len(matches)}{more} match(es) for '{query}' in {raw_path}:\n" + "\n".join(matches)


def _get_aosp_build_info() -> dict:
    """Safely load active AOSP project build/deploy info from the AOSP tab backend."""
    try:
        import telua_web_aosp as _aosp
        return _aosp._parse_aosp_info() or {}
    except Exception:
        try:
            from .. import telua_web_aosp as _aosp
            return _aosp._parse_aosp_info() or {}
        except Exception:
            return {}


def _tool_get_aosp_project_info(args: dict) -> str:
    """Return active AOSP tab configuration (project profile, lunch target, module, paths, build/deploy commands)."""
    info = _get_aosp_build_info()
    if not info:
        return "[WARNING] Could not read AOSP configuration from config/apk.config."
    active = info.get("active_project") or "—"
    prod = info.get("target_product") or ""
    var = info.get("target_variant") or ""
    lunch = f"{prod}-{var}" if prod and var else (prod or "—")
    profs = ", ".join(info.get("profiles") or []) or "—"
    aosp_root = str(info.get("aosp_root_dir") or "").strip().rstrip("/\\")
    src_rel = str(info.get("source_path") or "").strip().lstrip("/\\")
    work_dir = _resolve_aosp_source_dir(info) or (aosp_root or "<AOSP_ROOT_DIR>")
    return (
        f"ACTIVE_PROJECT: {active}\n"
        f"AOSP_ROOT_DIR: {aosp_root or '(auto-detect)'}\n"
        f"LUNCH_TARGET: {lunch}\n"
        f"MODULE_NAME: {info.get('module_name') or '—'} (type: {info.get('module_type') or 'apk'})\n"
        f"SOURCE_PATH: {src_rel or '—'}\n"
        f"FULL_PROJECT_DIR: {work_dir}\n"
        f"OUTPUT_FILE: {info.get('apk_name') or '—'}\n"
        f"DEPLOY_PATH: {info.get('deploy_path') or '—'}\n"
        f"AVAILABLE_PROFILES: {profs}\n"
        f"BUILD_DEPLOY_COMMANDS (always cd into FULL_PROJECT_DIR or AOSP_ROOT_DIR first):\n"
        f"  - Build active project: cd {work_dir} && tel b -y  (or: tel b -p {active} -y)\n"
        f"  - Run unit tests:       cd {work_dir} && tel t\n"
        f"  - Deploy to board:      cd {work_dir} && tel -y deploy\n"
        f"  - Capture logcat:       tel logcat"
    )


def _clean_filter_val(val) -> str:
    s = str(val or "").strip().lower()
    return "" if s in ("", "all", "auto", "any", "*") else s


def _build_chroma_where(project: str = "", aosp_version: str = "", source_id: str = "") -> Optional[dict]:
    """Build a ChromaDB `where` metadata filter dict (None if unfiltered)."""
    conds = []
    p = _clean_filter_val(project)
    v = _clean_filter_val(aosp_version)
    s = _clean_filter_val(source_id)
    if p:
        conds.append({"project": p})
    if v:
        conds.append({"aosp_version": v})
    if s:
        conds.append({"source_id": s})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def _parse_version_list(raw) -> List[str]:
    """Normalize aosp_versions (list or comma-separated string) into deduplicated version tags."""
    if not raw:
        return []
    items = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    out = []
    for item in items:
        v = _clean_filter_val(item)
        if v and v not in out:
            out.append(v)
    return out


def _format_knowledge_hit(idx: int, rec: dict) -> str:
    m = rec.get("meta") or {}
    proj = m.get("project") or "—"
    ver = m.get("aosp_version") or "generic"
    api_lvl = m.get("api_level")
    ver_disp = f"{ver} (API {api_lvl})" if api_lvl else ver
    src_name = m.get("source_name") or ""
    src_path = m.get("source") or "user_train"
    src_disp = f"{src_name} ({src_path})" if src_name and src_name != src_path else src_path
    topic = m.get("topic") or m.get("category") or "general"
    shard_lbl = rec.get("shard") or ""
    return f"[{idx}] (Shard: {shard_lbl} | Project: {proj} | AOSP: {ver_disp} | Source: {src_disp} | Topic: {topic})\n{rec.get('text', '')}"


def _tool_search_knowledge(args: dict) -> str:
    """Search sharded VectorDB knowledge base with automatic project / aosp_version(s) / source_id isolation.

    Pass `aosp_versions: ["a12", "a14", "a16"]` to compare multiple Android versions in a single call.
    """
    query = str(args.get("query", "")).strip()
    if not query:
        return "[ERROR] missing 'query' parameter"
    try:
        from .db import get_vector_db
        vdb = get_vector_db(base_dir=CHROMA_DATA_DIR)
        n_results = max(1, min(int(args.get("n_results", 4)), 10))
        project = _clean_filter_val(args.get("project")) or _clean_filter_val(getattr(_CHAT_CTX, "project", ""))
        source_id = _clean_filter_val(args.get("source_id"))

        versions = _parse_version_list(args.get("aosp_versions"))
        if len(versions) >= 2:
            # Multi-version comparison mode: query each version shard independently and group results
            per_ver = max(1, min(n_results, 5))
            sections = []
            for ver in versions[:6]:
                recs, _ = vdb.query(
                    query_text=query,
                    n_results=per_ver,
                    project=project,
                    aosp_version=ver,
                    source_id=source_id,
                    collection_name=CHROMA_COLLECTION_NAME,
                )
                if not recs:
                    sections.append(f"=== AOSP VERSION: {ver} (0 matches) ===")
                else:
                    body = "\n\n---\n\n".join(_format_knowledge_hit(i + 1, r) for i, r in enumerate(recs))
                    sections.append(f"=== AOSP VERSION: {ver} ({len(recs)} match(es)) ===\n{body}")
            return "\n\n".join(sections)

        aosp_version = (
            (versions[0] if len(versions) == 1 else "")
            or _clean_filter_val(args.get("aosp_version"))
            or _clean_filter_val(getattr(_CHAT_CTX, "aosp_version", ""))
        )
        where = _build_chroma_where(project=project, aosp_version=aosp_version, source_id=source_id)

        records, _queried_shards = vdb.query(
            query_text=query,
            n_results=n_results,
            project=project,
            aosp_version=aosp_version,
            source_id=source_id,
            collection_name=CHROMA_COLLECTION_NAME,
        )
        if not records:
            filt_str = f" with filter {where}" if where else ""
            return f"(No knowledge records matched query: '{query}'{filt_str})"
        return "\n\n---\n\n".join(_format_knowledge_hit(i + 1, rec) for i, rec in enumerate(records))
    except Exception as exc:
        return f"[ERROR querying VectorDB] {exc}"


def _tool_save_training_knowledge(args: dict) -> str:
    """Save new training knowledge / notes directly to the matching VectorDB shard."""
    content = str(args.get("content", "")).strip()
    if not content:
        return "[ERROR] missing 'content' to train/save"
    topic = str(args.get("topic", "general")).strip()
    source = str(args.get("source", "agent_train")).strip()
    project = _clean_filter_val(args.get("project")) or _clean_filter_val(getattr(_CHAT_CTX, "project", "")) or "aosp_aaos"
    aosp_version = _clean_filter_val(args.get("aosp_version")) or _clean_filter_val(getattr(_CHAT_CTX, "aosp_version", ""))
    try:
        from .db import get_vector_db
        vdb = get_vector_db(base_dir=CHROMA_DATA_DIR)
        import uuid
        import time
        doc_id = f"doc_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        meta = {
            "topic": topic,
            "source": source,
            "project": project,
            "aosp_version": aosp_version,
            "timestamp": int(time.time()),
        }
        s_key = vdb.add(
            doc_id=doc_id,
            document=content,
            metadata=meta,
            project=project,
            aosp_version=aosp_version,
            collection_name=CHROMA_COLLECTION_NAME,
        )
        return f"✓ Successfully persisted to VectorDB ({vdb.backend_name}) shard '{s_key}': id={doc_id}, topic={topic}, {len(content)} chars."
    except Exception as exc:
        return f"[ERROR saving to VectorDB] {exc}"


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
    "get_aosp_project_info": _tool_get_aosp_project_info,
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "edit_file": _tool_edit_file,
    "list_files": _tool_list_files,
    "grep_search": _tool_grep_search,
    "search_knowledge": _tool_search_knowledge,
    "save_training_knowledge": _tool_save_training_knowledge,
    "get_file_git_history": _tool_get_file_git_history,
    "get_commit_diff": _tool_get_commit_diff,
    "create_github_issue": _tool_create_github_issue,
    "create_git_fix_branch": _tool_create_git_fix_branch,
    "get_telua_skill": lambda args: _tool_get_telua_skill(args),
    "list_telua_skills": lambda args: _tool_list_telua_skills(args),
    "list_tasks": lambda args: _tool_list_tasks(args),
    "create_task": lambda args: _tool_create_task(args),
    "update_task": lambda args: _tool_update_task(args),
    "add_task_comment": lambda args: _tool_add_task_comment(args),
    "send_telegram_notify": lambda args: _tool_send_telegram_notify(args),
    "read_telegram_messages": lambda args: _tool_read_telegram_messages(args),
}

def _tool_list_tasks(args: dict) -> str:
    """List personal tasks from the Tasks tab (Today / 1-2w Sprint / 3-Month Roadmap / monthly or yearly archive)."""
    from .telua_web_tasks import list_tasks as _list_tasks
    horizon = str(args.get("horizon") or "current").strip()
    status = str(args.get("status") or "").strip()
    year = str(args.get("year") or "").strip()
    month = str(args.get("month") or "").strip()
    today_only = bool(args.get("today_only", False))
    include_done = bool(args.get("include_done", True))
    if (year or month) and not args.get("horizon"):
        horizon = "all"
    tasks, stats = _list_tasks(
        horizon=horizon,
        status=status,
        today_only=today_only,
        include_done=include_done,
        year=year,
        month=month,
    )
    period_lbl = f", month={month}" if month else (f", year={year}" if year else "")
    header = (
        f"=== TASKS SUMMARY (scope={horizon}{period_lbl}) ===\n"
        f"Today: {stats['today_done']}/{stats['today_count']} done (avg {stats['today_avg_progress']}%) | "
        f"Current Sprint (1-2w): {stats['sprint_done']}/{stats['sprint_count']} done (avg {stats['sprint_avg_progress']}%) | "
        f"3-Month Roadmap: {stats['quarter_count']} task(s) | "
        f"In-Progress: {stats['in_progress_count']} | Blocked: {stats['blocked_count']}\n"
    )
    if not tasks:
        return header + "(No tasks matched this filter.)"
    lines = []
    for t in tasks:
        today_tag = " [TODAY]" if (t.get("is_today") or t.get("horizon") == "today") else ""
        due = f" due:{t['due_date']}" if t.get("due_date") else ""
        done_at = f" done:{t['completed_at'][:10]}" if t.get("completed_at") else ""
        proj = f" proj:{t['project']}" if t.get("project") else ""
        cmts = t.get("comments") or []
        cmt_info = f" comments:{len(cmts)}" if cmts else ""
        notes = f" — {t['notes'][:120]}" if t.get("notes") else ""
        lines.append(
            f"- [{t['id']}] ({t['horizon']}{today_tag} | {t['status']} {t['progress']}% | {t['priority']}){due}{done_at}{proj}{cmt_info}: "
            f"{t['title']}{notes}"
        )
    return header + "\n".join(lines)


def _tool_create_task(args: dict) -> str:
    """Create a new task in the Tasks tab (Today / 1-2w Sprint / 3-Month Roadmap)."""
    from .telua_web_tasks import create_task as _create_task
    task, err, _ = _create_task(args, created_by="ai")
    if err or not task:
        return f"[ERROR] {err}"
    return (
        f"[SUCCESS] Created task {task['id']}: '{task['title']}' "
        f"(horizon={task['horizon']}, is_today={task['is_today']}, status={task['status']}, "
        f"progress={task['progress']}%, priority={task['priority']})"
    )


def _tool_update_task(args: dict) -> str:
    """Update an existing task's status, progress (0-100%), is_today pin, horizon, notes, or optional comment."""
    from .telua_web_tasks import add_task_comment as _add_task_comment, update_task as _update_task
    tid = str(args.get("task_id") or args.get("id") or "").strip()
    task, err, _ = _update_task(tid, args)
    if err or not task:
        return f"[ERROR] {err}"
    cmt_text = str(args.get("comment") or "").strip()
    cmt_note = ""
    if cmt_text:
        c, _, c_err = _add_task_comment(tid, cmt_text, author="ai")
        if c and not c_err:
            cmt_note = f", added AI comment {c['id']}"
    return (
        f"[SUCCESS] Updated task {task['id']}: '{task['title']}' -> "
        f"status={task['status']}, progress={task['progress']}%, horizon={task['horizon']}, is_today={task['is_today']}{cmt_note}"
    )


def _tool_add_task_comment(args: dict) -> str:
    """Add a comment (tagged author='ai') to an existing task."""
    from .telua_web_tasks import add_task_comment as _add_task_comment
    tid = str(args.get("task_id") or args.get("id") or "").strip()
    text = str(args.get("comment") or args.get("text") or "").strip()
    comment, task, err = _add_task_comment(tid, text, author="ai")
    if err or not comment:
        return f"[ERROR] {err}"
    return f"[SUCCESS] Added AI comment ({comment['id']}) to task {tid} ('{task['title'] if task else tid}')"

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
            "description": "Run a shell / tel / telua / adb command (e.g. 'tel b -y', 'tel t', 'tel dump battery', 'adb devices', 'git status'). For `tel b` (build) and `tel t` (test), pass `cwd` as the target project directory (or `cd <target_dir> && tel b -y`); if omitted, automatically uses the active Target Path directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "The command line to run"},
                    "cwd": {"type": "string", "description": "Optional working directory (required when building/testing inside a specific AOSP module directory)"}
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_aosp_project_info",
            "description": "Read the active AOSP tab configuration (ACTIVE_PROJECT, AOSP_ROOT_DIR, lunch target, module name/type, source path, APK/binary output, device deploy path, available profiles, and exact tel build/deploy commands).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search sharded VectorDB knowledge base for indexed documentation, source code, troubleshooting guides, or training data. Supports filtering by project, single aosp_version, or multiple aosp_versions (e.g. ['a12', 'a14', 'a16']) to compare Android versions side-by-side in a single call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search keywords or question to look up"},
                    "n_results": {"type": "integer", "description": "Number of results to return (or per version when aosp_versions is used; default 4)"},
                    "project": {"type": "string", "description": "Optional project filter (e.g. 'aosp_aaos', 'car_ivi')"},
                    "aosp_version": {"type": "string", "description": "Optional single AOSP version filter (e.g. 'a12', 'a14', 'a16')"},
                    "aosp_versions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of AOSP versions to query & compare side-by-side in one call (e.g. ['a12', 'a14', 'a16'])"
                    },
                    "source_id": {"type": "string", "description": "Optional knowledge source ID filter"}
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
            "name": "grep_search",
            "description": "Fast text or regex search across files in the workspace or any configured knowledge source directory. Returns matching 'file:line: content' lines. Use to find symbol definitions, callers, constants, or log tags before reading full files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Exact text or regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory or file path to search (relative to workspace or inside a configured source; default '.')"},
                    "is_regex": {"type": "boolean", "description": "Treat query as a regular expression (default false)"},
                    "case_sensitive": {"type": "boolean", "description": "Case-sensitive match (default true)"},
                    "include": {"type": "string", "description": "Optional filename glob filter (e.g. '*.java', '*.py', '*.aidl')"},
                    "max_results": {"type": "integer", "description": "Maximum matching lines to return (default 50, max 200)"}
                },
                "required": ["query"],
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
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List tasks from the Tasks tab (active.json + YYYY/YYYY-MM.json archives) to check Today's plan, current 1-2w sprint, 3-month roadmap, or monthly/yearly history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "horizon": {"type": "string", "description": "Filter scope: 'current' (default: today + 1-2w sprint), 'today', 'sprint_2w', 'quarter_3m', or 'all'"},
                    "status": {"type": "string", "description": "Optional status filter: 'todo', 'in_progress', 'blocked', 'done'"},
                    "year": {"type": "string", "description": "Optional year filter for archive/summary (e.g. '2026')"},
                    "month": {"type": "string", "description": "Optional month filter for archive/summary (e.g. '2026-11')"},
                    "today_only": {"type": "boolean", "description": "If true, only return tasks pinned to Today"},
                    "include_done": {"type": "boolean", "description": "Whether to include completed tasks (default true)"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task in the Tasks tab (Today focus, 1-2 week sprint, or 3-month roadmap). Use this when the user asks you to plan, break down, or add tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Concise, actionable task title"},
                    "horizon": {"type": "string", "description": "'today', 'sprint_2w' (1-2 weeks, default), or 'quarter_3m' (3-month roadmap)"},
                    "is_today": {"type": "boolean", "description": "Pin this task to Today's focus list"},
                    "priority": {"type": "string", "description": "'high', 'medium' (default), or 'low'"},
                    "progress": {"type": "integer", "description": "Initial completion percentage 0-100 (default 0)"},
                    "status": {"type": "string", "description": "'todo' (default), 'in_progress', 'blocked', or 'done'"},
                    "due_date": {"type": "string", "description": "Optional due date (YYYY-MM-DD)"},
                    "project": {"type": "string", "description": "Optional project/module tag (e.g. 'aosp_aaos', 'CarAudio')"},
                    "notes": {"type": "string", "description": "Optional implementation notes or sub-steps"}
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Update an existing task's progress (e.g. 50%), status ('todo'/'in_progress'/'blocked'/'done'), is_today flag, horizon, priority, or notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID from list_tasks (e.g. 'tsk_a1b2c3d4')"},
                    "status": {"type": "string", "description": "'todo', 'in_progress', 'blocked', or 'done'"},
                    "progress": {"type": "integer", "description": "Completion percentage 0-100"},
                    "is_today": {"type": "boolean", "description": "Pin/unpin task for Today"},
                    "horizon": {"type": "string", "description": "'today', 'sprint_2w', or 'quarter_3m'"},
                    "priority": {"type": "string", "description": "'high', 'medium', or 'low'"},
                    "due_date": {"type": "string", "description": "Due date (YYYY-MM-DD)"},
                    "notes": {"type": "string", "description": "Updated notes"},
                    "comment": {"type": "string", "description": "Optional progress comment to log on this task (recorded as author='ai')"}
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task_comment",
            "description": "Add a comment / progress log entry to an existing task in the Tasks tab (automatically recorded as comment by AI).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID from list_tasks (e.g. 'tsk_a1b2c3d4')"},
                    "comment": {"type": "string", "description": "Comment text (findings, build result, blocker, next step)"}
                },
                "required": ["task_id", "comment"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_notify",
            "description": "Send a Telegram notification message to the user using the Telegram Bot configured in AI Config -> Notify (useful for alerting on build/test errors or long task completion).",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Notification text to send to Telegram"}
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_telegram_messages",
            "description": "Read recent incoming messages sent by the user to the configured Telegram Bot (strictly filtered to the authorized Chat ID).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum number of recent messages to fetch (default 10, max 30)"}
                },
            },
        },
    },
]


