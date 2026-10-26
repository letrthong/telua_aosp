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


# --- Constants & Global Defaults ---
TELUA_GIT_VERSION="1.2.0"
TELUA_GIT_LAST_UPDATED="2026-10-17"
GIT_CONFIG_FILE_NAME="const_git.config"
CONST_CONFIG_DIR_NAME="config"
DEFAULT_GIT_BRANCH="main"

# ==============================================================================
# telua_git.sh - Git utilities for the Telua toolkit.
# Single source of truth for the git-related commands of build_apk.sh:
#   - 'telua --git-diff'  : run_git_diff  (show last commit, then exit)
#   - 'telua --git-amend' : run_git_amend (amend last commit, then exit)
#   - 'telua --git-help'  : show_git_help (print const_git.config cheatsheet)
# NOTE: 'telua update' (run_git_update + backup/restore_personal_configs +
# git_pull_with_recovery) lives in src/telua_utils.sh because it also serves
# the init flow (shared ensure_* helpers).
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_git.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, MASTER_SCRIPT_DIR, GIT_CONFIG_FILE
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_GIT_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_GIT_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_GIT_SOURCED=1

# --- 4c. Git Diff Utility (--git-diff: show last commit, then exit) ---
run_git_diff() {
    if [ "$GIT_DIFF" != "true" ]; then
        return 0
    fi

    log_info "Running in $SCRIPT_DIR: git diff HEAD^ HEAD"
    if ! git -C "$SCRIPT_DIR" diff HEAD^ HEAD; then
        log_error "'git diff HEAD^ HEAD' failed (is $SCRIPT_DIR a git repo with at least 2 commits?)"
        exit 1
    fi
    exit 0
}

# --- 4c. Git Amend Utility (--git-amend: amend last commit, then exit) ---
run_git_amend() {
    if [ "$GIT_AMEND" != "true" ]; then
        return 0
    fi

    log_info "Running in $SCRIPT_DIR: git commit --amend --no-edit"
    if ! git -C "$SCRIPT_DIR" commit --amend --no-edit; then
        log_error "'git commit --amend --no-edit' failed (is $SCRIPT_DIR a git repo with a commit to amend?)"
        exit 1
    fi
    log_success "Last commit amended."
    exit 0
}

# --- 4c. Git Help Utility (--git-help: frequently used Git commands) ---
# Commands are read dynamically from const_git.config (located with build_apk.sh)
show_git_help() {
    if [ -f "$GIT_CONFIG_FILE" ]; then
        cat "$GIT_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$GIT_CONFIG_FILE_NAME" ]; then
        cat "$MASTER_SCRIPT_DIR/$GIT_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$GIT_CONFIG_FILE_NAME" ]; then
        cat "$SCRIPT_DIR/$GIT_CONFIG_FILE_NAME"
    else
        log_warn "Git cheatsheet file '$GIT_CONFIG_FILE_NAME' not found!"
    fi
    exit 0
}



