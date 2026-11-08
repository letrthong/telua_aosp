#!/usr/bin/env python3
# ==============================================================================
# Unit tests for unused_methods_report.py
#
# Covers:
#   - _extract_decl: method-declaration parsing (modifiers, annotations,
#     control keywords, qualified calls, 'synchronized' statement form)
#   - _visibility: report column formatting
#   - _check_whitespace: whitespace violation detection (trailing whitespace,
#     leading tabs, keyword-paren spacing, blank-line runs, CRLF, EOF newline)
#   - is_test_file: test-code detection (path components + JUnit hints)
#   - resolve_scope_dir: module-root resolution (src dir / project markers)
#   - collect_java_files: recursive collection with pruning + dedup
#   - scan_java_file: declarations, contracts, unused params, test methods
#   - build_report / build_report_lines: end-to-end report content
#   - main: CLI wiring (--diff, --all, file target, --out)
# ==============================================================================

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
REPORT_SCRIPT = os.path.join(REPO_ROOT, "python", "unused_methods_report.py")
os.environ.setdefault("TELUA_SKIP_GJF_CLONE", "1")

# Ensure repo root and python/ subdir are in python path
for p in (REPO_ROOT, os.path.join(REPO_ROOT, "python")):
    if p not in sys.path:
        sys.path.insert(0, p)

import unused_methods_report as umr


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return path


