#!/bin/bash
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Contribution History:
#   - 2026-10: Thong Le <letrthong@gmail.com> (Architecture & Domain Design)
#   - 2026-10: Gemini 3.8 Pro - Google DeepMind (Implementation & Refactoring)
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

set -e

# --- Constants & Global Defaults ---
SCRIPT_VERSION="2.10.0"
SCRIPT_LAST_UPDATED="2026-10-15"
CONFIG_FILE_NAME="apk.config"
CAR_CONFIG_FILE_NAME="const_car.config"
DUMP_CONFIG_FILE_NAME="const_dumpsys.config"
MULTI_CONFIG_FILE_NAME="const_multi_cli.config"
MY_CONFIG_FILE_NAME="const_my_cli.config"
PROJECT_CONFIG_FILE_NAME="const_project_cli.config"
GIT_CONFIG_FILE_NAME="const_git.config"
DOCKER_CONFIG_FILE_NAME="const_docker.config"
NETWORK_CONFIG_FILE_NAME="const_network.config"
# Personal (untracked, git-ignored) files relative to the toolkit repo.
# 'telua init' creates them from '<file>.example' if missing; 'telua update' backs them up and restores them.
PERSONAL_CONFIG_FILES=("apk_overlays.config" "config/const_my_cli.config")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# Tìm apk.config: ưu tiên tại $PWD hoặc duyệt ngược lên các thư mục cha của dự án
find_config_file() {
    local check_dir="$PWD"
    while [ "$check_dir" != "/" ] && [ "$check_dir" != "." ]; do
        if [ -f "$check_dir/$CONFIG_FILE_NAME" ]; then
            echo "$check_dir/$CONFIG_FILE_NAME"
            return 0
        fi
        if [ -d "$check_dir/.repo" ]; then
            break
        fi
        check_dir="$(dirname "$check_dir")"
    done
    echo "$SCRIPT_DIR/$CONFIG_FILE_NAME"
}

CONFIG_FILE="$(find_config_file)"

# Thư mục con chứa các cấu hình constant
CONST_CONFIG_DIR_NAME="config"

# Tìm các file const_*.config: ưu tiên tại config/ của MASTER_SCRIPT_DIR, sau đó là root (tương thích ngược)
find_const_config_file() {
    local fname="$1"
    # 1. Ưu tiên trong thư mục config/ của MASTER_SCRIPT_DIR
    if [ -f "$MASTER_SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$fname" ]; then
        echo "$MASTER_SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$fname"
        return 0
    fi
    # 2. Tìm trong thư mục gốc của MASTER_SCRIPT_DIR (tương thích ngược)
    if [ -f "$MASTER_SCRIPT_DIR/$fname" ]; then
        echo "$MASTER_SCRIPT_DIR/$fname"
        return 0
    fi
    # 3. Tìm trong thư mục config/ hoặc gốc của SCRIPT_DIR
    if [ -f "$SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$fname" ]; then
        echo "$SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$fname"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$fname" ]; then
        echo "$SCRIPT_DIR/$fname"
        return 0
    fi
    # 4. Tìm trong thư mục dự án (nếu dự án tự override file const)
    local cfg_dir
    cfg_dir="$(dirname "$CONFIG_FILE" 2>/dev/null || echo "")"
    if [ -n "$cfg_dir" ]; then
        if [ -f "$cfg_dir/$CONST_CONFIG_DIR_NAME/$fname" ]; then
            echo "$cfg_dir/$CONST_CONFIG_DIR_NAME/$fname"
            return 0
        fi
        if [ -f "$cfg_dir/$fname" ]; then
            echo "$cfg_dir/$fname"
            return 0
        fi
    fi
    # Fallback mặc định
    if [ -d "$MASTER_SCRIPT_DIR/$CONST_CONFIG_DIR_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$CONST_CONFIG_DIR_NAME/$fname"
    else
        echo "$MASTER_SCRIPT_DIR/$fname"
    fi
}

CAR_CONFIG_FILE="$(find_const_config_file "$CAR_CONFIG_FILE_NAME")"
DUMP_CONFIG_FILE="$(find_const_config_file "$DUMP_CONFIG_FILE_NAME")"
GIT_CONFIG_FILE="$(find_const_config_file "$GIT_CONFIG_FILE_NAME")"
DOCKER_CONFIG_FILE="$(find_const_config_file "$DOCKER_CONFIG_FILE_NAME")"
NETWORK_CONFIG_FILE="$(find_const_config_file "$NETWORK_CONFIG_FILE_NAME")"
MULTI_CONFIG_FILE="$(find_const_config_file "$MULTI_CONFIG_FILE_NAME")"
MY_CONFIG_FILE="$(find_const_config_file "$MY_CONFIG_FILE_NAME")"
[ ! -f "$MY_CONFIG_FILE" ] && MY_CONFIG_FILE="$(find_const_config_file "$PROJECT_CONFIG_FILE_NAME")"
PROJECT_CONFIG_FILE="$MY_CONFIG_FILE"

# --- Logging helpers (single source of truth: src/telua_log.sh) ---
# Shared color logging helpers (log_info/log_success/log_warn/log_error) were
# extracted to src/telua_log.sh; sourcing it sets TELUA_LOG_SOURCED=1 and its
# internal guard makes double-sourcing (e.g. via src/telua_git.sh) a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_LOG_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_log.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_log.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_log.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_log.sh"
    fi
fi

# --- Init & Update utilities (single source of truth: src/telua_untils.sh) ---
# Code behind 'telua init' (init_project_config, apply_config_overlay,
# install_python_requirements, ensure_script_permissions, ensure_personal_configs)
# and 'telua update' (run_git_update, git_pull_with_recovery,
# backup_personal_configs, restore_personal_configs) was extracted to
# src/telua_untils.sh; sourcing it sets TELUA_UNTILS_SOURCED=1 and its internal
# guard makes double-sourcing a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_UNTILS_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_untils.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_untils.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_untils.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_untils.sh"
    fi
fi

# --- Git utilities (single source of truth: src/telua_git.sh) ---
# Code behind 'telua --git-diff' (run_git_diff), 'telua --git-amend'
# (run_git_amend) and 'telua --git-help' (show_git_help) was extracted to
# src/telua_git.sh; sourcing it sets TELUA_GIT_SOURCED=1 and its internal
# guard makes double-sourcing a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_GIT_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_git.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_git.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_git.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_git.sh"
    fi
fi

# --- Car control commands (single source of truth: src/telua_car.sh) ---
# Code behind 'telua car <action>' (show_car_short_help, show_car_help,
# is_car_action, handle_car_command) was extracted to src/telua_car.sh; it is
# driven by const_car.config (CAR_CLI_LIST, ADB_SHELL_CAR_*). Sourcing it sets
# TELUA_CAR_SOURCED=1 and its internal guard makes double-sourcing a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_CAR_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_car.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_car.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_car.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_car.sh"
    fi
fi

# --- Multi-CLI pipelines (single source of truth: src/telua_run.sh) ---
# Code behind 'telua run <group>' (show_run_short_help, show_run_help,
# is_run_group, handle_run_command) was extracted to src/telua_run.sh; it is
# driven by const_multi_cli.config (MULTI_GROUP_LIST, MULTI_CMD_*). Sourcing it
# sets TELUA_RUN_SOURCED=1 and its internal guard makes double-sourcing a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_RUN_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_run.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_run.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_run.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_run.sh"
    fi
fi

# --- Dumpsys diagnostics (single source of truth: src/telua_dump.sh) ---
# Code behind 'telua dump <target>' (show_dump_short_help, show_dump_help,
# is_dump_action, handle_dump_command) was extracted to src/telua_dump.sh; it is
# driven by const_dumpsys.config (DUMP_CLI_LIST, ADB_SHELL_DUMP_*). Sourcing it
# sets TELUA_DUMP_SOURCED=1 and its internal guard makes double-sourcing a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_DUMP_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_dump.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_dump.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_dump.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_dump.sh"
    fi
fi

# --- Android/QNX build & deploy pipeline (single source of truth: src/telua_android.sh) ---
# Code behind the build/deploy/device/log flow (resolve_android_paths,
# setup_build_environment*, build_apk, wait_for_device*, restart_framework,
# ensure_adb_remount, acquire_root, deploy_android, deploy_apk, capture_logs*)
# was extracted to src/telua_android.sh; sourcing it sets TELUA_ANDROID_SOURCED=1
# and its internal guard makes double-sourcing a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_ANDROID_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_android.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_android.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_android.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_android.sh"
    fi
fi

# --- QNX platform support (single source of truth: src/telua_qnx.sh) ---
# QNX-specific placeholders (setup_build_environment_qnx, deploy_qnx,
# capture_logs_qnx) live in src/telua_qnx.sh so future QNX SDP / qvm / slog2
# implementation only touches that module. Sourcing it sets TELUA_QNX_SOURCED=1
# and its internal guard makes double-sourcing a no-op.
# Lookup order: script dir -> master dir (both resolved through symlinks).
if [ "${TELUA_QNX_SOURCED:-}" != "1" ]; then
    if [ -f "$SCRIPT_DIR/src/telua_qnx.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/src/telua_qnx.sh"
    elif [ -f "$MASTER_SCRIPT_DIR/src/telua_qnx.sh" ]; then
        # shellcheck disable=SC1091
        source "$MASTER_SCRIPT_DIR/src/telua_qnx.sh"
    fi
fi

# --- RAM Monitoring (snapshot at start/end + peak usage sampler) ---
ENABLE_RAM_MONITOR="${ENABLE_RAM_MONITOR:-true}"
RAM_SAMPLE_INTERVAL="${RAM_SAMPLE_INTERVAL:-2}"
RAM_SAMPLER_PID=""
RAM_PEAK_FILE=""

# Summarize system memory from /proc/meminfo (values in kB -> GB)
get_mem_summary() {
    awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} /^SwapTotal:/ {st=$2} /^SwapFree:/ {sf=$2} END {
        printf "Total: %.2f GB | Used: %.2f GB | Avail: %.2f GB | Swap Used: %.2f GB",
               t/1048576, (t-a)/1048576, a/1048576, (st-sf)/1048576
    }' /proc/meminfo 2>/dev/null
}

# Current used RAM in MB (MemTotal - MemAvailable, the modern 'used' metric)
get_mem_used_mb() {
    awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} END {printf "%d", (t-a)/1024}' /proc/meminfo 2>/dev/null || echo 0
}

