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
# telua_docs.sh - Documentation (Sphinx Doc-as-Code) utilities for the Telua toolkit.
# Single source of truth for 'telua docs <action>' (alias 'telua doc <action>'):
#   - 'telua docs init'  : Initialize docs project in ./docs from sphinx template
#                          (idempotent: does NOT overwrite if directory exists)
#   - 'telua docs build' : Check, merge modular sections & compile Sphinx HTML
#   - 'telua docs clean' : Remove _build directory
#   - 'telua docs serve' : Run local HTTP preview server (default: port 8080)
#   - 'telua docs check' : Validate section file paths & image links
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_docs.sh"

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_DOCS_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_DOCS_SOURCED=1

# Display formatted help for docs commands
show_docs_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  TELUA DOCS — SPHINX DOC-AS-CODE MANAGEMENT\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "  Usage: \033[1;33mtelua docs <action> [options]\033[0m  (or: \033[1;33mtelua doc <action>\033[0m)"
    echo ""
    echo -e "\033[1;33mAVAILABLE ACTIONS:\033[0m"
    printf "  \033[1;36m%-18s\033[0m %s\n" "start [port]" "Build (if needed), launch HTTP server & open browser (default: 8080)"
    printf "  \033[1;36m%-18s\033[0m %s\n" "serve [port]" "Alias for 'start' to run local HTTP preview server"
    printf "  \033[1;36m%-18s\033[0m %s\n" "build" "Validate, merge modular sections & compile Sphinx HTML"
    printf "  \033[1;36m%-18s\033[0m %s\n" "check" "Verify section file paths and image links"
    printf "  \033[1;36m%-18s\033[0m %s\n" "clean" "Clean build artifacts (_build directory)"
    printf "  \033[1;36m%-18s\033[0m %s\n" "init [dir]" "Initialize docs from template in ./docs (skips if already exists)"
    printf "  \033[1;36m%-18s\033[0m %s\n" "help" "Show this help message"
    echo ""
    echo -e "\033[1;36m--------------------------------------------------------------------------------\033[0m"
    echo -e "  \033[0;90mTemplate Source:\033[0m ${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template"
    echo -e "  \033[0;90mScripts Engine :\033[0m ${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/scripts"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

# Resolve active documentation directory (checks ., ./docs, ./sphinx/template, ./sphinx)
resolve_docs_dir() {
    local candidate="${1:-}"
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
        echo "$candidate"
        return 0
    fi

    # Check if current working directory is a docs root
    if [ -f "./conf.py" ] && [ -f "./metadata.json" ]; then
        echo "."
        return 0
    fi

    # Check ./docs
    if [ -d "./docs" ] && ([ -f "./docs/conf.py" ] || [ -f "./docs/metadata.json" ]); then
        echo "./docs"
        return 0
    fi

    # Check ./sphinx/template
    if [ -d "./sphinx/template" ] && ([ -f "./sphinx/template/conf.py" ] || [ -f "./sphinx/template/metadata.json" ]); then
        echo "./sphinx/template"
        return 0
    fi

    # Check ./sphinx
    if [ -d "./sphinx" ] && ([ -f "./sphinx/conf.py" ] || [ -f "./sphinx/metadata.json" ]); then
        echo "./sphinx"
        return 0
    fi

    # Default fallback target directory for init
    echo "./docs"
    return 0
}

# Helper: locate python command
_docs_get_python_cmd() {
    for py in python3 python py; do
        if command -v "$py" >/dev/null 2>&1; then
            if "$py" --version >/dev/null 2>&1; then
                echo "$py"
                return 0
            fi
        fi
    done
    echo ""
    return 1
}

