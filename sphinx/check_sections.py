import json
import os

METADATA_FILE = 'metadata.json'

def main():
    with open(METADATA_FILE, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    errors = []
    for chapter in metadata:
        chapter_file = chapter.get('chapter')
        if not os.path.isfile(chapter_file):
            errors.append(f'Chapter file not found: {chapter_file}')
        for section in chapter.get('dataList', []):
            section_file = section['filePath']
            if not os.path.isfile(section_file):
                errors.append(f'Section file not found: {section_file}')
    if errors:
        print('File path errors found:')
        for err in errors:
            print(' -', err)
        exit(1)
    else:
        print('All chapter and section file paths are valid.')
        exit(0)

if __name__ == '__main__':
    main()
