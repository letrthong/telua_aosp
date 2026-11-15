import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INJECT = ROOT / "sphinx" / "scripts" / "inject_plantuml.py"

RST = """Legacy
======

.. uml::

   @startuml
   actor User
   participant "Frontend" as UI
   User -> UI : Click
   @enduml
"""

LEGACY_CONFS = {
    "no_plantuml": "project = 'Old'\nextensions = ['sphinx.ext.autodoc']\n",
    "no_extensions": "project = 'Old'\n",
    "broken_cmd": "project = 'Old'\nextensions = ['sphinxcontrib.plantuml']\nplantuml = 'plantuml_missing_bin'\nplantuml_output_format = 'svg'\n",
}


class TestInjectPlantUML(unittest.TestCase):
    def _build(self, conf_text):
        td = tempfile.mkdtemp()
        try:
            src = Path(td) / "src"
            out = Path(td) / "out"
            src.mkdir()
            (src / "conf.py").write_text(conf_text, encoding="utf-8")
            (src / "index.rst").write_text(RST, encoding="utf-8")

            r = subprocess.run([sys.executable, str(INJECT), str(src)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            # Idempotent
            subprocess.run([sys.executable, str(INJECT), str(src)], capture_output=True, text=True)
            conf = (src / "conf.py").read_text(encoding="utf-8")
            self.assertEqual(conf.count("telua-plantuml-autoconfig"), 1)

            res = subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", str(src), str(out)],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn("cannot be run", res.stderr)
            html = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="plantuml"', html)
            self.assertIn("<img src=\"_images/plantuml-", html)
            self.assertTrue(list((out / "_images").glob("*.svg")))
            self.assertTrue((out / "_static" / "telua_plantuml.css").is_file())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_legacy_confs(self):
        for name, conf in LEGACY_CONFS.items():
            with self.subTest(name=name):
                self._build(conf)


if __name__ == "__main__":
    unittest.main()
