#!/usr/bin/env python3
# ==============================================================================
# Unit tests for telua_web_docs.py & Sphinx Docs Web API
# ==============================================================================

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
for p in (str(REPO_ROOT), str(WEB_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import telua_web_docs as twd
import telua_web as tw


class TestTeluaWebDocsConverters(unittest.TestCase):
    def test_rst_to_html_basic(self):
        rst = "My Heading\n==========\n\nHello **world**.\n\n* Item A\n* Item B\n"
        html = twd.rst_to_html(rst)
        self.assertIn("My Heading", html)
        self.assertIn("<strong>world</strong>", html)
        self.assertIn("<li>", html)

    def test_rst_to_html_admonition(self):
        rst = ".. note::\n\n   Pay close attention.\n"
        html = twd.rst_to_html(rst)
        self.assertIn("admonition", html)
        self.assertIn("Pay close attention.", html)

    def test_html_to_rst_headings_and_formatting(self):
        html = "<h1>Main Title</h1><p>This is <strong>bold</strong> and <em>italic</em> and <code>code</code>.</p>"
        rst = twd.html_to_rst(html)
        self.assertIn("Main Title\n==========", rst)
        self.assertIn("**bold**", rst)
        self.assertIn("*italic*", rst)
        self.assertIn("``code``", rst)

    def test_html_to_rst_lists(self):
        html = "<ul><li>First</li><li>Second</li></ul><ol><li>One</li><li>Two</li></ol>"
        rst = twd.html_to_rst(html)
        self.assertIn("* First", rst)
        self.assertIn("* Second", rst)
        self.assertIn("#. One", rst)
        self.assertIn("#. Two", rst)

    def test_html_to_rst_code_block(self):
        html = "<pre class=\"ql-syntax\">def foo():\n    return 42</pre>"
        rst = twd.html_to_rst(html)
        self.assertIn(".. code-block:: text", rst)
        self.assertIn("    def foo():", rst)

    def test_html_to_rst_admonition(self):
        html = '<div class="admonition note"><p class="admonition-title">Note</p><p>Important detail.</p></div>'
        rst = twd.html_to_rst(html)
        self.assertIn(".. note::", rst)
        self.assertIn("    Important detail.", rst)

    def test_roundtrip_conversion(self):
        original_rst = "Architecture\n============\n\nOverview of the system.\n\n* Service A\n* Service B\n"
        html = twd.rst_to_html(original_rst)
        converted_rst = twd.html_to_rst(html)
        self.assertIn("Architecture", converted_rst)
        self.assertIn("Overview of the system.", converted_rst)
        self.assertIn("* Service A", converted_rst)

    def test_mermaid_and_table_and_image_support(self):
        rst = (
            "System Flows\n"
            "============\n\n"
            ".. mermaid::\n\n"
            "   graph TB\n"
            "   A --> B\n\n"
            ".. list-table:: Tech Breakdown\n"
            "   :header-rows: 1\n\n"
            "   * - Layer\n"
            "     - Framework\n"
            "   * - App\n"
            "     - Kotlin\n\n"
            ".. image:: /path/to/diagram.png\n"
            "   :alt: Diagram Image\n"
        )
        html = twd.rst_to_html(rst)
        self.assertIn("mermaid-block", html)
        self.assertIn("<table", html)
        self.assertIn("<img", html)

        # Convert back to RST
        back_rst = twd.html_to_rst(html)
        self.assertIn(".. mermaid::", back_rst)
        self.assertIn("graph TB", back_rst)
        self.assertIn(".. list-table:: Tech Breakdown", back_rst)
        self.assertIn("Kotlin", back_rst)
        self.assertIn(".. image:: /path/to/diagram.png", back_rst)

    def test_plantuml_support(self):
        rst = (
            "Architecture Model\n"
            "==================\n\n"
            ".. uml::\n\n"
            "   @startuml\n"
            "   Alice -> Bob: Call Service\n"
            "   Bob --> Alice: Return Status\n"
            "   @enduml\n"
        )
        html = twd.rst_to_html(rst)
        self.assertIn("plantuml-block", html)
        self.assertIn("Alice -&gt; Bob", html)

        # Convert back to RST
        back_rst = twd.html_to_rst(html)
        self.assertIn(".. uml::", back_rst)
        self.assertIn("Alice -> Bob: Call Service", back_rst)

    def test_quill_mermaid_dom_preservation(self):
        quill_html = (
            '<p>Section text</p>'
            '<div class="mermaid-block" contenteditable="false" data-mermaid="graph TB\n   App --> HAL">'
            '  <div class="mermaid-header">'
            '    <span class="mermaid-label">Mermaid</span>'
            '    <span class="mermaid-chip">.. mermaid::</span>'
            '  </div>'
            '  <div class="mermaid-diagram-wrap"><svg><g id="test"></g></svg></div>'
            '  <pre class="mermaid" style="display:none;">graph TB\n   App --> HAL</pre>'
            '</div>'
            '<p>Following text</p>'
        )
        back_rst = twd.html_to_rst(quill_html)
        self.assertIn(".. mermaid::", back_rst)
        self.assertIn("App --> HAL", back_rst)
        self.assertIn("Section text", back_rst)
        self.assertIn("Following text", back_rst)


class TestTeluaWebDocsAPI(unittest.TestCase):
    def setUp(self):
        tw.app.config["TESTING"] = True
        self.client = tw.app.test_client()
        self.test_dir = tempfile.mkdtemp(prefix="telua_web_docs_test_")
        self.orig_root = tw.ROOT
        tw.ROOT = Path(self.test_dir)

        # Create sample docs structure in temp dir
        docs_dir = tw.ROOT / "sphinx" / "templates" / "architecture"
        docs_dir.mkdir(parents=True, exist_ok=True)
        self.sample_rst = docs_dir / "index.rst"
        self.sample_rst.write_text("Test Title\n==========\n\nContent here.\n", encoding="utf-8")

    def tearDown(self):
        tw.ROOT = self.orig_root
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_api_docs_files(self):
        res = self.client.get("/api/docs/files")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertGreaterEqual(len(data.get("files", [])), 1)

    def test_api_docs_file_read(self):
        rel_path = "sphinx/templates/architecture/index.rst"
        res = self.client.get(f"/api/docs/file?name={rel_path}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("name"), rel_path)
        self.assertIn("Test Title", data.get("rst", ""))
        self.assertIn("Test Title", data.get("html", ""))

    def test_api_docs_file_read_invalid(self):
        res = self.client.get("/api/docs/file?name=../../escape.rst")
        self.assertEqual(res.status_code, 400)
        res2 = self.client.get("/api/docs/file?name=notfound.rst")
        self.assertEqual(res2.status_code, 404)

    def test_api_docs_convert_endpoint(self):
        # rst2html
        res = self.client.post("/api/docs/convert", json={
            "content": "Sample\n======\n\nText here.",
            "direction": "rst2html",
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("Sample", res.get_json().get("html", ""))

        # html2rst
        res2 = self.client.post("/api/docs/convert", json={
            "content": "<h1>Sample</h1><p>Text here.</p>",
            "direction": "html2rst",
        })
        self.assertEqual(res2.status_code, 200)
        self.assertIn("Sample\n======", res2.get_json().get("rst", ""))

    def test_api_docs_file_write_html_and_rst(self):
        rel_path = "sphinx/templates/architecture/index.rst"
        # Write via HTML (Quill format)
        res = self.client.post("/api/docs/file", json={
            "name": rel_path,
            "content": "<h1>Updated Title</h1><p>Updated content.</p>",
            "format": "html",
        })
        self.assertEqual(res.status_code, 200)
        saved = self.sample_rst.read_text(encoding="utf-8")
        self.assertIn("Updated Title\n=============", saved)
        self.assertIn("Updated content.", saved)

        # Check backup created
        bak = self.sample_rst.with_suffix(".rst.bak")
        self.assertTrue(bak.is_file())

    def test_api_docs_file_write_new_uploaded_file(self):
        # Save a new uploaded document that didn't exist before
        new_name = "new_section.rst"
        res = self.client.post("/api/docs/file", json={
            "name": new_name,
            "content": "<h1>Uploaded Section</h1><p>From computer.</p>",
            "format": "html",
        })
        self.assertEqual(res.status_code, 200)
        target = tw.ROOT / "docs" / new_name
        self.assertTrue(target.is_file())
        self.assertIn("Uploaded Section", target.read_text(encoding="utf-8"))

    def test_api_docs_custom_directory(self):
        # Create a separate custom docs folder
        custom_docs = tw.ROOT / "my_external_docs"
        custom_docs.mkdir(parents=True, exist_ok=True)
        custom_file = custom_docs / "guide.rst"
        custom_file.write_text("External Guide\n==============\n\nExternal docs content.\n", encoding="utf-8")

        # Scan with custom dir query param
        res = self.client.get(f"/api/docs/files?dir={custom_docs.as_posix()}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(len(data.get("files", [])), 1)
        self.assertEqual(data["files"][0]["name"], "guide.rst")

        # Read file from custom dir
        res2 = self.client.get(f"/api/docs/file?name=guide.rst&dir={custom_docs.as_posix()}")
        self.assertEqual(res2.status_code, 200)
        self.assertIn("External Guide", res2.get_json().get("rst", ""))

        # Write file to custom dir
        res3 = self.client.post("/api/docs/file", json={
            "name": "guide.rst",
            "dir": custom_docs.as_posix(),
            "content": "<h1>Updated External</h1><p>New content.</p>",
            "format": "html",
        })
        self.assertEqual(res3.status_code, 200)
        self.assertIn("Updated External\n================", custom_file.read_text(encoding="utf-8"))

    def test_api_docs_start(self):
        # Test /api/docs/start endpoint
        res = self.client.post("/api/docs/start", json={"port": 8899})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("port"), 8899)
        self.assertIn("http://localhost:8899", data.get("url", ""))

        # Clean up any spawned process
        if tw._DOCS_SERVER_PROC is not None:
            try:
                tw._DOCS_SERVER_PROC.terminate()
                tw._DOCS_SERVER_PROC.wait(timeout=2)
            except Exception:
                pass
            tw._DOCS_SERVER_PROC = None


if __name__ == "__main__":
    unittest.main()
