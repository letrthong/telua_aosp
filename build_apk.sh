#!/bin/bash
# ==============================================================================
# Copyright (C) 2026 letrthong@gmail.com
# Created & Maintained by: letrthong@gmail.com
# Generated & Refactored by: Gemini 3.8 Pro (Google DeepMind)
# Licensed under the Apache License, Version 2.0
# ==============================================================================

set -e

# --- Constants & Global Defaults ---
SCRIPT_VERSION="2.8.0"
SCRIPT_LAST_UPDATED="2026-10-13"
CONFIG_FILE_NAME="apk.config"
AUDIO_CONFIG_FILE_NAME="const_audio.config"
DUMP_CONFIG_FILE_NAME="const_dumpsys.config"
MULTI_CONFIG_FILE_NAME="const_multi_cli.config"
GIT_CONFIG_FILE_NAME="const_git.config"
DOCKER_CONFIG_FILE_NAME="const_docker.config"
NETWORK_CONFIG_FILE_NAME="const_network.config"
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

# Tìm const_audio.config: ưu tiên tại MASTER_SCRIPT_DIR (cùng thư mục build_apk.sh gốc) hoặc SCRIPT_DIR
find_audio_config_file() {
    if [ -f "$MASTER_SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME"
        return 0
    fi
    local cfg_dir
    cfg_dir="$(dirname "$CONFIG_FILE" 2>/dev/null || echo "")"
    if [ -n "$cfg_dir" ] && [ -f "$cfg_dir/$AUDIO_CONFIG_FILE_NAME" ]; then
        echo "$cfg_dir/$AUDIO_CONFIG_FILE_NAME"
        return 0
    fi
    echo "$MASTER_SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME"
}

AUDIO_CONFIG_FILE="$(find_audio_config_file)"

# Tìm const_dumpsys.config: ưu tiên tại MASTER_SCRIPT_DIR (cùng thư mục build_apk.sh gốc) hoặc SCRIPT_DIR
find_dump_config_file() {
    if [ -f "$MASTER_SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME"
        return 0
    fi
    local cfg_dir
    cfg_dir="$(dirname "$CONFIG_FILE" 2>/dev/null || echo "")"
    if [ -n "$cfg_dir" ] && [ -f "$cfg_dir/$DUMP_CONFIG_FILE_NAME" ]; then
        echo "$cfg_dir/$DUMP_CONFIG_FILE_NAME"
        return 0
    fi
    echo "$MASTER_SCRIPT_DIR/$DUMP_CONFIG_FILE_NAME"
}

DUMP_CONFIG_FILE="$(find_dump_config_file)"

# Tìm const_git.config: ưu tiên tại MASTER_SCRIPT_DIR (cùng thư mục build_apk.sh gốc) hoặc SCRIPT_DIR
find_git_config_file() {
    if [ -f "$MASTER_SCRIPT_DIR/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    local cfg_dir
    cfg_dir="$(dirname "$CONFIG_FILE" 2>/dev/null || echo "")"
    if [ -n "$cfg_dir" ] && [ -f "$cfg_dir/$GIT_CONFIG_FILE_NAME" ]; then
        echo "$cfg_dir/$GIT_CONFIG_FILE_NAME"
        return 0
    fi
    echo "$MASTER_SCRIPT_DIR/$GIT_CONFIG_FILE_NAME"
}

GIT_CONFIG_FILE="$(find_git_config_file)"

# Tìm const_docker.config: ưu tiên tại MASTER_SCRIPT_DIR (cùng thư mục build_apk.sh gốc) hoặc SCRIPT_DIR
find_docker_config_file() {
    if [ -f "$MASTER_SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME"
        return 0
    fi
    local cfg_dir
    cfg_dir="$(dirname "$CONFIG_FILE" 2>/dev/null || echo "")"
    if [ -n "$cfg_dir" ] && [ -f "$cfg_dir/$DOCKER_CONFIG_FILE_NAME" ]; then
        echo "$cfg_dir/$DOCKER_CONFIG_FILE_NAME"
        return 0
    fi
    echo "$MASTER_SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME"
}

DOCKER_CONFIG_FILE="$(find_docker_config_file)"

# Tìm const_network.config: ưu tiên tại MASTER_SCRIPT_DIR (cùng thư mục build_apk.sh gốc) hoặc SCRIPT_DIR
find_network_config_file() {
    if [ -f "$MASTER_SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME"
        return 0
    fi
    local cfg_dir
    cfg_dir="$(dirname "$CONFIG_FILE" 2>/dev/null || echo "")"
    if [ -n "$cfg_dir" ] && [ -f "$cfg_dir/$NETWORK_CONFIG_FILE_NAME" ]; then
        echo "$cfg_dir/$NETWORK_CONFIG_FILE_NAME"
        return 0
    fi
    echo "$MASTER_SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME"
}

NETWORK_CONFIG_FILE="$(find_network_config_file)"

# Tìm const_multi_cli.config: ưu tiên tại MASTER_SCRIPT_DIR (cùng thư mục build_apk.sh gốc) hoặc SCRIPT_DIR
find_multi_config_file() {
    if [ -f "$MASTER_SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME"
        return 0
    fi
    if [ -f "$SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME" ]; then
        echo "$SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME"
        return 0
    fi
    local cfg_dir
    cfg_dir="$(dirname "$CONFIG_FILE" 2>/dev/null || echo "")"
    if [ -n "$cfg_dir" ] && [ -f "$cfg_dir/$MULTI_CONFIG_FILE_NAME" ]; then
        echo "$cfg_dir/$MULTI_CONFIG_FILE_NAME"
        return 0
    fi
    echo "$MASTER_SCRIPT_DIR/$MULTI_CONFIG_FILE_NAME"
}

MULTI_CONFIG_FILE="$(find_multi_config_file)"

# Logging helpers with colors
log_info()    { echo -e "\033[1;34m[INFO]\033[0m $*"; }
log_success() { echo -e "\033[1;32m[SUCCESS]\033[0m $*"; }
log_warn()    { echo -e "\033[1;33m[WARN]\033[0m $*"; }
log_error()   { echo -e "\033[1;31m[ERROR]\033[0m $*"; }

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

Usage: telua [OPTIONS]  (or: $0 [OPTIONS])

Options:
  --install, install          Install/update 'telua' alias in ~/.bashrc pointing to:
                              $real_script
                              (auto-sources ~/.bashrc upon completion)
  --init, init                Initialize $CONFIG_FILE_NAME in current directory (\$PWD):
                              - Prompts for password to decrypt enc_apk.config
                              - Press Enter to use default plain $CONFIG_FILE_NAME
  --config <path>             Explicitly specify path to $CONFIG_FILE_NAME file
  -v, --version, version      Display script version and last update date, then exit
  --info, info                Display general build config and platform target info
  --platform android|qnx      Target platform: 'android' (default) or 'qnx' (reserved)
  --start-deploy true|false   Override ENABLE_DEPLOY from $CONFIG_FILE_NAME
  --no-reboot                 Fast restart (stop && start) instead of full device reboot
  --softlink [path]           Symlink this script + copy $CONFIG_FILE_NAME into [path] (overwrites)
                              (defaults to SOFTLINK_TARGET_PATH from $CONFIG_FILE_NAME if omitted)
  --audio, audio [action]     Control audio via ADB shell (actions from AUDIO_CLI_LIST
                              in $AUDIO_CONFIG_FILE_NAME: vol-up | vol-down | vol-mute | ks | ...)
  --dump, dump [target]       Run dumpsys diagnostics via ADB shell (targets from DUMP_CLI_LIST
                              in $DUMP_CONFIG_FILE_NAME: audio | car-service | car-audio | ...)
  --run, run [group]          Execute multi-command sequential pipeline group from
                              $MULTI_CONFIG_FILE_NAME (or: telua multi [group])
  --repo-sync                 Run 'repo sync' in ROOT_DIR, cd to android/qssi & run post_sync_cli before build
  --repo-reset                Run 'repo forall -c "git reset --hard && git clean -xdf"' (prompts for 'y' or use -y)
  -y, --yes                   Bypass confirmation prompts for dangerous operations (e.g. --repo-reset)
  --git-diff                  Run 'git diff HEAD^ HEAD' in this script's git repo and exit
  --git-amend                 Run 'git commit --amend --no-edit' (staged changes only) in this script's git repo and exit
  --update, update            Update script repo: 'git pull origin main' (auto-resets hard on error)
  --git-help, git             Display cheatsheet of commonly used Git commands and exit
  --docker-help, docker       Display cheatsheet of commonly used Docker commands and exit
  --network-help, network     Display cheatsheet of commonly used Network & Port commands and exit
  --find-file <pattern> [path] Search for files by pattern in [path] (default: '.')
  --find-dir <pattern> [path]  Search for directories by pattern in [path] (default: '.')
  --find-text <text> [path]    Search for text in files under [path] (default: '.')
  --test-mode true|false     Run unit test suite instead of full build
  -h, --help, help           Display this help message and exit

Configuration Info:
  Active Config:              $CONFIG_FILE
  Audio Config (Global):      $AUDIO_CONFIG_FILE
  Dump Config (Global):       $DUMP_CONFIG_FILE
  Multi-CLI Pipelines (Global):$MULTI_CONFIG_FILE
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
    while [[ $# -gt 0 ]]; do
        case "$1" in
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
            --audio|audio)
                if [ -n "$2" ] && [[ "$2" != --* ]]; then
                    AUDIO_ACTION="$2"
                    shift 2
                else
                    AUDIO_ACTION=""
                    shift 1
                fi
                handle_audio_command "$AUDIO_ACTION"
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
            vol-up|--vol-up)
                handle_audio_command "vol-up"
                exit 0
                ;;
            vol-down|--vol-down)
                handle_audio_command "vol-down"
                exit 0
                ;;
            vol-mute|--vol-mute)
                handle_audio_command "vol-mute"
                exit 0
                ;;
            -h|--help|help)
                print_help
                exit 0
                ;;
            *)
                local stripped_arg="${1#--}"
                stripped_arg=$(echo "$stripped_arg" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
                if is_audio_action "$stripped_arg"; then
                    handle_audio_command "$stripped_arg"
                    exit 0
                fi
                if is_dump_action "$stripped_arg"; then
                    handle_dump_command "$stripped_arg"
                    exit 0
                fi
                log_error "Unknown argument '$1'"
                print_help
                exit 1
                ;;
        esac
    done
}

# --- 1d. Audio Control & Custom ADB Shell Commands (--audio / audio) ---
show_audio_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  telua audio - Audio control commands via ADB Shell\033[0m"
    echo -e "  Config File:       \033[0;33m$CONFIG_FILE\033[0m"
    echo -e "  Audio Config File: \033[0;33m$AUDIO_CONFIG_FILE\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
    echo -e "\033[1;33mSUPPORTED AUDIO CLI COMMANDS:\033[0m"

    if [ -n "${AUDIO_CLI_LIST[*]}" ] && [ "${#AUDIO_CLI_LIST[@]}" -gt 0 ]; then
        local idx=1
        for item in "${AUDIO_CLI_LIST[@]}"; do
            local item_action="" item_desc="" item_cmd=""
            if [[ "$item" == *" :: "* ]]; then
                item_action="${item%% :: *}"
                local item_rest="${item#* :: }"
                item_desc="${item_rest%% :: *}"
                item_cmd="${item_rest#* :: }"
            elif [[ "$item" == *"|"* ]]; then
                item_action="$(echo "$item" | cut -d'|' -f1)"
                item_desc="$(echo "$item" | cut -d'|' -f2)"
                item_cmd="$(echo "$item" | cut -d'|' -f3-)"
            else
                item_action="$item"
                item_desc="Custom"
                item_cmd=""
            fi
            item_action="$(echo "$item_action" | xargs)"
            item_desc="$(echo "$item_desc" | xargs)"
            item_cmd="$(echo "$item_cmd" | xargs)"

            echo -e "  \033[1;32m$idx.\033[0m \033[1;37mtelua audio $item_action\033[0m"
            echo -e "     \033[0;90mDescription:\033[0m  $item_desc"
            echo -e "     \033[0;90mADB Command:\033[0m  \033[0;33madb shell $item_cmd\033[0m"
            echo ""
            idx=$((idx + 1))
        done
    else
        echo -e "  \033[0;90m(AUDIO_CLI_LIST not declared in $AUDIO_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi

    echo -e "\033[1;36m--------------------------------------------------------------------------------\033[0m"
    echo -e "\033[1;33mADB_SHELL_AUDIO_* CONFIG VARIABLES ($AUDIO_CONFIG_FILE_NAME):\033[0m"
    local has_dynamic_vars=0
    for var_name in ${!ADB_SHELL_AUDIO_@}; do
        echo -e "  \033[1;35m$var_name\033[0m = \"\033[0;32m${!var_name}\033[0m\""
        has_dynamic_vars=1
    done
    if [ "$has_dynamic_vars" -eq 0 ]; then
        echo -e "  \033[0;90m(No ADB_SHELL_AUDIO_* variables found)\033[0m"
    fi

    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

is_audio_action() {
    local target="$1"
    target=$(echo "$target" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    if [ -n "${AUDIO_CLI_LIST[*]}" ]; then
        for item in "${AUDIO_CLI_LIST[@]}"; do
            local act=""
            if [[ "$item" == *" :: "* ]]; then
                act="${item%% :: *}"
            elif [[ "$item" == *"|"* ]]; then
                act="$(echo "$item" | cut -d'|' -f1)"
            fi
            act="$(echo "$act" | xargs | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
            if [ "$act" = "$target" ]; then
                return 0
            fi
        done
    fi
    local suf
    suf=$(echo "$target" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    local v="ADB_SHELL_AUDIO_${suf}"
    if [ -n "${!v}" ]; then
        return 0
    fi
    return 1
}

handle_audio_command() {
    local action="$1"

    if [ -z "$action" ] || [ "$action" = "help" ] || [ "$action" = "--help" ] || [ "$action" = "-h" ]; then
        show_audio_help
        return 0
    fi

    local action_normalized
    action_normalized=$(echo "$action" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    local adb_cmd=""
    local action_label=""

    # 1. Tìm action trực tiếp trong mảng AUDIO_CLI_LIST (Single Source of Truth)
    if [ -n "${AUDIO_CLI_LIST[*]}" ]; then
        for item in "${AUDIO_CLI_LIST[@]}"; do
            local it_action="" it_desc="" it_cmd=""
            if [[ "$item" == *" :: "* ]]; then
                it_action="${item%% :: *}"
                local it_rest="${item#* :: }"
                it_desc="${it_rest%% :: *}"
                it_cmd="${it_rest#* :: }"
            elif [[ "$item" == *"|"* ]]; then
                it_action="$(echo "$item" | cut -d'|' -f1)"
                it_desc="$(echo "$item" | cut -d'|' -f2)"
                it_cmd="$(echo "$item" | cut -d'|' -f3-)"
            fi
            it_action="$(echo "$it_action" | xargs | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
            if [ "$it_action" = "$action_normalized" ]; then
                action_label="$(echo "$it_desc" | xargs)"
                adb_cmd="$(echo "$it_cmd" | xargs)"
                break
            fi
        done
    fi

    # 2. Nếu chưa có trong AUDIO_CLI_LIST, kiểm tra biến động ADB_SHELL_AUDIO_<ACTION> hoặc ADB_SHELL_<ACTION>
    if [ -z "$adb_cmd" ]; then
        local var_suffix
        var_suffix=$(echo "$action_normalized" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
        local var_audio="ADB_SHELL_AUDIO_${var_suffix}"
        local var_generic="ADB_SHELL_${var_suffix}"

        if [ -n "${!var_audio}" ]; then
            action_label="Audio ($action)"
            adb_cmd="${!var_audio}"
        elif [ -n "${!var_generic}" ]; then
            action_label="ADB Shell ($action)"
            adb_cmd="${!var_generic}"
        fi
    fi

    # 3. Nếu vẫn không tìm thấy, báo lỗi và hiển thị trợ giúp
    if [ -z "$adb_cmd" ]; then
        log_error "Unknown audio action '$action'!"
        log_error "Supported actions: vol-up | vol-down | vol-mute | ks | ks-stop (or configure AUDIO_CLI_LIST in $AUDIO_CONFIG_FILE_NAME)"
        if [ "$action_normalized" = "d" ] || [ "$action_normalized" = "dump" ]; then
            log_warn "'dump' has moved to: telua dump audio | telua dump car-service"
        fi
        show_audio_help
        exit 1
    fi

    if ! command -v adb >/dev/null 2>&1; then
        log_error "'adb' command not found. Please ensure Android platform-tools is in your PATH."
        exit 1
    fi

    # Verify device state
    local dev_state
    dev_state=$(adb get-state 2>/dev/null || echo "offline")
    if [ "$dev_state" != "device" ]; then
        log_error "No Android device connected or device is not ready (state: $dev_state)."
        log_error "Please connect a device via USB/TCP and verify with 'adb devices'."
        exit 1
    fi

    log_info "Executing $action_label via ADB Shell..."
    echo -e "  \033[1;36m[ADB CMD]\033[0m adb shell $adb_cmd"

    # Execute ADB shell command
    adb shell "$adb_cmd"
    local ret=$?
    if [ $ret -eq 0 ]; then
        log_success "$action_label command executed successfully."
    else
        log_error "Failed to execute '$action_label' command on device (exit code: $ret)."
        exit $ret
    fi
}

# --- 1d. Audio Control & Custom ADB Shell Commands (--audio / audio) ---
show_dump_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  telua dump - Dumpsys diagnostics commands via ADB Shell\033[0m"
    echo -e "  Config File:       \033[0;33m$CONFIG_FILE\033[0m"
    echo -e "  Dump Config File:  \033[0;33m$DUMP_CONFIG_FILE\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
    echo -e "\033[1;33mSUPPORTED DUMP CLI COMMANDS:\033[0m"

    if [ -n "${DUMP_CLI_LIST[*]}" ] && [ "${#DUMP_CLI_LIST[@]}" -gt 0 ]; then
        local idx=1
        for item in "${DUMP_CLI_LIST[@]}"; do
            local item_action="" item_desc="" item_cmd=""
            if [[ "$item" == *" :: "* ]]; then
                item_action="${item%% :: *}"
                local item_rest="${item#* :: }"
                item_desc="${item_rest%% :: *}"
                item_cmd="${item_rest#* :: }"
            elif [[ "$item" == *"|"* ]]; then
                item_action="$(echo "$item" | cut -d'|' -f1)"
                item_desc="$(echo "$item" | cut -d'|' -f2)"
                item_cmd="$(echo "$item" | cut -d'|' -f3-)"
            else
                item_action="$item"
                item_desc="Custom"
                item_cmd=""
            fi
            item_action="$(echo "$item_action" | xargs)"
            item_desc="$(echo "$item_desc" | xargs)"
            item_cmd="$(echo "$item_cmd" | xargs)"

            echo -e "  \033[1;32m$idx.\033[0m \033[1;37mtelua dump $item_action\033[0m"
            echo -e "     \033[0;90mDescription:\033[0m  $item_desc"
            echo -e "     \033[0;90mADB Command:\033[0m  \033[0;33madb shell $item_cmd\033[0m"
            echo ""
            idx=$((idx + 1))
        done
    else
        echo -e "  \033[0;90m(DUMP_CLI_LIST not declared in $DUMP_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi

    echo -e "\033[1;36m--------------------------------------------------------------------------------\033[0m"
    echo -e "\033[1;33mADB_SHELL_DUMP_* CONFIG VARIABLES ($DUMP_CONFIG_FILE_NAME):\033[0m"
    local has_dynamic_vars=0
    for var_name in ${!ADB_SHELL_DUMP_@}; do
        echo -e "  \033[1;35m$var_name\033[0m = \"\033[0;32m${!var_name}\033[0m\""
        has_dynamic_vars=1
    done
    if [ "$has_dynamic_vars" -eq 0 ]; then
        echo -e "  \033[0;90m(No ADB_SHELL_DUMP_* variables found)\033[0m"
    fi

    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

is_dump_action() {
    local target="$1"
    target=$(echo "$target" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    if [ -n "${DUMP_CLI_LIST[*]}" ]; then
        for item in "${DUMP_CLI_LIST[@]}"; do
            local act=""
            if [[ "$item" == *" :: "* ]]; then
                act="${item%% :: *}"
            elif [[ "$item" == *"|"* ]]; then
                act="$(echo "$item" | cut -d'|' -f1)"
            fi
            act="$(echo "$act" | xargs | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
            if [ "$act" = "$target" ]; then
                return 0
            fi
        done
    fi
    local suf
    suf=$(echo "$target" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    local v="ADB_SHELL_DUMP_${suf}"
    if [ -n "${!v}" ]; then
        return 0
    fi
    return 1
}

handle_dump_command() {
    local action="$1"

    if [ -z "$action" ] || [ "$action" = "help" ] || [ "$action" = "--help" ] || [ "$action" = "-h" ]; then
        show_dump_help
        return 0
    fi

    local action_normalized
    action_normalized=$(echo "$action" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    local adb_cmd=""
    local action_label=""

    # 1. Tìm action trực tiếp trong mảng DUMP_CLI_LIST (Single Source of Truth)
    if [ -n "${DUMP_CLI_LIST[*]}" ]; then
        for item in "${DUMP_CLI_LIST[@]}"; do
            local it_action="" it_desc="" it_cmd=""
            if [[ "$item" == *" :: "* ]]; then
                it_action="${item%% :: *}"
                local it_rest="${item#* :: }"
                it_desc="${it_rest%% :: *}"
                it_cmd="${it_rest#* :: }"
            elif [[ "$item" == *"|"* ]]; then
                it_action="$(echo "$item" | cut -d'|' -f1)"
                it_desc="$(echo "$item" | cut -d'|' -f2)"
                it_cmd="$(echo "$item" | cut -d'|' -f3-)"
            fi
            it_action="$(echo "$it_action" | xargs | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
            if [ "$it_action" = "$action_normalized" ]; then
                action_label="$(echo "$it_desc" | xargs)"
                adb_cmd="$(echo "$it_cmd" | xargs)"
                break
            fi
        done
    fi

    # 2. Nếu chưa có trong DUMP_CLI_LIST, kiểm tra biến động ADB_SHELL_DUMP_<ACTION>
    if [ -z "$adb_cmd" ]; then
        local var_suffix
        var_suffix=$(echo "$action_normalized" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
        local var_dump="ADB_SHELL_DUMP_${var_suffix}"

        if [ -n "${!var_dump}" ]; then
            action_label="Dump ($action)"
            adb_cmd="${!var_dump}"
        fi
    fi

    # 3. Nếu vẫn không tìm thấy, báo lỗi và hiển thị trợ giúp
    if [ -z "$adb_cmd" ]; then
        log_error "Unknown dump action '$action'!"
        log_error "Supported actions: audio | car-service | car-audio (or configure DUMP_CLI_LIST in $DUMP_CONFIG_FILE_NAME)"
        show_dump_help
        exit 1
    fi

    if ! command -v adb >/dev/null 2>&1; then
        log_error "'adb' command not found. Please ensure Android platform-tools is in your PATH."
        exit 1
    fi

    # Verify device state
    local dev_state
    dev_state=$(adb get-state 2>/dev/null || echo "offline")
    if [ "$dev_state" != "device" ]; then
        log_error "No Android device connected or device is not ready (state: $dev_state)."
        log_error "Please connect a device via USB/TCP and verify with 'adb devices'."
        exit 1
    fi

    log_info "Executing $action_label via ADB Shell..."
    echo -e "  \033[1;36m[ADB CMD]\033[0m adb shell $adb_cmd"

    # Execute ADB shell command
    adb shell "$adb_cmd"
    local ret=$?
    if [ $ret -eq 0 ]; then
        log_success "$action_label command executed successfully."
    else
        log_error "Failed to execute '$action_label' command on device (exit code: $ret)."
        exit $ret
    fi
}

# --- 1f. Multi-CLI Command Pipelines (--run / run / --multi / multi) ---
show_run_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  telua run - Sequential Multi-CLI Pipelines & Macro Execution\033[0m"
    echo -e "  Config File:       \033[0;33m$CONFIG_FILE\033[0m"
    echo -e "  Pipeline Config:   \033[0;33m$MULTI_CONFIG_FILE\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
    echo -e "\033[1;33mAVAILABLE PIPELINE GROUPS:\033[0m"

    if [ -n "${MULTI_GROUP_LIST[*]}" ] && [ "${#MULTI_GROUP_LIST[@]}" -gt 0 ]; then
        local idx=1
        for item in "${MULTI_GROUP_LIST[@]}"; do
            local grp_name="" grp_desc=""
            if [[ "$item" == *" :: "* ]]; then
                grp_name="${item%% :: *}"
                grp_desc="${item#* :: }"
            else
                grp_name="$item"
                grp_desc="Pipeline group"
            fi
            grp_name="$(echo "$grp_name" | xargs)"
            grp_desc="$(echo "$grp_desc" | xargs)"

            local var_suffix
            var_suffix=$(echo "$grp_name" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
            local array_name="MULTI_CMD_${var_suffix}"
            local -a steps=()
            if declare -p "$array_name" >/dev/null 2>&1; then
                eval "steps=(\"\${${array_name}[@]}\")"
            fi

            echo -e "  \033[1;32m$idx.\033[0m \033[1;37mtelua run $grp_name\033[0m"
            echo -e "     \033[0;90mDescription:\033[0m  $grp_desc"
            if [ "${#steps[@]}" -gt 0 ]; then
                echo -e "     \033[0;90mSteps:\033[0m        \033[0;36m(${#steps[@]} commands sequential)\033[0m"
                local step_i=1
                for step_cmd in "${steps[@]}"; do
                    echo -e "       \033[1;33m[$step_i/${#steps[@]}]\033[0m \033[0;37m$step_cmd\033[0m"
                    step_i=$((step_i + 1))
                done
            else
                echo -e "     \033[0;90mSteps:\033[0m        \033[0;31m(No steps declared in $array_name)\033[0m"
            fi
            echo ""
            idx=$((idx + 1))
        done
    else
        echo -e "  \033[0;90m(No MULTI_GROUP_LIST declared in $MULTI_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi

    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

is_run_group() {
    local target="$1"
    target=$(echo "$target" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    if [ -n "${MULTI_GROUP_LIST[*]}" ]; then
        for item in "${MULTI_GROUP_LIST[@]}"; do
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
    local array_name="MULTI_CMD_${suf}"
    if declare -p "$array_name" >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

handle_run_command() {
    local group="$1"

    if [ -z "$group" ] || [ "$group" = "help" ] || [ "$group" = "--help" ] || [ "$group" = "-h" ]; then
        show_run_help
        return 0
    fi

    local group_normalized
    group_normalized=$(echo "$group" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    local group_label=""
    if [ -n "${MULTI_GROUP_LIST[*]}" ]; then
        for item in "${MULTI_GROUP_LIST[@]}"; do
            local g_name="" g_desc=""
            if [[ "$item" == *" :: "* ]]; then
                g_name="${item%% :: *}"
                g_desc="${item#* :: }"
            else
                g_name="$item"
                g_desc="$item"
            fi
            g_name="$(echo "$g_name" | xargs | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
            if [ "$g_name" = "$group_normalized" ]; then
                group_label="$(echo "$g_desc" | xargs)"
                break
            fi
        done
    fi

    local var_suffix
    var_suffix=$(echo "$group_normalized" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    local array_name="MULTI_CMD_${var_suffix}"
    local -a step_cmds=()
    if declare -p "$array_name" >/dev/null 2>&1; then
        eval "step_cmds=(\"\${${array_name}[@]}\")"
    fi

    if [ "${#step_cmds[@]}" -eq 0 ]; then
        log_error "Pipeline group '$group' not found or has no steps defined!"
        log_error "Expected array '$array_name' in $MULTI_CONFIG_FILE_NAME or $CONFIG_FILE_NAME"
        show_run_help
        exit 1
    fi

    local total_steps="${#step_cmds[@]}"
    echo ""
    log_info "============================================================"
    log_info " Executing Multi-CLI Pipeline: '$group_normalized'"
    [ -n "$group_label" ] && log_info " Description: $group_label"
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
    log_success "All $total_steps steps of pipeline '$group_normalized' completed successfully."
    echo ""
}

# --- 1a. Install Alias into ~/.bashrc (--install) ---
install_bashrc_alias() {
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

# --- 1b. Initialize Project Config (--init) ---
init_project_config() {
    local target_config="$PWD/$CONFIG_FILE_NAME"
    local template_config="$SCRIPT_DIR/$CONFIG_FILE_NAME"
    local enc_config="$SCRIPT_DIR/enc_apk.config"
    local crypto_script="$SCRIPT_DIR/config_crypto.py"

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
            log_info "Decrypting template using config_crypto.py..."
            if echo "$input_pw" | python3 "$crypto_script" decrypt -i "$enc_config" -o "$target_config" --force - 2>/dev/null; then
                unset input_pw
                log_success "Successfully decrypted and created: $target_config"
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
        log_info "Next: edit $CONFIG_FILE_NAME, then run: telua --info"
        exit 0
    fi

    log_error "Neither '$enc_config' nor '$template_config' was found in $SCRIPT_DIR!"
    exit 1
}

# --- 1c. Install into a project directory (--softlink <path>) ---
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

# --- 1b. Diagnostic Info (--info) ---
show_info_general() {
    local module_name="${MODULE_NAME:-${APK_FILE_NAME%.apk}}"
    local jobs="${BUILD_JOBS:-$(nproc 2>/dev/null || echo 8)}"
    local target_platform="${PLATFORM:-${TARGET_PLATFORM:-android}}"

    echo -e "\n\033[1;36m=== 1. GENERAL BUILD CONFIGURATION ===\033[0m"
    echo "  Script Version:   v$SCRIPT_VERSION (Updated: $SCRIPT_LAST_UPDATED)"
    echo "  Config File:      $CONFIG_FILE"
    echo "  Audio Config:     $AUDIO_CONFIG_FILE"
    echo "  Project:          ${ACTIVE_PROJECT:-default}"
    echo "  Target Platform:  $target_platform"
    echo "  Target Lunch:     ${CONFIG_TARGET_PRODUCT}-${CONFIG_TARGET_BUILD_VARIANT}"
    echo "  Module Build Jobs:-j$jobs (m $module_name)"
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
    echo "  Audio Controls (ADB Shell):"
    echo "    Vol Up:         ${ADB_SHELL_AUDIO_UP:-cmd media_session volume --show --adj raise}"
    echo "    Vol Down:       ${ADB_SHELL_AUDIO_DOWN:-cmd media_session volume --show --adj lower}"
    echo "    Vol Mute:       ${ADB_SHELL_AUDIO_MUTE:-cmd media_session volume --show --adj mute}"
    echo "    Audio Dump:     ${ADB_SHELL_AUDIO_DUMP:-${ADB_SHELL_AUDIO_D:-dumpsys audio}}"
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
    echo -e "\033[1;36m====================================================\033[0m\n"
    exit 0
}

# --- 2. Load & Validate Configuration ---
load_and_validate_config() {
    # 1. Nạp cấu hình Audio chung (nằm cùng thư mục với build_apk.sh)
    if [ -f "$AUDIO_CONFIG_FILE" ]; then
        source "$AUDIO_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME" ]; then
        source "$MASTER_SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME" ]; then
        source "$SCRIPT_DIR/$AUDIO_CONFIG_FILE_NAME"
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

    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "Configuration file '$CONFIG_FILE_NAME' not found in $PWD or $SCRIPT_DIR!"
        log_error "Please create $CONFIG_FILE_NAME with required variables."
        exit 1
    fi

    # 2. Nạp cấu hình dự án (có thể ghi đè bất kỳ biến Audio nào nếu cần)
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

# --- 4. Resolve Android AOSP Top Directory ---
resolve_android_paths() {
    # Resolve starting directory: prioritize directory of CONFIG_FILE ($PWD if found), fallback to SCRIPT_DIR
    local current_dir
    if [ -f "$CONFIG_FILE" ]; then
        current_dir="$(cd "$(dirname "$CONFIG_FILE")" && pwd)"
    else
        current_dir="$SCRIPT_DIR"
    fi
    local android_dir=""

    while [ "$current_dir" != "/" ] && [ "$current_dir" != "." ]; do
        if [ "$(basename "$current_dir")" = "android" ]; then
            android_dir="$current_dir"
            break
        fi
        current_dir="$(dirname "$current_dir")"
    done

    if [ -z "$android_dir" ]; then
        log_error "Could not find the 'android' root directory in ancestor paths!"
        log_info "Must check apk.config"
        # 'return' (not 'exit') so callers like show_info can recover.
        return 1
    fi

    ROOT_DIR="$(dirname "$android_dir")"

    if [ -n "$AOSP_TOP_REL_PATH" ]; then
        ANDROID_TOP="$ROOT_DIR/$AOSP_TOP_REL_PATH"
    elif [ -d "$ROOT_DIR/android/qssi" ]; then
        ANDROID_TOP="$ROOT_DIR/android/qssi"
    else
        ANDROID_TOP="$android_dir"
    fi

    SOURCE_DIR="$ANDROID_TOP/$SOURCE_CODE_RELATIVE_PATH"
    DIR_OUT="$ANDROID_TOP/$APK_OUTPUT_RELATIVE_PATH"
    APK_OUT="$DIR_OUT/$APK_FILE_NAME"

    log_info "ROOT_DIR:    $ROOT_DIR"
    log_info "ANDROID_TOP: $ANDROID_TOP"
    log_info "SOURCE_DIR:  $SOURCE_DIR"
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

    log_info "Executing: git pull origin main..."
    if git -C "$target_repo" pull origin main; then
        log_success "Successfully pulled latest updates from origin/main."
        exit 0
    fi

    # Neu loi thi reset hard va pull ve lai
    log_warn "'git pull origin main' encountered an error or merge conflict!"
    log_info "Initiating automatic recovery: fetching origin main..."
    git -C "$target_repo" fetch origin main || true

    log_info "Running: git reset --hard origin/main..."
    if git -C "$target_repo" reset --hard origin/main; then
        log_success "Reset repository to origin/main successfully."
        log_info "Retrying: git pull origin main..."
        if git -C "$target_repo" pull origin main; then
            log_success "Successfully pulled latest updates after hard reset."
            exit 0
        else
            log_error "'git pull origin main' failed after hard reset."
            exit 1
        fi
    else
        log_error "Failed to execute 'git reset --hard origin/main'."
        exit 1
    fi
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

# --- 5a. Setup Android AOSP Build Environment ---
setup_build_environment_android() {
    cd "$ANDROID_TOP"

    local prod_var="${ENV_VAR_PRODUCT_NAME:-TARGET_PRODUCT}"
    local var_var="${ENV_VAR_VARIANT_NAME:-TARGET_BUILD_VARIANT}"
    local current_prod="${!prod_var}"
    local current_variant="${!var_var}"

    if [[ -n "$current_prod" && -n "$current_variant" ]]; then
        log_info "Build environment is already active:"
        log_info "$prod_var = $current_prod, $var_var = $current_variant"
        return 0
    fi

    if [ ! -f "build/envsetup.sh" ]; then
        log_error "Cannot find 'build/envsetup.sh' in $ANDROID_TOP"
        exit 1
    fi

    log_info "Initializing Android environment: source build/envsetup.sh"
    # envsetup.sh/lunch return non-zero on harmless warnings (e.g. symlink creation),
    # which 'set -e' would turn into an abort; success is verified via target env vars below.
    set +e
    source build/envsetup.sh

    local target="${CONFIG_TARGET_PRODUCT}-${CONFIG_TARGET_BUILD_VARIANT}"
    log_info "Running lunch target: $target"
    lunch "$target"
    set -e

    current_prod="${!prod_var}"
    current_variant="${!var_var}"

    if [[ -z "$current_prod" || -z "$current_variant" ]]; then
        log_error "Failed to initialize target environment variables ($prod_var, $var_var) after lunch."
        exit 1
    fi

    log_success "Android environment ready: $current_prod-$current_variant ($prod_var=$current_prod, $var_var=$current_variant)"
}

# --- 5b. Setup QNX Build Environment (SDP Toolchain) ---
setup_build_environment_qnx() {
    echo ""
    log_info "============================================"
    log_info " Setup QNX Build Environment (SDP Toolchain)"
    log_info "============================================"

    log_warn "Target platform is set to 'qnx'."
    log_info "QNX build toolchain initialization template:"
    log_info "  - Toolchain:    QNX Software Development Platform (SDP)"
    log_info "  - Environment:  source qnxsdp-env.sh / export QNX_TARGET & QNX_HOST"
    log_warn "QNX build environment setup is currently placeholder (will be supplemented later)."
    return 0
}

# --- 5. Setup Build Environment Dispatcher ---
setup_build_environment() {
    local target_platform="${PLATFORM:-${TARGET_PLATFORM:-android}}"
    case "$target_platform" in
        android)
            setup_build_environment_android
            ;;
        qnx)
            setup_build_environment_qnx
            ;;
        *)
            log_error "Unsupported build platform '$target_platform'! Supported: 'android' | 'qnx'"
            exit 1
            ;;
    esac
}

# --- 6. Compile APK Module ---
build_apk() {
    log_info "Cleaning previous build output: $DIR_OUT"
    rm -rf "$DIR_OUT"

    log_info "Navigating to module source directory: $SOURCE_DIR"
    if [ ! -d "$SOURCE_DIR" ]; then
        log_error "Source directory does not exist: $SOURCE_DIR"
        exit 1
    fi

    cd "$SOURCE_DIR"
    # 'mm' builds every module under the directory, including tests/androidTest,
    # so build only the APK module (name = APK file name without .apk).
    local module_name="${MODULE_NAME:-${APK_FILE_NAME%.apk}}"
    local jobs="${BUILD_JOBS:-$(nproc 2>/dev/null || echo 8)}"
    log_info "Compiling module '$module_name' with m -j$jobs..."
    m "$module_name" -j"$jobs"

    if [ ! -f "$APK_OUT" ]; then
        log_error "APK not found at $APK_OUT after build completed."
        exit 1
    fi

    cp -fv "$APK_OUT" "$SCRIPT_DIR/"
    log_success "Build successful!"
    log_success "APK copied to: $SCRIPT_DIR/$APK_FILE_NAME"
}

# --- 7. Device Wait Utility ---
wait_for_device() {
    local timeout_sec="${1:-180}"
    local elapsed=0

    log_info "Waiting for device (timeout: ${timeout_sec}s)..."
    while [ "$elapsed" -lt "$timeout_sec" ]; do
        if adb get-state 2>/dev/null | grep -q "device"; then
            log_info "Device is online."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log_error "Timed out waiting for device after ${timeout_sec}s"
    return 1
}

# Block until the device drops off adb after 'adb reboot', so wait_for_device
# does not return early on the still-running old session.
wait_for_disconnect() {
    # Older platform-tools lack wait-for-disconnect: fall back to a short sleep.
    if ! timeout 30 adb wait-for-disconnect 2>/dev/null; then
        sleep 3
    fi
}

# After a full reboot, wait until Android reports boot completed.
# (Only valid after a real reboot: the property is reset at boot, but NOT by
# 'stop'/'start' - see restart_framework.)
wait_for_boot_completed() {
    local timeout_sec="${1:-300}"
    local elapsed=0

    log_info "Waiting for boot to complete (sys.boot_completed=1, timeout: ${timeout_sec}s)..."
    while [ "$elapsed" -lt "$timeout_sec" ]; do
        if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
            log_info "Boot completed after ${elapsed}s."
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    log_error "Boot did not complete within ${timeout_sec}s."
    return 1
}

# Restart the Android framework without a full reboot (--no-reboot).
# NOTE: sys.boot_completed usually stays "1" across 'stop'/'start', so it
# cannot detect readiness. Instead, wait for a NEW system_server PID and for
# PackageManager to answer.
restart_framework() {
    local timeout_sec="${1:-90}"
    local elapsed=0
    local old_pid new_pid

    old_pid=$(adb shell pidof system_server 2>/dev/null | tr -d '\r')
    log_info "Fast restart (--no-reboot): restarting Android framework (old system_server PID: ${old_pid:-none})..."
    adb shell stop
    sleep 1
    adb shell start

    log_info "Waiting for Android framework to be ready (timeout: ${timeout_sec}s)..."
    while [ "$elapsed" -lt "$timeout_sec" ]; do
        new_pid=$(adb shell pidof system_server 2>/dev/null | tr -d '\r')
        if [ -n "$new_pid" ] && [ "$new_pid" != "$old_pid" ] \
            && adb shell pm path android 2>/dev/null | grep -q "package:"; then
            log_info "Android framework is up (new system_server PID: $new_pid) after ${elapsed}s."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log_error "Android framework did not come back within ${timeout_sec}s."
    return 1
}

# --- 8. Ensure ADB Remount (Handles first-time reboot requirement) ---
# NOTE:
# 1. Device MUST run a 'userdebug' or 'eng' build image. Production 'user' builds
#    do not support 'adb root' or 'adb remount'.
# 2. First-time remount setup (dynamic partition / overlayfs) requires an automatic
#    reboot and may take ~3-5 mins before the system partition becomes writable.
# 3. Subsequent remounts will complete instantly in 1-2 seconds.
ensure_adb_remount() {
    # Verify userdebug / eng build variant first (getprop works without root),
    # so 'user' builds get a clear error instead of a failed 'adb root'.
    local build_type
    build_type=$(adb shell getprop ro.build.type 2>/dev/null | tr -d '\r')
    log_info "Detected device build variant: '${build_type:-unknown}'"
    if [ "$build_type" = "user" ]; then
        log_error "Device is running a 'user' build! 'adb remount' is forbidden on user builds."
        log_error "Please flash a 'userdebug' or 'eng' build image to enable deployment."
        exit 1
    fi

    log_info "Acquiring root access (adb root)..."
    acquire_root || exit 1

    log_info "Remounting partitions read-write (adb remount)..."
    local remount_output
    remount_output=$(adb remount 2>&1 || true)
    echo "$remount_output"

    # Trust an actual write test, not adb's message text (it varies by version).
    if is_deploy_path_writable; then
        log_success "Filesystem is writable."
        return 0
    fi

    # Not writable yet: first-time overlayfs/scratch setup needs a reboot.
    if echo "$remount_output" | grep -qiE "reboot|scratch"; then
        log_warn "First-time remount detected (overlayfs/scratch setup required)."
        log_info "Rebooting device now (this first-time initialization takes ~3-5 minutes)..."
        adb reboot
        wait_for_disconnect
        if ! wait_for_device 300; then
            log_error "Device did not come back online after remount reboot. Aborting."
            exit 1
        fi

        log_info "Device back online. Re-acquiring root and completing remount..."
        acquire_root || exit 1
        remount_output=$(adb remount 2>&1 || true)
        echo "$remount_output"
        if is_deploy_path_writable; then
            log_success "First-time remount setup complete. Filesystem is writable."
            return 0
        fi
    fi

    log_error "'$(dirname "$APK_DEPLOY_PATH")' is still read-only after 'adb remount'."
    log_error "See the remount output above (if verity is enabled: 'adb disable-verity' then reboot)."
    exit 1
}

# Wait until adbd actually runs as root (uid 0). 'adb root' restarts adbd, so a
# plain wait_for_device can return on the old, non-root session.
acquire_root() {
    local elapsed=0
    while [ "$elapsed" -lt 30 ]; do
        if [ "$(adb shell id -u 2>/dev/null | tr -d '\r')" = "0" ]; then
            log_info "adbd is running as root."
            return 0
        fi
        adb root >/dev/null 2>&1 || true
        sleep 2
        elapsed=$((elapsed + 2))
    done
    log_error "adbd is not running as root after 30s ('adb root' failed)."
    return 1
}

# Return 0 if the parent directory of APK_DEPLOY_PATH can be written to.
is_deploy_path_writable() {
    local probe
    probe="$(dirname "$APK_DEPLOY_PATH")/.build_apk_rw_test"
    adb shell "touch '$probe' && rm -f '$probe'" >/dev/null 2>&1
}


# --- 9a. Deploy APK to Android Device (AOSP / ADB) ---
deploy_android() {
    echo ""
    log_info "============================================"
    log_info " Starting Deployment: Android Device (ADB)"
    log_info "============================================"

    if ! command -v adb >/dev/null 2>&1; then
        log_error "'adb' not found. Ensure Android platform-tools is in PATH."
        exit 1
    fi

    if ! wait_for_device 180; then
        log_error "Device did not become available before deployment. Aborting."
        exit 1
    fi

    ensure_adb_remount

    log_info "Pushing $APK_FILE_NAME to $APK_DEPLOY_PATH/$APK_FILE_NAME"
    adb push "$SCRIPT_DIR/$APK_FILE_NAME" "$APK_DEPLOY_PATH/$APK_FILE_NAME"
    adb shell chmod 644 "$APK_DEPLOY_PATH/$APK_FILE_NAME"
    # Remove old oat/dex cache if present to ensure updated code runs
    adb shell rm -rf "$APK_DEPLOY_PATH/oat" 2>/dev/null || true
    adb shell sync

    if [ "$ENABLE_DEBUG_LOG" = "true" ] && [ -n "$DEBUG_LOG_TAGS" ]; then
        local log_level="${DEBUG_LOG_LEVEL:-DEBUG}"
        log_info "Setting $log_level log properties for tags: $DEBUG_LOG_TAGS"
        for tag in $DEBUG_LOG_TAGS; do
            adb shell setprop persist.log.tag."$tag" "$log_level"
            adb shell setprop log.tag."$tag" "$log_level"
        done
        log_success "Debug log properties configured."
    fi

    # Clear old logcat buffer before restart so captured logs are 100% fresh
    local logcat_enabled="${ENABLE_ANDROID_LOGCAT:-${ENABLE_LOGCAT:-false}}"
    if [ "$logcat_enabled" = "true" ]; then
        log_info "Clearing previous device logcat buffer (adb logcat -c)..."
        adb logcat -c 2>/dev/null || true
    fi

    if [ "$NO_REBOOT" = "true" ]; then
        if ! restart_framework 90; then
            log_error "Fast restart failed. Re-run without --no-reboot for a full reboot."
            exit 1
        fi
    else
        log_info "Rebooting device to apply changes..."
        adb reboot
        wait_for_disconnect

        log_info "Waiting for device to come back online after reboot (approx 2-3 mins)..."
        if ! wait_for_device 300; then
            log_error "Device did not come back online after reboot. Aborting."
            exit 1
        fi

        # adb comes online early in boot; wait until Android reports boot done.
        if ! wait_for_boot_completed 300; then
            log_error "Device did not finish booting after reboot. Aborting."
            exit 1
        fi
    fi

    adb devices
    log_success "Android deployment completed successfully."
}

# --- 9b. Deploy APK to QNX Hypervisor (Android Guest VM) ---
deploy_qnx() {
    echo ""
    log_info "============================================"
    log_info " Starting Deployment: QNX Hypervisor"
    log_info "============================================"

    log_warn "Target platform is set to 'qnx'."
    log_warn "Direct deployment to QNX Hypervisor is currently under development (not yet supported)."
    log_info "Planned workflow for QNX Hypervisor:"
    log_info "  1. Connect ADB over virtual network (adb connect <QNX_ANDROID_IP>:5555)"
    log_info "  2. Push APK into Android Guest VM / shared virtio-fs mount"
    log_info "  3. Fast-restart Android Guest VM (qvm-control) without rebooting QNX host"
    log_warn "Skipping device deployment for now. APK module build completed successfully."
    return 0
}

# --- 9. Deploy APK Dispatcher ---
deploy_apk() {
    local target_platform="${PLATFORM:-${TARGET_PLATFORM:-android}}"
    case "$target_platform" in
        android)
            local deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_ANDROID_DEPLOY:-${ENABLE_DEPLOY:-true}}}"
            if [ "$deploy_enabled" != "true" ]; then
                log_info "Android deployment is disabled (ENABLE_ANDROID_DEPLOY='$deploy_enabled'), skipping."
                return 0
            fi
            deploy_android
            ;;
        qnx)
            local deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_QNX_DEPLOY:-${ENABLE_DEPLOY:-false}}}"
            if [ "$deploy_enabled" != "true" ]; then
                log_info "QNX deployment is disabled (ENABLE_QNX_DEPLOY='$deploy_enabled'), skipping."
                return 0
            fi
            deploy_qnx
            ;;
        *)
            log_error "Unsupported deployment platform '$target_platform'! Supported: 'android' | 'qnx'"
            exit 1
            ;;
    esac
}

# --- 10a. Android Logcat Capture ---
capture_logs_android() {
    local log_file="$SCRIPT_DIR/deployment_log.txt"

    # Give the app/service time to start and emit logs after boot/restart.
    local settle="${LOGCAT_SETTLE_SECONDS:-10}"
    log_info "Waiting ${settle}s for the app to start before capturing logcat..."
    sleep "$settle"

    if [ -n "$LOGCAT_FILTER" ]; then
        log_info "Capturing logcat filtered by '$LOGCAT_FILTER' to $log_file"
        adb logcat -d | grep -E "$LOGCAT_FILTER" > "$log_file" || true
    else
        log_info "Capturing full logcat (no filter) to $log_file"
        adb logcat -d > "$log_file" || true
    fi

    local line_count
    line_count=$(wc -l < "$log_file" | tr -d ' ')
    if [ "$line_count" -eq 0 ]; then
        log_warn "Captured log is empty. The app may not have started yet or LOGCAT_FILTER matches nothing."
        log_warn "Try a larger LOGCAT_SETTLE_SECONDS in $CONFIG_FILE_NAME."
    fi
    log_success "Deployment log saved to $log_file ($line_count lines)"
}

# --- 10b. QNX Log Capture (slog2 / slog2info) ---
capture_logs_qnx() {
    echo ""
    log_info "============================================"
    log_info " QNX Log Capture: slog2 / slog2info"
    log_info "============================================"

    local qnx_log_file="$SCRIPT_DIR/qnx_deployment_log.txt"
    local qnx_host="${QNX_HOST_IP:-${QNX_HOST:-192.168.1.100}}"
    local qnx_port="${QNX_SSH_PORT:-22}"

    log_warn "Target platform is set to 'qnx'."
    log_info "QNX slog2 / slog2info capture workflow template:"
    log_info "  - Tool:         slog2info (QNX System Logger v2)"
    log_info "  - Target Host:  $qnx_host (SSH port: $qnx_port)"
    log_info "  - Output file:  $qnx_log_file"
    log_info "  - Command:      ssh -p $qnx_port root@$qnx_host 'slog2info -t' > $qnx_log_file"
    log_warn "slog2 log capture is currently paused (placeholder for future implementation)."
    # Future execution snippet:
    # ssh -p "$qnx_port" -o ConnectTimeout=5 "root@$qnx_host" "slog2info -t" > "$qnx_log_file" 2>/dev/null || true
    return 0
}

# --- 10. Log Capture Dispatcher ---
capture_logs() {
    local target_platform="${PLATFORM:-${TARGET_PLATFORM:-android}}"
    case "$target_platform" in
        android)
            local deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_ANDROID_DEPLOY:-${ENABLE_DEPLOY:-true}}}"
            local log_enabled="${ENABLE_ANDROID_LOGCAT:-${ENABLE_LOGCAT:-false}}"
            if [ "$deploy_enabled" != "true" ] || [ "$log_enabled" != "true" ]; then
                return 0
            fi
            capture_logs_android
            ;;
        qnx)
            local deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_QNX_DEPLOY:-${ENABLE_DEPLOY:-false}}}"
            local log_enabled="${ENABLE_QNX_LOG:-${ENABLE_LOGCAT:-false}}"
            if [ "$deploy_enabled" != "true" ] || [ "$log_enabled" != "true" ]; then
                return 0
            fi
            capture_logs_qnx
            ;;
        *)
            log_warn "Unknown platform '$target_platform', skipping log capture."
            ;;
    esac
}

# --- Main Entry Point ---
main() {
    parse_early_arguments "$@"
    load_and_validate_config
    parse_arguments "$@"

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

    log_success "All tasks completed successfully."
    exit 0
}

main "$@"