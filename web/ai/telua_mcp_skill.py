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
# telua_mcp_skill.py — Model Context Protocol (MCP) Server & Knowledge Ingestor
# for Multi-Repository Skills:
# 1. telua_skill (Java_Android: rules, architecture templates, examples, AAOS)
#    https://github.com/letrthong/telua_skill/tree/main/Java_Android
# 2. claude-code-java (Java Agent Skills: concurrency, JPA, Spring, security, etc.)
#    https://github.com/decebals/claude-code-java.git
#
# Persistent Vector DB: ai_agent/data (ChromaDB)
# ==============================================================================

import hashlib
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _repo_root() -> Path:
    # web/ai/telua_mcp_skill.py -> web/ai -> web -> repo_root
    return Path(__file__).resolve().parent.parent.parent


DEFAULT_SKILL_LOCAL_PATH = "repos/telua_skill/Java_Android"
DEFAULT_SKILL_REPO_URL = "https://github.com/letrthong/telua_skill/tree/main/Java_Android"

DEFAULT_SOURCES = [
    {
        "id": "telua_skill",
        "name": "Telua Java/Android & AAOS",
        "repo_url": "https://github.com/letrthong/telua_skill/tree/main/Java_Android",
        "local_path": "repos/telua_skill/Java_Android",
        "enabled": True,
        "visibility": "public",
    },
    {
        "id": "claude_code_java",
        "name": "Claude Code Java Agent Skills",
        "repo_url": "https://github.com/decebals/claude-code-java.git",
        "local_path": "repos/claude-code-java",
        "enabled": True,
        "visibility": "public",
    },
]

DEFAULT_AOSP_VERSIONS = [
    {"id": "auto", "name": "⚡ Auto-detect (A12-A16+)", "api_level": None, "is_auto": True},
    {"id": "a16", "name": "Android 16 (Baklava / API 36)", "api_level": 36},
    {"id": "a15", "name": "Android 15 (VanillaIceCream / API 35)", "api_level": 35},
    {"id": "a14", "name": "Android 14 (UpsideDownCake / API 34)", "api_level": 34},
    {"id": "a13", "name": "Android 13 (Tiramisu / API 33)", "api_level": 33},
    {"id": "a12", "name": "Android 12 (SnowCone / API 31-32)", "api_level": 32},
]

try:
    from .ai_config_paths import candidates as _ai_cfg_candidates, overlay_file as _ai_overlay_file, \
        shared_file as _ai_shared_file
except ImportError:  # executed as a script: python web/ai/telua_mcp_skill.py --mcp
    from ai_config_paths import candidates as _ai_cfg_candidates, overlay_file as _ai_overlay_file, \
        shared_file as _ai_shared_file

# Shared config: config/ai_agent/ ; personal/runtime: config/overlay/ai_agent/ (git-ignored)
CONFIG_FILE_CANDIDATES = _ai_cfg_candidates("mcp_skills_config.json")
STATE_FILE_PATH = "config/overlay/ai_agent/mcp_skills_state.json"
PRIVATE_SOURCES_FILE_PATH = "config/overlay/ai_agent/mcp_skills_private.json"


def get_private_sources() -> List[dict]:
    """Read private skill sources from git-ignored overlay file."""
    p = _repo_root() / PRIVATE_SOURCES_FILE_PATH
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("sources"), list):
                res = []
                for s in data["sources"]:
                    if isinstance(s, dict):
                        item = dict(s)
                        item["visibility"] = "private"
                        item["is_private"] = True
                        res.append(item)
                return res
        except Exception:
            pass
    return []


def save_private_sources(sources: List[dict]) -> None:
    """Save private skill sources to git-ignored overlay file."""
    p = _repo_root() / PRIVATE_SOURCES_FILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned = []
    for s in sources:
        if isinstance(s, dict):
            item = dict(s)
            item["visibility"] = "private"
            item["is_private"] = True
            cleaned.append(item)
    p.write_text(json.dumps({"sources": cleaned}, indent=2, ensure_ascii=False), encoding="utf-8")


def _config_path() -> Path:
    root = _repo_root()
    for cand in CONFIG_FILE_CANDIDATES:
        p = root / cand
        if p.is_file():
            return p
    return _ai_shared_file("mcp_skills_config.json")


def detect_aosp_version_from_path(dir_path: Optional[Path]) -> dict:
    """
    Detect AOSP version, API level, and branch from an AOSP tree or repository path.
    Looks for build/make/core/version_defaults.mk, git tags, or directory naming heuristics.
    """
    res = {
        "project": "aosp_aaos",
        "aosp_version": "",
        "api_level": None,
        "branch": "",
    }
    if not dir_path:
        return res

    # 1. Search for version_defaults.mk in ancestors or self if directory exists
    if dir_path.is_dir():
        curr = dir_path.resolve()
        for _ in range(6):
            ver_file = curr / "build" / "make" / "core" / "version_defaults.mk"
            if not ver_file.is_file():
                ver_file = curr / "build" / "core" / "version_defaults.mk"
            if ver_file.is_file():
                try:
                    txt = ver_file.read_text(encoding="utf-8", errors="ignore")
                    m_ver = re.search(r"PLATFORM_VERSION\s*(?::=|=)\s*([0-9\.]+)", txt)
                    m_sdk = re.search(r"PLATFORM_SDK_VERSION\s*(?::=|=)\s*([0-9]+)", txt)
                    if m_ver:
                        v_str = m_ver.group(1).split(".")[0]
                        res["aosp_version"] = f"a{v_str}"
                    if m_sdk:
                        res["api_level"] = int(m_sdk.group(1))
                    break
                except Exception:
                    pass
            if curr.parent == curr:
                break
            curr = curr.parent

        # Check git branch or tag if git repo
        git_dir = dir_path / ".git"
        if git_dir.exists():
            try:
                head_f = git_dir / "HEAD" if git_dir.is_dir() else None
                if head_f and head_f.is_file():
                    head_content = head_f.read_text(encoding="utf-8").strip()
                    if "refs/heads/" in head_content:
                        res["branch"] = head_content.split("refs/heads/")[-1].strip()
            except Exception:
                pass

    # 2. Check path string heuristics if not detected (e.g. 'aosp_a16', 'android-14', 'a12')
    if not res["aosp_version"]:
        full_str = str(dir_path).lower().replace("\\", "/")
        m_a = re.search(r"(?:android[-_]?|aosp[-_]?|a)(\d{2})\b", full_str)
        if m_a:
            v_num = int(m_a.group(1))
            res["aosp_version"] = f"a{v_num}"
            api_map = {11: 30, 12: 31, 13: 33, 14: 34, 15: 35, 16: 36}
            res["api_level"] = api_map.get(v_num)

    return res


