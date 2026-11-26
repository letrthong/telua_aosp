# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""
code_structure_engine.py — AST and Structure-Aware Code Analysis Engine.

Solves the naive line/character slicing problem for AI code understanding:
1. Outline generation: View high-level symbols (classes, interfaces, methods, functions)
   with exact line numbers without flooding token context.
2. Complete Symbol Extraction: Fetch complete function bodies from signature to closing
   brace with enclosing class header context and javadoc/docstrings.
3. Smart Boundary Snapping: Automatically snap line-based chunk boundaries forward so
   functions are never severed in half.
4. Function-as-a-Chunk Vector Indexing: Slices code files into AST/method units with
   context headers for ChromaDB semantic search.
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pygments
    from pygments.lexers import get_lexer_for_filename, get_lexer_by_name
    from pygments.token import Token
    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False


@dataclass
class CodeSymbol:
    """Represents a code symbol (method, function, class, interface)."""
    name: str
    kind: str  # "class", "interface", "method", "function", "struct", "enum"
    signature: str
    start_line: int       # 1-based start line (including docstring/comments if present)
    signature_line: int   # 1-based line where signature statement starts
    end_line: int         # 1-based end line (closing brace or block end)
    docstring: str = ""
    enclosing_class: str = ""
    body: str = ""


@dataclass
class ParsedCodeStructure:
    """Structure map of a parsed code file."""
    filename: str
    language: str
    total_lines: int
    package: str = ""
    imports: List[str] = field(default_factory=list)
    classes: List[CodeSymbol] = field(default_factory=list)
    methods: List[CodeSymbol] = field(default_factory=list)
    header_context: str = ""  # Package, imports, class header, top member fields


