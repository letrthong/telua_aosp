import json
import os
import re
import sys

# Regex để tìm directive image trong file rst
IMAGE_REGEX = re.compile(r'^\s*\.\.\s*image::\s*(.+)$', re.MULTILINE)

def check_image_paths_in_rst(rst_path):
    errors = []
    if not os.path.exists(rst_path):
        return []
    with open(rst_path, 'r', encoding='utf-8') as f:
        content = f.read()
    for match in IMAGE_REGEX.finditer(content):
        img_path = match.group(1).strip()
        abs_img_path = os.path.normpath(os.path.join(os.path.dirname(rst_path), img_path))
        if not os.path.isfile(abs_img_path):
            errors.append(f'{rst_path}: Image not found: {img_path}')
    return errors

def main():
    base_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    metadata_file = os.path.join(base_dir, 'metadata.json')

    if not os.path.isfile(metadata_file):
        print(f"Error: metadata.json not found in {base_dir}")
        sys.exit(1)

    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    all_errors = []
    for chapter in metadata:
        chapter_file = os.path.join(base_dir, chapter['chapter'])
        all_errors.extend(check_image_paths_in_rst(chapter_file))
    if all_errors:
        print('Image path errors found:')
        for err in all_errors:
            print(' -', err)
        sys.exit(1)
    else:
        print('All image paths are valid.')
        sys.exit(0)

if __name__ == '__main__':
    main()
