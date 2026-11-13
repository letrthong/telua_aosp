#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Contribution History:
#   - 2026-10: Thong Le <letrthong@gmail.com> (Architecture & Domain Design)
#   - 2026-10: Gemini 3.8 Pro - Google DeepMind (Implementation & Refactoring)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Encrypt / decrypt private overlay configs (apk_overlays.config, const_my_cli.config) with a password.

By default (when -i / -o are omitted), operates on private config files inside
config/overlay/ if they exist:
  - Encrypts:
      config/overlay/apk_overlays.config  -> config/overlay/enc_apk_overlays.config
      config/overlay/const_my_cli.config  -> config/overlay/enc_const_my_cli.config
  - Decrypts:
      config/overlay/enc_apk_overlays.config  -> config/overlay/apk_overlays.config
      config/overlay/enc_const_my_cli.config  -> config/overlay/const_my_cli.config

Usage:
  ./python/config_crypto.py encrypt ?              # prompt for password interactively ('?' or omit)
  ./python/config_crypto.py encrypt                # same, interactive prompt (not echoed)
  ./python/config_crypto.py encrypt 12345          # direct password argument (encrypts existing overlay configs)
  ./python/config_crypto.py decrypt ?              # prompt for password interactively
  ./python/config_crypto.py decrypt                # same, interactive prompt
  ./python/config_crypto.py decrypt 12345          # decrypt using direct password
  ./python/config_crypto.py decrypt 12345 --force  # same, overwriting existing plaintext overlay configs
  echo "12345" | ./python/config_crypto.py encrypt - # read password from stdin
  ./python/config_crypto.py encrypt 12345 -i <in> -o <out> # encrypt a specific file

Requires: python3 -m pip install cryptography
File format: base64( salt(16 bytes) || Fernet token ); key = PBKDF2-HMAC-SHA256(password, salt).
NOTE: a password given on the command line is visible in shell history and `ps`.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import os
import sys

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    sys.exit("ERROR: missing dependency. Install it with: python3 -m pip install cryptography")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR) == "python" else SCRIPT_DIR
CONFIG_DIR = os.path.join(REPO_ROOT, "config")
OVERLAY_DIR = os.path.join(CONFIG_DIR, "overlay")

PRIVATE_CONFIG_NAMES = (
    "apk_overlays.config",
    "const_my_cli.config",
)

PLAIN_FILE = os.path.join(OVERLAY_DIR, "apk_overlays.config")
ENCRYPTED_FILE = os.path.join(OVERLAY_DIR, "enc_apk_overlays.config")
DECRYPTED_FILE = os.path.join(OVERLAY_DIR, "dec_apk_overlays.config")
SALT_SIZE = 16
KDF_ITERATIONS = 600_000


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=KDF_ITERATIONS
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def write_private(path: str, data: bytes) -> None:
    # 0600 so the file is not readable by other users.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def check_paths(src: str, dst: str, force: bool) -> None:
    if not os.path.isfile(src):
        sys.exit(f"ERROR: input file not found: {src}")
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("ERROR: input and output must be different files")
    if os.path.exists(dst) and not force:
        sys.exit(f"ERROR: '{dst}' already exists (use --force to overwrite)")


def get_password(arg_password: str | None, confirm: bool = False) -> str:
    """Resolve password from direct argument, '?' interactive prompt, or '-' stdin."""
    if arg_password == "-":
        pw = sys.stdin.readline().rstrip("\r\n")
        if not pw:
            sys.exit("ERROR: empty password received from stdin")
        return pw

    if arg_password is None or arg_password in ("?", "prompt"):
        pw = getpass.getpass("Password: ")
        if confirm:
            confirm_pw = getpass.getpass("Confirm password: ")
            if pw != confirm_pw:
                sys.exit("ERROR: passwords do not match")
        if not pw:
            sys.exit("ERROR: password must not be empty")
        return pw

    if not arg_password:
        sys.exit("ERROR: password must not be empty")
    return arg_password


def encrypt_single_file(src: str, dst: str, password: str) -> None:
    with open(src, "rb") as f:
        plaintext = f.read()

    salt = os.urandom(SALT_SIZE)
    token = Fernet(derive_key(password, salt)).encrypt(plaintext)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    write_private(dst, base64.b64encode(salt + token) + b"\n")
    print(f"Encrypted: {src} -> {dst}")


