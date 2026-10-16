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

"""Apply apk_overlays.config on top of apk.config (called by 'telua init').

Usage:
  ./config_overlay.py <target_config> [overlay_config] [--dry-run]
  ./config_overlay.py ./apk.config                      # overlay defaults to apk_overlays.config next to this script
  ./config_overlay.py ./apk.config my_overlay.config --dry-run

Rules:
  - Overlay lines of the form KEY=value (or multi-line arrays KEY=( ... )) are applied.
    Comments and blank lines in the overlay are ignored. If a key repeats, the last one wins.
  - Every top-level (non-indented) KEY= assignment in the target is replaced in place,
    keeping its position and surrounding comments. Multi-line arrays are replaced whole.
  - Keys with no top-level assignment in the target (e.g. MODULE_NAME, which only exists
    inside the ACTIVE_PROJECT case block, or commented-out examples) are appended at the
    end of the file, so they override earlier values when apk.config is sourced.
  - Indented assignments (inside the case block) are never touched, so other profiles stay intact.

Standard library only; no extra dependencies.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OVERLAY = os.path.join(SCRIPT_DIR, "apk_overlays.config")
ASSIGN_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
APPEND_HEADER = "# ---- Overrides from apk_overlays.config (appended by telua init) ----"


def read_lines(path: str) -> list[str]:
    # newline="" keeps the original line endings (LF must be preserved for Linux).
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read().splitlines(keepends=True)


def find_assignments(lines: list[str], allow_indent: bool) -> list[tuple[str, int, int]]:
    """Return (key, start_line, end_line) for each shell assignment; arrays may span lines."""
    result = []
    i = 0
    while i < len(lines):
        text = lines[i].rstrip("\r\n")
        if not allow_indent and text[:1] in (" ", "\t"):
            i += 1
            continue
        match = ASSIGN_RE.match(text.strip())
        if not match:
            i += 1
            continue
        key, value = match.group(1), match.group(2)
        end = i
        # Multi-line array: KEY=( ... ) where the closing ')' is on a later line.
        if value.lstrip().startswith("(") and not value.rstrip().endswith(")"):
            while end + 1 < len(lines):
                end += 1
                if lines[end].rstrip().endswith(")"):
                    break
        result.append((key, i, end))
        i = end + 1
    return result


def load_overlay(path: str) -> dict[str, list[str]]:
    """Map KEY -> lines of its assignment block (without line endings), in file order."""
    lines = read_lines(path)
    overlay: dict[str, list[str]] = {}
    for key, start, end in find_assignments(lines, allow_indent=True):
        block = [line.rstrip("\r\n") for line in lines[start:end + 1]]
        block[0] = block[0].lstrip()
        overlay.pop(key, None)  # last definition wins, and moves to the end of the order
        overlay[key] = block
    return overlay


def apply_overlay(target_lines: list[str], overlay: dict[str, list[str]], newline: str):
    top_level: dict[str, list[tuple[int, int]]] = {}
    for key, start, end in find_assignments(target_lines, allow_indent=False):
        top_level.setdefault(key, []).append((start, end))

    replacements: dict[int, tuple[int, list[str]]] = {}
    replaced, appended = [], []
    for key, block in overlay.items():
        if key in top_level:
            for start, end in top_level[key]:
                replacements[start] = (end, block)
            replaced.append(key)
        else:
            appended.append(key)

    output: list[str] = []
    i = 0
    while i < len(target_lines):
        if i in replacements:
            end, block = replacements[i]
            output.extend(line + newline for line in block)
            i = end + 1
        else:
            output.append(target_lines[i])
            i += 1

    if appended:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += newline
        output.append(newline)
        output.append(APPEND_HEADER + newline)
        for key in appended:
            output.extend(line + newline for line in overlay[key])

    return output, replaced, appended


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="apk.config to modify in place")
    parser.add_argument("overlay", nargs="?", default=DEFAULT_OVERLAY,
                        help="overlay file (default: apk_overlays.config next to this script)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    args = parser.parse_args()

    if not os.path.isfile(args.target):
        sys.exit(f"ERROR: target config not found: {args.target}")
    if not os.path.isfile(args.overlay):
        sys.exit(f"ERROR: overlay file not found: {args.overlay}")
    if os.path.abspath(args.target) == os.path.abspath(args.overlay):
        sys.exit("ERROR: target and overlay must be different files")

    overlay = load_overlay(args.overlay)
    if not overlay:
        print(f"Overlay has no KEY=value entries, nothing to apply: {args.overlay}")
        return

    target_lines = read_lines(args.target)
    newline = "\r\n" if target_lines and target_lines[0].endswith("\r\n") else "\n"
    output, replaced, appended = apply_overlay(target_lines, overlay, newline)

    if replaced:
        print(f"Replaced ({len(replaced)}): {' '.join(replaced)}")
    if appended:
        print(f"Appended ({len(appended)}): {' '.join(appended)}")

    if args.dry_run:
        print("Dry run: target not modified.")
        return

    # Writing into the existing file keeps its permissions (e.g. 0600 from decrypt).
    with open(args.target, "w", encoding="utf-8", newline="") as f:
        f.writelines(output)
    print(f"Overlay applied: {args.overlay} -> {args.target}")


if __name__ == "__main__":
    main()
