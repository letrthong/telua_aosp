#!/usr/bin/env python3
# ==============================================================================
# Unit tests for clean_java.py (whitespace cleaner)
#
# Covers:
#   - _expand_leading_tabs: leading-tab expansion (TAB_WIDTH), literal tabs
#     inside strings/comments untouched
#   - _mask_non_code: string/char/comment masking, block-comment state
#   - _find_matching_paren: paren matching on masked text
#   - _strip_paren_edge_whitespace: inner-paren whitespace removal
#   - _fix_keyword_paren_spacing: if(x)->if (x), if ( x )->if (x), multi-line
#     conditions, strings/comments untouched, block-comment state carry-over
#   - _load_clean_java_config / _apply_settings: config merge + reload
#   - clean_whitespace_in_file: end-to-end file cleaning (tabs, trailing ws,
#     CRLF->LF, blank-line collapse, trailing newline, idempotency, mtime)
#   - get_git_modified_java_files: git diff/status integration
#   - clean_java_files_in_directory: recursive walk + count
#   - main() CLI: --diff, --all, file, dir, help, invalid target
# ==============================================================================

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CLEAN_SCRIPT = os.path.join(REPO_ROOT, "python", "clean_java.py")

# Ensure repo root and python/ subdir are in python path
for p in (REPO_ROOT, os.path.join(REPO_ROOT, "python")):
    if p not in sys.path:
        sys.path.insert(0, p)

import clean_java as cj


