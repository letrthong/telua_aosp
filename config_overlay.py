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
  - Top-level KEY=value (or multi-line arrays KEY=( ... )) in the overlay:
      * every top-level KEY= in the target is replaced in place;
      * keys with no top-level assignment in the target are appended at the end.
    If a key repeats in the overlay, the last one wins.
  - case blocks (e.g. case "$ACTIVE_PROJECT" in ... esac) are merged per branch:
      * a branch "oem_service") ... ;; replaces the branch with the same label in the
        target's case block with the same expression; other branches stay untouched;
      * a branch not present in the target is inserted before the default '*)' branch
        (or before 'esac' if there is none), so you can add your own profiles;
      * a case block whose expression does not exist in the target is appended whole.
    Labels are compared without quotes/spaces, so "oem_service") matches oem_service).
  - Comments and blank lines in the overlay are ignored.

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
CASE_START_RE = re.compile(r"^\s*case\s+(.+?)\s+in\s*(?:#.*)?$")
CASE_END_RE = re.compile(r"^\s*esac\b")
# Branch label such as:  "oem_service")   *)   a|b)   ("x")
# '=' is excluded so assignments like FOO="$(cmd)" are never taken as labels.
BRANCH_LABEL_RE = re.compile(r"^\s*\(?\s*([^()#=]+?)\s*\)")
APPEND_HEADER = "# ---- Overrides from apk_overlays.config (appended by telua init) ----"


def read_lines(path: str) -> list[str]:
    # newline="" keeps the original line endings (LF must be preserved for Linux).
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read().splitlines(keepends=True)


def strip_eol(line: str) -> str:
    return line.rstrip("\r\n")


def normalize(text: str) -> str:
    """Compare case expressions/labels without quotes or whitespace."""
    return re.sub(r"[\"'\s]", "", text)


def parse_case_blocks(lines: list[str]) -> list[dict]:
    """Find case ... esac blocks and their branches (label line through ';;')."""
    blocks = []
    i = 0
    while i < len(lines):
        match = CASE_START_RE.match(strip_eol(lines[i]))
        if not match:
            i += 1
            continue
        block = {"expr": normalize(match.group(1)), "raw_expr": match.group(1).strip(),
                 "start": i, "end": None, "branches": []}
        current = None
        j = i + 1
        while j < len(lines):
            text = strip_eol(lines[j])
            if CASE_END_RE.match(text):
                if current is not None:  # last branch without ';;'
                    current["end"] = j - 1
                    block["branches"].append(current)
                block["end"] = j
                break
            if current is None:
                label = BRANCH_LABEL_RE.match(text)
                if label:
                    current = {"label": label.group(1).strip(), "norm": normalize(label.group(1)), "start": j}
                    if ";;" in text[label.end():]:  # single-line branch: "x") FOO=1 ;;
                        current["end"] = j
                        block["branches"].append(current)
                        current = None
            elif text.strip().startswith(";;"):
                current["end"] = j
                block["branches"].append(current)
                current = None
            j += 1
        if block["end"] is None:  # no matching esac: not a usable case block
            i += 1
            continue
        blocks.append(block)
        i = block["end"] + 1
    return blocks


def case_line_indices(blocks: list[dict]) -> set[int]:
    indices: set[int] = set()
    for block in blocks:
        indices.update(range(block["start"], block["end"] + 1))
    return indices


def find_assignments(lines: list[str], allow_indent: bool, skip: set[int]) -> list[tuple[str, int, int]]:
    """Return (key, start_line, end_line) for each shell assignment; arrays may span lines."""
    result = []
    i = 0
    while i < len(lines):
        text = strip_eol(lines[i])
        if i in skip or (not allow_indent and text[:1] in (" ", "\t")):
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


