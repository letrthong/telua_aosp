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
# telua_utils.sh - Init & Update utilities for the Telua toolkit.
# Single source of truth for the code behind 'telua init' and 'telua update',
# previously inlined in build_apk.sh:
#   - 'telua init'  : init_project_config (+ apply_config_overlay,
#                     install_python_requirements, ensure_script_permissions,
#                     ensure_personal_configs)
#   - 'telua update': run_git_update (+ git_pull_with_recovery,
#                     backup_personal_configs, restore_personal_configs)
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_utils.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, MASTER_SCRIPT_DIR, CONFIG_FILE_NAME,
#       PERSONAL_CONFIG_FILES (array)
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_UTILS_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_UTILS_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_UTILS_SOURCED=1

# ==============================================================================
# Shared low-level helpers (used by both 'init' and 'update' flows)
# ==============================================================================

# Restore executable bits on toolkit scripts inside the given repo directory.
# Missing files are skipped so 'set -e' never aborts the update.
# Covers the main scripts, EVERY python helper under python/ (config_crypto,
# config_overlay, apply_apk_overlays, ...) and every src/*.sh module
# (telua_log, telua_git, telua_utils, telua_car, telua_run, ...) so
# 'telua init' / 'telua update' never leave a freshly pulled file
# non-executable.
# Usage: ensure_script_permissions <repo_dir>
ensure_script_permissions() {
    local repo_dir="$1"
    local script
    if [ -z "$repo_dir" ] || [ ! -d "$repo_dir" ]; then
        log_warn "ensure_script_permissions: invalid directory '$repo_dir'"
        return 0
    fi
    for script in build_apk.sh config_crypto.py config_overlay.py; do
        if [ -f "$repo_dir/$script" ]; then
            chmod +x "$repo_dir/$script" || log_warn "Failed to chmod +x $repo_dir/$script"
        fi
    done
    # All python helpers under python/ (glob covers future additions).
    for script in "$repo_dir"/python/*.py; do
        if [ -f "$script" ]; then
            chmod +x "$script" || log_warn "Failed to chmod +x $script"
        fi
    done
    # All shell modules under src/ (glob may not match on older checkouts).
    for script in "$repo_dir"/src/*.sh; do
        if [ -f "$script" ]; then
            chmod +x "$script" || log_warn "Failed to chmod +x $script"
        fi
    done
    # All sphinx doc-as-code scripts and shell utilities
    for script in "$repo_dir"/sphinx/*.sh "$repo_dir"/sphinx/scripts/*.py; do
        if [ -f "$script" ]; then
            chmod +x "$script" 2>/dev/null || log_warn "Failed to chmod +x $script"
        fi
    done
    # All third_party submodule scripts (e.g. google-java-format-pre-commit)
    for script in "$repo_dir"/third_party/*/*.sh "$repo_dir"/third_party/*/pre-commit; do
        if [ -f "$script" ]; then
            chmod +x "$script" 2>/dev/null || log_warn "Failed to chmod +x $script"
        fi
    done
}

# Initialize and update Git submodules declared in .gitmodules (e.g.
# third_party/google-java-format).
# Usage: sync_git_submodules <repo_dir>
sync_git_submodules() {
    local repo_dir="$1"
    if [ -z "$repo_dir" ] || [ ! -d "$repo_dir" ] || ! command -v git >/dev/null 2>&1; then
        return 0
    fi
    if [ -f "$repo_dir/.gitmodules" ]; then
        git -C "$repo_dir" submodule update --init --recursive 2>/dev/null || true
    fi
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
# Looked up under config/ (or root fallback) in SCRIPT_DIR and MASTER_SCRIPT_DIR. No-op if absent.
apply_config_overlay() {
    local target_config="$1"
    local overlay_name="apk_overlays.config"
    local overlay_file="" overlay_script="" dir

    # Lookup order per dir: config/overlay/ (new personal overlay dir, git-ignored)
    # -> config/ (legacy) -> repo root (legacy).
    for dir in "$SCRIPT_DIR" "$MASTER_SCRIPT_DIR"; do
        if [ -z "$overlay_file" ] && [ -f "$dir/config/overlay/$overlay_name" ]; then
            overlay_file="$dir/config/overlay/$overlay_name"
        fi
        if [ -z "$overlay_file" ] && [ -f "$dir/config/$overlay_name" ]; then
            overlay_file="$dir/config/$overlay_name"
        fi
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

# Apply the profile requested via 'telua init -p <name>' to the freshly created
# apk.config (after the overlay merge). No-op when no -p was given or the
# ACTIVE_PROJECT key is missing. Usage: apply_init_profile <target_config>
apply_init_profile() {
    local target_config="$1"
    if [ -z "${CLI_PROFILE:-}" ] || [ ! -f "$target_config" ]; then
        return 0
    fi
    if grep -qE '^[[:space:]]*ACTIVE_PROJECT=' "$target_config"; then
        sed -i -E "s/^[[:space:]]*ACTIVE_PROJECT=.*/ACTIVE_PROJECT=\"$CLI_PROFILE\"/" "$target_config"
        log_info "Updated ACTIVE_PROJECT=\"$CLI_PROFILE\" in $target_config"
    else
        log_warn "No ACTIVE_PROJECT key in $target_config; profile '$CLI_PROFILE' not applied."
    fi
}