log_ram_snapshot() {
    log_info "RAM [$1]: $(get_mem_summary)"
}

# Background sampler: records peak used RAM into a temp file while the build runs
start_ram_sampler() {
    [ "$ENABLE_RAM_MONITOR" = "true" ] || return 0
    RAM_PEAK_FILE="$(mktemp "${TMPDIR:-/tmp}/telua_ram_peak.XXXXXX")"
    echo 0 > "$RAM_PEAK_FILE"
    (
        peak=0
        while :; do
            used=$(get_mem_used_mb)
            if [ "$used" -gt "$peak" ] 2>/dev/null; then
                peak="$used"
                echo "$peak" > "$RAM_PEAK_FILE"
            fi
            sleep "$RAM_SAMPLE_INTERVAL"
        done
    ) &
    RAM_SAMPLER_PID=$!
    log_info "RAM monitor: peak sampler started (every ${RAM_SAMPLE_INTERVAL}s, PID: $RAM_SAMPLER_PID)"
}

# Stop the background sampler (safe to call multiple times)
stop_ram_sampler() {
    if [ -n "$RAM_SAMPLER_PID" ]; then
        kill "$RAM_SAMPLER_PID" 2>/dev/null || true
        wait "$RAM_SAMPLER_PID" 2>/dev/null || true
        RAM_SAMPLER_PID=""
    fi
}

# Final report: END snapshot + peak usage observed during the run
report_ram_summary() {
    stop_ram_sampler
    log_ram_snapshot "END"
    local peak
    peak="$(cat "$RAM_PEAK_FILE" 2>/dev/null || echo 0)"
    if [ -n "$RAM_PEAK_FILE" ] && [ -f "$RAM_PEAK_FILE" ]; then
        rm -f "$RAM_PEAK_FILE"
        RAM_PEAK_FILE=""
    fi
    if [ "${peak:-0}" -gt 0 ] 2>/dev/null; then
        log_success "RAM peak usage during this run: $(awk -v p="$peak" 'BEGIN {printf "%.2f GB (%d MB)", p/1024, p}')"
    else
        log_warn "RAM peak usage: no samples collected (ENABLE_RAM_MONITOR=$ENABLE_RAM_MONITOR)"
    fi
}

show_version() {
    echo "build_apk.sh v$SCRIPT_VERSION (Last updated: $SCRIPT_LAST_UPDATED)"
    echo "AOSP & QNX Automotive Build, Deployment and Automation Tool"
    echo "Maintained by: letrthong@gmail.com"
    exit 0
}

