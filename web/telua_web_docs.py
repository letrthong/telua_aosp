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

import os
import re
import shutil
import subprocess
import textwrap
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
    name = name.strip()
    if custom_dir and custom_dir.strip():
        base = Path(custom_dir.strip())
        target_base = base if base.is_absolute() else (root / base).resolve()
        target = (target_base / name).resolve()
        return target, target.as_posix()
    if "/" not in name and "\\" not in name:
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
        fpath = Path(clean_file) if Path(clean_file).is_absolute() else (root / clean_file).resolve()
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


def encode_plantuml(text: str) -> str:
    """Encode PlantUML text into PlantUML standard deflate format (~1...)."""
    clean_text = text.strip()
    if not clean_text:
        return ""
    if not clean_text.startswith("@startuml"):
        clean_text = f"@startuml\n{clean_text}\n@enduml"
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(clean_text.encode("utf-8")) + compressor.flush()
    alphabet = PLANTUML_ALPHABET
    r = []
    i = 0
    n = len(compressed)
    while i < n:
        b1 = compressed[i]
        b2 = compressed[i + 1] if i + 1 < n else 0
        b3 = compressed[i + 2] if i + 2 < n else 0
        r.append(alphabet[(b1 >> 2) & 0x3F])
        r.append(alphabet[(((b1 & 0x3) << 4) | (b2 >> 4)) & 0x3F])
        if i + 1 < n:
            r.append(alphabet[(((b2 & 0xF) << 2) | (b3 >> 6)) & 0x3F])
        if i + 2 < n:
            r.append(alphabet[b3 & 0x3F])
        i += 3
    return "~1" + "".join(r)


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
        uml_url = get_plantuml_url(code) if code else ""
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


def _convert_table_to_rst(table_elem, caption_txt: str, rst_lines: list):
    caption_txt = re.sub(r"\s+", " ", caption_txt).strip()
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
            cell_txt = "".join(_inline_to_rst(c) for c in cell.children).strip()
            cell_txt = re.sub(r"[ \t]+", " ", cell_txt)
            if c_idx == 0:
                rst_lines.append(f"   * - {cell_txt}")
            else:
                rst_lines.append(f"     - {cell_txt}")
    rst_lines.append("")


def html_to_rst(html_text: str) -> str:
    """Convert HTML from Quill.js back to clean, valid reStructuredText (RST)."""
    if not html_text or not html_text.strip():
        return ""

    if BeautifulSoup is None:
        # Fallback if bs4 is missing
        clean = re.sub(r"<[^>]+>", "", html_text)
        return clean.strip()

    soup = BeautifulSoup(html_text, "html.parser")
    rst_lines = []

    def add_heading(text: str, char: str):
        text = text.strip()
        if not text:
            return
        underline = char * max(len(text), 4)
        rst_lines.append(text)
        rst_lines.append(underline)
        rst_lines.append("")

    def add_code_block(code_text: str, lang: str = "text"):
        rst_lines.append(f".. code-block:: {lang}")
        rst_lines.append("")
        for line in code_text.splitlines():
            rst_lines.append(f"    {line}")
        rst_lines.append("")

    def add_admonition(kind: str, title: str, content: str):
        rst_lines.append(f".. {kind}::")
        if title and title.lower() != kind.lower():
            rst_lines.append(f"    :title: {title}")
        rst_lines.append("")
        for line in content.splitlines():
            rst_lines.append(f"    {line}")
        rst_lines.append("")

    def process_element(element):
        if isinstance(element, NavigableString):
            txt = str(element).strip()
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
            text = "".join(_inline_to_rst(c) for c in element.children).strip()
            add_heading(text, "=")
        elif tag == "h2":
            text = "".join(_inline_to_rst(c) for c in element.children).strip()
            add_heading(text, "-")
        elif tag == "h3":
            text = "".join(_inline_to_rst(c) for c in element.children).strip()
            add_heading(text, "~")
        elif tag in ("h4", "h5", "h6"):
            text = "".join(_inline_to_rst(c) for c in element.children).strip()
            add_heading(text, "^")
        elif tag == "pre":
            if "mermaid" in classes:
                code = element.get_text().strip()
                rst_lines.append(".. mermaid::")
                rst_lines.append("")
                for line in code.splitlines():
                    rst_lines.append(f"   {line}")
                rst_lines.append("")
            elif "plantuml" in classes or "uml" in classes:
                code = element.get_text().strip()
                rst_lines.append(".. uml::")
                rst_lines.append("")
                for line in code.splitlines():
                    rst_lines.append(f"   {line}")
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
                rst_lines.append(f"   {line}")
            rst_lines.append("")
        elif "plantuml-block" in classes:
            code = element.get("data-plantuml", "").strip()
            if not code:
                elem = element.find("textarea") or element.find("pre")
                code = elem.get_text().strip() if elem else element.get_text().strip()
            rst_lines.append(".. uml::")
            rst_lines.append("")
            for line in code.splitlines():
                rst_lines.append(f"   {line}")
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
            text = "\n".join("    " + line for line in element.get_text().splitlines())
            rst_lines.append(text)
            rst_lines.append("")
        elif tag == "ul":
            for li in element.find_all("li", recursive=False):
                item_txt = "".join(_inline_to_rst(c) for c in li.children).strip()
                if item_txt:
                    rst_lines.append(f"* {item_txt}")
            rst_lines.append("")
        elif tag == "ol":
            for li in element.find_all("li", recursive=False):
                item_txt = "".join(_inline_to_rst(c) for c in li.children).strip()
                if item_txt:
                    rst_lines.append(f"#. {item_txt}")
            rst_lines.append("")
        elif tag == "p":
            text = "".join(_inline_to_rst(c) for c in element.children).strip()
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\s+([,.:;?!])", r"\1", text)
            if text:
                rst_lines.append(text)
                rst_lines.append("")
        else:
            text = "".join(_inline_to_rst(c) for c in element.children).strip()
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\s+([,.:;?!])", r"\1", text)
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
