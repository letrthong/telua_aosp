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
# telua_permission.sh - File permission & copy utilities for the Telua toolkit.
# Extracted from build_apk.sh so 'telua permission <cmd>' can delegate here.
# Also usable directly:
#   ./telua_permission.sh fix | check | copy | install | list
#
# Notes:
#   - 'fix' restores executable bits on all toolkit scripts (same logic as
#     ensure_script_permissions in build_apk.sh, but covers more files).
#   - 'install' = copy + chmod +x in one step (deploy a script somewhere).
#   - Default target dir is the toolkit repo, resolved through symlinks;
#     override with '--dir <path>' or a positional [dir] for fix/check.

set -e

# --- Constants & Global Defaults ---
SCRIPT_VERSION="1.1.0"
SCRIPT_LAST_UPDATED="2026-10-17"

# Toolkit scripts managed by this utility (relative to the toolkit repo root).
# MUST stay in sync with ensure_script_permissions() in build_apk.sh.
# Note: telua_git.sh / telua_permission.sh / telua_log.sh live in src/ since v2.12.0.
TOOLKIT_SCRIPTS=("build_apk.sh" "src/telua_log.sh" "src/telua_git.sh" "src/telua_permission.sh" "config_crypto.py" "config_overlay.py" "apply_apk_overlays.py")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Globals
CMD=""
CMD_ARGS=()
CLI_TARGET_DIR=""

# Resolve master script directory (even if executed through symlink)
get_master_script_dir() {
    local real_script
    if command -v realpath >/dev/null 2>&1; then
        real_script="$(realpath "${BASH_SOURCE[0]}")"
    elif command -v readlink >/dev/null 2>&1; then
        real_script="$(readlink -f "${BASH_SOURCE[0]}")"
    else
        real_script="${BASH_SOURCE[0]}"
    fi
    cd "$(dirname "$real_script")" && pwd
}
MASTER_SCRIPT_DIR="$(get_master_script_dir)"

# Walk up from a directory until we find the toolkit repo root (contains .git).
# Needed because this file lives in src/ but the toolkit root is its parent.
# Usage: find_toolkit_root <start_dir>; echoes the root (or start_dir if no .git found).
find_toolkit_root() {
    local check_dir="$1"
    while [ "$check_dir" != "/" ] && [ "$check_dir" != "." ]; do
        if [ -d "$check_dir/.git" ]; then
            echo "$check_dir"
            return 0
        fi
        check_dir="$(dirname "$check_dir")"
    done
    echo "$1"
}

# Toolkit repo root (parent of src/), resolved through symlinks.
TELUA_TOOLKIT_ROOT="$(find_toolkit_root "$MASTER_SCRIPT_DIR")"

