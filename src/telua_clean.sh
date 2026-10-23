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
# telua_clean.sh - Java source hygiene for the Telua toolkit.
# Single source of truth for 'telua clean-java [target]', driving python/clean_java.py.
#
# Functions:
#   - show_clean_short_help
#   - show_clean_help
#   - is_clean_action
#   - handle_clean_command
#
# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_CLEAN_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_CLEAN_SOURCED=1

CLEAN_JAVA_PY_NAME="python/clean_java.py"

resolve_clean_java_script() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [ -f "$script_dir/$CLEAN_JAVA_PY_NAME" ]; then
        echo "$script_dir/$CLEAN_JAVA_PY_NAME"
        return 0
    fi
    if [ -n "${MASTER_SCRIPT_DIR:-}" ] && [ -f "$MASTER_SCRIPT_DIR/$CLEAN_JAVA_PY_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$CLEAN_JAVA_PY_NAME"
        return 0
    fi
    if [ -f "$CLEAN_JAVA_PY_NAME" ]; then
        echo "$CLEAN_JAVA_PY_NAME"
        return 0
    fi
    return 1
}

show_clean_short_help() {
    echo ""
    echo -e "\033[1;32m  telua clean-java [target] - Clean trailing whitespace in Java source files\033[0m"
    echo "  Modes:"
    echo "    telua clean-java diff       Clean Git-modified or added .java files (default)"
    echo "    telua clean-java all        Clean all .java files under current workspace"
    echo "    telua clean-java <path>     Clean a specific .java file or directory"
    echo "    telua clean-java help       Show detailed clean_java.py usage"
    echo ""
}

show_clean_help() {
    show_clean_short_help
    local py_script
    py_script="$(resolve_clean_java_script)" || true
    if [ -n "$py_script" ]; then
        echo "Underlying helper ($CLEAN_JAVA_PY_NAME):"
        python "$py_script" --help 2>&1 || python3 "$py_script" --help 2>&1 || true
    fi
}

is_clean_action() {
    local action="$1"
    case "$action" in
        diff|all|help|-h|--help) return 0 ;;
        *.java) return 0 ;;
        *)
            if [ -d "$action" ] || [ -f "$action" ]; then
                return 0
            fi
            return 1
            ;;
    esac
}

handle_clean_command() {
    local action="$1"
    local py_script
    py_script="$(resolve_clean_java_script)" || {
        echo "[ERROR] Could not find $CLEAN_JAVA_PY_NAME helper script." >&2
        return 1
    }

    local py_cmd="python"
    if ! command -v python >/dev/null 2>&1; then
        if command -v python3 >/dev/null 2>&1; then
            py_cmd="python3"
        else
            echo "[ERROR] Python is required to run $CLEAN_JAVA_PY_NAME." >&2
            return 1
        fi
    fi

    case "$action" in
        help|-h|--help)
            show_clean_help
            ;;
        diff|--diff)
            "$py_cmd" "$py_script" --diff
            ;;
        all|--all)
            "$py_cmd" "$py_script" --all
            ;;
        "")
            "$py_cmd" "$py_script"
            ;;
        *)
            "$py_cmd" "$py_script" "$action"
            ;;
    esac
}
