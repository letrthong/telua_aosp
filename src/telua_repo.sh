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
# telua_repo.sh - Google Repo sync & reset utilities for the Telua toolkit.
# Single source of truth for the repo-related commands of build_apk.sh:
#   - 'telua --repo-sync'  : run_repo_sync  (repo sync + post-sync hooks)
#   - 'telua --repo-reset' : run_repo_reset (hard reset & clean all repos)
#   - post_sync_root_cli   : hook executed in ROOT_DIR after sync
#   - post_sync_cli        : hook executed in ANDROID_TOP after sync
#
# All functions are parameter-driven: explicit arguments take precedence,
# global config variables (apk.config) are only used as defaults. This keeps
# the module testable in isolation and reusable from other host scripts.
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_repo.sh"
#
# Function signatures:
#   run_timed_command <label> <command>
#       Execute <command> via eval, logging duration under <label>.
#       Returns the command's exit code (never exits the shell).
#
#   post_sync_root_cli [command]
#       Hook 1: run in ROOT_DIR right after repo sync.
#       [command] overrides $REPO_POST_SYNC_ROOT_COMMAND.
#
#   post_sync_cli [command]
#       Hook 2: run in ANDROID_TOP right after repo sync.
#       [command] overrides $REPO_POST_SYNC_BUILD_COMMAND.
#
#   run_repo_reset [confirm_yes]
#       Hard reset & clean all repos ('repo forall'). Exits when done unless
#       REPO_SYNC=true (then falls through to sync).
#       [confirm_yes] ("true"/"false") overrides $CONFIRM_YES.
#
#   run_repo_sync [jobs] [flags]
#       'repo sync' in ROOT_DIR, then hook 1 (ROOT_DIR) and hook 2 (ANDROID_TOP).
#       [jobs]  overrides ${REPO_SYNC_JOBS:-4}
#       [flags] overrides ${REPO_SYNC_FLAGS:--d -c --force-sync --no-clone-bundle --tags}
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       CONFIG_FILE_NAME, ROOT_DIR, ANDROID_TOP
#   - The host must set the flags REPO_SYNC / REPO_RESET / CONFIRM_YES
#     (from CLI parsing) before calling run_repo_sync / run_repo_reset.
#   - Optional config variables (read from apk.config):
#       REPO_SYNC_JOBS, REPO_SYNC_FLAGS, REPO_POST_SYNC_ROOT_COMMAND,
#       REPO_POST_SYNC_BUILD_COMMAND
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_REPO_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_REPO_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_REPO_SOURCED=1

# --- Shared helper: run a command via eval with duration logging ---
# Usage: run_timed_command <label> <command>
# Returns the command's exit code (caller decides whether to abort).
run_timed_command() {
    local label="$1"
    local cmd="$2"

    log_info "Executing $label command:"
    log_info ">> $cmd"

    local start_ts end_ts duration minutes seconds
    start_ts=$(date +%s)
    if ! eval "$cmd"; then
        log_error "$label command failed: $cmd"
        return 1
    fi
    end_ts=$(date +%s)
    duration=$((end_ts - start_ts))
    minutes=$((duration / 60))
    seconds=$((duration % 60))
    log_success "$label command completed in ${minutes}m ${seconds}s."
    return 0
}

# --- 4b. Post-Sync CLI Hook 1: ROOT_DIR (BEFORE entering android/qssi) ---
# Customize this hook to run CLI commands at ROOT_DIR right after repo sync
# finishes (e.g. BSP scripts, vendor setup, git status across repos).
# Usage: post_sync_root_cli [command]
#   [command] optional; defaults to $REPO_POST_SYNC_ROOT_COMMAND
post_sync_root_cli() {
    local root_cmd="${1:-$REPO_POST_SYNC_ROOT_COMMAND}"

    log_info "============================================================"
    log_info " Running Post-Sync Hook 1: ROOT_DIR (Before android/qssi)"
    log_info " Current Directory: $(pwd)"
    log_info "============================================================"

    if [ -n "$root_cmd" ]; then
        if ! run_timed_command "root" "$root_cmd"; then
            log_error "Post-sync ROOT_DIR hook failed."
            exit 1
        fi
    else
        log_info "No REPO_POST_SYNC_ROOT_COMMAND set in $CONFIG_FILE_NAME."
        log_info "Add custom root commands directly in post_sync_root_cli() or config."
        # Example commands in ROOT_DIR:
        #   ./scripts/setup_bsp.sh
        #   git status -s
    fi

    log_success "Post-sync ROOT_DIR hook completed."
}

# --- 4c. Post-Sync CLI Hook 2: ANDROID_TOP (AFTER entering android/qssi) ---
# Customize this hook to run CLI commands after entering
# $ROOT_DIR/android/qssi ($ANDROID_TOP), e.g. full project rebuild, lunch.
# Usage: post_sync_cli [command]
#   [command] optional; defaults to $REPO_POST_SYNC_BUILD_COMMAND
post_sync_cli() {
    local build_cmd="${1:-$REPO_POST_SYNC_BUILD_COMMAND}"

    log_info "============================================"
    log_info " Running Post-Sync Custom CLI Hook"
    log_info " Current Directory: $(pwd)"
    log_info "============================================"

    if [ -n "$build_cmd" ]; then
        # FULL PROJECT REBUILD: REPO_POST_SYNC_BUILD_COMMAND in apk.config
        # Example: "source build/envsetup.sh && lunch ... && m -j$(nproc)"
        if ! run_timed_command "full project rebuild" "$build_cmd"; then
            log_error "Post-sync CLI hook failed."
            exit 1
        fi
    else
        log_info "No REPO_POST_SYNC_BUILD_COMMAND set in $CONFIG_FILE_NAME."
        log_info "You can configure REPO_POST_SYNC_BUILD_COMMAND in $CONFIG_FILE_NAME"
        log_info "or insert your custom build commands directly below in this function."
        # CUSTOM POST-SYNC CLI COMMANDS (THÊM LỆNH TÙY CHỌN TẠI ĐÂY):
        #   source build/envsetup.sh
        #   lunch ${CONFIG_TARGET_PRODUCT}-${CONFIG_TARGET_BUILD_VARIANT}
        #   m -j$(nproc)
        #   git status -s
    fi

    log_success "Post-sync CLI hook completed."
}

