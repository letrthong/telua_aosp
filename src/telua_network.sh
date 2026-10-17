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
# telua_network.sh - Network, port & socket inspection utilities for the Telua
# toolkit.
# Single source of truth for the network-related commands of build_apk.sh:
#   - 'telua --network-help' / 'telua network' : show_network_help
#     (print const_network.config cheatsheet, then exit)
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_network.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, MASTER_SCRIPT_DIR, NETWORK_CONFIG_FILE,
#       NETWORK_CONFIG_FILE_NAME
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_NETWORK_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_NETWORK_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_NETWORK_SOURCED=1

# --- 4f. Network Help Utility (--network-help: frequently used Network & Port commands) ---
# Commands are read dynamically from const_network.config (located with build_apk.sh)
show_network_help() {
    if [ -f "$NETWORK_CONFIG_FILE" ]; then
        cat "$NETWORK_CONFIG_FILE"
    elif [ -f "$MASTER_SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME" ]; then
        cat "$MASTER_SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME"
    elif [ -f "$SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME" ]; then
        cat "$SCRIPT_DIR/$NETWORK_CONFIG_FILE_NAME"
    else
        log_warn "Network cheatsheet file '$NETWORK_CONFIG_FILE_NAME' not found!"
    fi
    exit 0
}
