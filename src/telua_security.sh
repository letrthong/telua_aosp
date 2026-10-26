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
# telua_security.sh - Security, SELinux & Diagnostics commands for the Telua toolkit.
# Single source of truth for the code behind 'telua sec <action>' (alias
# 'telua security <action>'), driven by const_security.config (SECURITY_CONFIG_FILE):
#   - SECURITY_CLI_LIST array       : "action :: description :: command" entries
#   - ADB_SHELL_SEC_<ACTION>        : per-action security command variables
#   - ADB_SEC_<ACTION>              : host-level adb commands (e.g. adb root)
#
# Functions:
#   - show_security_short_help        : one-line-per-action listing (telua sec)
#   - show_security_help              : detailed listing with commands (telua sec help)
#   - is_security_action              : predicate used by parse_arguments dispatch
#   - check_security_device_connected : verify target device is connected & online
#   - handle_security_command         : resolve + execute the security command
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_security.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SECURITY_CONFIG_FILE, SECURITY_CONFIG_FILE_NAME, CONFIG_FILE, CONFIG_FILE_NAME
#   - The host must have sourced const_security.config (or the project config that
#     declares SECURITY_CLI_LIST) before calling these functions.
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_SECURITY_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_SECURITY_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_SECURITY_SOURCED=1

# --- Security Diagnostics & Control Commands (--sec / sec / security) ---

# Short one-line-per-action listing (shown by: telua sec)
show_security_short_help() {
    echo ""
    echo -e "\033[1;32m  telua sec <action> - Security, SELinux & Diagnostics Control\033[0m"
    echo -e "  Security Config File: \033[0;33m$SECURITY_CONFIG_FILE\033[0m"
    echo ""
    if [ -n "${SECURITY_CLI_LIST[*]}" ] && [ "${#SECURITY_CLI_LIST[@]}" -gt 0 ]; then
        for item in "${SECURITY_CLI_LIST[@]}"; do
            local item_action="" item_desc=""
            if [[ "$item" == *" :: "* ]]; then
                item_action="${item%% :: *}"
                local item_rest="${item#* :: }"
                item_desc="${item_rest%% :: *}"
            elif [[ "$item" == *"|"* ]]; then
                item_action="$(echo "$item" | cut -d'|' -f1)"
                item_desc="$(echo "$item" | cut -d'|' -f2)"
            else
                item_action="$item"
                item_desc=""
            fi
            item_action="$(echo "$item_action" | xargs)"
            item_desc="$(echo "$item_desc" | xargs)"
            printf "    \033[1;36m%-16s\033[0m %s\n" "$item_action" "$item_desc"
        done
    else
        echo -e "  \033[0;90m(SECURITY_CLI_LIST not declared in $SECURITY_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi
    echo ""
    echo -e "  Run \033[1;33mtelua sec help\033[0m to view full command strings and usage tips."
    echo ""
}

# Detailed help listing with exact command strings (shown by: telua sec help)
show_security_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m TELUA SECURITY & SELINUX COMMANDS HELP\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "  Usage: \033[1;33mtelua sec <action>\033[0m  (or: \033[1;33mtelua security <action>\033[0m)"
    echo -e "  Security Config File: \033[0;33m$SECURITY_CONFIG_FILE\033[0m"
    echo ""
    echo -e "\033[1;33mSUPPORTED SECURITY ACTIONS:\033[0m"
    if [ -n "${SECURITY_CLI_LIST[*]}" ] && [ "${#SECURITY_CLI_LIST[@]}" -gt 0 ]; then
        for item in "${SECURITY_CLI_LIST[@]}"; do
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
                item_desc=""
                item_cmd=""
            fi
            item_action="$(echo "$item_action" | xargs)"
            item_desc="$(echo "$item_desc" | xargs)"
            item_cmd="$(echo "$item_cmd" | xargs)"
            printf "  \033[1;36m%-16s\033[0m %s\n" "$item_action" "$item_desc"
            if [ -n "$item_cmd" ]; then
                echo -e "    \033[0;90mCommand: $item_cmd\033[0m"
            fi
        done
    else
        echo -e "  \033[0;90m(SECURITY_CLI_LIST not declared in $SECURITY_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

