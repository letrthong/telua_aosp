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
#   - 'telua replace <current_text> <new_text> [path]' : replace_text
#     (find and replace text in files across directory or in a specific file)
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

# --- 4d. Search Utilities (find_file, find_dir, find_text, replace_text) ---
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

replace_text() {
    local current_text="$1"
    local new_text="$2"
    local search_path="${3:-.}"

    if [ -z "$current_text" ] || [ -z "$new_text" ]; then
        log_error "Usage: replace_text <current_text> <new_text> [search_path]"
        log_error "Or CLI: telua replace <current_text> <new_text> [path]"
        exit 1
    fi

    if [ ! -e "$search_path" ]; then
        log_error "Target path '$search_path' does not exist."
        exit 1
    fi

    log_info "Searching and replacing '$current_text' -> '$new_text' in '$search_path'..."

    # Collect matching files
    local file_list=()
    if [ -f "$search_path" ]; then
        file_list=("$search_path")
    elif command -v rg >/dev/null 2>&1; then
        while IFS= read -r line; do
            line="${line%$'\r'}"
            [ -n "$line" ] && file_list+=("$line")
        done < <(rg -l -F -- "$current_text" "$search_path" 2>/dev/null || true)
    else
        while IFS= read -r line; do
            line="${line%$'\r'}"
            [ -n "$line" ] && file_list+=("$line")
        done < <(grep -rIlF --exclude-dir=".git" --exclude-dir=".repo" --exclude-dir="out" -- "$current_text" "$search_path" 2>/dev/null || true)
    fi

    if [ ${#file_list[@]} -eq 0 ]; then
        log_warn "No files containing '$current_text' found in '$search_path'."
        return 0
    fi

    # Determine working Python binary if available (for exact literal matching without regex/sed escaping issues)
    local py_bin=""
    for candidate in python3 python py; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c "import sys" >/dev/null 2>&1; then
                py_bin="$candidate"
                break
            fi
        fi
    done

    local updated_count=0
    if [ -n "$py_bin" ]; then
        while IFS= read -r modified_file; do
            modified_file="${modified_file%$'\r'}"
            if [ -n "$modified_file" ]; then
                log_info "  -> Replaced in: $modified_file"
                updated_count=$((updated_count + 1))
            fi
        done < <(printf '%s\n' "${file_list[@]}" | "$py_bin" -c '
import os
import subprocess
import sys

current_text = sys.argv[1]
new_text = sys.argv[2]

for line in sys.stdin:
    fpath = line.rstrip("\r\n")
    if not fpath:
        continue
    target_path = fpath
    if not os.path.exists(target_path) and os.name == "nt":
        try:
            target_path = subprocess.check_output(["cygpath", "-w", fpath], text=True).strip()
        except Exception:
            pass
    try:
        with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if current_text in content:
            new_content = content.replace(current_text, new_text)
            with open(target_path, "w", encoding="utf-8", newline="") as f:
                f.write(new_content)
            sys.stdout.write(fpath + "\n")
            sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"Failed to replace in {fpath}: {e}\n")
' "$current_text" "$new_text")
    else
        # Fallback to sed if Python is not present
        for f in "${file_list[@]}"; do
            local escaped_old
            local escaped_new
            escaped_old=$(printf '%s\n' "$current_text" | sed -e 's/[[\&/|*.]/\\&/g')
            escaped_new=$(printf '%s\n' "$new_text" | sed -e 's=[\&/|]=0\\&=g' -e 's=0\\==g')
            if sed --version 2>/dev/null | grep -q GNU; then
                if grep -Fq "$current_text" "$f" 2>/dev/null; then
                    sed -i "s|${escaped_old}|${escaped_new}|g" "$f" 2>/dev/null
                    log_info "  -> Replaced in: $f"
                    updated_count=$((updated_count + 1))
                fi
            else
                if grep -Fq "$current_text" "$f" 2>/dev/null; then
                    sed -i '' "s|${escaped_old}|${escaped_new}|g" "$f" 2>/dev/null
                    log_info "  -> Replaced in: $f"
                    updated_count=$((updated_count + 1))
                fi
            fi
        done
    fi

    if [ "$updated_count" -gt 0 ]; then
        log_success "Replacement complete. Modified $updated_count file(s)."
    else
        log_warn "No files were modified."
    fi
}

replace() {
    replace_text "$@"
}
