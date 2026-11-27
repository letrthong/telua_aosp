# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
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
"""
test_telua_devops.py — Unit tests for GitHub Issue creation and git fix branch automation.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from web.ai.telua_web_ai import (
    _detect_github_repo,
    _get_github_token,
    _tool_create_github_issue,
    _tool_create_git_fix_branch,
    TOOL_EXECUTORS,
    TOOL_SCHEMAS,
)


class TestTeluaDevOps(unittest.TestCase):
    """Test suite for autonomous DevOps tools: create_github_issue and create_git_fix_branch."""

    def test_detect_github_repo(self):
        repo = _detect_github_repo()
        # In this repository, origin is https://github.com/letrthong/telua_aosp.git
        self.assertEqual(repo, "letrthong/telua_aosp")

    def test_create_github_issue_missing_params(self):
        # Missing title
        res = _tool_create_github_issue({"body": "some bug"})
        self.assertIn("[ERROR] missing 'title'", res)

        # Missing body
        res = _tool_create_github_issue({"title": "some bug"})
        self.assertIn("[ERROR] missing 'body'", res)

    def test_create_github_issue_missing_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("web.ai.telua_web_ai._get_github_token", return_value=""):
                res = _tool_create_github_issue({"title": "Test Bug", "body": "Details"})
                self.assertIn("[ERROR] GitHub token not found", res)
                self.assertIn("config/overlay/github_token.json", res)

    @patch("urllib.request.urlopen")
    def test_create_github_issue_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"number": 42, "html_url": "https://github.com/letrthong/telua_aosp/issues/42"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch("web.ai.telua_web_ai._get_github_token", return_value="fake_token_123"):
            res = _tool_create_github_issue({
                "title": "[AI-Bug] NullPointerException in CarAudioService",
                "body": "Detailed stack trace and AST context",
                "labels": ["bug", "aosp_a16"],
            })
            self.assertIn("[SUCCESS]", res)
            self.assertIn("#42", res)
            self.assertIn("https://github.com/letrthong/telua_aosp/issues/42", res)

    def test_create_git_fix_branch_missing_params(self):
        # Missing branch_name
        res = _tool_create_git_fix_branch({"commit_msg": "fix: bug"})
        self.assertIn("[ERROR] missing 'branch_name'", res)

        # Missing commit_msg
        res = _tool_create_git_fix_branch({"branch_name": "fix/my-branch"})
        self.assertIn("[ERROR] missing 'commit_msg'", res)

    def test_create_git_fix_branch_blocked_main(self):
        # Safety check: blocks main and master
        for bad_branch in ["main", "master", "HEAD", "/main"]:
            res = _tool_create_git_fix_branch({"branch_name": bad_branch, "commit_msg": "fix: test"})
            self.assertIn("[BLOCKED]", res)

    def test_tools_registered_in_schema_and_executors(self):
        # Verify both tools are in TOOL_EXECUTORS
        self.assertIn("create_github_issue", TOOL_EXECUTORS)
        self.assertIn("create_git_fix_branch", TOOL_EXECUTORS)

        # Verify both tools are in TOOL_SCHEMAS
        schema_names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        self.assertIn("create_github_issue", schema_names)
        self.assertIn("create_git_fix_branch", schema_names)


if __name__ == "__main__":
    unittest.main()