class CodeStructureEngine:
    """Unified AST and structure-aware code analysis engine for Telua AOSP."""

    # Regex patterns for Java, C++, Kotlin, C#
    _METHOD_RE = re.compile(
        r"^\s*(?:(?:public|private|protected|static|final|synchronized|abstract|default|native|override|suspend|inline|virtual|inline|constexpr)\s+)*"
        r"(?:([\w<>\[\],\s\?\*&]+)\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*"
        r"(?:throws\s+[\w,\s]+)?\s*(?:const)?\s*(?:override)?\s*\{?",
        re.MULTILINE,
    )

    _CLASS_RE = re.compile(
        r"^\s*(?:(?:public|private|protected|static|final|abstract|sealed|open|data)\s+)*"
        r"(class|interface|enum|record|struct)\s+([a-zA-Z0-9_]+)",
        re.MULTILINE,
    )

    _PACKAGE_RE = re.compile(r"^\s*package\s+([\w\.]+);?", re.MULTILINE)
    _IMPORT_RE = re.compile(r"^\s*(?:import|#include)\s+([^\n;]+);?", re.MULTILINE)

    @classmethod
    def detect_language(cls, filename_or_ext: str) -> str:
        """Infer programming language from file extension."""
        ext = Path(filename_or_ext).suffix.lower()
        mapping = {
            ".py": "python",
            ".java": "java",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".h": "cpp",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".aidl": "aidl",
            ".sh": "bash",
            ".bp": "blueprint",
        }
        return mapping.get(ext, "text")

    @classmethod
    def parse_text(cls, content: str, filename_or_ext: str = "") -> ParsedCodeStructure:
        """Parse source text into structural symbols (AST/Brace tracker)."""
        lang = cls.detect_language(filename_or_ext)
        lines = content.splitlines()
        total_lines = len(lines)

        if lang == "python":
            return cls._parse_python(content, filename_or_ext, lines)
        elif lang in ("java", "kotlin", "cpp", "c", "csharp", "javascript", "typescript", "rust", "go", "aidl"):
            return cls._parse_brace_code(content, filename_or_ext, lang, lines)
        else:
            # Fallback for plain text or generic files
            return ParsedCodeStructure(
                filename=filename_or_ext,
                language=lang,
                total_lines=total_lines,
                header_context="\n".join(lines[:min(30, total_lines)]),
            )

    @classmethod
    def _parse_python(cls, content: str, filename: str, lines: List[str]) -> ParsedCodeStructure:
        """Parse Python source using standard AST."""
        structure = ParsedCodeStructure(
            filename=filename,
            language="python",
            total_lines=len(lines),
        )

        try:
            tree = ast.parse(content)
        except Exception:
            # If syntax error, return partial structure
            structure.header_context = "\n".join(lines[:min(40, len(lines))])
            return structure

        # Collect imports
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    structure.imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = ", ".join(a.name for a in node.names)
                structure.imports.append(f"from {mod} import {names}")

        def _get_docstring_start(node: ast.AST) -> int:
            return getattr(node, "lineno", 1)

        # Walk classes and functions
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cls_doc = ast.get_docstring(node) or ""
                cls_sym = CodeSymbol(
                    name=node.name,
                    kind="class",
                    signature=f"class {node.name}:",
                    start_line=node.lineno,
                    signature_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    docstring=cls_doc,
                    body="\n".join(lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)]),
                )
                structure.classes.append(cls_sym)

                # Methods inside class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_doc = ast.get_docstring(item) or ""
                        sig_args = [a.arg for a in item.args.args]
                        prefix = "async def " if isinstance(item, ast.AsyncFunctionDef) else "def "
                        sig = f"{prefix}{item.name}({', '.join(sig_args)})"
                        
                        # Find decorator start line if any
                        start_l = item.lineno
                        if item.decorator_list:
                            start_l = min(d.lineno for d in item.decorator_list)

                        end_l = getattr(item, "end_lineno", item.lineno)
                        method_sym = CodeSymbol(
                            name=item.name,
                            kind="method",
                            signature=sig,
                            start_line=start_l,
                            signature_line=item.lineno,
                            end_line=end_l,
                            docstring=m_doc,
                            enclosing_class=node.name,
                            body="\n".join(lines[start_l - 1 : end_l]),
                        )
                        structure.methods.append(method_sym)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f_doc = ast.get_docstring(node) or ""
                sig_args = [a.arg for a in node.args.args]
                prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
                sig = f"{prefix}{node.name}({', '.join(sig_args)})"

                start_l = node.lineno
                if node.decorator_list:
                    start_l = min(d.lineno for d in node.decorator_list)

                end_l = getattr(node, "end_lineno", node.lineno)
                func_sym = CodeSymbol(
                    name=node.name,
                    kind="function",
                    signature=sig,
                    start_line=start_l,
                    signature_line=node.lineno,
                    end_line=end_l,
                    docstring=f_doc,
                    enclosing_class="",
                    body="\n".join(lines[start_l - 1 : end_l]),
                )
                structure.methods.append(func_sym)

        # Build header context: imports + class definitions + docstring
        hdr_lines = []
        if structure.imports:
            hdr_lines.extend(structure.imports[:15])
        for c in structure.classes:
            hdr_lines.append(f"class {c.name}: ...")
        structure.header_context = "\n".join(hdr_lines) if hdr_lines else "\n".join(lines[:min(30, len(lines))])

        return structure

    @classmethod
    def _parse_brace_code(
        cls, content: str, filename: str, lang: str, lines: List[str]
    ) -> ParsedCodeStructure:
        """Parse C-family, Java, Kotlin curly-brace languages with Pygments & brace tracker."""
        structure = ParsedCodeStructure(
            filename=filename,
            language=lang,
            total_lines=len(lines),
        )

        # Extract package and imports
        pkg_m = cls._PACKAGE_RE.search(content)
        if pkg_m:
            structure.package = pkg_m.group(1).strip()

        for imp in cls._IMPORT_RE.finditer(content):
            structure.imports.append(imp.group(0).strip())

        # Scan for classes and interfaces
        class_scopes: List[Tuple[str, str, int]] = []  # (kind, name, start_line)

        # Step 1: Detect all class/interface headers
        for idx, line in enumerate(lines, 1):
            m_cls = cls._CLASS_RE.search(line)
            if m_cls:
                kind = m_cls.group(1)
                name = m_cls.group(2)
                structure.classes.append(
                    CodeSymbol(
                        name=name,
                        kind=kind,
                        signature=line.strip(),
                        start_line=idx,
                        signature_line=idx,
                        end_line=len(lines),
                        enclosing_class="",
                    )
                )

        # Step 2: Use Pygments token stream to accurately track brace depth and locate methods
        method_candidates = []
        # Pre-scan potential method lines using regex
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and control statements
            if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                continue
            if stripped.startswith("if ") or stripped.startswith("for ") or stripped.startswith("while ") or stripped.startswith("switch "):
                continue
            if stripped.startswith("catch ") or stripped.startswith("else"):
                continue

            m = cls._METHOD_RE.search(line)
            if m:
                ret_or_mod = m.group(1) or ""
                m_name = m.group(2)
                params = m.group(3) or ""
                # Filter out keywords that look like function calls
                if m_name in ("if", "for", "while", "switch", "catch", "synchronized", "sizeof", "typeof"):
                    continue
                # Determine preceding docstring/comment lines
                doc_lines = []
                c_idx = idx - 2
                while c_idx >= 0:
                    prev = lines[c_idx].strip()
                    if prev.startswith("*") or prev.startswith("/*") or prev.startswith("*/") or prev.startswith("//") or prev.startswith("@"):
                        doc_lines.insert(0, lines[c_idx])
                        c_idx -= 1
                    else:
                        break
                
                docstring = "\n".join(doc_lines)
                start_l = (c_idx + 2) if doc_lines else idx

                method_candidates.append({
                    "name": m_name,
                    "signature": line.strip(),
                    "signature_line": idx,
                    "start_line": start_l,
                    "docstring": docstring,
                })

        # Step 3: Pygments brace depth tracking to match method start and end braces
        brace_tokens = []
        if _HAS_PYGMENTS:
            try:
                lexer = get_lexer_for_filename(filename) if filename else get_lexer_by_name(lang)
            except Exception:
                lexer = None

            if lexer:
                cur_line = 1
                for tok_type, val in pygments.lex(content, lexer):
                    if tok_type in Token.Punctuation and val in ("{", "}"):
                        brace_tokens.append((cur_line, val))
                    cur_line += val.count("\n")

        # Fallback simple brace scanner if pygments not loaded or produced no braces
        if not brace_tokens:
            in_multiline_comment = False
            for idx, line in enumerate(lines, 1):
                clean = ""
                i = 0
                while i < len(line):
                    if in_multiline_comment:
                        end_c = line.find("*/", i)
                        if end_c != -1:
                            in_multiline_comment = False
                            i = end_c + 2
                        else:
                            break
                    elif line[i:i+2] == "/*":
                        in_multiline_comment = True
                        i += 2
                    elif line[i:i+2] == "//":
                        break
                    elif line[i] in ('"', "'"):
                        quote = line[i]
                        i += 1
                        while i < len(line) and line[i] != quote:
                            if line[i] == "\\" and i + 1 < len(line):
                                i += 2
                            else:
                                i += 1
                        i += 1
                    else:
                        clean += line[i]
                        i += 1
                for ch in clean:
                    if ch in ("{", "}"):
                        brace_tokens.append((idx, ch))

        # Match class candidates to closing braces
        for c in structure.classes:
            sig_line = c.signature_line
            open_idx = -1
            open_depth = 0
            cur_depth = 0
            for b_idx, (b_line, b_val) in enumerate(brace_tokens):
                if b_line < sig_line:
                    cur_depth += 1 if b_val == "{" else -1
                elif b_line >= sig_line and b_line <= sig_line + 5:
                    if b_val == "{" and open_idx == -1:
                        open_idx = b_idx
                        open_depth = cur_depth + 1
                        cur_depth += 1
                    else:
                        cur_depth += 1 if b_val == "{" else -1
                else:
                    cur_depth += 1 if b_val == "{" else -1

            if open_idx != -1:
                match_depth = open_depth - 1
                run_depth = open_depth
                for b_idx in range(open_idx + 1, len(brace_tokens)):
                    b_line, b_val = brace_tokens[b_idx]
                    if b_val == "{":
                        run_depth += 1
                    elif b_val == "}":
                        run_depth -= 1
                        if run_depth == match_depth:
                            c.end_line = b_line
                            break

        # Match method candidates to opening and closing braces
        for cand in method_candidates:
            sig_line = cand["signature_line"]
            # Find the opening brace on or immediately after signature line (within 5 lines)
            open_idx = -1
            open_depth = 0
            cur_depth = 0

            for b_idx, (b_line, b_val) in enumerate(brace_tokens):
                if b_line < sig_line:
                    cur_depth += 1 if b_val == "{" else -1
                elif b_line >= sig_line and b_line <= sig_line + 5:
                    if b_val == "{" and open_idx == -1:
                        open_idx = b_idx
                        open_depth = cur_depth + 1
                        cur_depth += 1
                    else:
                        cur_depth += 1 if b_val == "{" else -1
                else:
                    cur_depth += 1 if b_val == "{" else -1

            if open_idx != -1:
                # Find matching closing brace where depth returns to open_depth - 1
                match_depth = open_depth - 1
                run_depth = open_depth
                end_line = cand["signature_line"]
                for b_idx in range(open_idx + 1, len(brace_tokens)):
                    b_line, b_val = brace_tokens[b_idx]
                    if b_val == "{":
                        run_depth += 1
                    elif b_val == "}":
                        run_depth -= 1
                        if run_depth == match_depth:
                            end_line = b_line
                            break

                # Infer enclosing class (innermost class enclosing signature line)
                enclosing = ""
                min_span = float("inf")
                for c in structure.classes:
                    if c.start_line <= sig_line <= c.end_line:
                        span = c.end_line - c.start_line
                        if span < min_span:
                            min_span = span
                            enclosing = c.name

                # Extract method body
                start_l = cand["start_line"]
                body = "\n".join(lines[start_l - 1 : end_line])

                structure.methods.append(
                    CodeSymbol(
                        name=cand["name"],
                        kind="method",
                        signature=cand["signature"],
                        start_line=start_l,
                        signature_line=cand["signature_line"],
                        end_line=end_line,
                        docstring=cand["docstring"],
                        enclosing_class=enclosing,
                        body=body,
                    )
                )

        # Build header context: Package, Imports, and First Class Declaration up to first method
        first_m_line = structure.methods[0].start_line if structure.methods else len(lines)
        first_m_line = max(1, min(first_m_line, 80))
        structure.header_context = "\n".join(lines[:first_m_line])

        return structure

    @classmethod
    def get_outline(cls, content: str, filename_or_ext: str = "", rel_path: str = "") -> str:
        """Generate a compact structural outline of classes, interfaces, and methods."""
        struct = cls.parse_text(content, filename_or_ext)
        display_path = rel_path or filename_or_ext or "File"

        lines = [
            f"=== OUTLINE: {display_path} ({struct.total_lines} lines, {struct.language.upper()}) ===",
        ]
        if struct.package:
            lines.append(f"Package: {struct.package}")

        if struct.classes:
            lines.append("Classes & Interfaces:")
            for c in struct.classes:
                lines.append(f"  [{c.kind.upper()}] Line {c.start_line}: {c.signature}")

        if struct.methods:
            lines.append(f"Methods & Functions ({len(struct.methods)} symbols):")
            for m in struct.methods:
                cls_pfx = f"{m.enclosing_class}." if m.enclosing_class else ""
                lines.append(f"  - Line {m.start_line:4d}-{m.end_line:4d}: {cls_pfx}{m.name}() -> {m.signature[:80]}")
        else:
            lines.append("(No distinct methods detected; use line range reading)")

        lines.append("\nTip: Use read_file with method='<name>' to read the complete function body without line limits.")
        return "\n".join(lines)

    @classmethod
    def extract_symbol(
        cls, content: str, filename_or_ext: str, symbol_name: str, rel_path: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Extract a complete function/method/class by name with enclosing header context."""
        struct = cls.parse_text(content, filename_or_ext)
        display_path = rel_path or filename_or_ext or "File"
        target = symbol_name.strip().lower()

        # Check methods
        matched_methods = [
            m for m in struct.methods
            if m.name.lower() == target or f"{m.enclosing_class}.{m.name}".lower() == target
        ]

        if matched_methods:
            # If multiple overloads exist, present them all or the first one
            blocks = []
            for idx, m in enumerate(matched_methods, 1):
                overload_tag = f" [Overload {idx}/{len(matched_methods)}]" if len(matched_methods) > 1 else ""
                header = (
                    f"=== SYMBOL: {m.enclosing_class + '.' if m.enclosing_class else ''}{m.name} "
                    f"in {display_path} (Lines {m.start_line}-{m.end_line}){overload_tag} ==="
                )
                enclosing_note = f"// Enclosing: {struct.package + '.' if struct.package else ''}{m.enclosing_class}"
                blocks.append(f"{header}\n{enclosing_note}\n\n{m.body}")

            return {
                "ok": True,
                "symbol": matched_methods[0].name,
                "kind": "method",
                "start_line": matched_methods[0].start_line,
                "end_line": matched_methods[-1].end_line,
                "output": "\n\n" + ("=" * 70) + "\n\n".join(blocks),
            }

        # Check classes
        matched_classes = [c for c in struct.classes if c.name.lower() == target]
        if matched_classes:
            c = matched_classes[0]
            header = f"=== CLASS SYMBOL: {c.name} in {display_path} (Lines {c.start_line}-{c.end_line}) ==="
            return {
                "ok": True,
                "symbol": c.name,
                "kind": c.kind,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "output": f"{header}\n\n{c.body[:8000]}",
            }

        return None

    @classmethod
    def snap_boundaries(
        cls, content: str, filename_or_ext: str, start_line: int, end_line: int, max_snap: int = 50
    ) -> Tuple[int, int, Optional[str]]:
        """
        Snap end_line forward if it cuts inside a method near its closing brace.
        Prevents chopping functions in half.
        """
        struct = cls.parse_text(content, filename_or_ext)
        actual_end = end_line
        note = None

        for m in struct.methods:
            # If end_line falls inside a method, and the remaining method lines <= max_snap
            if m.start_line <= end_line < m.end_line:
                remaining_in_method = m.end_line - end_line
                if remaining_in_method <= max_snap:
                    actual_end = m.end_line
                    note = f"[Smart Snap: Extended end_line {end_line} -> {actual_end} to complete {m.name}()]"
                    break

        return start_line, actual_end, note

    @classmethod
    def chunk_code_for_vector_db(
        cls,
        content: str,
        filename_or_ext: str,
        metadata_base: Dict[str, Any],
        max_chunk_chars: int = 3500,
    ) -> List[Dict[str, Any]]:
        """
        Slice source code into AST/Function-aware semantic chunks for ChromaDB.
        Each function is stored as a complete semantic chunk with file & class context.
        """
        struct = cls.parse_text(content, filename_or_ext)
        chunks: List[Dict[str, Any]] = []
        rel_path = metadata_base.get("rel_path", filename_or_ext)
        source_id = metadata_base.get("source_id", "source")

        # If no methods found (or non-code file), fallback to smart line chunking
        if not struct.methods:
            lines = content.splitlines()
            step = 100
            for i in range(0, len(lines), step):
                chunk_lines = lines[i : i + step]
                chunk_body = "\n".join(chunk_lines)
                if not chunk_body.strip():
                    continue
                part_num = (i // step) + 1
                doc_text = (
                    f"SOURCE: {metadata_base.get('source_name', source_id)}\n"
                    f"FILE: {rel_path} (Lines {i+1}-{min(len(lines), i+step)})\n\n"
                    f"{chunk_body}"
                )
                chunk_meta = dict(metadata_base)
                chunk_meta["chunk_type"] = "text_range"
                chunk_meta["start_line"] = i + 1
                chunk_meta["end_line"] = min(len(lines), i + step)
                clean_rel = rel_path.replace("/", "_").replace("\\", "_").replace(".", "_").replace("-", "_")
                chunk_id = f"skill_{source_id}_{clean_rel}_p{part_num}"
                chunks.append({"id": chunk_id, "document": doc_text, "metadata": chunk_meta})
            return chunks

        # Chunk 0: Class & Architecture Context
        class_summary_lines = []
        for c in struct.classes:
            class_summary_lines.append(f"Class: {c.signature}")
        method_names = [f"{m.name}()" for m in struct.methods[:30]]

        context_doc = (
            f"SOURCE: {metadata_base.get('source_name', source_id)}\n"
            f"FILE: {rel_path} (Total Lines: {struct.total_lines}, Language: {struct.language.upper()})\n"
            f"PACKAGE: {struct.package}\n"
            f"CLASSES: {', '.join(c.name for c in struct.classes)}\n"
            f"KEY METHODS: {', '.join(method_names)}\n\n"
            f"--- HEADER CONTEXT (Package, Imports & Declarations) ---\n"
            f"{struct.header_context}"
        )
        ctx_meta = dict(metadata_base)
        ctx_meta["chunk_type"] = "class_context"
        ctx_meta["symbol_name"] = "__class_context__"
        ctx_meta["start_line"] = 1
        ctx_meta["end_line"] = struct.methods[0].start_line - 1 if struct.methods else struct.total_lines
        clean_rel = rel_path.replace("/", "_").replace("\\", "_").replace(".", "_").replace("-", "_")
        chunks.append({
            "id": f"skill_{source_id}_{clean_rel}_context",
            "document": context_doc[:max_chunk_chars],
            "metadata": ctx_meta,
        })

        # Chunks 1..N: Each Method as a Complete Semantic Block
        for idx, m in enumerate(struct.methods):
            doc_lines = [
                f"SOURCE: {metadata_base.get('source_name', source_id)}",
                f"FILE: {rel_path} (Lines {m.start_line}-{m.end_line})",
                f"CLASS: {m.enclosing_class or 'Global'}",
                f"METHOD: {m.name}",
                f"SIGNATURE: {m.signature}",
            ]
            if m.docstring:
                doc_lines.append(f"DOCSTRING: {m.docstring.strip()[:300]}")
            doc_lines.append(f"\n// Full Body of {m.enclosing_class + '.' if m.enclosing_class else ''}{m.name}:")
            doc_lines.append(m.body)

            full_method_doc = "\n".join(doc_lines)
            if len(full_method_doc) > max_chunk_chars:
                full_method_doc = full_method_doc[:max_chunk_chars]

            m_meta = dict(metadata_base)
            m_meta["chunk_type"] = "method_symbol"
            m_meta["symbol_name"] = m.name
            m_meta["symbol_kind"] = m.kind
            m_meta["enclosing_class"] = m.enclosing_class
            m_meta["start_line"] = m.start_line
            m_meta["end_line"] = m.end_line

            clean_mname = m.name.replace(".", "_").replace("<", "_").replace(">", "_")
            chunks.append({
                "id": f"skill_{source_id}_{clean_rel}_m_{idx}_{clean_mname}",
                "document": full_method_doc,
                "metadata": m_meta,
            })

        return chunks
