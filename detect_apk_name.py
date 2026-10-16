import sys
import re

def resolve_android_bp(filepath):
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Tìm tất cả module android_app và lấy name
        pattern = r'android_app\s*\{([^}]*(?:\{[^}]*\}[^}]*)*?)\n\}'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for block in matches:
            name_match = re.search(r'name:\s*"([^"]+)"', block)
            if name_match:
                print(name_match.group(1))

    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        resolve_android_bp(sys.argv[1])
    else:
        print("Usage: python parser_name.py Android.bp")
