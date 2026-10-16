#!/usr/bin/env python3
# ==============================================================================
# Unit tests for config_overlay.py
# ==============================================================================

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
OVERLAY_SCRIPT = os.path.join(REPO_ROOT, "config_overlay.py")

# Ensure repo root is in python path
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_overlay


class TestConfigOverlay(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="telua_test_overlay_")
        self.target_file = os.path.join(self.test_dir, "target.config")
        self.overlay_file = os.path.join(self.test_dir, "overlay.config")

        self.initial_target = """# Target header
ACTIVE_PROJECT="oem_service"

case "$ACTIVE_PROJECT" in
    "oem_service")
        MODULE_NAME="OemService"
        APK_FILE_NAME="OemService.apk"
        ;;
    "car_audio")
        MODULE_NAME="CarAudioService"
        APK_FILE_NAME="CarAudioService.apk"
        ;;
    *)
        echo "Unknown"
        ;;
esac

BUILD_JOBS="8"
ENABLE_RAM_MONITOR="false"
"""
        with open(self.target_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.initial_target)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_top_level_replacement_inplace(self):
        """Test replacing top-level variables (e.g. ACTIVE_PROJECT, BUILD_JOBS) in-place."""
        overlay_content = """ACTIVE_PROJECT="car_audio"
BUILD_JOBS="16"
"""
        with open(self.overlay_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(overlay_content)

        res = subprocess.run(
            [sys.executable, OVERLAY_SCRIPT, self.target_file, self.overlay_file],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Error: {res.stderr}")

        with open(self.target_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('ACTIVE_PROJECT="car_audio"', content)
        self.assertIn('BUILD_JOBS="16"', content)
        self.assertNotIn('BUILD_JOBS="8"', content)

    def test_case_branch_replacement_and_addition(self):
        """Test updating an existing case branch and adding a new custom branch before *)"""
        overlay_content = """case "$ACTIVE_PROJECT" in
    "oem_service")
        MODULE_NAME="OemServiceCustom"
        APK_FILE_NAME="OemServiceCustom.apk"
        ;;
    "new_project")
        MODULE_NAME="NewProject"
        APK_FILE_NAME="NewProject.apk"
        ;;
esac
"""
        with open(self.overlay_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(overlay_content)

        res = subprocess.run(
            [sys.executable, OVERLAY_SCRIPT, self.target_file, self.overlay_file],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Error: {res.stderr}")

        with open(self.target_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Existing branch replaced
        self.assertIn('MODULE_NAME="OemServiceCustom"', content)
        # Other existing branch untouched
        self.assertIn('MODULE_NAME="CarAudioService"', content)
        # New branch added
        self.assertIn('"new_project")', content)
        self.assertIn('MODULE_NAME="NewProject"', content)

        # Ensure new_project is inserted BEFORE *)
        pos_new = content.find('"new_project")')
        pos_star = content.find('*)')
        self.assertTrue(pos_new < pos_star, "New branch must be before *)")

    def test_multiline_array_and_appended_keys(self):
        """Test multi-line array and appending unmatched keys to the end."""
        overlay_content = """CUSTOM_PIPELINE=(
    "adb root"
    "adb remount"
)
UNSEEN_KEY="custom_value"
"""
        with open(self.overlay_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(overlay_content)

        res = subprocess.run(
            [sys.executable, OVERLAY_SCRIPT, self.target_file, self.overlay_file],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Error: {res.stderr}")

        with open(self.target_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("CUSTOM_PIPELINE=(", content)
        self.assertIn('"adb root"', content)
        self.assertIn('UNSEEN_KEY="custom_value"', content)

    def test_dry_run_does_not_modify_file(self):
        """Test --dry-run shows changes without altering the target file."""
        overlay_content = 'BUILD_JOBS="99"\n'
        with open(self.overlay_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(overlay_content)

        res = subprocess.run(
            [sys.executable, OVERLAY_SCRIPT, self.target_file, self.overlay_file, "--dry-run"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Dry run", res.stdout)

        with open(self.target_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, self.initial_target)


if __name__ == "__main__":
    unittest.main()
