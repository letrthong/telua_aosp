# ==============================================================================
# Copyright (C) 2026 letrthong@gmail.com
# Created & Maintained by: letrthong@gmail.com
# Generated & Refactored by: Gemini 3.6 Pro (Google DeepMind)
# Licensed under the Apache License, Version 2.0
# ==============================================================================

import os
import re
import sys
import subprocess

def print_help():
    """Print CLI usage helper menu."""
    help_text = """
==============================================================================
Copyright (C) 2026 letrthong@gmail.com
Clean Code Whitespace Tool for Java/Android (clean_java.py)
==============================================================================

Description:
  Scans Java source files and enforces whitespace hygiene:
    1. Expands leading tabs (indentation) to 4 spaces per tab.
    2. Strips trailing whitespace & tabs from every line (CRLF -> LF).
    3. Trims trailing blank lines; the file ends with exactly one newline.
    4. Normalizes control-flow keyword spacing: exactly one space between
       the keyword and '(' (if(x) -> if (x)) and no redundant whitespace
       inside the parentheses (if ( x ) -> if (x), catch ( Exception e ) ->
       catch (Exception e), ...). String literals and comments are never
       modified; multi-line conditions are left untouched.
    5. Collapses runs of 2+ consecutive blank lines into a single blank line.
  Files that are already clean are skipped (not rewritten).

Config:
  config/const_clean_java.config (optional, bash-style KEY="VALUE") controls:
    ENSURE_TRAILING_NEWLINE, TAB_WIDTH, FIX_KEYWORD_PAREN_SPACING,
    COLLAPSE_BLANK_LINES. Missing file/keys fall back to built-in defaults.

Usage:
  python clean_java.py [OPTION | FILE_PATH | DIR_PATH]

Options:
  --diff, --git-diff    (Default) Clean trailing whitespace ONLY for Git modified/added .java files.
  --all                 Recursively scan and clean ALL .java files in the current workspace.
  <file_path>           Clean trailing whitespace for a specific target .java file.
  <dir_path>            Recursively scan and clean ALL .java files inside the specified directory.
  -h, --help            Show this CLI help message and exit.

Examples:
  python clean_java.py --diff
  python clean_java.py Java_Android/examples/SingletonTemplate.java
  python clean_java.py Java_Android/examples/
  python clean_java.py --all
==============================================================================
"""
    print(help_text.strip())

# ------------------------------------------------------------------------------
# Settings: defaults below are overridden by config/const_clean_java.config
# (bash-style KEY="VALUE" lines, '#' comments). The config file is optional.
# ------------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLEAN_JAVA_CONFIG_FILE = os.path.normpath(
    os.path.join(SCRIPT_DIR, '..', 'config', 'const_clean_java.config'))

SETTINGS = {
    'ENSURE_TRAILING_NEWLINE': '1',    # 1 = file ends with exactly one newline
    'TAB_WIDTH': '4',                  # spaces per leading tab (indentation)
    'FIX_KEYWORD_PAREN_SPACING': '1',  # 1 = if(x) -> if (x), if ( x ) -> if (x)
    'COLLAPSE_BLANK_LINES': '1',       # 1 = 2+ blank lines -> one blank line
}


def _load_clean_java_config(path=CLEAN_JAVA_CONFIG_FILE):
    """Merge KEY="VALUE" entries from const_clean_java.config into SETTINGS,
    then re-apply the module-level constants (TAB_WIDTH, ENSURE_TRAILING_NEWLINE,
    FIX_KEYWORD_PAREN_SPACING, COLLAPSE_BLANK_LINES).

    Unknown keys, comments and blank lines are ignored; a missing or
    unreadable config file silently keeps the built-in defaults.
    """
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'").strip()
                    if key in SETTINGS and value:
                        SETTINGS[key] = value
        except OSError:
            pass  # fall back to built-in defaults
    _apply_settings()


def _apply_settings():
    """Derive the module-level constants from the merged SETTINGS dict."""
    global TAB_WIDTH, ENSURE_TRAILING_NEWLINE
    global FIX_KEYWORD_PAREN_SPACING, COLLAPSE_BLANK_LINES
    TAB_WIDTH = int(SETTINGS['TAB_WIDTH'])
    ENSURE_TRAILING_NEWLINE = SETTINGS['ENSURE_TRAILING_NEWLINE'] == '1'
    FIX_KEYWORD_PAREN_SPACING = SETTINGS['FIX_KEYWORD_PAREN_SPACING'] == '1'
    COLLAPSE_BLANK_LINES = SETTINGS['COLLAPSE_BLANK_LINES'] == '1'


