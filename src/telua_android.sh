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
# telua_android.sh - Android build, deploy & device utilities for Telua.
# Single source of truth for the build/deploy/device/log pipeline previously
# inlined in build_apk.sh:
#   - resolve_android_paths      : locate ROOT_DIR / ANDROID_TOP / SOURCE_DIR
#   - setup_build_environment*   : envsetup + lunch (android)
#   - build_apk                  : clean + m <module> + copy APK out
#   - wait_for_device/_disconnect/_boot_completed, restart_framework
#   - ensure_adb_remount, acquire_root, is_deploy_path_writable
#   - deploy_android / deploy_apk (dispatcher)
#   - capture_logs_android / capture_logs (dispatcher)
# NOTE: QNX-specific placeholders (setup_build_environment_qnx, deploy_qnx,
# capture_logs_qnx) live in src/telua_qnx.sh.
#
# Usage (source, never execute):
#   source "$(dirname "${BASH_SOURCE[0]}")/src/telua_android.sh"
#
# All pipeline functions are parameter-driven: explicit arguments take
# precedence, global config variables (apk.config) are only used as defaults.
#
# Function signatures:
#   resolve_android_paths [start_dir]
#   setup_build_environment [platform]          ("android" | "qnx")
#   build_apk [module_name] [jobs]
#   wait_for_device [timeout_sec]               (default 180)
#   wait_for_boot_completed [timeout_sec]       (default 300)
#   restart_framework [timeout_sec]             (default 90)
#   ensure_adb_remount [deploy_path]
#   is_deploy_path_writable [deploy_path]
#   deploy_android [apk_file] [deploy_path] [no_reboot]
#   deploy_apk [platform] [deploy_enabled]
#   capture_logs_android [log_file] [filter]
#   capture_logs [platform] [deploy_enabled] [log_enabled]
#
# Contract with the sourcing (host) script:
#   - The host must define, BEFORE sourcing this file:
#       SCRIPT_DIR, CONFIG_FILE, CONFIG_FILE_NAME
#   - The host must have loaded the project config (variables like
#     ANDROID_TOP, SOURCE_CODE_RELATIVE_PATH, APK_OUTPUT_RELATIVE_PATH,
#     APK_FILE_NAME, MODULE_NAME, APK_DEPLOY_PATH, PLATFORM/TARGET_PLATFORM,
#     CONFIG_TARGET_PRODUCT, CONFIG_TARGET_BUILD_VARIANT, ENABLE_DEPLOY,
#     ENABLE_ANDROID_LOGCAT, LOGCAT_FILTER, ...) before calling these
#     functions.
#   - The host must provide resolve_build_jobs (sets BUILD_JOBS_RESOLVED /
#     BUILD_JOBS_SOURCE) and the logging helpers (log_info/log_success/
#     log_warn/log_error), e.g. by sourcing src/telua_log.sh first.
#   - Functions here only define behavior; they have no CLI entry point and
#     no side effects at source time, so sourcing is always safe.
#   - Guarded by TELUA_ANDROID_SOURCED so double-sourcing is a no-op and never
#     redefines an already-loaded copy.

