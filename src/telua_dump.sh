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
# telua_dump.sh - Dumpsys diagnostics commands for the Telua toolkit.
# Single source of truth for the code behind 'telua dump <target>', driven by
# const_dumpsys.config (DUMP_CONFIG_FILE):
#   - DUMP_CLI_LIST array     : "action :: description :: adb command" entries
#   - ADB_SHELL_DUMP_<ACTION> : per-target dumpsys command variables
#
# Functions:
#   - show_dump_short_help      : one-line-per-target listing (telua dump)
#   - show_dump_help            : detailed listing with ADB commands (telua dump help)
#   - check_dump_device_connected : verify device is connected and online
#   - is_dump_action            : predicate used by parse_arguments dispatch
#   - handle_dump_command       : resolve + execute the dumpsys ADB shell command
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_dump.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       DUMP_CONFIG_FILE, DUMP_CONFIG_FILE_NAME, CONFIG_FILE, CONFIG_FILE_NAME
#   - The host must have sourced const_dumpsys.config (or the project config
#     that declares DUMP_CLI_LIST / ADB_SHELL_DUMP_*) before calling these
#     functions.
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_DUMP_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_DUMP_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_DUMP_SOURCED=1

# --- 1d. Dumpsys Diagnostics Commands (--dump / dump) ---
# Short one-line-per-target listing (shown by: telua dump)
show_dump_short_help() {
    echo ""
    echo -e "\033[1;32m  telua dump <target> - Dumpsys diagnostics via ADB Shell\033[0m"
    echo -e "  Dump Config File:  \033[0;33m$DUMP_CONFIG_FILE\033[0m"
    echo ""
    if [ -n "${DUMP_CLI_LIST[*]}" ] && [ "${#DUMP_CLI_LIST[@]}" -gt 0 ]; then
        for item in "${DUMP_CLI_LIST[@]}"; do
            local item_action="" item_desc=""
            parse_cli_item "$item" item_action item_desc
            printf "  \033[1;37m%-26s\033[0m %s\n" "telua dump $item_action" "$item_desc"
        done
    else
        echo -e "  \033[0;90m(DUMP_CLI_LIST not declared in $DUMP_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi
    echo ""
    echo -e "  \033[0;90mTip: 'telua dump help' (or --help / -h) shows detailed ADB commands.\033[0m"
    echo ""
}

# Detailed listing with ADB command per target (shown by: telua dump help)
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
            parse_cli_item "$item" item_action item_desc item_cmd

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

# Verify device is connected & ready before running dump commands.
check_dump_device_connected() {
    check_adb_device_online
}

is_dump_action() {
    local target="$1"
    target=$(echo "$target" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    if [ -n "${DUMP_CLI_LIST[*]}" ]; then
        for item in "${DUMP_CLI_LIST[@]}"; do
            local act="" act_desc=""
            parse_cli_item "$item" act act_desc
            act=$(echo "$act" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
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

    if [ -z "$action" ]; then
        show_dump_short_help
        return 0
    fi

    if [ "$action" = "help" ] || [ "$action" = "--help" ] || [ "$action" = "-h" ]; then
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
            parse_cli_item "$item" it_action it_desc it_cmd
            local it_action_norm
            it_action_norm=$(echo "$it_action" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
            if [ "$it_action_norm" = "$action_normalized" ]; then
                action_label="$it_desc"
                adb_cmd="$it_cmd"
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

    # Verify device state before executing
    if ! check_dump_device_connected; then
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
