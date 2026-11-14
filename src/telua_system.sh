#!/bin/bash
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Contribution History:
#   - 2026-11: Thong Le <letrthong@gmail.com> (System & Docker CLI Pipelines)
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
# telua_system.sh - Executable System & Docker CLI pipelines for the Telua
# toolkit.
# Single source of truth for 'telua system <action>' / 'telua docker <action>',
# driven by config/const_system_cli.config (SYSTEM_GROUP_LIST, SYSTEM_CMD_*).
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_system.sh"

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_SYSTEM_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_SYSTEM_SOURCED=1

show_system_cli_short_help() {
    echo ""
    echo -e "\033[1;32m  telua system <action> (or: telua docker <action>) - System & Docker CLI Pipelines\033[0m"
    echo -e "  System CLI Config: \033[0;33m${SYSTEM_CLI_CONFIG_FILE:-config/const_system_cli.config}\033[0m"
    echo -e "  Docker Cheatsheet: \033[0;36mtelua --docker-help\033[0m"
    echo ""
    if [ -n "${SYSTEM_GROUP_LIST[*]}" ] && [ "${#SYSTEM_GROUP_LIST[@]}" -gt 0 ]; then
        local item grp_name grp_desc
        for item in "${SYSTEM_GROUP_LIST[@]}"; do
            grp_name=""
            grp_desc=""
            parse_cli_item "$item" grp_name grp_desc
            printf "  \033[1;37m%-30s\033[0m %s\n" "telua system $grp_name" "$grp_desc"
        done
    else
        echo -e "  \033[0;90m(No SYSTEM_GROUP_LIST declared in const_system_cli.config)\033[0m"
    fi
    echo ""
    echo -e "  \033[0;90mTip: 'telua system <action>' or 'telua docker <action>' runs the pipeline; 'telua --docker-help' prints the full Docker cheatsheet.\033[0m"
    echo ""
}

is_system_action() {
    local target="$1"
    [ -z "$target" ] && return 1
    if [ -n "${SYSTEM_GROUP_LIST[*]}" ]; then
        local item grp_name grp_desc
        for item in "${SYSTEM_GROUP_LIST[@]}"; do
            grp_name=""
            grp_desc=""
            parse_cli_item "$item" grp_name grp_desc
            if [ "$grp_name" = "$target" ]; then
                return 0
            fi
        done
    fi
    return 1
}

handle_system_command() {
    local action="${1:-}"
    if [ -z "$action" ]; then
        show_system_cli_short_help
        return 0
    fi
    if [ "$action" = "cheatsheet" ] || [ "$action" = "--help" ] || [ "$action" = "-h" ] || [ "$action" = "help" ]; then
        show_system_cli_short_help
        if declare -F show_docker_help >/dev/null 2>&1; then
            show_docker_help
        fi
        return 0
    fi

    local matched_desc=""
    local found=0
    if [ -n "${SYSTEM_GROUP_LIST[*]}" ]; then
        local item grp_name grp_desc
        for item in "${SYSTEM_GROUP_LIST[@]}"; do
            grp_name=""
            grp_desc=""
            parse_cli_item "$item" grp_name grp_desc
            if [ "$grp_name" = "$action" ]; then
                matched_desc="$grp_desc"
                found=1
                break
            fi
        done
    fi

    local upper_key
    upper_key=$(echo "$action" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    local arr_name="SYSTEM_CMD_${upper_key}"
    local arr_ref="${arr_name}[@]"
    local cmds=("${!arr_ref}")

    if [ "$found" -eq 0 ] && [ "${#cmds[@]}" -eq 0 ]; then
        log_error "Unknown System/Docker CLI action: '$action'"
        show_system_cli_short_help
        exit 1
    fi

    if [ "${#cmds[@]}" -eq 0 ]; then
        log_error "Action '$action' is listed in SYSTEM_GROUP_LIST, but array '$arr_name' is empty or not defined in $SYSTEM_CLI_CONFIG_FILE"
        exit 1
    fi

    execute_command_pipeline "$action" "$matched_desc" "SYSTEM/DOCKER CLI PIPELINE" "${cmds[@]}"
}