class TempDirTestCase(unittest.TestCase):
    """Base class providing a per-test temp directory."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="telua_test_report_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)


# ------------------------------------------------------------------------------
# _extract_decl
# ------------------------------------------------------------------------------
class TestExtractDecl(unittest.TestCase):
    def test_simple_method(self):
        # prefix = full 'modifiers + return type' text before the name
        self.assertEqual(umr._extract_decl("public void foo()"),
                         ("foo", "public void", {"public"}))

    def test_modifiers_and_generic_return(self):
        decl = umr._extract_decl(
            "private static final List<String> bar(int x)")
        self.assertIsNotNone(decl)
        name, prefix, mods = decl
        self.assertEqual(name, "bar")
        self.assertEqual(mods, {"private", "static", "final"})

    def test_annotated_method(self):
        self.assertEqual(umr._extract_decl("@Override public void run()"),
                         ("run", "public void", {"public"}))

    def test_qualified_call_rejected(self):
        self.assertIsNone(umr._extract_decl("obj.name(x)"))
        self.assertIsNone(umr._extract_decl("Class.name(x)"))

    def test_control_keywords_rejected(self):
        self.assertIsNone(umr._extract_decl("return foo()"))
        self.assertIsNone(umr._extract_decl("new Foo()"))
        self.assertIsNone(umr._extract_decl("if (x)"))
        self.assertIsNone(umr._extract_decl("while (it.hasNext())"))

    def test_synchronized_statement_rejected_as_method(self):
        # 'synchronized (mLock) {' parses as a decl named 'synchronized' but
        # the caller filters it via the statement-form check.
        decl = umr._extract_decl("synchronized (mLock) {")
        self.assertIsNotNone(decl)
        self.assertEqual(decl[0], "synchronized")

    def test_empty_and_garbage(self):
        self.assertIsNone(umr._extract_decl(""))
        self.assertIsNone(umr._extract_decl("foo"))
        self.assertIsNone(umr._extract_decl("= foo()"))
        self.assertIsNone(umr._extract_decl("}"))

    def test_visibility(self):
        self.assertEqual(umr._visibility({"public"}), "public")
        self.assertEqual(umr._visibility({"private", "static"}),
                         "private static")
        self.assertEqual(umr._visibility(set()), "package")
        self.assertEqual(umr._visibility({"protected"}), "protected")


# ------------------------------------------------------------------------------
# _check_whitespace
# ------------------------------------------------------------------------------
class TestCheckWhitespace(unittest.TestCase):
    def test_clean_file_no_violations(self):
        lines = ["package com.ex;", "public class A {", "    void f() {",
                 "        if (x) { }", "    }", "}"]
        self.assertEqual(umr._check_whitespace(lines), [])

    def test_trailing_whitespace(self):
        violations = umr._check_whitespace(["int x = 1;   "])
        self.assertEqual(len(violations), 1)
        line_no, kind, src = violations[0]
        self.assertEqual(line_no, 1)
        self.assertIn("trailing whitespace", kind)
        self.assertEqual(src, "int x = 1;   ")

    def test_leading_tab(self):
        violations = umr._check_whitespace(["\tint x = 1;"])
        self.assertEqual(len(violations), 1)
        self.assertIn("leading tab", violations[0][1])

    def test_keyword_paren_spacing(self):
        violations = umr._check_whitespace(["        if(x) { }"])
        self.assertEqual(len(violations), 1)
        self.assertIn("keyword-paren", violations[0][1])
        self.assertEqual(violations[0][2], "        if(x) { }")

    def test_keyword_paren_in_string_not_flagged(self):
        # 'if(x)' inside a string literal must not be reported.
        violations = umr._check_whitespace(
            ['        String s = "if(x)";'])
        self.assertEqual(violations, [])

    def test_blank_line_run(self):
        violations = umr._check_whitespace(["int a;", "", "", "int b;"])
        self.assertEqual(len(violations), 1)
        self.assertIn("blank line run", violations[0][1])
        self.assertEqual(violations[0][0], 3)  # 2nd blank of the run

    def test_crlf(self):
        violations = umr._check_whitespace(["int x = 1;\r"])
        self.assertEqual(len(violations), 1)
        self.assertIn("CRLF", violations[0][1])

    def test_missing_trailing_newline(self):
        # raw_lines from split('\n') end with '' when the file ends with \n.
        # Honour the active config: skip the check when disabled.
        if not umr.ENSURE_TRAILING_NEWLINE:
            self.skipTest("ENSURE_TRAILING_NEWLINE disabled in config")
        violations = umr._check_whitespace(["class A {", "}"])
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], 0)
        self.assertIn("trailing newline", violations[0][1])

    def test_trailing_newline_ok(self):
        if not umr.ENSURE_TRAILING_NEWLINE:
            self.skipTest("ENSURE_TRAILING_NEWLINE disabled in config")
        violations = umr._check_whitespace(["class A {", "}", ""])
        self.assertEqual(violations, [])

    def test_multiple_violations_same_line(self):
        violations = umr._check_whitespace(["\tif(x) { }  "])
        kinds = [v[1] for v in violations]
        self.assertEqual(len(kinds), 3)
        self.assertTrue(any("leading tab" in k for k in kinds))
        self.assertTrue(any("keyword-paren" in k for k in kinds))
        self.assertTrue(any("trailing whitespace" in k for k in kinds))


# ------------------------------------------------------------------------------
# is_test_file
# ------------------------------------------------------------------------------
class TestIsTestFile(unittest.TestCase):
    def test_test_dir_path(self):
        for comp in ("test", "tests", "androidTest", "javatests"):
            path = os.path.join("root", comp, "com", "Foo.java")
            self.assertTrue(umr.is_test_file(path, []),
                            f"{path} should be detected as test file")

    def test_junit_import_hint(self):
        masked = ["import org.junit.Test;", "public class FooTest { }"]
        self.assertTrue(umr.is_test_file("src/com/Foo.java", masked))

    def test_test_annotation_hint(self):
        masked = ["@Test", "public void foo() { }"]
        self.assertTrue(umr.is_test_file("src/com/Foo.java", masked))

    def test_production_file(self):
        masked = ["package com.ex;", "public class Foo {", "}"]
        self.assertFalse(umr.is_test_file("src/com/Foo.java", masked))


# ------------------------------------------------------------------------------
# resolve_scope_dir / collect_java_files
# ------------------------------------------------------------------------------
class TestScopeAndCollect(TempDirTestCase):
    def test_resolve_scope_dir_walks_to_src(self):
        deep = write_file(os.path.join(
            self.test_dir, "src", "com", "ex", "A.java"), "")
        scope = umr.resolve_scope_dir(deep)
        self.assertEqual(os.path.basename(scope), "src")

    def test_resolve_scope_dir_project_marker(self):
        write_file(os.path.join(self.test_dir, "Android.bp"), "")
        deep = write_file(os.path.join(
            self.test_dir, "java", "com", "A.java"), "")
        scope = umr.resolve_scope_dir(deep)
        self.assertEqual(scope, self.test_dir)

    def test_resolve_scope_dir_fallback_to_file_dir(self):
        deep = write_file(os.path.join(
            self.test_dir, "a", "b", "A.java"), "")
        scope = umr.resolve_scope_dir(deep)
        self.assertEqual(scope, os.path.dirname(deep))

    def test_collect_java_files_recursive_and_pruned(self):
        write_file(os.path.join(self.test_dir, "a", "A.java"), "")
        write_file(os.path.join(self.test_dir, "a", "b", "B.java"), "")
        write_file(os.path.join(self.test_dir, "out", "C.java"), "")
        write_file(os.path.join(self.test_dir, "a", "notes.txt"), "")
        files = umr.collect_java_files([self.test_dir])
        names = [os.path.basename(f) for f in files]
        self.assertIn("A.java", names)
        self.assertIn("B.java", names)
        self.assertNotIn("C.java", names)  # 'out' is pruned
        self.assertNotIn("notes.txt", names)

    def test_collect_java_files_dedup_nested_roots(self):
        write_file(os.path.join(self.test_dir, "a", "A.java"), "")
        files = umr.collect_java_files([self.test_dir,
                                        os.path.join(self.test_dir, "a")])
        self.assertEqual(len(files), 1)


# ------------------------------------------------------------------------------
# scan_java_file
# ------------------------------------------------------------------------------
class TestScanJavaFile(TempDirTestCase):
    def test_decls_params_contracts(self):
        path = write_file(os.path.join(self.test_dir, "A.java"), """\
