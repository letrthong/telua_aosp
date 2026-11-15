#!/usr/bin/env python3
# ==============================================================================
# inject_plantuml.py — Auto-enable PlantUML (.. uml:: / .. plantuml::) for
# existing / legacy Sphinx projects whose conf.py predates PlantUML support.
#
# Usage:
#   python inject_plantuml.py <docs_dir>            # patch <docs_dir>/conf.py
#   python inject_plantuml.py <docs_dir> --check    # only report status
#
# Build pipelines call this on the STAGING dir (_build/.staging), so source
# files of old projects stay untouched. 'telua docs upgrade' calls it on the
# real project dir to persist the config.
#
# Idempotent: a marker comment prevents double injection. User-defined
# settings are respected (only missing / broken values are filled in).
# ==============================================================================

import shutil
import sys
from pathlib import Path

MARKER = "# --- telua-plantuml-autoconfig ---"
SCRIPT_DIR = Path(__file__).resolve().parent
WRAPPER_SRC = SCRIPT_DIR / "plantuml_wrapper.py"

CSS = """/* Telua: PlantUML diagram styling (auto-injected) */
p.plantuml { display:flex; justify-content:center; align-items:center;
  background:#fff; padding:24px; border-radius:12px; border:1px solid #e2e8f0;
  box-shadow:0 4px 20px rgba(0,0,0,.05); margin:24px 0; overflow-x:auto; }
p.plantuml img, p.plantuml object { max-width:100%; height:auto; display:block; margin:0 auto; }
[data-theme="dark"] p.plantuml { background:#1e1e24; border-color:#2e2e38; }
"""

SNIPPET = '''

{marker}
# Auto-added by Telua: enables PlantUML (.. uml::) without Java/plantuml setup.
# Safe to keep: only fills in settings that are missing or not runnable.
def _telua_plantuml_setup(g):
    import os as _os, sys as _sys, shutil as _sh
    from pathlib import Path as _P
    try:
        import sphinxcontrib.plantuml  # noqa: F401
    except ImportError:
        return
    exts = g.setdefault("extensions", [])
    if "sphinxcontrib.plantuml" not in exts:
        exts.append("sphinxcontrib.plantuml")

    here = _P(__file__).resolve().parent
    cands = [_os.environ.get("PLANTUML_WRAPPER", ""),
             str(here / "plantuml_wrapper.py"),
             r"{fallback}"]
    wrapper = next((c for c in cands if c and _P(c).is_file()), None)

    cur = g.get("plantuml")
    first = cur[0] if isinstance(cur, (list, tuple)) and cur else (str(cur).split()[0] if cur else "")
    runnable = bool(first) and (_P(first).is_file() or _sh.which(first))
    if wrapper and not runnable:
        g["plantuml"] = [_sys.executable, wrapper]
    if g.get("plantuml_output_format") in (None, "svg"):
        g["plantuml_output_format"] = "svg_img"

    css_dir = here / "_telua_static"
    if (css_dir / "telua_plantuml.css").is_file():
        sp = list(g.get("html_static_path") or [])
        if "_telua_static" not in sp:
            sp.append("_telua_static")
        g["html_static_path"] = sp
        css = list(g.get("html_css_files") or [])
        if "telua_plantuml.css" not in css:
            css.append("telua_plantuml.css")
        g["html_css_files"] = css

_telua_plantuml_setup(globals())
del _telua_plantuml_setup
'''


def inject(docs_dir: Path, check_only: bool = False) -> int:
    conf = docs_dir / "conf.py"
    if not conf.is_file():
        print(f"[plantuml] No conf.py in {docs_dir} - skipped.")
        return 0

    text = conf.read_text(encoding="utf-8-sig")
    already = MARKER in text
    if check_only:
        print(f"[plantuml] {conf}: {'configured' if already else 'NOT configured'}")
        return 0 if already else 1

    # Always refresh helper files (wrapper + css) next to conf.py
    if WRAPPER_SRC.is_file():
        dst = docs_dir / "plantuml_wrapper.py"
        if dst.resolve() != WRAPPER_SRC.resolve():
            shutil.copy2(WRAPPER_SRC, dst)
    css_dir = docs_dir / "_telua_static"
    css_dir.mkdir(exist_ok=True)
    (css_dir / "telua_plantuml.css").write_text(CSS, encoding="utf-8")

    if already:
        print(f"[plantuml] {conf}: already configured.")
        return 0

    snippet = SNIPPET.replace("{marker}", MARKER).replace("{fallback}", str(WRAPPER_SRC))
    with conf.open("a", encoding="utf-8") as f:
        f.write(snippet)
    print(f"[plantuml] {conf}: PlantUML support injected.")
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_only = "--check" in sys.argv
    target = Path(args[0]) if args else Path.cwd()
    sys.exit(inject(target.resolve(), check_only))


if __name__ == "__main__":
    main()
