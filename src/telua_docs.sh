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
    printf "  \033[1;36m%-22s\033[0m %s\n" "start [port]" "Build (if needed), launch HTTP server & open browser (default: 8080)"
    printf "  \033[1;36m%-22s\033[0m %s\n" "serve [port]" "Alias for 'start' to run local HTTP preview server"
    printf "  \033[1;36m%-22s\033[0m %s\n" "sync [dir]" "Pre-check formatting & auto-sync folders/sections into metadata.json"
    printf "  \033[1;36m%-22s\033[0m %s\n" "build" "Validate, merge modular sections & compile Sphinx HTML"
    printf "  \033[1;36m%-22s\033[0m %s\n" "check" "Verify section file paths and image links"
    printf "  \033[1;36m%-22s\033[0m %s\n" "clean" "Clean build artifacts (_build directory)"
    printf "  \033[1;36m%-22s\033[0m %s\n" "init [dir] [-t type]" "Initialize docs (templates: basic, architecture, minimal, api)"
    printf "  \033[1;36m%-22s\033[0m %s\n" "help" "Show this help message"
    echo ""
    echo -e "\033[1;36m--------------------------------------------------------------------------------\033[0m"
    echo -e "  \033[0;90mTemplates Root :\033[0m ${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/templates (basic, architecture, minimal, api)"
    echo -e "  \033[0;90mScripts Engine :\033[0m ${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/scripts"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

# Resolve active documentation directory (checks ., ./docs, ./sphinx/templates/basic, ./sphinx)
resolve_docs_dir() {
    local candidate="${1:-}"
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
        echo "$candidate"
        return 0
    fi

    # Check if current working directory is a docs root
    if [ -f "./metadata.json" ] || [ -f "./index.rst" ] || [ -f "./conf.py" ]; then
        echo "."
        return 0
    fi

    # Check ./docs
    if [ -d "./docs" ] && ([ -f "./docs/metadata.json" ] || [ -f "./docs/index.rst" ] || [ -f "./docs/conf.py" ]); then
        echo "./docs"
        return 0
    fi

    # Check ./sphinx/templates/basic
    if [ -d "./sphinx/templates/basic" ] && ([ -f "./sphinx/templates/basic/metadata.json" ] || [ -f "./sphinx/templates/basic/index.rst" ]); then
        echo "./sphinx/templates/basic"
        return 0
    fi

    # Check ./sphinx/templates/architecture
    if [ -d "./sphinx/templates/architecture" ] && ([ -f "./sphinx/templates/architecture/metadata.json" ] || [ -f "./sphinx/templates/architecture/index.rst" ]); then
        echo "./sphinx/templates/architecture"
        return 0
    fi

    # Check ./sphinx/template (legacy fallback)
    if [ -d "./sphinx/template" ] && ([ -f "./sphinx/template/metadata.json" ] || [ -f "./sphinx/template/index.rst" ]); then
        echo "./sphinx/template"
        return 0
    fi

    # Check ./sphinx
    if [ -d "./sphinx" ] && ([ -f "./sphinx/metadata.json" ] || [ -f "./sphinx/conf.py" ]); then
        echo "./sphinx"
        return 0
    fi

    # Default fallback target directory for init
    echo "./docs"
    return 0
}