# Helper: locate doc toolchain script (checks target directory first, then central scripts/)
_docs_find_script() {
    local script_name="$1"
    local target_dir="$2"
    if [ -f "$target_dir/$script_name" ]; then
        echo "$target_dir/$script_name"
    elif [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/scripts/$script_name" ]; then
        echo "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/scripts/$script_name"
    elif [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/$script_name" ]; then
        echo "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/$script_name"
    else
        echo ""
    fi
}

# Helper: launch URL in default browser
_docs_open_browser() {
    local url="$1"
    (
        sleep 1 2>/dev/null || true
        if command -v explorer.exe >/dev/null 2>&1; then
            explorer.exe "$url" >/dev/null 2>&1
        elif command -v cmd.exe >/dev/null 2>&1; then
            cmd.exe /c start "" "$url" >/dev/null 2>&1
        elif command -v powershell.exe >/dev/null 2>&1; then
            powershell.exe -NoProfile -Command "Start-Process '$url'" >/dev/null 2>&1
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$url" >/dev/null 2>&1
        elif command -v open >/dev/null 2>&1; then
            open "$url" >/dev/null 2>&1
        fi
    ) &
}

# Action: init
docs_cmd_init() {
    local target_dir="${1:-docs}"
    local template_dir="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template"
    if [ ! -d "$template_dir" ]; then
        template_dir="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx"
    fi

    # Normalize target path
    target_dir="$(echo "$target_dir" | sed 's:/*$::')"

    # Check if target docs project already exists
    if [ -d "$target_dir" ]; then
        if [ -f "$target_dir/conf.py" ] || [ -f "$target_dir/metadata.json" ]; then
            log_warn "Documentation project already exists in '$target_dir' (found conf.py or metadata.json)."
            log_warn "Skipping initialization. Existing documentation files were NOT modified."
            echo ""
            echo -e "  To rebuild docs, run:   \033[1;33mtelua docs build\033[0m"
            echo -e "  To start preview, run:  \033[1;33mtelua docs start\033[0m"
            echo ""
            return 0
        fi
    fi

    # Verify template directory
    if [ ! -d "$template_dir" ]; then
        log_error "Sphinx template directory not found at: $template_dir"
        return 1
    fi

    log_info "Initializing documentation project in '$target_dir' from template..."
    mkdir -p "$target_dir"

    # Copy template files excluding _build, scripts, and internal files
    local copied_count=0
    for item in "$template_dir"/*; do
        local basename
        basename="$(basename "$item")"
        if [ "$basename" != "_build" ] && [ "$basename" != ".git" ] && [ "$basename" != "scripts" ] && [ "$basename" != "template" ] && [ "$basename" != "gen_sphinx.sh" ]; then
            cp -r "$item" "$target_dir/"
            copied_count=$((copied_count + 1))
        fi
    done

    # Ensure requirements.txt is copied if missing
    if [ ! -f "$target_dir/requirements.txt" ] && [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/requirements.txt" ]; then
        cp "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/requirements.txt" "$target_dir/requirements.txt"
        copied_count=$((copied_count + 1))
    fi

    log_success "Created documentation template in '$target_dir' ($copied_count items copied)."
    echo ""
    echo -e "  \033[1;32mNext steps:\033[0m"
    echo -e "    1. Install requirements : \033[1;37mpip install -r $target_dir/requirements.txt\033[0m"
    echo -e "    2. Edit metadata        : \033[1;37m$target_dir/metadata.json\033[0m"
    echo -e "    3. Build HTML           : \033[1;33mtelua docs build\033[0m"
    echo -e "    4. Open HTML preview    : \033[1;33mtelua docs start\033[0m  (default port 8080)"
    echo ""
    return 0
}

# Action: check
docs_cmd_check() {
    local target_dir
    target_dir="$(resolve_docs_dir "${1:-}")"

    if [ ! -f "$target_dir/metadata.json" ]; then
        log_error "No documentation project found in '$target_dir' (missing metadata.json)."
        log_error "Run 'telua docs init' to create a new documentation project."
        return 1
    fi

    local py_cmd
    py_cmd="$(_docs_get_python_cmd)"
    if [ -z "$py_cmd" ]; then
        log_error "Python 3 is required but not found in PATH."
        return 1
    fi

    log_info "Validating documentation project in '$target_dir'..."

    # Check sections
    local script_sec
    script_sec="$(_docs_find_script "check_sections.py" "$target_dir")"
    if [ -n "$script_sec" ]; then
        log_info "Checking chapter and section file paths..."
        if ! "$py_cmd" "$script_sec" "$target_dir"; then
            log_error "Section path validation failed!"
            return 1
        fi
    fi

    # Check images
    local script_img
    script_img="$(_docs_find_script "check_docs.py" "$target_dir")"
    if [ -n "$script_img" ]; then
        log_info "Checking image references..."
        if ! "$py_cmd" "$script_img" "$target_dir"; then
            log_error "Image validation failed!"
            return 1
        fi
    fi

    log_success "All documentation checks passed successfully."
    return 0
}

# Action: build
docs_cmd_build() {
    local target_dir
    target_dir="$(resolve_docs_dir "${1:-}")"

    if [ ! -f "$target_dir/conf.py" ] || [ ! -f "$target_dir/metadata.json" ]; then
        log_error "No documentation project found in '$target_dir' (missing conf.py or metadata.json)."
        log_error "Run 'telua docs init' to initialize a documentation project."
        return 1
    fi

    local py_cmd
    py_cmd="$(_docs_get_python_cmd)"
    if [ -z "$py_cmd" ]; then
        log_error "Python 3 is required but not found in PATH."
        return 1
    fi

    if ! command -v sphinx-build >/dev/null 2>&1; then
        log_error "'sphinx-build' command not found in PATH!"
        log_error "Please install Sphinx dependencies: pip install -r $target_dir/requirements.txt"
        return 1
    fi

    log_info "============================================================"
    log_info " Building Sphinx Documentation: '$target_dir'"
    log_info "============================================================"

    # 1. Check sections
    local script_sec
    script_sec="$(_docs_find_script "check_sections.py" "$target_dir")"
    if [ -n "$script_sec" ]; then
        log_info "Step 1/4: Checking chapter & section paths..."
        if ! "$py_cmd" "$script_sec" "$target_dir"; then
            log_error "Section validation failed! Build aborted."
            return 1
        fi
    fi

    # 2. Merge sections into chapters
    local script_merge
    script_merge="$(_docs_find_script "merge_docs.py" "$target_dir")"
    if [ -n "$script_merge" ]; then
        log_info "Step 2/4: Merging section files into chapter documents..."
        if ! "$py_cmd" "$script_merge" "$target_dir"; then
            log_error "Merge docs failed! Build aborted."
            return 1
        fi
    fi

    # 3. Check image references
    local script_img
    script_img="$(_docs_find_script "check_docs.py" "$target_dir")"
    if [ -n "$script_img" ]; then
        log_info "Step 3/4: Checking image links..."
        if ! "$py_cmd" "$script_img" "$target_dir"; then
            log_error "Image validation failed! Build aborted."
            return 1
        fi
    fi

    # 4. Compile Sphinx HTML
    log_info "Step 4/4: Compiling Sphinx HTML..."
    local out_html="$target_dir/_build/html"
    if ! sphinx-build -b html "$target_dir" "$out_html"; then
        log_error "Sphinx build failed!"
        return 1
    fi

    echo ""
    log_success "Documentation build completed successfully!"
    echo -e "  HTML Output: \033[1;36m$out_html/index.html\033[0m"
    echo -e "  To preview:  \033[1;33mtelua docs start\033[0m"
    echo ""
    return 0
}

# Action: clean
docs_cmd_clean() {
    local target_dir
    target_dir="$(resolve_docs_dir "${1:-}")"

    if [ -d "$target_dir/_build" ]; then
        log_info "Cleaning documentation build artifacts in '$target_dir/_build'..."
        rm -rf "$target_dir/_build"
        log_success "Cleaned $target_dir/_build."
    else
        log_info "Build directory '$target_dir/_build' does not exist. Nothing to clean."
    fi
    return 0
}

# Action: start / serve (opens browser and starts HTTP preview server)
docs_cmd_start() {
    local target_dir
    target_dir="$(resolve_docs_dir "")"
    local port="${1:-8080}"

    local html_dir="$target_dir/_build/html"
    if [ ! -f "$html_dir/index.html" ]; then
        log_warn "HTML documentation not found in '$html_dir'. Triggering build first..."
        if ! docs_cmd_build "$target_dir"; then
            return 1
        fi
    fi

    local py_cmd
    py_cmd="$(_docs_get_python_cmd)"
    if [ -z "$py_cmd" ]; then
        log_error "Python 3 is required to run preview server."
        return 1
    fi

    local preview_url="http://localhost:$port"

    echo ""
    log_info "============================================================"
    log_info " Starting Documentation Preview Server on port $port"
    log_info " Documentation root : $target_dir"
    log_info " HTML directory     : $html_dir"
    log_info " Local URL          : $preview_url"
    log_info " Opening default browser..."
    log_info " Press Ctrl+C to stop the HTTP server"
    log_info "============================================================"
    echo ""

    # Open browser automatically
    _docs_open_browser "$preview_url"

    # Start HTTP server
    "$py_cmd" -m http.server "$port" --directory "$html_dir"
}

# Main command handler for 'telua docs <action>'
handle_docs_command() {
    local action="${1:-}"
    shift 2>/dev/null || true

    case "$action" in
        init)
            docs_cmd_init "$@"
            ;;
        build)
            docs_cmd_build "$@"
            ;;
        clean)
            docs_cmd_clean "$@"
            ;;
        check)
            docs_cmd_check "$@"
            ;;
        start|serve|run|preview)
            docs_cmd_start "$@"
            ;;
        help|--help|-h|"")
            show_docs_help
            ;;
        *)
            log_error "Unknown docs action '$action'!"
            show_docs_help
            exit 1
            ;;
    esac
}

