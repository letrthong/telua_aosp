#!/bin/bash
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Contribution History:
#   - 2026-10: Thong Le <letrthong@gmail.com> (Architecture & Domain Design)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# telua_find.sh - Fast search utilities (file / directory / text) for the Telua
# toolkit.
# Single source of truth for the search commands of build_apk.sh:
#   - 'telua --find-file <pattern> [path]' : find_file (locate files by name)
#   - 'telua --find-dir <pattern> [path]'  : find_dir  (locate directories)
#   - 'telua --find-text <text> [path]'    : find_text (grep text in files,
#     prefers ripgrep for large AOSP trees, falls back to grep -w)
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_find.sh"
#
# Contract with the sourcing (host) script:
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_FIND_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_FIND_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_FIND_SOURCED=1

# --- 4d. Search Utilities (find_file, find_dir, find_text) ---
# Supports passing target search path as optional 2nd argument (defaults to '.')
find_file() {
    local pattern="$1"
    local search_path="${2:-.}"
    if [ -z "$pattern" ]; then
        log_error "Usage: find_file <file_pattern> [search_path]"
        exit 1
    fi
    log_info "Searching for file '$pattern' in '$search_path'..."
    find "$search_path" -type f -name "$pattern" 2>/dev/null
}

find_dir() {
    local pattern="$1"
    local search_path="${2:-.}"
    if [ -z "$pattern" ]; then
        log_error "Usage: find_dir <dir_pattern> [search_path]"
        exit 1
    fi
    log_info "Searching for directory '$pattern' in '$search_path'..."
    find "$search_path" -type d -name "$pattern" 2>/dev/null
}

find_text() {
    local text="$1"
    local search_path="${2:-.}"
    if [ -z "$text" ]; then
        log_error "Usage: find_text <text_pattern> [search_path]"
        exit 1
    fi
    # Prefer ripgrep (much faster on large AOSP trees, full-text match,
    # auto-skips out/.repo/ via .gitignore & hidden dirs). Fallback: grep -w.
    if command -v rg >/dev/null 2>&1; then
        log_info "Searching for text '$text' in '$search_path' (ripgrep)..."
        rg -n --no-heading -S -- "$text" "$search_path" 2>/dev/null
    else
        log_info "Searching for text '$text' in '$search_path' (grep; tip: install ripgrep for faster search)..."
        grep -rnw "$search_path" -e "$text" 2>/dev/null
    fi
}
