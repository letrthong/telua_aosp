# -- Sphinx Configuration for API Reference Project --

project = 'API & SDK Reference'
copyright = '2026, API Platform Team'
author = 'API Platform Team'

extensions = []

for ext in ['sphinxcontrib.mermaid', 'sphinxcontrib.plantuml', 'sphinx_copybutton']:
    try:
        __import__(ext)
        extensions.append(ext)
    except ImportError:
        pass

import os
import shutil
import sys
from pathlib import Path

# PlantUML CLI Wrapper: local binary, jar or online SVG fallback
_wrapper = os.environ.get("PLANTUML_WRAPPER")
if not (_wrapper and Path(_wrapper).is_file()):
    _curr = Path(__file__).resolve().parent
    for _ in range(6):
        for candidate_sub in [
            "plantuml_wrapper.py",
            "scripts/plantuml_wrapper.py",
            "sphinx/scripts/plantuml_wrapper.py",
        ]:
            _cand = _curr / candidate_sub
            if _cand.is_file():
                _wrapper = str(_cand)
                break
        if _wrapper or _curr.parent == _curr:
            break
        _curr = _curr.parent

if _wrapper and Path(_wrapper).is_file():
    plantuml = [sys.executable, str(_wrapper)]
    plantuml_output_format = 'svg_img'
elif shutil.which("plantuml"):
    plantuml = "plantuml"
    plantuml_output_format = 'svg_img'

source_suffix = '.rst'
exclude_patterns = ['_build']
html_theme = 'furo'
source_encoding = 'utf-8-sig'

# Mermaid.js version loaded in the browser.
# xychart-beta requires mermaid >= 10.3; 10.9.x is the last v10 line that
# still ships the UMD build (dist/mermaid.min.js) used by older
# sphinxcontrib-mermaid (0.9.x). Newer extensions (>=1.0) load the ESM build
# for the same version, so this pin works with both.
mermaid_version = '10.9.3'

# Custom static files (CSS & JS for modern aesthetics & interactive diagrams)
html_static_path = ['_static'] if os.path.isdir('_static') else []
html_css_files = ['custom.css'] if os.path.isfile(os.path.join('_static', 'custom.css')) else []
html_js_files = ['custom.js'] if os.path.isfile(os.path.join('_static', 'custom.js')) else []
