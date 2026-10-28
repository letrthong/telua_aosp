import json
import os

# Đường dẫn file metadata.json
METADATA_FILE = 'metadata.json'

# Đọc metadata.json
with open(METADATA_FILE, 'r', encoding='utf-8') as f:
    metadata = json.load(f)


for chapter_info in metadata:
    chapter_file = chapter_info['chapter']
    data_list = chapter_info.get('dataList', [])
    if not os.path.exists(chapter_file):
        print(f'Chapter file {chapter_file} not found.')
        continue

    # Đọc nội dung file chương
    with open(chapter_file, 'r', encoding='utf-8') as f:
        chapter_lines = f.readlines()


    # Xác định vị trí marker (có hoặc không có dấu cách)
    start_markers = ['..@created_docs_from_metadata.json start', '.. @created_docs_from_metadata.json start']
    end_markers = ['..@created_docs_from_metadata.json end', '.. @created_docs_from_metadata.json end']
    start_idx = None
    end_idx = None
    for idx, line in enumerate(chapter_lines):
        for sm in start_markers:
            if sm in line:
                start_idx = idx
        for em in end_markers:
            if em in line:
                end_idx = idx

    if start_idx is None or end_idx is None or start_idx >= end_idx:
        print(f'Markers not found or invalid in {chapter_file}.')
        continue

    # Tạo nội dung sections
    merged_sections = []
    for section in data_list:
        section_path = os.path.normpath(section['filePath'])
        if os.path.exists(section_path):
            with open(section_path, 'r', encoding='utf-8') as f:
                merged_sections.append(f'.. Section: {section_path}\n')
                merged_sections.append(f.read())
        else:
            merged_sections.append(f'.. Section file {section_path} not found.\n')

    # Luôn ghi đè nội dung giữa hai marker (xóa sạch phần cũ)
    new_chapter_lines = (
        chapter_lines[:start_idx+1]
        + ['\n']
        + ['\n'.join(merged_sections)]
        + ['\n']
        + chapter_lines[end_idx:]
    )

    # Ghi đè lại file chương
    with open(chapter_file, 'w', encoding='utf-8') as f:
        f.writelines(new_chapter_lines)

print('Merging completed.')