# Guard: skip re-definition when already sourced (idempotent).
if [ "${TELUA_ANDROID_SOURCED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
TELUA_ANDROID_SOURCED=1

# --- 4. Resolve Android AOSP Top Directory ---
# Usage: resolve_android_paths [start_dir]
#   [start_dir] optional; defaults to the directory of $CONFIG_FILE, then $SCRIPT_DIR.
#   Sets globals: ROOT_DIR, ANDROID_TOP, SOURCE_DIR, DIR_OUT, APK_OUT.
resolve_android_paths() {
    local current_dir="${1:-}"
    if [ -z "$current_dir" ]; then
        if [ -f "$CONFIG_FILE" ]; then
            current_dir="$(cd "$(dirname "$CONFIG_FILE")" && pwd)"
        else
            current_dir="$SCRIPT_DIR"
        fi
    fi
    local android_dir=""

    while [ "$current_dir" != "/" ] && [ "$current_dir" != "." ]; do
        if [ "$(basename "$current_dir")" = "android" ]; then
            android_dir="$current_dir"
            break
        fi
        current_dir="$(dirname "$current_dir")"
    done

    if [ -z "$android_dir" ]; then
        log_error "Could not find the 'android' root directory in ancestor paths!"
        log_info "Must check apk.config"
        # 'return' (not 'exit') so callers like show_info can recover.
        return 1
    fi

    ROOT_DIR="$(dirname "$android_dir")"

    if [ -n "$AOSP_TOP_REL_PATH" ]; then
        ANDROID_TOP="$ROOT_DIR/$AOSP_TOP_REL_PATH"
    elif [ -d "$ROOT_DIR/android/qssi" ]; then
        ANDROID_TOP="$ROOT_DIR/android/qssi"
    else
        ANDROID_TOP="$android_dir"
    fi

    SOURCE_DIR="$ANDROID_TOP/$SOURCE_CODE_RELATIVE_PATH"
    DIR_OUT="$ANDROID_TOP/$APK_OUTPUT_RELATIVE_PATH"
    APK_OUT="$DIR_OUT/$APK_FILE_NAME"

    log_info "ROOT_DIR:    $ROOT_DIR"
    log_info "ANDROID_TOP: $ANDROID_TOP"
    log_info "SOURCE_DIR:  $SOURCE_DIR"
}

# --- 5a. Setup Android AOSP Build Environment ---
setup_build_environment_android() {
    cd "$ANDROID_TOP"

    local prod_var="${ENV_VAR_PRODUCT_NAME:-TARGET_PRODUCT}"
    local var_var="${ENV_VAR_VARIANT_NAME:-TARGET_BUILD_VARIANT}"
    local current_prod="${!prod_var}"
    local current_variant="${!var_var}"

    if [[ -n "$current_prod" && -n "$current_variant" ]]; then
        log_info "Build environment is already active:"
        log_info "$prod_var = $current_prod, $var_var = $current_variant"
        return 0
    fi

    if [ ! -f "build/envsetup.sh" ]; then
        log_error "Cannot find 'build/envsetup.sh' in $ANDROID_TOP"
        exit 1
    fi

    log_info "Initializing Android environment: source build/envsetup.sh"
    # envsetup.sh/lunch return non-zero on harmless warnings (e.g. symlink creation),
    # which 'set -e' would turn into an abort; success is verified via target env vars below.
    set +e
    source build/envsetup.sh

    local target="${CONFIG_TARGET_PRODUCT}-${CONFIG_TARGET_BUILD_VARIANT}"
    log_info "Running lunch target: $target"
    lunch "$target"
    set -e

    current_prod="${!prod_var}"
    current_variant="${!var_var}"

    if [[ -z "$current_prod" || -z "$current_variant" ]]; then
        log_error "Failed to initialize target environment variables ($prod_var, $var_var) after lunch."
        exit 1
    fi

    log_success "Android environment ready: $current_prod-$current_variant ($prod_var=$current_prod, $var_var=$current_variant)"
}

# (setup_build_environment_qnx lives in src/telua_qnx.sh)

# --- 5. Setup Build Environment Dispatcher ---
# Usage: setup_build_environment [platform]
#   [platform] optional; defaults to ${PLATFORM:-${TARGET_PLATFORM:-android}}
setup_build_environment() {
    local target_platform="${1:-${PLATFORM:-${TARGET_PLATFORM:-android}}}"
    case "$target_platform" in
        android)
            setup_build_environment_android
            ;;
        qnx)
            setup_build_environment_qnx
            ;;
        *)
            log_error "Unsupported build platform '$target_platform'! Supported: 'android' | 'qnx'"
            exit 1
            ;;
    esac
}

