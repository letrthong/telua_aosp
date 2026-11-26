#!/usr/bin/env python3
# ==============================================================================
# Unit tests for web/telua_web_core.py, web/telua_web_pipelines.py, and web/telua_web.py
# ==============================================================================

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
WEB_DIR = os.path.join(REPO_ROOT, "web")

for p in (REPO_ROOT, WEB_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import telua_web_core  # noqa: E402
import telua_web_pipelines  # noqa: E402

try:
    import flask  # noqa: F401
    import telua_web  # noqa: E402
    HAS_FLASK = True
except (ImportError, SystemExit):
    HAS_FLASK = False


class TestTeluaWebCore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="telua_test_web_core_"))
        (self.tmp_dir / "config" / "overlay").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_is_editable_name(self):
        self.assertTrue(telua_web_core.is_editable_name("apk.config"))
        self.assertTrue(telua_web_core.is_editable_name("const_system_cli.config"))
        self.assertTrue(telua_web_core.is_editable_name("settings.json"))
        self.assertTrue(telua_web_core.is_editable_name("dec_apk_overlays.config"))
        self.assertFalse(telua_web_core.is_editable_name("enc_apk_overlays.config"))
        self.assertFalse(telua_web_core.is_editable_name("apk.config.bak"))
        self.assertFalse(telua_web_core.is_editable_name("readme.txt"))

    def test_ensure_overlay_configs_creates_from_example_without_overwriting(self):
        ov = self.tmp_dir / "config" / "overlay"
        (ov / "apk_overlays.config.example").write_text("# example overlay\n", encoding="utf-8")
        (ov / "const_my_cli.config.example").write_text("# example my cli\n", encoding="utf-8")

        telua_web_core.ensure_overlay_configs(self.tmp_dir)
        self.assertTrue((ov / "apk_overlays.config").is_file())
        self.assertTrue((ov / "const_my_cli.config").is_file())

        # Modify apk_overlays.config and ensure subsequent calls never overwrite it
        (ov / "apk_overlays.config").write_text("# custom user edit\n", encoding="utf-8")
        telua_web_core.ensure_overlay_configs(self.tmp_dir)
        self.assertEqual(
            (ov / "apk_overlays.config").read_text(encoding="utf-8"),
            "# custom user edit\n",
        )

    def test_scan_files_ordering_and_filtering(self):
        (self.tmp_dir / "config" / "apk.config").write_text("ACTIVE_PROJECT=\"demo\"\n", encoding="utf-8")
        (self.tmp_dir / "config" / "const_system_cli.config").write_text("SYSTEM_GROUP_LIST=()\n", encoding="utf-8")
        (self.tmp_dir / "config" / "overlay" / "enc_apk_overlays.config").write_text("secret", encoding="utf-8")
        (self.tmp_dir / "config" / "apk.config.bak").write_text("backup", encoding="utf-8")

        entries = telua_web_core.scan_files_in_root(self.tmp_dir)
        names = [e["name"] for e in entries]
        self.assertEqual(names[0], "config/apk.config")
        self.assertIn("config/const_system_cli.config", names)
        self.assertNotIn("config/overlay/enc_apk_overlays.config", names)
        self.assertNotIn("config/apk.config.bak", names)

    def test_parse_version_and_profiles(self):
        build_sh = self.tmp_dir / "build_apk.sh"
        build_sh.write_text('#!/bin/bash\nSCRIPT_VERSION="2.11.0"\n', encoding="utf-8")
        self.assertEqual(telua_web_core.parse_version_from_file(build_sh), "2.11.0")

        apk_cfg = self.tmp_dir / "config" / "apk.config"
        apk_cfg.write_text(
            'ACTIVE_PROJECT="proj_a"\n'
            'case "$ACTIVE_PROJECT" in\n'
            '    "proj_a")\n'
            '        ;;\n'
            '    "proj_b")\n'
            '        ;;\n'
            '    *)\n'
            '        ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        self.assertEqual(telua_web_core.parse_active_project_from_file(apk_cfg), "proj_a")
        self.assertEqual(telua_web_core.parse_profiles_from_file(apk_cfg), ["proj_a", "proj_b"])

    def test_ram_info_parsing(self):
        meminfo = self.tmp_dir / "meminfo"
        meminfo.write_text(
            "MemTotal:       16777216 kB\n"
            "MemFree:         4194304 kB\n"
            "MemAvailable:    8388608 kB\n"
            "SwapTotal:       2097152 kB\n",
            encoding="utf-8",
        )
        info = telua_web_core.ram_info(meminfo)
        self.assertIsNotNone(info)
        self.assertEqual(info["total_gb"], 16.0)
        self.assertEqual(info["available_gb"], 8.0)
        self.assertEqual(info["used_gb"], 8.0)
        self.assertEqual(info["used_pct"], 50)
        self.assertEqual(info["swap_total_gb"], 2.0)


class TestTeluaWebPipelines(unittest.TestCase):
    def test_parse_and_rewrite_array_pipelines(self):
        sample = [
            "#!/bin/bash",
            "# Header comment",
            "SYSTEM_GROUP_LIST=(",
            '    "ram             :: Show system RAM"',
            '    "docker-status   :: Check Docker status"',
            ")",
            "",
            "SYSTEM_CMD_RAM=(",
            '    "free -h"',
            ")",
            "",
            "SYSTEM_CMD_DOCKER_STATUS=(",
            '    "systemctl status docker --no-pager"',
            '    "docker ps -a"',
            ")",
        ]
        parsed = telua_web_pipelines.parse_array_pipelines(sample, prefix="SYSTEM")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["name"], "ram")
        self.assertEqual(parsed[0]["array"], "SYSTEM_CMD_RAM")
        self.assertEqual(parsed[0]["steps"], ["free -h"])
        self.assertEqual(parsed[1]["name"], "docker-status")
        self.assertEqual(parsed[1]["array"], "SYSTEM_CMD_DOCKER_STATUS")
        self.assertEqual(len(parsed[1]["steps"]), 2)

        # Add a new pipeline and rewrite
        parsed.append({
            "name": "ssh-pub",
            "description": "Print SSH public key",
            "steps": ["cat ~/.ssh/id_ed25519.pub"],
        })
        rewritten = telua_web_pipelines.rewrite_array_pipeline_lines(sample, parsed, prefix="SYSTEM")
        reparsed = telua_web_pipelines.parse_array_pipelines(rewritten, prefix="SYSTEM")
        self.assertEqual([p["name"] for p in reparsed], ["ram", "docker-status", "ssh-pub"])
        self.assertEqual(reparsed[2]["steps"], ["cat ~/.ssh/id_ed25519.pub"])

    def test_parse_and_rewrite_cli_list_pipelines(self):
        sample = [
            'ADB_SHELL_CAR_VOL_UP="cmd car_service inject-key 24"',
            'CAR_CLI_LIST=(',
            '    "vol-up             :: Volume Up                                    :: $ADB_SHELL_CAR_VOL_UP"',
            ')',
        ]
        parsed = telua_web_pipelines._parse_cli_list_pipelines(sample, "CAR_CLI_LIST", "ADB_SHELL_CAR_")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "vol-up")
        self.assertEqual(parsed[0]["steps"], ["cmd car_service inject-key 24"])

        parsed[0]["steps"] = ["cmd car_service inject-key 24 --repeat 2"]
        rewritten = telua_web_pipelines._rewrite_cli_list_lines(sample, parsed, "CAR_CLI_LIST", "ADB_SHELL_CAR_")
        reparsed = telua_web_pipelines._parse_cli_list_pipelines(rewritten, "CAR_CLI_LIST", "ADB_SHELL_CAR_")
        self.assertEqual(reparsed[0]["steps"], ["cmd car_service inject-key 24 --repeat 2"])


