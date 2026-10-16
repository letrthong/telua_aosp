#!/bin/bash
# ==============================================================================
# run_unittest_test.sh — Master Test Suite Runner for Telua Toolkit
# Triggered by: telua --test-mode true (or standalone execution)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for terminal output
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_BLUE="\033[1;34m"
C_GREEN="\033[1;32m"
C_RED="\033[1;31m"
C_YELLOW="\033[1;33m"

echo -e "${C_BLUE}======================================================================${C_RESET}"
echo -e "${C_BOLD} TELUA TOOLKIT — MASTER UNIT TEST SUITE${C_RESET}"
echo -e " Working Directory: $SCRIPT_DIR"
echo -e "${C_BLUE}======================================================================${C_RESET}"
echo ""

TOTAL_SUITES=2
SUITES_PASSED=0

# ------------------------------------------------------------------------------
# 1. Run Python Unit Tests (config_crypto.py & config_overlay.py)
# ------------------------------------------------------------------------------
echo -e "${C_YELLOW}[SUITE 1/2] Running Python Unit Tests...${C_RESET}"
chmod +x test_*.py 2>/dev/null || true

PYTHON_BIN=""
for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${C_RED}[ERROR] No working Python 3 binary found in PATH!${C_RESET}"
    exit 1
fi

if "$PYTHON_BIN" -m unittest discover -s "$SCRIPT_DIR" -p "test_*.py" -v; then
    echo -e "${C_GREEN}✓ Python Unit Tests Passed!${C_RESET}\n"
    SUITES_PASSED=$((SUITES_PASSED + 1))
else
    echo -e "${C_RED}✗ Python Unit Tests Failed!${C_RESET}\n"
fi

# ------------------------------------------------------------------------------
# 2. Run Shell Unit Tests (build_apk.sh)
# ------------------------------------------------------------------------------
echo -e "${C_YELLOW}[SUITE 2/2] Running Shell Unit Tests...${C_RESET}"
chmod +x test_build_apk.sh 2>/dev/null || true

if ./test_build_apk.sh; then
    echo -e "${C_GREEN}✓ Shell Unit Tests Passed!${C_RESET}\n"
    SUITES_PASSED=$((SUITES_PASSED + 1))
else
    echo -e "${C_RED}✗ Shell Unit Tests Failed!${C_RESET}\n"
fi

# ------------------------------------------------------------------------------
# Final Test Summary
# ------------------------------------------------------------------------------
echo -e "${C_BLUE}======================================================================${C_RESET}"
if [ "$SUITES_PASSED" -eq "$TOTAL_SUITES" ]; then
    echo -e "${C_GREEN}${C_BOLD}🎉 ALL UNIT TEST SUITES PASSED ($SUITES_PASSED/$TOTAL_SUITES)!${C_RESET}"
    echo -e "${C_BLUE}======================================================================${C_RESET}"
    exit 0
else
    echo -e "${C_RED}${C_BOLD}❌ TEST SUITES FAILED ($SUITES_PASSED/$TOTAL_SUITES PASSED)!${C_RESET}"
    echo -e "${C_BLUE}======================================================================${C_RESET}"
    exit 1
fi
