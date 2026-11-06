#!/usr/bin/env python3
"""Check mermaid diagrams in Sphinx RST docs for common syntax errors.

Mermaid parses each line as a separate statement. The most common mistakes
that render as "Syntax error in text" in the browser (while the Sphinx build
still succeeds) are:

  1. LEADING-ARROW : an edge arrow (--> | --- | ==> | -.- | ~~) that starts
     its own line. The previous node and the target must be on the same line.
  2. DANGLING-EDGE : a line that ends with an arrow (optionally with a label)
     while the target node is on the next line.

Usage:
    python check_mermaid.py <docs_dir>

Exit codes: 0 = clean, 1 = issues found (or docs dir / metadata.json missing).
"""

import json
import os
import re
import sys

# Edge arrows supported by flowchart / graph diagrams
ARROWS = r'(?:-->|---|==>|-\.-(?:-+)?|-+~~+|==o|-x|o--o|x--x)'

# Line that starts with an edge arrow (statement split across lines)
LEADING_ARROW = re.compile(r'^\s*' + ARROWS)

# Line that ends with an arrow, optionally followed by an edge label
# (target node is on the next line)
DANGLING_EDGE = re.compile(ARROWS + r'\s*(?:\|[^|]*\|)?\s*$')


def check_rst_file(rst_path):
    """Return a list of (line_number, kind, line_text) issues in one rst file."""
    issues = []
    with open(rst_path, 'r', encoding='utf-8-sig') as f:
        lines = f.read().split('\n')

    in_block = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == '.. mermaid::':
            in_block = True
            continue
        if in_block:
            # Blank line or indented content belongs to the mermaid block
            if stripped == '' or line.startswith(('   ', '\t')):
                if LEADING_ARROW.match(line):
                    issues.append((i, 'LEADING-ARROW', stripped))
                if DANGLING_EDGE.search(line):
                    issues.append((i, 'DANGLING-EDGE', stripped))
            else:
                # First non-indented line ends the mermaid block
                in_block = False
    return issues


def collect_rst_files(base_dir):
    """Collect chapter files from metadata.json plus all section files."""
    files = []
    metadata_file = os.path.join(base_dir, 'metadata.json')
    if not os.path.isfile(metadata_file):
        return files, None
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    for chapter in metadata:
        chapter_file = os.path.join(base_dir, chapter.get('chapter', ''))
        if os.path.isfile(chapter_file):
            files.append(chapter_file)
        for section in chapter.get('dataList', []):
            section_file = os.path.join(base_dir, section.get('filePath', ''))
            if os.path.isfile(section_file):
                files.append(section_file)
    return files, metadata_file


def main():
    base_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
        os.path.dirname(os.path.abspath(__file__))

    if not os.path.isdir(base_dir):
        print(f'Error: docs directory not found: {base_dir}')
        sys.exit(1)

    files, metadata_file = collect_rst_files(base_dir)
    if metadata_file is None:
        print(f'Error: metadata.json not found in {base_dir}')
        sys.exit(1)

    all_issues = []
    for path in files:
        for line_no, kind, text in check_rst_file(path):
            rel = os.path.relpath(path, base_dir)
            all_issues.append(f'{rel}:{line_no}: [{kind}] {text[:100]}')

    if all_issues:
        print('Mermaid syntax issues found '
              '(each edge must be a complete statement on ONE line):')
        for issue in all_issues:
            print(' -', issue)
        print(f'\nTotal: {len(all_issues)} issue(s). '
              'Fix in the SECTION files, then re-run merge_docs.py.')
        sys.exit(1)

    print(f'All mermaid diagrams are valid ({len(files)} rst files checked).')
    sys.exit(0)


if __name__ == '__main__':
    main()