package com.ex;
interface Api {
    void contract();
}
abstract class Base {
    abstract void baseContract();
}
class Impl extends Base {
    private int usedField;
    private void used() { helper(1); }
    private void helper(int value) { usedField = value; }
    private void dead() { }
    @Override
    public void contract() { }
}
""")
        data = umr.scan_java_file(path)
        self.assertIsNotNone(data)
        decl_names = {name for _, name, _ in data["decls"]}
        self.assertIn("dead", decl_names)
        self.assertIn("used", decl_names)
        self.assertIn("helper", decl_names)
        self.assertNotIn("contract", decl_names)  # @Override skipped
        self.assertIn("contract", data["contracts"])
        self.assertIn("baseContract", data["contracts"])
        # helper has param 'value' used in body -> not reported as unused
        param_names = [p for _, _, plist, _ in data["params"]
                       for p, _ in plist]
        self.assertIn("value", param_names)

    def test_unused_param_detected(self):
        path = write_file(os.path.join(self.test_dir, "B.java"), """\
package com.ex;
class B {
    void m(int unusedParam) { }
}
""")
        data = umr.scan_java_file(path)
        unused = [(m, p) for _, m, plist, _ in data["params"]
                  for p, _ in plist
                  if not umr._ident_pattern(p).search(
                      next(b for ml, mn, pl, b in data["params"]
                           if mn == m))]
        self.assertIn(("m", "unusedParam"), unused)

    def test_commented_out_param_skipped(self):
        path = write_file(os.path.join(self.test_dir, "C.java"), """\
package com.ex;
class C {
    void m(int /*name*/ x) { }
}
""")
        data = umr.scan_java_file(path)
        self.assertEqual(data["params"], [])

    def test_test_method_not_in_decls(self):
        path = write_file(os.path.join(self.test_dir, "D.java"), """\