# --- 4c. Repo Reset Utility (--repo-reset: reset only, then exit) ---
# Usage: run_repo_reset [confirm_yes]
#   [confirm_yes] optional ("true"/"false"); defaults to $CONFIRM_YES
# NOTE: only runs when REPO_RESET=true (set by --repo-reset). A plain
# 'telua build' must NEVER reach the destructive 'repo forall' prompt.
run_repo_reset() {
    local confirm_yes="${1:-$CONFIRM_YES}"

    if [ "$REPO_RESET" != "true" ]; then
        return 0
    fi

    if ! command -v repo >/dev/null 2>&1; then
        log_error "'repo' binary not found in PATH! Please ensure Google repo is installed and accessible."
        exit 1
    fi

    if [ ! -d "$ROOT_DIR" ]; then
        log_error "ROOT_DIR '$ROOT_DIR' does not exist!"
        exit 1
    fi

    cd "$ROOT_DIR"
    echo ""
    log_warn "============================================================"
    log_warn " ⚠️  CAUTION: HARD RESET & CLEAN ALL REPOSITORIES (repo forall)!"
    log_warn " Target Directory: $ROOT_DIR"
    log_warn " Command:          repo forall -c \"git reset --hard && git clean -xdf\""
    log_warn " ALL uncommitted changes, staged files, and untracked files"
    log_warn " across ALL sub-repositories will be PERMANENTLY DESTROYED!"
    log_warn "============================================================"

    if [ "$confirm_yes" != "true" ]; then
        local user_confirm=""
        read -r -p "Are you sure you want to proceed with hard reset? [y/N]: " user_confirm
        case "$user_confirm" in
            [yY]|[yY][eE][sS])
                log_info "Confirmation received ('$user_confirm'). Proceeding with repo reset..."
                ;;
            *)
                log_warn "Operation cancelled by user. No files were modified."
                exit 0
                ;;
        esac
    else
        log_info "Bypassing confirmation (-y / --yes specified)."
    fi

    if ! repo forall -c "git reset --hard && git clean -xdf"; then
        log_error "'repo forall' git reset failed in $ROOT_DIR!"
        exit 1
    fi

    if [ "$REPO_SYNC" = "true" ]; then
        log_success "All repositories reset and cleaned successfully. Proceeding to repo sync..."
    else
        log_success "All repositories reset and cleaned successfully. Exiting (no sync, no build)."
        exit 0
    fi
}

# --- 4d. Repo Sync Utility ---
# Usage: run_repo_sync [jobs] [flags]
#   [jobs]  optional; defaults to ${REPO_SYNC_JOBS:-4}
#   [flags] optional; defaults to ${REPO_SYNC_FLAGS:--d -c --force-sync --no-clone-bundle --tags}
run_repo_sync() {
    local jobs="${1:-${REPO_SYNC_JOBS:-4}}"
    local sync_flags="${2:-${REPO_SYNC_FLAGS:--d -c --force-sync --no-clone-bundle --tags}}"

    if [ "$REPO_SYNC" != "true" ]; then
        return 0
    fi

    log_info "============================================"
    log_info " Starting Repo Sync in ROOT_DIR"
    log_info "============================================"

    if ! command -v repo >/dev/null 2>&1; then
        log_error "'repo' binary not found in PATH! Please ensure Google repo is installed and accessible."
        exit 1
    fi

    if [ ! -d "$ROOT_DIR" ]; then
        log_error "ROOT_DIR '$ROOT_DIR' does not exist!"
        exit 1
    fi

    log_info "Navigating to ROOT_DIR: $ROOT_DIR"
    cd "$ROOT_DIR"

    if [ ! -d ".repo" ]; then
        log_warn "No '.repo' directory found in ROOT_DIR ($ROOT_DIR). Attempting repo sync anyway..."
    fi

    local start_ts
    start_ts=$(date +%s)
    local start_str
    start_str=$(date '+%Y-%m-%d %H:%M:%S')

    log_info "Sync started at: $start_str"
    log_info "Executing: repo sync -j$jobs $sync_flags"
    log_warn "NOTE: 'repo sync' can take a substantial amount of time. Please wait..."

    if ! repo sync -j"$jobs" $sync_flags; then
        log_error "repo sync failed in $ROOT_DIR!"
        exit 1
    fi

    local end_ts
    end_ts=$(date +%s)
    local duration=$((end_ts - start_ts))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))
    log_success "repo sync completed in ${minutes}m ${seconds}s ($duration seconds)."

    # 1. Run Hook 1 in ROOT_DIR (BEFORE cd to android/qssi)
    post_sync_root_cli

    # 2. Navigate to ANDROID_TOP
    log_info "Navigating to: $ANDROID_TOP"
    if [ ! -d "$ANDROID_TOP" ]; then
        log_error "Target directory '$ANDROID_TOP' does not exist after repo sync!"
        exit 1
    fi
    cd "$ANDROID_TOP"
    log_info "Current working directory: $(pwd)"

    # 3. Run Hook 2 in ANDROID_TOP (AFTER cd to android/qssi)
    post_sync_cli
}
