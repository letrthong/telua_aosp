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
# telua_docker.sh - Docker daemon, container & image utilities for the Telua
# toolkit.
# Single source of truth for the docker-related commands of build_apk.sh:
#   - 'telua --docker-help' / 'telua docker' : show_docker_help
#     (print const_docker.config cheatsheet, then exit)
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_docker.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, MASTER_SCRIPT_DIR, DOCKER_CONFIG_FILE,
#       DOCKER_CONFIG_FILE_NAME
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_DOCKER_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_DOCKER_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_DOCKER_SOURCED=1

# --- 4e. Docker Help Utility (--docker-help: frequently used Docker commands) ---
# Commands are read dynamically from const_docker.config (located with build_apk.sh)
show_docker_help() {
    if [ -f "$DOCKER_CONFIG_FILE" ]; then
        cat "$DOCKER_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME" ]; then
        cat "$MASTER_SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME" ]; then
        cat "$SCRIPT_DIR/$DOCKER_CONFIG_FILE_NAME"
    else
        log_warn "Docker cheatsheet file '$DOCKER_CONFIG_FILE_NAME' not found!"
    fi
    exit 0
}