def decrypt_single_file(src: str, dst: str, password: str) -> None:
    with open(src, "rb") as f:
        try:
            payload = base64.b64decode(f.read().strip(), validate=True)
        except binascii.Error:
            sys.exit(f"ERROR: input is not valid base64: {src}")
    if len(payload) <= SALT_SIZE:
        sys.exit(f"ERROR: input is too short to be an encrypted config: {src}")
    salt, token = payload[:SALT_SIZE], payload[SALT_SIZE:]

    try:
        plaintext = Fernet(derive_key(password, salt)).decrypt(token)
    except InvalidToken:
        sys.exit("ERROR: wrong password or corrupted file")

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    write_private(dst, plaintext)
    print(f"Decrypted: {src} -> {dst}")


def resolve_encrypt_targets(overlay_dir: str | None = None) -> list[tuple[str, str]]:
    """Find existing private config files (apk_overlays.config, const_my_cli.config) to encrypt."""
    base_overlay = overlay_dir or OVERLAY_DIR
    search_dirs = [base_overlay]
    if overlay_dir is None:
        search_dirs.extend([CONFIG_DIR, REPO_ROOT])

    targets: list[tuple[str, str]] = []
    for name in PRIVATE_CONFIG_NAMES:
        for d in search_dirs:
            candidate = os.path.join(d, name)
            if os.path.isfile(candidate):
                targets.append((candidate, os.path.join(d, f"enc_{name}")))
                break
    return targets


def resolve_decrypt_targets(overlay_dir: str | None = None) -> list[tuple[str, str]]:
    """Find existing encrypted private config files (enc_apk_overlays.config, enc_const_my_cli.config) to decrypt."""
    base_overlay = overlay_dir or OVERLAY_DIR
    search_dirs = [base_overlay]
    if overlay_dir is None:
        search_dirs.extend([CONFIG_DIR, REPO_ROOT])

    targets: list[tuple[str, str]] = []
    for name in PRIVATE_CONFIG_NAMES:
        enc_name = f"enc_{name}"
        for d in search_dirs:
            candidate = os.path.join(d, enc_name)
            if os.path.isfile(candidate):
                targets.append((candidate, os.path.join(d, name)))
                break
    return targets


def encrypt(args: argparse.Namespace) -> None:
    if args.input:
        src = args.input
        dst = args.output or os.path.join(os.path.dirname(src) or ".", "enc_" + os.path.basename(src))
        check_paths(src, dst, force=True)
        password = get_password(args.password, confirm=True)
        encrypt_single_file(src, dst, password)
        return

    targets = resolve_encrypt_targets(getattr(args, "dir", None))
    if not targets:
        target_dir = getattr(args, "dir", None) or OVERLAY_DIR
        sys.exit(
            f"ERROR: no private config files ({', '.join(PRIVATE_CONFIG_NAMES)}) found in {target_dir}"
        )

    for src, dst in targets:
        check_paths(src, dst, force=True)

    password = get_password(args.password, confirm=True)
    for src, dst in targets:
        encrypt_single_file(src, dst, password)


def decrypt(args: argparse.Namespace) -> None:
    if args.input:
        src = args.input
        if args.output:
            dst = args.output
        else:
            base = os.path.basename(src)
            plain_name = base[4:] if base.startswith("enc_") else f"dec_{base}"
            dst = os.path.join(os.path.dirname(src) or ".", plain_name)
        check_paths(src, dst, args.force)
        password = get_password(args.password, confirm=False)
        decrypt_single_file(src, dst, password)
        return

    targets = resolve_decrypt_targets(getattr(args, "dir", None))
    if not targets:
        target_dir = getattr(args, "dir", None) or OVERLAY_DIR
        enc_names = ", ".join(f"enc_{n}" for n in PRIVATE_CONFIG_NAMES)
        sys.exit(f"ERROR: no encrypted private config files ({enc_names}) found in {target_dir}")

    for src, dst in targets:
        check_paths(src, dst, args.force)

    password = get_password(args.password, confirm=False)
    for src, dst in targets:
        decrypt_single_file(src, dst, password)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func in (("encrypt", encrypt), ("decrypt", decrypt)):
        p = sub.add_parser(name)
        p.add_argument("password", nargs="?", help="password, '?' to prompt interactively, '-' for stdin, or omit")
        p.add_argument("-i", "--input", help="explicit input file (optional; defaults to config/overlay/ private files)")
        p.add_argument("-o", "--output", help="explicit output file (optional)")
        p.add_argument("-d", "--dir", help="override overlay directory to scan (default: config/overlay)")
        p.add_argument("--force", action="store_true", help="overwrite existing output")
        p.set_defaults(func=func)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
