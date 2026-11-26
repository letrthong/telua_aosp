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
    },
    {
        "id": "claude_code_java",
        "name": "Claude Code Java Agent Skills",
        "repo_url": "https://github.com/decebals/claude-code-java.git",
        "local_path": "repos/claude-code-java",
        "enabled": True,
    },
]

CONFIG_FILE_CANDIDATES = [
    "config/overlay/mcp_skills_config.json",
    "config/mcp_skills_config.json",
]
STATE_FILE_PATH = "config/overlay/mcp_skills_state.json"


def _config_path() -> Path:
    root = _repo_root()
    for cand in CONFIG_FILE_CANDIDATES:
        p = root / cand
        if p.is_file():
            return p
    return root / "config" / "mcp_skills_config.json"


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

    # Clean and validate sources if passed
    if "sources" in cleaned and isinstance(cleaned["sources"], list):
        cleaned_sources = []
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
            cleaned_sources.append({
                "id": s_id,
                "name": name,
                "local_path": local_path,
                "repo_url": str(s.get("repo_url", "")).strip(),
                "enabled": bool(s.get("enabled", True)),
            })
        cleaned["sources"] = cleaned_sources
        if cleaned_sources and not cleaned.get("local_path"):
            cleaned["local_path"] = cleaned_sources[0]["local_path"]
            cleaned["repo_url"] = cleaned_sources[0]["repo_url"]

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
    """Return all configured sources with resolution status (exists, resolved_path, enabled)."""
    cfg = get_mcp_skill_config()
    sources = cfg.get("sources") or DEFAULT_SOURCES
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
        result.append({
            "id": s_id,
            "name": s.get("name") or s_id,
            "repo_url": s.get("repo_url", ""),
            "local_path": rel,
            "enabled": s.get("enabled", True),
            "exists": exists,
            "resolved_path": str(p) if exists else "",
            "dir": p if exists else None,
        })
    return result


def resolve_skill_sources() -> List[dict]:
    """Resolve all configured and enabled skill source repositories."""
    sources = get_all_configured_sources()
    return [s for s in sources if s.get("enabled", True) and s.get("exists", False)]


def _parse_skill_metadata(file_path: Path, ext: str) -> Tuple[str, str]:
    """Extract (title, summary) from file content or YAML frontmatter."""
    title = file_path.name
    summary = ""
    try:
        head_text = file_path.read_text(encoding="utf-8", errors="ignore")[:1500]
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
        if not summary or title == file_path.name:
            for line in head_text.splitlines():
                line = line.strip()
                if line.startswith("#") and title == file_path.name:
                    title = line.lstrip("#").strip()
                    break
        if not summary:
            # Pick first non-empty lines
            lines = [l.strip() for l in head_text.splitlines() if l.strip() and not l.strip().startswith("---") and not l.strip().startswith("#")]
            summary = " ".join(lines[:3]).strip()
    except Exception:
        pass
    return title, summary[:300]


def scan_skills(source_id: Optional[str] = None) -> List[dict]:
    """Scan all skill, rule, template, and script files across all configured skill sources."""
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
        else:
            return []

    valid_exts = {".md", ".java", ".sh", ".bat", ".config", ".json", ".template"}
    ignore_dirs = {".git", ".github", ".claude", "node_modules", "target", "build", ".idea"}
    skills = []

    for src in sources:
        if source_id and src["id"].lower() != source_id.lower():
            continue

        base_dir = src["dir"]
        s_id = src["id"]
        s_name = src["name"]

        for file_path in base_dir.rglob("*.*"):
            ext = file_path.suffix.lower()
            if ext not in valid_exts:
                continue
            if any(part in ignore_dirs for part in file_path.parts):
                continue

            try:
                rel = file_path.relative_to(base_dir).as_posix()
                parts = rel.split("/")

                # Determine clean category
                if s_id == "claude_code_java" and parts[0] == "skills" and len(parts) > 1:
                    category = parts[1]  # e.g. "concurrency-review", "spring-boot-patterns"
                else:
                    category = parts[0] if len(parts) > 1 else "root"

                stat = file_path.stat()
                title, summary = _parse_skill_metadata(file_path, ext)
                scoped_path = f"{s_id}/{rel}"

                skills.append({
                    "name": file_path.name,
                    "title": title,
                    "rel_path": rel,
                    "scoped_path": scoped_path,
                    "source_id": s_id,
                    "source_name": s_name,
                    "category": category,
                    "size_bytes": stat.st_size,
                    "ext": ext,
                    "summary": summary,
                })
            except Exception:
                continue

    skills.sort(key=lambda s: (s["source_id"], s["category"], s["name"]))
    return skills


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


