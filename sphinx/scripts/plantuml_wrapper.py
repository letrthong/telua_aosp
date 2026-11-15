#!/usr/bin/env python3
# ==============================================================================
# plantuml_wrapper.py — Cross-platform PlantUML CLI Wrapper for Sphinx
#
# Supports:
#   1. Local plantuml executable (if found in PATH)
#   2. Local plantuml.jar (via java -jar if present)
#   3. Online PlantUML SVG generation fallback (plantuml.com)
# ==============================================================================

import base64
import os
import shutil
import subprocess
import sys
import urllib.request
import zlib

PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
STANDARD_BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
TRANSLATE_TO_PLANTUML = str.maketrans(STANDARD_BASE64_ALPHABET, PLANTUML_ALPHABET)


def encode_plantuml(text: str) -> str:
    """Encode PlantUML code into official PlantUML URL format."""
    clean_text = text.strip()
    if not clean_text:
        return ""
    if not clean_text.startswith("@startuml"):
        clean_text = f"@startuml\n{clean_text}\n@enduml"
    utf8_bytes = clean_text.encode("utf-8")
    compressed = zlib.compress(utf8_bytes, level=9)[2:-4]
    b64 = base64.b64encode(compressed).decode("ascii").rstrip("=")
    return b64.translate(TRANSLATE_TO_PLANTUML)


def main():
    uml_code = sys.stdin.read()
    if not uml_code.strip():
        return

    # 1. Try local plantuml command in PATH
    plantuml_bin = shutil.which("plantuml")
    if plantuml_bin:
        try:
            p = subprocess.run([plantuml_bin] + sys.argv[1:], input=uml_code.encode("utf-8"), capture_output=True, timeout=20)
            if p.returncode == 0 and p.stdout:
                sys.stdout.buffer.write(p.stdout)
                return
        except Exception:
            pass

    # 2. Try java -jar plantuml.jar if java exists
    java_bin = shutil.which("java")
    if java_bin:
        jar_candidates = [
            os.environ.get("PLANTUML_JAR", ""),
            "/usr/share/plantuml/plantuml.jar",
            "/usr/local/share/plantuml/plantuml.jar",
            os.path.expanduser("~/.local/share/plantuml/plantuml.jar"),
        ]
        for jar in jar_candidates:
            if jar and os.path.isfile(jar):
                try:
                    p = subprocess.run([java_bin, "-jar", jar] + sys.argv[1:], input=uml_code.encode("utf-8"), capture_output=True, timeout=20)
                    if p.returncode == 0 and p.stdout:
                        sys.stdout.buffer.write(p.stdout)
                        return
                except Exception:
                    pass

    # 3. Fallback: Request SVG directly from PlantUML standard server
    try:
        encoded = encode_plantuml(uml_code)
        if not encoded:
            return
        url = f"https://www.plantuml.com/plantuml/svg/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Telua-Sphinx-PlantUML/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            svg_data = resp.read()
            if b"HUFFMAN" not in svg_data and b"bad URL" not in svg_data:
                sys.stdout.buffer.write(svg_data)
                return
    except Exception as exc:
        # Produce a fallback visible SVG with error notice
        error_msg = str(exc).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        fallback_svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80">'
            f'<rect width="100%" height="100%" fill="#fee2e2" stroke="#ef4444" rx="4"/>'
            f'<text x="20" y="30" fill="#991b1b" font-family="sans-serif" font-size="12" font-weight="bold">PlantUML Render Notice</text>'
            f'<text x="20" y="55" fill="#7f1d1d" font-family="sans-serif" font-size="10">{error_msg[:60]}</text>'
            f'</svg>'
        )
        sys.stdout.buffer.write(fallback_svg.encode("utf-8"))


if __name__ == "__main__":
    main()