def load_overlay(path: str):
    """Return (assignments: KEY -> lines, cases: expr -> {raw_expr, lines, branches: norm -> branch})."""
    lines = read_lines(path)
    blocks = parse_case_blocks(lines)

    assignments: dict[str, list[str]] = {}
    for key, start, end in find_assignments(lines, allow_indent=True, skip=case_line_indices(blocks)):
        block = [strip_eol(line) for line in lines[start:end + 1]]
        block[0] = block[0].lstrip()
        assignments.pop(key, None)  # last definition wins, and moves to the end of the order
        assignments[key] = block

    cases: dict[str, dict] = {}
    for block in blocks:
        entry = cases.setdefault(block["expr"], {"raw_expr": block["raw_expr"], "lines": [], "branches": {}})
        entry["lines"] = [strip_eol(line) for line in lines[block["start"]:block["end"] + 1]]
        for branch in block["branches"]:
            entry["branches"].pop(branch["norm"], None)
            entry["branches"][branch["norm"]] = {
                "label": branch["label"],
                "lines": [strip_eol(line) for line in lines[branch["start"]:branch["end"] + 1]],
            }
    return assignments, cases


def apply_overlay(target_lines: list[str], assignments: dict, cases: dict, newline: str):
    target_cases = parse_case_blocks(target_lines)
    skip = case_line_indices(target_cases)

    top_level: dict[str, list[tuple[int, int]]] = {}
    for key, start, end in find_assignments(target_lines, allow_indent=False, skip=skip):
        top_level.setdefault(key, []).append((start, end))

    replacements: dict[int, tuple[int, list[str]]] = {}  # start line -> (end line, new lines)
    insertions: dict[int, list[str]] = {}                # insert before line -> new lines
    report = {"replaced": [], "appended": [], "branch_replaced": [], "branch_added": [], "case_appended": []}
    appended_blocks: list[list[str]] = []

    for key, block in assignments.items():
        if key in top_level:
            for start, end in top_level[key]:
                replacements[start] = (end, block)
            report["replaced"].append(key)
        else:
            appended_blocks.append(block)
            report["appended"].append(key)

    for expr, overlay_case in cases.items():
        target = next((c for c in target_cases if c["expr"] == expr), None)
        if target is None:
            appended_blocks.append(overlay_case["lines"])
            report["case_appended"].append(overlay_case["raw_expr"])
            continue
        by_label = {b["norm"]: b for b in target["branches"]}
        default_branch = by_label.get("*")
        anchor = default_branch["start"] if default_branch else target["end"]
        for norm, branch in overlay_case["branches"].items():
            existing = by_label.get(norm)
            if existing:
                replacements[existing["start"]] = (existing["end"], branch["lines"])
                report["branch_replaced"].append(branch["label"])
            else:
                insertions.setdefault(anchor, []).extend(branch["lines"])
                report["branch_added"].append(branch["label"])

    output: list[str] = []
    i = 0
    while i < len(target_lines):
        if i in insertions:
            output.extend(line + newline for line in insertions[i])
        if i in replacements:
            end, block = replacements[i]
            output.extend(line + newline for line in block)
            i = end + 1
        else:
            output.append(target_lines[i])
            i += 1

    if appended_blocks:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += newline
        output.append(newline)
        output.append(APPEND_HEADER + newline)
        for block in appended_blocks:
            output.extend(line + newline for line in block)

    return output, report


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

    assignments, cases = load_overlay(args.overlay)
    if not assignments and not cases:
        print(f"Overlay has no KEY=value entries or case blocks, nothing to apply: {args.overlay}")
        return

    target_lines = read_lines(args.target)
    newline = "\r\n" if target_lines and target_lines[0].endswith("\r\n") else "\n"
    output, report = apply_overlay(target_lines, assignments, cases, newline)

    labels = {
        "replaced": "Replaced",
        "appended": "Appended",
        "branch_replaced": "Case branches replaced",
        "branch_added": "Case branches added",
        "case_appended": "Case blocks appended",
    }
    for name, title in labels.items():
        if report[name]:
            print(f"{title} ({len(report[name])}): {' '.join(report[name])}")

    if args.dry_run:
        print("Dry run: target not modified.")
        return

    # Writing into the existing file keeps its permissions (e.g. 0600 from decrypt).
    with open(args.target, "w", encoding="utf-8", newline="") as f:
        f.writelines(output)
    print(f"Overlay applied: {args.overlay} -> {args.target}")


if __name__ == "__main__":
    main()
