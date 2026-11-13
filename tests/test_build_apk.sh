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
assert_success "Help lists test subcommand" grep -q "test, t" <<< "$out_help"
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

# Test 4b: Java utilities (telua java / clean-java)
log_test "Testing java utilities (telua java / clean-java)..."
out_clean=$("$MAIN_SCRIPT" java help 2>&1 || true)
assert_success "Java help lists python/clean_java.py" grep -q "clean_java.py" <<< "$out_clean"
assert_success "Java help lists diff mode" grep -q "clean-java diff" <<< "$out_clean"
assert_success "Java help lists all mode" grep -q "clean-java all" <<< "$out_clean"

TMP_CLEAN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_clean_test.XXXXXX")
printf 'package com.example;\npublic class Foo { \n    int bar = 1;\t\n}\n' > "$TMP_CLEAN_DIR/Foo.java"
out_clean_all=$(cd "$TMP_CLEAN_DIR" && "$MAIN_SCRIPT" java all 2>&1 || true)
assert_success "Java all cleans .java files recursively" grep -q "Foo.java" <<< "$out_clean_all"
assert_success "Java removed trailing whitespace" bash -c '! grep -q -E "[[:blank:]]+$" "$1"' bash "$TMP_CLEAN_DIR/Foo.java"
rm -rf "$TMP_CLEAN_DIR"

# Test 4c: Unused-method report (telua java report / clean-java report)
log_test "Testing unused-method report (telua java report)..."
TMP_REPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_report_test.XXXXXX")
mkdir -p "$TMP_REPORT_DIR/src/com/example"
cat > "$TMP_REPORT_DIR/src/com/example/Dead.java" <<'EOF'
package com.example;
public class Dead {
    private void entryPoint() { usedMethod(); }
    private void usedMethod() { helper(); }
    private void helper() { }
    private void deadMethod() { }
}
EOF
out_report=$(cd "$TMP_REPORT_DIR" && "$MAIN_SCRIPT" java report src/com/example/Dead.java 2>&1 || true)
assert_success "Report runs and finds unused method" grep -q "deadMethod" <<< "$out_report"
assert_success "Report does not flag used method" bash -c '! grep -q "usedMethod  (" <<< "$1" || grep -q "No unused" <<< "$1"' bash <<< "$out_report"
assert_success "Report does not flag helper called from usedMethod" bash -c '! grep -q "helper  (" <<< "$1"' bash <<< "$out_report"

# Test 4c-1b: Whitespace violations must be reported (read-only preview)
printf 'package com.example;\npublic class Dirty {\n    private void dirtyMethod() { \n        if(x) { }\n\n\n    }\n\tint y = 1;\n}\n' > "$TMP_REPORT_DIR/src/com/example/Dirty.java"
out_report_ws=$(cd "$TMP_REPORT_DIR" && "$MAIN_SCRIPT" clean-java report src/com/example/Dead.java 2>&1 || true)
assert_success "Report lists trailing whitespace" grep -q "trailing whitespace" <<< "$out_report_ws"
assert_success "Report lists keyword-paren spacing" grep -q "keyword-paren" <<< "$out_report_ws"
assert_success "Report lists blank line run" grep -q "blank line run" <<< "$out_report_ws"
assert_success "Report lists leading tab" grep -q "leading tab" <<< "$out_report_ws"

# Test 4c-2: JUnit test code must not be reported as unused (framework-invoked)
cat > "$TMP_REPORT_DIR/src/com/example/DeadTest.java" <<'EOF'
package com.example;
import org.junit.Test;
public class DeadTest {
    @Test
    public void frameworkInvokedTest() { }
    private void plainHelper() { }
}
EOF
mkdir -p "$TMP_REPORT_DIR/src/tests"
cat > "$TMP_REPORT_DIR/src/tests/PathBasedTest.java" <<'EOF'
package tests;
public class PathBasedTest {
    public void frameworkInvokedToo() { }
}
EOF
out_report2=$(cd "$TMP_REPORT_DIR" && "$MAIN_SCRIPT" clean-java report src/com/example/Dead.java 2>&1 || true)
assert_success "Report skips @Test-annotated methods" bash -c '! grep -q "frameworkInvokedTest  (" <<< "$1"' bash <<< "$out_report2"
assert_success "Report skips JUnit test files (content)" bash -c '! grep -q "plainHelper  (" <<< "$1"' bash <<< "$out_report2"
assert_success "Report skips test directories (path)" bash -c '! grep -q "frameworkInvokedToo  (" <<< "$1"' bash <<< "$out_report2"
assert_success "Report still finds production dead method" grep -q "deadMethod" <<< "$out_report2"
assert_success "Report includes [4] google-java-format violations section" grep -q "\[4\] google-java-format violations" <<< "$out_report2"
assert_success "Report includes [5] Unused imports section" grep -q "\[5\] Unused imports" <<< "$out_report2"
assert_success "Report includes [6] Unused private fields section" grep -q "\[6\] Unused private fields" <<< "$out_report2"
rm -rf "$TMP_REPORT_DIR"

