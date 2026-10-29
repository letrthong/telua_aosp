# -- Sphinx Configuration for Architecture & System Design Project --

project = 'System Architecture Documentation'
copyright = '2026, Architecture Team'
author = 'Architecture Team'

extensions = []

# Optional extensions with graceful fallback to prevent build failure if package is missing
for ext in ['sphinxcontrib.mermaid', 'sphinx_copybutton']:
    try:
        __import__(ext)
        extensions.append(ext)
    except ImportError:
        pass

import os

source_suffix = '.rst'
exclude_patterns = ['_build']
html_theme = 'furo'
source_encoding = 'utf-8-sig'

# Custom static files (CSS & JS for modern aesthetics & interactive diagrams)
html_static_path = ['_static'] if os.path.isdir('_static') else []
html_css_files = ['custom.css'] if os.path.isfile(os.path.join('_static', 'custom.css')) else []
html_js_files = ['custom.js'] if os.path.isfile(os.path.join('_static', 'custom.js')) else []
