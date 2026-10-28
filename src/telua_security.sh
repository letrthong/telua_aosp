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
            parse_cli_item "$item" item_action item_desc
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
            parse_cli_item "$item" item_action item_desc item_cmd

            local var_suffix
            var_suffix=$(echo "$item_action" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
            local sec_array_name="SEC_CMD_${var_suffix}"
            local adb_sec_array_name="ADB_SEC_${var_suffix}"
            local is_array=0
            local -a array_steps=()

            if declare -p "$sec_array_name" 2>/dev/null | grep -q 'declare -a'; then
                eval "array_steps=(\"\${${sec_array_name}[@]}\")"
                is_array=1
            elif declare -p "$adb_sec_array_name" 2>/dev/null | grep -q 'declare -a'; then
                eval "array_steps=(\"\${${adb_sec_array_name}[@]}\")"
                is_array=1
            elif [ -n "$item_cmd" ] && declare -p "$item_cmd" 2>/dev/null | grep -q 'declare -a'; then
                eval "array_steps=(\"\${${item_cmd}[@]}\")"
                is_array=1
            fi

            if [ "$is_array" -eq 1 ] && [ "${#array_steps[@]}" -gt 0 ]; then
                printf "  \033[1;36m%-16s\033[0m %s \033[0;90m(%d sequential steps)\033[0m\n" "$item_action" "$item_desc" "${#array_steps[@]}"
                local s_idx=1
                for s in "${array_steps[@]}"; do
                    echo -e "    \033[0;33mStep $s_idx:\033[0m \033[0;37m$s\033[0m"
                    s_idx=$((s_idx + 1))
                done
            else
                printf "  \033[1;36m%-16s\033[0m %s\n" "$item_action" "$item_desc"
                if [ -n "$item_cmd" ]; then
                    echo -e "    \033[0;90mCommand: $item_cmd\033[0m"
                fi
            fi
        done
    else
        echo -e "  \033[0;90m(SECURITY_CLI_LIST not declared in $SECURITY_CONFIG_FILE_NAME or $CONFIG_FILE_NAME)\033[0m"
    fi
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

# Print one aligned audit row: "    <label> ....... <value>"
# Color codes: g=green, y=yellow, r=red, d=dim, (empty)=default
_sec_audit_row() {
    local label="$1" value="$2" color="${3:-}"
    local width=24
    local pad=$((width - ${#label}))
    [ "$pad" -lt 2 ] && pad=2
    local dots
    dots=$(printf '%*s' "$pad" '' | tr ' ' '.')
    case "$color" in
        g) printf "    %s \033[0;90m%s\033[0m \033[0;32m%s\033[0m\n" "$label" "$dots" "$value" ;;
        y) printf "    %s \033[0;90m%s\033[0m \033[1;33m%s\033[0m\n" "$label" "$dots" "$value" ;;
        r) printf "    %s \033[0;90m%s\033[0m \033[1;31m%s\033[0m\n" "$label" "$dots" "$value" ;;
        d) printf "    %s \033[0;90m%s\033[0m \033[0;90m%s\033[0m\n" "$label" "$dots" "$value" ;;
        *) printf "    %s \033[0;90m%s\033[0m %s\n" "$label" "$dots" "$value" ;;
    esac
}

# Print a section title inside the host audit report
_sec_audit_section() {
    echo -e "\n  \033[1;33m$1\033[0m"
}

