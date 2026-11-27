#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# web/ai/db/base.py — Abstract VectorDB interface & shard naming helpers.
#
# All application code (telua_web_ai.py, telua_mcp_skill.py) talks ONLY to this
# interface. Swapping ChromaDB for Qdrant / LanceDB / Milvus / FAISS later only
# requires implementing a new subclass under web/ai/db/<backend>/.
# ==============================================================================

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "ai_agent" / "data"
DEFAULT_COLLECTION_NAME = "telua_knowledge"


def clean_tag(val, default: str = "") -> str:
    s = str(val or "").strip().lower()
    if s in ("", "all", "auto", "any", "*", "none", "unknown", "generic"):
        return default
    s = re.sub(r"[^a-z0-9_\-]", "_", s).strip("_")
    return s or default


def shard_key(project: str = "", aosp_version: str = "") -> str:
    """Canonical shard identifier: '<project>__<aosp_version|shared>'."""
    p = clean_tag(project, "aosp_aaos")
    v = clean_tag(aosp_version, "shared")
    return f"{p}__{v}"


def parse_shard_key(key: str) -> Tuple[str, str]:
    if "__" in key:
        p, v = key.split("__", 1)
        return p, ("" if v == "shared" else v)
    return key, ""


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


class VectorDB(ABC):
    """Backend-agnostic Vector Database interface with (project, aosp_version) sharding."""

    backend_name: str = "base"

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir: Path = Path(base_dir) if base_dir is not None else DEFAULT_DATA_DIR

    @abstractmethod
    def is_available(self) -> Tuple[bool, str]:
        """Return (available, error_message_if_not)."""

    @abstractmethod
    def upsert(
        self,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict],
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        """Insert or update a batch of documents in the (project, aosp_version) shard."""

    @abstractmethod
    def add(
        self,
        doc_id: str,
        document: str,
        metadata: Dict,
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> str:
        """Add a single document and return the shard key where it was stored."""

    @abstractmethod
    def query(
        self,
        query_text: str,
        n_results: int = 4,
        project: str = "",
        aosp_version: str = "",
        source_id: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> Tuple[List[dict], List[str]]:
        """Query matching shard(s) and return (records, queried_shard_keys).

        Each record has shape: {"text": str, "meta": dict, "distance": float, "shard": str}
        """

    @abstractmethod
    def status(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> dict:
        """Return aggregated status & per-shard stats."""
