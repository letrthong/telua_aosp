# ==============================================================================
# Copyright (C) 2026 letrthong@gmail.com
# Created & Maintained by: letrthong@gmail.com
# Licensed under the Apache License, Version 2.0
# ==============================================================================

"""Report Java methods and parameters that are declared but never used,
plus whitespace hygiene and google-java-format violations (read-only preview).

The report covers four checks:

  1. UNUSED METHODS - declared methods whose name never appears in code
     (outside their own declaration line) anywhere in the search scope.
  2. UNUSED PARAMETERS - parameters whose name never appears inside their
     own method body (the classic "-Wunused-parameter" IDE/lint warning).
     The usual fix mirrors the C++ idiom: comment out the name, keep the
     type, e.g.
         // Before: 'spare' triggers an unused-parameter warning
         void processData(int data, int spare) { ... }
         // After: name commented out, warning suppressed
         void processData(int data, int /*spare*/) { ... }
     Parameters whose name is already commented out are skipped, so after
     applying the fix the report converges to a clean result.
  3. WHITESPACE VIOLATIONS - trailing whitespace, leading tabs (indentation),
     control-flow keyword-paren spacing (if(x) -> if (x)), runs of 2+ blank
     lines, CRLF line endings and a missing single trailing newline. This is
     a read-only preview of exactly what clean_java.py would fix when run
     with 'clean-java'; the report itself never modifies files.
  4. GOOGLE-JAVA-FORMAT VIOLATIONS - read-only style check powered by
     google-java-format (or the maciejwalkowiak/google-java-format-pre-commit
     Git submodule in third_party/google-java-format-pre-commit, initialized
     automatically if missing). Reports lines whose formatting differs from
     Google/AOSP Java Style without modifying any source file.

The usage-search scope is the module/source tree of each target file: it
walks up from the file to the nearest 'src' directory or project marker
(Android.bp, Android.mk, build.gradle, pom.xml, settings.gradle). The report
lists unused methods and parameters for EVERY .java file in that scope, not
only the files named on the command line, so one run captures the whole
module in the saved report file.

Heuristics used to avoid false positives - the unused-method check SKIPS:
  - constructors, @Override methods, abstract/native methods and main()
  - methods declared inside interfaces (they are contracts) and methods
    whose name matches any interface/abstract method found in the scope
  - Object overrides: toString/equals/hashCode/clone/finalize
  - test code: files under test/tests/androidTest/javatests directories or
    with JUnit/TestNG hints (@Test, @RunWith, org.junit imports). Test
    methods are invoked by the test framework, never by name from other
    code, so a name-based search would flag every one of them. Test files
    still COUNT as usage sources for production methods.
Usage detection ignores comments and string literals (code is masked) and
accepts plain calls, qualified calls (obj.name(...)) and '::name' references.

NOTE: this is a fast name-based heuristic (not a compiler-grade call graph).
Overloads share usages, recursion inside a method body counts as a usage,
and references from non-Java files (XML, JNI) are not seen. Review results
before deleting any code.

The report is always saved to a text file (default: ./unused_java_report.txt)
so results can be kept for later review.

Usage:
  python unused_methods_report.py [OPTION | FILE_PATH | DIR_PATH] [--out FILE]

Options:
  (no argument)         (Default) Report ALL .java files under the CURRENT directory.
  --diff, --git-diff    Report Git modified/added .java files.
  --all                 Report ALL .java files under the current directory.
  <file_path>           Report one specific .java file.
  <dir_path>            Report all .java files under the directory.
  --out FILE, -o FILE   Report output file (default: unused_java_report.txt).
  -h, --help            Show this help message and exit.

Examples:
  python unused_methods_report.py
  python unused_methods_report.py --diff
  python unused_methods_report.py MyService.java
  python unused_methods_report.py src/com/example/app/ --out report.txt
"""

import bisect
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# Reuse the masking + git helpers from the sibling whitespace cleaner so both
# tools share one implementation of "ignore strings & comments".
try:
    from clean_java import (_mask_non_code, get_git_modified_java_files,
                            _expand_leading_tabs, _fix_keyword_paren_spacing,
                            TAB_WIDTH, ENSURE_TRAILING_NEWLINE,
                            FIX_KEYWORD_PAREN_SPACING, COLLAPSE_BLANK_LINES,
                            ENABLE_GOOGLE_JAVA_FORMAT, GOOGLE_JAVA_FORMAT_AOSP,
                            GOOGLE_JAVA_FORMAT_REPO_URL)
