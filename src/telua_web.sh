#!/bin/bash
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Contribution History:
#   - 2026-11: Thong Le <letrthong@gmail.com> (Architecture & Domain Design)
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
# telua_web.sh - Web UI (Flask) module for the Telua toolkit.
# Single source of truth for the code behind 'telua web <action>':
#   - 'telua web start [port]' : install Flask if missing, launch the web UI
#                                server in the background & open the browser
#   - 'telua web stop'         : stop the background web UI server
#   - 'telua web status'       : show server state (PID, port, URL, health)
#   - 'telua web restart'      : stop + start
#   - 'telua web log'          : tail the server log file
#   - 'telua web help'         : this help
#
# Server engine : web/telua_web.py (Flask backend, stdlib-free besides Flask)
# Frontend      : web/static/ (index.html + app.js + style.css, vanilla JS)
# Default port  : 8788 (override via CLI arg or TELUA_WEB_PORT)
# PID / log file: .telua_web.pid / .telua_web.log (in the toolkit root)
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_web.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, MASTER_SCRIPT_DIR
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_WEB_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_WEB_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_WEB_SOURCED=1

# --- Web UI constants ---
WEB_DIR_NAME="web"
WEB_SERVER_PY="telua_web.py"
WEB_DEFAULT_PORT="${TELUA_WEB_PORT:-8788}"
WEB_PID_FILE=".telua_web.pid"
WEB_LOG_FILE=".telua_web.log"

# Resolve the toolkit root (dir containing web/), preferring MASTER_SCRIPT_DIR
# so softlinked workspaces all reuse the same master web UI.
_web_toolkit_root() {
    if [ -n "${MASTER_SCRIPT_DIR:-}" ] && [ -d "$MASTER_SCRIPT_DIR/$WEB_DIR_NAME" ]; then
        echo "$MASTER_SCRIPT_DIR"
        return 0
    fi
    if [ -n "${SCRIPT_DIR:-}" ] && [ -d "$SCRIPT_DIR/$WEB_DIR_NAME" ]; then
        echo "$SCRIPT_DIR"
        return 0
    fi
    # Fallback: parent of this src/ directory
    echo "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
}

# Locate the Flask server script. Returns empty string when missing.
_web_server_script() {
    local root
    root="$(_web_toolkit_root)"
    if [ -f "$root/$WEB_DIR_NAME/$WEB_SERVER_PY" ]; then
        echo "$root/$WEB_DIR_NAME/$WEB_SERVER_PY"
    fi
}

# Locate a usable python binary (python3 preferred, WindowsApps stubs skipped).
_web_get_python_cmd() {
    local py path_to_py
    for py in python3 python py; do
        path_to_py="$(command -v "$py" 2>/dev/null || true)"
        [ -z "$path_to_py" ] && continue
        case "$path_to_py" in
            *WindowsApps*) continue ;;
        esac
        if "$py" --version >/dev/null 2>&1; then
            echo "$py"
            return 0
        fi
    done
    echo ""
}

# Ensure Flask is importable; auto-install via pip when missing (opt-out via
# TELUA_WEB_SKIP_PIP=1). Returns 0 when Flask is available.
_web_ensure_flask() {
    local py_cmd="$1"
    if "$py_cmd" -c "import flask" >/dev/null 2>&1; then
        return 0
    fi
    if [ "${TELUA_WEB_SKIP_PIP:-0}" = "1" ]; then
        log_warn "Flask is missing and auto-install is disabled (TELUA_WEB_SKIP_PIP=1)."
        return 1
    fi
    log_warn "Flask is not installed. Installing via pip (one-time setup)..."
    if "$py_cmd" -m pip install flask >/dev/null 2>&1 \
        || "$py_cmd" -m pip install --user flask >/dev/null 2>&1; then
        log_success "Flask installed successfully."
        return 0
    fi
    log_error "Failed to install Flask automatically."
    log_error "Please run manually: $py_cmd -m pip install flask"
    return 1
}

# Read the stored server PID (empty when no valid pid file).
_web_server_pid() {
    local root
    root="$(_web_toolkit_root)"
    local pid_file="$root/$WEB_PID_FILE"
    [ -f "$pid_file" ] || { echo ""; return 0; }
    local pid
    pid="$(cat "$pid_file" 2>/dev/null | tr -d '[:space:]')"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "$pid"
    else
        # Stale pid file: clean it up.
        rm -f "$pid_file" 2>/dev/null || true
        echo ""
    fi
}

# Extract the bound port from the server log (fallback: default port).
_web_server_port() {
    local root
    root="$(_web_toolkit_root)"
    local port
    port="$(grep -oE 'http://[^ ]+:[0-9]+' "$root/$WEB_LOG_FILE" 2>/dev/null \
        | head -n1 | grep -oE '[0-9]+$')"
    echo "${port:-$WEB_DEFAULT_PORT}"
}

