TARGET_DIR="${1:-template}"
SCRIPT_DIR="$(dirname "$0")/scripts"

echo "Target documentation directory: $TARGET_DIR"
echo "Checking chapter and section file paths in metadata.json..."
python "$SCRIPT_DIR/check_sections.py" "$TARGET_DIR"
if [ $? -ne 0 ]; then
  echo "Path errors in metadata.json detected. Build aborted."
  exit 1
fi

echo "Merging docs from metadata.json..."
python "$SCRIPT_DIR/merge_docs.py" "$TARGET_DIR"

echo "Checking image paths in docs..."
python "$SCRIPT_DIR/check_docs.py" "$TARGET_DIR"
if [ $? -ne 0 ]; then
  echo "Image path errors detected. Build aborted."
  exit 1
fi

echo "Cleaning previous build..."
rm -rf "$TARGET_DIR/_build/html"

echo "Building Sphinx HTML..."
sphinx-build -b html "$TARGET_DIR" "$TARGET_DIR/_build/html"

echo "Documentation build completed successfully."