package com.ex;
import org.junit.Test;
class D {
    @Test
    public void frameworkInvoked() { }
    private void plain() { }
}
""")
        data = umr.scan_java_file(path)
        decl_names = {name for _, name, _ in data["decls"]}
        self.assertNotIn("frameworkInvoked", decl_names)
        self.assertIn("plain", decl_names)
        self.assertTrue(data["is_test"])

    def test_unreadable_file_returns_none(self):
        self.assertIsNone(umr.scan_java_file(
            os.path.join(self.test_dir, "missing.java")))


# ------------------------------------------------------------------------------
# build_report / build_report_lines (end-to-end)
# ------------------------------------------------------------------------------
class TestBuildReport(TempDirTestCase):
    def _make_module(self):
        src = os.path.join(self.test_dir, "src", "com", "ex")
        write_file(os.path.join(src, "Dead.java"), """\
package com.ex;
public class Dead {
    private void entryPoint() { usedMethod(); }
    private void usedMethod() { helper(); }
    private void helper() { }
    private void deadMethod() { }
    void withUnusedParam(int spare) { }
}
""")
        write_file(os.path.join(src, "Dirty.java"),
                   "package com.ex;\npublic class Dirty {\n"
                   "    void m() {\n        if(x) { }\n\n\n    }\n"
                   "\tint y = 1;  \n}\n")
        write_file(os.path.join(src, "DeadTest.java"), """\
package com.ex;
import org.junit.Test;
public class DeadTest {
    @Test
    public void frameworkInvokedTest() { }
    private void plainHelper() { }
}
""")
        write_file(os.path.join(self.test_dir, "src", "tests",
                                "PathBasedTest.java"), """\