# Test 4e: Profile switching (-p / --profile) updates apk.config and rejects invalid profile
log_test "Testing profile switch (-p / --profile)..."
TMP_PROF_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_profile_test.XXXXXX")
cp "$REPO_ROOT/config/apk.config" "$TMP_PROF_DIR/apk.config"
out_prof=$("$MAIN_SCRIPT" info --config "$TMP_PROF_DIR/apk.config" -p car_audio 2>&1 || true)
assert_success "Profile switch (-p car_audio) updates ACTIVE_PROJECT in apk.config" grep -q 'ACTIVE_PROJECT="car_audio"' "$TMP_PROF_DIR/apk.config"
assert_success "Info output reflects switched CarAudioService module" grep -q "CarAudioService" <<< "$out_prof"

out_bad_prof=$("$MAIN_SCRIPT" info --config "$TMP_PROF_DIR/apk.config" -p non_existent_profile 2>&1 || true)
assert_success "Invalid profile is rejected with error" grep -q "Unknown ACTIVE_PROJECT" <<< "$out_bad_prof"
assert_success "Invalid profile does not corrupt apk.config" grep -q 'ACTIVE_PROJECT="car_audio"' "$TMP_PROF_DIR/apk.config"
rm -rf "$TMP_PROF_DIR"

# Test 5: Safe personal config backup and restore logic
log_test "Testing personal config backup and restore isolation..."
TMP_TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_sh_test.XXXXXX")

# Create mock repo environment (personal configs live in config/overlay/)
mkdir -p "$TMP_TEST_DIR/config/overlay"
echo "TEST_OVERLAY=1" > "$TMP_TEST_DIR/config/overlay/apk_overlays.config"
echo "TEST_MY_CLI=1" > "$TMP_TEST_DIR/config/overlay/const_my_cli.config"
echo "EXAMPLE_OVERLAY=1" > "$TMP_TEST_DIR/config/overlay/apk_overlays.config.example"

