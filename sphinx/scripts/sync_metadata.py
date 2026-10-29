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
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""
sync_metadata.py - Automatically synchronize modular docs structure with metadata.json.

Pre-checks formatting of directories and newly added section files:
  - Validates naming conventions (no spaces, recommended snake_case / kebab-case).
  - Validates RST/MD content format and extracts the top-level heading as title.
  - Generates/preserves metadata entries, tagging missing fields with "must update".
  - Creates chapter wrapper files if missing, ensuring merge markers are intact.
"""

import datetime
import json
import os
import re
import sys

if sys.platform == 'win32' and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

IGNORED_DIRS = {
    "_build", ".git", "asset", "assets", "static", "_static",
    "templates", "_templates", "scripts", "template", "__pycache__"
}

RST_ADORNMENTS = set("=-~^\"'*#+`_")

def extract_rst_title(file_path):
    """
    Extract the first heading from an RST or Markdown file and validate formatting.
    Returns: (title, errors, warnings)
    """
    errors = []
    warnings = []
    title = None

    if not os.path.isfile(file_path):
        return None, [f"File does not exist: {file_path}"], []

    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)

    # 1. Check filename format (no spaces)
    if ' ' in filename:
        errors.append(f"Filename contains spaces: '{filename}'. Use underscores or hyphens instead.")

    # 2. Check empty file
    if file_size == 0:
        warnings.append(f"File is empty (0 bytes): {filename}")
        return "must update", errors, warnings

    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = [line.rstrip() for line in f]

    # Markdown style (# Title)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# '):
            title = stripped[2:].strip()
            break

    # RST style heading
    if not title:
        for i in range(len(lines)):
            line = lines[i].strip()
            if not line:
                continue

            # Underline heading (Line followed by adornment)
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(set(next_line)) == 1 and next_line[0] in RST_ADORNMENTS and len(next_line) >= 3:
                    title = line
                    if len(next_line) < len(line):
                        warnings.append(f"In '{filename}': Underline '{next_line}' is shorter than title '{line}'")
                    break

            # Overline + Underline heading
            if i + 2 < len(lines):
                curr = lines[i].strip()
                mid = lines[i + 1].strip()
                bot = lines[i + 2].strip()
                if curr and bot and len(set(curr)) == 1 and curr[0] in RST_ADORNMENTS and curr == bot and mid:
                    title = mid
                    break

    if not title:
        warnings.append(f"No standard top-level heading found in '{filename}'. Setting title to 'must update'.")
        title = "must update"

    return title, errors, warnings


def ensure_chapter_file(base_dir, chapter_name):
    """
    Ensure the chapter .rst file exists and contains the required merge markers.
    """
    chapter_path = os.path.join(base_dir, chapter_name)
    start_markers = ['..@created_docs_from_metadata.json start', '.. @created_docs_from_metadata.json start']
    end_markers = ['..@created_docs_from_metadata.json end', '.. @created_docs_from_metadata.json end']

    title_stem = os.path.splitext(chapter_name)[0].replace('_', ' ').title()

    if not os.path.isfile(chapter_path):
        underline = "=" * max(len(title_stem), 4)
        content = (
            f"{title_stem}\n"
            f"{underline}\n\n"
            f".. @created_docs_from_metadata.json start\n\n"
            f".. @created_docs_from_metadata.json end\n"
        )
        with open(chapter_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, f"Auto-created chapter wrapper: {chapter_name}"

    # Verify markers in existing file
    with open(chapter_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    has_start = any(sm in content for sm in start_markers)
    has_end = any(em in content for em in end_markers)

    if not has_start or not has_end:
        with open(chapter_path, 'a', encoding='utf-8') as f:
            f.write("\n\n.. @created_docs_from_metadata.json start\n\n.. @created_docs_from_metadata.json end\n")
        return True, f"Added missing merge markers to: {chapter_name}"

    return False, None


def main():
    base_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
    metadata_file = os.path.join(base_dir, 'metadata.json')
    today_str = datetime.date.today().isoformat()

    print(f"\033[1;36m[DOCS-SYNC]\033[0m Target documentation directory: {base_dir}")

    # Load existing metadata if present
    existing_metadata = []
    if os.path.isfile(metadata_file):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                existing_metadata = json.load(f)
        except Exception as e:
            print(f"\033[1;33m[WARN]\033[0m Could not parse existing metadata.json ({e}). Starting fresh.")
            existing_metadata = []

    # Build lookup map of existing chapters and sections
    chapter_map = {}
    for ch in existing_metadata:
        c_name = ch.get('chapter', '')
        if c_name:
            chapter_map[c_name] = {
                'info': ch,
                'sections': {s.get('filePath', ''): s for s in ch.get('dataList', []) if s.get('filePath')}
            }

    all_errors = []
    all_warnings = []

    # 1. Discover chapter directories and standalone chapter .rst files
    discovered_chapters = {}

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)

        # Candidate chapter directories (e.g., chapter1, chapter2, getting_started)
        if os.path.isdir(entry_path):
            if entry in IGNORED_DIRS or entry.startswith('.'):
                continue

            # Format check for directory name
            if ' ' in entry:
                all_errors.append(f"Directory name contains spaces: '{entry}'. Use underscores or hyphens instead.")

            # Scan for .rst or .md files inside this chapter directory
            section_files = []
            for root, _, files in os.walk(entry_path):
                for f in sorted(files):
                    if f.endswith('.rst') or f.endswith('.md'):
                        rel_path = os.path.relpath(os.path.join(root, f), base_dir).replace('\\', '/')
                        section_files.append(rel_path)

            if section_files:
                # Chapter wrapper name (e.g., chapter1.rst)
                chapter_file = f"{entry}.rst"
                discovered_chapters[chapter_file] = {
                    'dir_name': entry,
                    'sections': section_files
                }

    # Also discover any chapter .rst files explicitly in metadata or on disk
    for ch_file in list(chapter_map.keys()):
        if ch_file not in discovered_chapters and os.path.isfile(os.path.join(base_dir, ch_file)):
            stem = os.path.splitext(ch_file)[0]
            discovered_chapters[ch_file] = {
                'dir_name': stem,
                'sections': []
            }

    # 2. Format validation on discovered sections
    print("\033[1;34m[INFO]\033[0m Validating formatting of modular chapter files...")
    section_titles = {}
    for ch_file, ch_data in discovered_chapters.items():
        for s_path in ch_data['sections']:
            abs_s_path = os.path.join(base_dir, s_path)
            title, errs, warns = extract_rst_title(abs_s_path)
            section_titles[s_path] = title
            all_errors.extend(errs)
            all_warnings.extend(warns)

    # Print format validation results
    if all_warnings:
        print(f"\033[1;33m[FORMAT WARNINGS]\033[0m ({len(all_warnings)} issues found):")
        for w in all_warnings:
            print(f"  \033[0;33m⚠\033[0m {w}")

    if all_errors:
        print(f"\033[1;31m[FORMAT ERRORS]\033[0m ({len(all_errors)} issues found):")
        for e in all_errors:
            print(f"  \033[1;31m✖\033[0m {e}")
        print("\033[1;31m[ERROR]\033[0m Please fix formatting errors (e.g. remove spaces from filenames) before syncing.")
        sys.exit(1)

    # 3. Synchronize metadata
    updated_metadata = []
    added_sections_count = 0
    preserved_sections_count = 0
    must_update_count = 0

    for ch_file, ch_data in discovered_chapters.items():
        # Ensure chapter wrapper file exists
        created, msg = ensure_chapter_file(base_dir, ch_file)
        if created and msg:
            print(f"\033[1;32m[INFO]\033[0m {msg}")

        existing_ch = chapter_map.get(ch_file, {})
        existing_info = existing_ch.get('info', {})
        existing_sections = existing_ch.get('sections', {})

        ch_author = existing_info.get('author', 'must update')
        if not ch_author or ch_author.strip() == '':
            ch_author = 'must update'
        if ch_author == 'must update':
            must_update_count += 1

        ch_created = existing_info.get('updateCreated', today_str)

        new_data_list = []
        for s_path in ch_data['sections']:
            if s_path in existing_sections:
                # Preserve existing metadata
                sec = existing_sections[s_path].copy()
                if not sec.get('title') or sec.get('title') == 'must update':
                    sec['title'] = section_titles.get(s_path, 'must update')
                if not sec.get('description'):
                    sec['description'] = 'must update'
                if not sec.get('updateCreated'):
                    sec['updateCreated'] = today_str
                if sec.get('description') == 'must update':
                    must_update_count += 1
                new_data_list.append(sec)
                preserved_sections_count += 1
            else:
                # New section discovered
                new_sec = {
                    'filePath': s_path,
                    'title': section_titles.get(s_path, 'must update'),
                    'description': 'must update',
                    'updateCreated': today_str
                }
                new_data_list.append(new_sec)
                added_sections_count += 1
                must_update_count += 1

        updated_metadata.append({
            'chapter': ch_file,
            'author': ch_author,
            'updateCreated': ch_created,
            'dataList': new_data_list
        })

    # 4. Save updated metadata.json
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(updated_metadata, f, indent=4, ensure_ascii=False)
        f.write('\n')

    print("\n\033[1;32m============================================================\033[0m")
    print("\033[1;32m  DOCS METADATA SYNC COMPLETED SUCCESSFULLY\033[0m")
    print("\033[1;32m============================================================\033[0m")
    print(f"  Chapters synchronized : {len(updated_metadata)}")
    print(f"  Sections preserved    : {preserved_sections_count}")
    print(f"  New sections added    : \033[1;32m+{added_sections_count}\033[0m")
    if must_update_count > 0:
        print(f"  Pending fields        : \033[1;33m{must_update_count} fields marked as 'must update'\033[0m")
        print("  \033[0;90mTip: Open metadata.json and search 'must update' to fill in descriptions.\033[0m")
    else:
        print("  Pending fields        : \033[1;32mAll descriptions and metadata are up to date!\033[0m")
    print(f"  Target File           : {metadata_file}\n")


if __name__ == '__main__':
    main()
