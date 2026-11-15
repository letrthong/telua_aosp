#!/usr/bin/env python3
# ==============================================================================
# plantuml_wrapper.py — Cross-platform PlantUML CLI Wrapper for Sphinx
#
# Supports:
#   1. Local plantuml executable (if found in PATH)
#   2. Local plantuml.jar (via java -jar if present)
#   3. Online PlantUML SVG/PNG generation fallback (plantuml.com)
#   4. Graceful standalone fallback (preventing Sphinx build crashes)
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

# 1x1 transparent PNG fallback for offline/error mode
EMPTY_1X1_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


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

    # Determine requested format from command line arguments
    out_format = "svg"
    args = sys.argv[1:]
    if "-tsvg" in args:
        out_format = "svg"
    elif "-tpng" in args:
        out_format = "png"
    elif "-ttxt" in args:
        out_format = "txt"
    elif "-teps" in args:
        out_format = "eps"
    else:
        # Default in plantuml CLI without -t is png
        out_format = "png"

    # 1. Try local plantuml command in PATH
    plantuml_bin = shutil.which("plantuml")
    if plantuml_bin:
        try:
            p = subprocess.run([plantuml_bin] + args, input=uml_code.encode("utf-8"), capture_output=True, timeout=25)
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
                    p = subprocess.run([java_bin, "-jar", jar] + args, input=uml_code.encode("utf-8"), capture_output=True, timeout=25)
                    if p.returncode == 0 and p.stdout:
                        sys.stdout.buffer.write(p.stdout)
                        return
                except Exception:
                    pass

    # 3. Fallback: Request rendered diagram from PlantUML public server
    try:
        encoded = encode_plantuml(uml_code)
        if not encoded:
            return
        url_format = "svg" if out_format == "svg" else "png"
        url = f"https://www.plantuml.com/plantuml/{url_format}/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Telua-Sphinx-PlantUML/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            if b"HUFFMAN" not in data and b"bad URL" not in data:
                sys.stdout.buffer.write(data)
                return
    except Exception as exc:
        pass

    # 4. Graceful standalone fallback (prevent build failure)
    if out_format == "svg":
        fallback_svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80">'
            f'<rect width="100%" height="100%" fill="#f8fafc" stroke="#94a3b8" stroke-dasharray="4" rx="6"/>'
            f'<text x="20" y="32" fill="#334155" font-family="sans-serif" font-size="12" font-weight="bold">PlantUML Diagram (Offline Mode)</text>'
            f'<text x="20" y="54" fill="#64748b" font-family="sans-serif" font-size="10">Diagram compiled without local Java / PlantUML service</text>'
            f'</svg>'
        )
        sys.stdout.buffer.write(fallback_svg.encode("utf-8"))
    else:
        sys.stdout.buffer.write(EMPTY_1X1_PNG)


if __name__ == "__main__":
    main()