# --- 6. Compile APK Module ---
# Usage: build_apk [module_name] [jobs]
#   [module_name] optional; defaults to ${MODULE_NAME:-${APK_FILE_NAME%.apk}}
#   [jobs]        optional; defaults to resolve_build_jobs (RAM-aware auto scale)
build_apk() {
    local module_name="${1:-${MODULE_NAME:-${APK_FILE_NAME%.apk}}}"
    local jobs="${2:-}"

    log_info "Cleaning previous build output: $DIR_OUT"
    rm -rf "$DIR_OUT"

    log_info "Navigating to module source directory: $SOURCE_DIR"
    if [ ! -d "$SOURCE_DIR" ]; then
        log_error "Source directory does not exist: $SOURCE_DIR"
        exit 1
    fi

    cd "$SOURCE_DIR"
    # 'mm' builds every module under the directory, including tests/androidTest,
    # so build only the APK module (name = APK file name without .apk).
    if [ -z "$jobs" ]; then
        resolve_build_jobs
        jobs="$BUILD_JOBS_RESOLVED"
    fi
    log_info "Compiling module '$module_name' with m -j$jobs... [BUILD_JOBS source: ${BUILD_JOBS_SOURCE:-explicit}]"
    m "$module_name" -j"$jobs"

    if [ ! -f "$APK_OUT" ]; then
        log_error "APK not found at $APK_OUT after build completed."
        exit 1
    fi

    cp -fv "$APK_OUT" "$SCRIPT_DIR/"
    log_success "Build successful!"
    log_success "APK copied to: $SCRIPT_DIR/$APK_FILE_NAME"
}

# --- 7. Device Wait Utility ---
wait_for_device() {
    local timeout_sec="${1:-180}"
    local elapsed=0

    log_info "Waiting for device (timeout: ${timeout_sec}s)..."
    while [ "$elapsed" -lt "$timeout_sec" ]; do
        if adb get-state 2>/dev/null | grep -q "device"; then
            log_info "Device is online."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log_error "Timed out waiting for device after ${timeout_sec}s"
    return 1
}

# Block until the device drops off adb after 'adb reboot', so wait_for_device
# does not return early on the still-running old session.
wait_for_disconnect() {
    # Older platform-tools lack wait-for-disconnect: fall back to a short sleep.
    if ! timeout 30 adb wait-for-disconnect 2>/dev/null; then
        sleep 3
    fi
}

# After a full reboot, wait until Android reports boot completed.
# (Only valid after a real reboot: the property is reset at boot, but NOT by
# 'stop'/'start' - see restart_framework.)
wait_for_boot_completed() {
    local timeout_sec="${1:-300}"
    local elapsed=0

    log_info "Waiting for boot to complete (sys.boot_completed=1, timeout: ${timeout_sec}s)..."
    while [ "$elapsed" -lt "$timeout_sec" ]; do
        if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
            log_info "Boot completed after ${elapsed}s."
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    log_error "Boot did not complete within ${timeout_sec}s."
    return 1
}

# Restart the Android framework without a full reboot (--no-reboot).
# NOTE: sys.boot_completed usually stays "1" across 'stop'/'start', so it
# cannot detect readiness. Instead, wait for a NEW system_server PID and for
# PackageManager to answer.
restart_framework() {
    local timeout_sec="${1:-90}"
    local elapsed=0
    local old_pid new_pid

    old_pid=$(adb shell pidof system_server 2>/dev/null | tr -d '\r')
    log_info "Fast restart (--no-reboot): restarting Android framework (old system_server PID: ${old_pid:-none})..."
    adb shell stop
    sleep 1
    adb shell start

    log_info "Waiting for Android framework to be ready (timeout: ${timeout_sec}s)..."
    while [ "$elapsed" -lt "$timeout_sec" ]; do
        new_pid=$(adb shell pidof system_server 2>/dev/null | tr -d '\r')
        if [ -n "$new_pid" ] && [ "$new_pid" != "$old_pid" ] \
            && adb shell pm path android 2>/dev/null | grep -q "package:"; then
            log_info "Android framework is up (new system_server PID: $new_pid) after ${elapsed}s."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log_error "Android framework did not come back within ${timeout_sec}s."
    return 1
}

