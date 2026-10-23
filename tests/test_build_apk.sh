#!/bin/bash
# ==============================================================================
# Unit tests for build_apk.sh (Shell test harness)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAIN_SCRIPT="$REPO_ROOT/build_apk.sh"

PASSED=0
FAILED=0

log_test() {
    echo -e "\033[1;34m[TEST]\033[0m $1"
}

assert_success() {
    local name="$1"
    shift
    if "$@"; then
        echo -e "  \033[1;32m✓ PASS:\033[0m $name"
        PASSED=$((PASSED + 1))
    else
        echo -e "  \033[1;31m✗ FAIL:\033[0m $name"
        FAILED=$((FAILED + 1))
    fi
}

echo "============================================================"
echo " Running Shell Unit Tests for build_apk.sh"
echo " Target: $MAIN_SCRIPT"
echo "============================================================"

# Test 1: Syntax Validation
log_test "Validating Bash syntax (bash -n)..."
assert_success "Bash syntax is valid" bash -n "$MAIN_SCRIPT"

# Test 2: Version display
log_test "Testing version option (-v / --version)..."
out_ver=$("$MAIN_SCRIPT" -v 2>&1 || true)
assert_success "Version output contains version tag" grep -q "build_apk.sh v" <<< "$out_ver"

# Test 3: Help display
log_test "Testing help option (-h / --help)..."
out_help=$("$MAIN_SCRIPT" -h 2>&1 || true)
assert_success "Help output contains usage instructions" grep -E -q "Usage:.*telua" <<< "$out_help"
assert_success "Help lists build subcommand" grep -q "build, b" <<< "$out_help"
assert_success "Help lists init subcommand" grep -q "init" <<< "$out_help"

# Test 4: Find utilities
log_test "Testing search utilities (--find-file)..."
out_find=$("$MAIN_SCRIPT" --find-file "config_crypto.py" "$REPO_ROOT" 2>&1 || true)
assert_success "Find file locates config_crypto.py" grep -q "config_crypto.py" <<< "$out_find"

# Test 4c: Replace utilities
log_test "Testing replace utilities (telua replace)..."
TMP_REP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_replace_test.XXXXXX")
echo "Hello UNIQUE_FIND_ME_AAA world" > "$TMP_REP_DIR/test1.txt"
echo "Another UNIQUE_FIND_ME_AAA occurrence" > "$TMP_REP_DIR/test2.txt"

# Test replace across folder
out_rep=$("$MAIN_SCRIPT" replace "UNIQUE_FIND_ME_AAA" "UNIQUE_REPLACED_BBB" "$TMP_REP_DIR" 2>&1 || true)
assert_success "Replace completes successfully" grep -q "Replacement complete" <<< "$out_rep"
assert_success "Test1 file content replaced" grep -q "Hello UNIQUE_REPLACED_BBB world" "$TMP_REP_DIR/test1.txt"
assert_success "Test2 file content replaced" grep -q "Another UNIQUE_REPLACED_BBB occurrence" "$TMP_REP_DIR/test2.txt"

# Test replace on single file with --replace
echo "Single UNIQUE_SINGLE_AAA file" > "$TMP_REP_DIR/single.txt"
out_single=$("$MAIN_SCRIPT" --replace "UNIQUE_SINGLE_AAA" "UNIQUE_SINGLE_BBB" "$TMP_REP_DIR/single.txt" 2>&1 || true)
assert_success "Single file replace succeeded" grep -q "Single UNIQUE_SINGLE_BBB file" "$TMP_REP_DIR/single.txt"

# Test missing argument validation
out_missing=$("$MAIN_SCRIPT" replace "only_one" 2>&1 || true)
assert_success "Replace rejects missing new_text argument" grep -q "Missing arguments for replace" <<< "$out_missing"

rm -rf "$TMP_REP_DIR"

# Test 4d: Car ks device check
log_test "Testing car command device offline check (telua car ks)..."
out_car_ks=$("$MAIN_SCRIPT" car ks 2>&1 || true)
assert_success "Car ks reports device offline when disconnected" grep -qi "device offline" <<< "$out_car_ks"