# Predicate: return 0 if the given argument is a known security action
is_security_action() {
    local target="$1"
    [ -z "$target" ] && return 1

    target=$(echo "$target" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    # Support aliases
    [ "$target" = "permissive" ] && target="perm"
    [ "$target" = "enforcing" ] && target="enforce"
    [ "$target" = "denials" ] && target="avc"
    [ "$target" = "info" ] && target="status"

    if [ -n "${SECURITY_CLI_LIST[*]}" ]; then
        for item in "${SECURITY_CLI_LIST[@]}"; do
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
    local v="ADB_SHELL_SEC_${suf}"
    local v_host="ADB_SEC_${suf}"
    if [ -n "${!v}" ] || [ -n "${!v_host}" ]; then
        return 0
    fi
    return 1
}

# Verify Android device is connected and online before executing security commands
check_security_device_connected() {
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
    return 0
}

# Dispatch & execute the security command
handle_security_command() {
    local action="$1"

    if [ -z "$action" ]; then
        show_security_short_help
        return 0
    fi

    if [ "$action" = "help" ] || [ "$action" = "--help" ] || [ "$action" = "-h" ]; then
        show_security_help
        return 0
    fi

    local action_normalized
    action_normalized=$(echo "$action" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    # Support aliases
    [ "$action_normalized" = "permissive" ] && action_normalized="perm"
    [ "$action_normalized" = "enforcing" ] && action_normalized="enforce"
    [ "$action_normalized" = "denials" ] && action_normalized="avc"
    [ "$action_normalized" = "info" ] && action_normalized="status"

    local exec_cmd=""
    local action_label=""

    # 1. Search in SECURITY_CLI_LIST
    if [ -n "${SECURITY_CLI_LIST[*]}" ]; then
        for item in "${SECURITY_CLI_LIST[@]}"; do
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
                exec_cmd="$(echo "$it_cmd" | xargs)"
                break
            fi
        done
    fi

    # 2. Check variable conventions if not matched in list
    if [ -z "$exec_cmd" ]; then
        local var_suffix
        var_suffix=$(echo "$action_normalized" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
        local var_sec="ADB_SHELL_SEC_${var_suffix}"
        local var_host="ADB_SEC_${var_suffix}"

        if [ -n "${!var_sec}" ]; then
            action_label="Security ($action)"
            exec_cmd="${!var_sec}"
        elif [ -n "${!var_host}" ]; then
            action_label="ADB Security ($action)"
            exec_cmd="${!var_host}"
        fi
    fi

    # 3. Not found -> report error and show help
    if [ -z "$exec_cmd" ]; then
        log_error "Unknown security action '$action'!"
        log_error "Supported actions: status | perm | enforce | avc | privapp | appops | keystore | policy | root | unroot | remount | disable-verity"
        show_security_help
        exit 1
    fi

    # Check device online
    if ! check_security_device_connected; then
        exit 1
    fi

    log_info "Executing security action: $action_label..."

    # Determine whether it's a host-level adb command or an adb shell command
    local ret=0
    if [[ "$exec_cmd" =~ ^adb[[:space:]] ]]; then
        echo -e "  \033[1;36m[CMD]\033[0m $exec_cmd"
        eval "$exec_cmd"
        ret=$?
    else
        echo -e "  \033[1;36m[ADB CMD]\033[0m adb shell $exec_cmd"
        adb shell "$exec_cmd"
        ret=$?
    fi

    if [ $ret -eq 0 ]; then
        log_success "$action_label completed successfully."
    else
        log_error "Failed to execute '$action_label' (exit code: $ret)."
        exit $ret
    fi
}
