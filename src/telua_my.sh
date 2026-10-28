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
# telua_my.sh - Personal & Workspace-Specific CLI commands for the Telua toolkit.
# Single source of truth for the code behind 'telua my <action>' (alias
# 'telua proj <action>' / 'telua project <action>'), driven by
# const_my_cli.config (MY_CONFIG_FILE):
#   - MY_GROUP_LIST array      : "action :: description" entries
#   - MY_CMD_<ACTION>          : per-action sequential command arrays
#   - (legacy PROJECT_GROUP_LIST / PROJECT_CMD_* also supported for backwards compat)
#
# Functions:
#   - show_project_short_help : one-line-per-action listing (telua my)
#   - show_project_help       : detailed listing with all steps (telua my help)
#   - is_project_action       : predicate used by parse_arguments dispatch
#   - handle_my_command       : resolve + sequentially execute personal action commands
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_my.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       MY_CONFIG_FILE, MY_CONFIG_FILE_NAME, CONFIG_FILE, CONFIG_FILE_NAME,
#       ACTIVE_PROJECT
#   - The host must have sourced const_my_cli.config (or the project config
#     that declares MY_GROUP_LIST / MY_CMD_*) before calling these functions.
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_MY_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_MY_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_MY_SOURCED=1

# --- 1g. Personal & Workspace-Specific CLI Commands (--my / my / --proj / proj) ---
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
            parse_cli_item "$item" grp_name grp_desc
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
            parse_cli_item "$item" grp_name grp_desc

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
            local grp="" grp_desc=""
            parse_cli_item "$item" grp grp_desc
            grp=$(echo "$grp" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
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

handle_my_command() {
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
            parse_cli_item "$item" g_name g_desc
            local g_name_norm
            g_name_norm=$(echo "$g_name" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
            if [ "$g_name_norm" = "$action_normalized" ]; then
                action_label="$g_desc"
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

    execute_command_pipeline "$action_normalized" "$action_label" "${step_cmds[@]}"
}