# Best-effort launch of the default browser (Linux / Windows / macOS).
_web_open_browser() {
    local url="$1"
    (
        sleep 1 2>/dev/null || true
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$url" >/dev/null 2>&1
        elif command -v open >/dev/null 2>&1; then
            open "$url" >/dev/null 2>&1
        elif command -v explorer.exe >/dev/null 2>&1; then
            explorer.exe "$url" >/dev/null 2>&1
        elif command -v cmd.exe >/dev/null 2>&1; then
            cmd.exe /c start "" "$url" >/dev/null 2>&1
        fi
    ) &
}

# Action: start (launch the Flask web UI server in the background)
web_cmd_start() {
    local port="${1:-$WEB_DEFAULT_PORT}"
    local root server_py py_cmd pid

    root="$(_web_toolkit_root)"
    server_py="$(_web_server_script)"
    if [ -z "$server_py" ]; then
        log_error "Web UI server not found: $root/$WEB_DIR_NAME/$WEB_SERVER_PY"
        log_error "The 'web/' directory is missing from the toolkit installation."
        return 1
    fi

    # Already running? Just report and exit.
    pid="$(_web_server_pid)"
    if [ -n "$pid" ]; then
        local running_port
        running_port="$(_web_server_port)"
        log_warn "Web UI is already running (PID: $pid, port: $running_port)."
        log_info "Open: http://localhost:$running_port  (use 'telua web stop' to stop it)"
        return 0
    fi

    py_cmd="$(_web_get_python_cmd)"
    if [ -z "$py_cmd" ]; then
        log_error "Python 3 is required to run the Web UI server."
        return 1
    fi
    if ! _web_ensure_flask "$py_cmd"; then
        return 1
    fi

    log_info "Starting Telua Web UI (Flask) on port $port..."
    log_info "Server script : $server_py"
    log_info "Toolkit root  : $root"
    log_info "Log file      : $root/$WEB_LOG_FILE"

    (
        cd "$root" || exit 1
        nohup "$py_cmd" "$server_py" --host 127.0.0.1 --port "$port" \
            > "$WEB_LOG_FILE" 2>&1 &
        echo $! > "$WEB_PID_FILE"
    )

    # Wait briefly for the server to accept connections (health probe).
    local elapsed=0 max_wait=15
    while [ "$elapsed" -lt "$max_wait" ]; do
        if command -v curl >/dev/null 2>&1; then
            if curl -sf "http://127.0.0.1:$port/api/ping" >/dev/null 2>&1; then
                break
            fi
        else
            sleep 2
            break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    pid="$(_web_server_pid)"
    if [ -z "$pid" ]; then
        log_error "Web UI server failed to start. Last log lines:"
        tail -n 15 "$root/$WEB_LOG_FILE" 2>/dev/null || true
        return 1
    fi

    echo ""
    log_success "Telua Web UI is running!"
    printf "  \033[1;37m%-14s\033[0m \033[1;32m%s\033[0m\n" "URL:" "http://localhost:$port"
    printf "  \033[1;37m%-14s\033[0m %s\n" "PID:" "$pid"
    printf "  \033[1;37m%-14s\033[0m %s\n" "Toolkit root:" "$root"
    printf "  \033[1;37m%-14s\033[0m %s\n" "Stop server:" "telua web stop"
    echo ""

    _web_open_browser "http://localhost:$port"
    return 0
}

# Action: stop (terminate the background server)
web_cmd_stop() {
    local pid
    pid="$(_web_server_pid)"
    if [ -z "$pid" ]; then
        log_info "Web UI server is not running."
        return 0
    fi
    log_info "Stopping Telua Web UI (PID: $pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$(_web_toolkit_root)/$WEB_PID_FILE" 2>/dev/null || true
    log_success "Web UI server stopped."
    return 0
}