# --- 1b. Initialize Project Config (--init) ---
# Creates $PWD/apk.config from the encrypted template (config/enc_apk.config, password
# prompt) or the plain template (config/apk.config), then applies the personal overlay.
init_project_config() {
    local base_toolkit_dir="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}"
    local target_config="$PWD/$CONFIG_FILE_NAME"
    local template_config="$base_toolkit_dir/config/$CONFIG_FILE_NAME"
    [ ! -f "$template_config" ] && template_config="$base_toolkit_dir/$CONFIG_FILE_NAME"
    local enc_config="$base_toolkit_dir/config/enc_apk.config"
    [ ! -f "$enc_config" ] && enc_config="$base_toolkit_dir/enc_apk.config"
    # Prefer python/ subdir (new layout), fall back to repo root (old layout).
    local crypto_script
    if [ -f "$base_toolkit_dir/python/config_crypto.py" ]; then
        crypto_script="$base_toolkit_dir/python/config_crypto.py"
    else
        crypto_script="$base_toolkit_dir/config_crypto.py"
    fi

    # Make sure helper scripts (config_crypto.py, config_overlay.py, ...) are executable.
    # Covers both the script dir and the master dir (they differ when run via symlink).
    ensure_script_permissions "$SCRIPT_DIR"
    if [ "$MASTER_SCRIPT_DIR" != "$SCRIPT_DIR" ]; then
        ensure_script_permissions "$MASTER_SCRIPT_DIR"
    fi

    # Decrypt private overlay configs (enc_apk_overlays.config, enc_const_my_cli.config) if present
    local enc_overlay="$base_toolkit_dir/config/overlay/enc_apk_overlays.config"
    local enc_my_cli="$base_toolkit_dir/config/overlay/enc_const_my_cli.config"
    if { [ -f "$enc_overlay" ] || [ -f "$enc_my_cli" ]; } && [ -f "$crypto_script" ] && [ -t 0 ] && [ -t 1 ]; then
        echo -n -e "\033[1;33m[PROMPT]\033[0m Enter password to decrypt private configs in config/overlay/ (Press Enter to skip): "
        local overlay_pw
        read -r -s overlay_pw
        echo ""
        if [ -n "$overlay_pw" ]; then
            install_python_requirements
            log_info "Decrypting private overlay configs using config_crypto.py..."
            if printf '%s\n' "$overlay_pw" | python3 "$crypto_script" decrypt -d "$base_toolkit_dir/config/overlay" --force - 2>/dev/null; then
                log_success "Successfully decrypted private overlay configs in $base_toolkit_dir/config/overlay/"
            else
                log_warn "Decryption of private overlay configs failed (incorrect password)! Falling back to *.example..."
            fi
        fi
        unset overlay_pw
    fi

    # Create missing personal configs (apk_overlays.config, const_my_cli.config) from *.example
    ensure_personal_configs "$MASTER_SCRIPT_DIR"
    sync_git_submodules "$MASTER_SCRIPT_DIR"

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
                apply_init_profile "$target_config"
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
        apply_init_profile "$target_config"
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
    local target_repo="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}"
    if [ -z "$target_repo" ] || [ ! -d "$target_repo/.git" ]; then
        local real_file
        real_file="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "")"
        if [ -n "$real_file" ] && [ -f "$real_file" ]; then
            # BASH_SOURCE is in src/, repo root is parent directory
            target_repo="$(cd "$(dirname "$real_file")/.." && pwd)"
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
        sync_git_submodules "$target_repo"
        ensure_script_permissions "$target_repo"
        exit 0
    fi
    exit 1
}

