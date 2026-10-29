#!/bin/bash
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

TARGET_DIR="${1:-templates/basic}"
SCRIPT_DIR="$(dirname "$0")/scripts"

echo "Target documentation directory: $TARGET_DIR"
echo "Checking chapter and section file paths in metadata.json..."
python "$SCRIPT_DIR/check_sections.py" "$TARGET_DIR"
if [ $? -ne 0 ]; then
  echo "Path errors in metadata.json detected. Build aborted."
  exit 1
fi

STAGING_DIR="$TARGET_DIR/_build/.staging"
OUT_HTML="$TARGET_DIR/_build/html"

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

# Copy source docs into staging (exclude _build and .git)
for item in "$TARGET_DIR"/*; do
  bname="$(basename "$item")"
  if [ "$bname" != "_build" ] && [ "$bname" != ".git" ]; then
    cp -r "$item" "$STAGING_DIR/"
  fi
done

# If staging lacks conf.py, fallback to basic template conf.py
if [ ! -f "$STAGING_DIR/conf.py" ]; then
  if [ -f "$(dirname "$0")/templates/basic/conf.py" ]; then
    cp "$(dirname "$0")/templates/basic/conf.py" "$STAGING_DIR/conf.py"
  elif [ -f "$(dirname "$0")/template/conf.py" ]; then
    cp "$(dirname "$0")/template/conf.py" "$STAGING_DIR/conf.py"
  fi
fi

# Ensure custom static directory (_static) is copied into staging
if [ ! -d "$STAGING_DIR/_static" ]; then
  if [ -d "$(dirname "$0")/templates/basic/_static" ]; then
    cp -r "$(dirname "$0")/templates/basic/_static" "$STAGING_DIR/"
  elif [ -d "$(dirname "$0")/template/_static" ]; then
    cp -r "$(dirname "$0")/template/_static" "$STAGING_DIR/"
  fi
fi

echo "Merging docs from metadata.json into staging directory..."
python "$SCRIPT_DIR/merge_docs.py" "$STAGING_DIR"
if [ $? -ne 0 ]; then
  echo "Merge failed. Build aborted."
  rm -rf "$STAGING_DIR"
  exit 1
fi

echo "Checking image paths in docs..."
python "$SCRIPT_DIR/check_docs.py" "$STAGING_DIR"
if [ $? -ne 0 ]; then
  echo "Image path errors detected. Build aborted."
  rm -rf "$STAGING_DIR"
  exit 1
fi

echo "Cleaning previous build..."
rm -rf "$OUT_HTML"

echo "Building Sphinx HTML..."
sphinx-build -b html "$STAGING_DIR" "$OUT_HTML"
BUILD_STATUS=$?

# Clean up staging directory
rm -rf "$STAGING_DIR"

if [ $BUILD_STATUS -ne 0 ]; then
  echo "Sphinx build failed."
  exit $BUILD_STATUS
fi

echo "Documentation build completed successfully."