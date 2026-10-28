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
    errors = []
    for chapter in metadata:
        chapter_file = os.path.join(base_dir, chapter.get('chapter', ''))
        if not os.path.isfile(chapter_file):
            errors.append(f'Chapter file not found: {chapter.get("chapter")}')
        for section in chapter.get('dataList', []):
            section_file = os.path.join(base_dir, section['filePath'])
            if not os.path.isfile(section_file):
                errors.append(f'Section file not found: {section["filePath"]}')
    if errors:
        print('File path errors found:')
        for err in errors:
            print(' -', err)
        sys.exit(1)
    else:
        print('All chapter and section file paths are valid.')
        sys.exit(0)

if __name__ == '__main__':
    main()