# ==============================================================================
# Shared CLI Specification & ADB Utilities
# ==============================================================================

# Parse a CLI specification item ("action :: description :: command" or legacy "action|description|command")
# Usage:
#   parse_cli_item "$item" action_var desc_var [cmd_var]
# Example:
#   parse_cli_item "ks :: Kill Server :: am kill-all" act desc cmd
#   parse_cli_item "net-up :: Bring up eth0" act desc
parse_cli_item() {
    local __pci_raw="$1"
    local __pci_out_action="$2"
    local __pci_out_desc="$3"
    local __pci_out_cmd="${4:-}"

    local __pci_act="" __pci_desc="" __pci_cmd=""
    if [[ "$__pci_raw" == *" :: "* ]]; then
        __pci_act="${__pci_raw%% :: *}"
        local __pci_rest="${__pci_raw#* :: }"
        if [[ "$__pci_rest" == *" :: "* ]]; then
            __pci_desc="${__pci_rest%% :: *}"
            __pci_cmd="${__pci_rest#* :: }"
        else
            __pci_desc="$__pci_rest"
            __pci_cmd=""
        fi
    elif [[ "$__pci_raw" == *"|"* ]]; then
        __pci_act="$(echo "$__pci_raw" | cut -d'|' -f1)"
        __pci_desc="$(echo "$__pci_raw" | cut -d'|' -f2)"
        __pci_cmd="$(echo "$__pci_raw" | cut -d'|' -f3-)"
    else
        __pci_act="$__pci_raw"
        __pci_desc="$__pci_raw"
        __pci_cmd=""
    fi

    # Trim leading/trailing whitespace WITHOUT xargs: xargs also strips shell
    # quotes, which breaks commands containing quoted args (e.g.
    # "grep -E 'A|B|C'") by silently removing the quotes before execution.
    __pci_act="${__pci_act#"${__pci_act%%[![:space:]]*}"}"
    __pci_act="${__pci_act%"${__pci_act##*[![:space:]]}"}"
    __pci_desc="${__pci_desc#"${__pci_desc%%[![:space:]]*}"}"
    __pci_desc="${__pci_desc%"${__pci_desc##*[![:space:]]}"}"
    if [ -n "$__pci_cmd" ]; then
        __pci_cmd="${__pci_cmd#"${__pci_cmd%%[![:space:]]*}"}"
        __pci_cmd="${__pci_cmd%"${__pci_cmd##*[![:space:]]}"}"
    fi

    printf -v "$__pci_out_action" '%s' "$__pci_act"
    printf -v "$__pci_out_desc" '%s' "$__pci_desc"
    [ -n "$__pci_out_cmd" ] && printf -v "$__pci_out_cmd" '%s' "$__pci_cmd"
    return 0
}

# Verify Android device is connected and online before executing ADB commands.
# If multiple devices are detected and ANDROID_SERIAL is not set, prints an informative warning.
# Returns 0 if device is ready, 1 on error/offline.
check_adb_device_online() {
    if ! command -v adb >/dev/null 2>&1; then
        log_error "device offline: 'adb' command not found. Please ensure Android platform-tools is in PATH."
        return 1
    fi

    local dev_state
    dev_state=$(adb get-state 2>/dev/null || echo "offline")
    local online_devices
    online_devices=$(adb devices 2>/dev/null | grep -v "List of devices attached" | grep -w "device" || true)

    if [ "$dev_state" != "device" ] && [ -z "$online_devices" ]; then
        local raw_devices
        raw_devices=$(adb devices 2>/dev/null | grep -v "List of devices attached" | grep -v "^$" || true)
        if [ -n "$raw_devices" ]; then
            log_error "device offline: Connected Android device is not ready (state: $dev_state)."
        else
            log_error "device offline: No Android device connected."
        fi
        log_error "Please connect a device via USB/TCP and verify with 'adb devices'."
        return 1
    fi

    # Multiple devices awareness: warn user if multiple devices exist and ANDROID_SERIAL is unset
    if [ -z "${ANDROID_SERIAL:-}" ]; then
        local dev_count
        dev_count=$(echo "$online_devices" | grep -c . || true)
        if [ "$dev_count" -gt 1 ]; then
            log_warn "Multiple Android devices connected ($dev_count devices). Consider setting: export ANDROID_SERIAL=<device_serial>"
        fi
    fi

    return 0
}

# Execute a sequential multi-command pipeline array with step-by-step progress, timing & fail-fast safety.
# Usage:
#   execute_command_pipeline "Pipeline Name" "Description" "${step_cmds[@]}"
execute_command_pipeline() {
    local pipeline_name="$1"
    local pipeline_desc="$2"
    shift 2
    local -a steps=("$@")

    local total_steps="${#steps[@]}"
    if [ "$total_steps" -eq 0 ]; then
        log_error "Pipeline '$pipeline_name' has no steps defined to execute!"
        return 1
    fi

    # Auto device pre-check: if any step is an ADB command (directly or via
    # 'adb shell ...' fallback), verify a device is connected & online BEFORE
    # starting, so the pipeline fails fast with a clear message instead of
    # failing mid-way at the first adb step. Host-only pipelines (no adb
    # steps, e.g. 'unittest', 'net-up', 'logcat-stop') skip the check.
    # Opt-out: TELUA_RUN_SKIP_DEVICE_CHECK=1.
    local needs_device=0
    local cmd_probe
    for cmd_probe in "${steps[@]}"; do
        if [[ "$cmd_probe" =~ ^adb([[:space:]]|$) ]] || [[ "$cmd_probe" =~ ^adb\ shell ]]; then
            needs_device=1
            break
        fi
    done
    if [ "$needs_device" -eq 1 ] && [ "${TELUA_RUN_SKIP_DEVICE_CHECK:-0}" != "1" ]; then
        log_info "Pipeline contains ADB steps; verifying device connectivity first..."
        if ! check_adb_device_online; then
            log_error "Pipeline '$pipeline_name' aborted before start (no ready device)."
            log_error "Connect a device or set TELUA_RUN_SKIP_DEVICE_CHECK=1 to bypass."
            return 1
        fi
    fi

    echo ""
    log_info "============================================================"
    log_info " Executing Pipeline: '$pipeline_name'"
    [ -n "$pipeline_desc" ] && log_info " Description: $pipeline_desc"
    log_info " Total Steps: $total_steps"
    log_info "============================================================"

    # Ensure 'tel' and 'telua' work inside non-interactive pipeline subshells (e.g. Web UI '▶ Run')
    # where ~/.bashrc aliases are not loaded.
    if ! command -v tel >/dev/null 2>&1; then
        tel() { "$MASTER_SCRIPT_DIR/build_apk.sh" "$@"; }
    fi
    if ! command -v telua >/dev/null 2>&1; then
        telua() { "$MASTER_SCRIPT_DIR/build_apk.sh" "$@"; }
    fi

    local step_idx=1
    for cmd in "${steps[@]}"; do
        echo ""
        echo -e "\033[1;36m[STEP $step_idx/$total_steps]\033[0m \033[1;37m$cmd\033[0m"
        local step_start
        step_start=$(date +%s)

        local ret=0
        if [[ "$cmd" =~ ^(adb|sudo|echo|sleep|cd|export|source|\.|tel|telua|git|repo|python|python3|bash|sh|test|\[|mkdir|rm|cp|mv|ls|pwd)([[:space:]]|$) ]] || [[ "$cmd" =~ ^\./ ]]; then
            eval "$cmd"
            ret=$?
        else
            adb shell "$cmd" 2>/dev/null || eval "$cmd"
            ret=$?
        fi

        if [ $ret -eq 0 ]; then
            local step_end
            step_end=$(date +%s)
            local step_dur=$((step_end - step_start))
            log_success "Step $step_idx/$total_steps finished (${step_dur}s)."
        else
            local exit_code=$ret
            log_error "Step $step_idx failed with exit code $exit_code! Aborting pipeline."
            exit $exit_code
        fi
        step_idx=$((step_idx + 1))
    done

    echo ""
    log_success "All $total_steps steps of pipeline '$pipeline_name' completed successfully."
    echo ""
    return 0
}

# ==============================================================================
# 'telua crypto' / 'tel enc' / 'tel dec' support (Private Overlay Encryption)
# ==============================================================================

_crypto_get_python_cmd() {
    local py path_to_py
    for py in python3 python py; do
        path_to_py="$(command -v "$py" 2>/dev/null || true)"
        [ -z "$path_to_py" ] && continue
        case "$path_to_py" in
            *WindowsApps*) continue ;;
        esac
        if "$py" -c "import sys" >/dev/null 2>&1; then
            echo "$py"
            return 0
        fi
    done
    echo ""
}

show_crypto_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  TELUA CRYPTO — Private Overlay Config Encryption (PBKDF2 + Fernet AES)\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "  Usage: \033[1;33mtelua crypto [action] [options]\033[0m  (or shortcuts: \033[1;32mtel enc\033[0m / \033[1;32mtel dec\033[0m)"
    echo ""
    echo -e "\033[1;33mAVAILABLE ACTIONS:\033[0m"
    printf "  \033[1;36m%-26s\033[0m %s\n" "status, check" "Check existence & sync state of private configs in config/overlay/"
    printf "  \033[1;36m%-26s\033[0m %s\n" "encrypt, enc [pw]" "Encrypt existing apk_overlays.config & const_my_cli.config -> enc_*"
    printf "  \033[1;36m%-26s\033[0m %s\n" "decrypt, dec [pw]" "Decrypt existing enc_apk_overlays.config & enc_const_my_cli.config"
    printf "  \033[1;36m%-26s\033[0m %s\n" "help" "Show this help message"
    echo ""
    echo -e "\033[1;33mOPTIONS:\033[0m"
    printf "  \033[1;36m%-26s\033[0m %s\n" "-d, --dir <path>" "Override target overlay directory (default: config/overlay)"
    printf "  \033[1;36m%-26s\033[0m %s\n" "-i <in> -o <out>" "Encrypt/decrypt a single custom file explicitly"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

crypto_cmd_status() {
    local overlay_dir="$1"
    local priv_names=("apk_overlays.config" "const_my_cli.config")
    local name plain_path enc_path

    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  TELUA CRYPTO — PRIVATE OVERLAY CONFIG STATUS\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    printf "  \033[1;37m%-18s\033[0m %s\n" "Overlay Dir:" "$overlay_dir"
    echo ""

    for name in "${priv_names[@]}"; do
        plain_path="$overlay_dir/$name"
        enc_path="$overlay_dir/enc_$name"
        local has_plain=0 has_enc=0
        [ -f "$plain_path" ] && has_plain=1
        [ -f "$enc_path" ] && has_enc=1

        echo -e "  \033[1;33m• $name\033[0m"
        if [ "$has_plain" -eq 1 ]; then
            printf "    \033[0;90m%-16s\033[0m \033[1;32mEXISTS\033[0m (%s)\n" "Plaintext:" "$plain_path"
        else
            printf "    \033[0;90m%-16s\033[0m \033[0;90mMISSING\033[0m\n" "Plaintext:"
        fi

        if [ "$has_enc" -eq 1 ]; then
            printf "    \033[0;90m%-16s\033[0m \033[1;36mEXISTS\033[0m (%s)\n" "Encrypted:" "$enc_path"
        else
            printf "    \033[0;90m%-16s\033[0m \033[0;90mMISSING\033[0m\n" "Encrypted:"
        fi

        if [ "$has_plain" -eq 1 ] && [ "$has_enc" -eq 1 ]; then
            if [ "$plain_path" -nt "$enc_path" ]; then
                printf "    \033[0;90m%-16s\033[0m \033[1;33mMODIFIED (plaintext is newer — run 'tel enc' to update)\033[0m\n" "Sync State:"
            else
                printf "    \033[0;90m%-16s\033[0m \033[1;32mSYNCED (encrypted backup is up-to-date)\033[0m\n" "Sync State:"
            fi
        elif [ "$has_plain" -eq 1 ] && [ "$has_enc" -eq 0 ]; then
            printf "    \033[0;90m%-16s\033[0m \033[1;33mUNENCRYPTED (run 'tel enc' to encrypt)\033[0m\n" "Sync State:"
        elif [ "$has_plain" -eq 0 ] && [ "$has_enc" -eq 1 ]; then
            printf "    \033[0;90m%-16s\033[0m \033[1;36mENCRYPTED ONLY (run 'tel dec' to decrypt)\033[0m\n" "Sync State:"
        else
            printf "    \033[0;90m%-16s\033[0m \033[0;90mNOT CREATED (run 'tel init' to create from *.example)\033[0m\n" "Sync State:"
        fi
        echo ""
    done
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
    return 0
}

handle_crypto_command() {
    local action="${1:-status}"
    shift 2>/dev/null || true

    local base_toolkit_dir="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}"
    local overlay_dir="$base_toolkit_dir/config/overlay"
    local crypto_script="$base_toolkit_dir/python/config_crypto.py"
    [ ! -f "$crypto_script" ] && crypto_script="$base_toolkit_dir/config_crypto.py"

    # Parse optional -d / --dir to allow overriding overlay_dir
    local -a forward_args=()
    local has_explicit_input=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--dir)
                if [ -z "${2:-}" ]; then
                    log_error "Missing directory path for $1"
                    return 1
                fi
                overlay_dir="$2"
                shift 2
                ;;
            -i|--input)
                has_explicit_input=1
                forward_args+=("$1" "$2")
                shift 2
                ;;
            *)
                forward_args+=("$1")
                shift
                ;;
        esac
    done

    case "$action" in
        status|check|"")
            crypto_cmd_status "$overlay_dir"
            return 0
            ;;
        help|-h|--help)
            show_crypto_help
            return 0
            ;;
        encrypt|enc|--encrypt|--enc)
            if [ ! -f "$crypto_script" ]; then
                log_error "Crypto helper script not found: $crypto_script"
                return 1
            fi
            if [ "$has_explicit_input" -eq 0 ]; then
                local found_plain=0
                local f
                for f in "apk_overlays.config" "const_my_cli.config"; do
                    if [ -f "$overlay_dir/$f" ]; then
                        log_info "Found private config to encrypt: $overlay_dir/$f -> $overlay_dir/enc_$f"
                        found_plain=1
                    fi
                done
                if [ "$found_plain" -eq 0 ]; then
                    log_error "No private config files (apk_overlays.config, const_my_cli.config) found in $overlay_dir"
                    log_info "Tip: Run 'tel init' or create $overlay_dir/apk_overlays.config first."
                    return 1
                fi
                forward_args+=("-d" "$overlay_dir")
            fi
            install_python_requirements
            local py_cmd
            py_cmd="$(_crypto_get_python_cmd)"
            if [ -z "$py_cmd" ]; then
                log_error "Python 3 is required to run config_crypto.py."
                return 1
            fi
            "$py_cmd" "$crypto_script" encrypt "${forward_args[@]}"
            return $?
            ;;
        decrypt|dec|--decrypt|--dec)
            if [ ! -f "$crypto_script" ]; then
                log_error "Crypto helper script not found: $crypto_script"
                return 1
            fi
            if [ "$has_explicit_input" -eq 0 ]; then
                local found_enc=0
                local f
                for f in "enc_apk_overlays.config" "enc_const_my_cli.config"; do
                    if [ -f "$overlay_dir/$f" ]; then
                        log_info "Found encrypted config to decrypt: $overlay_dir/$f -> $overlay_dir/${f#enc_}"
                        found_enc=1
                    fi
                done
                if [ "$found_enc" -eq 0 ]; then
                    log_error "No encrypted config files (enc_apk_overlays.config, enc_const_my_cli.config) found in $overlay_dir"
                    return 1
                fi
                forward_args+=("-d" "$overlay_dir" "--force")
            fi
            install_python_requirements
            local py_cmd
            py_cmd="$(_crypto_get_python_cmd)"
            if [ -z "$py_cmd" ]; then
                log_error "Python 3 is required to run config_crypto.py."
                return 1
            fi
            "$py_cmd" "$crypto_script" decrypt "${forward_args[@]}"
            return $?
            ;;
        *)
            log_error "Unknown crypto action '$action'!"
            show_crypto_help
            return 1
            ;;
    esac
}