package tests;
public class PathBasedTest {
    public void frameworkInvokedToo() { }
}
""")

    def test_build_report_counts(self):
        self._make_module()
        target = os.path.join(self.test_dir, "src", "com", "ex", "Dead.java")
        (unused, unused_params, _decl, _dirs, file_count,
         test_count, ws_by_file) = umr.build_report([target])
        unused_names = {name for _, _, name, _ in unused}
        self.assertIn("deadMethod", unused_names)
        self.assertIn("entryPoint", unused_names)  # nothing calls it
        # usedMethod/helper are called from other bodies -> used
        self.assertNotIn("usedMethod", unused_names)
        self.assertNotIn("helper", unused_names)
        # Test files are skipped from decl reporting but counted
        self.assertEqual(test_count, 2)
        self.assertEqual(file_count, 4)
        # Unused parameter 'spare' in Dead.java (name absent from body)
        self.assertTrue(any(pname == "spare"
                            for _, _, _, pname, _ in unused_params))
        # Whitespace violations found in Dirty.java
        ws_files = {os.path.basename(p): v for p, v in ws_by_file.items()}
        self.assertIn("Dirty.java", ws_files)
        kinds = [k for _, k, _ in ws_files["Dirty.java"]]
        self.assertTrue(any("keyword-paren" in k for k in kinds))
        self.assertTrue(any("blank line run" in k for k in kinds))
        self.assertTrue(any("leading tab" in k for k in kinds))
        self.assertTrue(any("trailing whitespace" in k for k in kinds))

    def test_report_lines_content(self):
        self._make_module()
        target = os.path.join(self.test_dir, "src", "com", "ex", "Dead.java")
        text = "\n".join(umr.build_report_lines([target]))
        self.assertIn("[1] Unused methods", text)
        self.assertIn("[2] Unused parameters", text)
        self.assertIn("[3] Whitespace violations", text)
        self.assertIn("[4] google-java-format violations", text)
        self.assertIn("deadMethod", text)
        self.assertIn("spare", text)
        self.assertIn("keyword-paren", text)
        self.assertIn("if(x) { }", text)  # offending source line shown
        self.assertIn("Test files skipped", text)
        self.assertNotIn("frameworkInvokedTest", text)
        self.assertNotIn("plainHelper", text)
        self.assertNotIn("frameworkInvokedToo", text)


# ------------------------------------------------------------------------------
# [4] google-java-format violations
# ------------------------------------------------------------------------------
class TestGoogleJavaFormat(TempDirTestCase):
    def test_diff_google_java_format_lines(self):
        orig = ["package com.ex;", "public class A{", "  void f(){}", "}"]
        fmt = ["package com.ex;", "public class A {", "    void f() {}", "}"]
        violations = umr._diff_google_java_format_lines(orig, fmt)
        self.assertTrue(len(violations) >= 1)
        self.assertEqual(violations[0][0], 2)
        self.assertIn("google-java-format", violations[0][1])

    def test_find_jar_or_script_in_dir(self):
        script = write_file(
            os.path.join(self.test_dir, "run-google-java-format.sh"),
            "#!/bin/bash\n")
        found = umr._find_jar_or_script_in_dir(self.test_dir)
        self.assertIsNotNone(found)
        self.assertEqual(found[0], "hook")
        self.assertIn(script, found[1])

    def test_hook_runner_is_readonly_on_target(self):
        src_file = write_file(
            os.path.join(self.test_dir, "Sample.java"),
            "package com.ex;\npublic class Sample{\n}\n")
        with open(src_file, "rb") as f:
            before = f.read()

        # Mock pre-commit hook that rewrites its argument file in-place
        mock_hook = write_file(
            os.path.join(self.test_dir, "mock_hook.py"),
            "import sys\n"
            "p = sys.argv[-1]\n"
            "with open(p, 'r', encoding='utf-8') as f:\n"
            "    txt = f.read()\n"
            "with open(p, 'w', encoding='utf-8') as f:\n"
            "    f.write(txt.replace('Sample{', 'Sample {'))\n")
        runner = ("hook", [sys.executable, mock_hook])
        violations = umr._check_google_java_format_file(src_file, runner)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], 2)
        self.assertIn("Sample {", violations[0][1])
        with open(src_file, "rb") as f:
            self.assertEqual(f.read(), before,
                             "hook check must never modify the original file")

    def test_builtin_google_java_format_checker(self):
        lines = [
            "package com.ex;",
            "import java.util.*;",
            "public class Sample{",
            "    void f(int a,int b)",
            "    {",
            "        int x = 1; int y = 2;",
            "    }",
            "}",
        ]
        violations = umr._check_builtin_google_java_format_lines(lines)
        kinds = [k for _, k, _ in violations]
        self.assertTrue(any("wildcard import" in k for k in kinds))
        self.assertTrue(any("missing space before '{'" in k for k in kinds))
        self.assertTrue(any("missing space after ','" in k for k in kinds))
        self.assertTrue(any("'{' should sit at end" in k for k in kinds))
        self.assertTrue(any("multiple statements" in k for k in kinds))

    def test_builtin_line_length_and_import_exemption(self):
        long_import = "import " + "a." * 50 + "Foo;"
        long_code = "        String s = \"" + "x" * 95 + "\";"
        lines = [
            "package com.ex;",
            long_import,
            "public class Sample {",
            long_code,
            "}",
        ]
        violations = umr._check_builtin_google_java_format_lines(lines)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], 4)
        self.assertIn("> 100 columns", violations[0][1])

    def test_builtin_clean_file_zero_violations(self):
        lines = [
            "package com.ex;",
            "import java.util.List;",
            "public class Clean {",
            "    void f(int a, int b) {",
            "        if (a > b) {",
            "            int x = a + b;",
            "        } else if (a == b) {",
            "            int y = 0;",
            "        } else {",
            "            int z = 1;",
            "        }",
            "    }",
            "}",
        ]
        self.assertEqual(
            umr._check_builtin_google_java_format_lines(lines), [])

    def test_missing_braces_on_if_and_else_detected(self):
        lines = [
            "package com.ex;",
            "public class NoBraces {",
            "    void f(int a) {",
            "        if (a > 0) return;",
            "        if (a < 0)",
            "            a = 0;",
            "        else",
            "            a = 1;",
            "    }",
            "}",
        ]
        violations = umr._check_builtin_google_java_format_lines(lines)
        by_line = {line_no: kind for line_no, kind, _ in violations}
        self.assertIn(4, by_line)
        self.assertIn("'if' statement must use '{}' braces", by_line[4])
        self.assertIn(5, by_line)
        self.assertIn("'if' statement must use '{}' braces", by_line[5])
        self.assertIn(7, by_line)
        self.assertIn("'else' statement must use '{}' braces", by_line[7])

    def test_check_google_java_format_toggle(self):
        f = write_file(
            os.path.join(self.test_dir, "Bad.java"),
            "package com.ex;\npublic class Bad{\n}\n")
        old_flag = umr.ENABLE_GOOGLE_JAVA_FORMAT
        try:
            umr.ENABLE_GOOGLE_JAVA_FORMAT = True
            gjf_map, avail = umr.check_google_java_format(
                [f], runner=("builtin", []))
            self.assertTrue(avail)
            self.assertIn(os.path.abspath(f), gjf_map)

            umr.ENABLE_GOOGLE_JAVA_FORMAT = False
            gjf_map_off, avail_off = umr.check_google_java_format(
                [f], runner=("builtin", []))
            self.assertFalse(avail_off)
            self.assertEqual(gjf_map_off, {})
        finally:
            umr.ENABLE_GOOGLE_JAVA_FORMAT = old_flag


# ------------------------------------------------------------------------------
# main() CLI
# ------------------------------------------------------------------------------
class TestMainCli(TempDirTestCase):
    def _make_module(self):
        src = os.path.join(self.test_dir, "src", "com", "ex")
        write_file(os.path.join(src, "Dead.java"), """\
