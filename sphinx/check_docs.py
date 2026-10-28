import json
import os
import re
import sys

METADATA_FILE = 'metadata.json'

# Regex để tìm directive image trong file rst
IMAGE_REGEX = re.compile(r'^\s*\.\.\s*image::\s*(.+)$', re.MULTILINE)

def check_image_paths_in_rst(rst_path):
    errors = []
    if not os.path.exists(rst_path):
        return []  # Không báo lỗi nếu file section không tồn tại (tránh báo nhầm)
    with open(rst_path, 'r', encoding='utf-8') as f:
        content = f.read()
    for match in IMAGE_REGEX.finditer(content):
        img_path = match.group(1).strip()
        # Chuẩn hóa đường dẫn tương đối
        abs_img_path = os.path.normpath(os.path.join(os.path.dirname(rst_path), img_path))
        if not os.path.isfile(abs_img_path):
            errors.append(f'{rst_path}: Image not found: {img_path}')
    return errors

def main():
    with open(METADATA_FILE, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    all_errors = []
    for chapter in metadata:
        chapter_file = chapter['chapter']
        # Kiểm tra file chương chính
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