def get_mcp_skill_state() -> dict:
    """Read dynamic runtime state (last_sync, indexed_count) from overlay."""
    p = _repo_root() / STATE_FILE_PATH
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"last_sync": "", "indexed_count": 0}


def save_mcp_skill_state(state: dict) -> dict:
    """Save dynamic runtime state to overlay file (never modifying tracked config)."""
    p = _repo_root() / STATE_FILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    current = get_mcp_skill_state()
    current.update(state)
    p.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def get_mcp_skill_config() -> dict:
    """Read MCP skill configuration (merged with overlay runtime state)."""
    path = _config_path()
    default_cfg = {
        "enabled": True,
        "auto_sync_enabled": True,
        "sync_on_startup": True,
        "sync_interval_hours": 3,
        "repo_url": DEFAULT_SKILL_REPO_URL,
        "local_path": DEFAULT_SKILL_LOCAL_PATH,
        "collection_name": "telua_knowledge",
        "sources": [dict(s) for s in DEFAULT_SOURCES],
        "aosp_versions": [dict(v) for v in DEFAULT_AOSP_VERSIONS],
        "last_sync": "",
        "indexed_count": 0,
    }
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                default_cfg.update(data)
                # Ensure sources list exists
                if "sources" not in data or not data.get("sources"):
                    default_cfg["sources"] = [dict(s) for s in DEFAULT_SOURCES]
                # Merge or load custom AOSP versions
                if "aosp_versions" in data and isinstance(data["aosp_versions"], list) and data["aosp_versions"]:
                    known_ids = {v["id"] for v in DEFAULT_AOSP_VERSIONS}
                    merged_vers = [dict(v) for v in DEFAULT_AOSP_VERSIONS]
                    for custom in data["aosp_versions"]:
                        if isinstance(custom, dict) and custom.get("id") and custom["id"] not in known_ids:
                            merged_vers.append(custom)
                            known_ids.add(custom["id"])
                    default_cfg["aosp_versions"] = merged_vers
        except Exception:
            pass
    # Merge overlay dynamic state without modifying static config file
    state = get_mcp_skill_state()
    default_cfg.update(state)
    return default_cfg


def save_mcp_skill_config(cfg: dict) -> dict:
    """Save static MCP skill configuration (stripping dynamic runtime state)."""
    # Extract dynamic state if passed
    state_updates = {}
    cleaned = dict(cfg)
    for k in ["last_sync", "indexed_count"]:
        if k in cleaned:
            state_updates[k] = cleaned.pop(k)
    if state_updates:
        save_mcp_skill_state(state_updates)

    # Clean and validate custom AOSP versions if passed
    if "aosp_versions" in cleaned and isinstance(cleaned["aosp_versions"], list):
        sanitized_versions = []
        for v in cleaned["aosp_versions"]:
            if not isinstance(v, dict) or not v.get("id"):
                continue
            v_id = str(v["id"]).strip().lower()
            if not v_id:
                continue
            v_name = str(v.get("name") or v_id).strip()
            v_api = int(v["api_level"]) if v.get("api_level") else None
            is_auto = bool(v_id == "auto" or v.get("is_auto"))
            is_custom = bool(v_id not in {"auto", "a16", "a15", "a14", "a13", "a12"})
            sanitized_versions.append({
                "id": v_id,
                "name": v_name,
                "api_level": v_api,
                "is_auto": is_auto,
                "is_custom": is_custom,
            })
        cleaned["aosp_versions"] = sanitized_versions

    # Clean and validate sources if passed
    if "sources" in cleaned and isinstance(cleaned["sources"], list):
        public_sources = []
        private_sources = []
        for i, s in enumerate(cleaned["sources"]):
            if not isinstance(s, dict):
                continue
            local_path = str(s.get("local_path", "")).strip()
            if not local_path:
                continue
            name = str(s.get("name", "")).strip() or f"Source {i+1}"
            s_id = str(s.get("id", "")).strip()
            if not s_id:
                s_id = local_path.replace("\\", "/").rstrip("/").split("/")[-1].lower().replace("-", "_").replace(".", "_")
            is_priv = bool(s.get("visibility") == "private" or s.get("is_private"))
            entry = {
                "id": s_id,
                "name": name,
                "local_path": local_path,
                "repo_url": str(s.get("repo_url", "")).strip(),
                "project": str(s.get("project", "")).strip() or "aosp_aaos",
                "aosp_version": str(s.get("aosp_version", "")).strip(),
                "api_level": int(s.get("api_level")) if s.get("api_level") else None,
                "branch": str(s.get("branch", "")).strip(),
                "enabled": bool(s.get("enabled", True)),
                "visibility": "private" if is_priv else "public",
                "is_private": is_priv,
            }
            if is_priv:
                private_sources.append(entry)
            else:
                public_sources.append(entry)

        save_private_sources(private_sources)
        cleaned["sources"] = public_sources
        if public_sources and not cleaned.get("local_path"):
            cleaned["local_path"] = public_sources[0]["local_path"]
            cleaned["repo_url"] = public_sources[0]["repo_url"]

    # Read existing static config only
    path = _config_path()
    current = {}
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    current.update(cleaned)
    for k in ["last_sync", "indexed_count"]:
        current.pop(k, None)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_mcp_skill_config()