@unittest.skipUnless(HAS_FLASK, "Flask not installed in current Python environment")
class TestTeluaWebFlaskRoutes(unittest.TestCase):
    def setUp(self):
        self.client = telua_web.app.test_client()

    def test_api_ping(self):
        res = self.client.get("/api/ping")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["tool"], "telua_web")

    def test_static_js_modular_scripts(self):
        scripts = [
            "core.js", "tab_files.js", "tab_pipelines.js", "tab_terminal.js",
            "tab_docs.js", "tab_aosp.js", "tab_logcat.js", "tab_mirror.js", "tab_power.js", "tab_bi.js", "app.js",
        ]
        for s in scripts:
            res = self.client.get(f"/static/js/{s}")
            self.assertEqual(res.status_code, 200, f"/static/js/{s} returned {res.status_code}")
            self.assertGreater(len(res.data), 100, f"/static/js/{s} is too small")
            res.close()

    def test_api_status_and_adb_remote_script(self):
        # 1. Test /api/status returns adb_remote_script info
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("adb_devices", data)
        self.assertIn("adb_remote_script", data)
        self.assertTrue(data["adb_remote_script"]["exists"])
        self.assertTrue(data["adb_remote_script"]["path"].endswith("adb_remote_pc.bat"))
        self.assertEqual(data["adb_remote_script"]["download_url"], "/api/adb/remote-script")

        # 2. Test /api/adb/remote-script downloads adb_remote_pc.bat
        res_bat = self.client.get("/api/adb/remote-script")
        self.assertEqual(res_bat.status_code, 200)
        self.assertIn("adb_remote_pc.bat", res_bat.headers.get("Content-Disposition", ""))
        content = res_bat.data.decode("utf-8", errors="ignore")
        self.assertIn("ssh -R 5037:127.0.0.1:5037", content)
        res_bat.close()

    def test_api_pipelines_system(self):
        res = self.client.get("/api/pipelines?source=system")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "system")
        names = [p["name"] for p in data["pipelines"]]
        self.assertIn("ram", names)
        self.assertIn("os", names)
        self.assertIn("docker-status", names)
        self.assertIn("ssh-pub", names)

    def test_api_pipelines_dump(self):
        res = self.client.get("/api/pipelines?source=dump")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "dump")
        names = [p["name"] for p in data["pipelines"]]
        self.assertIn("audio", names)
        self.assertIn("car-service", names)
        self.assertIn("car-audio", names)
        self.assertIn("audio-all", names)
        audio_all = next(p for p in data["pipelines"] if p["name"] == "audio-all")
        self.assertGreaterEqual(len(audio_all["steps"]), 3)

    def test_api_terminal_run_and_stream(self):
        script = telua_web._build_terminal_bash_script("tel system")
        self.assertIn("tel()", script)
        self.assertIn("telua()", script)
        res = self.client.post("/api/terminal/run", json={"command": "echo hello_terminal"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("hello_terminal", data["output"])

        res_stream = self.client.post("/api/terminal/stream", json={"command": "echo stream_ok"})
        self.assertEqual(res_stream.status_code, 200)
        body = res_stream.get_data(as_text=True)
        self.assertIn("stream_ok", body)
        self.assertIn("__TELUA_EXIT_CODE__:0", body)

        res_stop = self.client.post("/api/terminal/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertTrue(res_stop.get_json()["ok"])

    def test_api_aosp_config_get_and_post(self):
        res = self.client.get("/api/aosp/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("aosp_root_dir", data)
        self.assertIn("active_project", data)
        self.assertIn("profiles", data)

        # Test updating AOSP config including target lunch and overlay persistence
        res_post = self.client.post("/api/aosp/config", json={
            "aosp_root_dir": "D:/test_aosp_path",
            "active_project": "oem_service",
            "target_product": "test_board_car",
            "target_variant": "userdebug",
        })
        self.assertEqual(res_post.status_code, 200)
        updated = res_post.get_json()
        self.assertEqual(updated["aosp_root_dir"], "D:/test_aosp_path")
        self.assertEqual(updated["active_project"], "oem_service")
        self.assertEqual(updated["target_product"], "test_board_car")
        self.assertEqual(updated["target_variant"], "userdebug")
        self.assertIn("apk_overlays.config", updated["config_file"])

        # Reset AOSP_ROOT_DIR back to empty
        self.client.post("/api/aosp/config", json={"aosp_root_dir": ""})

    def test_api_overlay_upload(self):
        import io
        # 1. Test uploading const_my_cli.config via JSON
        res_my = self.client.post("/api/overlay/upload", json={
            "target": "const_my_cli.config",
            "content": 'MY_GROUP_LIST=("upload_test :: Test upload macro")\nMY_CMD_UPLOAD_TEST=("echo uploaded_ok")\n',
        })
        self.assertEqual(res_my.status_code, 200)
        data_my = res_my.get_json()
        self.assertTrue(data_my["ok"])
        self.assertEqual(data_my["filename"], "const_my_cli.config")

        # 2. Test uploading apk_overlays.config via multipart/form-data
        overlay_content = b'ACTIVE_PROJECT="oem_service"\nCONFIG_TARGET_PRODUCT="uploaded_board"\nCONFIG_TARGET_BUILD_VARIANT="userdebug"\n'
        data_upload = {
            "target": "apk_overlays.config",
            "file": (io.BytesIO(overlay_content), "apk_overlays.config"),
        }
        res_ov = self.client.post("/api/overlay/upload", data=data_upload, content_type="multipart/form-data")
        self.assertEqual(res_ov.status_code, 200)
        data_ov = res_ov.get_json()
        self.assertTrue(data_ov["ok"])
        self.assertEqual(data_ov["filename"], "apk_overlays.config")
        self.assertIsNotNone(data_ov["aosp_info"])
        self.assertEqual(data_ov["aosp_info"]["target_product"], "uploaded_board")

        # 3. Test invalid bash syntax (should return 400)
        res_bad = self.client.post("/api/overlay/upload", json={
            "target": "apk_overlays.config",
            "content": 'ACTIVE_PROJECT="oem_service\nunterminated quote',
        })
        self.assertEqual(res_bad.status_code, 400)

        # 4. Test invalid target name (should return 400)
        res_bad_name = self.client.post("/api/overlay/upload", json={
            "target": "../../../etc/passwd",
            "content": "echo bad",
        })
        self.assertEqual(res_bad_name.status_code, 400)

    def test_api_logcat_endpoints(self):
        # 1. Test logcat status endpoint
        res_status = self.client.get("/api/logcat/status")
        self.assertEqual(res_status.status_code, 200)
        data_status = res_status.get_json()
        self.assertTrue(data_status["ok"])
        self.assertIn("adb_available", data_status)
        self.assertIn("streaming", data_status)

        # 2. Test logcat stop endpoint
        res_stop = self.client.post("/api/logcat/stop")
        self.assertEqual(res_stop.status_code, 200)
        data_stop = res_stop.get_json()
        self.assertTrue(data_stop["ok"])
        self.assertEqual(data_stop["stopped"], 0)

        # 3. Test logcat filters get (default or saved)
        res_filters = self.client.get("/api/logcat/filters")
        self.assertEqual(res_filters.status_code, 200)
        data_filters = res_filters.get_json()
        self.assertTrue(data_filters["ok"])
        self.assertIsInstance(data_filters["filters"], list)

        # 4. Test logcat filters post — saves to PERSONAL overlay by default
        sample_filters = [
            {"id": "test-1", "name": "UnitTest Rule", "enabled": True, "level": "W", "tag": "TestTag", "text": "error", "pid": "123"}
        ]
        res_post_filters = self.client.post("/api/logcat/filters", json={"filters": sample_filters})
        self.assertEqual(res_post_filters.status_code, 200)
        data_post = res_post_filters.get_json()
        self.assertTrue(data_post["ok"])
        self.assertEqual(data_post["count"], 1)
        self.assertTrue(data_post["personal"])
        self.assertEqual(data_post["path"], "config/overlay/logcat_filters.json")
        overlay_file = telua_web.ROOT / "config" / "overlay" / "logcat_filters.json"
        self.assertTrue(overlay_file.is_file())

        # Verify saved — GET now reads from the personal overlay
        res_verify = self.client.get("/api/logcat/filters")
        self.assertEqual(res_verify.status_code, 200)
        data_verify = res_verify.get_json()
        self.assertEqual(len(data_verify["filters"]), 1)
        self.assertEqual(data_verify["filters"][0]["name"], "UnitTest Rule")
        self.assertTrue(data_verify["personal"])
        self.assertEqual(data_verify["path"], "config/overlay/logcat_filters.json")

        # 5. Test shared=true — writes the Git-tracked template instead
        res_shared = self.client.post("/api/logcat/filters", json={"filters": sample_filters, "shared": True})
        self.assertEqual(res_shared.status_code, 200)
        data_shared = res_shared.get_json()
        self.assertTrue(data_shared["ok"])
        self.assertFalse(data_shared["personal"])
        self.assertEqual(data_shared["path"], "config/logcat_filters.json")

        # Restore default filters (personal overlay + shared template)
        self.client.post("/api/logcat/filters", json={"filters": telua_web.DEFAULT_LOGCAT_FILTERS})
        self.client.post("/api/logcat/filters", json={"filters": telua_web.DEFAULT_LOGCAT_FILTERS, "shared": True})

    def test_api_logcat_filters_overlay_priority_and_migration(self):
        """Personal overlay wins over shared template; one-time migration copies
        a customized shared file into the overlay."""
        overlay_file = telua_web.ROOT / "config" / "overlay" / "logcat_filters.json"
        shared_file = telua_web.ROOT / "config" / "logcat_filters.json"
        saved_overlay = saved_shared = None
        try:
            saved_overlay = overlay_file.read_bytes() if overlay_file.is_file() else None
            saved_shared = shared_file.read_bytes() if shared_file.is_file() else None

            # --- Migration: customized shared file + no overlay -> auto-copy ---
            if overlay_file.exists():
                overlay_file.unlink()
            custom = [{"id": "rule-custom", "name": "My Bosch Rule", "enabled": True,
                       "level": "D", "tag": "BOSCH_CAR_AUDIO", "text": "", "pid": ""}]
            shared_file.parent.mkdir(parents=True, exist_ok=True)
            shared_file.write_text(json.dumps(custom), encoding="utf-8")

            res = self.client.get("/api/logcat/filters")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["personal"])
            self.assertEqual(data["path"], "config/overlay/logcat_filters.json")
            self.assertTrue(overlay_file.is_file(), "migration should create overlay file")
            self.assertEqual(data["filters"][0]["name"], "My Bosch Rule")

            # --- Priority: overlay beats shared when both exist ---
            overlay_rules = [{"id": "rule-ov", "name": "Overlay Rule", "enabled": True,
                              "level": "I", "tag": "Ov.*", "text": "", "pid": ""}]
            overlay_file.write_text(json.dumps(overlay_rules), encoding="utf-8")
            res2 = self.client.get("/api/logcat/filters")
            data2 = res2.get_json()
            self.assertEqual(data2["filters"][0]["name"], "Overlay Rule")
        finally:
            # Restore original state
            if saved_overlay is not None:
                overlay_file.write_bytes(saved_overlay)
            elif overlay_file.exists():
                overlay_file.unlink()
            if saved_shared is not None:
                shared_file.write_bytes(saved_shared)
            elif shared_file.exists():
                shared_file.unlink()


    def test_api_mirror_endpoints(self):
        """Test Screen Mirroring info and input injection endpoints."""
        # 1. /api/mirror/info without mocking
        res_info = self.client.get("/api/mirror/info")
        self.assertEqual(res_info.status_code, 200)
        data_info = res_info.get_json()
        self.assertTrue(data_info["ok"])
        self.assertIn("adb_available", data_info)
        self.assertIn("width", data_info)
        self.assertIn("height", data_info)
        self.assertIn("density", data_info)

        # 2. Mock adb and subprocess for input injection endpoints
        with patch("telua_web_mirror._resolve_adb_binary", return_value="dummy_adb"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"dummy")

            # Touch
            res_touch = self.client.post("/api/mirror/touch", json={"x": 540, "y": 960})
            self.assertEqual(res_touch.status_code, 200)
            self.assertTrue(res_touch.get_json()["ok"])

            # Touch invalid coordinates
            res_touch_bad = self.client.post("/api/mirror/touch", json={"x": "abc"})
            self.assertEqual(res_touch_bad.status_code, 400)

            # Swipe
            res_swipe = self.client.post("/api/mirror/swipe", json={"x1": 100, "y1": 200, "x2": 100, "y2": 800, "duration": 300})
            self.assertEqual(res_swipe.status_code, 200)
            self.assertTrue(res_swipe.get_json()["ok"])

            # Key
            res_key = self.client.post("/api/mirror/key", json={"key": "4"})
            self.assertEqual(res_key.status_code, 200)
            self.assertTrue(res_key.get_json()["ok"])

            # Key invalid format (prevent injection)
            res_key_bad = self.client.post("/api/mirror/key", json={"key": "invalid;rm -rf"})
            self.assertEqual(res_key_bad.status_code, 400)

            # Text
            res_text = self.client.post("/api/mirror/text", json={"text": "Hello Telua Mirror"})
            self.assertEqual(res_text.status_code, 200)
            self.assertTrue(res_text.get_json()["ok"])

            # Frame - mock valid PNG output
            png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
            mock_run.return_value = MagicMock(returncode=0, stdout=png_header)
            res_frame = self.client.get("/api/mirror/frame")
            self.assertEqual(res_frame.status_code, 200)
            self.assertEqual(res_frame.mimetype, "image/png")
            res_frame.close()

    def test_api_power_controls_endpoints(self):
        """Test Target Power Controls persistent status, ON, OFF, and toggle."""
        # 1. Status
        res = self.client.get("/api/power/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn(data["state"], ("ON", "OFF"))
        self.assertEqual(data["config_file"], "config/target_power_state.json")

        # 2. Set OFF
        res_off = self.client.post("/api/power/set", json={"state": "OFF"})
        self.assertEqual(res_off.status_code, 200)
        data_off = res_off.get_json()
        self.assertTrue(data_off["ok"])
        self.assertEqual(data_off["state"], "OFF")
        self.assertFalse(data_off["is_on"])

        # 3. Set ON
        res_on = self.client.post("/api/power/set", json={"state": "ON"})
        self.assertEqual(res_on.status_code, 200)
        data_on = res_on.get_json()
        self.assertTrue(data_on["ok"])
        self.assertEqual(data_on["state"], "ON")
        self.assertTrue(data_on["is_on"])

        # 4. Toggle
        res_toggle = self.client.post("/api/power/toggle")
        self.assertEqual(res_toggle.status_code, 200)
        data_tog = res_toggle.get_json()
        self.assertTrue(data_tog["ok"])
        self.assertEqual(data_tog["state"], "OFF")

        # 5. Invalid state
        res_bad = self.client.post("/api/power/set", json={"state": "INVALID"})
        self.assertEqual(res_bad.status_code, 400)

        # 6. Test independent output controls (out1 & out2)
        res_out1_off = self.client.post("/api/power/output/out1", json={"state": "OFF"})
        self.assertEqual(res_out1_off.status_code, 200)
        data_o1 = res_out1_off.get_json()
        self.assertEqual(data_o1["output"], "out1")
        self.assertEqual(data_o1["state"], "OFF")

        res_out2_on = self.client.post("/api/power/output/out2", json={"state": "ON"})
        self.assertEqual(res_out2_on.status_code, 200)
        data_o2 = res_out2_on.get_json()
        self.assertEqual(data_o2["output"], "out2")
        self.assertEqual(data_o2["state"], "ON")

        # 7. Restore to ON (Master)
        self.client.post("/api/power/set", json={"state": "ON"})


if __name__ == "__main__":
    unittest.main()

