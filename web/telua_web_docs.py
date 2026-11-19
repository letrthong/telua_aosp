#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ==============================================================================
#
# telua_web_docs.py — Sphinx Doc-as-Code helpers & RST <-> HTML converter engine
# Handles:
#   - Scanning .rst files in docs/ and sphinx/templates/
#   - Two-way conversion: rst_to_html and html_to_rst
#   - Sphinx build & live preview helpers

import base64
import os
import re
import shutil
import subprocess
import textwrap
import urllib.parse
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from docutils.core import publish_parts
except ImportError:  # pragma: no cover
    publish_parts = None

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:  # pragma: no cover
    BeautifulSoup = None


def scan_docs_files(root: Path, custom_dir: Optional[str] = None) -> Tuple[List[Dict], str]:
    """Scan root/docs, root/sphinx/templates, or a custom directory for .rst files.
    Returns (files_list, effective_dir_path).
    """
    results = []
    seen = set()
    effective_dir = ""

    if custom_dir and custom_dir.strip():
        raw_path = Path(custom_dir.strip())
        target_dir = raw_path if raw_path.is_absolute() else (root / raw_path).resolve()
        if target_dir.is_dir():
            effective_dir = target_dir.as_posix()
            for p in sorted(target_dir.rglob("*.rst")):
                if not p.is_file() or any(part in ("_build", ".staging", ".git") for part in p.parts):
                    continue
                try:
                    rel = p.relative_to(target_dir).as_posix()
                except ValueError:
                    rel = p.as_posix()
                if rel in seen:
                    continue
                seen.add(rel)

                title = _extract_rst_title(p)
                try:
                    stat = p.stat()
                    mtime = int(stat.st_mtime)
                    size = stat.st_size
                except OSError:
                    mtime = 0
                    size = 0

                results.append({
                    "name": rel,
                    "full_path": p.as_posix(),
                    "title": title or p.name,
                    "category": target_dir.name or "custom",
                    "size": size,
                    "mtime": mtime,
                })
            return results, effective_dir

    search_dirs = [
        root / "docs",
        root / "sphinx" / "templates",
        root / "sphinx",
    ]
    effective_dir = (root / "docs").as_posix() if (root / "docs").is_dir() else root.as_posix()

    for base in search_dirs:
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.rst")):
            if not p.is_file() or any(part in ("_build", ".staging", ".git") for part in p.parts):
                continue
            rel = p.relative_to(root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)

            title = _extract_rst_title(p)
            try:
                stat = p.stat()
                mtime = int(stat.st_mtime)
                size = stat.st_size
            except OSError:
                mtime = 0
                size = 0

            # Determine category / template
            parts = Path(rel).parts
            category = "docs"
            if len(parts) > 2 and parts[0] == "sphinx" and parts[1] == "templates":
                category = parts[2]  # e.g. architecture, basic, api, minimal
            elif parts[0] == "docs":
                category = "project"

            results.append({
                "name": rel,
                "full_path": p.as_posix(),
                "title": title or Path(rel).name,
                "category": category,
                "size": size,
                "mtime": mtime,
            })

    return results, effective_dir


def resolve_rst_target(name: str, root: Path, custom_dir: Optional[str] = None) -> Tuple[Path, str]:
    """Resolve a .rst file name either inside custom_dir or relative to root."""
    name = name.strip().replace("\\", "/")

    # 1. If name is already an absolute path that exists
    p_name = Path(name)
    if p_name.is_absolute() and p_name.is_file():
        return p_name.resolve(), p_name.resolve().as_posix()

    # 2. If custom_dir is provided
    if custom_dir and custom_dir.strip():
        raw_base = Path(custom_dir.strip())
        target_base = raw_base if raw_base.is_absolute() else (root / raw_base).resolve()

        # Deduplicate prefix if name already starts with custom_dir
        clean_custom = custom_dir.strip().replace("\\", "/").rstrip("/")
        if name.startswith(clean_custom + "/"):
            name = name[len(clean_custom) + 1:]
        elif target_base.as_posix() != "/" and name.startswith(target_base.as_posix() + "/"):
            name = name[len(target_base.as_posix()) + 1:]

        target = (target_base / name).resolve()

        # Guard: if target does not exist, but (root / name) exists as an actual file,
        # it means the user selected a root-relative file from a different directory
        if not target.is_file() and (root / name).is_file():
            return (root / name).resolve(), name

        return target, target.as_posix()

    # 3. No custom_dir:
    # If the file exists directly under root / name
    if (root / name).is_file():
        return (root / name).resolve(), name

    # If single filename without directory, check root / docs
    if "/" not in name:
        docs_dir = root / "docs"
        if docs_dir.is_dir() or not (root / name).is_file():
            target = (docs_dir / name).resolve()
            return target, f"docs/{name}"

    target = (root / name).resolve()
    return target, name