# Action: status (show server state + health probe)
web_cmd_status() {
    local root pid port
    root="$(_web_toolkit_root)"
    pid="$(_web_server_pid)"

    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  TELUA WEB UI - SERVER STATUS\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    printf "  \033[1;37m%-14s\033[0m %s\n" "Toolkit root:" "$root"
    printf "  \033[1;37m%-14s\033[0m %s\n" "Server script:" "$root/$WEB_DIR_NAME/$WEB_SERVER_PY"

    if [ -n "$pid" ]; then
        port="$(_web_server_port)"
        printf "  \033[1;37m%-14s\033[0m \033[1;32mRUNNING (PID: %s)\033[0m\n" "State:" "$pid"
        printf "  \033[1;37m%-14s\033[0m \033[1;36mhttp://localhost:%s\033[0m\n" "URL:" "$port"
        if command -v curl >/dev/null 2>&1; then
            if curl -sf "http://127.0.0.1:$port/api/ping" >/dev/null 2>&1; then
                printf "  \033[1;37m%-14s\033[0m \033[1;32mhealthy (/api/ping OK)\033[0m\n" "Health:"
            else
                printf "  \033[1;37m%-14s\033[0m \033[1;33mno response on /api/ping\033[0m\n" "Health:"
            fi
        fi
    else
        printf "  \033[1;37m%-14s\033[0m \033[1;31mSTOPPED\033[0m\n" "State:"
        printf "  \033[1;37m%-14s\033[0m Run: \033[1;33mtelua web start\033[0m\n" "Start:"
    fi
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
    return 0
}

# Action: restart (stop + start)
web_cmd_restart() {
    local port="${1:-$WEB_DEFAULT_PORT}"
    web_cmd_stop
    sleep 1
    web_cmd_start "$port"
}

# Action: log (tail the server log)
web_cmd_log() {
    local root
    root="$(_web_toolkit_root)"
    local log_file="$root/$WEB_LOG_FILE"
    if [ ! -f "$log_file" ]; then
        log_warn "No log file found at $log_file (server never started?)."
        return 0
    fi
    log_info "Tailing $log_file (Ctrl+C to exit)..."
    tail -n 40 -f "$log_file"
}

# Help for 'telua web'
show_web_help() {
    echo ""
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "\033[1;32m  TELUA WEB — Config Manager Web UI (Flask)\033[0m"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo -e "  Usage: \033[1;33mtelua web <action> [port]\033[0m"
    echo ""
    echo -e "\033[1;33mAVAILABLE ACTIONS:\033[0m"
    printf "  \033[1;36m%-22s\033[0m %s\n" "start [port]" "Launch the Web UI server & open browser (default port: $WEB_DEFAULT_PORT)"
    printf "  \033[1;36m%-22s\033[0m %s\n" "stop" "Stop the background Web UI server"
    printf "  \033[1;36m%-22s\033[0m %s\n" "status" "Show server state (PID, port, URL, health)"
    printf "  \033[1;36m%-22s\033[0m %s\n" "restart [port]" "Restart the Web UI server"
    printf "  \033[1;36m%-22s\033[0m %s\n" "log" "Tail the server log file"
    printf "  \033[1;36m%-22s\033[0m %s\n" "help" "Show this help message"
    echo ""
    echo -e "\033[1;33mWHAT YOU CAN DO IN THE UI:\033[0m"
    echo -e "  \033[0;90m-\033[0m Browse & edit every \033[1;37m*.config\033[0m / \033[1;37m*.json\033[0m file (apk.config, const_*.config, ...)"
    echo -e "  \033[0;90m-\033[0m Syntax validation before save (bash -n / JSON) + automatic \033[1;37m.bak\033[0m backups"
    echo -e "  \033[0;90m-\033[0m Switch \033[1;37mACTIVE_PROJECT\033[0m profile (same as \033[1;33mtelua -p <name>\033[0m)"
    echo -e "  \033[0;90m-\033[0m Live status: toolkit version, ADB devices, system RAM"
    echo -e "  \033[0;90m-\033[0m Run \033[1;37mbuild_apk.sh --info\033[0m diagnostics from the browser"
    echo ""
    echo -e "\033[1;36m--------------------------------------------------------------------------------\033[0m"
    echo -e "  \033[0;90mServer engine :\033[0m $WEB_DIR_NAME/$WEB_SERVER_PY (Flask backend)"
    echo -e "  \033[0;90mFrontend      :\033[0m $WEB_DIR_NAME/static/ (vanilla JS, no build step)"
    echo -e "  \033[0;90mEnv overrides :\033[0m TELUA_WEB_PORT=8788  TELUA_WEB_SKIP_PIP=1"
    echo -e "\033[1;36m================================================================================\033[0m"
    echo ""
}

# Main command handler for 'telua web <action>'
handle_web_command() {
    local action="${1:-}"
    shift 2>/dev/null || true

    case "$action" in
        start|serve|run|up)
            web_cmd_start "$@"
            ;;
        stop|down|kill)
            web_cmd_stop
            ;;
        status)
            web_cmd_status
            ;;
        restart|reload)
            web_cmd_restart "$@"
            ;;
        log|logs)
            web_cmd_log
            ;;
        help|--help|-h|"")
            show_web_help
            ;;
        *)
            log_error "Unknown web action '$action'!"
            show_web_help
            exit 1
            ;;
    esac
}
