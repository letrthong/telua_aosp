#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# web/ai/db/chroma/store.py — Sharded ChromaDB implementation of VectorDB.
#
# Layout under <base_dir> (default: ai_agent/data/):
#   shards/<project>__<aosp_version>/chroma.sqlite3   (isolated per project+version)
#   chroma.sqlite3                                    (legacy root fallback, read-only)
# ==============================================================================

import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..base import (
    DEFAULT_COLLECTION_NAME,
    VectorDB,
    clean_tag,
    parse_shard_key,
    shard_key,
)


def _chroma_where(project: str = "", aosp_version: str = "", source_id: str = "") -> Optional[dict]:
    """Translate neutral filter arguments into ChromaDB's `$and` where-dict syntax."""
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


class ChromaVectorDB(VectorDB):
    """Persistent, sharded ChromaDB backend."""

    backend_name = "chroma"

    def __init__(self, base_dir: Optional[Path] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(base_dir=base_dir, config=config)
        self._lock = threading.Lock()
        self._clients: Dict[str, object] = {}

    @property
    def shards_dir(self) -> Path:
        return self.base_dir / "shards"

    def is_available(self) -> Tuple[bool, str]:
        try:
            import chromadb  # noqa: F401
            return True, ""
        except ImportError:
            return False, "chromadb package not installed. Run: pip install chromadb"

    def _get_client(self, db_path: Path):
        key = str(db_path.resolve())
        with self._lock:
            client = self._clients.get(key)
            if client is not None:
                return client
            import chromadb
            db_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(db_path))
            self._clients[key] = client
            return client

    def _get_collection(self, project: str, aosp_version: str, collection_name: str):
        sk = shard_key(project, aosp_version)
        client = self._get_client(self.shards_dir / sk)
        return client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": f"Telua Sharded Knowledge Base ({sk})",
                "project": clean_tag(project, "aosp_aaos"),
                "aosp_version": clean_tag(aosp_version, ""),
            },
        )

    def _iter_existing_shards(self) -> List[Tuple[str, Path, bool]]:
        out: List[Tuple[str, Path, bool]] = []
        if self.shards_dir.is_dir():
            for child in sorted(self.shards_dir.iterdir()):
                if child.is_dir() and (child / "chroma.sqlite3").is_file():
                    out.append((child.name, child, False))
        if (self.base_dir / "chroma.sqlite3").is_file():
            out.append(("legacy", self.base_dir, True))
        return out

    def _matching_shards(self, project: str = "", aosp_version: str = "") -> List[Tuple[str, Path, bool]]:
        p = clean_tag(project, "")
        v = clean_tag(aosp_version, "")
        all_dbs = self._iter_existing_shards()
        if not p and not v:
            return all_dbs

        matched: List[Tuple[str, Path, bool]] = []
        for key, path, is_legacy in all_dbs:
            if is_legacy:
                matched.append((key, path, True))
                continue
            sp, sv = parse_shard_key(key)
            if p and sp != p:
                continue
            if v and sv != v:
                continue
            matched.append((key, path, False))
        return matched

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
        if not ids:
            return
        col = self._get_collection(project, aosp_version, collection_name)
        kwargs: Dict[str, Any] = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        col.upsert(**kwargs)

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
        col = self._get_collection(project, aosp_version, collection_name)
        kwargs: Dict[str, Any] = {"ids": [doc_id], "documents": [document], "metadatas": [metadata]}
        if embedding is not None:
            kwargs["embeddings"] = [embedding]
        col.add(**kwargs)
        return shard_key(project, aosp_version)

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
        # ChromaDB performs vector similarity search (search_mode / alpha accepted for interface compatibility).
        dbs = self._matching_shards(project=project, aosp_version=aosp_version)
        if not dbs:
            return [], []

        hits: List[dict] = []
        queried: List[str] = []
        for key, path, is_legacy in dbs:
            try:
                client = self._get_client(path)
                col = client.get_or_create_collection(name=collection_name)
                cnt = col.count()
                if cnt <= 0:
                    continue
                queried.append(key)
                where = _chroma_where(
                    project=project if is_legacy else "",
                    aosp_version=aosp_version if is_legacy else "",
                    source_id=source_id,
                )
                q_kwargs: Dict[str, Any] = {"n_results": min(n_results, cnt)}
                if query_embedding is not None:
                    q_kwargs["query_embeddings"] = [query_embedding]
                else:
                    q_kwargs["query_texts"] = [query_text]
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

    def delete_by_source(
        self,
        source_id: str,
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> int:
        sid = clean_tag(source_id, "")
        if not sid:
            return 0
        deleted = 0
        for _key, path, _is_legacy in self._matching_shards(project=project, aosp_version=aosp_version):
            try:
                client = self._get_client(path)
                col = client.get_or_create_collection(name=collection_name)
                before = col.count()
                col.delete(where={"source_id": sid})
                deleted += max(0, before - col.count())
            except Exception:
                continue
        return deleted

    def drop_shard(
        self,
        project: str,
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> bool:
        sk = shard_key(project, aosp_version)
        target = (self.shards_dir / sk).resolve()
        with self._lock:
            self._clients.pop(str(target), None)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            return True
        return False

    def status(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> dict:
        ok, err = self.is_available()
        if not ok:
            return {
                "ok": True,
                "backend": self.backend_name,
                "installed": False,
                "error": err,
                "doc_count": 0,
                "shards": [],
                "shard_count": 0,
                "collections": [],
                "path": str(self.shards_dir),
            }

        shards_info = []
        total_docs = 0
        for key, path, is_legacy in self._iter_existing_shards():
            try:
                client = self._get_client(path)
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
            "backend": self.backend_name,
            "installed": True,
            "collection": collection_name,
            "collections": [collection_name],
            "doc_count": total_docs,
            "shards": shards_info,
            "shard_count": len(shards_info),
            "path": str(self.shards_dir),
        }

    def close(self) -> None:
        with self._lock:
            self._clients.clear()
