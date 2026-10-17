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
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_repo.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       CONFIG_FILE_NAME, ROOT_DIR, ANDROID_TOP
#   - The host must set the flags REPO_SYNC / REPO_RESET / CONFIRM_YES
#     (from CLI parsing) before calling run_repo_sync / run_repo_reset.
#   - Optional config variables (read from apk.config):
#       REPO_SYNC_JOBS, REPO_SYNC_FLAGS, REPO_POST_SYNC_ROOT_COMMAND,
#       POST_SYNC_ROOT_COMMAND, REPO_POST_SYNC_BUILD_COMMAND,
#       POST_SYNC_BUILD_COMMAND
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

# --- 4b. Post-Sync CLI Hook 1: ROOT_DIR (BEFORE entering android/qssi) ---
# Customize this function to run CLI commands at ROOT_DIR right after repo sync finishes.
# (e.g. BSP scripts, vendor setup, git status across repos)
post_sync_root_cli() {
    log_info "============================================================"
    log_info " Running Post-Sync Hook 1: ROOT_DIR (Before android/qssi)"
    log_info " Current Directory: $(pwd)"
    log_info "============================================================"

    local root_cmd="${REPO_POST_SYNC_ROOT_COMMAND:-$POST_SYNC_ROOT_COMMAND}"
    if [ -n "$root_cmd" ]; then
        log_info "Executing root command from config: $root_cmd"
        local r_start
        r_start=$(date +%s)
        eval "$root_cmd"
        local r_end
        r_end=$(date +%s)
        local r_dur=$((r_end - r_start))
        log_success "Root command completed in $((r_dur / 60))m $((r_dur % 60))s."
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
# Customize this function to run CLI commands after entering $ROOT_DIR/android/qssi ($ANDROID_TOP).
# (e.g. full project rebuild, lunch, target compile)
post_sync_cli() {
    log_info "============================================"
    log_info " Running Post-Sync Custom CLI Hook"
    log_info " Current Directory: $(pwd)"
    log_info "============================================"

    # --------------------------------------------------------------------------
    # 1. FULL PROJECT REBUILD (CẬP NHẬT CLI TẠI ĐÂY)
    # Nếu đã cấu hình REPO_POST_SYNC_BUILD_COMMAND trong apk.config thì tự động chạy:
    # --------------------------------------------------------------------------
    local build_cmd="${REPO_POST_SYNC_BUILD_COMMAND:-$POST_SYNC_BUILD_COMMAND}"
    if [ -n "$build_cmd" ]; then
        log_info "Executing full project rebuild command from config:"
        log_info ">> $build_cmd"
        local b_start
        b_start=$(date +%s)
        eval "$build_cmd"
        local b_end
        b_end=$(date +%s)
        local b_dur=$((b_end - b_start))
        log_success "Full project rebuild completed in $((b_dur / 60))m $((b_dur % 60))s."
    else
        log_info "No REPO_POST_SYNC_BUILD_COMMAND set in $CONFIG_FILE_NAME."
        log_info "You can configure REPO_POST_SYNC_BUILD_COMMAND in $CONFIG_FILE_NAME"
        log_info "or insert your custom build commands directly below in this function."
    fi

    # --------------------------------------------------------------------------
    # 2. CUSTOM POST-SYNC CLI COMMANDS (THÊM LỆNH TÙY CHỌN TẠI ĐÂY):
    # Ví dụ khi cần cập nhật sau này:
    #   source build/envsetup.sh
    #   lunch ${CONFIG_TARGET_PRODUCT}-${CONFIG_TARGET_BUILD_VARIANT}
    #   m -j$(nproc)
    #   git status -s
    # --------------------------------------------------------------------------

    log_success "Post-sync CLI hook completed."
}

# --- 4c. Repo Reset Utility (--repo-reset: reset only, then exit) ---
run_repo_reset() {
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

    if [ "$CONFIRM_YES" != "true" ]; then
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
run_repo_sync() {
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

    local jobs="${REPO_SYNC_JOBS:-4}"
    local sync_flags="${REPO_SYNC_FLAGS:--d -c --force-sync --no-clone-bundle --tags}"
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
