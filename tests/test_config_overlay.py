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
OVERLAY_SCRIPT = os.path.join(REPO_ROOT, "python", "config_overlay.py")

# Ensure repo root and python/ subdir are in python path
for p in (REPO_ROOT, os.path.join(REPO_ROOT, "python")):
    if p not in sys.path:
        sys.path.insert(0, p)

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

    def test_missing_overlay_or_target_path_returns_error(self):
        """Test that wrong/non-existent target or overlay paths fail with clear error."""
        bad_overlay = os.path.join(self.test_dir, "wrong_path", "apk_overlays.config")
        res = subprocess.run(
            [sys.executable, OVERLAY_SCRIPT, self.target_file, bad_overlay],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0, "Expected non-zero exit code when overlay path does not exist")
        self.assertIn("ERROR: overlay file not found", res.stderr)

        bad_target = os.path.join(self.test_dir, "wrong_path", "apk.config")
        res_target = subprocess.run(
            [sys.executable, OVERLAY_SCRIPT, bad_target, self.overlay_file],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res_target.returncode, 0, "Expected non-zero exit code when target path does not exist")
        self.assertIn("ERROR: target config not found", res_target.stderr)

    def test_repository_overlay_paths_and_code_sync(self):
        """Verify config/overlay/ paths exist and stay in sync across build_apk.sh, telua_utils.sh, and python scripts."""
        overlay_dir = os.path.join(REPO_ROOT, "config", "overlay")
        self.assertTrue(
            os.path.isdir(overlay_dir),
            f"Missing directory '{overlay_dir}'! Did someone rename or move config/overlay/?",
        )
        for fname in ("apk_overlays.config.example", "const_my_cli.config.example"):
            fpath = os.path.join(overlay_dir, fname)
            self.assertTrue(
                os.path.isfile(fpath),
                f"Missing template '{fpath}'! Code in build_apk.sh / telua_web expects it at config/overlay/{fname}.",
            )

        # Ensure build_apk.sh PERSONAL_CONFIG_FILES still references config/overlay/apk_overlays.config
        build_apk_path = os.path.join(REPO_ROOT, "build_apk.sh")
        with open(build_apk_path, "r", encoding="utf-8", errors="replace") as f:
            build_sh_text = f.read()
        self.assertIn(
            "config/overlay/apk_overlays.config",
            build_sh_text,
            "build_apk.sh is out of sync: missing 'config/overlay/apk_overlays.config' in PERSONAL_CONFIG_FILES",
        )

        # Ensure src/telua_utils.sh apply_config_overlay still checks config/overlay/apk_overlays.config
        utils_path = os.path.join(REPO_ROOT, "src", "telua_utils.sh")
        with open(utils_path, "r", encoding="utf-8", errors="replace") as f:
            utils_text = f.read()
        self.assertIn(
            'overlay_name="apk_overlays.config"',
            utils_text,
            "src/telua_utils.sh is out of sync: overlay_name='apk_overlays.config' was changed without updating tests",
        )
        self.assertIn(
            "config/overlay/$overlay_name",
            utils_text,
            "src/telua_utils.sh is out of sync: missing 'config/overlay/$overlay_name' lookup path",
        )

    def test_real_apk_overlays_config_syntax_and_merge(self):
        """Validate real config/overlay/apk_overlays.config (if present) merges cleanly with config/apk.config."""
        master_apk = os.path.join(REPO_ROOT, "config", "apk.config")
        self.assertTrue(os.path.isfile(master_apk), f"Master template not found: {master_apk}")

        candidates = [
            os.path.join(REPO_ROOT, "config", "overlay", "apk_overlays.config.example"),
            os.path.join(REPO_ROOT, "config", "overlay", "apk_overlays.config"),
        ]
        for ov_path in candidates:
            if not os.path.isfile(ov_path):
                continue
            merged_target = os.path.join(self.test_dir, "merged_apk.config")
            shutil.copyfile(master_apk, merged_target)
            res = subprocess.run(
                [sys.executable, OVERLAY_SCRIPT, merged_target, ov_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                res.returncode,
                0,
                f"Failed to merge {ov_path} into {master_apk}: {res.stderr}",
            )
            with open(merged_target, "r", encoding="utf-8", errors="replace") as f:
                merged_text = f.read()
            # Every profile branch in merged apk.config must define the 4 required variables
            _, cases = config_overlay.load_overlay(ov_path)
            for case_block in cases.values():
                for label, branch_info in case_block["branches"].items():
                    if label == "*":
                        continue
                    branch_body = "\n".join(branch_info["lines"])
                    for req_var in (
                        "SOURCE_CODE_RELATIVE_PATH",
                        "APK_OUTPUT_RELATIVE_PATH",
                        "APK_FILE_NAME",
                        "APK_DEPLOY_PATH",
                    ):
                        self.assertIn(
                            f"{req_var}=",
                            branch_body,
                            f"Profile '{label}' in {ov_path} is missing required path variable '{req_var}='!",
                        )

    def test_fresh_clone_without_apk_overlays_config_until_init(self):
        """Simulate a fresh git clone where apk_overlays.config does not exist until init/web start creates it from .example."""
        sim_root = os.path.join(self.test_dir, "fresh_clone")
        sim_cfg = os.path.join(sim_root, "config")
        sim_ov = os.path.join(sim_cfg, "overlay")
        os.makedirs(sim_ov, exist_ok=True)

        # Copy tracked files only (.example and master apk.config), no apk_overlays.config yet
        shutil.copyfile(os.path.join(REPO_ROOT, "config", "apk.config"), os.path.join(sim_cfg, "apk.config"))
        shutil.copyfile(
            os.path.join(REPO_ROOT, "config", "overlay", "apk_overlays.config.example"),
            os.path.join(sim_ov, "apk_overlays.config.example"),
        )
        plain_ov = os.path.join(sim_ov, "apk_overlays.config")
        self.assertFalse(os.path.exists(plain_ov), "Fresh clone must not have apk_overlays.config before init")

        # Simulate init / web startup creating apk_overlays.config from .example
        shutil.copyfile(os.path.join(sim_ov, "apk_overlays.config.example"), plain_ov)
        self.assertTrue(os.path.isfile(plain_ov))

        # Verify merging the newly initialized apk_overlays.config onto apk.config succeeds
        res = subprocess.run(
            [sys.executable, OVERLAY_SCRIPT, os.path.join(sim_cfg, "apk.config"), plain_ov],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Merge after fresh init failed: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
