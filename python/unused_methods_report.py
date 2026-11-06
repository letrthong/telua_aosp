# ==============================================================================
# Copyright (C) 2026 letrthong@gmail.com
# Created & Maintained by: letrthong@gmail.com
# Licensed under the Apache License, Version 2.0
# ==============================================================================

"""Report Java methods and parameters that are declared but never used.

The report covers two checks:

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
  python unused_methods_report.py FocusInteraction.java
  python unused_methods_report.py src/com/bosch/car/oem/ --out report.txt
"""

import bisect
import os
import re
import sys
from datetime import datetime

# Reuse the masking + git helpers from the sibling whitespace cleaner so both
# tools share one implementation of "ignore strings & comments".
try:
    from clean_java import _mask_non_code, get_git_modified_java_files
except ImportError:  # pragma: no cover - direct copy fallback
    sys.exit("ERROR: clean_java.py must sit in the same directory as "
             "unused_methods_report.py")

DEFAULT_REPORT_FILE = 'unused_java_report.txt'

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


def scan_java_file(file_path):
    """One-pass scan of a Java file.

    Returns dict with:
      masked   - list of lines with strings/comments blanked (usage search)
      decls    - list of (line_no_1based, name, visibility) report candidates
      params   - list of (method_line, method_name, [(param, line)...], body)
      contracts- names declared in interfaces or as abstract/native methods
      classes  - type names declared in the file (constructor detection)
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

    for idx, masked in enumerate(masked_lines):
        stripped = masked.strip()
        for m in TYPE_DECL_RE.finditer(masked):
            class_names.add(m.group(1))
        if INTERFACE_HEADER_RE.search(masked):
            awaiting_interface_body = True
        if re.match(r'^\s*@Override\b', masked):
            override_pending = 3

        decl = _extract_decl(stripped)
        if decl is not None:
            name, _prefix, mods = decl
            # 'synchronized (lock) {' statement form parses as a method named
            # 'synchronized'; it is a block, not a method - skip param scan.
            is_sync_block = (name == 'synchronized'
                             and re.match(r'^synchronized\s*\(', stripped))
            # Parameter/body extraction runs for every method-like decl,
            # including constructors and @Override methods (unused params
            # there still trigger lint warnings).
            if not is_sync_block:
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
            else:
                decls.append((idx + 1, name, _visibility(mods)))

        if stripped and override_pending > 0:
            override_pending -= 1

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
    }


# ------------------------------------------------------------------------------
# Scope resolution & usage counting
# ------------------------------------------------------------------------------
PROJECT_MARKERS = ('Android.bp', 'Android.mk', 'build.gradle',
                   'build.gradle.kts', 'pom.xml', 'settings.gradle')
PRUNE_DIRS = {'.git', '.repo', 'out', 'node_modules', 'build', 'target',
              '.gradle', '.idea', '.vscode'}


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
# Report
# ------------------------------------------------------------------------------
def build_report(target_files):
    """Return (unused_methods, unused_params, decl_count, scope_dirs, files)."""
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
    # Report EVERY file in the usage-search scope, not only the targets: any
    # unused method/parameter anywhere in the module is captured in the report.
    for abspath in sorted(file_data):
        data = file_data[abspath]
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
    return unused, unused_params, decl_count, scope_dirs, len(file_data)


def build_report_lines(target_files):
    """Compose the full report as a list of text lines."""
    unused, unused_params, decl_count, scope_dirs, file_count = \
        build_report(target_files)
    cwd = os.getcwd()

    def rel(path):
        try:
            return os.path.relpath(path, cwd)
        except ValueError:
            return path

    lines = []
    lines.append("=" * 78)
    lines.append("Unused Java Method & Parameter Report "
                 "(unused_methods_report.py)")
    lines.append("=" * 78)
    lines.append(f"Generated          : "
                 f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for d in scope_dirs:
        lines.append(f"Usage-search scope : {d}")
    lines.append(f"Scope files        : {file_count} .java file(s) "
                 f"(all scanned; targets: {len(target_files)})")
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
    lines.append("-" * 78)
    lines.append(f"Summary: {len(unused)} unused method(s), "
                 f"{len(unused_params)} unused parameter(s). Review before "
                 f"deleting (heuristic report, see --help).")
    lines.append("=" * 78)
    return lines


def run_report(target_files, out_path):
    """Print the report and always save it to `out_path` for later review."""
    lines = build_report_lines(target_files)
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
