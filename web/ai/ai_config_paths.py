#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Licensed under the Apache License, Version 2.0
# ==============================================================================
# ai_config_paths.py — single place that decides where AI / MCP config lives.
#
#   config/ai_agent/            shared, tracked in Git (team defaults)
#   config/overlay/ai_agent/    personal / secret / runtime state (git-ignored)
#
# Legacy locations (config/<name>, config/overlay/<name>) are still read as a
# fallback, and legacy files are moved into the new folders once at import.
# ==============================================================================

import os
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

AI_CONFIG_REL = "config/ai_agent"
AI_OVERLAY_REL = "config/overlay/ai_agent"
_LEGACY_CONFIG_REL = "config"
_LEGACY_OVERLAY_REL = "config/overlay"

AI_CONFIG_DIR = REPO_ROOT / AI_CONFIG_REL
AI_OVERLAY_DIR = REPO_ROOT / AI_OVERLAY_REL

# Every AI-related file managed by the web AI module / MCP skill ingestor.
AI_CONFIG_FILES = (
    "const_ai.config",              # active provider/model, api_key (overlay)
    "ai_providers.json",            # provider registry (overlay when it holds keys)
    "ai_providers.template.json",   # provider templates (shared)
    "ai_guardrails.json",           # token guardrails (overlay)
    "ai_token_usage.json",          # monthly token usage (overlay, runtime)
    "mcp_skills_config.json",       # MCP public sources & schedule (shared)
    "mcp_skills_private.json",      # MCP private sources (overlay)
    "mcp_skills_state.json",        # last_sync / indexed_count (overlay, runtime)
    "mcp_skills_hashes.json",       # incremental sync hashes (overlay, runtime)
)


def overlay_file(name: str) -> Path:
    """Git-ignored personal location: config/overlay/ai_agent/<name>."""
    return AI_OVERLAY_DIR / name


def shared_file(name: str) -> Path:
    """Tracked shared location: config/ai_agent/<name>."""
    return AI_CONFIG_DIR / name


def candidates(name: str, overlay: bool = True, shared: bool = True) -> List[str]:
    """Repo-relative lookup order (new folders first, then legacy fallback)."""
    out = []
    if overlay:
        out += [f"{AI_OVERLAY_REL}/{name}", f"{_LEGACY_OVERLAY_REL}/{name}"]
    if shared:
        out += [f"{AI_CONFIG_REL}/{name}", f"{_LEGACY_CONFIG_REL}/{name}"]
    return out


def find_file(name: str, overlay: bool = True, shared: bool = True) -> Optional[Path]:
    for rel in candidates(name, overlay, shared):
        p = REPO_ROOT / rel
        if p.is_file():
            return p
    return None


def migrate_legacy_files() -> List[str]:
    """Move legacy config/<name> and config/overlay/<name> into the ai_agent folders.

    Never overwrites an existing file in the new location. Returns moved paths.
    """
    moved = []
    for name in AI_CONFIG_FILES:
        for legacy_rel, new_path in ((_LEGACY_OVERLAY_REL, overlay_file(name)),
                                     (_LEGACY_CONFIG_REL, shared_file(name))):
            legacy = REPO_ROOT / legacy_rel / name
            try:
                if legacy.is_file() and not new_path.exists():
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(legacy, new_path)
                    moved.append(f"{legacy_rel}/{name} -> {new_path.relative_to(REPO_ROOT).as_posix()}")
            except OSError:
                pass
    return moved


try:
    _MIGRATED = migrate_legacy_files()
except Exception:  # never block startup on a migration problem
    _MIGRATED = []
