#!/usr/bin/env python3
"""Convert the installed Backup Preferences workflow into a localbackup UI.

Run with --workflow PATH. A complete copy is saved in a temporary directory
before the installed workflow is changed.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import shutil
import tempfile


START = "DBC1BB9E-CF55-4493-A686-1EDD5FE0DC5B"
START_SCRIPT = "4679003D-7510-4EE8-908F-E1A9058554D9"
NOW = "FA3142D0-808A-47C8-BBDE-0F8796B78DC5"
NOW_SCRIPT = "5201952E-FBB9-4F36-97DF-A2958AC3EE5F"
BACKUP_NOTIFICATION = "70A4D85C-6E26-4062-A2DE-C97212E1FCB2"
STOP = "F5C22C94-07D9-4BB0-ADAF-6E05F8BF2BBF"
STOP_SCRIPT = "0EF9669C-0341-48C7-A3B2-1FB14416C8C4"
STOP_NOTIFICATION = "09A8A4F5-849B-4AB3-8029-F62F45D7758C"
STATUS = "AE538C70-3676-4AB0-92B9-6AD54C8231CB"
RESTORE = "D233FBB6-340D-4D2F-AE73-318850F5256D"
RESTORE_ARGUMENT = "5CD63DD8-3EF7-4CAD-84A1-8FFBD50A1DF0"
RESTORE_CONDITION = "D3CB316A-7C91-41BA-8038-68D8605758A8"
RESTORE_DIALOG = "6F716EA5-B930-4FFB-A431-CD7B99CA6C19"
RESTORE_SCRIPT = "084676FF-E013-428E-9477-53AC6722265D"
RESTORE_TRIGGER = "0241E1B3-DFBC-4C3C-BA8F-CA3DDFCB21CB"
RESTORE_NOTIFICATION = "D6B3844D-04FB-487E-8D2A-D3128500FFA8"

KEEP = {
    START, START_SCRIPT, NOW, NOW_SCRIPT, BACKUP_NOTIFICATION, STOP, STOP_SCRIPT,
    STOP_NOTIFICATION, STATUS, RESTORE, RESTORE_ARGUMENT, RESTORE_CONDITION,
    RESTORE_DIALOG, RESTORE_SCRIPT, RESTORE_TRIGGER, RESTORE_NOTIFICATION,
}
BRIDGE = '${alfred_preferences}/workflows/${alfred_workflow_uid}/localbackup_bridge.py'
BUNDLE_ID = "local.kevinmuka.alfred.backuppreferences"


def connection(uid: str, output: str | None = None) -> dict:
    result = {"destinationuid": uid, "modifiers": 0, "modifiersubtext": "", "vitoclose": False}
    if output:
        result["sourceoutputuid"] = output
    return result


def run_script(command: str, argument: str = "") -> str:
    return f'/usr/bin/python3 -B "{BRIDGE}" {command}{argument}'


def integrated(info: dict) -> bool:
    managed = {START_SCRIPT, NOW_SCRIPT, STOP_SCRIPT, STATUS, RESTORE, RESTORE_SCRIPT}
    return info.get("bundleid") == BUNDLE_ID and managed <= {
        item["uid"] for item in info["objects"]
        if BRIDGE in item.get("config", {}).get("script", "")
    }


def transform(info: dict) -> dict:
    if info.get("bundleid") != BUNDLE_ID:
        raise ValueError("Unexpected Alfred workflow bundle ID")
    objects = {item["uid"]: item for item in info["objects"]}
    missing = KEEP - objects.keys()
    if missing:
        raise ValueError(f"Workflow objects are missing: {', '.join(sorted(missing))}")

    objects[START_SCRIPT]["config"]["script"] = run_script("start")
    objects[NOW_SCRIPT]["config"]["script"] = run_script("now")
    objects[STOP_SCRIPT]["config"]["script"] = run_script("stop")
    objects[STATUS]["config"]["script"] = run_script("status")
    objects[RESTORE]["config"]["script"] = run_script("archives")
    objects[RESTORE]["config"]["type"] = 11  # shell Script Filter
    objects[RESTORE_SCRIPT]["config"]["script"] = run_script("restore", ' "${restore_from}"')

    objects[START]["config"]["subtext"] = "Creates both archives now and enables the localbackup schedule"
    objects[NOW]["config"]["subtext"] = "Creates both archives without changing the schedule"
    objects[STATUS]["config"]["subtext"] = "Check the localbackup LaunchAgent and its schedule"
    objects[BACKUP_NOTIFICATION]["config"]["text"] = "Preferences and Workflow Data archives created by localbackup"

    info["objects"] = [item for item in info["objects"] if item["uid"] in KEEP]
    info["uidata"] = {uid: data for uid, data in info["uidata"].items() if uid in KEEP}
    info["connections"] = {
        START: [connection(START_SCRIPT)],
        START_SCRIPT: [connection(BACKUP_NOTIFICATION)],
        NOW: [connection(NOW_SCRIPT)],
        NOW_SCRIPT: [connection(BACKUP_NOTIFICATION)],
        STOP: [connection(STOP_SCRIPT)],
        STOP_SCRIPT: [connection(STOP_NOTIFICATION)],
        RESTORE: [connection(RESTORE_ARGUMENT)],
        RESTORE_ARGUMENT: [connection(RESTORE_CONDITION)],
        RESTORE_CONDITION: [
            connection(RESTORE_DIALOG, "63F722FC-DA00-4F03-AC5D-3F42AEBFF5FC"),
            connection(RESTORE_SCRIPT),
        ],
        RESTORE_DIALOG: [connection(RESTORE_SCRIPT, "_button1")],
        RESTORE_TRIGGER: [connection(RESTORE_NOTIFICATION)],
    }
    info["variables"].pop("backup_prefix", None)
    info.pop("webaddress", None)
    info["userconfigurationconfig"] = [
        field for field in info["userconfigurationconfig"]
        if field["variable"] in {"backup_keyword", "confirm_restore"}
    ]
    info["readme"] = """# Backup Preferences (Custom)

