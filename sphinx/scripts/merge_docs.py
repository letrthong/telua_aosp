import json
import os
import sys

def main():
    base_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    metadata_file = os.path.join(base_dir, 'metadata.json')

    if not os.path.isfile(metadata_file):
        print(f"Error: metadata.json not found in {base_dir}")
        sys.exit(1)

    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    for chapter_info in metadata:
        chapter_name = chapter_info['chapter']
        chapter_file = os.path.join(base_dir, chapter_name)
        data_list = chapter_info.get('dataList', [])
        if not os.path.exists(chapter_file):
            print(f'Chapter file {chapter_file} not found.')
            continue

        with open(chapter_file, 'r', encoding='utf-8') as f:
            chapter_lines = f.readlines()

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

        merged_sections = []
        for section in data_list:
            section_rel = os.path.normpath(section['filePath'])
            section_path = os.path.join(base_dir, section_rel)
            if os.path.exists(section_path):
                with open(section_path, 'r', encoding='utf-8') as f:
                    merged_sections.append(f'.. Section: {section_rel}\n')
                    merged_sections.append(f.read())
            else:
                merged_sections.append(f'.. Section file {section_rel} not found.\n')

        new_chapter_lines = (
            chapter_lines[:start_idx+1]
            + ['\n']
            + ['\n'.join(merged_sections)]
            + ['\n']
            + chapter_lines[end_idx:]
        )

        with open(chapter_file, 'w', encoding='utf-8') as f:
            f.writelines(new_chapter_lines)

    print('Merging completed.')

if __name__ == '__main__':
    main()
