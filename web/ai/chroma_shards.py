#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# chroma_shards.py — Sharded Persistent ChromaDB manager by (project, aosp_version).
#
# Layout under ai_agent/data/:
#   ai_agent/data/shards/<project>__<aosp_version>/   (e.g. aosp_aaos__a16, aosp_aaos__a12, aosp_aaos__shared)
#   ai_agent/data/chroma.sqlite3                      (legacy single-DB fallback, read-only if present)
#
# Benefits for 100-200 GB AOSP repos:
#   - Querying A16 only loads the A16 HNSW index into RAM (fast, low RAM, zero A12 bleed).
#   - Each shard is an independent SQLite DB -> easy backup/rebuild/delete per version,
#     and different shards can be written in parallel (1 writer thread per shard).
# ==============================================================================

import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHROMA_ROOT_DIR = REPO_ROOT / "ai_agent" / "data"
SHARDS_ROOT_DIR = CHROMA_ROOT_DIR / "shards"
DEFAULT_COLLECTION_NAME = "telua_knowledge"

_CLIENT_LOCK = threading.Lock()
_CLIENTS: Dict[str, object] = {}


def clean_tag(val, default: str = "") -> str:
    s = str(val or "").strip().lower()
    if s in ("", "all", "auto", "any", "*", "none", "unknown", "generic"):
        return default
    s = re.sub(r"[^a-z0-9_\-]", "_", s).strip("_")
    return s or default


def shard_key(project: str = "", aosp_version: str = "") -> str:
    """Canonical shard folder name: '<project>__<aosp_version|shared>'."""
    p = clean_tag(project, "aosp_aaos")
    v = clean_tag(aosp_version, "shared")
    return f"{p}__{v}"


def parse_shard_key(key: str) -> Tuple[str, str]:
    if "__" in key:
        p, v = key.split("__", 1)
        return p, ("" if v == "shared" else v)
    return key, ""


def shard_dir(project: str = "", aosp_version: str = "", base_dir: Optional[Path] = None) -> Path:
    root = (base_dir / "shards") if base_dir is not None else SHARDS_ROOT_DIR
    return root / shard_key(project, aosp_version)


def get_client_for_path(db_path: Path):
    """Return a cached chromadb.PersistentClient for db_path (thread-safe)."""
    key = str(db_path.resolve())
    with _CLIENT_LOCK:
        client = _CLIENTS.get(key)
        if client is not None:
            return client
        import chromadb
        db_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(db_path))
        _CLIENTS[key] = client
        return client


def get_shard_collection(
    project: str = "",
    aosp_version: str = "",
    collection_name: str = DEFAULT_COLLECTION_NAME,
    base_dir: Optional[Path] = None,
):
    """Get or create the ChromaDB collection inside the (project, aosp_version) shard."""
    db_path = shard_dir(project, aosp_version, base_dir=base_dir)
    client = get_client_for_path(db_path)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": f"Telua Sharded Knowledge Base ({shard_key(project, aosp_version)})",
            "project": clean_tag(project, "aosp_aaos"),
            "aosp_version": clean_tag(aosp_version, ""),
        },
    )


def _iter_existing_shard_paths(base_dir: Optional[Path] = None) -> List[Tuple[str, Path, bool]]:
    """Return list of (shard_key, path, is_legacy) for all existing DBs on disk."""
    root = base_dir if base_dir is not None else CHROMA_ROOT_DIR
    sroot = root / "shards"
    out: List[Tuple[str, Path, bool]] = []
    if sroot.is_dir():
        for child in sorted(sroot.iterdir()):
            if child.is_dir() and (child / "chroma.sqlite3").is_file():
                out.append((child.name, child, False))
    if (root / "chroma.sqlite3").is_file():
        out.append(("legacy", root, True))
    return out


