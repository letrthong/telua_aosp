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
# telua_git.sh - Standalone Git utilities for the Telua toolkit.
# Extracted from build_apk.sh so 'telua git <cmd>' can delegate here.
# Also usable directly:
#   ./telua_git.sh update | status | log | diff | amend | fetch | cheat
#
# Notes:
#   - 'update' always targets the toolkit repo (resolved through symlinks),
#     and protects PERSONAL_CONFIG_FILES with backup/restore around
#     'git pull' + 'reset --hard' recovery (same logic as build_apk.sh).
#   - Other commands default to the toolkit repo; use '--repo <path>' to
#     operate on another repository.

set -e

# --- Constants & Global Defaults ---
# NOTE: version vars use the TELUA_GIT_ prefix so that sourcing this file
# from build_apk.sh never clobbers build_apk.sh's own SCRIPT_VERSION.
TELUA_GIT_VERSION="1.2.0"
TELUA_GIT_LAST_UPDATED="2026-10-17"
GIT_CONFIG_FILE_NAME="const_git.config"
CONST_CONFIG_DIR_NAME="config"
DEFAULT_GIT_BRANCH="main"
# Personal (untracked, git-ignored) files protected during 'update'.
# MUST stay in sync with PERSONAL_CONFIG_FILES in build_apk.sh.
PERSONAL_CONFIG_FILES=("apk_overlays.config" "config/const_my_cli.config")
# Guarded: when sourced from build_apk.sh these are already set (identical
# values); they are computed here only when this file runs standalone.
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# Globals
CMD=""
CLI_REPO=""
LOG_COUNT=""
DIFF_REF=""
GIT_BRANCH="${TELUA_GIT_BRANCH:-$DEFAULT_GIT_BRANCH}"
TARGET_REPO=""

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
if [ -z "${MASTER_SCRIPT_DIR:-}" ]; then
    MASTER_SCRIPT_DIR="$(get_master_script_dir)"
fi

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
# Guarded: when sourced from build_apk.sh, TELUA_TOOLKIT_ROOT is already set.
if [ -z "${TELUA_TOOLKIT_ROOT:-}" ]; then
    TELUA_TOOLKIT_ROOT="$(find_toolkit_root "$MASTER_SCRIPT_DIR")"
fi

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

