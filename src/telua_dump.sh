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
#   - DUMP_GROUP_LIST array   : "target :: description" entries (Multi-CLI)
#   - DUMP_CMD_<TARGET> array : sequential command steps per target
#   - DUMP_CLI_LIST array     : legacy "action :: description :: adb command" entries
#   - ADB_SHELL_DUMP_<ACTION> : legacy per-target dumpsys command variables
#
# Functions:
#   - show_dump_short_help      : one-line-per-target listing (telua dump)
#   - show_dump_help            : detailed listing with commands/steps (telua dump help)
#   - check_dump_device_connected : verify device is connected and online
#   - is_dump_action            : predicate used by parse_arguments dispatch
#   - handle_dump_command       : resolve + execute dumpsys multi-cli steps or ADB shell command
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_dump.sh"
#
# Guarded by TELUA_DUMP_SOURCED so double-sourcing is a no-op.

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
    if [ -n "${DUMP_GROUP_LIST[*]}" ] && [ "${#DUMP_GROUP_LIST[@]}" -gt 0 ]; then
        for item in "${DUMP_GROUP_LIST[@]}"; do
            local item_action="" item_desc=""
            parse_cli_item "$item" item_action item_desc
            printf "  \033[1;37m%-26s\033[0m %s\n" "telua dump $item_action" "$item_desc"
        done
    elif [ -n "${DUMP_CLI_LIST[*]}" ] && [ "${#DUMP_CLI_LIST[@]}" -gt 0 ]; then
        for item in "${DUMP_CLI_LIST[@]}"; do
            local item_action="" item_desc=""
            parse_cli_item "$item" item_action item_desc
            printf "  \033[1;37m%-26s\033[0m %s\n" "telua dump $item_action" "$item_desc"
        done
    else
        echo -e "  \033[0;90m(No DUMP_GROUP_LIST or DUMP_CLI_LIST declared in $DUMP_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi
    echo ""
    echo -e "  \033[0;90mTip: 'telua dump help' (or --help / -h) shows detailed command steps.\033[0m"
    echo ""
}

# Detailed listing with command steps per target (shown by: telua dump help)
show_dump_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  telua dump - Dumpsys Diagnostics Multi-CLI Pipelines\033[0m"
    echo -e "  Config File:       \033[0;33m$CONFIG_FILE\033[0m"
    echo -e "  Dump Config File:  \033[0;33m$DUMP_CONFIG_FILE\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
    echo -e "\033[1;33mSUPPORTED DUMP TARGETS & PIPELINES:\033[0m"

    if [ -n "${DUMP_GROUP_LIST[*]}" ] && [ "${#DUMP_GROUP_LIST[@]}" -gt 0 ]; then
        local idx=1
        for item in "${DUMP_GROUP_LIST[@]}"; do
            local item_action="" item_desc=""
            parse_cli_item "$item" item_action item_desc

            local var_suffix
            var_suffix=$(echo "$item_action" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
            local array_name="DUMP_CMD_${var_suffix}"
            local -a steps=()
            if declare -p "$array_name" >/dev/null 2>&1; then
                eval "steps=(\"\${${array_name}[@]}\")"
            fi

            echo -e "  \033[1;32m$idx.\033[0m \033[1;37mtelua dump $item_action\033[0m"
            echo -e "     \033[0;90mDescription:\033[0m  $item_desc"
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
    elif [ -n "${DUMP_CLI_LIST[*]}" ] && [ "${#DUMP_CLI_LIST[@]}" -gt 0 ]; then
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
        echo -e "  \033[0;90m(No DUMP_GROUP_LIST or DUMP_CLI_LIST declared in $DUMP_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi

    # Check for any dynamic ADB_SHELL_DUMP_* variables
    local has_dynamic_vars=0
    for var_name in ${!ADB_SHELL_DUMP_@}; do
        if [ "$has_dynamic_vars" -eq 0 ]; then
            echo -e "\033[1;36m--------------------------------------------------------------------------------\033[0m"
            echo -e "\033[1;33mADB_SHELL_DUMP_* CONFIG VARIABLES ($DUMP_CONFIG_FILE_NAME):\033[0m"
        fi
        echo -e "  \033[1;35m$var_name\033[0m = \"\033[0;32m${!var_name}\033[0m\""
        has_dynamic_vars=1
    done

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

    if [ -n "${DUMP_GROUP_LIST[*]}" ]; then
        for item in "${DUMP_GROUP_LIST[@]}"; do
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
    local array_name="DUMP_CMD_${suf}"
    if declare -p "$array_name" >/dev/null 2>&1; then
        return 0
    fi

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

    local action_label=""
    local -a step_cmds=()

    # 1. Tìm action trong DUMP_GROUP_LIST
    if [ -n "${DUMP_GROUP_LIST[*]}" ]; then
        for item in "${DUMP_GROUP_LIST[@]}"; do
            local it_action="" it_desc=""
            parse_cli_item "$item" it_action it_desc
            local it_action_norm
            it_action_norm=$(echo "$it_action" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
            if [ "$it_action_norm" = "$action_normalized" ]; then
                action_label="$it_desc"
                break
            fi
        done
    fi

    # 2. Tìm mảng multi-cli DUMP_CMD_<TARGET>
    local var_suffix
    var_suffix=$(echo "$action_normalized" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    local array_name="DUMP_CMD_${var_suffix}"
    if declare -p "$array_name" >/dev/null 2>&1; then
        eval "step_cmds=(\"\${${array_name}[@]}\")"
    fi

    # 3. Nếu có step_cmds từ mảng multi-cli, chạy tuần tự qua execute_command_pipeline
    if [ "${#step_cmds[@]}" -gt 0 ]; then
        [ -z "$action_label" ] && action_label="Dump ($action)"
        execute_command_pipeline "$action_normalized" "$action_label" "${step_cmds[@]}"
        return $?
    fi

    # 4. Fallback: DUMP_CLI_LIST (Single CLI legacy)
    local adb_cmd=""
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

    # 5. Fallback: ADB_SHELL_DUMP_<ACTION>
    if [ -z "$adb_cmd" ]; then
        local var_dump="ADB_SHELL_DUMP_${var_suffix}"
        if [ -n "${!var_dump}" ]; then
            action_label="Dump ($action)"
            adb_cmd="${!var_dump}"
        fi
    fi

    # 6. Nếu không tìm thấy
    if [ -z "$adb_cmd" ]; then
        log_error "Unknown dump target '$action'!"
        log_error "Supported targets: run 'telua dump' to list available diagnostics"
        show_dump_help
        exit 1
    fi

    # Verify device state before executing single adb command
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
