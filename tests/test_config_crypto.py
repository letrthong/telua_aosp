#!/usr/bin/env python3
# ==============================================================================
# Unit tests for config_crypto.py
# ==============================================================================

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CRYPTO_SCRIPT = os.path.join(REPO_ROOT, "python", "config_crypto.py")

# Ensure repo root and python/ subdir are in python path
for p in (REPO_ROOT, os.path.join(REPO_ROOT, "python")):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import cryptography
    import config_crypto
    HAS_CRYPTOGRAPHY = True
except (ImportError, SystemExit):
    HAS_CRYPTOGRAPHY = False


@unittest.skipUnless(HAS_CRYPTOGRAPHY, "cryptography library not installed")
class TestConfigCrypto(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="telua_test_crypto_")
        self.plain_file = os.path.join(self.test_dir, "test.config")
        self.enc_file = os.path.join(self.test_dir, "enc.config")
        self.dec_file = os.path.join(self.test_dir, "dec.config")
        self.sample_content = b'ACTIVE_PROJECT="oem_service"\nSECRET_KEY="super_secret_123"\n'

        with open(self.plain_file, "wb") as f:
            f.write(self.sample_content)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_encrypt_decrypt_roundtrip(self):
        """Test full encryption and decryption round-trip with password."""
        password = "TestPassword_2026!"

        # 1. Encrypt
        cmd_enc = [
            sys.executable,
            CRYPTO_SCRIPT,
            "encrypt",
            password,
            "-i",
            self.plain_file,
            "-o",
            self.enc_file,
        ]
        res_enc = subprocess.run(cmd_enc, capture_output=True, text=True)
        self.assertEqual(res_enc.returncode, 0, f"Encrypt failed: {res_enc.stderr}")
        self.assertTrue(os.path.exists(self.enc_file))

        # Encrypted file should not contain plaintext secret
        with open(self.enc_file, "rb") as f:
            enc_data = f.read()
        self.assertNotIn(b"super_secret_123", enc_data)

        # 2. Decrypt
        cmd_dec = [
            sys.executable,
            CRYPTO_SCRIPT,
            "decrypt",
            password,
            "-i",
            self.enc_file,
            "-o",
            self.dec_file,
            "--force",
        ]
        res_dec = subprocess.run(cmd_dec, capture_output=True, text=True)
        self.assertEqual(res_dec.returncode, 0, f"Decrypt failed: {res_dec.stderr}")
        self.assertTrue(os.path.exists(self.dec_file))

        # Content must match original
        with open(self.dec_file, "rb") as f:
            dec_content = f.read()
        self.assertEqual(dec_content, self.sample_content)

    def test_decrypt_wrong_password_fails(self):
        """Test decryption with wrong password fails with error."""
        password = "CorrectPassword123"
        wrong_password = "WrongPassword999"

        # Encrypt first
        cmd_enc = [
            sys.executable,
            CRYPTO_SCRIPT,
            "encrypt",
            password,
            "-i",
            self.plain_file,
            "-o",
            self.enc_file,
        ]
        subprocess.run(cmd_enc, check=True, capture_output=True)

        # Decrypt with wrong password
        cmd_dec = [
            sys.executable,
            CRYPTO_SCRIPT,
            "decrypt",
            wrong_password,
            "-i",
            self.enc_file,
            "-o",
            self.dec_file,
            "--force",
        ]
        res_dec = subprocess.run(cmd_dec, capture_output=True, text=True)
        self.assertNotEqual(res_dec.returncode, 0)
        self.assertIn("wrong password", res_dec.stderr.lower())

    def test_key_derivation_salt_randomness(self):
        """Test that different random salts produce different keys for same password."""
        salt1 = os.urandom(16)
        salt2 = os.urandom(16)
        key1 = config_crypto.derive_key("same_password", salt1)
        key2 = config_crypto.derive_key("same_password", salt2)
        self.assertNotEqual(key1, key2)

    def test_encrypt_decrypt_overlay_directory_both_files(self):
        """Test default batch encrypt/decrypt of apk_overlays.config and const_my_cli.config in overlay dir."""
        overlay_dir = os.path.join(self.test_dir, "overlay")
        os.makedirs(overlay_dir, exist_ok=True)
        apk_ov = os.path.join(overlay_dir, "apk_overlays.config")
        my_cli = os.path.join(overlay_dir, "const_my_cli.config")
        enc_apk_ov = os.path.join(overlay_dir, "enc_apk_overlays.config")
        enc_my_cli = os.path.join(overlay_dir, "enc_const_my_cli.config")

        apk_ov_bytes = b'ACTIVE_PROJECT="private_oem"\n'
        my_cli_bytes = b'MY_GROUP_LIST=("secret :: private cmd")\n'
        with open(apk_ov, "wb") as f:
            f.write(apk_ov_bytes)
        with open(my_cli, "wb") as f:
            f.write(my_cli_bytes)

        password = "OverlaySecretPassword_2026!"

        # 1. Encrypt both existing private files in overlay_dir
        res_enc = subprocess.run(
            [sys.executable, CRYPTO_SCRIPT, "encrypt", password, "-d", overlay_dir],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_enc.returncode, 0, f"Batch encrypt failed: {res_enc.stderr}")
        self.assertTrue(os.path.isfile(enc_apk_ov))
        self.assertTrue(os.path.isfile(enc_my_cli))

        # Remove plaintext files to simulate fresh clone
        os.remove(apk_ov)
        os.remove(my_cli)

        # 2. Decrypt both encrypted files back in overlay_dir
        res_dec = subprocess.run(
            [sys.executable, CRYPTO_SCRIPT, "decrypt", password, "-d", overlay_dir, "--force"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_dec.returncode, 0, f"Batch decrypt failed: {res_dec.stderr}")
        self.assertTrue(os.path.isfile(apk_ov))
        self.assertTrue(os.path.isfile(my_cli))
        with open(apk_ov, "rb") as f:
            self.assertEqual(f.read(), apk_ov_bytes)
        with open(my_cli, "rb") as f:
            self.assertEqual(f.read(), my_cli_bytes)

    def test_encrypt_overlay_directory_partial_and_empty(self):
        """Test that batch encrypt works when only one file exists and fails cleanly when none exist."""
        overlay_dir = os.path.join(self.test_dir, "overlay_partial")
        os.makedirs(overlay_dir, exist_ok=True)

        # Empty directory -> should fail cleanly
        res_empty = subprocess.run(
            [sys.executable, CRYPTO_SCRIPT, "encrypt", "pw123", "-d", overlay_dir],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res_empty.returncode, 0)
        self.assertIn("no private config files", res_empty.stderr.lower())

        # Only apk_overlays.config exists -> should encrypt only apk_overlays.config
        apk_ov = os.path.join(overlay_dir, "apk_overlays.config")
        with open(apk_ov, "wb") as f:
            f.write(b'BUILD_JOBS="16"\n')

        res_one = subprocess.run(
            [sys.executable, CRYPTO_SCRIPT, "encrypt", "pw123", "-d", overlay_dir],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_one.returncode, 0, f"Single overlay encrypt failed: {res_one.stderr}")
        self.assertTrue(os.path.isfile(os.path.join(overlay_dir, "enc_apk_overlays.config")))
        self.assertFalse(os.path.isfile(os.path.join(overlay_dir, "enc_const_my_cli.config")))


if __name__ == "__main__":
    unittest.main()
