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
# telua_log.sh - Shared color logging helpers for the Telua toolkit.
# Single source of truth for log_info / log_success / log_warn / log_error,
# previously duplicated in build_apk.sh, src/telua_git.sh and
# src/telua_permission.sh.
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_log.sh"
#
# Notes:
#   - This file defines functions only; it has no CLI entry point and no
#     side effects, so it is always safe to source from any module.
#   - Guarded by TELUA_LOG_SOURCED so double-sourcing (e.g. build_apk.sh
#     sources it, then telua_git.sh sources it again) is a no-op and never
#     redefines an already-loaded copy.
#   - Colors use the same ANSI codes as the original inline definitions:
#     INFO=bold blue, SUCCESS=bold green, WARN=bold yellow, ERROR=bold red.

# Guard: skip re-definition when already sourced (idempotent).
# NOTE: must compare against "1" (not just non-empty) because callers may
# pre-set TELUA_LOG_SOURCED=0 before sourcing to track success/failure.
if [ "${TELUA_LOG_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_LOG_SOURCED=1

# Logging helpers with colors (single source of truth for the toolkit).
log_info()    { echo -e "\033[1;34m[INFO]\033[0m $*"; }
log_success() { echo -e "\033[1;32m[SUCCESS]\033[0m $*"; }
log_warn()    { echo -e "\033[1;33m[WARN]\033[0m $*"; }
log_error()   { echo -e "\033[1;31m[ERROR]\033[0m $*"; }