# --- Host Linux Security Environment Check (telua sec host / sec env) ---
check_host_linux_security() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  TELUA TOOLKIT — LINUX HOST SECURITY & ENVIRONMENT AUDIT\033[0m"
    echo -e "  Host: \033[1;33m$(hostname 2>/dev/null || echo "localhost")\033[0m | Date: \033[0;37m$(date 2>/dev/null || echo "N/A")\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"

    # --- Operating System & Kernel ---
    _sec_audit_section "OS & Kernel"
    local os_desc="Unknown Linux"
    if [ -f /etc/os-release ]; then
        os_desc=$(grep -E '^PRETTY_NAME=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
    elif command -v lsb_release >/dev/null 2>&1; then
        os_desc=$(lsb_release -ds 2>/dev/null)
    fi
    _sec_audit_row "Operating System" "$os_desc"
    _sec_audit_row "Kernel Version" "$(uname -srm 2>/dev/null || uname -a)"
    if [ -f /proc/version ]; then
        local gcc_ver
        gcc_ver=$(grep -oE 'gcc version [^ )]+' /proc/version | head -n1)
        [ -n "$gcc_ver" ] && _sec_audit_row "Kernel Toolchain" "$gcc_ver" d
    fi

    # --- Security Modules (LSM) ---
    _sec_audit_section "Security Modules (LSM)"
    local lsm_found=0
    if command -v aa-status >/dev/null 2>&1; then
        if aa-status --enabled 2>/dev/null; then
            local aa_profiles
            aa_profiles=$(aa-status 2>/dev/null | grep -E 'profiles are in enforce mode' | head -n1 | xargs || echo "active")
            _sec_audit_row "AppArmor" "enabled (${aa_profiles:-active})" g
            lsm_found=1
        fi
    elif [ -d /sys/kernel/security/apparmor ]; then
        _sec_audit_row "AppArmor" "loaded (/sys/kernel/security/apparmor)" g
        lsm_found=1
    fi

    if command -v getenforce >/dev/null 2>&1; then
        local host_se
        host_se=$(getenforce 2>/dev/null || echo "Disabled")
        case "$host_se" in
            Enforcing)  _sec_audit_row "Host SELinux" "Enforcing" g ;;
            Permissive) _sec_audit_row "Host SELinux" "Permissive" y ;;
            *)          _sec_audit_row "Host SELinux" "$host_se" d ;;
        esac
        lsm_found=1
    fi
    if [ "$lsm_found" -eq 0 ]; then
        _sec_audit_row "AppArmor / SELinux" "no active module detected" d
    fi

    # --- User Identity & Privileges ---
    _sec_audit_section "User & Privileges"
    local cur_uid
    cur_uid=$(id -u 2>/dev/null || echo "1000")
    local cur_user
    cur_user=$(id -un 2>/dev/null || echo "user")
    if [ "$cur_uid" -eq 0 ]; then
        _sec_audit_row "Current User" "root (UID 0) — run AOSP builds as a regular user!" r
    else
        _sec_audit_row "Current User" "$cur_user (UID: $cur_uid, GID: $(id -g 2>/dev/null))"
    fi
    local groups_str
    groups_str=$(id -Gn 2>/dev/null || groups 2>/dev/null || echo "")
    groups_str=$(echo "$groups_str" | tr '\r\n' ' ' | xargs)
    _sec_audit_row "User Groups" "$groups_str" d
    if echo "$groups_str" | grep -qwE '(sudo|wheel|admin)'; then
        _sec_audit_row "Admin Membership" "sudo/wheel group present" g
    else
        _sec_audit_row "Admin Membership" "not in standard sudo/wheel group" d
    fi

    # --- System Resource Limits (ulimit) for AOSP Build ---
    _sec_audit_section "Resource Limits (ulimit)"
    local nofile_limit
    nofile_limit=$(ulimit -n 2>/dev/null || echo "1024")
    if [ "$nofile_limit" = "unlimited" ] || [ "$nofile_limit" -ge 4096 ]; then
        _sec_audit_row "Max open files" "$nofile_limit (optimal for AOSP Ninja/Soong)" g
    elif [ "$nofile_limit" -ge 2048 ]; then
        _sec_audit_row "Max open files" "$nofile_limit (recommend >= 4096 via limits.conf)" y
    else
        _sec_audit_row "Max open files" "$nofile_limit (too low, may break builds!)" r
    fi
    _sec_audit_row "Max user processes" "$(ulimit -u 2>/dev/null || echo "unlimited")"
    _sec_audit_row "Stack size" "$(ulimit -s 2>/dev/null || echo "unlimited")"

    # --- Filesystem & Temporary Directory ---
    _sec_audit_section "Filesystem & /tmp"
    local tmp_mount
    tmp_mount=$(mount 2>/dev/null | grep -E '[[:space:]]/tmp[[:space:]]' || true)
    if [ -n "$tmp_mount" ]; then
        if echo "$tmp_mount" | grep -qw "noexec"; then
            _sec_audit_row "/tmp mount" "noexec set — build scripts in /tmp will fail!" r
        else
            _sec_audit_row "/tmp mount" "isolated mount, executables allowed" g
        fi
    else
        _sec_audit_row "/tmp mount" "part of root filesystem (no restrictions)" g
    fi
    local ws_disk
    ws_disk=$(df -h . 2>/dev/null | tail -n1 | awk '{print $4 " available (" $5 " used on " $1 ")"}')
    [ -n "$ws_disk" ] && _sec_audit_row "Workspace disk" "$ws_disk"

    # --- Network & Firewall ---
    _sec_audit_section "Network & Firewall"
    if command -v ufw >/dev/null 2>&1; then
        local ufw_status
        ufw_status=$(sudo -n ufw status 2>/dev/null || echo "unprivileged")
        if echo "$ufw_status" | grep -qi "active"; then
            _sec_audit_row "UFW Firewall" "active" g
        elif [ "$ufw_status" = "unprivileged" ]; then
            _sec_audit_row "UFW Firewall" "installed (sudo needed to read status)" d
        else
            _sec_audit_row "UFW Firewall" "inactive" y
        fi
    else
        _sec_audit_row "UFW Firewall" "not installed" d
    fi
    local open_ports_count=0
    if command -v ss >/dev/null 2>&1; then
        open_ports_count=$(ss -tulpn 2>/dev/null | grep -E '^tcp|^udp' | wc -l || echo 0)
    elif command -v netstat >/dev/null 2>&1; then
        open_ports_count=$(netstat -tulpn 2>/dev/null | grep -E '^tcp|^udp' | wc -l || echo 0)
    fi
    _sec_audit_row "Listening sockets" "$open_ports_count"

    # --- Developer Security & Key Hygiene ---
    _sec_audit_section "Developer Hygiene"
    local git_name git_email
    git_name=$(git config --get user.name 2>/dev/null || echo "")
    git_email=$(git config --get user.email 2>/dev/null || echo "")
    if [ -n "$git_name" ] && [ -n "$git_email" ]; then
        _sec_audit_row "Git identity" "$git_name <$git_email>" g
    else
        _sec_audit_row "Git identity" "user.name / user.email not set globally!" y
    fi

    local ssh_dir="$HOME/.ssh"
    if [ -d "$ssh_dir" ]; then
        local ssh_perm
        ssh_perm=$(stat -c "%a" "$ssh_dir" 2>/dev/null || stat -f "%Op" "$ssh_dir" 2>/dev/null || echo "")
        if [ -n "$ssh_perm" ] && [[ "$ssh_perm" =~ 700$ ]]; then
            _sec_audit_row "~/.ssh permissions" "$ssh_perm (secure owner-only)" g
        elif [ -n "$ssh_perm" ]; then
            _sec_audit_row "~/.ssh permissions" "$ssh_perm (recommend chmod 700)" y
        fi
    else
        _sec_audit_row "~/.ssh" "no directory found" d
    fi

    local py_cmd=""
    for candidate in python3 python py; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c "import sys" >/dev/null 2>&1; then
                py_cmd="$candidate"
                break
            fi
        fi
    done
    if [ -n "$py_cmd" ]; then
        local py_version
        py_version=$("$py_cmd" --version 2>&1)
        if "$py_cmd" -c "import cryptography" >/dev/null 2>&1; then
            _sec_audit_row "Python" "$py_version + cryptography module" g
        else
            _sec_audit_row "Python" "$py_version (cryptography missing — run: telua init)" y
        fi
    else
        _sec_audit_row "Python" "python3 not found in PATH!" r
    fi

    echo -e "\n\033[1;36m================================================================================\033[0m"
    log_success "Host Linux security & environment audit completed."
    echo ""
    return 0
}