# --- 8. Ensure ADB Remount (Handles first-time reboot requirement) ---
# NOTE:
# 1. Device MUST run a 'userdebug' or 'eng' build image. Production 'user' builds
#    do not support 'adb root' or 'adb remount'.
# 2. First-time remount setup (dynamic partition / overlayfs) requires an automatic
#    reboot and may take ~3-5 mins before the system partition becomes writable.
# 3. Subsequent remounts will complete instantly in 1-2 seconds.
# Usage: ensure_adb_remount [deploy_path]
#   [deploy_path] optional; defaults to $APK_DEPLOY_PATH
ensure_adb_remount() {
    local deploy_path="${1:-$APK_DEPLOY_PATH}"

    # Verify userdebug / eng build variant first (getprop works without root),
    # so 'user' builds get a clear error instead of a failed 'adb root'.
    local build_type
    build_type=$(adb shell getprop ro.build.type 2>/dev/null | tr -d '\r')
    log_info "Detected device build variant: '${build_type:-unknown}'"
    if [ "$build_type" = "user" ]; then
        log_error "Device is running a 'user' build! 'adb remount' is forbidden on user builds."
        log_error "Please flash a 'userdebug' or 'eng' build image to enable deployment."
        exit 1
    fi

    log_info "Acquiring root access (adb root)..."
    acquire_root || exit 1

    log_info "Remounting partitions read-write (adb remount)..."
    local remount_output
    remount_output=$(adb remount 2>&1 || true)
    echo "$remount_output"

    # Trust an actual write test, not adb's message text (it varies by version).
    if is_deploy_path_writable; then
        log_success "Filesystem is writable."
        return 0
    fi

    # Not writable yet: first-time overlayfs/scratch setup needs a reboot.
    if echo "$remount_output" | grep -qiE "reboot|scratch"; then
        log_warn "First-time remount detected (overlayfs/scratch setup required)."
        log_info "Rebooting device now (this first-time initialization takes ~3-5 minutes)..."
        adb reboot
        wait_for_disconnect
        if ! wait_for_device 300; then
            log_error "Device did not come back online after remount reboot. Aborting."
            exit 1
        fi

        log_info "Device back online. Re-acquiring root and completing remount..."
        acquire_root || exit 1
        remount_output=$(adb remount 2>&1 || true)
        echo "$remount_output"
        if is_deploy_path_writable "$deploy_path"; then
            log_success "First-time remount setup complete. Filesystem is writable."
            return 0
        fi
    fi

    log_error "'$(dirname "$deploy_path")' is still read-only after 'adb remount'."
    log_error "See the remount output above (if verity is enabled: 'adb disable-verity' then reboot)."
    exit 1
}

# Wait until adbd actually runs as root (uid 0). 'adb root' restarts adbd, so a
# plain wait_for_device can return on the old, non-root session.
acquire_root() {
    local elapsed=0
    while [ "$elapsed" -lt 30 ]; do
        if [ "$(adb shell id -u 2>/dev/null | tr -d '\r')" = "0" ]; then
            log_info "adbd is running as root."
            return 0
        fi
        adb root >/dev/null 2>&1 || true
        sleep 2
        elapsed=$((elapsed + 2))
    done
    log_error "adbd is not running as root after 30s ('adb root' failed)."
    return 1
}

# Return 0 if the parent directory of the deploy path can be written to.
# Usage: is_deploy_path_writable [deploy_path]
#   [deploy_path] optional; defaults to $APK_DEPLOY_PATH
is_deploy_path_writable() {
    local deploy_path="${1:-$APK_DEPLOY_PATH}"
    local probe
    probe="$(dirname "$deploy_path")/.build_apk_rw_test"
    adb shell "touch '$probe' && rm -f '$probe'" >/dev/null 2>&1
}