print_help() {
    local real_script
    if command -v realpath >/dev/null 2>&1; then
        real_script="$(realpath "${BASH_SOURCE[0]}")"
    elif command -v readlink >/dev/null 2>&1; then
        real_script="$(readlink -f "${BASH_SOURCE[0]}")"
    else
        real_script="$(cd "$SCRIPT_DIR" && pwd)/$(basename "${BASH_SOURCE[0]}")"
    fi

    cat <<EOF
telua / build_apk.sh - AOSP & QNX Automotive Build, Deployment and Automation Tool
Version:      v$SCRIPT_VERSION (Updated: $SCRIPT_LAST_UPDATED)
Maintained by: letrthong@gmail.com
Script Path:  $real_script

Usage: telua [COMMAND] [OPTIONS]  (or: $0 [COMMAND] [OPTIONS])

Primary Subcommands:
  build, b                    Build active module, push APK to device, and reboot
  init                        Initialize $CONFIG_FILE_NAME in current directory (\$PWD)
  install                     Install 'telua' alias in ~/.bashrc & dependencies
  info                        Display general build config, paths, and connected DUT
  update                      Update toolkit: git pull origin main (with auto-recovery)
  car [action]                Control AAOS car (vol-up, vol-down, vol-mute, ks, ks-stop, car-status)
  dump [target]               Run dumpsys diagnostics (audio, car-service, car-audio, ...)
  run [group]                 Execute multi-command pipeline macro (dev-prep, audio-cycle, ...)
  my, proj [action]           Execute personal / private pipeline macro (hello, ...)
  git                         Display Git & Google Repo cheatsheet
  docker                      Display Docker daemon & container cheatsheet
  network                     Display Network & socket inspection cheatsheet

Build & Deployment Options (used with 'build' or standalone):
  --no-reboot                 Fast restart (stop && start) instead of full device reboot
  --start-deploy true|false   Override ENABLE_DEPLOY from $CONFIG_FILE_NAME
  --platform android|qnx      Target platform: 'android' (default) or 'qnx' (reserved)
  --repo-sync                 Run 'repo sync' in ROOT_DIR before building module
  --repo-reset                Hard reset all repos before sync (prompts for 'y' or use -y)
  -y, --yes                   Bypass confirmation prompts (e.g. for --repo-reset)
  --config <path>             Explicitly specify custom path to config file
  --softlink [path]           Symlink this script + copy $CONFIG_FILE_NAME into [path]
  --test-mode true|false      Run unit test suite instead of full build
  --ram-monitor true|false    Show RAM usage at start/end and track peak RAM (default: true)
  --find-file <pattern> [path] Search for files by pattern in [path] (default: '.')
  --find-dir <pattern> [path]  Search for directories by pattern in [path] (default: '.')
  --find-text <text> [path]    Search for text in files under [path] (default: '.')
  -h, --help, help            Display this help message and exit

Configuration Info:
  Active Config:              $CONFIG_FILE
  Car Config (Global):        $CAR_CONFIG_FILE
  Dump Config (Global):       $DUMP_CONFIG_FILE
  Multi-CLI Pipelines (Global):$MULTI_CONFIG_FILE
  Personal Pipelines (Private):$MY_CONFIG_FILE
  Git Cheatsheet (Global):    $GIT_CONFIG_FILE
  Docker Cheatsheet (Global): $DOCKER_CONFIG_FILE
  Network Cheatsheet (Global):$NETWORK_CONFIG_FILE
  Master Template:            $SCRIPT_DIR/$CONFIG_FILE_NAME
  Encrypted Template:         $SCRIPT_DIR/enc_apk.config
EOF
}

parse_early_arguments() {
    local prev=""
    for arg in "$@"; do
        if [ "$prev" = "--config" ]; then
            if [ -f "$arg" ]; then
                CONFIG_FILE="$(readlink -f "$arg" 2>/dev/null || echo "$arg")"
            else
                log_error "Config file specified via --config not found: $arg"
                exit 1
            fi
        fi
        prev="$arg"
    done
}

# --- 1. Parse Command Line Arguments ---
parse_arguments() {
    # If invoked with no arguments at all, display help by default (Zero Cognitive Load & Safe)
    if [ $# -eq 0 ]; then
        print_help
        exit 0
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            build|--build|b)
                # Primary build subcommand: consume it and parse subsequent options
                shift
                ;;
            --config)
                # Handled early in parse_early_arguments
                shift 2
                ;;
            --init|--init-config|init)
                init_project_config
                exit 0
                ;;
            --install|install)
                install_bashrc_alias
                exit 0
                ;;
            -v|--version|version)
                show_version
                ;;
            --info|info)
                SHOW_INFO="true"
                shift
                ;;
            --platform)
                if [[ "$2" != "android" && "$2" != "qnx" ]]; then
                    log_error "--platform requires 'android' or 'qnx', got '$2'"
                    exit 1
                fi
                CLI_PLATFORM="$2"
                shift 2
                ;;
            --start-deploy)
                if [[ "$2" != "true" && "$2" != "false" ]]; then
                    log_error "--start-deploy requires 'true' or 'false', got '$2'"
                    exit 1
                fi
                CLI_START_DEPLOY="$2"
                ENABLE_DEPLOY="$2"
                shift 2
                ;;
            --no-reboot)
                NO_REBOOT="true"
                shift
                ;;
            --softlink)
                if [ -n "$2" ] && [[ "$2" != --* ]]; then
                    SOFTLINK_PATH="$2"
                    shift 2
                else
                    SOFTLINK_PATH="${SOFTLINK_TARGET_PATH:-$DEFAULT_SOFTLINK_PATH}"
                    if [ -z "$SOFTLINK_PATH" ]; then
                        log_error "No target directory path provided for --softlink!"
                        log_error "Usage: $0 --softlink <project_path>"
                        log_error "Or configure 'SOFTLINK_TARGET_PATH' in $CONFIG_FILE_NAME"
                        exit 1
                    fi
                    shift 1
                fi
                ;;
            --repo-sync)
                REPO_SYNC="true"
                shift
                ;;
            --repo-reset)
                REPO_RESET="true"
                shift
                ;;
            -y|--yes|--force|-f)
                CONFIRM_YES="true"
                shift
                ;;
            --git-diff)
                GIT_DIFF="true"
                shift
                ;;
            --git-amend)
                GIT_AMEND="true"
                shift
                ;;
            --update|update|--git-update)
                run_git_update
                exit 0
                ;;
            --git-help|git-help|git|--git)
                SHOW_GIT_HELP="true"
                shift
                ;;
            --docker-help|docker-help|docker|--docker)
                SHOW_DOCKER_HELP="true"
                shift
                ;;
            --network-help|network-help|network|--network)
                SHOW_NETWORK_HELP="true"
                shift
                ;;
            --find-file|find_file)
                if [ -z "$2" ] || [[ "$2" == --* ]]; then
                    log_error "Missing pattern for --find-file! Usage: $0 --find-file <file_pattern> [search_path]"
                    exit 1
                fi
                ACTION_CMD="find_file"
                SEARCH_PATTERN="$2"
                shift 2
                if [ -n "$1" ] && [[ "$1" != --* ]]; then
                    SEARCH_TARGET_PATH="$1"
                    shift 1
                fi
                ;;
            --find-dir|find_dir)
                if [ -z "$2" ] || [[ "$2" == --* ]]; then
                    log_error "Missing pattern for --find-dir! Usage: $0 --find-dir <dir_pattern> [search_path]"
                    exit 1
                fi
                ACTION_CMD="find_dir"
                SEARCH_PATTERN="$2"
                shift 2
                if [ -n "$1" ] && [[ "$1" != --* ]]; then
                    SEARCH_TARGET_PATH="$1"
                    shift 1
                fi
                ;;
            --find-text|find_text)
                if [ -z "$2" ] || [[ "$2" == --* ]]; then
                    log_error "Missing text for --find-text! Usage: $0 --find-text <text_pattern> [search_path]"
                    exit 1
                fi
                ACTION_CMD="find_text"
                SEARCH_PATTERN="$2"
                shift 2
                if [ -n "$1" ] && [[ "$1" != --* ]]; then
                    SEARCH_TARGET_PATH="$1"
                    shift 1
                fi
                ;;
            --test-mode)
                if [[ "$2" != "true" && "$2" != "false" ]]; then
                    log_error "--test-mode requires 'true' or 'false', got '$2'"
                    exit 1
                fi
                TEST_MODE="$2"
                shift 2
                ;;
            --ram-monitor)
                if [[ "$2" != "true" && "$2" != "false" ]]; then
                    log_error "--ram-monitor requires 'true' or 'false', got '$2'"
                    exit 1
                fi
                ENABLE_RAM_MONITOR="$2"
                shift 2
                ;;
            --car|car)
                if [ -n "$2" ] && [[ "$2" != --* ]]; then
                    CAR_ACTION="$2"
                    shift 2
                else
                    CAR_ACTION=""
                    shift 1
                fi
                handle_car_command "$CAR_ACTION"
                exit 0
                ;;
            --dump|dump)
                if [ -n "$2" ] && [[ "$2" != --* ]]; then
                    DUMP_ACTION="$2"
                    shift 2
                else
                    DUMP_ACTION=""
                    shift 1
                fi
                handle_dump_command "$DUMP_ACTION"
                exit 0
                ;;
            --run|run|--multi|multi)
                if [ -n "$2" ] && [[ "$2" != --* ]]; then
                    RUN_GROUP="$2"
                    shift 2
                else
                    RUN_GROUP=""
                    shift 1
                fi
                handle_run_command "$RUN_GROUP"
                exit 0
                ;;
            --my|my|--proj|proj|--project|project)
                if [ -n "$2" ] && [[ "$2" != --* ]]; then
                    PROJ_ACTION="$2"
                    shift 2
                else
                    PROJ_ACTION=""
                    shift 1
                fi
                handle_project_command "$PROJ_ACTION"
                exit 0
                ;;
            vol-up|--vol-up)
                handle_car_command "vol-up"
                exit 0
                ;;
            vol-down|--vol-down)
                handle_car_command "vol-down"
                exit 0
                ;;
            vol-mute|--vol-mute)
                handle_car_command "vol-mute"
                exit 0
                ;;
            -h|--help|help)
                print_help
                exit 0
                ;;
            *)
                local stripped_arg="${1#--}"
                stripped_arg=$(echo "$stripped_arg" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
                if is_car_action "$stripped_arg"; then
                    handle_car_command "$stripped_arg"
                    exit 0
                fi
                if is_dump_action "$stripped_arg"; then
                    handle_dump_command "$stripped_arg"
                    exit 0
                fi
                if is_project_action "$stripped_arg"; then
                    handle_project_command "$stripped_arg"
                    exit 0
                fi
                log_error "Unknown argument '$1'"
                print_help
                exit 1
                ;;
        esac
    done
}

