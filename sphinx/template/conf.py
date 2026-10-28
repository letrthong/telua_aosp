# -- Sphinx Configuration for Sample Project --

project = 'Home'
copyright = '2026, Example Author'
author = 'Example Author'

extensions = []

# Optional extensions with graceful fallback to prevent build failure if package is missing
for ext in ['sphinxcontrib.mermaid', 'sphinx_copybutton']:
    try:
        __import__(ext)
        extensions.append(ext)
    except ImportError:
        pass

source_suffix = '.rst'
exclude_patterns = ['_build']
html_theme = 'furo'
html_static_path = []
source_encoding = 'utf-8-sig'