# Helper: locate python command (bypasses WindowsApps stubs, safe under set -e)
_docs_get_python_cmd() {
    for py in python py python3; do
        local path_to_py
        path_to_py="$(command -v "$py" 2>/dev/null || true)"
        if [ -n "$path_to_py" ]; then
            if [[ "$path_to_py" == *"WindowsApps"* ]]; then
                continue
            fi
            if "$py" --version >/dev/null 2>&1; then
                echo "$py"
                return 0
            fi
        fi
    done
    echo ""
    return 0
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

# Helper: detect sphinx build command (command line or python -m module, safe under set -e)
_docs_get_sphinx_build_cmd() {
    local py_cmd="${1:-}"
    [ -z "$py_cmd" ] && py_cmd="$(_docs_get_python_cmd)"

    if command -v sphinx-build >/dev/null 2>&1; then
        echo "sphinx-build"
        return 0
    fi

    if [ -n "$py_cmd" ] && "$py_cmd" -m sphinx.cmd.build --version >/dev/null 2>&1; then
        echo "$py_cmd -m sphinx.cmd.build"
        return 0
    fi

    echo ""
    return 0
}

# Helper: ensure sphinx-build is installed, auto-install via pip if missing
_docs_ensure_sphinx_build() {
    local target_dir="${1:-docs}"
    local py_cmd
    py_cmd="$(_docs_get_python_cmd)"

    if [ -z "$py_cmd" ]; then
        log_warn "Python 3 is required to check or install Sphinx dependencies."
        return 1
    fi

    local sphinx_cmd
    sphinx_cmd="$(_docs_get_sphinx_build_cmd "$py_cmd")"

    local missing_mermaid=0
    if [ -n "$py_cmd" ] && ! "$py_cmd" -c "import sphinxcontrib.mermaid" >/dev/null 2>&1; then
        missing_mermaid=1
    fi

    if [ -n "$sphinx_cmd" ] && [ "$missing_mermaid" -eq 0 ]; then
        log_info "Sphinx build tool ready: $sphinx_cmd (diagram extensions verified)"
        return 0
    fi

    # Locate requirements.txt from central toolkit first (fallback to target directory)
    local req_file=""
    if [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/requirements.txt" ]; then
        req_file="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/requirements.txt"
    elif [ -f "$target_dir/requirements.txt" ]; then
        req_file="$target_dir/requirements.txt"
    elif [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/requirements.txt" ]; then
        req_file="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/requirements.txt"
    fi

    if [ -z "$req_file" ]; then
        log_warn "No requirements.txt found to install Sphinx dependencies."
        return 1
    fi

    echo ""
    if [ -z "$sphinx_cmd" ]; then
        log_warn "Sphinx build tool ('sphinx-build') is not detected."
    else
        log_warn "Sphinx diagram extension ('sphinxcontrib.mermaid') is missing."
    fi
    log_info "Auto-installing Sphinx and required extensions via pip..."
    log_info "Running: $py_cmd -m pip install -r $req_file"
    echo ""

    local install_ok=0
    if "$py_cmd" -m pip install -r "$req_file"; then
        install_ok=1
    else
        log_warn "Standard pip install returned non-zero. Retrying with --user..."
        if "$py_cmd" -m pip install --user -r "$req_file"; then
            install_ok=1
        fi
    fi

    # Re-verify
    sphinx_cmd="$(_docs_get_sphinx_build_cmd "$py_cmd")"
    if [ -n "$sphinx_cmd" ]; then
        echo ""
        log_success "Sphinx dependencies installed successfully! Build command: $sphinx_cmd"
        return 0
    elif [ "$install_ok" -eq 1 ]; then
        echo ""
        log_success "Sphinx packages installed into Python environment."
        log_warn "Note: If 'sphinx-build' is not in PATH, '$py_cmd -m sphinx.cmd.build' will be used."
        return 0
    else
        echo ""
        log_error "Automatic installation of Sphinx dependencies failed."
        log_error "Please run manually: $py_cmd -m pip install -r $req_file"
        return 1
    fi
}

# Action: init (supports --template architecture|minimal|api)
docs_cmd_init() {
    local target_dir="docs"
    local chosen_template=""

    # Parse arguments: target directory and --template / -t flags
    while [ $# -gt 0 ]; do
        case "$1" in
            --template=*)
                chosen_template="${1#*=}"
                shift
                ;;
            --template|-t)
                chosen_template="${2:-}"
                shift 2 2>/dev/null || shift
                ;;
            -*)
                log_warn "Unknown init option '$1' (ignored)."
                shift
                ;;
            *)
                target_dir="$1"
                shift
                ;;
        esac
    done

    # Normalize target path
    target_dir="$(echo "$target_dir" | sed 's:/*$::')"

    # Check if target docs project already exists
    if [ -d "$target_dir" ]; then
        if [ -f "$target_dir/metadata.json" ] || [ -f "$target_dir/index.rst" ] || [ -f "$target_dir/conf.py" ]; then
            log_warn "Documentation project already exists in '$target_dir' (found metadata.json, index.rst or conf.py)."
            log_warn "Skipping initialization. Existing documentation files were NOT modified."
            echo ""
            _docs_ensure_sphinx_build "$target_dir"
            echo ""
            echo -e "  To rebuild docs, run:   \033[1;33mtelua docs build\033[0m"
            echo -e "  To start preview, run:  \033[1;33mtelua docs start\033[0m"
            echo ""
            return 0
        fi
    fi

    # Interactive template selection if not specified and running in interactive terminal
    if [ -z "$chosen_template" ] && [ -t 0 ]; then
        echo ""
        echo -e "\033[1;36m============================================================\033[0m"
        echo -e "\033[1;32m  TELUA DOCS INITIALIZER — SELECT TEMPLATE\033[0m"
        echo -e "\033[1;36m============================================================\033[0m"
        echo -e "  Target directory: \033[1;33m$target_dir\033[0m"
        echo ""
        echo -e "  \033[1;33m[1]\033[0m \033[1;37mbasic\033[0m         Standard starter template (original chapters & assets)"
        echo -e "  \033[1;33m[2]\033[0m \033[1;37marchitecture\033[0m  System Design, Mermaid Diagrams, AAOS flows"
        echo -e "  \033[1;33m[3]\033[0m \033[1;37mminimal\033[0m       Clean & lightweight starter, single chapter"
        echo -e "  \033[1;33m[4]\033[0m \033[1;37mapi\033[0m           API & SDK reference, parameter tables, status codes"
        echo ""
        read -r -p "Select template [1-4] (default 1): " t_choice
        case "$t_choice" in
            2) chosen_template="architecture" ;;
            3) chosen_template="minimal" ;;
            4) chosen_template="api" ;;
            *) chosen_template="basic" ;;
        esac
    fi

    # Normalize template name / aliases
    case "$(echo "${chosen_template:-basic}" | tr '[:upper:]' '[:lower:]')" in
        basic|default|"")
            chosen_template="basic"
            ;;
        arch|architecture)
            chosen_template="architecture"
            ;;
        min|minimal|clean)
            chosen_template="minimal"
            ;;
        api|sdk|rest)
            chosen_template="api"
            ;;
        *)
            log_error "Unknown documentation template '$chosen_template'!"
            echo -e "  Available templates: \033[1;33mbasic\033[0m, \033[1;33marchitecture\033[0m (or \033[1;33march\033[0m), \033[1;33mminimal\033[0m (or \033[1;33mmin\033[0m), \033[1;33mapi\033[0m"
            return 1
            ;;
    esac

    # Locate template directory
    local base_templates="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/templates"
    local template_dir=""

    if [ -d "$base_templates/$chosen_template" ]; then
        template_dir="$base_templates/$chosen_template"
    elif [ -d "$base_templates/basic" ]; then
        template_dir="$base_templates/basic"
    elif [ -d "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template" ]; then
        template_dir="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template"
    elif [ -d "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx" ]; then
        template_dir="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx"
    fi

    # Verify template directory exists
    if [ ! -d "$template_dir" ]; then
        log_error "Template directory not found at: $template_dir"
        return 1
    fi

    log_info "Initializing documentation project in '$target_dir' using template [\033[1;33m$chosen_template\033[0m]..."
    mkdir -p "$target_dir"

    # Copy template content files only:
    local copied_count=0
    for item in "$template_dir"/*; do
        local basename
        basename="$(basename "$item")"
        case "$basename" in
            conf.py)
                cp -r "$item" "$target_dir/"
                copied_count=$((copied_count + 1))
                ;;
            *.py|requirements.txt|ReadMe*|README*|github.md|_build|.git|scripts|templates|template|gen_sphinx.sh)
                # Skip toolchain scripts, requirements.txt, ReadMe and internal files
                continue
                ;;
            *)
                cp -r "$item" "$target_dir/"
                copied_count=$((copied_count + 1))
                ;;
        esac
    done

    # Ensure custom static directory (_static) is copied if not already captured
    if [ -d "$template_dir/_static" ] && [ ! -d "$target_dir/_static" ]; then
        cp -r "$template_dir/_static" "$target_dir/"
        copied_count=$((copied_count + 1))
    fi

    # Ensure asset directory (images) is copied (fallback to sphinx/template/asset if needed)
    if [ ! -d "$target_dir/asset" ]; then
        if [ -d "$template_dir/asset" ]; then
            cp -r "$template_dir/asset" "$target_dir/" 2>/dev/null || true
            copied_count=$((copied_count + 1))
        elif [ -d "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/asset" ]; then
            cp -r "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/asset" "$target_dir/" 2>/dev/null || true
            copied_count=$((copied_count + 1))
        fi
    fi

    log_success "Created documentation in '$target_dir' using '$chosen_template' template ($copied_count items copied)."

    # Automatically check and install Sphinx dependencies if missing
    _docs_ensure_sphinx_build "$target_dir"

    echo ""
    echo -e "  \033[1;32mNext steps:\033[0m"
    echo -e "    1. Project config       : \033[1;37m$target_dir/conf.py\033[0m (project name, author, theme)"
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

    if [ ! -f "$target_dir/metadata.json" ] && [ ! -f "$target_dir/index.rst" ]; then
        log_error "No documentation project found in '$target_dir' (missing metadata.json or index.rst)."
        log_error "Run 'telua docs init' to initialize a documentation project."
        return 1
    fi

    local py_cmd
    py_cmd="$(_docs_get_python_cmd)"
    if [ -z "$py_cmd" ]; then
        log_error "Python 3 is required but not found in PATH."
        return 1
    fi

    local sphinx_cmd
    sphinx_cmd="$(_docs_get_sphinx_build_cmd "$py_cmd")"
    if [ -z "$sphinx_cmd" ] || ! "$py_cmd" -c "import sphinxcontrib.mermaid" >/dev/null 2>&1; then
        _docs_ensure_sphinx_build "$target_dir"
        sphinx_cmd="$(_docs_get_sphinx_build_cmd "$py_cmd")"
    fi

    if [ -z "$sphinx_cmd" ]; then
        log_error "Sphinx build tool is still unavailable!"
        log_error "Please install Sphinx dependencies manually: pip install -r ${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/requirements.txt"
        return 1
    fi

    # Resolve conf.py: use local if customized by user, else fallback to central template conf.py
    local conf_arg=""
    if [ -f "$target_dir/conf.py" ]; then
        conf_arg="-c $target_dir"
    elif [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/conf.py" ]; then
        conf_arg="-c ${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template"
    elif [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/conf.py" ]; then
        conf_arg="-c ${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx"
    fi

    log_info "============================================================"
    log_info " Building Sphinx Documentation: '$target_dir'"
    log_info "============================================================"

    # Prepare isolated staging directory in _build/.staging (keeps source files 100% untouched)
    local staging_dir="$target_dir/_build/.staging"
    local out_html="$target_dir/_build/html"

    rm -rf "$staging_dir"
    mkdir -p "$staging_dir"

    # Copy source docs into staging (exclude _build, .git)
    local item
    for item in "$target_dir"/*; do
        local bname
        bname="$(basename "$item")"
        if [ "$bname" != "_build" ] && [ "$bname" != ".git" ]; then
            cp -r "$item" "$staging_dir/"
        fi
    done

    # If staging lacks conf.py, fallback to central template conf.py
    if [ ! -f "$staging_dir/conf.py" ]; then
        if [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/conf.py" ]; then
            cp "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/conf.py" "$staging_dir/conf.py"
        elif [ -f "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/conf.py" ]; then
            cp "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/conf.py" "$staging_dir/conf.py"
        fi
    fi

    # Ensure custom static directory (_static) is copied into staging
    if [ ! -d "$staging_dir/_static" ] && [ -d "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/_static" ]; then
        cp -r "${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}/sphinx/template/_static" "$staging_dir/"
    fi

    # 1. Check sections (on staging_dir)
    local script_sec
    script_sec="$(_docs_find_script "check_sections.py" "$staging_dir")"
    if [ -n "$script_sec" ]; then
        log_info "Step 1/4: Checking chapter & section paths..."
        if ! "$py_cmd" "$script_sec" "$staging_dir"; then
            log_error "Section validation failed! Build aborted."
            rm -rf "$staging_dir"
            return 1
        fi
    fi

    # 2. Merge sections into chapters (in staging_dir ONLY, source files remain untouched!)
    local script_merge
    script_merge="$(_docs_find_script "merge_docs.py" "$staging_dir")"
    if [ -n "$script_merge" ]; then
        log_info "Step 2/4: Merging sections in staging directory (source files untouched)..."
        if ! "$py_cmd" "$script_merge" "$staging_dir"; then
            log_error "Merge docs failed! Build aborted."
            rm -rf "$staging_dir"
            return 1
        fi
    fi

    # 3. Check image references
    local script_img
    script_img="$(_docs_find_script "check_docs.py" "$staging_dir")"
    if [ -n "$script_img" ]; then
        log_info "Step 3/4: Checking image links..."
        if ! "$py_cmd" "$script_img" "$staging_dir"; then
            log_error "Image validation failed! Build aborted."
            rm -rf "$staging_dir"
            return 1
        fi
    fi

    # 4. Compile Sphinx HTML from staging_dir
    log_info "Step 4/4: Compiling Sphinx HTML using '$sphinx_cmd'..."
    if ! $sphinx_cmd -b html "$staging_dir" "$out_html"; then
        log_error "Sphinx build failed!"
        rm -rf "$staging_dir"
        return 1
    fi

    # Clean up staging directory after successful build
    rm -rf "$staging_dir"

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

# Action: sync / metadata (pre-validates format & synchronizes folders into metadata.json)
docs_cmd_sync() {
    local target_dir
    target_dir="$(resolve_docs_dir "${1:-}")"

    local py_cmd
    py_cmd="$(_docs_get_python_cmd)"
    if [ -z "$py_cmd" ]; then
        log_error "Python 3 is required to synchronize documentation metadata."
        return 1
    fi

    local sync_script
    sync_script="$(_docs_find_script "sync_metadata.py" "$target_dir")"
    if [ -z "$sync_script" ]; then
        log_error "'sync_metadata.py' engine not found!"
        return 1
    fi

    log_info "Pre-checking formatting and synchronizing documentation structure for '$target_dir'..."
    if ! "$py_cmd" "$sync_script" "$target_dir"; then
        log_error "Documentation synchronization failed due to formatting errors!"
        return 1
    fi

    return 0
}

# Helper: ensure all sphinx python scripts and shell utilities have execute permissions
_docs_ensure_script_permissions() {
    local base_dir="${MASTER_SCRIPT_DIR:-$SCRIPT_DIR}"
    local f
    for f in "$base_dir"/sphinx/*.sh "$base_dir"/sphinx/scripts/*.py; do
        if [ -f "$f" ] && [ ! -x "$f" ]; then
            chmod +x "$f" 2>/dev/null || true
        fi
    done
}

# Main command handler for 'telua docs <action>'
handle_docs_command() {
    local action="${1:-}"
    shift 2>/dev/null || true

    # Proactively ensure all docs scripts (.py and .sh) have execution permissions
    _docs_ensure_script_permissions

    case "$action" in
        init)
            docs_cmd_init "$@"
            ;;
        sync|metadata)
            docs_cmd_sync "$@"
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