This workflow is an Alfred interface for localbackup. It does not create or
restore archives or manage a LaunchAgent itself. Install localbackup at
~/.config/scripts/localbackup. Configure the backup folder, version count,
and schedule in ~/.config/localbackup/config.toml. Run start after changing
the schedule to update its LaunchAgent. The workflow only configures its
keyword and whether to confirm a restore.

Use the configured keyword (default: backup) followed by start, now, stop,
status, or restore. Start creates both Alfred archives immediately and enables
the configured daily or weekly schedule. Now creates both archives without
changing the schedule. Stop removes the localbackup schedule and keeps all
archives. Restore lists preferences archives, validates the selected ZIP,
quits Alfred, and asks localbackup to replace the preferences. It preserves
this integrated workflow from the current installation so an older archive
cannot bring back the independent scripts. The previous full preferences
folder is kept as a before-localbackup copy beside the restored folder.
Workflow Data can be restored with the localbackup CLI.

Keep the original workflow update source disabled: installing an upstream
version can replace this integration. The version-controlled bridge and
installer are in the dotfiles repository under lib/localbackup/integrations/
and tools/localbackup/.
"""
    return info


def install(workflow: Path) -> Path:
    info_path = workflow / "info.plist"
    if workflow.is_symlink() or not info_path.is_file() or info_path.is_symlink():
        raise ValueError("Expected a regular installed workflow folder and info.plist")
    source = Path(__file__).resolve().parents[2] / "lib/localbackup/integrations/alfred_workflow_bridge.py"
    original = plistlib.loads(info_path.read_bytes())
    patched = None if integrated(original) else transform(original)
    bridge_path = workflow / "localbackup_bridge.py"
    if bridge_path.is_symlink():
        raise ValueError("Workflow bridge must not be a symbolic link")
    if patched is not None:
        prefs_path = workflow / "prefs.plist"
        if prefs_path.is_symlink():
            raise ValueError("Workflow preferences must not be a symbolic link")
        prefs = plistlib.loads(prefs_path.read_bytes()) if prefs_path.exists() else {}
        prefs = {key: value for key, value in prefs.items() if key in {"backup_keyword", "confirm_restore"}}
    backup_root = Path(tempfile.mkdtemp(prefix="alfred-workflow-before-localbackup-"))
    backup = backup_root / workflow.name
    shutil.copytree(workflow, backup)
    if patched is None:
        # Refresh the adapter without changing the workflow graph or preferences.
        shutil.copy2(source, bridge_path)
        return backup
    with tempfile.NamedTemporaryFile(prefix=".info-localbackup-", dir=workflow, delete=False) as stream:
        pending = Path(stream.name)
        plistlib.dump(patched, stream)
    with tempfile.NamedTemporaryFile(prefix=".prefs-localbackup-", dir=workflow, delete=False) as stream:
        pending_prefs = Path(stream.name)
        plistlib.dump(prefs, stream)
    try:
        os.chmod(pending, info_path.stat().st_mode & 0o777)
        os.chmod(pending_prefs, prefs_path.stat().st_mode & 0o777 if prefs_path.exists() else 0o600)
        shutil.copy2(source, bridge_path)
        os.replace(pending, info_path)
        os.replace(pending_prefs, prefs_path)
        for unused in ("backup_workflow_data.py", "validate_archive.py"):
            (workflow / unused).unlink(missing_ok=True)
    finally:
        pending.unlink(missing_ok=True)
        pending_prefs.unlink(missing_ok=True)
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", required=True, type=Path)
    args = parser.parse_args()
    print(f"Original workflow copy: {install(args.workflow)}")


if __name__ == "__main__":
    main()