def write_file(path, content, newline="\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)
    return path


def read_file(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


class TempDirTestCase(unittest.TestCase):
    """Base class providing a per-test temp directory."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="telua_test_clean_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)


# ------------------------------------------------------------------------------
# _expand_leading_tabs
# ------------------------------------------------------------------------------
class TestExpandLeadingTabs(unittest.TestCase):
    def test_leading_tab_expanded(self):
        self.assertEqual(cj._expand_leading_tabs("\tint x;", 4),
                         "    int x;")

    def test_multiple_tabs(self):
        self.assertEqual(cj._expand_leading_tabs("\t\tif (x) {", 4),
                         "        if (x) {")

    def test_custom_tab_width(self):
        self.assertEqual(cj._expand_leading_tabs("\tx", 2), "  x")

    def test_tab_after_code_untouched(self):
        # Only LEADING whitespace is expanded; literal tabs after code stay.
        self.assertEqual(cj._expand_leading_tabs("int x = 1;\t// note", 4),
                         "int x = 1;\t// note")

    def test_mixed_leading_space_tab(self):
        self.assertEqual(cj._expand_leading_tabs("  \tint x;", 4),
                         "      int x;")

    def test_no_tabs(self):
        self.assertEqual(cj._expand_leading_tabs("    int x;", 4),
                         "    int x;")


# ------------------------------------------------------------------------------
# _mask_non_code
# ------------------------------------------------------------------------------
class TestMaskNonCode(unittest.TestCase):
    def test_string_masked(self):
        masked, in_block = cj._mask_non_code('String s = "if(x)";', False)
        self.assertNotIn("if(x)", masked)
        self.assertEqual(len(masked), len('String s = "if(x)";'))
        self.assertFalse(in_block)

    def test_char_literal_masked(self):
        masked, _ = cj._mask_non_code("char c = '(';", False)
        self.assertNotIn("(", masked.replace("c =", "").replace(";", "")
                         .replace("char", "").replace(" ", ""))
        # simpler: the paren inside quotes is blanked
        masked2, _ = cj._mask_non_code("char c = '(';", False)
        self.assertEqual(masked2[9], " ")

    def test_line_comment_masked(self):
        masked, _ = cj._mask_non_code("int x = 1; // if(x)", False)
        self.assertNotIn("if(x)", masked)

    def test_block_comment_same_line(self):
        masked, in_block = cj._mask_non_code("int x; /* if(x) */ int y;",
                                             False)
        self.assertNotIn("if(x)", masked)
        self.assertFalse(in_block)

    def test_block_comment_carries_state(self):
        masked, in_block = cj._mask_non_code("/* start", False)
        self.assertTrue(in_block)
        masked2, in_block2 = cj._mask_non_code("still comment */ int x;",
                                               in_block)
        self.assertFalse(in_block2)
        self.assertIn("int x;", masked2)
        self.assertNotIn("still comment", masked2)

    def test_escaped_quote(self):
        masked, _ = cj._mask_non_code('String s = "a\\"b"; int x;', False)
        self.assertIn("int x;", masked)

    def test_code_outside_comments_untouched(self):
        line = "if (x) { run(); }"
        masked, _ = cj._mask_non_code(line, False)
        self.assertEqual(masked, line)


# ------------------------------------------------------------------------------
# _find_matching_paren / _strip_paren_edge_whitespace
# ------------------------------------------------------------------------------
class TestParenHelpers(unittest.TestCase):
    def test_find_matching_paren(self):
        masked = "foo(a, (b, c), d)"
        self.assertEqual(cj._find_matching_paren(masked, 0),
                         len(masked) - 1)

    def test_find_matching_paren_unbalanced(self):
        self.assertEqual(cj._find_matching_paren("foo(a, b", 0), -1)

    def test_find_matching_paren_ignores_masked(self):
        # Parens inside a masked-out string must not affect depth: mask the
        # line with the real helper first, then match on the masked text.
        raw = 'foo(")", a)'
        masked, _ = cj._mask_non_code(raw, False)
        self.assertEqual(cj._find_matching_paren(masked, 0),
                         len(raw) - 1)

    def test_strip_paren_edge_whitespace(self):
        text = "if ( x )"
        masked = "if ( x )"
        self.assertEqual(
            cj._strip_paren_edge_whitespace(text, masked, 0, len(text)),
            "if (x)")

    def test_strip_keeps_inner_spacing(self):
        text = "if (a + b)"
        self.assertEqual(
            cj._strip_paren_edge_whitespace(text, text, 0, len(text)),
            "if (a + b)")


# ------------------------------------------------------------------------------
# _fix_keyword_paren_spacing
# ------------------------------------------------------------------------------
class TestFixKeywordParenSpacing(unittest.TestCase):
    def test_if_no_space(self):
        fixed, _, changed = cj._fix_keyword_paren_spacing("if(x) { }", False)
        self.assertEqual(fixed, "if (x) { }")
        self.assertTrue(changed)

    def test_if_redundant_inner_space(self):
        fixed, _, changed = cj._fix_keyword_paren_spacing(
            "if ( x ) { }", False)
        self.assertEqual(fixed, "if (x) { }")
        self.assertTrue(changed)

    def test_already_correct_unchanged(self):
        fixed, _, changed = cj._fix_keyword_paren_spacing(
            "if (x) { }", False)
        self.assertEqual(fixed, "if (x) { }")
        self.assertFalse(changed)

    def test_all_keywords(self):
        for kw in ("if", "for", "while", "switch", "catch", "synchronized"):
            fixed, _, changed = cj._fix_keyword_paren_spacing(
                f"{kw}(x)", False)
            self.assertEqual(fixed, f"{kw} (x)", kw)
            self.assertTrue(changed, kw)

    def test_try_no_paren_untouched(self):
        # 'try {' has no paren; 'try(' as a call must not be touched either.
        fixed, _, changed = cj._fix_keyword_paren_spacing("try {", False)
        self.assertEqual(fixed, "try {")
        self.assertFalse(changed)

    def test_string_literal_untouched(self):
        fixed, _, changed = cj._fix_keyword_paren_spacing(
            'String s = "if(x)";', False)
        self.assertEqual(fixed, 'String s = "if(x)";')
        self.assertFalse(changed)

    def test_comment_untouched(self):
        fixed, _, changed = cj._fix_keyword_paren_spacing(
            "// if(x) hint", False)
        self.assertEqual(fixed, "// if(x) hint")
        self.assertFalse(changed)

    def test_multiline_condition_kept(self):
        # Condition closes on a later line: only the keyword gap is fixed.
        fixed, _, changed = cj._fix_keyword_paren_spacing(
            "if (a &&", False)
        self.assertEqual(fixed, "if (a &&")
        self.assertFalse(changed)

    def test_block_comment_state_carried(self):
        _, in_block, _ = cj._fix_keyword_paren_spacing("/* start", False)
        self.assertTrue(in_block)
        fixed, in_block2, _ = cj._fix_keyword_paren_spacing(
            "end */ if(x)", in_block)
        self.assertFalse(in_block2)
        self.assertEqual(fixed, "end */ if (x)")

    def test_identifier_not_keyword(self):
        # 'myif(x)' is a call, not the 'if' keyword.
        fixed, _, changed = cj._fix_keyword_paren_spacing("myif(x);", False)
        self.assertEqual(fixed, "myif(x);")
        self.assertFalse(changed)


# ------------------------------------------------------------------------------
# _load_clean_java_config / _apply_settings
# ------------------------------------------------------------------------------
class TestConfig(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self._orig_settings = dict(cj.SETTINGS)

    def tearDown(self):
        cj.SETTINGS.clear()
        cj.SETTINGS.update(self._orig_settings)
        cj._apply_settings()

    def test_missing_file_keeps_defaults(self):
        cj._load_clean_java_config("/nonexistent/config.file")
        self.assertEqual(cj.TAB_WIDTH, 4)
        self.assertTrue(cj.FIX_KEYWORD_PAREN_SPACING)

    def test_config_override_and_reload(self):
        cfg = write_file(os.path.join(self.test_dir, "cfg.config"),
                         'TAB_WIDTH="2"\n'
                         '# comment line\n'
                         'ENSURE_TRAILING_NEWLINE="0"\n'
                         'UNKNOWN_KEY="ignored"\n')
        cj._load_clean_java_config(cfg)
        self.assertEqual(cj.TAB_WIDTH, 2)
        self.assertFalse(cj.ENSURE_TRAILING_NEWLINE)
        # Reload with a config restoring the defaults (merge-only loader:
        # a missing file keeps the previously merged values).
        cfg2 = write_file(os.path.join(self.test_dir, "default.config"),
                          'TAB_WIDTH="4"\n'
                          'ENSURE_TRAILING_NEWLINE="1"\n')
        cj._load_clean_java_config(cfg2)
        self.assertEqual(cj.TAB_WIDTH, 4)
        self.assertTrue(cj.ENSURE_TRAILING_NEWLINE)

    def test_invalid_values_fall_back(self):
        cfg = write_file(os.path.join(self.test_dir, "bad.config"),
                         'TAB_WIDTH=""\n')  # empty value ignored
        cj._load_clean_java_config(cfg)
        self.assertEqual(cj.TAB_WIDTH, 4)


# ------------------------------------------------------------------------------
# clean_whitespace_in_file (end-to-end)
# ------------------------------------------------------------------------------
class TestCleanWhitespaceInFile(TempDirTestCase):
    def test_full_clean(self):
        path = write_file(os.path.join(self.test_dir, "A.java"),
                          "package com.ex;\n"
                          "public class A {\n"
                          "\tvoid f() {  \n"
                          "if(x) { }\n"
                          "\n"
                          "\n"
                          "        int y = 1;\t\n"
                          "    }\n"
                          "}\n\n\n")
        self.assertTrue(cj.clean_whitespace_in_file(path))
        content = read_file(path)
        self.assertNotIn("\t", content)
        self.assertNotIn("if(x)", content)
        self.assertIn("if (x) { }", content)
        self.assertNotRegex(content, r"[ \t]+$", )
        self.assertNotIn("\n\n\n", content)
        self.assertTrue(content.endswith("}\n"))
        self.assertNotIn("\r", content)

    def test_crlf_converted_to_lf(self):
        path = write_file(os.path.join(self.test_dir, "B.java"),
                          "class B {\r\n    int x = 1;\r\n}\r\n",
                          newline="\r\n")
        self.assertTrue(cj.clean_whitespace_in_file(path))
        self.assertNotIn("\r", read_file(path))

    def test_clean_file_not_rewritten(self):
        clean = "class C {\n    int x = 1;\n}\n"
        path = write_file(os.path.join(self.test_dir, "C.java"), clean)
        mtime_before = os.path.getmtime(path)
        self.assertFalse(cj.clean_whitespace_in_file(path))
        self.assertEqual(os.path.getmtime(path), mtime_before,
                         "already-clean file must not be rewritten")

    def test_idempotent(self):
        dirty = "class D {\n\tif(x) { }  \n}\n\n\n"
        path = write_file(os.path.join(self.test_dir, "D.java"), dirty)
        self.assertTrue(cj.clean_whitespace_in_file(path))
        once = read_file(path)
        self.assertFalse(cj.clean_whitespace_in_file(path))
        self.assertEqual(read_file(path), once)

    def test_missing_file(self):
        self.assertFalse(cj.clean_whitespace_in_file(
            os.path.join(self.test_dir, "missing.java")))

    def test_string_and_comment_preserved(self):
        path = write_file(os.path.join(self.test_dir, "E.java"),
                          'class E {\n'
                          '    String s = "keep  this  spacing";  \n'
                          '    // keep\tcomment\ttabs\n'
                          '}\n')
        self.assertTrue(cj.clean_whitespace_in_file(path))
        content = read_file(path)
        self.assertIn("keep  this  spacing", content)
        self.assertIn("keep\tcomment\ttabs", content)
        # Trailing whitespace after the string line was fixed.
        self.assertNotRegex(content, r"[ \t]+$")


# ------------------------------------------------------------------------------
# get_git_modified_java_files
# ------------------------------------------------------------------------------
class TestGitModifiedFiles(TempDirTestCase):
    def _git(self, *args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True)

    def test_git_repo_modified_and_untracked(self):
        repo = os.path.join(self.test_dir, "repo")
        os.makedirs(repo)
        self._git("init", "-q", cwd=repo)
        self._git("config", "user.email", "t@t", cwd=repo)
        self._git("config", "user.name", "t", cwd=repo)
        tracked = write_file(os.path.join(repo, "Tracked.java"),
                             "class Tracked {\n}\n")
        self._git("add", "Tracked.java", cwd=repo)
        self._git("commit", "-qm", "init", cwd=repo)
        # Modify tracked file
        write_file(os.path.join(repo, "Tracked.java"),
                   "class Tracked {\n    int x = 1;\n}\n")
        # Untracked file
        write_file(os.path.join(repo, "Untracked.java"),
                   "class Untracked {\n}\n")
        # Untracked non-java file (must be ignored)
        write_file(os.path.join(repo, "notes.txt"), "hello\n")

        old_cwd = os.getcwd()
        os.chdir(repo)
        try:
            files = cj.get_git_modified_java_files()
        finally:
            os.chdir(old_cwd)
        names = [os.path.basename(f) for f in files]
        self.assertIn("Tracked.java", names)
        self.assertIn("Untracked.java", names)
        self.assertNotIn("notes.txt", names)

    def test_non_git_dir_returns_empty(self):
        old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            self.assertEqual(cj.get_git_modified_java_files(), [])
        finally:
            os.chdir(old_cwd)


# ------------------------------------------------------------------------------
# clean_java_files_in_directory
# ------------------------------------------------------------------------------
class TestCleanDirectory(TempDirTestCase):
    def test_recursive_clean_counts(self):
        write_file(os.path.join(self.test_dir, "a", "A.java"),
                   "class A {  \n}\n")
        write_file(os.path.join(self.test_dir, "a", "b", "B.java"),
                   "class B {\n\tint x;\n}\n")
        write_file(os.path.join(self.test_dir, "a", "readme.md"), "x\n")
        # Capture stdout to keep test output clean
        import io
        from unittest.mock import patch
        with patch("sys.stdout", new_callable=io.StringIO):
            cj.clean_java_files_in_directory(self.test_dir)
        self.assertEqual(read_file(os.path.join(self.test_dir, "a",
                                                "A.java")),
                         "class A {\n}\n")
        self.assertEqual(read_file(os.path.join(self.test_dir, "a", "b",
                                                "B.java")),
                         "class B {\n    int x;\n}\n")
        self.assertEqual(read_file(os.path.join(self.test_dir, "a",
                                                "readme.md")), "x\n")


# ------------------------------------------------------------------------------
# main() CLI (subprocess, real entry point)
# ------------------------------------------------------------------------------
class TestMainCli(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="telua_test_clean_cli_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run([sys.executable, CLEAN_SCRIPT, *args],
                              capture_output=True, text=True,
                              cwd=self.test_dir)

    def test_help(self):
        res = self._run("--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("clean_java.py", res.stdout)

    def test_file_target(self):
        path = write_file(os.path.join(self.test_dir, "F.java"),
                          "class F {  \n}\n")
        res = self._run(path)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(read_file(path), "class F {\n}\n")

    def test_dir_target(self):
        write_file(os.path.join(self.test_dir, "sub", "G.java"),
                   "class G {\n\tx;\n}\n")
        res = self._run(os.path.join(self.test_dir, "sub"))
        self.assertEqual(res.returncode, 0)
        self.assertEqual(
            read_file(os.path.join(self.test_dir, "sub", "G.java")),
            "class G {\n    x;\n}\n")

    def test_all_flag(self):
        write_file(os.path.join(self.test_dir, "H.java"),
                   "class H {  \n}\n")
        res = self._run("--all")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(read_file(os.path.join(self.test_dir, "H.java")),
                         "class H {\n}\n")

    def test_diff_flag_runs(self):
        res = self._run("--diff")
        self.assertEqual(res.returncode, 0)

    def test_invalid_target(self):
        # A non-.java, non-existent target prints an error hint but exits 0
        # (fallthrough branch of the CLI - no exception, no file touched).
        res = self._run("no_such_thing.xyz")
        self.assertEqual(res.returncode, 0)
        self.assertIn("not a valid option", res.stdout)


if __name__ == "__main__":
    unittest.main()