except ImportError:  # pragma: no cover - direct copy fallback
    sys.exit("ERROR: clean_java.py must sit in the same directory as "
             "unused_methods_report.py")

DEFAULT_REPORT_FILE = 'unused_java_report.txt'
REPO_ROOT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
GJF_DEFAULT_DIR = os.path.join(
    REPO_ROOT_DIR, 'third_party', 'google-java-format-pre-commit')

# ------------------------------------------------------------------------------
# Declaration parsing
# ------------------------------------------------------------------------------
MODIFIER_WORDS = {
    'public', 'protected', 'private', 'static', 'final', 'abstract',
    'default', 'synchronized', 'native', 'strictfp',
}
CONTROL_KEYWORDS = {
    'if', 'for', 'while', 'switch', 'catch', 'try', 'do', 'else', 'case',
    'return', 'new', 'break', 'continue', 'throw', 'throws', 'assert',
    'finally', 'instanceof', 'this', 'super', 'null', 'true', 'false',
    'import', 'package', 'extends', 'implements',
}
OBJECT_METHOD_NAMES = {'toString', 'equals', 'hashCode', 'clone', 'finalize'}
# Characters allowed in the "return type + modifiers" prefix of a declaration.
# Anything else (= ; { } ) & | ? : etc. means the line is not a declaration.
ALLOWED_PREFIX_CHARS = set(
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$.<>[], @')

ANNOTATION_PREFIX_RE = re.compile(r'^(?:@\w+(?:\s*\([^)]*\))?\s*)+')
INTERFACE_HEADER_RE = re.compile(r'\binterface\s+[\w$]+')
TYPE_DECL_RE = re.compile(r'\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)')
IDENT_TAIL_RE = re.compile(r'([A-Za-z_$][\w$]*)\s*$')
PREFIX_TOKEN_RE = re.compile(r'@?[\w$]+')


def _extract_decl(code):
    """Extract a method declaration candidate from one masked code line.

    Returns (name, prefix, mods_set) or None when the line is not a method
    declaration (call statement, control-flow keyword, field access, ...).
    """
    code = code.strip()
    if not code:
        return None
    m = ANNOTATION_PREFIX_RE.match(code)
    if m:
        code = code[m.end():].strip()
        if not code:
            return None
    open_idx = code.find('(')
    if open_idx <= 0:
        return None
    head = code[:open_idx]
    nm = IDENT_TAIL_RE.search(head)
    if not nm:
        return None
    name = nm.group(1)
    before = head[:nm.start()].rstrip()
    if before.endswith('.'):
        return None  # qualified call: obj.name( / Class.name(
    if name in CONTROL_KEYWORDS:
        return None
    prefix = before.strip()
    if prefix and any(c not in ALLOWED_PREFIX_CHARS for c in prefix):
        return None
    mods = set()
    if prefix:
        for tok in PREFIX_TOKEN_RE.findall(prefix):
            if tok in CONTROL_KEYWORDS:
                return None  # e.g. 'return foo(', 'new Foo('
            if tok in MODIFIER_WORDS:
                mods.add(tok)
    return name, prefix, mods


def _visibility(mods):
    """Human-readable visibility (+ static) for the report column."""
    vis = ('private' if 'private' in mods
           else 'protected' if 'protected' in mods
           else 'public' if 'public' in mods else 'package')
    return f"{vis} static" if 'static' in mods else vis


# ------------------------------------------------------------------------------
# Parameter list & method body extraction
# ------------------------------------------------------------------------------
def _find_matching_paren_text(text, open_idx):
    """Index of the ')' matching the '(' at `open_idx`, or -1 (same text)."""
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _find_matching_brace(text, open_idx):
    """Index of the '}' matching the '{' at `open_idx`, or -1 (same text)."""
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _collect_params_and_body(params, raw_text, masked_text, line_starts,
                             paren_off, method_name):
    """Extract the parameter list and body of the method whose '(' sits at
    `paren_off` in the (same-length) raw/masked texts.

    Appends (method_line, method_name, [(param_name, param_line)...], body)
    to `params` when the method has a body. Parameters whose name is already
    commented out (raw part contains a comment) are skipped - the warning is
    already suppressed with the 'int /*name*/' idiom.
    """
    close_off = _find_matching_paren_text(masked_text, paren_off)
    if close_off == -1:
        return

    # Split the parameter list at top-level commas (generics <..>, annotation
    # parens (..) and array brackets [..] raise the depth so their commas are
    # not split points).
    param_spans = []
    depth = 0
    start = paren_off + 1
    for i in range(paren_off + 1, close_off):
        ch = masked_text[i]
        if ch in '<([{':
            depth += 1
        elif ch in '>)]}':
            depth = max(0, depth - 1)
        elif ch == ',' and depth == 0:
            param_spans.append((start, i))
            start = i + 1
    param_spans.append((start, close_off))

    parsed = []
    for ps, pe in param_spans:
        part_masked = masked_text[ps:pe].strip()
        part_raw = raw_text[ps:pe]
        if '/*' in part_raw or '//' in part_raw:
            continue  # name already commented out (warning suppressed)
        nm = IDENT_TAIL_RE.search(part_masked)
        if not nm:
            continue  # no name (malformed or type-only after masking)
        pname = nm.group(1)
        if pname in CONTROL_KEYWORDS or pname == '_':
            continue
        parsed.append((pname, bisect.bisect_right(line_starts, ps)))
    if not parsed:
        return

    # Locate the body: skip whitespace and an optional throws clause.
    j = close_off + 1
    n = len(masked_text)
    while j < n and masked_text[j] in ' \t\n':
        j += 1
    if (masked_text[j:j + 6] == 'throws'
            and j + 6 < n and masked_text[j + 6] in ' \t\n'):
        j += 6
        while j < n and masked_text[j] not in '{;':
            j += 1
    if j >= n or masked_text[j] != '{':
        return  # abstract / interface / native method: no body to search
    body_close = _find_matching_brace(masked_text, j)
    if body_close == -1:
        return
    body = masked_text[j + 1:body_close]
    params.append((bisect.bisect_right(line_starts, paren_off),
                   method_name, parsed, body))


# ------------------------------------------------------------------------------
# Whitespace hygiene checks (read-only preview of clean_java.py fixes)
# ------------------------------------------------------------------------------
def _check_whitespace(raw_lines):
    """Detect whitespace hygiene violations in one file's raw lines.

    Mirrors exactly what clean_whitespace_in_file() would fix (honouring the
    const_clean_java.config settings imported from clean_java):
      - CRLF line endings (cleaner converts to LF)
      - leading tabs in indentation (expanded to TAB_WIDTH spaces)
      - trailing whitespace on any line
      - keyword-paren spacing (if(x) -> if (x), for(x) -> for (x), ...)
      - runs of 2+ blank lines (collapsed to one)
      - missing single trailing newline / trailing blank lines at EOF
    Returns a list of (line_no, description, line_text); line_no 0 marks a
    file-level (EOF) issue (line_text is ''). Strings and comments are never
    misreported: the keyword check runs on masked text via
    _fix_keyword_paren_spacing.
    """
    violations = []
    in_block = False
    prev_blank = False
    for idx, ln in enumerate(raw_lines):
        line_no = idx + 1
        body = ln[:-1] if ln.endswith('\r') else ln
        if body != ln:
            violations.append((line_no, 'CRLF line ending', body))
        if _expand_leading_tabs(body, TAB_WIDTH) != body:
            violations.append((line_no, 'leading tab (indentation)', body))
        stripped = body.rstrip()
        if stripped != body:
            violations.append((line_no, 'trailing whitespace', body))
        if FIX_KEYWORD_PAREN_SPACING:
            _, in_block, changed = _fix_keyword_paren_spacing(stripped,
                                                              in_block)
            if changed:
                violations.append(
                    (line_no,
                     'keyword-paren spacing (if/for/switch(x) -> kw (x))',
                     body))
        blank = (stripped == '')
        if COLLAPSE_BLANK_LINES and blank and prev_blank:
            violations.append((line_no, 'blank line run (2+)', body))
        prev_blank = blank
    if ENSURE_TRAILING_NEWLINE and raw_lines:
        if raw_lines[-1] != '' or (len(raw_lines) >= 2
                                   and raw_lines[-2] == ''):
            violations.append((0, 'missing single trailing newline', ''))
    return violations


def scan_java_file(file_path):
    """One-pass scan of a Java file.

    Returns dict with:
      masked   - list of lines with strings/comments blanked (usage search)
      decls    - list of (line_no_1based, name, visibility) report candidates
      params   - list of (method_line, method_name, [(param, line)...], body)
      contracts- names declared in interfaces or as abstract/native methods
      classes  - type names declared in the file (constructor detection)
      is_test  - True when the file is test code (test dir / JUnit hints)
      ws       - whitespace violations [(line_no, desc, line_text)]; 0 = EOF
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            raw_lines = f.read().split('\n')
    except OSError as e:
        print(f"Error reading {file_path}: {e}")
        return None

    masked_lines = []
    in_block = False
    for ln in raw_lines:
        masked, in_block = _mask_non_code(ln, in_block)
        masked_lines.append(masked)

    # Test-code detection (path components + JUnit/TestNG content hints).
    is_test = is_test_file(file_path, masked_lines)

    # Whitespace hygiene findings (read-only preview of clean_java.py fixes).
    ws_violations = _check_whitespace(raw_lines)

    raw_text = '\n'.join(raw_lines)
    masked_text = '\n'.join(masked_lines)
    # Offset of the start of each line (raw and masked have identical lengths).
    line_starts = [0]
    for ln in raw_lines[:-1]:
        line_starts.append(line_starts[-1] + len(ln) + 1)

    decls = []
    params = []
    contracts = set()
    class_names = set()
    depth = 0
    interface_depth = None      # depth value while inside an interface body
    awaiting_interface_body = False
    override_pending = 0        # lines remaining where @Override still applies
    test_pending = 0            # lines remaining where @Test/@Before applies

    for idx, masked in enumerate(masked_lines):
        stripped = masked.strip()
        for m in TYPE_DECL_RE.finditer(masked):
            class_names.add(m.group(1))
        if INTERFACE_HEADER_RE.search(masked):
            awaiting_interface_body = True
        if re.match(r'^\s*@Override\b', masked):
            override_pending = 3
        if TEST_ANNOTATION_RE.match(masked):
            test_pending = 4

        decl = _extract_decl(stripped)
        if decl is not None:
            name, _prefix, mods = decl
            # 'synchronized (lock) {' statement form parses as a method named
            # 'synchronized'; it is a block, not a method - skip param scan.
            is_sync_block = (name == 'synchronized'
                             and re.match(r'^synchronized\s*\(', stripped))
            # Parameter/body extraction runs for every method-like decl,
            # including constructors and @Override methods (unused params
            # there still trigger lint warnings). Test-framework methods
            # (@Test/@Before/...) are skipped: the runner invokes them.
            is_test_method = test_pending > 0
            test_pending = 0  # annotation consumed by this declaration
            if not is_sync_block and not is_test_method:
                pm = re.search(re.escape(name) + r'\s*\(', masked)
                if pm is not None:
                    _collect_params_and_body(
                        params, raw_text, masked_text, line_starts,
                        line_starts[idx] + pm.end() - 1, name)

            inside_interface = (interface_depth is not None
                                and depth >= interface_depth)
            is_ctor = name in class_names
            is_contract = 'abstract' in mods or 'native' in mods
            if inside_interface:
                contracts.add(name)
            elif is_ctor:
                pass  # constructors are invoked via 'new'; never reported
            elif is_contract:
                contracts.add(name)
            elif override_pending > 0:
                pass  # implements a super/interface method
            elif name == 'main' or name in OBJECT_METHOD_NAMES:
                pass
            elif is_sync_block:
                pass  # synchronized statement, not a method declaration
            elif is_test_method:
                pass  # @Test/@Before/... method: invoked by the test runner
            else:
                decls.append((idx + 1, name, _visibility(mods)))

        if stripped and override_pending > 0:
            override_pending -= 1
        if stripped and test_pending > 0:
            test_pending -= 1

        opens = masked.count('{')
        closes = masked.count('}')
        if awaiting_interface_body and opens > 0:
            interface_depth = depth + 1
            awaiting_interface_body = False
        depth += opens - closes
        if interface_depth is not None and depth < interface_depth:
            interface_depth = None  # left the interface body

    return {
        'masked': masked_lines,
        'decls': decls,
        'params': params,
        'contracts': contracts,
        'classes': class_names,
        'is_test': is_test,
        'ws': ws_violations,
    }


# ------------------------------------------------------------------------------
# Scope resolution & usage counting
# ------------------------------------------------------------------------------
PROJECT_MARKERS = ('Android.bp', 'Android.mk', 'build.gradle',
                   'build.gradle.kts', 'pom.xml', 'settings.gradle')
PRUNE_DIRS = {'.git', '.repo', 'out', 'node_modules', 'build', 'target',
              '.gradle', '.idea', '.vscode'}

# Test-code detection: methods in test files or annotated with test-framework
# annotations are invoked by the test runner (JUnit / Android instrumentation),
# not by name from other code, so a name-based usage search would flag every
# one of them. Test files are excluded from the report but still COUNT as
# usage sources for production methods.
TEST_DIR_COMPONENTS = {'test', 'tests', 'androidtest', 'javatests'}
TEST_ANNOTATION_RE = re.compile(
    r'^\s*@(?:Test|Before|After|BeforeClass|AfterClass|SetUp|TearDown'
    r'|Parameterized|RepeatedTest|RunWith|UiThreadTest)\b')
TEST_FILE_HINT_RE = re.compile(
    r'\b(?:org\.junit|org\.testng|junit\.framework|androidx\.test)\b')


def is_test_file(file_path, masked_lines):
    """True when `file_path` looks like test code: it lives under a test
    directory (test/tests/androidTest/javatests) or contains JUnit/TestNG
    hints (imports or @Test/@RunWith-style annotations on code lines)."""
    parts = [p.lower() for p in os.path.normpath(file_path).split(os.sep)]
    if TEST_DIR_COMPONENTS.intersection(parts):
        return True
    return any(TEST_FILE_HINT_RE.search(ln) or TEST_ANNOTATION_RE.match(ln)
               for ln in masked_lines)


def resolve_scope_dir(file_path):
    """Walk up from a file to its module/source root for the usage search."""
    d = os.path.dirname(os.path.abspath(file_path))
    for _ in range(8):
        if os.path.basename(d) == 'src' or any(
                os.path.isfile(os.path.join(d, marker))
                for marker in PROJECT_MARKERS):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.dirname(os.path.abspath(file_path))


def collect_java_files(root_dirs):
    """Recursively list .java files under the given roots (deduped, pruned)."""
    roots = []
    for r in sorted({os.path.abspath(x) for x in root_dirs}):
        if not any(r == x or r.startswith(x + os.sep) for x in roots):
            roots.append(r)
    files = []
    for r in roots:
        for dirpath, dirnames, filenames in os.walk(r):
            dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
            for fn in filenames:
                if fn.endswith('.java'):
                    files.append(os.path.join(dirpath, fn))
    return sorted(files)


def _ident_pattern(name):
    return re.compile(r'(?<![\w$])' + re.escape(name) + r'(?![\w$])')


def is_method_used(name, decl_file, decl_line_idx, file_data):
    """True when `name` appears in code outside its own declaration line."""
    pat = _ident_pattern(name)
    for path, data in file_data.items():
        for i, ln in enumerate(data['masked']):
            if path == decl_file and i == decl_line_idx:
                continue  # skip the declaration itself
            if pat.search(ln):
                return True
    return False


# ------------------------------------------------------------------------------
# Google Java Format (maciejwalkowiak/google-java-format-pre-commit)
# ------------------------------------------------------------------------------
def ensure_google_java_format_repo(repo_dir=None, repo_url=None):
    """Ensure the third_party/google-java-format-pre-commit submodule is
    initialized; run 'git submodule update --init' or shallow clone if missing.

    Returns True if `repo_dir` exists and is non-empty, False otherwise.
    """
    target_dir = repo_dir or GJF_DEFAULT_DIR
    url = repo_url or GOOGLE_JAVA_FORMAT_REPO_URL
    if os.path.isdir(target_dir) and os.listdir(target_dir):
        return True
    if os.environ.get('TELUA_SKIP_GJF_CLONE') == '1':
        return False
    if not shutil.which('git'):
        return False
    try:
        subprocess.run(
            ['git', '-C', REPO_ROOT_DIR, 'submodule', 'update',
             '--init', '--recursive'],
            capture_output=True, text=True, timeout=60)
        if os.path.isdir(target_dir) and os.listdir(target_dir):
            return True
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        res = subprocess.run(
            ['git', 'clone', '--depth', '1', url, target_dir],
            capture_output=True, text=True, timeout=60)
        return res.returncode == 0 and os.path.isdir(target_dir)
    except (OSError, subprocess.SubprocessError):
        return False


def _find_jar_or_script_in_dir(directory):
    """Search `directory` for a google-java-format .jar or hook script."""
    if not directory or not os.path.isdir(directory):
        return None
    jars = []
    scripts = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d != '.git']
        for fn in sorted(files):
            full = os.path.join(root, fn)
            low = fn.lower()
            if low.endswith('.jar') and 'google-java-format' in low:
                jars.append(full)
            elif (low in ('run-google-java-format.sh',
                          'google-java-format.sh',
                          'google-java-format',
                          'pre-commit',
                          'entrypoint.sh')
                  or (low.endswith('.sh') and 'format' in low)):
                scripts.append(full)
    if jars and shutil.which('java'):
        return ('jar', ['java', '-jar', jars[-1]])
    if scripts:
        script = scripts[0]
        if script.endswith('.sh') and shutil.which('bash'):
            return ('hook', ['bash', script])
        return ('hook', [script])
    return None


def resolve_google_java_format_cmd(repo_dir=None, auto_clone=False):
    """Locate a google-java-format runner: returns (kind, cmd_list) or None.

    Lookup order:
      1. GOOGLE_JAVA_FORMAT_PATH environment variable (.jar or binary/script).
      2. ~/google-java-format-pre-commit (cloning first when auto_clone=True).
      3. ~/.cache/google-java-format (cached .jar downloaded by pre-commit).
      4. $ANDROID_BUILD_TOP/prebuilts/tools/common/google-java-format/...
      5. 'google-java-format' on system PATH.
    """
    env_path = os.environ.get('GOOGLE_JAVA_FORMAT_PATH', '').strip()
    if env_path and os.path.isfile(env_path):
        if env_path.lower().endswith('.jar'):
            return ('jar', ['java', '-jar', env_path])
        return ('bin', [env_path])

    target_dir = repo_dir or GJF_DEFAULT_DIR
    if auto_clone and not os.path.isdir(target_dir):
        ensure_google_java_format_repo(target_dir)

    found = _find_jar_or_script_in_dir(target_dir)
    if found is not None:
        return found

    cache_dir = os.path.join(
        os.path.expanduser('~'), '.cache', 'google-java-format')
    found_cache = _find_jar_or_script_in_dir(cache_dir)
    if found_cache is not None:
        return found_cache

    android_top = os.environ.get('ANDROID_BUILD_TOP', '').strip()
    if android_top:
        aosp_bin = os.path.join(
            android_top, 'prebuilts', 'tools', 'common',
            'google-java-format', 'google-java-format')
        if os.path.isfile(aosp_bin):
            return ('bin', [aosp_bin])

    sys_bin = shutil.which('google-java-format')
    if sys_bin:
        return ('bin', [sys_bin])
    return None


def _diff_google_java_format_lines(orig_lines, fmt_lines):
    """Compare original vs google-java-format lines and return violations."""
    violations = []
    matcher = difflib.SequenceMatcher(None, orig_lines, fmt_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        line_no = i1 + 1 if i1 < len(orig_lines) else max(1, len(orig_lines))
        src_line = orig_lines[i1] if i1 < len(orig_lines) else ''
        if tag == 'replace':
            expected = fmt_lines[j1].strip() if j1 < len(fmt_lines) else ''
            if len(expected) > 60:
                expected = expected[:57] + '...'
            kind = (f"google-java-format style mismatch "
                    f"(expected: '{expected}')")
        elif tag == 'delete':
            kind = (f"google-java-format removes {i2 - i1} line(s) "
                    f"starting at line {line_no}")
        else:  # 'insert'
            inserted = fmt_lines[j1].strip() if j1 < len(fmt_lines) else ''
            if len(inserted) > 60:
                inserted = inserted[:57] + '...'
            kind = (f"google-java-format inserts line(s) "
                    f"(expected: '{inserted}')")
        violations.append((line_no, kind, src_line))
    return violations


def _check_google_java_format_file(file_path, runner, aosp=None):
    """Run google-java-format in read-only mode on `file_path` and return a
    list of (line_no, kind, src_line) style violations. Never modifies
    `file_path`."""
    if runner is None:
        return []
    use_aosp = GOOGLE_JAVA_FORMAT_AOSP if aosp is None else aosp
    kind, cmd = runner
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            orig_text = f.read()
    except OSError:
        return []
    orig_lines = orig_text.splitlines()

    if kind in ('jar', 'bin'):
        args = list(cmd)
        if use_aosp:
            args.append('--aosp')
        args.append(file_path)
        try:
            res = subprocess.run(
                args, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=30)
        except (OSError, subprocess.SubprocessError):
            return []
        if res.returncode != 0 or not res.stdout:
            return []
        fmt_lines = res.stdout.splitlines()
        return _diff_google_java_format_lines(orig_lines, fmt_lines)

    # 'hook' script: run on a temporary copy so in-place (--replace) hooks
    # never touch the real source file.
    tmp_dir = tempfile.mkdtemp(prefix='telua_gjf_')
    try:
        tmp_file = os.path.join(tmp_dir, os.path.basename(file_path))
        with open(tmp_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(orig_text)
        try:
            res = subprocess.run(
                list(cmd) + [tmp_file],
                capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=30)
        except (OSError, subprocess.SubprocessError):
            return []
        # Prefer formatted temp file if modified in-place; otherwise stdout.
        try:
            with open(tmp_file, 'r', encoding='utf-8', errors='replace') as f:
                after_text = f.read()
        except OSError:
            after_text = orig_text
        if after_text != orig_text:
            return _diff_google_java_format_lines(
                orig_lines, after_text.splitlines())
        if res.returncode == 0 and res.stdout.strip():
            return _diff_google_java_format_lines(
                orig_lines, res.stdout.splitlines())
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def check_google_java_format(scope_files, runner=None, auto_clone=False):
    """Run google-java-format across `scope_files` (read-only).

    Returns (gjf_by_file, runner_available).
    """
    if not ENABLE_GOOGLE_JAVA_FORMAT:
        return {}, False
    active_runner = (runner if runner is not None
                     else resolve_google_java_format_cmd(auto_clone=auto_clone))
    if active_runner is None:
        return {}, False
    gjf_by_file = {}
    for path in sorted(scope_files):
        abspath = os.path.abspath(path)
        violations = _check_google_java_format_file(abspath, active_runner)
        if violations:
            gjf_by_file[abspath] = violations
    return gjf_by_file, True


# ------------------------------------------------------------------------------
# Report
# ------------------------------------------------------------------------------
def build_report(target_files):
    """Return (unused_methods, unused_params, decl_count, scope_dirs,
    file_count, test_file_count, ws_by_file)."""
    scope_dirs = sorted({resolve_scope_dir(f) for f in target_files})
    scope_files = collect_java_files(scope_dirs)

    file_data = {}
    all_contracts = set()
    for path in scope_files:
        data = scan_java_file(path)
        if data is not None:
            file_data[os.path.abspath(path)] = data
            all_contracts |= data['contracts']

    unused = []
    unused_params = []
    decl_count = 0
    test_file_count = 0
    ws_by_file = {}
    # Report EVERY file in the usage-search scope, not only the targets: any
    # unused method/parameter anywhere in the module is captured in the report.
    for abspath in sorted(file_data):
        data = file_data[abspath]
        if data['ws']:
            # Whitespace findings are reported for ALL files (test files
            # too): 'clean-java' would clean them as well.
            ws_by_file[abspath] = data['ws']
        if data['is_test']:
            # Test code: methods are invoked by the test framework (JUnit /
            # Instrumentation), never by name from other code, so a name-based
            # search would flag every test method. Skipped in the report, but
            # the file still contributes usages for production code above.
            test_file_count += 1
            continue
        for line_no, name, vis in data['decls']:
            decl_count += 1
            if name in all_contracts:
                continue
            if not is_method_used(name, abspath, line_no - 1, file_data):
                unused.append((abspath, line_no, name, vis))
        # Unused parameters: name never appears inside its own method body.
        for method_line, method_name, plist, body in data['params']:
            for pname, pline in plist:
                if not _ident_pattern(pname).search(body):
                    unused_params.append(
                        (abspath, method_line, method_name, pname, pline))
    unused.sort(key=lambda u: (u[0], u[1]))
    unused_params.sort(key=lambda u: (u[0], u[1]))
    return (unused, unused_params, decl_count, scope_dirs, len(file_data),
            test_file_count, ws_by_file)


def build_report_lines(target_files, gjf_runner=None, auto_clone_gjf=False):
    """Compose the full report as a list of text lines."""
    unused, unused_params, decl_count, scope_dirs, file_count, test_file_count, \
        ws_by_file = build_report(target_files)
    scope_files = collect_java_files(scope_dirs)
    gjf_by_file, gjf_available = check_google_java_format(
        scope_files, runner=gjf_runner, auto_clone=auto_clone_gjf)
    cwd = os.getcwd()

    def rel(path):
        try:
            return os.path.relpath(path, cwd)
        except ValueError:
            return path

    lines = []
    lines.append("=" * 78)
    lines.append("Unused Java Method, Parameter & Whitespace Report "
                 "(unused_methods_report.py)")
    lines.append("=" * 78)
    lines.append(f"Generated          : "
                 f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for d in scope_dirs:
        lines.append(f"Usage-search scope : {d}")
    lines.append(f"Scope files        : {file_count} .java file(s) "
                 f"(all scanned; targets: {len(target_files)})")
    lines.append(f"Test files skipped : {test_file_count} .java file(s) "
                 f"(framework-invoked test code not reported)")
    lines.append(f"Declarations parsed: {decl_count} method(s)")
    lines.append("-" * 78)

    lines.append(f"[1] Unused methods: {len(unused)}")
    if unused:
        by_file = {}
        for path, line_no, name, vis in unused:
            by_file.setdefault(path, []).append((line_no, name, vis))
        for path in sorted(by_file):
            lines.append(f"{rel(path)}")
            for line_no, name, vis in by_file[path]:
                lines.append(f"    line {line_no:>5}: {name}  ({vis})")
    lines.append("")

    lines.append(f"[2] Unused parameters: {len(unused_params)}")
    if unused_params:
        by_file = {}
        for path, m_line, m_name, pname, p_line in unused_params:
            by_file.setdefault(path, []).append((m_line, m_name, pname, p_line))
        for path in sorted(by_file):
            lines.append(f"{rel(path)}")
            for m_line, m_name, pname, p_line in by_file[path]:
                lines.append(f"    line {m_line:>5}: {m_name} - unused "
                             f"parameter '{pname}' (declared line {p_line})")
    lines.append("")

    ws_total = sum(len(v) for v in ws_by_file.values())
    lines.append(f"[3] Whitespace violations: {ws_total} "
                 f"(read-only preview of what 'clean-java' would fix)")
    if ws_by_file:
        for path in sorted(ws_by_file):
            lines.append(f"{rel(path)}")
            for line_no, kind, src in ws_by_file[path]:
                if line_no == 0:
                    lines.append(f"    file end     : {kind}")
                else:
                    lines.append(f"    line {line_no:>5}: {kind}")
                    # Show the offending source line (tabs expanded, capped)
                    # so the fix can be located without opening the file.
                    shown = _expand_leading_tabs(src, TAB_WIDTH).rstrip()
                    if len(shown) > 100:
                        shown = shown[:97] + '...'
                    lines.append(f"                 > {shown}")
    lines.append("")

    gjf_total = sum(len(v) for v in gjf_by_file.values())
    gjf_note = ("read-only check via google-java-format"
                if gjf_available
                else "skipped - google-java-format not available")
    lines.append(f"[4] google-java-format violations: {gjf_total} ({gjf_note})")
    if gjf_by_file:
        for path in sorted(gjf_by_file):
            lines.append(f"{rel(path)}")
            for line_no, kind, src in gjf_by_file[path]:
                lines.append(f"    line {line_no:>5}: {kind}")
                if src:
                    shown = _expand_leading_tabs(src, TAB_WIDTH).rstrip()
                    if len(shown) > 100:
                        shown = shown[:97] + '...'
                    lines.append(f"                 > {shown}")
    lines.append("")

    lines.append("-" * 78)
    lines.append(f"Summary: {len(unused)} unused method(s), "
                 f"{len(unused_params)} unused parameter(s), "
                 f"{ws_total} whitespace violation(s), "
                 f"{gjf_total} google-java-format violation(s). Review before "
                 f"deleting (heuristic report, see --help).")
    lines.append("=" * 78)
    return lines


def run_report(target_files, out_path):
    """Print the report and always save it to `out_path` for later review."""
    lines = build_report_lines(target_files, auto_clone_gjf=True)
    text = '\n'.join(lines)
    print(text)
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
    except OSError as e:
        print(f"Error writing report file {out_path}: {e}")
        return
    print(f"\nReport saved to: {os.path.abspath(out_path)}")


def print_help():
    print(__doc__.strip())


def _resolve_targets(argv):
    """Map CLI arguments to a list of target .java files.

    Default (no argument): scan the CURRENT directory recursively.
    """
    if not argv:
        cwd = os.getcwd()
        print(f"Current Directory Mode: Scanning directory: {cwd}")
        files = collect_java_files(['.'])
        if not files:
            print(f"No .java files found under: {cwd}")
        return files
    arg = argv[0]
    if arg in ('-h', '--help', 'help'):
        print_help()
        return None
    if arg in ('--diff', '--git-diff'):
        return get_git_modified_java_files()
    if arg == '--all':
        return collect_java_files(['.'])
    if os.path.isfile(arg):
        if not arg.endswith('.java'):
            print(f"Error: '{arg}' is not a .java file.")
            return None
        return [arg]
    if os.path.isdir(arg):
        files = collect_java_files([arg])
        if not files:
            print(f"No .java files found under: {os.path.abspath(arg)}")
        return files
    print(f"Error: '{arg}' is not a valid option, file, or directory!")
    print("Use 'python unused_methods_report.py --help' for usage.")
    return None


def main(argv):
    out_path = None
    rest = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('--out', '-o'):
            if i + 1 >= len(argv):
                print("Error: --out requires a file path argument.")
                return 1
            out_path = argv[i + 1]
            i += 2
            continue
        rest.append(arg)
        i += 1

    targets = _resolve_targets(rest)
    if targets is None:
        return 1
    if not targets:
        return 0
    run_report(targets, out_path or DEFAULT_REPORT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