# --- 9a. Deploy APK to Android Device (AOSP / ADB) ---
# Usage: deploy_android [apk_file] [deploy_path] [no_reboot]
#   [apk_file]    optional; defaults to $APK_FILE_NAME
#   [deploy_path] optional; defaults to $APK_DEPLOY_PATH
#   [no_reboot]   optional ("true"/"false"); defaults to ${NO_REBOOT:-false}
#               ("true" = fast framework restart instead of full reboot)
deploy_android() {
    local apk_file="${1:-$APK_FILE_NAME}"
    local deploy_path="${2:-$APK_DEPLOY_PATH}"
    local no_reboot="${3:-${NO_REBOOT:-false}}"

    echo ""
    log_info "============================================"
    log_info " Starting Deployment: Android Device (ADB)"
    log_info "============================================"

    if ! command -v adb >/dev/null 2>&1; then
        log_error "'adb' not found. Ensure Android platform-tools is in PATH."
        exit 1
    fi

    if ! wait_for_device 180; then
        log_error "Device did not become available before deployment. Aborting."
        exit 1
    fi

    ensure_adb_remount "$deploy_path"

    log_info "Pushing $apk_file to $deploy_path/$apk_file"
    adb push "$SCRIPT_DIR/$apk_file" "$deploy_path/$apk_file"
    adb shell chmod 644 "$deploy_path/$apk_file"
    # Remove old oat/dex cache if present to ensure updated code runs
    adb shell rm -rf "$deploy_path/oat" 2>/dev/null || true
    adb shell sync

    if [ "$ENABLE_DEBUG_LOG" = "true" ] && [ -n "$DEBUG_LOG_TAGS" ]; then
        local log_level="${DEBUG_LOG_LEVEL:-DEBUG}"
        log_info "Setting $log_level log properties for tags: $DEBUG_LOG_TAGS"
        for tag in $DEBUG_LOG_TAGS; do
            adb shell setprop persist.log.tag."$tag" "$log_level"
            adb shell setprop log.tag."$tag" "$log_level"
        done
        log_success "Debug log properties configured."
    fi

    # Clear old logcat buffer before restart so captured logs are 100% fresh
    local logcat_enabled="${ENABLE_ANDROID_LOGCAT:-${ENABLE_LOGCAT:-false}}"
    if [ "$logcat_enabled" = "true" ]; then
        log_info "Clearing previous device logcat buffer (adb logcat -c)..."
        adb logcat -c 2>/dev/null || true
    fi

    if [ "$no_reboot" = "true" ]; then
        if ! restart_framework 90; then
            log_error "Fast restart failed. Re-run without --no-reboot for a full reboot."
            exit 1
        fi
    else
        log_info "Rebooting device to apply changes..."
        adb reboot
        wait_for_disconnect

        log_info "Waiting for device to come back online after reboot (approx 2-3 mins)..."
        if ! wait_for_device 300; then
            log_error "Device did not come back online after reboot. Aborting."
            exit 1
        fi

        # adb comes online early in boot; wait until Android reports boot done.
        if ! wait_for_boot_completed 300; then
            log_error "Device did not finish booting after reboot. Aborting."
            exit 1
        fi
    fi

    adb devices
    log_success "Android deployment completed successfully."
}

# (deploy_qnx lives in src/telua_qnx.sh)

# --- 9. Deploy APK Dispatcher ---
# Usage: deploy_apk [platform] [deploy_enabled]
#   [platform]       optional; defaults to ${PLATFORM:-${TARGET_PLATFORM:-android}}
#   [deploy_enabled] optional ("true"/"false"); overrides the per-platform default
#                    chain (CLI_START_DEPLOY -> ENABLE_*_DEPLOY -> ENABLE_DEPLOY)
deploy_apk() {
    local target_platform="${1:-${PLATFORM:-${TARGET_PLATFORM:-android}}}"
    local deploy_enabled="${2:-}"
    case "$target_platform" in
        android)
            if [ -z "$deploy_enabled" ]; then
                deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_ANDROID_DEPLOY:-${ENABLE_DEPLOY:-true}}}"
            fi
            if [ "$deploy_enabled" != "true" ]; then
                log_info "Android deployment is disabled (ENABLE_ANDROID_DEPLOY='$deploy_enabled'), skipping."
                return 0
            fi
            deploy_android
            ;;
        qnx)
            if [ -z "$deploy_enabled" ]; then
                deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_QNX_DEPLOY:-${ENABLE_DEPLOY:-false}}}"
            fi
            if [ "$deploy_enabled" != "true" ]; then
                log_info "QNX deployment is disabled (ENABLE_QNX_DEPLOY='$deploy_enabled'), skipping."
                return 0
            fi
            deploy_qnx
            ;;
        *)
            log_error "Unsupported deployment platform '$target_platform'! Supported: 'android' | 'qnx'"
            exit 1
            ;;
    esac
}

