echo "Checking chapter and section file paths in metadata.json..."
python check_sections.py
if [ $? -ne 0 ]; then
  echo "Path errors in metadata.json detected. Build aborted."
  exit 1
fi

echo "Merging docs from metadata.json..."
python merge_docs.py

echo "Checking image paths in docs..."
python check_docs.py
if [ $? -ne 0 ]; then
  echo "Image path errors detected. Build aborted."
  exit 1
fi

echo "Cleaning previous build..."
rm -rf _build/html

echo "Building Sphinx HTML..."
sphinx-build -b html . _build/html

echo "Documentation build completed successfully."