#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# web/ai/db/base.py — Backend-agnostic VectorDB interface & shard helpers.
#
# All application code (telua_web_ai.py, telua_mcp_skill.py) talks ONLY to this
# interface. Swapping ChromaDB for Weaviate / Qdrant / LanceDB / Milvus later
# requires ONLY implementing a subclass under web/ai/db/<backend>/store.py.
# ==============================================================================

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    """Canonical shard / tenant identifier: '<project>__<aosp_version|shared>'."""
    p = clean_tag(project, "aosp_aaos")
    v = clean_tag(aosp_version, "shared")
    return f"{p}__{v}"


def parse_shard_key(key: str) -> Tuple[str, str]:
    if "__" in key:
        p, v = key.split("__", 1)
        return p, ("" if v == "shared" else v)
    return key, ""


class VectorDB(ABC):
    """Backend-agnostic Vector Database interface with (project, aosp_version) sharding."""

    backend_name: str = "base"

    def __init__(self, base_dir: Optional[Path] = None, config: Optional[Dict[str, Any]] = None):
        self.base_dir: Path = Path(base_dir) if base_dir is not None else DEFAULT_DATA_DIR
        self.config: Dict[str, Any] = dict(config or {})

    @abstractmethod
    def is_available(self) -> Tuple[bool, str]:
        """Return (available, reason_if_unavailable)."""

    @abstractmethod
    def upsert(
        self,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict],
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        """Insert or update a batch of documents in the (project, aosp_version) shard/tenant."""

    @abstractmethod
    def add(
        self,
        doc_id: str,
        document: str,
        metadata: Dict,
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """Add a single document and return the shard/tenant key where it was stored."""

    @abstractmethod
    def query(
        self,
        query_text: str,
        n_results: int = 4,
        project: str = "",
        aosp_version: str = "",
        source_id: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
        search_mode: str = "hybrid",
        alpha: float = 0.5,
        query_embedding: Optional[List[float]] = None,
    ) -> Tuple[List[dict], List[str]]:
        """Query matching shard(s) and return (records, queried_shard_keys).

        search_mode: 'hybrid' (BM25 + vector when supported, else vector), 'vector', or 'keyword'.
        alpha: hybrid weighting (0.0 = pure keyword, 1.0 = pure vector).
        Each record has shape: {"text": str, "meta": dict, "distance": float, "shard": str}
        """

    @abstractmethod
    def delete_ids(
        self,
        ids: List[str],
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> int:
        """Delete specific document/chunk IDs from the (project, aosp_version) shard."""

    @abstractmethod
    def delete_by_source(
        self,
        source_id: str,
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> int:
        """Delete all documents belonging to source_id from matching shard(s)."""

    @abstractmethod
    def drop_shard(
        self,
        project: str,
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> bool:
        """Delete/drop an entire (project, aosp_version) shard or tenant."""

    @abstractmethod
    def status(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> dict:
        """Return aggregated status & per-shard stats."""

    def close(self) -> None:
        """Release any open connections / sockets (override for networked DBs like Weaviate)."""
        return None
