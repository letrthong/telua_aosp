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
# telua_untils.sh - Init & Update utilities for the Telua toolkit.
# Single source of truth for the code behind 'telua init' and 'telua update',
# previously inlined in build_apk.sh:
#   - 'telua init'  : init_project_config (+ apply_config_overlay,
#                     install_python_requirements, ensure_script_permissions,
#                     ensure_personal_configs)
#   - 'telua update': run_git_update (+ git_pull_with_recovery,
#                     backup_personal_configs, restore_personal_configs)
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_untils.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, MASTER_SCRIPT_DIR, CONFIG_FILE_NAME,
#       PERSONAL_CONFIG_FILES (array)
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_UNTILS_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_UNTILS_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_UNTILS_SOURCED=1

# ==============================================================================
# Shared low-level helpers (used by both 'init' and 'update' flows)
# ==============================================================================

# Restore executable bits on toolkit scripts inside the given repo directory.
# Missing files are skipped so 'set -e' never aborts the update.
# Covers the main scripts AND every src/*.sh module (telua_log, telua_git,
# telua_untils, telua_car, telua_run, ...) so 'telua update' never leaves a
# freshly pulled module non-executable.
# Usage: ensure_script_permissions <repo_dir>
ensure_script_permissions() {
    local repo_dir="$1"
    local script
    if [ -z "$repo_dir" ] || [ ! -d "$repo_dir" ]; then
        log_warn "ensure_script_permissions: invalid directory '$repo_dir'"
        return 0
    fi
    for script in build_apk.sh python/config_crypto.py python/config_overlay.py config_crypto.py config_overlay.py; do
        if [ -f "$repo_dir/$script" ]; then
            chmod +x "$repo_dir/$script" || log_warn "Failed to chmod +x $repo_dir/$script"
        fi
    done
    # All shell modules under src/ (glob may not match on older checkouts).
    for script in "$repo_dir"/src/*.sh; do
        if [ -f "$script" ]; then
            chmod +x "$script" || log_warn "Failed to chmod +x $script"
        fi
    done
}

# Create missing personal configs from their tracked '<file>.example' templates.
# Existing files are never overwritten. Usage: ensure_personal_configs <repo_dir>
ensure_personal_configs() {
    local repo_dir="$1"
    local rel
    for rel in "${PERSONAL_CONFIG_FILES[@]}"; do
        if [ ! -f "$repo_dir/$rel" ] && [ -f "$repo_dir/$rel.example" ]; then
            if cp "$repo_dir/$rel.example" "$repo_dir/$rel"; then
                log_info "Created personal config: $repo_dir/$rel (from $rel.example)"
            else
                log_warn "Failed to create $repo_dir/$rel from $rel.example"
            fi
        fi
    done
}

# ==============================================================================
# 'telua init' support (init_project_config and its helpers)
# ==============================================================================

# --- 1a-pre. Install Python Dependencies (--install / --init) ---
install_python_requirements() {
    local req_file="$MASTER_SCRIPT_DIR/requirements.txt"
    [ ! -f "$req_file" ] && req_file="$SCRIPT_DIR/requirements.txt"

    if ! command -v python3 >/dev/null 2>&1; then
        return 0
    fi

    # Check if cryptography module is already available
    if python3 -c "import cryptography" >/dev/null 2>&1; then
        return 0
    fi

    echo ""
    log_info "============================================================"
    log_info " Checking & Installing Python Dependencies"
    log_info " Missing package: 'cryptography' (used by config_crypto.py)"
    log_info "============================================================"

    if command -v pip3 >/dev/null 2>&1 || python3 -m pip --version >/dev/null 2>&1; then
        if [ -f "$req_file" ]; then
            log_info "Executing: python3 -m pip install -r $req_file"
            if python3 -m pip install -r "$req_file"; then
                log_success "Python dependencies installed successfully."
            else
                log_warn "Failed to install Python dependencies via pip. You can install manually:"
                log_warn "  python3 -m pip install -r $req_file"
            fi
        else
            log_info "Executing: python3 -m pip install cryptography"
            if python3 -m pip install cryptography; then
                log_success "'cryptography' installed successfully."
            else
                log_warn "Failed to install 'cryptography' via pip."
            fi
        fi
    else
        log_warn "'pip' not found. Please install manually:"
        log_warn "  sudo apt install python3-pip && python3 -m pip install cryptography"
    fi
    echo ""
}

# --- 1b. Initialize Project Config (--init) ---
# Apply apk_overlays.config (personal/site overrides) on top of a freshly created apk.config.
# Looked up next to the script (SCRIPT_DIR), then in the master toolkit dir. No-op if absent.
apply_config_overlay() {
    local target_config="$1"
    local overlay_name="apk_overlays.config"
    local overlay_file="" overlay_script="" dir

    for dir in "$SCRIPT_DIR" "$MASTER_SCRIPT_DIR"; do
        if [ -z "$overlay_file" ] && [ -f "$dir/$overlay_name" ]; then
            overlay_file="$dir/$overlay_name"
        fi
        # Prefer python/ subdir (new layout), fall back to repo root (old layout).
        if [ -z "$overlay_script" ] && [ -f "$dir/python/config_overlay.py" ]; then
            overlay_script="$dir/python/config_overlay.py"
        fi
        if [ -z "$overlay_script" ] && [ -f "$dir/config_overlay.py" ]; then
            overlay_script="$dir/config_overlay.py"
        fi
    done

    if [ -z "$overlay_file" ]; then
        return 0
    fi
    if [ -z "$overlay_script" ]; then
        log_warn "Found $overlay_file but config_overlay.py is missing. Overlay skipped."
        return 0
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        log_warn "python3 not found. $overlay_name was not applied."
        return 0
    fi

    log_info "Applying overlay: $overlay_file"
    if python3 "$overlay_script" "$target_config" "$overlay_file"; then
        log_success "Overlay applied to: $target_config"
    else
        log_warn "Failed to apply $overlay_name. $CONFIG_FILE_NAME was created without overlay."
    fi
}

# --- 1b. Initialize Project Config (--init) ---
# Creates $PWD/apk.config from the encrypted template (enc_apk.config, password
# prompt) or the plain template, then applies the personal overlay.
init_project_config() {
    local target_config="$PWD/$CONFIG_FILE_NAME"
    local template_config="$SCRIPT_DIR/$CONFIG_FILE_NAME"
    local enc_config="$SCRIPT_DIR/enc_apk.config"
    # Prefer python/ subdir (new layout), fall back to repo root (old layout).
    local crypto_script
    if [ -f "$SCRIPT_DIR/python/config_crypto.py" ]; then
        crypto_script="$SCRIPT_DIR/python/config_crypto.py"
    else
        crypto_script="$SCRIPT_DIR/config_crypto.py"
    fi

    # Make sure helper scripts (config_crypto.py, config_overlay.py, ...) are executable.
    # Covers both the script dir and the master dir (they differ when run via symlink).
    ensure_script_permissions "$SCRIPT_DIR"
    if [ "$MASTER_SCRIPT_DIR" != "$SCRIPT_DIR" ]; then
        ensure_script_permissions "$MASTER_SCRIPT_DIR"
    fi

    # Create missing personal configs (apk_overlays.config, const_my_cli.config) from *.example
    ensure_personal_configs "$MASTER_SCRIPT_DIR"

    if [ "$PWD" = "$SCRIPT_DIR" ]; then
        log_warn "Already in master script directory ($PWD). Template config is here."
        exit 0
    fi

    if [ -f "$target_config" ]; then
        log_warn "'$CONFIG_FILE_NAME' already exists in current directory ($PWD)."
        read -r -p "Do you want to overwrite it? (y/N): " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            log_info "Aborted. Existing $CONFIG_FILE_NAME preserved."
            exit 0
        fi
    fi

    # Case 1: Decrypt from enc_apk.config using config_crypto.py
    if [ -f "$enc_config" ] && [ -f "$crypto_script" ]; then
        echo -n -e "\033[1;33m[PROMPT]\033[0m Enter password to decrypt enc_apk.config (Press Enter to use default config): "
        local input_pw
        read -r -s input_pw
        echo ""

        if [ -z "$input_pw" ]; then
            log_info "No password entered. Copying default $CONFIG_FILE_NAME..."
        else
            install_python_requirements
            log_info "Decrypting template using config_crypto.py..."
            if printf '%s\n' "$input_pw" | python3 "$crypto_script" decrypt -i "$enc_config" -o "$target_config" --force - 2>/dev/null; then
                unset input_pw
                log_success "Successfully decrypted and created: $target_config"
                apply_config_overlay "$target_config"
                log_info "Next: edit $CONFIG_FILE_NAME, then run: telua --info"
                exit 0
            else
                unset input_pw
                log_warn "Decryption failed (incorrect password)! Falling back to default $CONFIG_FILE_NAME..."
            fi
        fi
        unset input_pw
    fi

    # Case 2: Copy default plain template config
    if [ -f "$template_config" ]; then
        cp "$template_config" "$target_config"
        log_success "Initialized with default template: $target_config"
        apply_config_overlay "$target_config"
        log_info "Next: edit $CONFIG_FILE_NAME, then run: telua --info"
        exit 0
    fi

    log_error "Neither '$enc_config' nor '$template_config' was found in $SCRIPT_DIR!"
    exit 1
}

# ==============================================================================
# 'telua update' support (run_git_update and its helpers)
# ==============================================================================

# Back up personal configs before 'telua update' (git reset --hard would wipe tracked edits).
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

# git pull origin main; on failure: fetch + reset --hard origin/main, then pull again.
# Returns 0 on success, 1 on failure (never exits, so the caller can restore backups).
git_pull_with_recovery() {
    local target_repo="$1"

    log_info "Executing: git pull origin main..."
    if git -C "$target_repo" pull origin main; then
        log_success "Successfully pulled latest updates from origin/main."
        return 0
    fi

    # Neu loi thi reset hard va pull ve lai
    log_warn "'git pull origin main' encountered an error or merge conflict!"
    log_info "Initiating automatic recovery: fetching origin main..."
    git -C "$target_repo" fetch origin main || true

    log_info "Running: git reset --hard origin/main..."
    if ! git -C "$target_repo" reset --hard origin/main; then
        log_error "Failed to execute 'git reset --hard origin/main'."
        return 1
    fi
    log_success "Reset repository to origin/main successfully."

    log_info "Retrying: git pull origin main..."
    if git -C "$target_repo" pull origin main; then
        log_success "Successfully pulled latest updates after hard reset."
        return 0
    fi
    log_error "'git pull origin main' failed after hard reset."
    return 1
}

# --- 4c. Git Update Utility (--update / update: git pull origin main with auto reset hard) ---
run_git_update() {
    local target_repo="$SCRIPT_DIR"
    if [ -L "${BASH_SOURCE[0]}" ]; then
        local real_file
        real_file="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "")"
        if [ -n "$real_file" ] && [ -f "$real_file" ]; then
            target_repo="$(cd "$(dirname "$real_file")" && pwd)"
        fi
    fi

    echo ""
    log_info "============================================================"
    log_info " Updating Telua Toolkit from Git Remote (origin/main)"
    log_info " Target Repository: $target_repo"
    log_info "============================================================"

    if ! command -v git >/dev/null 2>&1; then
        log_error "'git' command not found. Please ensure Git is installed and in PATH."
        exit 1
    fi

    if ! git -C "$target_repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_error "'$target_repo' is not a Git repository!"
        exit 1
    fi

    local current_branch
    current_branch="$(git -C "$target_repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
    log_info "Active Git branch: $current_branch"

    # Protect personal configs: reset --hard below would overwrite them if they are tracked.
    local backup_dir=""
    if ! backup_dir="$(backup_personal_configs "$target_repo")"; then
        log_error "Failed to back up personal configs. Update aborted to protect your files."
        exit 1
    fi
    if [ -n "$backup_dir" ]; then
        log_info "Backed up personal configs to: $backup_dir"
    fi

    local update_status=0
    git_pull_with_recovery "$target_repo" || update_status=$?

    restore_personal_configs "$target_repo" "$backup_dir"

    if [ "$update_status" -eq 0 ]; then
        ensure_script_permissions "$target_repo"
        exit 0
    fi
    exit 1
}