def detect_docs_project_dir(current_file: Optional[str] = None, custom_dir: Optional[str] = None, root: Optional[Path] = None) -> Path:
    """Detect the documentation project root directory from custom_dir, current_file, or project templates."""
    if root is None:
        root = Path(__file__).resolve().parent.parent

    # 1. Custom directory explicitly provided
    if custom_dir and custom_dir.strip():
        base = Path(custom_dir.strip())
        return base if base.is_absolute() else (root / base).resolve()

    # 2. Derive from active/current file path (e.g. sphinx/templates/basic/... or docs/...)
    if current_file and current_file.strip():
        clean_file = current_file.replace("\\", "/").strip()
        fpath = Path(clean_file)
        if not fpath.is_absolute():
            if (root / clean_file).is_file():
                fpath = (root / clean_file).resolve()
            else:
                for cand in [
                    root / "sphinx" / "templates" / "architecture" / clean_file,
                    root / "sphinx" / "templates" / "basic" / clean_file,
                    root / "docs" / clean_file,
                ]:
                    if cand.is_file():
                        fpath = cand.resolve()
                        break
                else:
                    fpath = (root / clean_file).resolve()
        cur = fpath if fpath.is_dir() else fpath.parent
        root_resolved = root.resolve()
        while cur and cur != cur.parent and cur != root_resolved:
            if (cur / "metadata.json").is_file() or (cur / "conf.py").is_file() or (cur / "index.rst").is_file():
                return cur
            cur = cur.parent

    # 3. Default fallback order
    if (root / "docs").is_dir():
        return (root / "docs").resolve()
    if (root / "sphinx" / "templates" / "architecture").is_dir():
        return (root / "sphinx" / "templates" / "architecture").resolve()
    if (root / "sphinx" / "templates" / "basic").is_dir():
        return (root / "sphinx" / "templates" / "basic").resolve()
    return root.resolve()


