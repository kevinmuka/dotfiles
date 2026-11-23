#!/usr/bin/env python3
"""Adapt Alfred's Script Filter and Run Script actions to the localbackup CLI.

This file is copied into the installed workflow. It contains no backup,
retention, scheduling, or archive extraction implementation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


LAUNCHER = Path.home() / ".config/scripts/localbackup"
PYTHON_CANDIDATES = ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", sys.executable)


def python_for_cli() -> str:
    for candidate in PYTHON_CANDIDATES:
        if not Path(candidate).is_file():
            continue
        result = subprocess.run(
            [candidate, "-c", "import sys; sys.exit(sys.version_info < (3, 11))"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return candidate
    raise RuntimeError("localbackup requires Python 3.11 or newer")


def call(*args: str) -> dict:
    if not LAUNCHER.is_file():
        raise RuntimeError(f"localbackup launcher is missing: {LAUNCHER}")
    result = subprocess.run(
        [python_for_cli(), str(LAUNCHER), *args, "--json"],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError(result.stderr.strip() or "localbackup returned invalid JSON") from error
    if result.returncode or not data.get("ok", True):
        errors = data.get("errors", [])
        message = "; ".join(item.get("message", str(item)) for item in errors)
        raise RuntimeError(message or result.stderr.strip() or "localbackup failed")
    return data


def first_result(data: dict) -> dict:
    results = data.get("results", [])
    if len(results) != 1:
        raise RuntimeError("localbackup returned an unexpected result")
    return results[0]


def backup(command: str) -> None:
    entry = first_result(call(command, "alfred"))
    paths = [item["path"] for item in entry.get("archives", [])]
    if not paths:
        raise RuntimeError("localbackup did not return an archive")
    print("\n".join(paths))


def stop() -> None:
    first_result(call("stop", "alfred"))
    print("Automatic backups stopped. Existing archives were kept.")


def status() -> None:
    entry = first_result(call("status", "alfred"))
    frequency = entry.get("configured")
    clock = entry.get("time")
    if frequency == "weekly":
        schedule = f"every {entry.get('weekday', '').capitalize()} at {clock}"
    elif frequency == "daily":
        schedule = f"daily at {clock}"
    else:
        schedule = "disabled in TOML"
    if entry.get("legacy_alfred_loaded"):
        title = "Conflicting Alfred schedule active"
        subtitle = "The old workflow LaunchAgent is loaded; stop it before backup start"
    elif entry.get("loaded"):
        title = "Automatic backups active"
        subtitle = f"localbackup LaunchAgent loaded; {schedule}"
        if not entry.get("matches_config"):
            subtitle += "; run backup start to apply current settings"
    elif entry.get("installed"):
        title = "Automatic backups inactive"
        subtitle = f"LaunchAgent file exists but is not loaded; configured {schedule}"
    else:
        title = "Automatic backups stopped"
        subtitle = f"Configured {schedule}; run backup start to enable it"
    print(json.dumps({"items": [{"title": title, "subtitle": subtitle, "valid": False}]}))


def archives() -> None:
    entries = first_result(call("archives", "alfred")).get("archives", [])
    items = []
    for entry in entries:
        if entry.get("kind") != "preferences":
            continue
        path = Path(entry["path"])
        items.append({
            "title": path.stem.removeprefix("Alfred Backup "),
            "subtitle": str(path).replace(str(Path.home()), "~", 1),
            "type": "file",
            "arg": str(path),
        })
    if not items:
        items.append({
            "title": "No preference backups found",
            "subtitle": "Run backup now or backup start to create an archive",
            "valid": False,
        })
    print(json.dumps({"items": items}))


def _running(name: str) -> bool:
    return subprocess.run(
        ["/usr/bin/pgrep", "-x", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def keep_installed_workflow(current: Path, saved: Path) -> None:
    """Replace only this workflow in the restored preferences, with rollback."""
    token = uuid4().hex
    pending = current.with_name(f".{current.name}.localbackup-pending-{token}")
    old = current.with_name(f".{current.name}.localbackup-restored-{token}")
    shutil.copytree(saved, pending, symlinks=True)
    moved_old = False
    try:
        if current.exists() or current.is_symlink():
            os.replace(current, old)
            moved_old = True
        try:
            os.replace(pending, current)
        except Exception:
            if moved_old:
                os.replace(old, current)
                moved_old = False
            raise
        if moved_old:
            if old.is_dir() and not old.is_symlink():
                shutil.rmtree(old)
            else:
                old.unlink()
    finally:
        if pending.exists():
            shutil.rmtree(pending)


def restore_preferences(path: str) -> None:
    # Validate the selected archive before asking either app to quit.
    call("restore", "alfred", "--preferences", path)
    current = Path(os.environ["alfred_preferences"]) / "workflows" / os.environ["alfred_workflow_uid"]
    if current.is_symlink() or not current.is_dir():
        raise RuntimeError("Could not preserve the installed backup workflow")
    with tempfile.TemporaryDirectory(prefix="localbackup-alfred-workflow-") as temporary:
        saved = Path(temporary) / current.name
        shutil.copytree(current, saved, symlinks=True)
        for bundle in ("com.runningwithcrayons.Alfred-Preferences", "com.runningwithcrayons.Alfred"):
            result = subprocess.run(
                ["/usr/bin/osascript", "-l", "JavaScript", "-e", f'Application("{bundle}").quit()'],
                capture_output=True, text=True,
            )
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or f"Could not quit {bundle}")
        for _ in range(50):
            if not any(_running(name) for name in ("Alfred", "Alfred Preferences")):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Quit Alfred and Alfred Preferences before restoring")
        try:
            call("restore", "alfred", "--preferences", path, "--apply")
            keep_installed_workflow(current, saved)
        finally:
            subprocess.run(["/usr/bin/open", "-a", "Alfred"], check=False)
    workflow = os.environ.get("alfred_workflow_bundleid", "")
    if workflow:
        for _ in range(50):
            if _running("Alfred"):
                break
            time.sleep(0.2)
        subprocess.run([
            "/usr/bin/osascript", "-l", "JavaScript", "-e",
            'function run(argv) { Application("com.runningwithcrayons.Alfred").runTrigger("restore_notification", { inWorkflow: argv[0], withArgument: argv[1] }) }',
            workflow, path,
        ], check=False)


def notify_error(message: str) -> None:
    subprocess.run([
        "/usr/bin/osascript", "-e",
        'on run argv\n display notification (item 1 of argv) with title "localbackup"\nend run',
        message,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if command in ("start", "now"):
            backup(command)
        elif command == "stop":
            stop()
        elif command == "status":
            status()
        elif command == "archives":
            archives()
        elif command == "restore" and len(sys.argv) == 3:
            restore_preferences(sys.argv[2])
        else:
            raise RuntimeError("Invalid Alfred workflow bridge command")
    except Exception as error:
        if command in ("status", "archives"):
            print(json.dumps({"items": [{
                "title": "Backup unavailable",
                "subtitle": str(error),
                "valid": False,
            }]}))
            return 0
        notify_error(str(error))
        print(f"localbackup: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
