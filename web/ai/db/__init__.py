#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# web/ai/db/__init__.py — VectorDB factory & registry.
#
# To swap vector databases in the future (e.g. Qdrant, LanceDB, Milvus, FAISS):
#   1. Implement a subclass of VectorDB in web/ai/db/<backend>/store.py
#   2. Register it in _BACKENDS below
#   3. Set TELUA_VECTOR_DB=<backend> (or pass backend="<backend>")
# ==============================================================================

import os
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, Type

from .base import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DATA_DIR,
    VectorDB,
    build_where_filter,
    clean_tag,
    parse_shard_key,
    shard_key,
)
from .chroma import ChromaVectorDB

_BACKENDS: Dict[str, Type[VectorDB]] = {
    "chroma": ChromaVectorDB,
}

_INSTANCE_LOCK = threading.Lock()
_INSTANCES: Dict[Tuple[str, str], VectorDB] = {}


def register_vector_db(name: str, cls: Type[VectorDB]) -> None:
    """Register a custom VectorDB backend class."""
    _BACKENDS[name.strip().lower()] = cls


def get_vector_db(
    backend: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> VectorDB:
    """Return a cached VectorDB instance for the configured backend."""
    name = (backend or os.environ.get("TELUA_VECTOR_DB") or "chroma").strip().lower()
    cls = _BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"Unknown VectorDB backend '{name}'. Available: {sorted(_BACKENDS.keys())}")
    resolved_dir = Path(base_dir).resolve() if base_dir is not None else DEFAULT_DATA_DIR.resolve()
    cache_key = (name, str(resolved_dir))
    with _INSTANCE_LOCK:
        inst = _INSTANCES.get(cache_key)
        if inst is None:
            inst = cls(base_dir=resolved_dir)
            _INSTANCES[cache_key] = inst
        return inst


__all__ = [
    "VectorDB",
    "ChromaVectorDB",
    "DEFAULT_COLLECTION_NAME",
    "DEFAULT_DATA_DIR",
    "clean_tag",
    "shard_key",
    "parse_shard_key",
    "build_where_filter",
    "register_vector_db",
    "get_vector_db",
]