def matching_shard_paths(
    project: str = "",
    aosp_version: str = "",
    base_dir: Optional[Path] = None,
) -> List[Tuple[str, Path, bool]]:
    """Return only the shard DB paths that can contain documents for (project, aosp_version)."""
    p = clean_tag(project, "")
    v = clean_tag(aosp_version, "")
    all_dbs = _iter_existing_shard_paths(base_dir=base_dir)
    if not p and not v:
        return all_dbs

    matched: List[Tuple[str, Path, bool]] = []
    for key, path, is_legacy in all_dbs:
        if is_legacy:
            # Legacy root DB may hold mixed records; filter via Chroma `where` at query time.
            matched.append((key, path, True))
            continue
        sp, sv = parse_shard_key(key)
        if p and sp != p:
            continue
        if v and sv != v:
            continue
        matched.append((key, path, False))
    return matched


def build_where_filter(project: str = "", aosp_version: str = "", source_id: str = "") -> Optional[dict]:
    conds = []
    p = clean_tag(project, "")
    v = clean_tag(aosp_version, "")
    s = clean_tag(source_id, "")
    if p:
        conds.append({"project": p})
    if v:
        conds.append({"aosp_version": v})
    if s:
        conds.append({"source_id": s})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def query_shards(
    query_text: str,
    n_results: int = 4,
    project: str = "",
    aosp_version: str = "",
    source_id: str = "",
    collection_name: str = DEFAULT_COLLECTION_NAME,
    base_dir: Optional[Path] = None,
) -> Tuple[List[dict], List[str]]:
    """Query matching ChromaDB shards and merge results by vector distance.

    Returns (records, queried_shard_keys) where each record is:
      {"text": str, "meta": dict, "distance": float, "shard": str}
    """
    dbs = matching_shard_paths(project=project, aosp_version=aosp_version, base_dir=base_dir)
    if not dbs:
        return [], []

    hits: List[dict] = []
    queried: List[str] = []
    for key, path, is_legacy in dbs:
        try:
            client = get_client_for_path(path)
            col = client.get_or_create_collection(name=collection_name)
            cnt = col.count()
            if cnt <= 0:
                continue
            queried.append(key)
            # For sharded DBs, project & aosp_version are already isolated by folder;
            # only apply `where` for source_id (or for legacy root DB).
            where = build_where_filter(
                project=project if is_legacy else "",
                aosp_version=aosp_version if is_legacy else "",
                source_id=source_id,
            )
            q_kwargs = {"query_texts": [query_text], "n_results": min(n_results, cnt)}
            if where:
                q_kwargs["where"] = where
            res = col.query(**q_kwargs)
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            for idx, (doc, meta) in enumerate(zip(docs, metas)):
                dist = float(dists[idx]) if idx < len(dists) and dists[idx] is not None else 0.0
                hits.append({
                    "text": doc,
                    "meta": meta or {},
                    "distance": dist,
                    "shard": key,
                })
        except Exception:
            continue

    hits.sort(key=lambda h: h["distance"])
    return hits[:n_results], queried


def get_total_chroma_status(
    collection_name: str = DEFAULT_COLLECTION_NAME,
    base_dir: Optional[Path] = None,
) -> dict:
    """Return aggregated status across all ChromaDB shards (plus legacy root if any)."""
    root = base_dir if base_dir is not None else CHROMA_ROOT_DIR
    try:
        import chromadb  # noqa: F401
    except ImportError:
        return {
            "ok": True,
            "installed": False,
            "doc_count": 0,
            "shards": [],
            "path": str(root),
        }

    shards_info = []
    total_docs = 0
    for key, path, is_legacy in _iter_existing_shard_paths(base_dir=root):
        try:
            client = get_client_for_path(path)
            col = client.get_or_create_collection(name=collection_name)
            cnt = int(col.count())
        except Exception:
            cnt = 0
        sp, sv = ("legacy", "") if is_legacy else parse_shard_key(key)
        total_docs += cnt
        shards_info.append({
            "key": key,
            "project": sp,
            "aosp_version": sv,
            "doc_count": cnt,
            "path": str(path),
            "is_legacy": is_legacy,
        })

    return {
        "ok": True,
        "installed": True,
        "collection": collection_name,
        "doc_count": total_docs,
        "shards": shards_info,
        "shard_count": len(shards_info),
        "path": str(root / "shards"),
    }