# Test 4b: Clean-java utilities
log_test "Testing clean-java utilities (telua clean-java)..."
out_clean=$("$MAIN_SCRIPT" clean-java help 2>&1 || true)
assert_success "Clean-java help lists python/clean_java.py" grep -q "clean_java.py" <<< "$out_clean"
assert_success "Clean-java help lists diff mode" grep -q "clean-java diff" <<< "$out_clean"
assert_success "Clean-java help lists all mode" grep -q "clean-java all" <<< "$out_clean"

TMP_CLEAN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_clean_test.XXXXXX")
printf 'package com.example;\npublic class Foo { \n    int bar = 1;\t\n}\n' > "$TMP_CLEAN_DIR/Foo.java"
out_clean_all=$(cd "$TMP_CLEAN_DIR" && "$MAIN_SCRIPT" clean-java all 2>&1 || true)
assert_success "Clean-java all cleans .java files recursively" grep -q "Foo.java" <<< "$out_clean_all"
assert_success "Clean-java removed trailing whitespace" bash -c '! grep -q -E "[[:blank:]]+$" "$1"' bash "$TMP_CLEAN_DIR/Foo.java"
rm -rf "$TMP_CLEAN_DIR"

# Test 5: Safe personal config backup and restore logic
log_test "Testing personal config backup and restore isolation..."
TMP_TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_sh_test.XXXXXX")

# Create mock repo environment
mkdir -p "$TMP_TEST_DIR/config"
echo "TEST_OVERLAY=1" > "$TMP_TEST_DIR/apk_overlays.config"
echo "TEST_MY_CLI=1" > "$TMP_TEST_DIR/config/const_my_cli.config"
echo "EXAMPLE_OVERLAY=1" > "$TMP_TEST_DIR/apk_overlays.config.example"

# Extract and run backup/restore functions in subshell
(
    # Source minimal helpers from main script
    eval "$(grep '^PERSONAL_CONFIG_FILES=' "$MAIN_SCRIPT")"
    
    # Extract functions (init/update helpers now live in src/telua_untils.sh)
    UNTILS_SCRIPT="$REPO_ROOT/src/telua_untils.sh"
    extract_func() {
        awk -v f="$1" '$0 ~ "^"f"\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$UNTILS_SCRIPT"
    }
    
    eval "$(extract_func backup_personal_configs)"
    eval "$(extract_func restore_personal_configs)"
    eval "$(extract_func ensure_personal_configs)"
    eval "$(extract_func ensure_script_permissions)"
    
    log_info() { :; }
    log_success() { :; }
    log_warn() { :; }
    log_error() { :; }

    # Test backup
    b_dir="$(backup_personal_configs "$TMP_TEST_DIR")"
    [ -n "$b_dir" ] && [ -f "$b_dir/apk_overlays.config" ]

    # Simulate wipe
    rm -f "$TMP_TEST_DIR/apk_overlays.config"

    # Test restore
    restore_personal_configs "$TMP_TEST_DIR" "$b_dir"
    [ -f "$TMP_TEST_DIR/apk_overlays.config" ]
    [ "$(cat "$TMP_TEST_DIR/apk_overlays.config")" = "TEST_OVERLAY=1" ]
)
assert_success "Backup and restore preserves personal configs" [ $? -eq 0 ]

# Cleanup
rm -rf "$TMP_TEST_DIR"

# Test 6: Alias & completion installation into mock bashrc
log_test "Testing alias & completion installation (telua & tel)..."
TMP_HOME=$(mktemp -d "${TMPDIR:-/tmp}/telua_home_test.XXXXXX")
(
    export HOME="$TMP_HOME"
    out_inst=$("$MAIN_SCRIPT" install 2>&1 || true)
    grep -q "alias telua=" "$TMP_HOME/.bashrc" && \
    grep -q "alias tel=" "$TMP_HOME/.bashrc" && \
    grep -q "telua_completion.sh" "$TMP_HOME/.bashrc"
)
assert_success "Install adds aliases and tab completion" [ $? -eq 0 ]
rm -rf "$TMP_HOME"

echo "============================================================"
echo -e "Results: \033[1;32m$PASSED passed\033[0m, \033[1;31m$FAILED failed\033[0m"
echo "============================================================"

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
exit 0
