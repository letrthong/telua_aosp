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
# telua_run.sh - Sequential Multi-CLI pipeline runner for the Telua toolkit.
# Single source of truth for the code behind 'telua run <group>' (alias
# 'telua multi <group>'), driven by const_multi_cli.config (MULTI_CONFIG_FILE):
#   - MULTI_GROUP_LIST array : "group :: description" entries
#   - MULTI_CMD_<GROUP>      : per-group sequential command arrays
#
# Functions:
#   - show_run_short_help : one-line-per-group listing (telua run)
#   - show_run_help       : detailed listing with all steps (telua run help)
#   - is_run_group        : predicate used by parse_arguments dispatch
#   - handle_run_command  : resolve + sequentially execute the group commands
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_run.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       MULTI_CONFIG_FILE, MULTI_CONFIG_FILE_NAME, CONFIG_FILE, CONFIG_FILE_NAME
#   - The host must have sourced const_multi_cli.config (or the project config
#     that declares MULTI_GROUP_LIST / MULTI_CMD_*) before calling these
#     functions.
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_RUN_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_RUN_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_RUN_SOURCED=1

# --- 1f. Multi-CLI Command Pipelines (--run / run / --multi / multi) ---
# Short one-line-per-group listing (shown by: telua run)
show_run_short_help() {
    echo ""
    echo -e "\033[1;32m  telua run <group> - Multi-CLI Pipelines\033[0m"
    echo -e "  Pipeline Config:   \033[0;33m$MULTI_CONFIG_FILE\033[0m"
    echo ""
    if [ -n "${MULTI_GROUP_LIST[*]}" ] && [ "${#MULTI_GROUP_LIST[@]}" -gt 0 ]; then
        for item in "${MULTI_GROUP_LIST[@]}"; do
            local grp_name="" grp_desc=""
            parse_cli_item "$item" grp_name grp_desc
            printf "  \033[1;37m%-30s\033[0m %s\n" "telua run $grp_name" "$grp_desc"
        done
    else
        echo -e "  \033[0;90m(No MULTI_GROUP_LIST declared in $MULTI_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi
    echo ""
    echo -e "  \033[0;90mTip: 'telua run help' (or --help / -h) shows detailed steps for each group.\033[0m"
    echo ""
}

# Detailed listing with every step of every group (shown by: telua run help)
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
            parse_cli_item "$item" grp_name grp_desc

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
    local array_name="MULTI_CMD_${suf}"
    if declare -p "$array_name" >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

handle_run_command() {
    local group="$1"

    if [ -z "$group" ]; then
        show_run_short_help
        return 0
    fi

    if [ "$group" = "help" ] || [ "$group" = "--help" ] || [ "$group" = "-h" ]; then
        show_run_help
        return 0
    fi

    local group_normalized
    group_normalized=$(echo "$group" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    local group_label=""
    if [ -n "${MULTI_GROUP_LIST[*]}" ]; then
        for item in "${MULTI_GROUP_LIST[@]}"; do
            local g_name="" g_desc=""
            parse_cli_item "$item" g_name g_desc
            local g_name_norm
            g_name_norm=$(echo "$g_name" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
            if [ "$g_name_norm" = "$group_normalized" ]; then
                group_label="$g_desc"
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

    execute_command_pipeline "$group_normalized" "$group_label" "${step_cmds[@]}"
}