# Predicate: return 0 if the given argument is a known security action
is_security_action() {
    local target="$1"
    [ -z "$target" ] && return 1

    target=$(echo "$target" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    # Support aliases
    [ "$target" = "host" ] && return 0
    [ "$target" = "env" ] && return 0
    [ "$target" = "linux" ] && return 0
    [ "$target" = "check-host" ] && return 0
    [ "$target" = "permissive" ] && target="perm"
    [ "$target" = "enforcing" ] && target="enforce"
    [ "$target" = "denials" ] && target="avc"
    [ "$target" = "info" ] && target="status"

    if [ -n "${SECURITY_CLI_LIST[*]}" ]; then
        for item in "${SECURITY_CLI_LIST[@]}"; do
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
    local v_arr="SEC_CMD_${suf}"
    local v_host_arr="ADB_SEC_${suf}"
    local v="ADB_SHELL_SEC_${suf}"
    local v_host="ADB_SEC_${suf}"
    if declare -p "$v_arr" >/dev/null 2>&1 || declare -p "$v_host_arr" >/dev/null 2>&1 || [ -n "${!v}" ] || [ -n "${!v_host}" ]; then
        return 0
    fi
    return 1
}

# Verify Android device is connected and online before executing security commands
check_security_device_connected() {
    check_adb_device_online
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

    # Host-level Linux Security & Environment check (does not require Android device)
    if [ "$action_normalized" = "host" ] || [ "$action_normalized" = "env" ] || [ "$action_normalized" = "linux" ] || [ "$action_normalized" = "check-host" ]; then
        check_host_linux_security
        exit 0
    fi

    # Support aliases
    [ "$action_normalized" = "permissive" ] && action_normalized="perm"
    [ "$action_normalized" = "enforcing" ] && action_normalized="enforce"
    [ "$action_normalized" = "denials" ] && action_normalized="avc"
    [ "$action_normalized" = "info" ] && action_normalized="status"

    local exec_cmd=""
    local action_label=""
    local is_array=0
    local -a step_cmds=()

    # 1. Check if defined as a multi-command array: SEC_CMD_<ACTION> or ADB_SEC_<ACTION>
    local var_suffix
    var_suffix=$(echo "$action_normalized" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
    local sec_array_name="SEC_CMD_${var_suffix}"
    local adb_sec_array_name="ADB_SEC_${var_suffix}"

    if declare -p "$sec_array_name" 2>/dev/null | grep -q 'declare -a'; then
        eval "step_cmds=(\"\${${sec_array_name}[@]}\")"
        is_array=1
    elif declare -p "$adb_sec_array_name" 2>/dev/null | grep -q 'declare -a'; then
        eval "step_cmds=(\"\${${adb_sec_array_name}[@]}\")"
        is_array=1
    fi

    # 2. Search in SECURITY_CLI_LIST
    if [ -n "${SECURITY_CLI_LIST[*]}" ]; then
        for item in "${SECURITY_CLI_LIST[@]}"; do
            local it_action="" it_desc="" it_cmd=""
            parse_cli_item "$item" it_action it_desc it_cmd
            local it_action_norm
            it_action_norm=$(echo "$it_action" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
            if [ "$it_action_norm" = "$action_normalized" ]; then
                action_label="$it_desc"
                if [ -n "$it_cmd" ] && declare -p "$it_cmd" 2>/dev/null | grep -q 'declare -a'; then
                    eval "step_cmds=(\"\${${it_cmd}[@]}\")"
                    is_array=1
                elif [ "$is_array" -eq 0 ] && [ -n "$it_cmd" ]; then
                    exec_cmd="$it_cmd"
                fi
                break
            fi
        done
    fi

    # 3. Check variable conventions if not matched as array or in list
    if [ "$is_array" -eq 0 ] && [ -z "$exec_cmd" ]; then
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

    # 4. Not found -> report error and show help
    if [ "$is_array" -eq 0 ] && [ -z "$exec_cmd" ]; then
        log_error "Unknown security action '$action'!"
        log_error "Supported actions: host | status | perm | enforce | avc | privapp | appops | keystore | policy | root | unroot | remount | disable-verity | enable-verity"
        show_security_help
        exit 1
    fi

    # Check device online
    if ! check_security_device_connected; then
        exit 1
    fi

    # Case A: Execute multi-command sequential pipeline array
    if [ "$is_array" -eq 1 ] && [ "${#step_cmds[@]}" -gt 0 ]; then
        execute_command_pipeline "$action_normalized" "$action_label" "${step_cmds[@]}"
        exit 0
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