# --- 1g. Personal & Project Command Pipelines (--my / my / --proj / proj) ---
# (show_dump_short_help, show_dump_help, is_dump_action, handle_dump_command
# live in src/telua_dump.sh; show_run_* / is_run_group / handle_run_command
# live in src/telua_run.sh)
# Short one-line-per-action listing (shown by: telua my)
show_project_short_help() {
    echo ""
    echo -e "\033[1;32m  telua my <action> - Personal & Private Pipelines (or: telua proj)\033[0m"
    echo -e "  Active Project:    \033[1;37m${ACTIVE_PROJECT:-default}\033[0m"
    echo -e "  Personal Config:   \033[0;33m$MY_CONFIG_FILE\033[0m"
    echo ""
    local -a grp_list=()
    if [ -n "${MY_GROUP_LIST[*]}" ] && [ "${#MY_GROUP_LIST[@]}" -gt 0 ]; then
        grp_list=("${MY_GROUP_LIST[@]}")
    elif [ -n "${PROJECT_GROUP_LIST[*]}" ] && [ "${#PROJECT_GROUP_LIST[@]}" -gt 0 ]; then
        grp_list=("${PROJECT_GROUP_LIST[@]}")
    fi

    if [ "${#grp_list[@]}" -gt 0 ]; then
        for item in "${grp_list[@]}"; do
            local grp_name="" grp_desc=""
            if [[ "$item" == *" :: "* ]]; then
                grp_name="${item%% :: *}"
                grp_desc="${item#* :: }"
            else
                grp_name="$item"
                grp_desc="Personal action"
            fi
            grp_name="$(echo "$grp_name" | xargs)"
            grp_desc="$(echo "$grp_desc" | xargs)"
            printf "  \033[1;37m%-30s\033[0m %s\n" "telua my $grp_name" "$grp_desc"
        done
    else
        echo -e "  \033[0;90m(No MY_GROUP_LIST declared in $MY_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi
    echo ""
    echo -e "  \033[0;90mTip: 'telua my help' (or --help / -h) shows detailed steps for each action.\033[0m"
    echo ""
}

