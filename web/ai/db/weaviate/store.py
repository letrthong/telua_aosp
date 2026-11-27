#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# web/ai/db/weaviate/store.py — Template / Skeleton for Weaviate VectorDB backend.
#
# Status: STUB (not implemented yet).
# When you want to switch from ChromaDB to Weaviate (https://weaviate.io):
#   1. pip install weaviate-client
#   2. Implement the TODO methods below using Weaviate v4 Multi-Tenancy + Hybrid Search
#   3. Set environment variable: TELUA_VECTOR_DB=weaviate
#      (and WEAVIATE_URL / WEAVIATE_API_KEY as needed)
#   No changes needed in telua_web_ai.py or telua_mcp_skill.py!
# ==============================================================================

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..base import (
    DEFAULT_COLLECTION_NAME,
    VectorDB,
    shard_key,
)


class WeaviateVectorDB(VectorDB):
    """Skeleton VectorDB backend for Weaviate (Multi-Tenancy + Hybrid BM25/Vector Search).

    Recommended mapping:
      - shard_key(project, aosp_version)  -->  Weaviate Tenant name (e.g. 'aosp_aaos__a16')
      - upsert()                          -->  collection.with_tenant(sk).batch.dynamic()
                                               with deterministic uuid5(NAMESPACE, doc_id)
      - query(search_mode='hybrid')       -->  collection.with_tenant(sk).query.hybrid(
                                               query=query_text, alpha=alpha, limit=n_results)
      - drop_shard()                      -->  collection.tenants.remove([sk])
      - close()                           -->  self._client.close()
    """

    backend_name = "weaviate"

    def __init__(self, base_dir: Optional[Path] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(base_dir=base_dir, config=config)
        # TODO: Read connection config (e.g. url, grpc_port, api_key) from self.config or env:
        #   self.url = self.config.get("url") or os.environ.get("WEAVIATE_URL", "http://localhost:8080")
        #   self.api_key = self.config.get("api_key") or os.environ.get("WEAVIATE_API_KEY", "")
        self._client = None

    def is_available(self) -> Tuple[bool, str]:
        return (
            False,
            "WeaviateVectorDB is a template stub and not implemented yet. "
            "See web/ai/db/weaviate/README.md to enable it.",
        )

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
        # TODO: Ensure tenant `shard_key(project, aosp_version)` exists, then batch upsert.
        raise NotImplementedError("WeaviateVectorDB.upsert() is not implemented yet.")

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
        # TODO: Insert single object into tenant `shard_key(project, aosp_version)`.
        _sk = shard_key(project, aosp_version)
        raise NotImplementedError(f"WeaviateVectorDB.add() is not implemented yet (tenant={_sk}).")

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
        # TODO: Query matching Weaviate tenant(s) with hybrid (BM25 + vector) or near_text/near_vector,
        #       applying Filter.by_property("source_id").equal(source_id) when source_id is set.
        raise NotImplementedError("WeaviateVectorDB.query() is not implemented yet.")

    def delete_by_source(
        self,
        source_id: str,
        project: str = "",
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> int:
        # TODO: collection.with_tenant(sk).data.delete_many(where=Filter.by_property("source_id").equal(source_id))
        raise NotImplementedError("WeaviateVectorDB.delete_by_source() is not implemented yet.")

    def drop_shard(
        self,
        project: str,
        aosp_version: str = "",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> bool:
        # TODO: collection.tenants.remove([shard_key(project, aosp_version)])
        raise NotImplementedError("WeaviateVectorDB.drop_shard() is not implemented yet.")

    def status(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> dict:
        ok, err = self.is_available()
        return {
            "ok": True,
            "backend": self.backend_name,
            "installed": ok,
            "error": err,
            "collection": collection_name,
            "collections": [],
            "doc_count": 0,
            "shards": [],
            "shard_count": 0,
            "path": self.config.get("url", "http://localhost:8080"),
        }

    def close(self) -> None:
        # TODO: if self._client: self._client.close()
        self._client = None