package com.ex;
public class Dead {
    private void deadMethod() { }
}
""")

    def _run_main(self, argv, cwd):
        old_cwd = os.getcwd()
        old_stdout = sys.stdout
        import io
        buf = io.StringIO()
        sys.stdout = buf
        try:
            os.chdir(cwd)
            code = umr.main(argv)
        finally:
            sys.stdout = old_stdout
            os.chdir(old_cwd)
        return code, buf.getvalue()

    def test_main_file_target_and_out(self):
        self._make_module()
        target = os.path.join(self.test_dir, "src", "com", "ex", "Dead.java")
        out = os.path.join(self.test_dir, "custom_report.txt")
        code, output = self._run_main([target, "--out", out],
                                      cwd=self.test_dir)
        self.assertEqual(code, 0)
        self.assertIn("deadMethod", output)
        self.assertTrue(os.path.isfile(out))
        with open(out, encoding="utf-8") as f:
            self.assertIn("deadMethod", f.read())

    def test_main_default_scans_cwd(self):
        self._make_module()
        code, output = self._run_main([], cwd=self.test_dir)
        self.assertEqual(code, 0)
        self.assertIn("deadMethod", output)
        default_report = os.path.join(self.test_dir,
                                      umr.DEFAULT_REPORT_FILE)
        self.assertTrue(os.path.isfile(default_report))

    def test_main_no_java_files(self):
        code, _ = self._run_main([], cwd=self.test_dir)
        self.assertEqual(code, 0)

    def test_main_invalid_target(self):
        code, output = self._run_main(["no_such_file_or_dir"],
                                      cwd=self.test_dir)
        self.assertEqual(code, 1)
        self.assertIn("not a valid option", output)

    def test_main_help(self):
        code, output = self._run_main(["--help"], cwd=self.test_dir)
        self.assertEqual(code, 1)  # help returns None -> main returns 1
        self.assertIn("Usage", output)


class TestScriptExecutable(unittest.TestCase):
    """Run the script as a subprocess to verify the CLI entry point."""

    def test_subprocess_report_and_readonly(self):
        tmp = tempfile.mkdtemp(prefix="telua_test_report_cli_")
        try:
            src = os.path.join(tmp, "src", "com", "ex")
            write_file(os.path.join(src, "Dead.java"), """\
package com.ex;
public class Dead {
    private void deadMethod() { }
}
""")
            target = os.path.join(src, "Dead.java")
            with open(target, "rb") as f:
                before = f.read()
            res = subprocess.run(
                [sys.executable, REPORT_SCRIPT, target,
                 "--out", os.path.join(tmp, "r.txt")],
                capture_output=True, text=True, cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("deadMethod", res.stdout)
            with open(target, "rb") as f:
                self.assertEqual(f.read(), before,
                                 "report must not modify the target file")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
