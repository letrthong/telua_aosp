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
#   - skill_cmd_setup (telua java skill: .skill/java/ softlink registry)
#
# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_CLEAN_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_CLEAN_SOURCED=1

CLEAN_JAVA_PY_NAME="python/clean_java.py"
UNUSED_REPORT_PY_NAME="python/unused_methods_report.py"

# Skill registry locations (relative to the toolkit root, i.e. the directory
# that contains this src/ folder). Both are git repos cloned under repos/.
SKILL_DIR_NAME=".skill"
SKILL_JAVA_SUBDIR="java"
SKILL_SOURCE_TELUA="repos/telua_skill/Java_Android"
SKILL_SOURCE_CLAUDE="repos/claude-code-java/skills"

# Resolve the toolkit root (dir containing src/telua_clean.sh), preferring
# MASTER_SCRIPT_DIR when this module is sourced from a softlinked copy.
resolve_toolkit_root() {
    if [ -n "${MASTER_SCRIPT_DIR:-}" ] && [ -d "$MASTER_SCRIPT_DIR/repos" ]; then
        echo "$MASTER_SCRIPT_DIR"
        return 0
    fi
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    echo "$script_dir"
}

# telua java skill — create .skill/java/ with softlinks to the 2 skill sources:
#   .skill/java/Java_Android -> repos/telua_skill/Java_Android   (rules/docs/design manifest)
#   .skill/java/<skill-name> -> repos/claude-code-java/skills/<skill-name>  (per-skill SKILL.md)
skill_cmd_setup() {
    local toolkit_root
    toolkit_root="$(resolve_toolkit_root)"
    local telua_src="$toolkit_root/$SKILL_SOURCE_TELUA"
    local claude_src="$toolkit_root/$SKILL_SOURCE_CLAUDE"

    if [ ! -d "$telua_src" ]; then
        echo "[ERROR] Skill source not found: $telua_src" >&2
        echo "        Expected the telua_skill repo under repos/ (git clone first)." >&2
        return 1
    fi

    local skill_root="$PWD/$SKILL_DIR_NAME"
    local skill_java_dir="$skill_root/$SKILL_JAVA_SUBDIR"
    mkdir -p "$skill_java_dir"

    echo "[INFO] Skill registry: $skill_java_dir"

    # 1. Link the whole Java_Android knowledge base (rules/docs/design/examples)
    local link="$skill_java_dir/Java_Android"
    if [ -L "$link" ] || [ -e "$link" ]; then
        echo "[SKIP] $link already exists"
    else
        ln -s "$telua_src" "$link" \
            && echo "[LINK] Java_Android -> $telua_src" \
            || { echo "[ERROR] Failed to link Java_Android" >&2; return 1; }
    fi

    # 2. Link each individual claude-code-java skill (SKILL.md convention)
    if [ -d "$claude_src" ]; then
        local entry name linked=0 skipped=0
        for entry in "$claude_src"/*; do
            [ -d "$entry" ] || continue
            name="$(basename "$entry")"
            link="$skill_java_dir/$name"
            if [ -L "$link" ] || [ -e "$link" ]; then
                skipped=$((skipped + 1))
            else
                ln -s "$entry" "$link" \
                    && { echo "[LINK] $name -> $entry"; linked=$((linked + 1)); } \
                    || echo "[WARN]  Failed to link $name" >&2
            fi
        done
        echo "[INFO] claude-code-java skills: $linked linked, $skipped already present"
    else
        echo "[WARN] claude-code-java skills not found: $claude_src (skipped)" >&2
    fi

    echo ""
    echo "[OK] Skill registry ready: $skill_java_dir"
    echo "     AI agents can now discover skills via .skill/java/ in this workspace."
    return 0
}

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

resolve_unused_report_script() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [ -f "$script_dir/$UNUSED_REPORT_PY_NAME" ]; then
        echo "$script_dir/$UNUSED_REPORT_PY_NAME"
        return 0
    fi
    if [ -n "${MASTER_SCRIPT_DIR:-}" ] && [ -f "$MASTER_SCRIPT_DIR/$UNUSED_REPORT_PY_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR/$UNUSED_REPORT_PY_NAME"
        return 0
    fi
    if [ -f "$UNUSED_REPORT_PY_NAME" ]; then
        echo "$UNUSED_REPORT_PY_NAME"
        return 0
    fi
    return 1
}

GJF_JAR_VERSION="1.24.0"
GJF_JAR_URL="https://github.com/google/google-java-format/releases/download/v${GJF_JAR_VERSION}/google-java-format-${GJF_JAR_VERSION}-all-deps.jar"

ensure_google_java_format_pre_commit() {
    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    [ -n "${MASTER_SCRIPT_DIR:-}" ] && [ -d "${MASTER_SCRIPT_DIR}" ] && repo_dir="$MASTER_SCRIPT_DIR"
    local gjf_dir="$repo_dir/third_party/google-java-format"
    local gjf_jar="$gjf_dir/google-java-format-${GJF_JAR_VERSION}-all-deps.jar"
    if [ -s "$gjf_jar" ]; then
        return 0
    fi
    mkdir -p "$gjf_dir"
    echo "[INFO] Downloading google-java-format-${GJF_JAR_VERSION}-all-deps.jar into $gjf_dir ..."
    if command -v curl >/dev/null 2>&1; then
        curl -fksSL "$GJF_JAR_URL" -o "$gjf_jar" || rm -f "$gjf_jar"
    elif command -v wget >/dev/null 2>&1; then
        wget --no-check-certificate -qO "$gjf_jar" "$GJF_JAR_URL" || rm -f "$gjf_jar"
    fi
}

show_clean_short_help() {
    echo ""
    echo -e "\033[1;32m  telua java [target] (alias: clean-java) - Java source hygiene & static report\033[0m"
    echo "  Modes:"
    echo "    telua java [clean]          Clean .java files in current directory (default)"
    echo "    telua java diff             Clean Git-modified or added .java files (clean-java diff)"
    echo "    telua java all              Clean all .java files under current workspace (clean-java all)"
    echo "    telua java <path>           Clean a specific .java file or directory"
    echo "    telua java report [t]       Report unused methods/params, whitespace & google-java-format"
    echo "    telua java skill            Create .skill/java/ softlink registry (telua_skill + claude-code-java)"
    echo "    telua java help             Show detailed clean_java.py usage"
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
        clean|diff|all|report|skill|help|-h|--help) return 0 ;;
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
    if [ "$action" = "clean" ] || [ "$action" = "--clean" ]; then
        shift
        action="${1:-}"
    fi
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
        skill|--skill)
            skill_cmd_setup
            ;;
        diff|--diff)
            "$py_cmd" "$py_script" --diff
            ;;
        all|--all)
            "$py_cmd" "$py_script" --all
            ;;
        report)
            # Unused-method report: optional sub-target (diff|all|<file|dir>).
            # No sub-target -> scan the CURRENT directory (default).
            local report_script report_target=""
            report_script="$(resolve_unused_report_script)" || {
                echo "[ERROR] Could not find $UNUSED_REPORT_PY_NAME helper script." >&2
                return 1
            }
            if [ -n "$2" ]; then
                report_target="$2"
            fi
            if [ "$report_target" != "help" ] && [ "$report_target" != "-h" ] && [ "$report_target" != "--help" ]; then
                ensure_google_java_format_pre_commit
            fi
            if [ -z "$report_target" ] || [ "$report_target" = "all" ] || [ "$report_target" = "--all" ]; then
                "$py_cmd" "$report_script"
            elif [ "$report_target" = "diff" ] || [ "$report_target" = "--diff" ]; then
                "$py_cmd" "$report_script" --diff
            elif [ "$report_target" = "help" ] || [ "$report_target" = "-h" ] || [ "$report_target" = "--help" ]; then
                "$py_cmd" "$report_script" --help
            else
                "$py_cmd" "$report_script" "$report_target"
            fi
            ;;
        "")
            "$py_cmd" "$py_script"
            ;;
        *)
            "$py_cmd" "$py_script" "$action"
            ;;
    esac
}