# --- Locate the Git cheatsheet (const_git.config) ---
# Priority: config/ of master dir -> master dir root -> config/ of script dir -> script dir root
find_git_config_file() {
    if [ -f "$MASTER_SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$MASTER_SCRIPT_DIR/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    # Also check the toolkit root (config/ lives there, not in src/)
    if [ -f "$TELUA_TOOLKIT_ROOT/$CONST_CONFIG_DIR_NAME/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$TELUA_TOOLKIT_ROOT/$CONST_CONFIG_DIR_NAME/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$TELUA_TOOLKIT_ROOT/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$TELUA_TOOLKIT_ROOT/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    echo ""
}
# Keep an already-resolved value (build_apk.sh also checks project-level
# overrides); compute only when running standalone.
GIT_CONFIG_FILE="${GIT_CONFIG_FILE:-$(find_git_config_file)}"

# --- Resolve target repository ---
# --repo <path> wins; otherwise the toolkit repo (resolved through symlinks,
# so running 'telua git' from a project dir still updates the toolkit itself).
resolve_target_repo() {
    local target
    if [ -n "$CLI_REPO" ]; then
        if [ ! -d "$CLI_REPO" ]; then
            log_error "Repository path does not exist: $CLI_REPO"
            exit 1
        fi
        target="$(cd "$CLI_REPO" && pwd)"
        echo "$target"
        return 0
    fi

    # Default: the toolkit repo root (parent of src/), resolved through
    # symlinks. Uses BASH_SOURCE[0] (not $SCRIPT_DIR) so the result is
    # correct both standalone and when this file is sourced by build_apk.sh.
    local this_file="${BASH_SOURCE[0]}"
    target="$(cd "$(dirname "$this_file")" && pwd)"
    if [ -L "$this_file" ]; then
        local real_file
        real_file="$(readlink -f "$this_file" 2>/dev/null || realpath "$this_file" 2>/dev/null || echo "")"
        if [ -n "$real_file" ] && [ -f "$real_file" ]; then
            target="$(cd "$(dirname "$real_file")" && pwd)"
        fi
    fi
    target="$(find_toolkit_root "$target")"
    echo "$target"
}

# --- Common pre-flight checks for repo commands ---
require_git_repo() {
    if ! command -v git >/dev/null 2>&1; then
        log_error "'git' command not found. Please ensure Git is installed and in PATH."
        exit 1
    fi
    if ! git -C "$TARGET_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_error "'$TARGET_REPO' is not a Git repository!"
        exit 1
    fi
}

# Restore executable bits on toolkit scripts inside the given repo directory.
# Missing files are skipped so 'set -e' never aborts the update.
# Usage: ensure_script_permissions <repo_dir>
ensure_script_permissions() {
    local repo_dir="$1"
    local script
    if [ -z "$repo_dir" ] || [ ! -d "$repo_dir" ]; then
        log_warn "ensure_script_permissions: invalid directory '$repo_dir'"
        return 0
    fi
    for script in build_apk.sh telua_git.sh config_crypto.py config_overlay.py; do
        if [ -f "$repo_dir/$script" ]; then
            chmod +x "$repo_dir/$script" || log_warn "Failed to chmod +x $repo_dir/$script"
        fi
    done
}

# Back up personal configs before 'update' (git reset --hard would wipe tracked edits).
# Prints the backup directory on stdout (empty if nothing to back up). Usage: backup_personal_configs <repo_dir>
backup_personal_configs() {
    local repo_dir="$1"
    local backup_dir rel saved=0
    backup_dir="$(mktemp -d "${TMPDIR:-/tmp}/telua_personal_backup.XXXXXX")" || return 1
    for rel in "${PERSONAL_CONFIG_FILES[@]}"; do
        if [ -f "$repo_dir/$rel" ]; then
            mkdir -p "$backup_dir/$(dirname "$rel")" || { rm -rf "$backup_dir"; return 1; }
            cp -p "$repo_dir/$rel" "$backup_dir/$rel" || { rm -rf "$backup_dir"; return 1; }
            saved=$((saved + 1))
        fi
    done
    if [ "$saved" -eq 0 ]; then
        rm -rf "$backup_dir"
        return 0
    fi
    echo "$backup_dir"
}

# Copy backed-up personal configs back into the repo, then remove the backup.
# The backup is kept (and its path printed) if any file fails to restore.
# Usage: restore_personal_configs <repo_dir> <backup_dir>
restore_personal_configs() {
    local repo_dir="$1"
    local backup_dir="$2"
    local rel failed=0
    if [ -z "$backup_dir" ] || [ ! -d "$backup_dir" ]; then
        return 0
    fi
    for rel in "${PERSONAL_CONFIG_FILES[@]}"; do
        if [ -f "$backup_dir/$rel" ]; then
            mkdir -p "$repo_dir/$(dirname "$rel")" 2>/dev/null || true
            if cp -p "$backup_dir/$rel" "$repo_dir/$rel"; then
                log_info "Restored personal config: $rel"
            else
                log_warn "Failed to restore personal config: $rel"
                failed=1
            fi
        fi
    done
    if [ "$failed" -eq 0 ]; then
        rm -rf "$backup_dir"
    else
        log_warn "Backup kept at: $backup_dir (copy files back manually)"
    fi
}

# git pull origin <branch>; on failure: fetch + reset --hard origin/<branch>, then pull again.
# Returns 0 on success, 1 on failure (never exits, so the caller can restore backups).
git_pull_with_recovery() {
    local target_repo="$1"
    local branch="${2:-$DEFAULT_GIT_BRANCH}"

    log_info "Executing: git pull origin $branch..."
    if git -C "$target_repo" pull origin "$branch"; then
        log_success "Successfully pulled latest updates from origin/$branch."
        return 0
    fi

    # Neu loi thi reset hard va pull ve lai
    log_warn "'git pull origin $branch' encountered an error or merge conflict!"
    log_info "Initiating automatic recovery: fetching origin $branch..."
    git -C "$target_repo" fetch origin "$branch" || true

    log_info "Running: git reset --hard origin/$branch..."
    if ! git -C "$target_repo" reset --hard "origin/$branch"; then
        log_error "Failed to execute 'git reset --hard origin/$branch'."
        return 1
    fi
    log_success "Reset repository to origin/$branch successfully."

    log_info "Retrying: git pull origin $branch..."
    if git -C "$target_repo" pull origin "$branch"; then
        log_success "Successfully pulled latest updates after hard reset."
        return 0
    fi
    log_error "'git pull origin $branch' failed after hard reset."
    return 1
}

# --- Command: update (git pull origin <branch> with auto-recovery) ---
cmd_update() {
    echo ""
    log_info "============================================================"
    log_info " Updating Telua Toolkit from Git Remote (origin/$GIT_BRANCH)"
    log_info " Target Repository: $TARGET_REPO"
    log_info "============================================================"

    require_git_repo

    local current_branch
    current_branch="$(git -C "$TARGET_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
    log_info "Active Git branch: $current_branch"

    # Protect personal configs: reset --hard below would overwrite them if they are tracked.
    local backup_dir=""
    if ! backup_dir="$(backup_personal_configs "$TARGET_REPO")"; then
        log_error "Failed to back up personal configs. Update aborted to protect your files."
        exit 1
    fi
    if [ -n "$backup_dir" ]; then
        log_info "Backed up personal configs to: $backup_dir"
    fi

    local update_status=0
    git_pull_with_recovery "$TARGET_REPO" "$GIT_BRANCH" || update_status=$?

    restore_personal_configs "$TARGET_REPO" "$backup_dir"

    if [ "$update_status" -eq 0 ]; then
        ensure_script_permissions "$TARGET_REPO"
        log_success "Update completed successfully."
        exit 0
    fi
    exit 1
}

# --- Command: status (branch + short status + ahead/behind) ---
cmd_status() {
    require_git_repo

    local branch ahead behind
    branch="$(git -C "$TARGET_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
    ahead="$(git -C "$TARGET_REPO" rev-list --count "@{u}..HEAD" 2>/dev/null || echo "?")"
    behind="$(git -C "$TARGET_REPO" rev-list --count "HEAD..@{u}" 2>/dev/null || echo "?")"

    log_info "Repository: $TARGET_REPO"
    log_info "Branch:     $branch (ahead: $ahead, behind: $behind vs upstream)"
    echo ""
    git -C "$TARGET_REPO" status -sb
    echo ""
    log_success "Status completed."
    exit 0
}

# --- Command: log (last N commits, default 10) ---
cmd_log() {
    require_git_repo

    local count="${LOG_COUNT:-10}"
    log_info "Last $count commits in $TARGET_REPO:"
    if ! git -C "$TARGET_REPO" log --oneline --decorate -n "$count"; then
        log_error "'git log' failed (does $TARGET_REPO have any commits?)"
        exit 1
    fi
    exit 0
}

# --- Command: diff (last commit by default, or working tree vs <ref>) ---
cmd_diff() {
    require_git_repo

    if [ -n "$DIFF_REF" ]; then
        log_info "Running in $TARGET_REPO: git diff $DIFF_REF"
        if ! git -C "$TARGET_REPO" diff "$DIFF_REF"; then
            log_error "'git diff $DIFF_REF' failed (invalid ref?)"
            exit 1
        fi
    else
        log_info "Running in $TARGET_REPO: git diff HEAD^ HEAD"
        if ! git -C "$TARGET_REPO" diff HEAD^ HEAD; then
            log_error "'git diff HEAD^ HEAD' failed (is $TARGET_REPO a git repo with at least 2 commits?)"
            exit 1
        fi
    fi
    exit 0
}

# --- Command: amend (amend last commit without editing message) ---
cmd_amend() {
    require_git_repo

    log_info "Running in $TARGET_REPO: git commit --amend --no-edit"
    if ! git -C "$TARGET_REPO" commit --amend --no-edit; then
        log_error "'git commit --amend --no-edit' failed (is $TARGET_REPO a git repo with a commit to amend?)"
        exit 1
    fi
    log_success "Last commit amended."
    exit 0
}

# --- Command: fetch (fetch origin without merging) ---
cmd_fetch() {
    require_git_repo

    log_info "Running in $TARGET_REPO: git fetch origin"
    if ! git -C "$TARGET_REPO" fetch origin; then
        log_error "'git fetch origin' failed in $TARGET_REPO."
        exit 1
    fi
    log_success "Fetched origin successfully."
    exit 0
}

# --- Command: cheat (Git & Google Repo cheatsheet from const_git.config) ---
cmd_cheat() {
    if [ -n "$GIT_CONFIG_FILE" ] && [ -f "$GIT_CONFIG_FILE" ]; then
        cat "$GIT_CONFIG_FILE"
        exit 0
    fi
    log_warn "Git cheatsheet file '$GIT_CONFIG_FILE_NAME' not found!"
    log_info "Expected in: $MASTER_SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/ or $SCRIPT_DIR/"
    exit 1
}

telua_git_show_version() {
    echo "telua_git.sh v$TELUA_GIT_VERSION (Last updated: $TELUA_GIT_LAST_UPDATED)"
    echo "Git utilities for the Telua toolkit"
    echo "Maintained by: letrthong@gmail.com"
    exit 0
}

telua_git_print_help() {
    cat <<EOF
telua_git.sh - Git utilities for the Telua toolkit
Version:      v$TELUA_GIT_VERSION (Updated: $TELUA_GIT_LAST_UPDATED)
Maintained by: letrthong@gmail.com

Usage: telua_git.sh [COMMAND] [OPTIONS]   (or: telua git [COMMAND])

Commands:
  update, pull          Update the toolkit repo: git pull origin $GIT_BRANCH
                        with auto-recovery (fetch + reset --hard + retry).
                        Personal configs are backed up & restored automatically.
  status, st            Show branch, short status and ahead/behind counters
  log [n]               Show the last n commits (default: 10)
  diff [ref]            Diff of the last commit (default) or 'git diff <ref>'
  amend                 Amend the last commit without editing its message
  fetch                 Fetch origin without merging
  cheat, cheatsheet     Show the Git & Google Repo cheatsheet ($GIT_CONFIG_FILE_NAME)
  -h, --help, help      Display this help message and exit
  -v, --version         Display version and exit

Options:
  --repo <path>         Operate on <path> instead of the toolkit repo
  --branch <name>       Branch used by 'update' (default: $GIT_BRANCH, env: TELUA_GIT_BRANCH)

Target Repo:  $SCRIPT_DIR (resolved through symlinks; override with --repo)
Cheatsheet:   ${GIT_CONFIG_FILE:-Not found}

Tip: 'telua git cheat' shows the full Git & Repo cheatsheet (previous 'telua git' behavior).
EOF
}

# Prefixed with telua_git_ so sourcing this file never collides with
# build_apk.sh's own parse_arguments / print_help / show_version.
telua_git_parse_arguments() {
    # No arguments: show usage (safe default, same philosophy as build_apk.sh)
    if [ $# -eq 0 ]; then
        telua_git_print_help
        exit 0
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            update|pull)
                CMD="update"
                shift
                ;;
            status|st)
                CMD="status"
                shift
                ;;
            log)
                CMD="log"
                shift
                if [ -n "$1" ] && [[ "$1" != -* ]]; then
                    LOG_COUNT="$1"
                    shift
                fi
                ;;
            diff)
                CMD="diff"
                shift
                if [ -n "$1" ] && [[ "$1" != -* ]]; then
                    DIFF_REF="$1"
                    shift
                fi
                ;;
            amend)
                CMD="amend"
                shift
                ;;
            fetch)
                CMD="fetch"
                shift
                ;;
            cheat|cheatsheet)
                CMD="cheat"
                shift
                ;;
            --repo)
                if [ -z "$2" ]; then
                    log_error "--repo requires a path argument!"
                    exit 1
                fi
                CLI_REPO="$2"
                shift 2
                ;;
            --branch)
                if [ -z "$2" ]; then
                    log_error "--branch requires a branch name!"
                    exit 1
                fi
                GIT_BRANCH="$2"
                shift 2
                ;;
            -v|--version|version)
                telua_git_show_version
                ;;
            -h|--help|help)
                telua_git_print_help
                exit 0
                ;;
            *)
                log_error "Unknown command or option '$1'"
                telua_git_print_help
                exit 1
                ;;
        esac
    done
}


