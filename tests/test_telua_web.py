#!/usr/bin/env python3
# ==============================================================================
# Unit tests for web/telua_web_core.py, web/telua_web_pipelines.py, and web/telua_web.py
# ==============================================================================

import os
import shutil
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()