HASH_FILE_CANDIDATES = [
    "config/overlay/mcp_skills_hashes.json",
    "config/mcp_skills_hashes.json",
]


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
    path = _repo_root() / "config" / "overlay" / "mcp_skills_hashes.json"
    if not path.parent.is_dir():
        path = _repo_root() / "config" / "mcp_skills_hashes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hashes, indent=2), encoding="utf-8")


_CHROMA_LOCK = threading.Lock()


def sync_skills_to_chroma(collection_name: str = "telua_knowledge", incremental: bool = True) -> dict:
    """Index all skills from all configured sources into persistent ChromaDB in ai_agent/data.
    
    If incremental=True, uses MD5 hashes to only re-embed new or modified files.
    """
    with _CHROMA_LOCK:
        sources = resolve_skill_sources()
        if not sources:
            primary = resolve_skill_dir()
            if primary.is_dir():
                sources = [{"id": "telua_skill", "name": "Telua Java/Android", "dir": primary, "local_path": DEFAULT_SKILL_LOCAL_PATH}]
            else:
                return {
                    "ok": False,
                    "error": "No active skill sources found to index.",
                    "indexed": 0,
                }

        try:
            import chromadb
        except ImportError:
            return {
                "ok": False,
                "error": "chromadb package not installed. Run: pip install chromadb",
                "indexed": 0,
            }

        chroma_dir = _repo_root() / "ai_agent" / "data"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(chroma_dir))
        col = client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Telua Multi-Source Java/Android & Agent Skills Knowledge Base"}
        )

        skills = scan_skills()
        if not skills:
            return {"ok": True, "indexed": 0, "skipped": 0, "message": "No skill files found to index."}

        previous_hashes = _load_skill_hashes() if incremental else {}
        current_hashes = dict(previous_hashes)

        docs = []
        metas = []
        ids = []
        skipped_count = 0

        # Mapping for source roots
        src_map = {s["id"]: s["dir"] for s in sources}

        for s in skills:
            base_dir = src_map.get(s["source_id"])
            if not base_dir:
                continue
            fp = base_dir / s["rel_path"]
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    continue

                file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                clean_name = s['name'].replace('.', '_').replace('-', '_')
                doc_id = f"skill_{s['source_id']}_{s['category']}_{clean_name}"

                # Incremental skip: if hash matches, no re-embedding needed
                if incremental and previous_hashes.get(doc_id) == file_hash:
                    skipped_count += 1
                    continue

                current_hashes[doc_id] = file_hash

                metadata = {
                    "source_id": s["source_id"],
                    "source_name": s["source_name"],
                    "category": s["category"],
                    "name": s["name"],
                    "title": s["title"],
                    "rel_path": s["rel_path"],
                    "scoped_path": s["scoped_path"],
                    "source": f"{s['source_id']}/{s['rel_path']}",
                    "ext": s["ext"],
                    "type": "agent_skill",
                    "indexed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                # Formulate semantic embedding document with clear provenance
                full_doc = (
                    f"SOURCE: {s['source_name']} ({s['source_id']})\n"
                    f"CATEGORY: {s['category']}\n"
                    f"TITLE: {s['title']}\n"
                    f"FILE: {s['name']} (Path: {s['scoped_path']})\n"
                    f"SUMMARY: {s['summary']}\n\n"
                    f"{content}"
                )
                if len(full_doc) > 15000:
                    full_doc = full_doc[:15000]

                docs.append(full_doc)
                metas.append(metadata)
                ids.append(doc_id)
            except Exception:
                continue

        if docs:
            # Batch upsert in chunks of 50 to avoid oversized payloads
            chunk_size = 50
            for i in range(0, len(docs), chunk_size):
                col.upsert(
                    documents=docs[i:i + chunk_size],
                    metadatas=metas[i:i + chunk_size],
                    ids=ids[i:i + chunk_size],
                )

        _save_skill_hashes(current_hashes)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_mcp_skill_state({
            "last_sync": timestamp,
            "indexed_count": len(skills),
        })

        return {
            "ok": True,
            "indexed": len(docs),
            "skipped": skipped_count,
            "total_files": len(skills),
            "sources_count": len(sources),
            "last_sync": timestamp,
            "collection": collection_name,
            "chroma_path": str(chroma_dir),
        }


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
                res = sync_skills_to_chroma(incremental=True)
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
                    res = sync_skills_to_chroma(incremental=True)
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