# --- 10a. Android Logcat Capture ---
# Usage: capture_logs_android [log_file] [filter]
#   [log_file] optional; defaults to $SCRIPT_DIR/deployment_log.txt
#   [filter]   optional regex; defaults to $LOGCAT_FILTER (empty = full logcat)
capture_logs_android() {
    local log_file="${1:-$SCRIPT_DIR/deployment_log.txt}"
    local filter="${2:-$LOGCAT_FILTER}"

    # Give the app/service time to start and emit logs after boot/restart.
    local settle="${LOGCAT_SETTLE_SECONDS:-10}"
    log_info "Waiting ${settle}s for the app to start before capturing logcat..."
    sleep "$settle"

    if [ -n "$filter" ]; then
        log_info "Capturing logcat filtered by '$filter' to $log_file"
        adb logcat -d | grep -E "$filter" > "$log_file" || true
    else
        log_info "Capturing full logcat (no filter) to $log_file"
        adb logcat -d > "$log_file" || true
    fi

    local line_count
    line_count=$(wc -l < "$log_file" | tr -d ' ')
    if [ "$line_count" -eq 0 ]; then
        log_warn "Captured log is empty. The app may not have started yet or LOGCAT_FILTER matches nothing."
        log_warn "Try a larger LOGCAT_SETTLE_SECONDS in $CONFIG_FILE_NAME."
    fi
    log_success "Deployment log saved to $log_file ($line_count lines)"
}

# (capture_logs_qnx lives in src/telua_qnx.sh)

# --- 10. Log Capture Dispatcher ---
# Usage: capture_logs [platform] [deploy_enabled] [log_enabled]
#   [deploy_enabled] optional; overrides CLI_START_DEPLOY -> ENABLE_*_DEPLOY chain
#   [log_enabled]    optional; overrides ENABLE_*_LOGCAT / ENABLE_*_LOG chain
capture_logs() {
    local target_platform="${1:-${PLATFORM:-${TARGET_PLATFORM:-android}}}"
    local deploy_enabled="${2:-}"
    local log_enabled="${3:-}"
    case "$target_platform" in
        android)
            if [ -z "$deploy_enabled" ]; then
                deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_ANDROID_DEPLOY:-${ENABLE_DEPLOY:-true}}}"
            fi
            if [ -z "$log_enabled" ]; then
                log_enabled="${ENABLE_ANDROID_LOGCAT:-${ENABLE_LOGCAT:-false}}"
            fi
            if [ "$deploy_enabled" != "true" ] || [ "$log_enabled" != "true" ]; then
                return 0
            fi
            capture_logs_android
            ;;
        qnx)
            if [ -z "$deploy_enabled" ]; then
                deploy_enabled="${CLI_START_DEPLOY:-${ENABLE_QNX_DEPLOY:-${ENABLE_DEPLOY:-false}}}"
            fi
            if [ -z "$log_enabled" ]; then
                log_enabled="${ENABLE_QNX_LOG:-${ENABLE_LOGCAT:-false}}"
            fi
            if [ "$deploy_enabled" != "true" ] || [ "$log_enabled" != "true" ]; then
                return 0
            fi
            capture_logs_qnx
            ;;
        *)
            log_warn "Unknown platform '$target_platform', skipping log capture."
            ;;
    esac
}