# --- Source telua_log.sh (shared color logging helpers - single source of truth) ---
# Lookup order: src/ (canonical) -> script dir root (backward compat).
# When sourced from build_apk.sh, TELUA_LOG_SOURCED=1 is already set and this
# block is skipped (functions already defined in the caller's shell).
if [ "${TELUA_LOG_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_log.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_log.sh"
    elif [ -f "$SCRIPT_DIR/telua_log.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/telua_log.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_log.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_log.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/telua_log.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/telua_log.sh"
    fi
fi

# Fallback: identical inline copies used only when telua_log.sh is unavailable.
if [ "${TELUA_LOG_SOURCED:-}" != "1" ]; then
    log_info()    { echo -e "\033[1;34m[INFO]\033[0m $*"; }
    log_success() { echo -e "\033[1;32m[SUCCESS]\033[0m $*"; }
    log_warn()    { echo -e "\033[1;33m[WARN]\033[0m $*"; }
    log_error()   { echo -e "\033[1;31m[ERROR]\033[0m $*"; }
fi

# --- Resolve target toolkit directory ---
# --dir <path> or positional [dir] wins; otherwise the toolkit repo
# (resolved through symlinks, so running via a project link still works).
resolve_toolkit_dir() {
    local target
    if [ -n "$CLI_TARGET_DIR" ]; then
        if [ ! -d "$CLI_TARGET_DIR" ]; then
            log_error "Directory does not exist: $CLI_TARGET_DIR"
            exit 1
        fi
        target="$(cd "$CLI_TARGET_DIR" && pwd)"
        echo "$target"
        return 0
    fi
    echo "$TELUA_TOOLKIT_ROOT"
}

# --- Command: fix (chmod +x all toolkit scripts) ---
cmd_fix() {
    local repo_dir
    repo_dir="$(resolve_toolkit_dir)"

    log_info "Restoring executable bits in: $repo_dir"
    local script fixed=0 missing=0
    for script in "${TOOLKIT_SCRIPTS[@]}"; do
        if [ -f "$repo_dir/$script" ]; then
            if chmod +x "$repo_dir/$script"; then
                log_success "chmod +x  $script"
                fixed=$((fixed + 1))
            else
                log_warn "Failed to chmod +x $repo_dir/$script"
            fi
        else
            log_warn "Not found (skipped): $repo_dir/$script"
            missing=$((missing + 1))
        fi
    done
    log_success "Done: $fixed file(s) chmod +x, $missing missing."
    exit 0
}

# --- Command: check (show executable status of toolkit scripts) ---
cmd_check() {
    local repo_dir
    repo_dir="$(resolve_toolkit_dir)"

    log_info "Executable status in: $repo_dir"
    local script mode status
    for script in "${TOOLKIT_SCRIPTS[@]}"; do
        printf "  %-26s " "$script"
        if [ -f "$repo_dir/$script" ]; then
            mode="$(stat -c '%a' "$repo_dir/$script" 2>/dev/null || stat -f '%Lp' "$repo_dir/$script" 2>/dev/null || echo '?')"
            if [ -x "$repo_dir/$script" ]; then
                status="\033[1;32mexecutable\033[0m"
            else
                status="\033[1;31mNOT executable\033[0m"
            fi
            echo -e "$status (mode: $mode)"
        else
            echo -e "\033[0;90mmissing\033[0m"
        fi
    done
    exit 0
}

# --- Command: copy (copy file(s) preserving permissions, cp -p) ---
cmd_copy() {
    if [ "$#" -lt 2 ]; then
        log_error "Usage: telua_permission.sh copy <src>... <dst>"
        exit 1
    fi

    local args=("$@")
    local count=${#args[@]}
    local dst="${args[$((count - 1))]}"
    local srcs=("${args[@]:0:count-1}")
    local src

    for src in "${srcs[@]}"; do
        if [ ! -e "$src" ]; then
            log_error "Source not found: $src"
            exit 1
        fi
    done

    log_info "Copying (permissions preserved): ${srcs[*]} -> $dst"
    if cp -p "${srcs[@]}" "$dst"; then
        log_success "Copy completed."
    else
        log_error "Copy failed."
        exit 1
    fi
    exit 0
}

# --- Command: install (copy a script into <dir> + chmod +x) ---
cmd_install() {
    if [ "$#" -ne 2 ]; then
        log_error "Usage: telua_permission.sh install <script> <target_dir>"
        exit 1
    fi

    local src="$1" dst_dir="$2" base
    if [ ! -f "$src" ]; then
        log_error "Source script not found: $src"
        exit 1
    fi
    if [ ! -d "$dst_dir" ]; then
        log_error "Target directory does not exist: $dst_dir"
        exit 1
    fi

    base="$(basename "$src")"
    log_info "Installing: $src -> $dst_dir/$base (copy + chmod +x)"
    if cp -p "$src" "$dst_dir/$base" && chmod +x "$dst_dir/$base"; then
        log_success "Installed: $dst_dir/$base"
    else
        log_error "Install failed."
        exit 1
    fi
    exit 0
}

# --- Command: list (show managed toolkit scripts) ---
cmd_list() {
    log_info "Toolkit scripts managed by telua_permission.sh:"
    local script
    for script in "${TOOLKIT_SCRIPTS[@]}"; do
        echo "  $script"
    done
    exit 0
}

show_version() {
    echo "telua_permission.sh v$SCRIPT_VERSION (Last updated: $SCRIPT_LAST_UPDATED)"
    echo "File permission & copy utilities for the Telua toolkit"
    echo "Maintained by: letrthong@gmail.com"
    exit 0
}

print_help() {
    cat <<EOF
telua_permission.sh - File permission & copy utilities for the Telua toolkit
Version:      v$SCRIPT_VERSION (Updated: $SCRIPT_LAST_UPDATED)
Maintained by: letrthong@gmail.com

Usage: telua_permission.sh [COMMAND] [OPTIONS]   (or: telua permission [COMMAND])

Commands:
  fix [dir]             Restore executable bits (chmod +x) on all toolkit scripts
  check [dir]           Show executable status of all toolkit scripts
  copy <src>... <dst>   Copy file(s) preserving permissions (cp -p)
  install <src> <dir>   Copy a script into <dir> and chmod +x it
  list                  List the toolkit scripts managed by this utility
  -h, --help, help      Display this help message and exit
  -v, --version         Display version and exit

Options:
  --dir <path>          Target toolkit directory (default: resolved through symlinks)

Managed Scripts: ${TOOLKIT_SCRIPTS[*]}
Default Dir:     $TELUA_TOOLKIT_ROOT

Examples:
  telua permission fix              # chmod +x all toolkit scripts
  telua permission check            # verify executable status
  telua permission install ./tool.sh ~/bin   # copy + chmod +x
  telua permission copy a.conf b.conf config/ # cp -p multiple files
EOF
}

parse_arguments() {
    # No arguments: show usage (safe default, same philosophy as build_apk.sh)
    if [ $# -eq 0 ]; then
        print_help
        exit 0
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            fix|chmod)
                CMD="fix"
                shift
                if [ -n "$1" ] && [[ "$1" != -* ]]; then
                    CLI_TARGET_DIR="$1"
                    shift
                fi
                ;;
            check|status)
                CMD="check"
                shift
                if [ -n "$1" ] && [[ "$1" != -* ]]; then
                    CLI_TARGET_DIR="$1"
                    shift
                fi
                ;;
            copy|cp)
                CMD="copy"
                shift
                CMD_ARGS=("$@")
                break
                ;;
            install)
                CMD="install"
                shift
                CMD_ARGS=("$@")
                break
                ;;
            list|ls)
                CMD="list"
                shift
                ;;
            --dir)
                if [ -z "$2" ]; then
                    log_error "--dir requires a path argument!"
                    exit 1
                fi
                CLI_TARGET_DIR="$2"
                shift 2
                ;;
            -v|--version|version)
                show_version
                ;;
            -h|--help|help)
                print_help
                exit 0
                ;;
            *)
                log_error "Unknown command or option '$1'"
                print_help
                exit 1
                ;;
        esac
    done
}