# Extract and run backup/restore functions in subshell
(
    # Source minimal helpers from main script
    eval "$(grep '^PERSONAL_CONFIG_FILES=' "$MAIN_SCRIPT")"
    
    # Extract functions (init/update helpers now live in src/telua_utils.sh)
    UTILS_SCRIPT="$REPO_ROOT/src/telua_utils.sh"
    extract_func() {
        awk -v f="$1" '$0 ~ "^"f"\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$UTILS_SCRIPT"
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
    [ -n "$b_dir" ] && [ -f "$b_dir/config/overlay/apk_overlays.config" ]

    # Simulate wipe
    rm -f "$TMP_TEST_DIR/config/overlay/apk_overlays.config"

    # Test restore
    restore_personal_configs "$TMP_TEST_DIR" "$b_dir"
    [ -f "$TMP_TEST_DIR/config/overlay/apk_overlays.config" ]
    [ "$(cat "$TMP_TEST_DIR/config/overlay/apk_overlays.config")" = "TEST_OVERLAY=1" ]
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

# Test 6b: Tab completion for top-level (java, web), subcommands, -p/--profile and -t/--template
log_test "Testing tab completion for java, web, -p/--profile and -t/--template..."
(
    source "$REPO_ROOT/src/telua_completion.sh"
    COMP_WORDS=(tel "")
    COMP_CWORD=1
    _telua_completions
    echo " ${COMPREPLY[*]} " | grep -q " java " && \
    echo " ${COMPREPLY[*]} " | grep -q " web " && \
    echo " ${COMPREPLY[*]} " | grep -q " crypto " && \
    ! echo " ${COMPREPLY[*]} " | grep -q " clean-java " && \
    COMP_WORDS=(tel crypto "") && \
    COMP_CWORD=2 && \
    _telua_completions && \
    echo " ${COMPREPLY[*]} " | grep -q " encrypt " && \
    echo " ${COMPREPLY[*]} " | grep -q " decrypt " && \
    COMP_WORDS=(tel web "") && \
    COMP_CWORD=2 && \
    _telua_completions && \
    echo " ${COMPREPLY[*]} " | grep -q " start " && \
    echo " ${COMPREPLY[*]} " | grep -q " restart " && \
    COMP_WORDS=(tel java "") && \
    COMP_CWORD=2 && \
    _telua_completions && \
    echo " ${COMPREPLY[*]} " | grep -q " report " && \
    echo " ${COMPREPLY[*]} " | grep -q " skill " && \
    COMP_WORDS=(tel b -p "") && \
    COMP_CWORD=3 && \
    _telua_completions && \
    echo "${COMPREPLY[*]}" | grep -q "car_audio" && \
    COMP_WORDS=(tel docs init -t "") && \
    COMP_CWORD=4 && \
    _telua_completions && \
    echo "${COMPREPLY[*]}" | grep -q "architecture"
)
assert_success "Tab completion resolves java, web, subcommands, -p profiles and -t templates" [ $? -eq 0 ]

# Test 6c: Private overlay crypto CLI (telua crypto status, enc, dec)
log_test "Testing private overlay crypto CLI (telua crypto, enc, dec)..."
TMP_CRYPTO_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_crypto_cli_test.XXXXXX")
(
    # 1. Empty dir -> status shows NOT CREATED and enc fails fast
    status_out=$("$MAIN_SCRIPT" crypto status -d "$TMP_CRYPTO_DIR" 2>&1)
    echo "$status_out" | grep -q "NOT CREATED" && \
    ! "$MAIN_SCRIPT" enc "TestPw123" -d "$TMP_CRYPTO_DIR" >/dev/null 2>&1 && \
    # 2. Create private files -> status shows UNENCRYPTED, enc encrypts both, dec decrypts both
    printf 'ACTIVE_PROJECT="car_audio"\n' > "$TMP_CRYPTO_DIR/apk_overlays.config" && \
    printf 'MY_GROUP_LIST=("demo :: echo hi")\n' > "$TMP_CRYPTO_DIR/const_my_cli.config" && \
    status_unenc=$("$MAIN_SCRIPT" crypto status -d "$TMP_CRYPTO_DIR" 2>&1) && \
    echo "$status_unenc" | grep -q "UNENCRYPTED" && \
    "$MAIN_SCRIPT" enc "TestPw123" -d "$TMP_CRYPTO_DIR" >/dev/null 2>&1 && \
    [ -f "$TMP_CRYPTO_DIR/enc_apk_overlays.config" ] && \
    [ -f "$TMP_CRYPTO_DIR/enc_const_my_cli.config" ] && \
    rm -f "$TMP_CRYPTO_DIR/apk_overlays.config" "$TMP_CRYPTO_DIR/const_my_cli.config" && \
    "$MAIN_SCRIPT" dec "TestPw123" -d "$TMP_CRYPTO_DIR" >/dev/null 2>&1 && \
    grep -q 'ACTIVE_PROJECT="car_audio"' "$TMP_CRYPTO_DIR/apk_overlays.config" && \
    grep -q 'MY_GROUP_LIST=' "$TMP_CRYPTO_DIR/const_my_cli.config"
)
assert_success "Crypto CLI checks existence, encrypts and decrypts private overlay configs" [ $? -eq 0 ]
rm -rf "$TMP_CRYPTO_DIR"

# Test 7: Documentation module (telua docs help, init, check)
log_test "Testing documentation module (telua docs help, init, check)..."
TMP_DOCS_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telua_docs_test.XXXXXX")
(
    export TELUA_DOCS_SKIP_PIP=1
    # Check help output contains start and serve
    help_out=$("$MAIN_SCRIPT" docs help 2>&1)
    echo "$help_out" | grep -q "start \[port\]" && \
    echo "$help_out" | grep -q "serve \[port\]" && \
    # Init into temp directory (verify non-interactive default fallback and explicit -t basic)
    "$MAIN_SCRIPT" docs init "$TMP_DOCS_DIR" </dev/null >/dev/null 2>&1 && \
    [ -f "$TMP_DOCS_DIR/conf.py" ] && \
    [ -f "$TMP_DOCS_DIR/index.rst" ] && \
    [ -f "$TMP_DOCS_DIR/metadata.json" ] && \
    [ ! -f "$TMP_DOCS_DIR/requirements.txt" ] && \
    [ ! -f "$TMP_DOCS_DIR/check_sections.py" ] && \
    [ ! -f "$TMP_DOCS_DIR/merge_docs.py" ] && \
    # Check documentation validity
    "$MAIN_SCRIPT" docs check "$TMP_DOCS_DIR" >/dev/null 2>&1 && \
    # Add new section to chapter1
    printf "New Section\n-----------\nBody content\n" > "$TMP_DOCS_DIR/chapter1/chapter1_section3.rst" && \
    # Test auto-sync
    "$MAIN_SCRIPT" docs sync "$TMP_DOCS_DIR" >/dev/null 2>&1 && \
    grep -q "chapter1_section3.rst" "$TMP_DOCS_DIR/metadata.json" && \
    grep -q "must update" "$TMP_DOCS_DIR/metadata.json" && \
    # Test format error detection (illegal spaces in filename)
    touch "$TMP_DOCS_DIR/chapter1/bad filename space.rst" && \
    ! "$MAIN_SCRIPT" docs sync "$TMP_DOCS_DIR" >/dev/null 2>&1 && \
    rm -f "$TMP_DOCS_DIR/chapter1/bad filename space.rst" && \
    "$MAIN_SCRIPT" docs sync "$TMP_DOCS_DIR" >/dev/null 2>&1
)
assert_success "Documentation module initializes, validates format and auto-syncs metadata" [ $? -eq 0 ]
rm -rf "$TMP_DOCS_DIR"

echo "============================================================"
echo -e "Results: \033[1;32m$PASSED passed\033[0m, \033[1;31m$FAILED failed\033[0m"
echo "============================================================"

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
exit 0