# Detailed listing with every step of every action (shown by: telua my help)
show_project_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  telua my - Personal & Private Pipelines (or: telua proj)\033[0m"
    echo -e "  Active Project:    \033[1;37m${ACTIVE_PROJECT:-default}\033[0m"
    echo -e "  Config File:       \033[0;33m$CONFIG_FILE\033[0m"
    echo -e "  Personal Config:   \033[0;33m$MY_CONFIG_FILE\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
    echo -e "\033[1;33mAVAILABLE PERSONAL ACTIONS:\033[0m"

    local -a grp_list=()
    if [ -n "${MY_GROUP_LIST[*]}" ] && [ "${#MY_GROUP_LIST[@]}" -gt 0 ]; then
        grp_list=("${MY_GROUP_LIST[@]}")
    elif [ -n "${PROJECT_GROUP_LIST[*]}" ] && [ "${#PROJECT_GROUP_LIST[@]}" -gt 0 ]; then
        grp_list=("${PROJECT_GROUP_LIST[@]}")
    fi

    if [ "${#grp_list[@]}" -gt 0 ]; then
        local idx=1
        for item in "${grp_list[@]}"; do
            local grp_name="" grp_desc=""
            if [[ "$item" == *" :: "* ]]; then
                grp_name="${item%% :: *}"
                grp_desc="${item#* :: }"
            else
                grp_name="$item"
                grp_desc="Personal action"
            fi
            grp_name="$(echo "$grp_name" | xargs)"
            grp_desc="$(echo "$grp_desc" | xargs)"

            local var_suffix
            var_suffix=$(echo "$grp_name" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
            local -a steps=()
            if declare -p "MY_CMD_${var_suffix}" >/dev/null 2>&1; then
                eval "steps=(\"\${MY_CMD_${var_suffix}[@]}\")"
            elif declare -p "PROJECT_CMD_${var_suffix}" >/dev/null 2>&1; then
                eval "steps=(\"\${PROJECT_CMD_${var_suffix}[@]}\")"
            fi

            echo -e "  \033[1;32m$idx.\033[0m \033[1;37mtelua my $grp_name\033[0m"
            echo -e "     \033[0;90mDescription:\033[0m  $grp_desc"
            if [ "${#steps[@]}" -gt 0 ]; then
                echo -e "     \033[0;90mSteps:\033[0m        \033[0;36m(${#steps[@]} commands sequential)\033[0m"
                local step_i=1
                for step_cmd in "${steps[@]}"; do
                    echo -e "       \033[1;33m[$step_i/${#steps[@]}]\033[0m \033[0;37m$step_cmd\033[0m"
                    step_i=$((step_i + 1))
                done
            else
                echo -e "     \033[0;90mSteps:\033[0m        \033[0;31m(No steps declared in MY_CMD_${var_suffix})\033[0m"
            fi
            echo ""
            idx=$((idx + 1))
        done
    else
        echo -e "  \033[0;90m(No MY_GROUP_LIST declared in $MY_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi

    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

is_project_action() {
    local target="$1"
    target=$(echo "$target" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    local -a grp_list=()
    if [ -n "${MY_GROUP_LIST[*]}" ]; then
        grp_list=("${MY_GROUP_LIST[@]}")
    elif [ -n "${PROJECT_GROUP_LIST[*]}" ]; then
        grp_list=("${PROJECT_GROUP_LIST[@]}")
    fi

    if [ "${#grp_list[@]}" -gt 0 ]; then
        for item in "${grp_list[@]}"; do
            local grp=""
            if [[ "$item" == *" :: "* ]]; then
                grp="${item%% :: *}"
            else
                grp="$item"
            fi
            grp="$(echo "$grp" | xargs | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
            if [ "$grp" = "$target" ]; then
                return 0
            fi
        done
    fi

    local suf
    suf=$(echo "$target" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    if declare -p "MY_CMD_${suf}" >/dev/null 2>&1 || declare -p "PROJECT_CMD_${suf}" >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

handle_project_command() {
    local action="$1"

    if [ -z "$action" ]; then
        show_project_short_help
        return 0
    fi

    if [ "$action" = "help" ] || [ "$action" = "--help" ] || [ "$action" = "-h" ]; then
        show_project_help
        return 0
    fi

    local action_normalized
    action_normalized=$(echo "$action" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    local -a grp_list=()
    if [ -n "${MY_GROUP_LIST[*]}" ]; then
        grp_list=("${MY_GROUP_LIST[@]}")
    elif [ -n "${PROJECT_GROUP_LIST[*]}" ]; then
        grp_list=("${PROJECT_GROUP_LIST[@]}")
    fi

    local action_label=""
    if [ "${#grp_list[@]}" -gt 0 ]; then
        for item in "${grp_list[@]}"; do
            local g_name="" g_desc=""
            if [[ "$item" == *" :: "* ]]; then
                g_name="${item%% :: *}"
                g_desc="${item#* :: }"
            else
                g_name="$item"
                g_desc="$item"
            fi
            g_name="$(echo "$g_name" | xargs | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
            if [ "$g_name" = "$action_normalized" ]; then
                action_label="$(echo "$g_desc" | xargs)"
                break
            fi
        done
    fi

    local var_suffix
    var_suffix=$(echo "$action_normalized" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    local -a step_cmds=()
    if declare -p "MY_CMD_${var_suffix}" >/dev/null 2>&1; then
        eval "step_cmds=(\"\${MY_CMD_${var_suffix}[@]}\")"
    elif declare -p "PROJECT_CMD_${var_suffix}" >/dev/null 2>&1; then
        eval "step_cmds=(\"\${PROJECT_CMD_${var_suffix}[@]}\")"
    fi

    if [ "${#step_cmds[@]}" -eq 0 ]; then
        log_error "Personal action '$action' not found or has no steps defined!"
        log_error "Expected array 'MY_CMD_${var_suffix}' in $MY_CONFIG_FILE_NAME or $CONFIG_FILE_NAME"
        show_project_help
        exit 1
    fi

    local total_steps="${#step_cmds[@]}"
    echo ""
    log_info "============================================================"
    log_info " Executing Personal Pipeline: '$action_normalized'"
    [ -n "$action_label" ] && log_info " Description: $action_label"
    log_info " Total Steps: $total_steps"
    log_info "============================================================"

    local step_idx=1
    for cmd in "${step_cmds[@]}"; do
        echo ""
        echo -e "\033[1;36m[STEP $step_idx/$total_steps]\033[0m \033[1;37m$cmd\033[0m"
        local step_start
        step_start=$(date +%s)

        if eval "$cmd"; then
            local step_end
            step_end=$(date +%s)
            local step_dur=$((step_end - step_start))
            log_success "Step $step_idx/$total_steps finished (${step_dur}s)."
        else
            local exit_code=$?
            log_error "Step $step_idx failed with exit code $exit_code! Aborting pipeline."
            exit $exit_code
        fi
        step_idx=$((step_idx + 1))
    done

    echo ""
    log_success "All $total_steps steps of personal action '$action_normalized' completed successfully."
    echo ""
}

# --- 1a. Install Alias into ~/.bashrc (--install) ---
# (install_python_requirements used here lives in src/telua_untils.sh)
install_bashrc_alias() {
    # Check and install python dependencies if missing
    install_python_requirements

    local real_script
    if command -v realpath >/dev/null 2>&1; then
        real_script="$(realpath "${BASH_SOURCE[0]}")"
    elif command -v readlink >/dev/null 2>&1; then
        real_script="$(readlink -f "${BASH_SOURCE[0]}")"
    else
        real_script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
    fi

    local bashrc_file="${HOME}/.bashrc"
    if [ ! -f "$bashrc_file" ]; then
        log_info "$bashrc_file not found, creating new file..."
        touch "$bashrc_file"
    fi

    local alias_entry="alias telua='$real_script'"

    if grep -E -q '^[[:space:]]*alias[[:space:]]+telua=' "$bashrc_file"; then
        # Update existing alias in ~/.bashrc
        if sed --version 2>/dev/null | grep -q GNU; then
            sed -i "s#^[[:space:]]*alias[[:space:]]\+telua=.*#$alias_entry#g" "$bashrc_file"
        else
            sed -i '' "s#^[[:space:]]*alias[[:space:]]\{1,\}telua=.*#$alias_entry#g" "$bashrc_file" 2>/dev/null || sed -i "s#^[[:space:]]*alias[[:space:]]\+telua=.*#$alias_entry#g" "$bashrc_file"
        fi
        log_success "Updated existing alias in $bashrc_file:"
        echo -e "  \033[1;36m$alias_entry\033[0m"
    else
        # Append alias to ~/.bashrc
        echo "" >> "$bashrc_file"
        echo "# Telua build automation alias" >> "$bashrc_file"
        echo "$alias_entry" >> "$bashrc_file"
        log_success "Added alias to $bashrc_file:"
        echo -e "  \033[1;36m$alias_entry\033[0m"
    fi

    # Source ~/.bashrc for the current shell environment
    if [ -f "$bashrc_file" ]; then
        # shellcheck disable=SC1090
        source "$bashrc_file" 2>/dev/null || true
    fi

    log_info "Configuration reloaded. To use the 'telua' alias in your current terminal session immediately, run:"
    log_info "  source ~/.bashrc"
}

# --- 1c. Install into a project directory (--softlink <path>) ---
# (apply_config_overlay and init_project_config live in src/telua_untils.sh)
# Symlinks this script (fixes to the original reach every project) and copies
# apk.config (each project keeps its own settings). Existing files are overwritten.
# NOTE: the script finds apk.config and the 'android' root relative to the
# link's location, so <path> must be inside the target AOSP tree.
install_to_project() {
    local target_dir="$1"
    local real_script real_target

    if [ ! -d "$target_dir" ]; then
        local parent_dir
        parent_dir="$(dirname "$target_dir")"
        if [ -d "$parent_dir" ]; then
            log_info "Target directory '$target_dir' does not exist, but parent directory exists."
            log_info "Automatically creating target directory: mkdir -p '$target_dir'"
            if ! mkdir -p "$target_dir"; then
                log_error "Failed to create target directory: $target_dir"
                exit 1
            fi
        else
            log_error "Target directory '$target_dir' does not exist (parent directory '$parent_dir' also does not exist)!"
            log_error "Please check the path for typos or create it manually: mkdir -p '$target_dir'"
            exit 1
        fi
    fi

    # Resolve the ORIGINAL script, even if this run was started via a symlink.
    real_script="$(readlink -f "${BASH_SOURCE[0]}")"
    real_target="$(cd "$target_dir" && pwd -P)"

    if [ "$real_target" = "$(dirname "$real_script")" ] \
        || [ "$real_target" = "$(cd "$SCRIPT_DIR" && pwd -P)" ]; then
        log_error "Target is the script's own directory: $real_target"
        exit 1
    fi

    case "$real_target/" in
        */android/*) ;;
        *) log_warn "'$real_target' is not under an 'android' directory; the build will not find the AOSP tree from there." ;;
    esac

    ln -sfn "$real_script" "$real_target/build_apk.sh"
    # rm first: if the old config is a symlink, 'cp' would write through it.
    rm -f "$real_target/$CONFIG_FILE_NAME"
    cp "$SCRIPT_DIR/$CONFIG_FILE_NAME" "$real_target/$CONFIG_FILE_NAME"

    log_success "Linked:  $real_target/build_apk.sh -> $real_script"
    log_success "Copied:  $SCRIPT_DIR/$CONFIG_FILE_NAME -> $real_target/$CONFIG_FILE_NAME"
    log_info "Next: edit $real_target/$CONFIG_FILE_NAME, then run: cd \"$real_target\" && ./build_apk.sh --info"
}

# --- Resolve build jobs: BUILD_JOBS from config, or auto-detect based on available RAM ---
# Sets BUILD_JOBS_RESOLVED (number) and BUILD_JOBS_SOURCE ("config" | "auto")
# Auto mode scales parallel jobs by FREE RAM (MemAvailable) to avoid OOM during builds:
#   avail > 80 GB -> nproc/2   (plenty of RAM, go fast)
#   avail > 40 GB -> nproc/4   (moderate, be careful)
#   avail <= 40 GB -> nproc/8  (low RAM, be conservative)
resolve_build_jobs() {
    local nproc_count avail_gb
    nproc_count=$(nproc 2>/dev/null || echo 8)
    if [ -n "$BUILD_JOBS" ]; then
        BUILD_JOBS_RESOLVED="$BUILD_JOBS"
        BUILD_JOBS_SOURCE="config"
        return 0
    fi

    avail_gb=$(awk '/^MemAvailable:/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0)
    if [ "$avail_gb" -gt 80 ] 2>/dev/null; then
        BUILD_JOBS_RESOLVED=$((nproc_count / 2))
        BUILD_JOBS_SOURCE="auto (RAM ${avail_gb}GB>80 -> nproc/2)"
    elif [ "$avail_gb" -gt 40 ] 2>/dev/null; then
        BUILD_JOBS_RESOLVED=$((nproc_count / 4))
        BUILD_JOBS_SOURCE="auto (RAM ${avail_gb}GB 40-80 -> nproc/4)"
    else
        BUILD_JOBS_RESOLVED=$((nproc_count / 8))
        BUILD_JOBS_SOURCE="auto (RAM ${avail_gb}GB<=40 -> nproc/8)"
    fi
    # NOTE: use 'if' (not '[ ] &&') so the function always returns 0 under 'set -e'
    if [ "$BUILD_JOBS_RESOLVED" -lt 1 ]; then
        BUILD_JOBS_RESOLVED=1
    fi
    return 0
}

# --- 1b. Diagnostic Info (--info) ---
show_info_general() {
    local module_name="${MODULE_NAME:-${APK_FILE_NAME%.apk}}"
    resolve_build_jobs
    local target_platform="${PLATFORM:-${TARGET_PLATFORM:-android}}"

    echo -e "\n\033[1;36m=== 1. GENERAL BUILD CONFIGURATION ===\033[0m"
    echo "  Script Version:   v$SCRIPT_VERSION (Updated: $SCRIPT_LAST_UPDATED)"
    echo "  Config File:      $CONFIG_FILE"
    echo "  Car Config:       $CAR_CONFIG_FILE"
    echo "  Project:          ${ACTIVE_PROJECT:-default}"
    echo "  Target Platform:  $target_platform"
    echo "  Target Lunch:     ${CONFIG_TARGET_PRODUCT}-${CONFIG_TARGET_BUILD_VARIANT}"
    echo "  Module Build Jobs:-j$BUILD_JOBS_RESOLVED (m $module_name) [${BUILD_JOBS_SOURCE}]"
    echo "  RAM Monitor:      ${ENABLE_RAM_MONITOR:-true} (sample interval: ${RAM_SAMPLE_INTERVAL:-2}s)"
    echo "  Module Name:      $module_name"
    echo "  Source Path:      $SOURCE_CODE_RELATIVE_PATH"
    echo "  APK Output:       $APK_OUTPUT_RELATIVE_PATH/$APK_FILE_NAME"
    echo "  Root Dir:         ${ROOT_DIR:-Not found}"
    echo "  AOSP Top Rel:     ${AOSP_TOP_REL_PATH:-Auto-detect (android/qssi or android)}"
    echo "  AOSP Top:         ${ANDROID_TOP:-Not found (no 'android' dir above $SCRIPT_DIR)}"
    echo "  Repo Sync Jobs:   ${REPO_SYNC_JOBS:-4}"
    echo "  Repo Post Root:   ${REPO_POST_SYNC_ROOT_COMMAND:-${POST_SYNC_ROOT_COMMAND:-None}}"
    echo "  Repo Post Top:    ${REPO_POST_SYNC_BUILD_COMMAND:-${POST_SYNC_BUILD_COMMAND:-None}}"
    if [ -n "$SOFTLINK_TARGET_PATH" ]; then
        if [ -d "$SOFTLINK_TARGET_PATH" ]; then
            echo "  Softlink Target:  $SOFTLINK_TARGET_PATH [EXISTS]"
        else
            echo "  Softlink Target:  $SOFTLINK_TARGET_PATH [NOT FOUND - will auto-create if parent exists]"
        fi
    else
        echo "  Softlink Target:  Not configured (provide path via CLI)"
    fi
}

show_info_android() {
    local deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_ANDROID_DEPLOY:-${ENABLE_DEPLOY:-true}}}"
    local logcat_enabled="${ENABLE_ANDROID_LOGCAT:-${ENABLE_LOGCAT:-false}}"

    echo -e "\n\033[1;32m=== 2. ANDROID TARGET INFO (ADB) ===\033[0m"
    echo "  Platform:         android"
    echo "  Deploy Enabled:   $deploy_enabled"
    echo "  Deploy Path:      $APK_DEPLOY_PATH"
    echo "  Logcat Enabled:   $logcat_enabled"
    echo "  Logcat Filter:    ${LOGCAT_FILTER:-None (full)}"
    echo "  Debug Tags:       ${DEBUG_LOG_TAGS:-None} (Enabled: ${ENABLE_DEBUG_LOG:-false})"
    echo "  Car Controls (ADB Shell):"
    echo "    Vol Up:         ${ADB_SHELL_CAR_UP:-cmd media_session volume --show --adj raise}"
    echo "    Vol Down:       ${ADB_SHELL_CAR_DOWN:-cmd media_session volume --show --adj lower}"
    echo "    Vol Mute:       ${ADB_SHELL_CAR_MUTE:-cmd media_session volume --show --adj mute}"
    echo "    Audio Dump:     ${ADB_SHELL_CAR_DUMP:-${ADB_SHELL_CAR_D:-dumpsys audio}}"
    if command -v adb >/dev/null 2>&1; then
        local dev_state build_type internal_id vendor_build_type
        dev_state=$(adb get-state 2>/dev/null || echo "offline")
        build_type=$(adb shell getprop ro.build.type 2>/dev/null | tr -d '\r')
        internal_id=$(adb shell getprop ro.build.internal.id 2>/dev/null | tr -d '\r')
        vendor_build_type=$(adb shell getprop ro.vendor.build.type 2>/dev/null | tr -d '\r')
        echo "  ADB Device State: $dev_state (Build: ${build_type:-unknown})"
        echo "  Internal ID:      ${internal_id:-unknown}"
        echo "  Vendor Build:     ${vendor_build_type:-unknown}"
    else
        echo "  ADB Binary:       Not installed / not in PATH"
    fi
}

show_info_qnx() {
    local deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_QNX_DEPLOY:-${ENABLE_DEPLOY:-false}}}"
    local log_enabled="${ENABLE_QNX_LOG:-${ENABLE_LOGCAT:-false}}"

    echo -e "\n\033[1;33m=== 2. QNX TARGET INFO (Hypervisor / Guest VM) ===\033[0m"
    echo "  Platform:         qnx"
    echo "  Deploy Enabled:   $deploy_enabled"
    echo "  Deploy Path:      ${QNX_TARGET_DIR:-${QNX_DEPLOY_PATH:-${APK_DEPLOY_PATH:-N/A}}}"
    echo "  Target Host/IP:   ${QNX_HOST_IP:-${QNX_HOST:-Not configured (e.g. 192.168.1.100)}}"
    echo "  SSH/SCP Port:     ${QNX_SSH_PORT:-22}"
    echo "  Log Capture:      $log_enabled (slog2info)"
    echo "  Status:           Placeholder - QNX deployment & diagnostics will be supplemented here"
    echo "  Note:             Android ADB properties are skipped on QNX platform."
}

# --- 1c. System RAM Info (--info) ---
show_info_ram() {
    echo -e "\n\033[1;35m=== 3. SYSTEM RAM INFO ===\033[0m"
    if [ ! -r /proc/meminfo ]; then
        echo "  RAM Info:         Not available (/proc/meminfo not readable)"
        return 0
    fi

    local total_kb avail_kb free_kb swap_total_kb swap_free_kb buffers_kb cached_kb
    total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
    avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    free_kb=$(awk '/^MemFree:/ {print $2}' /proc/meminfo)
    buffers_kb=$(awk '/^Buffers:/ {print $2}' /proc/meminfo)
    cached_kb=$(awk '/^Cached:/ {print $2}' /proc/meminfo)
    swap_total_kb=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
    swap_free_kb=$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)

    local used_kb=$((total_kb - avail_kb))
    local used_pct=0
    [ "$total_kb" -gt 0 ] 2>/dev/null && used_pct=$((used_kb * 100 / total_kb))

    echo "  RAM Total:        $(awk -v t="$total_kb" 'BEGIN {printf "%.2f GB (%d MB)", t/1048576, t/1024}')"
    echo "  RAM Used:         $(awk -v u="$used_kb" 'BEGIN {printf "%.2f GB (%d MB)", u/1048576, u/1024}')  [${used_pct}%]"
    echo "  RAM Available:    $(awk -v a="$avail_kb" 'BEGIN {printf "%.2f GB (%d MB)", a/1048576, a/1024}')  (free: $(awk -v f="$free_kb" 'BEGIN {printf "%.2f GB", f/1048576}'))"
    echo "  Buffers/Cached:   $(awk -v b="$buffers_kb" -v c="$cached_kb" 'BEGIN {printf "%.2f GB / %.2f GB", b/1048576, c/1048576}')"
    if [ "${swap_total_kb:-0}" -gt 0 ] 2>/dev/null; then
        echo "  Swap Total:       $(awk -v s="$swap_total_kb" 'BEGIN {printf "%.2f GB", s/1048576}')"
        echo "  Swap Used:        $(awk -v st="$swap_total_kb" -v sf="$swap_free_kb" 'BEGIN {printf "%.2f GB", (st-sf)/1048576}')"
    else
        echo "  Swap:             Not enabled"
    fi
    echo "  CPU Cores:        $(nproc 2>/dev/null || echo unknown)"
    echo "  RAM Monitor:      ${ENABLE_RAM_MONITOR:-true} (peak sampler interval: ${RAM_SAMPLE_INTERVAL:-2}s)"
}

show_info() {
    resolve_android_paths >/dev/null 2>&1 || true

    local target_platform="${PLATFORM:-${TARGET_PLATFORM:-android}}"

    show_info_general

    case "$target_platform" in
        android)
            show_info_android
            ;;
        qnx)
            show_info_qnx
            ;;
        *)
            echo -e "\n\033[1;31m=== 2. PLATFORM TARGET INFO (Unknown: $target_platform) ===\033[0m"
            echo "  Unsupported platform: '$target_platform'. Supported: 'android' | 'qnx'"
            ;;
    esac

    show_info_ram

    echo -e "\033[1;36m====================================================\033[0m\n"
    exit 0
}

# --- 2. Load & Validate Configuration ---
load_and_validate_config() {
    # 1. Nạp cấu hình Car chung (nằm cùng thư mục với build_apk.sh)
    if [ -f "$CAR_CONFIG_FILE" ]; then
        source "$CAR_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$CAR_CONFIG_FILE_NAME" ]; then
        source "$MASTER_SCRIPT_DIR/$CAR_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$CAR_CONFIG_FILE_NAME" ]; then
        source "$SCRIPT_DIR/$CAR_CONFIG_FILE_NAME"
    fi

    # 1b. Nạp cấu hình Dumpsys chung (nằm cùng thư mục với build_apk.sh)
    if [ -f "$DUMP_CONFIG_FILE" ]; then
        source "$DUMP_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME" ]; then
        source "$MASTER_SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME" ]; then
        source "$SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME"
    fi

    # 1c. Nạp cấu hình Multi-CLI Pipelines chung (nằm cùng thư mục với build_apk.sh)
    if [ -f "$MULTI_CONFIG_FILE" ]; then
        source "$MULTI_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME" ]; then
        source "$MASTER_SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME" ]; then
        source "$SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME"
    fi

    # 1d. Nạp cấu hình Personal Pipelines (const_my_cli.config hoặc fallback const_project_cli.config)
    if [ -f "$MY_CONFIG_FILE" ]; then
        source "$MY_CONFIG_FILE"
    elif [ -f "$PROJECT_CONFIG_FILE" ]; then
        source "$PROJECT_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$MY_CONFIG_FILE_NAME" ]; then
        source "$MASTER_SCRIPT_DIR/$MY_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$MY_CONFIG_FILE_NAME" ]; then
        source "$SCRIPT_DIR/$MY_CONFIG_FILE_NAME"
    fi

    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "Configuration file '$CONFIG_FILE_NAME' not found in $PWD or $SCRIPT_DIR!"
        log_error "Please create $CONFIG_FILE_NAME with required variables."
        exit 1
    fi

    # 2. Nạp cấu hình dự án (có thể ghi đè bất kỳ biến Car nào nếu cần)
    source "$CONFIG_FILE"

    local missing_vars=0
    local required_vars=(
        "SOURCE_CODE_RELATIVE_PATH"
        "APK_OUTPUT_RELATIVE_PATH"
        "APK_FILE_NAME"
        "APK_DEPLOY_PATH"
    )

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log_error "Missing required variable '$var' in $CONFIG_FILE_NAME"
            missing_vars=1
        fi
    done

    if [ "$missing_vars" -eq 1 ]; then
        log_error "Please update your $CONFIG_FILE_NAME file to include all required fields."
        exit 1
    fi

    # Resolve target platform (CLI flag takes precedence over config, default: android)
    PLATFORM="${CLI_PLATFORM:-${TARGET_PLATFORM:-android}}"
}

# --- 3. Run Test Mode ---
run_tests() {
    if [ "$TEST_MODE" != "true" ]; then
        return 0
    fi

    log_info "Running in Test Mode..."
    if [ -z "$TEST_RELATIVE_PATH" ] || [ -z "$TEST_BUILD_SCRIPT" ]; then
        log_error "Missing 'TEST_RELATIVE_PATH' or 'TEST_BUILD_SCRIPT' in $CONFIG_FILE_NAME"
        exit 1
    fi

    local config_dir
    config_dir="$(dirname "$CONFIG_FILE")"
    local test_dir="$config_dir/$TEST_RELATIVE_PATH"
    if [ ! -d "$test_dir" ]; then
        log_error "Test directory '$test_dir' does not exist"
        exit 1
    fi

    cd "$test_dir"
    if ! "./$TEST_BUILD_SCRIPT"; then
        log_error "Test build script '$TEST_BUILD_SCRIPT' failed"
        exit 1
    fi

    log_success "Tests completed successfully."
    exit 0
}

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

# --- 4d. Search Utilities (find_file, find_dir, find_text) ---
# (run_git_diff, run_git_amend and show_git_help live in src/telua_git.sh)
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

# --- 4e. Docker Help Utility (--docker-help: frequently used Docker commands) ---
# Commands are read dynamically from const_docker.config (located with build_apk.sh)
show_docker_help() {
    if [ -f "$DOCKER_CONFIG_FILE" ]; then
        cat "$DOCKER_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME" ]; then
        cat "$MASTER_SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME" ]; then
        cat "$SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME"
    else
        log_warn "Docker cheatsheet file '$DOCKER_CONFIG_FILE_NAME' not found!"
    fi
    exit 0
}

# --- 4f. Network Help Utility (--network-help: frequently used Network & Port commands) ---
# Commands are read dynamically from const_network.config (located with build_apk.sh)
show_network_help() {
    if [ -f "$NETWORK_CONFIG_FILE" ]; then
        cat "$NETWORK_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME" ]; then
        cat "$MASTER_SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME" ]; then
        cat "$SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME"
    else
        log_warn "Network cheatsheet file '$NETWORK_CONFIG_FILE_NAME' not found!"
    fi
    exit 0
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

# --- Main Entry Point ---
main() {
    parse_early_arguments "$@"
    load_and_validate_config
    parse_arguments "$@"

    # RAM monitoring: snapshot at start + peak sampler for the whole run
    if [ "$ENABLE_RAM_MONITOR" = "true" ]; then
        log_ram_snapshot "START"
        start_ram_sampler
        trap stop_ram_sampler EXIT
    fi

    if [ -n "$SOFTLINK_PATH" ]; then
        install_to_project "$SOFTLINK_PATH"
        exit 0
    fi

    if [ "$SHOW_INFO" = "true" ]; then
        show_info
    fi

    if [ "$SHOW_GIT_HELP" = "true" ]; then
        show_git_help
    fi

    if [ "$SHOW_DOCKER_HELP" = "true" ]; then
        show_docker_help
    fi

    if [ "$SHOW_NETWORK_HELP" = "true" ]; then
        show_network_help
    fi

    if [ -n "$ACTION_CMD" ]; then
        "$ACTION_CMD" "$SEARCH_PATTERN" "${SEARCH_TARGET_PATH:-.}"
        exit 0
    fi

    run_git_diff
    run_git_amend

    # Test scripts need ANDROID_BUILD_TOP, so set up the build env before them.
    resolve_android_paths || exit 1

    run_repo_reset

    # Run repo sync in ROOT_DIR, then cd to android/qssi and run post_sync_cli
    run_repo_sync

    setup_build_environment

    run_tests

    build_apk
    deploy_apk
    capture_logs

    # RAM monitoring: snapshot at end + peak usage report
    report_ram_summary

    log_success "All tasks completed successfully."
    exit 0
}

main "$@"