def resolve_skill_dir() -> Path:
    """Resolve primary skill directory (backward-compatible)."""
    cfg = get_mcp_skill_config()
    rel = cfg.get("local_path") or DEFAULT_SKILL_LOCAL_PATH
    root = _repo_root()
    p = Path(rel)
    if not p.is_dir():
        p = (root / rel).resolve()
    if p.is_dir():
        return p
    candidates = [
        root / "repos" / "telua_skill" / "Java_Android",
        root / "telua_skill" / "Java_Android",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return p


def get_all_configured_sources() -> List[dict]:
    """Return all configured sources (public config + private overlay) with resolution status."""
    cfg = get_mcp_skill_config()
    public_sources = cfg.get("sources") or DEFAULT_SOURCES
    private_sources = get_private_sources()

    # Combine public and private sources
    seen_ids = set()
    combined = []
    # Private sources come first or override matching IDs
    for s in private_sources:
        s_copy = dict(s)
        s_copy["visibility"] = "private"
        s_copy["is_private"] = True
        combined.append(s_copy)
        seen_ids.add(s_copy.get("id"))

    for s in public_sources:
        if s.get("id") not in seen_ids:
            s_copy = dict(s)
            s_copy["visibility"] = s_copy.get("visibility", "public")
            s_copy["is_private"] = (s_copy.get("visibility") == "private")
            combined.append(s_copy)
            seen_ids.add(s_copy.get("id"))

    sources = combined
    root = _repo_root()
    result = []

    for s in sources:
        rel = str(s.get("local_path", "")).strip()
        # 1. Try absolute or direct path
        p = Path(rel)
        if not p.is_dir():
            # 2. Try relative to repo root
            p = (root / rel).resolve()
        if not p.is_dir():
            # 3. Try under repos/
            for cand in [root / rel, root / "repos" / rel]:
                if cand.is_dir():
                    p = cand.resolve()
                    break

        exists = p.is_dir()
        s_id = s.get("id") or (p.name if exists else (rel.replace("\\", "/").rstrip("/").split("/")[-1] or "source"))
        detected = detect_aosp_version_from_path(p if exists else None)
        final_proj = str(s.get("project", "")).strip() or detected.get("project") or "aosp_aaos"
        final_ver = str(s.get("aosp_version", "")).strip() or detected.get("aosp_version") or ""
        final_api = s.get("api_level") or detected.get("api_level")
        final_br = str(s.get("branch", "")).strip() or detected.get("branch") or ""

        result.append({
            "id": s_id,
            "name": s.get("name") or s_id,
            "repo_url": s.get("repo_url", ""),
            "local_path": rel,
            "project": final_proj,
            "aosp_version": final_ver,
            "api_level": final_api,
            "branch": final_br,
            "enabled": s.get("enabled", True),
            "visibility": s.get("visibility", "public"),
            "is_private": bool(s.get("visibility") == "private" or s.get("is_private")),
            "exists": exists,
            "resolved_path": str(p) if exists else "",
            "dir": p if exists else None,
        })
    return result


def resolve_skill_sources() -> List[dict]:
    """Resolve all configured and enabled skill source repositories."""
    sources = get_all_configured_sources()
    return [s for s in sources if s.get("enabled", True) and s.get("exists", False)]


SKILL_VALID_EXTS = {".md", ".java", ".sh", ".bat", ".config", ".json", ".template"}
# Directories pruned while walking (never descended into). ".repo" and "out" are
# added for AOSP trees: they hold repo metadata / build output (tens of GB).
SKILL_IGNORE_DIRS = {
    ".git", ".github", ".claude", "node_modules", "target", "build", ".idea",
    ".repo", "out", "__pycache__", ".gradle",
}
SKILL_CODE_EXTS = {".java", ".kt", ".kts", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
                   ".py", ".js", ".ts", ".rs", ".go", ".aidl"}


def _parse_skill_metadata_text(default_title: str, head_text: str) -> Tuple[str, str]:
    """Extract (title, summary) from the first ~1500 chars of a file."""
    title = default_title
    summary = ""
    try:
        # Parse YAML frontmatter if available
        if head_text.startswith("---"):
            fm_end = head_text.find("---", 3)
            if fm_end != -1:
                fm_text = head_text[3:fm_end]
                for line in fm_text.splitlines():
                    line = line.strip()
                    if line.startswith("name:"):
                        title = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        summary = line.split(":", 1)[1].strip()

        # Fallback to markdown heading
        if not summary or title == default_title:
            for line in head_text.splitlines():
                line = line.strip()
                if line.startswith("#") and title == default_title:
                    title = line.lstrip("#").strip()
                    break
        if not summary:
            # Pick first non-empty lines
            lines = [l.strip() for l in head_text.splitlines() if l.strip() and not l.strip().startswith("---") and not l.strip().startswith("#")]
            summary = " ".join(lines[:3]).strip()
    except Exception:
        pass
    return title, summary[:300]


def _parse_skill_metadata(file_path: Path, ext: str) -> Tuple[str, str]:
    """Extract (title, summary) from file content or YAML frontmatter."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            head_text = fh.read(1500)
    except Exception:
        return file_path.name, ""
    return _parse_skill_metadata_text(file_path.name, head_text)


def _skill_category(s_id: str, rel: str) -> str:
    parts = rel.split("/")
    if s_id == "claude_code_java" and parts[0] == "skills" and len(parts) > 1:
        return parts[1]  # e.g. "concurrency-review", "spring-boot-patterns"
    return parts[0] if len(parts) > 1 else "root"


def _iter_source_files(base_dir, should_stop=None):
    """Fast iterative directory walk (os.scandir) that prunes ignored dirs.

    Yields (full_path, rel_posix, ext, size, mtime). Unlike Path.rglob, ignored
    directories (.git, .repo, out, ...) are never descended into, which matters a
    lot on 100-200 GB AOSP trees.
    """
    base = os.path.abspath(str(base_dir))
    prefix = base.rstrip("\\/") + os.sep
    stack = [base]
    n = 0
    while stack:
        if should_stop is not None and should_stop():
            return
        cur = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in SKILL_IGNORE_DIRS:
                            stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext not in SKILL_VALID_EXTS:
                        continue
                    st = entry.stat(follow_symlinks=False)
                    full = entry.path
                    rel = full[len(prefix):] if full.startswith(prefix) else os.path.relpath(full, base)
                    n += 1
                    if should_stop is not None and (n & 1023) == 0 and should_stop():
                        return
                    yield full, rel.replace("\\", "/"), ext, st.st_size, st.st_mtime
                except OSError:
                    continue


def _resolve_sources_with_fallback() -> List[dict]:
    sources = resolve_skill_sources()
    if not sources:
        primary = resolve_skill_dir()
        if primary.is_dir():
            sources = [{
                "id": "telua_skill",
                "name": "Telua Java/Android",
                "repo_url": DEFAULT_SKILL_REPO_URL,
                "local_path": DEFAULT_SKILL_LOCAL_PATH,
                "dir": primary,
            }]
    return sources


def _make_skill_entry(src: dict, rel: str, ext: str, size: int, title: str = "", summary: str = "") -> dict:
    s_id = src["id"]
    name = rel.rsplit("/", 1)[-1]
    return {
        "name": name,
        "title": title or name,
        "rel_path": rel,
        "scoped_path": f"{s_id}/{rel}",
        "source_id": s_id,
        "source_name": src["name"],
        "project": src.get("project", "aosp_aaos"),
        "aosp_version": src.get("aosp_version", ""),
        "api_level": src.get("api_level"),
        "branch": src.get("branch", ""),
        "category": _skill_category(s_id, rel),
        "size_bytes": size,
        "ext": ext,
        "summary": summary,
        "visibility": src.get("visibility", "public"),
        "is_private": bool(src.get("visibility") == "private" or src.get("is_private")),
    }


# Directory listing cache: walking a 200 GB tree takes a long time, and the web UI
# calls /api/ai/mcp/config + /api/ai/mcp/skills together on every refresh.
_SCAN_CACHE: dict = {"key": None, "ts": 0.0, "items": None}
_SCAN_LOCK = threading.Lock()
SCAN_CACHE_TTL_S = 120.0


def invalidate_skill_scan_cache() -> None:
    with _SCAN_LOCK:
        _SCAN_CACHE.update({"key": None, "ts": 0.0, "items": None})


def _sources_cache_key(sources: List[dict]) -> str:
    return json.dumps([{k: (str(v) if isinstance(v, Path) else v) for k, v in s.items()} for s in sources],
                      sort_keys=True, default=str)


def scan_skills(source_id: Optional[str] = None, limit: Optional[int] = None, with_meta: bool = True) -> List[dict]:
    """Scan all skill, rule, template, and script files across all configured skill sources.

    - The directory walk result is cached for SCAN_CACHE_TTL_S seconds (concurrent
      callers wait for one walk instead of walking the tree twice).
    - with_meta=False skips reading file heads (title/summary) -> just a listing.
    - limit caps the number of returned entries (metadata only parsed for those).
    """
    sources = _resolve_sources_with_fallback()
    if not sources:
        return []

    with _SCAN_LOCK:
        key = _sources_cache_key(sources)
        cached = _SCAN_CACHE.get("items")
        if cached is not None and _SCAN_CACHE.get("key") == key and (time.time() - _SCAN_CACHE["ts"]) < SCAN_CACHE_TTL_S:
            items = cached
        else:
            items = []
            for src in sources:
                for full, rel, ext, size, _mtime in _iter_source_files(src["dir"]):
                    entry = _make_skill_entry(src, rel, ext, size)
                    entry["_full"] = full
                    items.append(entry)
            items.sort(key=lambda s: (s["source_id"], s["category"], s["name"]))
            _SCAN_CACHE.update({"key": key, "ts": time.time(), "items": items})

    if source_id:
        sid = source_id.lower()
        items = [s for s in items if s["source_id"].lower() == sid]
    if limit is not None and limit >= 0:
        items = items[:limit]

    out = []
    for s in items:
        d = dict(s)
        full = d.pop("_full", None)
        if with_meta and full:
            d["title"], d["summary"] = _parse_skill_metadata_text(d["name"], _read_head(full))
        out.append(d)
    return out


def _read_head(full_path: str, n: int = 1500) -> str:
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read(n)
    except Exception:
        return ""


def get_skill_content(rel_path: str) -> Optional[dict]:
    """Retrieve the full text content of a skill file by name, relative path, or scoped path."""
    sources = resolve_skill_sources()
    if not sources:
        primary = resolve_skill_dir()
        if primary.is_dir():
            sources = [{"id": "telua_skill", "name": "Telua Java/Android", "dir": primary, "local_path": DEFAULT_SKILL_LOCAL_PATH}]
        else:
            return None

    clean_query = rel_path.strip().lstrip("/\\")

    for src in sources:
        base_dir = src["dir"]
        s_id = src["id"]
        s_name = src["name"]

        target_file = None
        target_rel = None

        # 1. Match scoped path: e.g. "claude_code_java/skills/concurrency-review/SKILL.md"
        if clean_query.startswith(f"{s_id}/"):
            sub_query = clean_query[len(s_id) + 1:]
            candidate = (base_dir / sub_query).resolve()
            if candidate.is_file() and str(candidate).startswith(str(base_dir.resolve())):
                target_file = candidate
                target_rel = sub_query

        # 2. Match exact relative path in base_dir
        if not target_file:
            candidate = (base_dir / clean_query).resolve()
            if candidate.is_file() and str(candidate).startswith(str(base_dir.resolve())):
                target_file = candidate
                target_rel = clean_query

        # 3. Match skill folder name (e.g. "concurrency-review" -> SKILL.md)
        if not target_file:
            for skill_dir in [base_dir / "skills" / clean_query, base_dir / clean_query]:
                if skill_dir.is_dir():
                    for cand_name in ["SKILL.md", "README.md"]:
                        cand_file = skill_dir / cand_name
                        if cand_file.is_file():
                            target_file = cand_file
                            target_rel = cand_file.relative_to(base_dir).as_posix()
                            break
                if target_file:
                    break

        # 4. Search by filename across files in this source
        if not target_file:
            for f in base_dir.rglob("*.*"):
                if f.name.lower() == clean_query.lower() or f.stem.lower() == clean_query.lower():
                    target_file = f
                    target_rel = f.relative_to(base_dir).as_posix()
                    break

        if target_file and target_file.is_file():
            try:
                content = target_file.read_text(encoding="utf-8", errors="replace")
                parts = target_rel.split("/")
                if s_id == "claude_code_java" and parts[0] == "skills" and len(parts) > 1:
                    category = parts[1]
                else:
                    category = parts[0] if len(parts) > 1 else "root"

                title, summary = _parse_skill_metadata(target_file, target_file.suffix.lower())

                return {
                    "name": target_file.name,
                    "title": title,
                    "rel_path": target_rel,
                    "scoped_path": f"{s_id}/{target_rel}",
                    "source_id": s_id,
                    "source_name": s_name,
                    "category": category,
                    "content": content,
                    "size": len(content),
                    "summary": summary,
                }
            except Exception:
                continue

    return None


HASH_FILE_CANDIDATES = _ai_cfg_candidates("mcp_skills_hashes.json")


def _load_skill_hashes() -> dict:
    root = _repo_root()
    for cand in HASH_FILE_CANDIDATES:
        p = root / cand
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _save_skill_hashes(hashes: dict):
    path = _ai_overlay_file("mcp_skills_hashes.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Compact + atomic write: the map can hold millions of entries for large
    # sources and is checkpointed periodically during a sync.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(hashes, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


_CHROMA_LOCK = threading.Lock()

# ------------------------------------------------------------------------------
# Threaded sync pipeline with live progress
#
#   walker thread (1)  --file_q-->  reader threads (N)  --doc_q-->  writer thread (1)
#   os.scandir, prune               read + md5 + chunk              ChromaDB upsert
#
# - Queues are bounded -> memory stays flat even for 100-200 GB sources.
# - Only ONE thread writes to ChromaDB (SQLite / HNSW index is not happy with
#   concurrent writers); readers parallelise disk I/O + chunking.
# - Incremental: files whose (size, mtime) are unchanged are skipped WITHOUT
#   reading them; hashes are checkpointed every 30 s so a crash/cancel resumes.
# - Progress lives in _SYNC_PROGRESS; Flask only reads a snapshot of it.
# ------------------------------------------------------------------------------

_SYNC_STATE_LOCK = threading.Lock()
_SYNC_CANCEL = threading.Event()
_SYNC_PROGRESS: dict = {}
_HASH_CHECKPOINT_S = 30.0


def _new_progress(trigger: str) -> dict:
    return {
        "running": True,
        "phase": "starting",
        "trigger": trigger,
        "started_at": time.time(),
        "finished_at": None,
        "sources_total": 0,
        "current_source": "",
        "scan_done": False,
        "files_discovered": 0,
        "bytes_discovered": 0,
        "files_processed": 0,
        "bytes_processed": 0,
        "files_indexed": 0,
        "files_skipped": 0,
        "files_too_large": 0,
        "files_failed": 0,
        "chunks_written": 0,
        "batches_written": 0,
        "current_file": "",
        "errors": 0,
        "last_error": "",
        "reader_threads": 0,
        "cancel_requested": False,
        "result": None,
    }


def _prog_set(**kw) -> None:
    with _SYNC_STATE_LOCK:
        _SYNC_PROGRESS.update(kw)


def _prog_inc(**kw) -> None:
    with _SYNC_STATE_LOCK:
        for k, v in kw.items():
            _SYNC_PROGRESS[k] = _SYNC_PROGRESS.get(k, 0) + v


def _prog_error(msg: str) -> None:
    with _SYNC_STATE_LOCK:
        _SYNC_PROGRESS["errors"] = _SYNC_PROGRESS.get("errors", 0) + 1
        _SYNC_PROGRESS["last_error"] = msg[:500]


def get_sync_progress() -> dict:
    """Thread-safe snapshot of the current / last sync job (cheap; safe to poll)."""
    with _SYNC_STATE_LOCK:
        p = dict(_SYNC_PROGRESS)
    if not p:
        return {"running": False, "phase": "idle"}
    end = p.get("finished_at") or time.time()
    elapsed = max(0.001, end - p["started_at"])
    fps = p["files_processed"] / elapsed
    p["elapsed_s"] = round(elapsed, 1)
    p["files_per_s"] = round(fps, 1)
    p["mb_per_s"] = round(p["bytes_processed"] / elapsed / 1048576.0, 2)
    p["percent"] = None
    p["eta_s"] = None
    if p["files_discovered"]:
        if p["scan_done"]:
            p["percent"] = round(min(100.0, 100.0 * p["files_processed"] / p["files_discovered"]), 1)
            if p["running"] and fps > 0:
                p["eta_s"] = round((p["files_discovered"] - p["files_processed"]) / fps)
    return p


def _cfg_int(cfg: dict, key: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(cfg.get(key, default))))
    except (TypeError, ValueError):
        return default


def _skill_doc_id(s_id: str, rel: str) -> str:
    clean_rel = rel.replace('/', '_').replace('\\', '_').replace('.', '_').replace('-', '_')
    return f"skill_{s_id}_{clean_rel}"


def _run_sync_pipeline(collection_name: str, incremental: bool) -> dict:
    """Run the walker/readers/writer pipeline. Caller must hold _CHROMA_LOCK."""
    import queue

    sources = _resolve_sources_with_fallback()
    if not sources:
        return {"ok": False, "error": "No active skill sources found to index.", "indexed": 0}

    try:
        import chromadb
    except ImportError:
        return {"ok": False, "error": "chromadb package not installed. Run: pip install chromadb", "indexed": 0}

    from .code_structure_engine import CodeStructureEngine

    cfg = get_mcp_skill_config()
    n_readers = _cfg_int(cfg, "sync_reader_threads", min(8, max(2, os.cpu_count() or 4)), 1, 32)
    batch_size = _cfg_int(cfg, "sync_batch_size", 64, 8, 1000)
    max_file_bytes = _cfg_int(cfg, "sync_max_file_kb", 2048, 16, 102400) * 1024

    chroma_dir = _repo_root() / "ai_agent" / "data"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    col = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "Telua Multi-Source Java/Android & Agent Skills Knowledge Base"}
    )

    previous_hashes = _load_skill_hashes()      # read-only snapshot for readers
    current_hashes = dict(previous_hashes)      # owned by the writer thread only

    _prog_set(phase="indexing", sources_total=len(sources), reader_threads=n_readers)

    file_q: "queue.Queue" = queue.Queue(maxsize=50000)
    doc_q: "queue.Queue" = queue.Queue(maxsize=max(64, n_readers * 16))
    abort = threading.Event()
    SENTINEL = None

    def stopped() -> bool:
        return abort.is_set() or _SYNC_CANCEL.is_set()

    def put(q, item) -> bool:
        while True:
            try:
                q.put(item, timeout=0.5)
                return True
            except queue.Full:
                if stopped():
                    return False

    # ---------------- walker ----------------
    def walker():
        try:
            for src in sources:
                if stopped():
                    break
                _prog_set(current_source=src.get("name") or src["id"])
                for full, rel, ext, size, mtime in _iter_source_files(src["dir"], stopped):
                    if not put(file_q, (src, full, rel, ext, size, mtime)):
                        return
                    _prog_inc(files_discovered=1, bytes_discovered=size)
        except Exception as e:
            _prog_error(f"scan: {e}")
        finally:
            _prog_set(scan_done=True)
            for _ in range(n_readers):
                put(file_q, SENTINEL)

    # ---------------- readers ----------------
    def build_records(src, rel, ext, size, content):
        s_id = src["id"]
        doc_id = _skill_doc_id(s_id, rel)
        title, summary = _parse_skill_metadata_text(rel.rsplit("/", 1)[-1], content[:1500])
        s = _make_skill_entry(src, rel, ext, size, title, summary)
        is_priv = s["is_private"]
        metadata = {
            "source_id": s_id,
            "source_name": s["source_name"],
            "project": s.get("project") or "aosp_aaos",
            "aosp_version": s.get("aosp_version") or "",
            "api_level": s.get("api_level") or 0,
            "branch": s.get("branch") or "",
            "category": s["category"],
            "name": s["name"],
            "title": s["title"],
            "rel_path": rel,
            "scoped_path": s["scoped_path"],
            "source": f"{s_id}/{rel}",
            "ext": ext,
            "type": "agent_skill",
            "visibility": "private" if is_priv else "public",
            "is_private": is_priv,
            "indexed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if ext in SKILL_CODE_EXTS:
            # AST / Structure-Aware Semantic Chunking for source code
            chunks = CodeStructureEngine.chunk_code_for_vector_db(content, rel, metadata, max_chunk_chars=4000)
            return [(ch["id"], ch["document"], ch["metadata"]) for ch in chunks]
        full_doc = (
            f"SOURCE: {s['source_name']} ({s_id})\n"
            f"CATEGORY: {s['category']}\n"
            f"TITLE: {s['title']}\n"
            f"FILE: {s['name']} (Path: {s['scoped_path']})\n"
            f"SUMMARY: {s['summary']}\n\n"
            f"{content}"
        )
        return [(doc_id, full_doc[:15000], metadata)]

    def reader():
        while True:
            try:
                item = file_q.get(timeout=0.5)
            except queue.Empty:
                if stopped():
                    return
                continue
            if item is SENTINEL or stopped():
                put(doc_q, SENTINEL)
                return
            src, full, rel, ext, size, mtime = item
            doc_id = _skill_doc_id(src["id"], rel)
            try:
                if size > max_file_bytes:
                    _prog_inc(files_processed=1, files_too_large=1, bytes_processed=size)
                    continue
                prev = previous_hashes.get(doc_id) if incremental else None
                mtime_r = round(mtime, 3)
                # Fast path: unchanged size + mtime -> skip without reading the file
                if isinstance(prev, dict) and prev.get("s") == size and prev.get("m") == mtime_r:
                    _prog_inc(files_processed=1, files_skipped=1, bytes_processed=size)
                    continue
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                if not content.strip():
                    _prog_inc(files_processed=1, files_skipped=1, bytes_processed=size)
                    continue
                file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                hash_entry = {"h": file_hash, "m": mtime_r, "s": size}
                prev_h = prev.get("h") if isinstance(prev, dict) else prev
                if incremental and prev_h == file_hash:
                    # Content unchanged (only touched / legacy hash format) -> refresh entry only
                    put(doc_q, ("hash", doc_id, hash_entry, None))
                    _prog_inc(files_processed=1, files_skipped=1, bytes_processed=size)
                    continue
                records = build_records(src, rel, ext, size, content)
                _prog_set(current_file=f"{src['id']}/{rel}")
                put(doc_q, ("docs", doc_id, hash_entry, records))
                _prog_inc(files_processed=1, bytes_processed=size)
            except Exception as e:
                _prog_inc(files_processed=1, files_failed=1, bytes_processed=size)
                _prog_error(f"{src['id']}/{rel}: {e}")

    # ---------------- writer (single ChromaDB writer) ----------------
    def writer():
        ids: list = []
        docs: list = []
        metas: list = []
        seen: set = set()          # per-batch: Chroma rejects duplicate ids in one upsert
        pending: list = []         # (doc_id, hash_entry, is_indexed_file)
        last_save = time.time()

        def flush():
            nonlocal ids, docs, metas, seen, pending, last_save
            ok = True
            if ids:
                try:
                    col.upsert(ids=ids, documents=docs, metadatas=metas)
                    _prog_inc(chunks_written=len(ids), batches_written=1)
                except Exception as e:
                    ok = False
                    _prog_error(f"upsert: {e}")
            n_files = sum(1 for p in pending if p[2])
            if ok:
                for did, he, _ in pending:
                    current_hashes[did] = he
                if n_files:
                    _prog_inc(files_indexed=n_files)
            elif n_files:
                _prog_inc(files_failed=n_files)
            ids, docs, metas, seen, pending = [], [], [], set(), []
            if time.time() - last_save > _HASH_CHECKPOINT_S:
                _save_skill_hashes(current_hashes)
                last_save = time.time()

        sentinels = 0
        try:
            while sentinels < n_readers:
                try:
                    item = doc_q.get(timeout=0.5)
                except queue.Empty:
                    if stopped():
                        break
                    continue
                if item is SENTINEL:
                    sentinels += 1
                    continue
                kind, did, he, records = item
                if kind == "docs":
                    for rid, doc, meta in records:
                        if rid in seen:
                            continue
                        seen.add(rid)
                        ids.append(rid)
                        docs.append(doc)
                        metas.append(meta)
                    pending.append((did, he, True))
                else:
                    pending.append((did, he, False))
                if len(ids) >= batch_size or len(pending) >= 2000:
                    flush()
            flush()
        except Exception as e:
            _prog_error(f"writer: {e}")
            abort.set()
        finally:
            try:
                _save_skill_hashes(current_hashes)
            except Exception as e:
                _prog_error(f"save hashes: {e}")

    threads = [threading.Thread(target=walker, name="ChromaSyncWalker", daemon=True)]
    threads += [threading.Thread(target=reader, name=f"ChromaSyncReader-{i}", daemon=True) for i in range(n_readers)]
    threads.append(threading.Thread(target=writer, name="ChromaSyncWriter", daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    cancelled = _SYNC_CANCEL.is_set()
    p = get_sync_progress()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not cancelled and not abort.is_set():
        save_mcp_skill_state({"last_sync": timestamp, "indexed_count": p["files_discovered"]})
    invalidate_skill_scan_cache()

    return {
        "ok": not cancelled and not abort.is_set(),
        "cancelled": cancelled,
        "error": p.get("last_error", "") if abort.is_set() else "",
        "indexed": p["files_indexed"],
        "chunks": p["chunks_written"],
        "skipped": p["files_skipped"],
        "too_large": p["files_too_large"],
        "failed": p["files_failed"],
        "errors": p["errors"],
        "total_files": p["files_discovered"],
        "sources_count": len(sources),
        "elapsed_s": p["elapsed_s"],
        "last_sync": timestamp,
        "collection": collection_name,
        "chroma_path": str(chroma_dir),
    }


def _run_sync_job(collection_name: str, incremental: bool) -> dict:
    """Execute a sync job (caller holds _CHROMA_LOCK and has reset the progress)."""
    try:
        res = _run_sync_pipeline(collection_name, incremental)
    except Exception as e:
        _prog_error(str(e))
        res = {"ok": False, "error": str(e), "indexed": 0}
    phase = "cancelled" if res.get("cancelled") else ("done" if res.get("ok") else "error")
    _prog_set(running=False, phase=phase, finished_at=time.time(), result=res, current_file="")
    return res


def _reset_progress(trigger: str) -> None:
    _SYNC_CANCEL.clear()
    with _SYNC_STATE_LOCK:
        _SYNC_PROGRESS.clear()
        _SYNC_PROGRESS.update(_new_progress(trigger))


def sync_skills_to_chroma(collection_name: str = "telua_knowledge", incremental: bool = True,
                          trigger: str = "manual") -> dict:
    """Blocking sync of all configured sources into ChromaDB (used by scheduler / MCP CLI).

    If incremental=True, unchanged files (size+mtime, then MD5) are not re-embedded.
    Returns immediately with busy=True if another sync is already running.
    """
    if not _CHROMA_LOCK.acquire(blocking=False):
        return {"ok": False, "busy": True, "error": "A ChromaDB sync is already running.", "indexed": 0}
    try:
        _reset_progress(trigger)
        return _run_sync_job(collection_name, incremental)
    finally:
        _CHROMA_LOCK.release()


def start_sync_job(collection_name: str = "telua_knowledge", incremental: bool = True,
                   trigger: str = "web") -> dict:
    """Start a sync in a background thread and return immediately (for Flask)."""
    if not _CHROMA_LOCK.acquire(blocking=False):
        return {"ok": True, "started": False, "already_running": True, "progress": get_sync_progress()}
    try:
        _reset_progress(trigger)

        def _bg():
            try:
                _run_sync_job(collection_name, incremental)
            finally:
                _CHROMA_LOCK.release()

        threading.Thread(target=_bg, name="TeluaChromaSync", daemon=True).start()
    except Exception:
        _CHROMA_LOCK.release()
        raise
    return {"ok": True, "started": True, "progress": get_sync_progress()}


def cancel_sync_job() -> dict:
    """Request cancellation of the running sync (already-written batches are kept)."""
    if not get_sync_progress().get("running"):
        return {"ok": False, "error": "No sync is running."}
    _SYNC_CANCEL.set()
    _prog_set(cancel_requested=True, phase="cancelling")
    return {"ok": True}


# ==============================================================================
# Background Scheduler (Startup + Periodic Timer e.g. 3h, 6h)
# ==============================================================================

_SCHEDULER_THREAD = None
_STOP_EVENT = threading.Event()


def start_mcp_background_scheduler():
    """Start background scheduler for ChromaDB skills training.
    
    1. Triggers an initial sync 3 seconds after web start.
    2. Runs an incremental sync check every N hours (default 3h or 6h).
    """
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD is not None and _SCHEDULER_THREAD.is_alive():
        return

    _STOP_EVENT.clear()

    def _worker():
        # 1. Startup sync (delay 3 seconds so server finishes binding port)
        if _STOP_EVENT.wait(3.0):
            return
        cfg = get_mcp_skill_config()
        if cfg.get("auto_sync_enabled", True) and cfg.get("sync_on_startup", True):
            try:
                res = sync_skills_to_chroma(incremental=True, trigger="startup")
                sys.stderr.write(
                    f"[Telua MCP Sync] Startup sync completed: {res.get('indexed', 0)} updated, "
                    f"{res.get('skipped', 0)} cached (total {res.get('total_files', 0)} skills across {res.get('sources_count', 0)} sources).\n"
                )
                sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"[Telua MCP Sync] Startup sync warning: {e}\n")
                sys.stderr.flush()

        # 2. Periodic loop (checks every interval: 3h, 6h, etc.)
        while not _STOP_EVENT.is_set():
            cfg = get_mcp_skill_config()
            interval_val = cfg.get("sync_interval_hours", 3)
            try:
                interval_hours = float(interval_val)
            except (ValueError, TypeError):
                interval_hours = 3.0

            sleep_total = max(180, int(interval_hours * 3600))
            for _ in range(sleep_total // 30):
                if _STOP_EVENT.wait(30.0):
                    return

            cfg = get_mcp_skill_config()
            if cfg.get("auto_sync_enabled", True):
                try:
                    res = sync_skills_to_chroma(incremental=True, trigger="scheduled")
                    if res.get("indexed", 0) > 0:
                        sys.stderr.write(
                            f"[Telua MCP Sync] Periodic ({interval_hours}h) sync: {res.get('indexed')} updated.\n"
                        )
                        sys.stderr.flush()
                except Exception as e:
                    sys.stderr.write(f"[Telua MCP Sync] Periodic sync error: {e}\n")
                    sys.stderr.flush()

    _SCHEDULER_THREAD = threading.Thread(target=_worker, name="TeluaMcpSyncScheduler", daemon=True)
    _SCHEDULER_THREAD.start()


def stop_mcp_background_scheduler():
    """Stop the background scheduler thread."""
    _STOP_EVENT.set()


# ==============================================================================
# Model Context Protocol (MCP) JSON-RPC 2.0 Server Interface
# Can be run via: python web/ai/telua_mcp_skill.py --mcp
# ==============================================================================

def run_mcp_stdio_server():
    """Run Model Context Protocol (MCP) server over standard I/O (JSON-RPC 2.0)."""
    sys.stderr.write("Starting Telua MCP Multi-Skill Server (telua_skill & claude-code-java)...\n")
    sys.stderr.flush()

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            request = json.loads(line)
            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params") or {}

            response = {"jsonrpc": "2.0", "id": req_id}

            if method == "initialize":
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "telua-multi-skill-mcp",
                        "version": "1.1.0",
                        "description": "Model Context Protocol server for Telua Android Automotive & Claude Code Java Agent skills"
                    },
                    "capabilities": {
                        "tools": {}
                    }
                }
            elif method == "tools/list":
                response["result"] = {
                    "tools": [
                        {
                            "name": "list_skills",
                            "description": "List all Android Automotive, Java, AAOS VHAL, and Claude Code Java Agent skills across telua_skill and claude-code-java.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "source": {"type": "string", "description": "Filter by source: 'telua_skill' or 'claude_code_java'"},
                                    "category": {"type": "string", "description": "Filter by category: rules, examples, design, concurrency-review, spring-boot-patterns, security-audit, etc."}
                                }
                            }
                        },
                        {
                            "name": "get_skill",
                            "description": "Retrieve full source code or rule guide for a specific skill (e.g. 'concurrency-review', 'spring-boot-patterns', 'BinderServiceTemplate.java', 'thread_safety_concurrency_rule.md').",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "rel_path": {"type": "string", "description": "Relative path, skill name, or scoped path"}
                                },
                                "required": ["rel_path"]
                            }
                        },
                        {
                            "name": "sync_to_chroma",
                            "description": "Sync and index all skills from all configured sources into the local ChromaDB vector database (ai_agent/data).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {}
                            }
                        }
                    ]
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments") or {}

                if tool_name == "list_skills":
                    src = args.get("source")
                    cat = args.get("category")
                    all_s = scan_skills(source_id=src)
                    if cat:
                        all_s = [s for s in all_s if s["category"].lower() == cat.lower()]
                    response["result"] = {
                        "content": [
                            {"type": "text", "text": json.dumps(all_s, indent=2)}
                        ]
                    }
                elif tool_name == "get_skill":
                    rel = args.get("rel_path") or ""
                    res = get_skill_content(rel)
                    if res:
                        response["result"] = {
                            "content": [
                                {"type": "text", "text": res["content"]}
                            ]
                        }
                    else:
                        response["error"] = {"code": -32602, "message": f"Skill not found: {rel}"}
                elif tool_name == "sync_to_chroma":
                    res = sync_skills_to_chroma()
                    response["result"] = {
                        "content": [
                            {"type": "text", "text": json.dumps(res, indent=2)}
                        ]
                    }
                else:
                    response["error"] = {"code": -32601, "message": f"Tool not found: {tool_name}"}
            else:
                response["error"] = {"code": -32601, "message": f"Method not supported: {method}"}

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if "--mcp" in sys.argv or "--stdio" in sys.argv:
        run_mcp_stdio_server()
    else:
        # CLI test mode
        cfg = get_mcp_skill_config()
        skills = scan_skills()
        print(f"Telua MCP Multi-Skill Provider: found {len(skills)} skills across {len(resolve_skill_sources())} sources.")
        by_src = {}
        for s in skills:
            by_src[s['source_id']] = by_src.get(s['source_id'], 0) + 1
        print("Skills per source:", by_src)
        categories = sorted(set(s['category'] for s in skills))
        print(f"Total categories ({len(categories)}):", categories[:10], "...")
        if "--sync" in sys.argv:
            print("Syncing all sources to ChromaDB...")
            res = sync_skills_to_chroma()
            print("Sync Result:", res)
