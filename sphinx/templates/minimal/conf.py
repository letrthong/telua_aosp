# -- Sphinx Configuration for Minimal Project --

project = 'Project Documentation'
copyright = '2026, Documentation Team'
author = 'Documentation Team'

extensions = []

for ext in ['sphinxcontrib.mermaid', 'sphinxcontrib.plantuml', 'sphinx_copybutton']:
    try:
        __import__(ext)
        extensions.append(ext)
    except ImportError:
        pass

import os
import sys
from pathlib import Path

# PlantUML CLI Wrapper: local binary, jar or online SVG fallback
_candidate_wrappers = [
    Path(__file__).resolve().parent / "plantuml_wrapper.py",
    Path(__file__).resolve().parent.parent.parent / "scripts" / "plantuml_wrapper.py",
]
for _cw in _candidate_wrappers:
    if _cw.is_file():
        plantuml = [sys.executable, str(_cw)]
        plantuml_output_format = 'svg'
        break

source_suffix = '.rst'
exclude_patterns = ['_build']
html_theme = 'furo'
source_encoding = 'utf-8-sig'

# Custom static files (CSS & JS for modern aesthetics & interactive diagrams)
html_static_path = ['_static'] if os.path.isdir('_static') else []
html_css_files = ['custom.css'] if os.path.isfile(os.path.join('_static', 'custom.css')) else []
html_js_files = ['custom.js'] if os.path.isfile(os.path.join('_static', 'custom.js')) else []