_load_clean_java_config()
# Control-flow keywords whose header parentheses get normalized:
#   - exactly one space between the keyword and '(' (Google Java Style:
#     'if (' not 'if(')
#   - no redundant whitespace just after '(' or just before the matching
#     ')' ('if ( x )' -> 'if (x)')
# All of these are Java reserved words, so they can never be part of an
# identifier before '('.
KEYWORD_PAREN_RE = re.compile(
    r'\b(if|for|while|switch|catch|try|synchronized)([ \t]*)(\()')


def _expand_leading_tabs(line, tab_width=TAB_WIDTH):
    """Replace each leading tab (indentation) with `tab_width` spaces.

    Only the leading whitespace run is expanded, so literal tabs inside
    string literals or comment text are never modified.
    """
    out = []
    in_leading_ws = True
    for ch in line:
        if in_leading_ws:
            if ch == '\t':
                out.append(' ' * tab_width)
                continue
            if ch != ' ':
                in_leading_ws = False
        out.append(ch)
    return ''.join(out)


def _mask_non_code(line, in_block_comment):
    """Return a same-length copy of `line` where string/char literal contents
    and comments are replaced by spaces, so keyword regexes only see real
    code. `in_block_comment` carries the /* ... */ state across lines.
    """
    out = list(line)
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_block_comment:
            if ch == '*' and i + 1 < n and line[i + 1] == '/':
                in_block_comment = False
                i += 2
                continue
            out[i] = ' '
            i += 1
            continue
        if ch == '/' and i + 1 < n and line[i + 1] == '/':
            for j in range(i, n):
                out[j] = ' '
            break
        if ch == '/' and i + 1 < n and line[i + 1] == '*':
            out[i] = out[i + 1] = ' '
            in_block_comment = True
            i += 2
            continue
        if ch in ('"', "'"):
            quote = ch
            out[i] = ' '
            i += 1
            while i < n:
                if line[i] == '\\' and i + 1 < n:
                    out[i] = out[i + 1] = ' '
                    i += 2
                    continue
                out[i] = ' '
                if line[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        i += 1
    return ''.join(out), in_block_comment


def _find_matching_paren(masked, open_idx):
    """Return the index of the ')' matching the '(' at `open_idx` in the
    masked code text, or -1 when it is not on the same line (the condition
    continues on the next line). Parens inside string literals or comments
    are masked out, so they never affect the depth count.
    """
    depth = 0
    for i in range(open_idx, len(masked)):
        ch = masked[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _strip_paren_edge_whitespace(text, masked, start, end):
    """Within text[start:end] (a balanced, single-line code region), remove
    whitespace directly after every '(' and directly before every ')'.
    Parens are located through `masked`, so string literals and comments
    are never modified.
    """
    out = []
    i = start
    while i < end:
        mc = masked[i]
        if mc == '(':
            out.append(text[i])
            i += 1
            while i < end and text[i] in ' \t':
                i += 1
        elif mc == ')':
            while out and out[-1] in ' \t':
                out.pop()
            out.append(text[i])
            i += 1
        else:
            out.append(text[i])
            i += 1
    return ''.join(out)


def _fix_keyword_paren_spacing(line, in_block_comment):
    """Normalize spacing of control-flow headers on one line:
      - exactly one space between keyword and '('  (if(x)    -> if (x))
      - no whitespace after '(' / before ')'       (if ( x ) -> if (x))
    e.g. 'if ( contextId == INVALID )' -> 'if (contextId == INVALID)'.
    String literals and comments are never modified. Conditions that close
    on a later line are left untouched (only the keyword gap is fixed).
    Returns (fixed_line, in_block_comment, changed).
    """
    masked, in_block_comment = _mask_non_code(line, in_block_comment)
    if not KEYWORD_PAREN_RE.search(masked):
        return line, in_block_comment, False

    out = []
    prev = 0
    changed = False
    for m in KEYWORD_PAREN_RE.finditer(masked):
        kw_end = m.end(1)
        open_idx = m.start(3)
        if open_idx < prev:
            continue  # keyword sits inside an already normalized region
        gap = line[kw_end:open_idx]
        out.append(line[prev:kw_end])
        if gap != ' ':
            out.append(' ')
            changed = True
        else:
            out.append(gap)
        close_idx = _find_matching_paren(masked, open_idx)
        if close_idx == -1:
            # Condition closes on a later line: keep the remainder as-is.
            out.append(line[open_idx:])
            prev = len(line)
            break
        segment = line[open_idx:close_idx + 1]
        fixed = _strip_paren_edge_whitespace(
            line, masked, open_idx, close_idx + 1)
        out.append(fixed)
        if fixed != segment:
            changed = True
        prev = close_idx + 1
    out.append(line[prev:])
    return ''.join(out), in_block_comment, changed


def clean_whitespace_in_file(file_path):
    """Clean one Java file in place:
      1. Expand leading tabs (indentation) to 4 spaces.
      2. Strip trailing whitespace/tabs from every line (CRLF -> LF).
      3. Trim trailing blank lines so the file ends with exactly one newline.
      4. Normalize control-flow header spacing: one space between keyword
         and '(' (if(x) -> if (x)) and no redundant whitespace inside the
         parentheses (if ( x ) -> if (x)); strings & comments untouched.
      5. Collapse runs of 2+ consecutive blank lines into a single blank line.
    Every step honours config/const_clean_java.config (built-in defaults
    apply when the file or a key is missing).
    Returns True when the file was modified, False when unchanged or on error.
    """
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        return False
    try:
        with open(file_path, 'r', encoding='utf-8', newline='') as f:
            raw = f.read()

        # Split on '\n' only; rstrip() below also drops any '\r' (CRLF -> LF).
        cleaned_parts = []
        in_block_comment = False
        for part in raw.split('\n'):
            expanded = _expand_leading_tabs(part, TAB_WIDTH).rstrip()
            if FIX_KEYWORD_PAREN_SPACING:
                expanded, in_block_comment, _ = _fix_keyword_paren_spacing(
                    expanded, in_block_comment)
            cleaned_parts.append(expanded)

        if COLLAPSE_BLANK_LINES:
            # Collapse runs of 2+ blank lines into a single blank line.
            compacted = []
            prev_blank = False
            for part in cleaned_parts:
                if part == '':
                    if prev_blank:
                        continue  # drop 2nd/3rd/... blank line of the run
                    prev_blank = True
                else:
                    prev_blank = False
                compacted.append(part)
            cleaned_parts = compacted

        if ENSURE_TRAILING_NEWLINE:
            # Trim trailing blank lines: file must end with exactly one newline.
            while cleaned_parts and cleaned_parts[-1] == '':
                cleaned_parts.pop()

        cleaned = '\n'.join(cleaned_parts)
        if cleaned and ENSURE_TRAILING_NEWLINE:
            cleaned += '\n'

        if cleaned == raw:
            return False  # already clean; skip write to preserve mtime

        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            f.write(cleaned)

        print(f"Processed: {file_path}")
        return True
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return False

def get_git_modified_java_files():
    """Fetch all modified, added, or untracked .java files using git diff and status."""
    modified_files = set()
    try:
        # 1. Staged and unstaged modified/added files
        diff_output = subprocess.check_output(
            ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMRT"],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in diff_output.splitlines():
            line = line.strip()
            if line.endswith(".java") and os.path.isfile(line):
                modified_files.add(line)
        
        # 2. Untracked files
        status_output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in status_output.splitlines():
            line = line.strip()
            if line.startswith("??") and line.endswith(".java"):
                file_path = line[3:].strip()
                if os.path.isfile(file_path):
                    modified_files.add(file_path)
    except Exception:
        pass
    return sorted(list(modified_files))

def clean_java_files_in_directory(root_dir):
    """Recursively scan the directory to find and process all .java files."""
    count = 0
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.java'):
                file_path = os.path.join(dirpath, filename)
                if clean_whitespace_in_file(file_path):
                    count += 1
    print(f"\nDone! Cleaned whitespace for a total of {count} Java file(s).")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ["-h", "--help", "help"]:
            print_help()
        elif arg in ["--diff", "--git-diff"]:
            files = get_git_modified_java_files()
            print(f"Git Diff Mode: Found {len(files)} modified .java file(s).")
            changed = sum(1 for f in files if clean_whitespace_in_file(f))
            print(f"\nDone! Cleaned whitespace for {changed} Git modified Java file(s).")
        elif arg == "--all":
            target_directory = "."
            print(f"Full Scan Mode: Scanning directory: {os.path.abspath(target_directory)}")
            clean_java_files_in_directory(target_directory)
        elif os.path.isfile(arg):
            clean_whitespace_in_file(arg)
        elif os.path.isdir(arg):
            print(f"Scanning directory: {os.path.abspath(arg)}")
            clean_java_files_in_directory(arg)
        else:
            print(f"Error: '{arg}' is not a valid option, file, or directory!")
            print("Use 'python clean_java.py --help' to view available commands.")
    else:
        # Default behavior: Clean git diff modified files if present, otherwise clean git diff
        files = get_git_modified_java_files()
        if files:
            print(f"Git Diff Mode (Default): Found {len(files)} modified .java file(s).")
            changed = sum(1 for f in files if clean_whitespace_in_file(f))
            print(f"\nDone! Cleaned whitespace for {changed} Git modified Java file(s).")
        else:
            print("No Git modified .java files found. Use 'python clean_java.py --help' for usage options.")