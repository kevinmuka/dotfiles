"""Regression checks for the Alfred UI's delegation to localbackup."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lib.localbackup.integrations import alfred_workflow_bridge as bridge
from tools.localbackup.install_alfred_workflow import KEEP, transform


class AlfredWorkflowBridgeTests(unittest.TestCase):
    def test_manual_backup_uses_cli_and_returns_both_paths(self):
        output = StringIO()
        result = {"results": [{"archives": [
            {"path": "/tmp/preferences.zip"}, {"path": "/tmp/workflow-data.zip"},
        ]}]}
        with patch.object(bridge, "call", return_value=result) as cli, redirect_stdout(output):
            bridge.backup("now")
        cli.assert_called_once_with("now", "alfred")
        self.assertEqual(output.getvalue().splitlines(), ["/tmp/preferences.zip", "/tmp/workflow-data.zip"])

    def test_status_warns_about_legacy_schedule(self):
        output = StringIO()
        result = {"results": [{
            "loaded": False, "installed": False, "legacy_alfred_loaded": True,
            "configured": "weekly", "weekday": "monday", "time": "03:00",
        }]}
        with patch.object(bridge, "call", return_value=result) as cli, redirect_stdout(output):
            bridge.status()
        cli.assert_called_once_with("status", "alfred")
        self.assertIn("Conflicting Alfred schedule", json.loads(output.getvalue())["items"][0]["title"])

    def test_restore_keeps_installed_workflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current, saved = root / "current", root / "saved"
            current.mkdir()
            saved.mkdir()
            (current / "old-script.py").write_text("old")
            (saved / "localbackup_bridge.py").write_text("new")
            bridge.keep_installed_workflow(current, saved)
            self.assertEqual((current / "localbackup_bridge.py").read_text(), "new")
            self.assertFalse((current / "old-script.py").exists())


class AlfredWorkflowInstallerTests(unittest.TestCase):
    def test_converted_graph_has_one_backup_implementation(self):
        info = {
            "bundleid": "local.kevinmuka.alfred.backuppreferences",
            "objects": [{"uid": uid, "config": {}} for uid in KEEP],
            "uidata": {uid: {} for uid in KEEP},
            "connections": {},
            "variables": {"backup_prefix": "Alfred Backup "},
            "userconfigurationconfig": [
                {"variable": name} for name in (
                    "backup_keyword", "backup_target", "backup_time", "backup_frequency",
                    "backup_weekday", "backup_count", "confirm_restore",
                )
            ],
        }
        result = transform(info)
        self.assertEqual([item["variable"] for item in result["userconfigurationconfig"]], [
            "backup_keyword", "confirm_restore",
        ])
        scripts = [item["config"].get("script", "") for item in result["objects"]]
        self.assertEqual(sum("localbackup_bridge.py" in script for script in scripts), 6)
        self.assertFalse(any("launchctl" in script or "/usr/bin/ditto" in script for script in scripts))


if __name__ == "__main__":
    unittest.main()
