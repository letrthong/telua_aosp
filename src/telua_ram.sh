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
# telua_ram.sh - RAM monitoring utilities for the Telua toolkit.
# Single source of truth for the memory monitoring code of build_apk.sh:
#   - get_mem_summary      : one-line memory summary from /proc/meminfo
#   - get_mem_used_mb      : current used RAM in MB (MemTotal - MemAvailable)
#   - get_mem_available_gb : current available RAM in GB (integer)
#   - get_ram_job_divisor  : build-job divisor (2/4/8) scaled by available RAM
#   - log_ram_snapshot     : log a labeled RAM snapshot (START / END)
#   - start_ram_sampler    : background sampler recording peak used RAM
#   - stop_ram_sampler     : stop the background sampler (safe to re-call)
#   - report_ram_summary   : END snapshot + peak usage report
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_ram.sh"
#
# Contract with the sourcing (host) script:
#   - The host must provide the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - The host controls the monitor via:
#       ENABLE_RAM_MONITOR  ("true"/"false", default "true")
#       RAM_SAMPLE_INTERVAL (seconds between samples, default 2)
#   - State variables owned by this module: RAM_SAMPLER_PID, RAM_PEAK_FILE.
#   - Typical host flow:
#       log_ram_snapshot "START"; start_ram_sampler
#       trap stop_ram_sampler EXIT
#       ... work ...
#       report_ram_summary
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_RAM_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_RAM_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_RAM_SOURCED=1

# --- RAM Monitoring (snapshot at start/end + peak usage sampler) ---
ENABLE_RAM_MONITOR="${ENABLE_RAM_MONITOR:-true}"
RAM_SAMPLE_INTERVAL="${RAM_SAMPLE_INTERVAL:-2}"
RAM_SAMPLER_PID=""
RAM_PEAK_FILE=""

# Summarize system memory from /proc/meminfo (values in kB -> GB)
get_mem_summary() {
    awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} /^SwapTotal:/ {st=$2} /^SwapFree:/ {sf=$2} END {
        printf "Total: %.2f GB | Used: %.2f GB | Avail: %.2f GB | Swap Used: %.2f GB",
               t/1048576, (t-a)/1048576, a/1048576, (st-sf)/1048576
    }' /proc/meminfo 2>/dev/null
}

# Current used RAM in MB (MemTotal - MemAvailable, the modern 'used' metric)
get_mem_used_mb() {
    awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} END {printf "%d", (t-a)/1024}' /proc/meminfo 2>/dev/null || echo 0
}

# Current available RAM in GB (integer, from MemAvailable)
get_mem_available_gb() {
    awk '/^MemAvailable:/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0
}

# Build-job divisor scaled by available RAM to avoid OOM during builds.
# Single source of truth for the RAM->parallelism policy:
#   avail > 80 GB  -> 2  (plenty of RAM, go fast:   nproc/2)
#   avail > 40 GB  -> 4  (moderate, be careful:     nproc/4)
#   avail <= 40 GB -> 8  (low RAM, be conservative: nproc/8)
# Echoes the divisor (2|4|8); always returns 0 so it is safe under 'set -e'.
get_ram_job_divisor() {
    local avail_gb
    avail_gb="$(get_mem_available_gb)"
    if [ "$avail_gb" -gt 80 ] 2>/dev/null; then
        echo 2
    elif [ "$avail_gb" -gt 40 ] 2>/dev/null; then
        echo 4
    else
        echo 8
    fi
}

log_ram_snapshot() {
    log_info "RAM [$1]: $(get_mem_summary)"
}

# Background sampler: records peak used RAM into a temp file while the build runs
start_ram_sampler() {
    [ "$ENABLE_RAM_MONITOR" = "true" ] || return 0
    RAM_PEAK_FILE="$(mktemp "${TMPDIR:-/tmp}/telua_ram_peak.XXXXXX")"
    echo 0 > "$RAM_PEAK_FILE"
    (
        peak=0
        while :; do
            used=$(get_mem_used_mb)
            if [ "$used" -gt "$peak" ] 2>/dev/null; then
                peak="$used"
                echo "$peak" > "$RAM_PEAK_FILE"
            fi
            sleep "$RAM_SAMPLE_INTERVAL"
        done
    ) &
    RAM_SAMPLER_PID=$!
    log_info "RAM monitor: peak sampler started (every ${RAM_SAMPLE_INTERVAL}s, PID: $RAM_SAMPLER_PID)"
}

# Stop the background sampler (safe to call multiple times)
stop_ram_sampler() {
    if [ -n "$RAM_SAMPLER_PID" ]; then
        kill "$RAM_SAMPLER_PID" 2>/dev/null || true
        wait "$RAM_SAMPLER_PID" 2>/dev/null || true
        RAM_SAMPLER_PID=""
    fi
}

# Final report: END snapshot + peak usage observed during the run
report_ram_summary() {
    stop_ram_sampler
    log_ram_snapshot "END"
    local peak
    peak="$(cat "$RAM_PEAK_FILE" 2>/dev/null || echo 0)"
    if [ -n "$RAM_PEAK_FILE" ] && [ -f "$RAM_PEAK_FILE" ]; then
        rm -f "$RAM_PEAK_FILE"
        RAM_PEAK_FILE=""
    fi
    if [ "${peak:-0}" -gt 0 ] 2>/dev/null; then
        log_success "RAM peak usage during this run: $(awk -v p="$peak" 'BEGIN {printf "%.2f GB (%d MB)", p/1024, p}')"
    else
        log_warn "RAM peak usage: no samples collected (ENABLE_RAM_MONITOR=$ENABLE_RAM_MONITOR)"
    fi
}
