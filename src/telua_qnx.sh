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
# telua_qnx.sh - QNX platform support for the Telua toolkit.
# Single source of truth for the QNX-specific placeholders, extracted from
# src/telua_android.sh so future QNX implementation only touches this module:
#   - setup_build_environment_qnx : QNX SDP toolchain env (placeholder)
#   - deploy_qnx                  : deploy to QNX Hypervisor Android guest VM
#                                   (placeholder, planned qvm-control flow)
#   - capture_logs_qnx            : slog2 / slog2info capture (placeholder)
#
# Roadmap (when implementing for real):
#   1. setup_build_environment_qnx : source qnxsdp-env.sh, export QNX_TARGET /
#      QNX_HOST, verify qcc version.
#   2. deploy_qnx                  : adb connect <QNX_ANDROID_IP>:5555, push APK
#      into the Android guest VM via virtio-fs shared mount, fast-restart the
#      guest with qvm-control without rebooting the QNX host.
#   3. capture_logs_qnx            : ssh root@$QNX_HOST 'slog2info -t' capture.
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_qnx.sh"
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, CONFIG_FILE_NAME
#   - The host must have loaded the project config (QNX_HOST_IP/QNX_HOST,
#     QNX_SSH_PORT, ENABLE_QNX_DEPLOY, ENABLE_QNX_LOG, ...) before calling
#     these functions.
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_QNX_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_QNX_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_QNX_SOURCED=1

# --- 5b. Setup QNX Build Environment (SDP Toolchain) ---
setup_build_environment_qnx() {
    echo ""
    log_info "============================================"
    log_info " Setup QNX Build Environment (SDP Toolchain)"
    log_info "============================================"

    log_warn "Target platform is set to 'qnx'."
    log_info "QNX build toolchain initialization template:"
    log_info "  - Toolchain:    QNX Software Development Platform (SDP)"
    log_info "  - Environment:  source qnxsdp-env.sh / export QNX_TARGET & QNX_HOST"
    log_warn "QNX build environment setup is currently placeholder (will be supplemented later)."
    return 0
}

# --- 9b. Deploy APK to QNX Hypervisor (Android Guest VM) ---
deploy_qnx() {
    echo ""
    log_info "============================================"
    log_info " Starting Deployment: QNX Hypervisor"
    log_info "============================================"

    log_warn "Target platform is set to 'qnx'."
    log_warn "Direct deployment to QNX Hypervisor is currently under development (not yet supported)."
    log_info "Planned workflow for QNX Hypervisor:"
    log_info "  1. Connect ADB over virtual network (adb connect <QNX_ANDROID_IP>:5555)"
    log_info "  2. Push APK into Android Guest VM / shared virtio-fs mount"
    log_info "  3. Fast-restart Android Guest VM (qvm-control) without rebooting QNX host"
    log_warn "Skipping device deployment for now. APK module build completed successfully."
    return 0
}

# --- 10b. QNX Log Capture (slog2 / slog2info) ---
capture_logs_qnx() {
    echo ""
    log_info "============================================"
    log_info " QNX Log Capture: slog2 / slog2info"
    log_info "============================================"

    local qnx_log_file="$SCRIPT_DIR/qnx_deployment_log.txt"
    local qnx_host="${QNX_HOST_IP:-${QNX_HOST:-192.168.1.100}}"
    local qnx_port="${QNX_SSH_PORT:-22}"

    log_warn "Target platform is set to 'qnx'."
    log_info "QNX slog2 / slog2info capture workflow template:"
    log_info "  - Tool:         slog2info (QNX System Logger v2)"
    log_info "  - Target Host:  $qnx_host (SSH port: $qnx_port)"
    log_info "  - Output file:  $qnx_log_file"
    log_info "  - Command:      ssh -p $qnx_port root@$qnx_host 'slog2info -t' > $qnx_log_file"
    log_warn "slog2 log capture is currently paused (placeholder for future implementation)."
    # Future execution snippet:
    # ssh -p "$qnx_port" -o ConnectTimeout=5 "root@$qnx_host" "slog2info -t" > "$qnx_log_file" 2>/dev/null || true
    return 0
}
