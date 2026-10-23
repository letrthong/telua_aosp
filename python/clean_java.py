# ==============================================================================
# Copyright (C) 2026 letrthong@gmail.com
# Created & Maintained by: letrthong@gmail.com
# Generated & Refactored by: Gemini 3.6 Pro (Google DeepMind)
# Licensed under the Apache License, Version 2.0
# ==============================================================================

import os
import sys
import subprocess

def print_help():
    """Print CLI usage helper menu."""
    help_text = """
==============================================================================
Copyright (C) 2026 letrthong@gmail.com
Clean Code Whitespace Tool for Java/Android (clean_java.py)
==============================================================================

Description:
  Scans Java source files, strips trailing whitespace & tabs, and enforces
  standard UNIX newline endings.

Usage:
  python clean_java.py [OPTION | FILE_PATH | DIR_PATH]

Options:
  --diff, --git-diff    (Default) Clean trailing whitespace ONLY for Git modified/added .java files.
  --all                 Recursively scan and clean ALL .java files in the current workspace.
  <file_path>           Clean trailing whitespace for a specific target .java file.
  <dir_path>            Recursively scan and clean ALL .java files inside the specified directory.
  -h, --help            Show this CLI help message and exit.

Examples:
  python clean_java.py --diff
  python clean_java.py Java_Android/examples/SingletonTemplate.java
  python clean_java.py Java_Android/examples/
  python clean_java.py --all
==============================================================================
"""
    print(help_text.strip())

def clean_whitespace_in_file(file_path):
    """Read the Java file, remove trailing whitespace/tabs from each line, and overwrite it."""
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        return False
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        cleaned_lines = []
        for line in lines:
            cleaned_line = line.rstrip() + '\n'
            cleaned_lines.append(cleaned_line)
        
        if lines and not lines[-1].endswith('\n'):
            if cleaned_lines:
                cleaned_lines[-1] = cleaned_lines[-1].rstrip('\n')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(cleaned_lines)
            
        print(f"Processed: {file_path}")
        return True
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return False

def get_git_modified_java_files():
    """Fetch all modified, added, or untracked .java files using git diff and status."""
    modified_files = set()
    try:
        # 1. Staged and unstaged modified/added files
        diff_output = subprocess.check_output(
            ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMRT"],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in diff_output.splitlines():
            line = line.strip()
            if line.endswith(".java") and os.path.isfile(line):
                modified_files.add(line)
        
        # 2. Untracked files
        status_output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in status_output.splitlines():
            line = line.strip()
            if line.startswith("??") and line.endswith(".java"):
                file_path = line[3:].strip()
                if os.path.isfile(file_path):
                    modified_files.add(file_path)
    except Exception:
        pass
    return sorted(list(modified_files))

def clean_java_files_in_directory(root_dir):
    """Recursively scan the directory to find and process all .java files."""
    count = 0
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.java'):
                file_path = os.path.join(dirpath, filename)
                if clean_whitespace_in_file(file_path):
                    count += 1
    print(f"\nDone! Cleaned whitespace for a total of {count} Java file(s).")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ["-h", "--help", "help"]:
            print_help()
        elif arg in ["--diff", "--git-diff"]:
            files = get_git_modified_java_files()
            print(f"Git Diff Mode: Found {len(files)} modified .java file(s).")
            for f in files:
                clean_whitespace_in_file(f)
            print(f"\nDone! Cleaned whitespace for {len(files)} Git modified Java file(s).")
        elif arg == "--all":
            target_directory = "."
            print(f"Full Scan Mode: Scanning directory: {os.path.abspath(target_directory)}")
            clean_java_files_in_directory(target_directory)
        elif os.path.isfile(arg):
            clean_whitespace_in_file(arg)
        elif os.path.isdir(arg):
            print(f"Scanning directory: {os.path.abspath(arg)}")
            clean_java_files_in_directory(arg)
        else:
            print(f"Error: '{arg}' is not a valid option, file, or directory!")
            print("Use 'python clean_java.py --help' to view available commands.")
    else:
        # Default behavior: Clean git diff modified files if present, otherwise clean git diff
        files = get_git_modified_java_files()
        if files:
            print(f"Git Diff Mode (Default): Found {len(files)} modified .java file(s).")
            for f in files:
                clean_whitespace_in_file(f)
            print(f"\nDone! Cleaned whitespace for {len(files)} Git modified Java file(s).")
        else:
            print("No Git modified .java files found. Use 'python clean_java.py --help' for usage options.")