def _extract_rst_title(file_path: Path) -> Optional[str]:
    """Quickly extract top-level title from an .rst file without full parse."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.rstrip() for line in f.readlines()[:15]]
            for i in range(len(lines) - 1):
                cur = lines[i].strip()
                nxt = lines[i + 1].strip()
                if cur and nxt and len(nxt) >= len(cur):
                    # Check if next line is underline with =, -, ~, ^, #, *
                    if all(ch == nxt[0] for ch in nxt) and nxt[0] in "=~-^#*":
                        return cur
            for line in lines:
                if line.strip() and not line.startswith("..") and not line.startswith(":"):
                    return line.strip()
    except OSError:
        pass
    return None


PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
STANDARD_BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
TRANSLATE_TO_PLANTUML = str.maketrans(STANDARD_BASE64_ALPHABET, PLANTUML_ALPHABET)


def encode_plantuml(text: str) -> str:
    """Encode PlantUML text into official PlantUML URL format."""
    clean_text = text.strip()
    if not clean_text:
        return ""
    if not clean_text.startswith("@startuml"):
        clean_text = f"@startuml\n{clean_text}\n@enduml"
    utf8_bytes = clean_text.encode("utf-8")
    compressed = zlib.compress(utf8_bytes, level=9)[2:-4]
    b64 = base64.b64encode(compressed).decode("ascii").rstrip("=")
    return b64.translate(TRANSLATE_TO_PLANTUML)


def get_plantuml_url(text: str) -> str:
    """Get public PlantUML server SVG URL for a diagram text."""
    encoded = encode_plantuml(text)
    if not encoded:
        return ""
    return f"https://www.plantuml.com/plantuml/svg/{encoded}"


def _protect_rst_directives(rst_text: str) -> str:
    """Transform Sphinx-specific directives (like .. mermaid::, .. uml::, .. plantuml::)
    into raw HTML blocks so docutils preserves them without throwing parse errors.
    """
    mermaid_pattern = re.compile(r'^\.\.\s+mermaid::\s*\n((?:[ \t]+.*\n|\n)*)', re.MULTILINE)
    def repl_mermaid(match):
        code = textwrap.dedent(match.group(1)).strip()
        escaped_code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        html_block = f'<div class="mermaid-block" data-mermaid="{escaped_code}"><div class="mermaid-label">📊 Mermaid Architecture Diagram</div><pre class="mermaid">{escaped_code}</pre></div>'
        indented = "\n".join("   " + line for line in html_block.splitlines())
        raw_block = [
            "",
            ".. raw:: html",
            "",
            indented,
            "",
        ]
        return "\n".join(raw_block) + "\n"
    rst_text = mermaid_pattern.sub(repl_mermaid, rst_text)

    plantuml_pattern = re.compile(r'^\.\.\s+(?:plantuml|uml)::\s*\n((?:[ \t]+.*\n|\n)*)', re.MULTILINE)
    def repl_plantuml(match):
        code = textwrap.dedent(match.group(1)).strip()
        escaped_code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        uml_url = f"/api/docs/plantuml/svg?code={urllib.parse.quote(code)}" if code else ""
        html_block = (
            f'<div class="plantuml-block" data-plantuml="{escaped_code}">'
            f'<div class="plantuml-header" contenteditable="false">'
            f'<div class="plantuml-title-wrap">'
            f'<span class="plantuml-label">📐 PlantUML Architecture Diagram</span>'
            f'<span class="plantuml-chip">.. uml::</span>'
            f'</div>'
            f'<div class="plantuml-actions">'
            f'<button type="button" class="plantuml-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>'
            f'<button type="button" class="plantuml-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>'
            f'<button type="button" class="plantuml-btn btn-copy-uml" title="Copy PlantUML Syntax">📋 Copy</button>'
            f'<button type="button" class="plantuml-btn btn-del-uml danger" title="Delete Diagram">🗑</button>'
            f'</div>'
            f'</div>'
            f'<div class="plantuml-diagram-wrap" contenteditable="false">'
            f'<img class="plantuml-svg-img" src="{uml_url}" alt="PlantUML Diagram" loading="lazy" />'
            f'</div>'
            f'<textarea class="plantuml-code-input" spellcheck="false" style="display:none;" placeholder="Type PlantUML syntax here…">{escaped_code}</textarea>'
            f'</div>'
        )
        indented = "\n".join("   " + line for line in html_block.splitlines())
        raw_block = [
            "",
            ".. raw:: html",
            "",
            indented,
            "",
        ]
        return "\n".join(raw_block) + "\n"
    rst_text = plantuml_pattern.sub(repl_plantuml, rst_text)
    return rst_text


def rst_to_html(rst_text: str) -> str:
    """Convert reStructuredText (RST) to HTML using docutils."""
    if not rst_text or not rst_text.strip():
        return "<p></p>"
    if publish_parts is None:
        return f"<pre>{rst_text}</pre>"

    try:
        protected_text = _protect_rst_directives(rst_text)
        settings = {
            "report_level": 5,      # suppress warnings/errors in output HTML
            "halt_level": 6,
            "raw_enabled": True,
            "file_insertion_enabled": False,
        }
        parts = publish_parts(source=protected_text, writer_name="html5", settings_overrides=settings)
        body = parts.get("html_body", "").strip()
        # Remove outermost <main ...> and </main> if present to let Quill edit smoothly
        body = re.sub(r"^<main[^>]*>\s*", "", body, flags=re.IGNORECASE)
        body = re.sub(r"\s*</main>$", "", body, flags=re.IGNORECASE)
        return body or "<p></p>"
    except Exception as exc:
        return f'<div class="admonition warning"><p class="admonition-title">RST Parse Warning</p><p>{exc}</p></div><pre>{rst_text}</pre>'


def _inline_to_rst(node) -> str:
    """Recursively convert inline HTML nodes (bold, italic, code, link) to RST markup."""
    if isinstance(node, NavigableString):
        return str(node)

    if not isinstance(node, Tag):
        return ""

    tag = node.name.lower()
    inner = "".join(_inline_to_rst(child) for child in node.children)

    if tag in ("strong", "b"):
        inner = inner.strip()
        return f" **{inner}** " if inner else ""
    elif tag in ("em", "i"):
        inner = inner.strip()
        return f" *{inner}* " if inner else ""
    elif tag == "code":
        inner = inner.strip()
        return f" ``{inner}`` " if inner else ""
    elif tag == "a":
        href = node.get("href", "").strip()
        inner = inner.strip()
        if href and inner:
            return f" `{inner} <{href}>`_ "
        return inner
    elif tag == "br":
        return "\n"
    elif tag == "span":
        return inner
    return inner


def _clean_rst_spacing(text: str) -> str:
    """Clean inline spacing around RST bold, code, links, and punctuation."""
    if not text:
        return ""
    # Collapse multiple tabs/spaces
    text = re.sub(r"[ \t]+", " ", text)
    # Remove space before punctuation: , . : ; ? ! ) ]
    text = re.sub(r"\s+([,.:;?!)\]])", r"\1", text)
    # Remove space after opening brackets: ( [
    text = re.sub(r"([(\[])\s+", r"\1", text)
    # Fix link syntax: `text <url>` _ -> `text <url>`_
    text = re.sub(r"`\s+_", "`_", text)
    return text.strip()


def _convert_table_to_rst(table_elem, caption_txt: str, rst_lines: list):
    caption_txt = _clean_rst_spacing(caption_txt)
    if caption_txt:
        rst_lines.append(f".. list-table:: {caption_txt}")
    else:
        rst_lines.append(".. list-table::")

    cols = table_elem.find_all("col")
    widths = []
    for col in cols:
        style = col.get("style", "")
        m = re.search(r"width:\s*(\d+(?:\.\d+)?)%", style)
        if m:
            widths.append(str(int(round(float(m.group(1))))))
    if widths:
        rst_lines.append(f"   :widths: {' '.join(widths)}")

    rst_lines.append("   :header-rows: 1")
    rst_lines.append("")
    for row in table_elem.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        for c_idx, cell in enumerate(cells):
            cell_txt = "".join(_inline_to_rst(c) for c in cell.children)
            cell_txt = _clean_rst_spacing(cell_txt)
            if c_idx == 0:
                rst_lines.append(f"   * - {cell_txt}")
            else:
                rst_lines.append(f"     - {cell_txt}")
    rst_lines.append("")


def html_to_rst(html_text: str, file_name: Optional[str] = None) -> str:
    """Convert HTML from Quill.js back to clean, valid reStructuredText (RST)
    matching the exact Sphinx architecture template conventions."""
    if not html_text or not html_text.strip():
        return ""

    if BeautifulSoup is None:
        # Fallback if bs4 is missing
        clean = re.sub(r"<[^>]+>", "", html_text)
        return clean.strip()

    soup = BeautifulSoup(html_text, "html.parser")
    rst_lines = []

    # Detect if target is a section file (e.g. chapterX_sectionY.rst or title starts with X.Y)
    is_section = False
    if file_name:
        fn_clean = file_name.replace("\\", "/").lower()
        base_name = fn_clean.split("/")[-1]
        # index.rst and chapterX.rst are root/chapter files, never section files
        if base_name in ("index.rst", "conf.py") or re.match(r"^chapter\d+\.rst$", base_name):
            is_section = False
        elif "section" in base_name or re.search(r"chapter\d+/", fn_clean):
            is_section = True
    if not is_section:
        first_h = soup.find(["h1", "h2", "h3"])
        if first_h and re.match(r"^\d+\.\d+", first_h.get_text().strip()):
            is_section = True

    def add_heading(text: str, level: int):
        text = _clean_rst_spacing(text)
        if not text:
            return
        if is_section:
            # Section file (e.g. chapterX_sectionY.rst):
            # Level 1 = section title (hyphen underline, 90 chars in architecture template)
            # Level 2 = subsection (tilde underline, matching text length)
            # Level 3 = sub-subsection (caret underline)
            if level == 1:
                underline = "-" * max(len(text), 90)
            elif level == 2:
                underline = "~" * len(text)
            elif level == 3:
                underline = "^" * len(text)
            else:
                underline = '"' * len(text)
        else:
            # Root or chapter file (e.g. index.rst, chapter1.rst):
            if level == 1:
                underline = "=" * max(len(text), 4)
            elif level == 2:
                underline = "-" * max(len(text), 4)
            elif level == 3:
                underline = "~" * len(text)
            else:
                underline = "^" * len(text)

        rst_lines.append(text)
        rst_lines.append(underline)
        rst_lines.append("")

    def add_code_block(code_text: str, lang: str = "text"):
        rst_lines.append(f".. code-block:: {lang}")
        rst_lines.append("")
        for line in code_text.splitlines():
            if line.strip():
                rst_lines.append(f"    {line}")
            else:
                rst_lines.append("")
        rst_lines.append("")

    def add_admonition(kind: str, title: str, content: str):
        rst_lines.append(f".. {kind}::")
        indent = "   " if is_section else "    "
        if title and title.lower() != kind.lower():
            rst_lines.append(f"{indent}:title: {title}")
        for line in content.splitlines():
            line_str = _clean_rst_spacing(line)
            if line_str:
                rst_lines.append(f"{indent}{line_str}")
            else:
                rst_lines.append("")
        rst_lines.append("")

    def process_element(element):
        if isinstance(element, NavigableString):
            txt = _clean_rst_spacing(str(element))
            if txt:
                rst_lines.append(txt)
                rst_lines.append("")
            return

        if not isinstance(element, Tag):
            return

        tag = element.name.lower()
        classes = element.get("class", [])

        # Unpack nested section or container div unless it's a special block
        if tag == "section" or (tag == "div" and "admonition" not in classes and "mermaid-block" not in classes and "plantuml-block" not in classes and "doc-table-block" not in classes):
            for child in element.children:
                process_element(child)
            return

        if tag == "h1":
            text = "".join(_inline_to_rst(c) for c in element.children)
            add_heading(text, 1)
        elif tag == "h2":
            text = "".join(_inline_to_rst(c) for c in element.children)
            add_heading(text, 2)
        elif tag == "h3":
            text = "".join(_inline_to_rst(c) for c in element.children)
            add_heading(text, 3)
        elif tag in ("h4", "h5", "h6"):
            text = "".join(_inline_to_rst(c) for c in element.children)
            add_heading(text, 4)
        elif tag == "pre":
            if "mermaid" in classes:
                code = element.get_text().strip()
                rst_lines.append(".. mermaid::")
                rst_lines.append("")
                for line in code.splitlines():
                    if line.strip():
                        rst_lines.append(f"   {line}")
                    else:
                        rst_lines.append("")
                rst_lines.append("")
            elif "plantuml" in classes or "uml" in classes:
                code = element.get_text().strip()
                rst_lines.append(".. uml::")
                rst_lines.append("")
                for line in code.splitlines():
                    if line.strip():
                        rst_lines.append(f"   {line}")
                    else:
                        rst_lines.append("")
                rst_lines.append("")
            else:
                code = element.get_text()
                add_code_block(code)
        elif "mermaid-block" in classes:
            code = element.get("data-mermaid", "").strip()
            if not code:
                elem = element.find("textarea") or element.find("pre")
                code = elem.get_text().strip() if elem else element.get_text().strip()
            rst_lines.append(".. mermaid::")
            rst_lines.append("")
            for line in code.splitlines():
                if line.strip():
                    rst_lines.append(f"   {line}")
                else:
                    rst_lines.append("")
            rst_lines.append("")
        elif "plantuml-block" in classes:
            code = element.get("data-plantuml", "").strip()
            if not code:
                elem = element.find("textarea") or element.find("pre")
                code = elem.get_text().strip() if elem else element.get_text().strip()
            rst_lines.append(".. uml::")
            rst_lines.append("")
            for line in code.splitlines():
                if line.strip():
                    rst_lines.append(f"   {line}")
                else:
                    rst_lines.append("")
            rst_lines.append("")
        elif "doc-table-block" in classes:
            table_elem = element.find("table")
            if not table_elem:
                return
            caption_input = element.find("input", class_="doc-table-caption-input")
            caption_txt = caption_input.get("value", "").strip() if caption_input else ""
            if not caption_txt:
                caption_node = table_elem.find("caption")
                if caption_node:
                    caption_txt = "".join(_inline_to_rst(c) for c in caption_node.children).strip()
            _convert_table_to_rst(table_elem, caption_txt, rst_lines)
        elif tag == "table":
            caption_node = element.find("caption")
            caption_txt = "".join(_inline_to_rst(c) for c in caption_node.children).strip() if caption_node else ""
            _convert_table_to_rst(element, caption_txt, rst_lines)
        elif tag == "img":
            src = element.get("src", "").strip()
            alt = element.get("alt", "").strip()
            if src:
                rst_lines.append(f".. image:: {src}")
                if alt:
                    rst_lines.append(f"   :alt: {alt}")
                rst_lines.append("")
        elif tag in ("div", "aside") and "admonition" in classes:
            kind = "note"
            for k in ("note", "warning", "tip", "important", "caution", "danger", "attention"):
                if k in classes:
                    kind = k
                    break
            title_node = element.find(class_="admonition-title")
            title = title_node.get_text().strip() if title_node else ""
            if title_node:
                title_node.decompose()
            body_text = "\n".join(
                "".join(_inline_to_rst(c) for c in p.children).strip()
                for p in element.find_all(["p", "div"])
            ) or element.get_text().strip()
            add_admonition(kind, title, body_text)
        elif tag == "blockquote":
            text = "\n".join("   " + line for line in element.get_text().splitlines())
            rst_lines.append(text)
            rst_lines.append("")
        elif tag == "ul":
            bullet_prefix = "- " if is_section else "* "
            for li in element.find_all("li", recursive=False):
                item_txt = "".join(_inline_to_rst(c) for c in li.children)
                item_txt = _clean_rst_spacing(item_txt)
                if item_txt:
                    rst_lines.append(f"{bullet_prefix}{item_txt}")
            rst_lines.append("")
        elif tag == "ol":
            for idx, li in enumerate(element.find_all("li", recursive=False)):
                item_txt = "".join(_inline_to_rst(c) for c in li.children)
                item_txt = _clean_rst_spacing(item_txt)
                if item_txt:
                    num_prefix = f"{idx + 1}. " if is_section else "#. "
                    rst_lines.append(f"{num_prefix}{item_txt}")
            rst_lines.append("")
        elif tag == "p":
            text = "".join(_inline_to_rst(c) for c in element.children)
            text = _clean_rst_spacing(text)
            if text:
                rst_lines.append(text)
                rst_lines.append("")
        else:
            text = "".join(_inline_to_rst(c) for c in element.children)
            text = _clean_rst_spacing(text)
            if text:
                rst_lines.append(text)
                rst_lines.append("")

    # Traverse top-level blocks recursively
    for element in soup.children:
        process_element(element)

    result = "\n".join(rst_lines)
    # Collapse 3+ consecutive newlines to 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip() + "\n"


# ==============================================================================
# Docs REST API & Sphinx Preview Server (Flask Blueprint)
# ==============================================================================
from flask import Blueprint, Response, abort, jsonify, request

docs_bp = Blueprint("docs", __name__)


def get_root() -> Path:
    """Dynamically get ROOT from telua_web if loaded, else fallback to toolkit root."""
    import sys
    if "telua_web" in sys.modules:
        tw = sys.modules["telua_web"]
        if hasattr(tw, "ROOT"):
            return tw.ROOT
    return Path(__file__).resolve().parent.parent


def open_browser(url: str):
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass


@docs_bp.get("/api/docs/files")
def api_docs_files():
    """List all discoverable .rst documentation files."""
    root = get_root()
    custom_dir = request.args.get("dir", "").strip()
    files, effective_dir = scan_docs_files(root, custom_dir=custom_dir or None)
    return jsonify({"ok": True, "files": files, "dir": effective_dir})


@docs_bp.get("/api/docs/file")
def api_docs_file_read():
    """Read a specific .rst file, returning both raw RST and converted HTML."""
    root = get_root()
    name = request.args.get("name", "").strip()
    custom_dir = request.args.get("dir", "").strip()
    if not name or ".." in name or not name.endswith(".rst"):
        abort(400, description="Invalid .rst file name.")
    target, full_name = resolve_rst_target(name, root, custom_dir=custom_dir or None)
    if not target.is_file():
        abort(404, description=f"File '{name}' not found.")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        stat = target.stat()
        mtime = int(stat.st_mtime)
    except OSError as exc:
        abort(500, description=f"Failed to read file: {exc}")

    return jsonify({
        "ok": True,
        "name": name,
        "full_path": full_name,
        "rst": content,
        "html": rst_to_html(content),
        "mtime": mtime,
        "readonly": not os.access(str(target), os.W_OK),
    })


@docs_bp.post("/api/docs/file")
def api_docs_file_write():
    """Write/save a .rst file from either raw RST or Quill.js HTML."""
    root = get_root()
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    custom_dir = payload.get("dir", "").strip()
    content = payload.get("content", "")
    fmt = payload.get("format", "rst").lower()

    if not name or ".." in name or not name.endswith(".rst"):
        abort(400, description="Invalid .rst file name.")
    target, full_name = resolve_rst_target(name, root, custom_dir=custom_dir or None)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        abort(500, description=f"Failed to create directory: {exc}")

    # If incoming format is HTML, convert to RST first
    if fmt == "html":
        rst_content = html_to_rst(content, file_name=name)
    else:
        rst_content = content

    # Create backup .bak if target exists
    if target.is_file():
        try:
            bak = target.with_suffix(".rst.bak")
            shutil.copyfile(str(target), str(bak))
        except OSError:
            pass

    try:
        target.write_text(rst_content, encoding="utf-8")
        stat = target.stat()
    except OSError as exc:
        abort(500, description=f"Failed to write file: {exc}")

    return jsonify({
        "ok": True,
        "name": name,
        "full_path": full_name,
        "rst": rst_content,
        "html": rst_to_html(rst_content),
        "mtime": int(stat.st_mtime),
    })


@docs_bp.post("/api/docs/convert")
def api_docs_convert():
    """Convert on-the-fly between RST and HTML."""
    payload = request.get_json(silent=True) or {}
    content = payload.get("content", "")
    direction = payload.get("direction", "rst2html").lower()

    if direction in ("rst2html", "rst_to_html"):
        return jsonify({"ok": True, "html": rst_to_html(content)})
    elif direction in ("html2rst", "html_to_rst"):
        file_name = payload.get("name", "")
        return jsonify({"ok": True, "rst": html_to_rst(content, file_name=file_name)})
    abort(400, description="Unknown conversion direction. Use 'rst2html' or 'html2rst'.")


_PLANTUML_CACHE = {}


@docs_bp.route("/api/docs/plantuml/svg", methods=["GET", "POST"])
def api_docs_plantuml_svg():
    """Render PlantUML code to SVG using local plantuml, jar, or server proxy with cache."""
    import urllib.request

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        code = payload.get("code", "")
    else:
        code = request.args.get("code", "")

    code = (code or "").strip()
    if not code:
        return Response('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="30"></svg>', mimetype="image/svg+xml")

    if code in _PLANTUML_CACHE:
        return Response(_PLANTUML_CACHE[code], mimetype="image/svg+xml")

    # 1. Local plantuml or jar if available
    plantuml_bin = shutil.which("plantuml")
    if plantuml_bin:
        try:
            p = subprocess.run([plantuml_bin, "-tsvg", "-pipe"], input=code.encode("utf-8"), capture_output=True, timeout=10)
            if p.returncode == 0 and p.stdout and b"<svg" in p.stdout:
                svg_text = p.stdout.decode("utf-8", errors="replace")
                _PLANTUML_CACHE[code] = svg_text
                return Response(svg_text, mimetype="image/svg+xml")
        except Exception:
            pass

    # 2. Online plantuml server via backend proxy (avoids client-side hotlink/referer blocking)
    try:
        url = get_plantuml_url(code)
        if url:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/svg+xml,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                svg_data = resp.read().decode("utf-8", errors="replace")
                if "<svg" in svg_data and "HUFFMAN" not in svg_data and "bad URL" not in svg_data:
                    _PLANTUML_CACHE[code] = svg_data
                    return Response(svg_data, mimetype="image/svg+xml")
    except Exception:
        pass

    # 3. Fallback SVG: generate clean vector diagram
    lines = [l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith("@")]
    h = max(120, 60 + len(lines) * 24)
    escaped_lines = "\n".join(
        f'<text x="24" y="{45 + idx * 24}" fill="#e2e8f0" font-family="monospace" font-size="12">{l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</text>'
        for idx, l in enumerate(lines[:20])
    )
    fallback_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="{h}">'
        f'<rect width="100%" height="100%" fill="#1e1e2e" stroke="#a855f7" stroke-width="2" rx="8"/>'
        f'<rect x="0" y="0" width="100%" height="28" fill="#2d1b4e" rx="8"/>'
        f'<text x="14" y="19" fill="#c084fc" font-family="sans-serif" font-size="12" font-weight="bold">📐 PlantUML Architecture Diagram</text>'
        f'{escaped_lines}'
        f'</svg>'
    )
    return Response(fallback_svg, mimetype="image/svg+xml")


@docs_bp.route("/api/docs/plantuml/url", methods=["GET", "POST"])
def api_docs_plantuml_url():
    """Generate PlantUML SVG URL from code."""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        code = payload.get("code", "")
    else:
        code = request.args.get("code", "")
    if not code:
        return jsonify({"ok": False, "error": "No PlantUML code provided"}), 400
    url = get_plantuml_url(code)
    return jsonify({"ok": True, "url": url})


_DOCS_SERVER_PROC = None
_DOCS_SERVER_DIR = None
_DOCS_SERVER_PORT = None


def _build_sphinx_docs_py(target_dir: Path):
    """Compile Sphinx documentation into target_dir/_build/html with staging, merge, and fallbacks."""
    import sys
    root = get_root()
    out_html = target_dir / "_build" / "html"
    staging_dir = target_dir / "_build" / ".staging"
    merge_script = root / "sphinx" / "scripts" / "merge_docs.py"

    if staging_dir.is_dir():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for item in target_dir.iterdir():
        if item.name not in ("_build", ".git"):
            dest = staging_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # Fallback conf.py if missing in staging
    if not (staging_dir / "conf.py").is_file():
        for candidate in [
            root / "sphinx" / "templates" / "basic" / "conf.py",
            root / "sphinx" / "templates" / "architecture" / "conf.py",
            root / "sphinx" / "conf.py",
        ]:
            if candidate.is_file():
                shutil.copy2(candidate, staging_dir / "conf.py")
                break

    # Fallback _static if missing in staging
    if not (staging_dir / "_static").is_dir():
        for candidate in [
            root / "sphinx" / "templates" / "basic" / "_static",
            root / "sphinx" / "templates" / "architecture" / "_static",
        ]:
            if candidate.is_dir():
                shutil.copytree(candidate, staging_dir / "_static", dirs_exist_ok=True)
                break

    # Fallback asset directory if missing in staging
    if not (staging_dir / "asset").is_dir():
        for candidate in [
            root / "sphinx" / "templates" / "basic" / "asset",
            root / "sphinx" / "templates" / "architecture" / "asset",
        ]:
            if candidate.is_dir():
                shutil.copytree(candidate, staging_dir / "asset", dirs_exist_ok=True)
                break

    # Ensure PlantUML support in staging (auto-upgrades legacy conf.py; source untouched)
    inject_script = root / "sphinx" / "scripts" / "inject_plantuml.py"
    if inject_script.is_file():
        subprocess.run([sys.executable, str(inject_script), str(staging_dir)], capture_output=True, timeout=30)

    if (staging_dir / "metadata.json").is_file() and merge_script.is_file():
        subprocess.run([sys.executable, str(merge_script), str(staging_dir)], capture_output=True, timeout=30)

    cmd = [sys.executable, "-m", "sphinx", "-E", "-a", "-b", "html", str(staging_dir), str(out_html)]
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=60)
    return (proc.returncode == 0, proc.returncode, proc.stdout, proc.stderr, target_dir, out_html)


@docs_bp.post("/api/docs/build")
def api_docs_build():
    """Trigger Sphinx build for target docs directory."""
    import sys
    root = get_root()
    payload = request.get_json(silent=True) or {}
    custom_dir = payload.get("dir", "").strip()
    current_file = payload.get("current_file", "").strip()

    target_dir = detect_docs_project_dir(current_file=current_file, custom_dir=custom_dir, root=root)

    if not target_dir.is_dir():
        return jsonify({"ok": False, "error": f"Documentation directory '{target_dir}' does not exist"}), 404

    # On Linux/macOS with build_apk.sh, delegate to bash build_apk.sh docs build <target_dir>
    if (root / "build_apk.sh").is_file() and not sys.platform.startswith("win"):
        cmd = ["bash", "build_apk.sh", "docs", "build", str(target_dir)]
        try:
            proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=60)
            return jsonify({
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "target_dir": str(target_dir),
                "html_dir": str(target_dir / "_build" / "html"),
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    # Cross-platform / Windows fallback
    try:
        ok, ret, stdout, stderr, tdir, ohtml = _build_sphinx_docs_py(target_dir)
        return jsonify({
            "ok": ok,
            "exit_code": ret,
            "stdout": stdout,
            "stderr": stderr,
            "target_dir": str(tdir),
            "html_dir": str(ohtml),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@docs_bp.post("/api/docs/clean")
def api_docs_clean():
    """Remove _build directory and cached doctrees for target docs project."""
    root = get_root()
    payload = request.get_json(silent=True) or {}
    custom_dir = payload.get("dir", "").strip()
    current_file = payload.get("current_file", "").strip()

    target_dir = detect_docs_project_dir(current_file=current_file, custom_dir=custom_dir, root=root)
    if not target_dir.is_dir():
        return jsonify({"ok": False, "error": f"Documentation directory '{target_dir}' does not exist"}), 404

    build_dir = target_dir / "_build"
    cleaned = False
    if build_dir.is_dir():
        try:
            shutil.rmtree(build_dir, ignore_errors=True)
            cleaned = True
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Failed to clean _build: {exc}"}), 500

    return jsonify({
        "ok": True,
        "target_dir": str(target_dir),
        "cleaned_dir": str(build_dir),
        "was_present": cleaned,
    })


def _kill_docs_server(target_dir: Optional[Path] = None, port: int = 8789):
    """Ensure any running docs preview server is terminated before restart."""
    import sys
    global _DOCS_SERVER_PROC
    import telua_web
    proc = _DOCS_SERVER_PROC or getattr(telua_web, "_DOCS_SERVER_PROC", None)
    if proc is not None:
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=2)
        except Exception:
            pass
        _DOCS_SERVER_PROC = None
        telua_web._DOCS_SERVER_PROC = None

    if target_dir is not None:
        pid_file = target_dir / ".telua_docs.pid"
        if pid_file.is_file():
            try:
                raw_pid = pid_file.read_text(encoding="utf-8").strip()
                pid = int(raw_pid)
                if pid > 0 and pid != os.getpid():
                    if sys.platform.startswith("win"):
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    else:
                        os.kill(pid, 9)
            except Exception:
                pass
            try:
                pid_file.unlink(missing_ok=True)
            except Exception:
                pass

    if sys.platform.startswith("win"):
        try:
            out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, errors="ignore")
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = int(parts[-1])
                    if pid > 0 and pid != os.getpid():
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        except Exception:
            pass
    else:
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
        except Exception:
            pass


@docs_bp.post("/api/docs/start")
def api_docs_start():
    """Launch Sphinx HTTP preview server (telua docs start) and open in browser."""
    import sys
    import time
    global _DOCS_SERVER_PROC, _DOCS_SERVER_DIR, _DOCS_SERVER_PORT
    import telua_web
    root = get_root()
    payload = request.get_json(silent=True) or {}
    custom_dir = payload.get("dir", "").strip()
    current_file = payload.get("current_file", "").strip()
    port = int(payload.get("port", 8789))
    clean_requested = bool(payload.get("clean", False))

    target_dir = detect_docs_project_dir(current_file=current_file, custom_dir=custom_dir, root=root)
    if not target_dir.is_dir():
        return jsonify({"ok": False, "error": f"Documentation directory '{target_dir}' does not exist"}), 404
    html_dir = target_dir / "_build" / "html"

    # If clean requested, wipe _build completely
    if clean_requested:
        build_dir = target_dir / "_build"
        if build_dir.is_dir():
            shutil.rmtree(build_dir, ignore_errors=True)

    # Always restart: terminate running server process or port occupier
    _kill_docs_server(target_dir=target_dir, port=port)

    # Always re-compile docs to ensure http://localhost:8789 serves 100% fresh content
    if (root / "build_apk.sh").is_file() and not sys.platform.startswith("win"):
        try:
            subprocess.run(["bash", "build_apk.sh", "docs", "build", str(target_dir)], cwd=str(root), capture_output=True, timeout=60)
        except Exception:
            pass
    else:
        try:
            _build_sphinx_docs_py(target_dir)
        except Exception:
            pass

    if not html_dir.is_dir():
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / "index.html").write_text("<h1>Sphinx Docs Preview</h1><p>Ready to build.</p>", encoding="utf-8")

    url = f"http://localhost:{port}"

    try:
        server_script = (
            "import http.server, sys, os, mimetypes\n"
            "mimetypes.add_type('image/svg+xml', '.svg')\n"
            "port = int(sys.argv[1])\n"
            "directory = os.path.abspath(sys.argv[2])\n"
            "class NoCacheHandler(http.server.SimpleHTTPRequestHandler):\n"
            "    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.svg': 'image/svg+xml'}\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        super().__init__(*args, directory=directory, **kwargs)\n"
            "    def end_headers(self):\n"
            "        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0')\n"
            "        self.send_header('Pragma', 'no-cache')\n"
            "        self.send_header('Expires', '0')\n"
            "        super().end_headers()\n"
            "    def send_head(self):\n"
            "        if 'If-Modified-Since' in self.headers:\n"
            "            del self.headers['If-Modified-Since']\n"
            "        if 'If-None-Match' in self.headers:\n"
            "            del self.headers['If-None-Match']\n"
            "        return super().send_head()\n"
            "server = http.server.ThreadingHTTPServer(('', port), NoCacheHandler)\n"
            "server.serve_forever()\n"
        )
        _DOCS_SERVER_PROC = subprocess.Popen(
            [sys.executable, "-c", server_script, str(port), str(html_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        telua_web._DOCS_SERVER_PROC = _DOCS_SERVER_PROC
        _DOCS_SERVER_DIR = str(html_dir)
        _DOCS_SERVER_PORT = port
    except Exception as exc:
        abort(500, description=f"Failed to start docs server: {exc}")

    cache_bust_url = f"{url}/?_t={int(time.time())}"
    open_browser(cache_bust_url)

    return jsonify({
        "ok": True,
        "url": url,
        "cache_bust_url": cache_bust_url,
        "port": port,
        "pid": _DOCS_SERVER_PROC.pid if _DOCS_SERVER_PROC else None,
        "target_dir": str(target_dir),
        "html_dir": str(html_dir),
    })
