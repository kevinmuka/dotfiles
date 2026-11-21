"""Back up Alfred Preferences and Workflow Data as separate archives."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile

from ..common import (
    BackupError, archive_path, check_zip, local_host_name, restricted_directory,
    prune, sqlite_snapshot,
)
from ..config import default_output_dir
from ..archive import validate_zip


DATA_ROOT = "Alfred Workflow Data Backup"
PREFERENCES_ROOT = "Alfred.alfredpreferences"
PREFERENCES_PREFIX = "Alfred Backup "
DATA_PREFIX = "Alfred Workflow Data "
SQLITE_HEADER = b"SQLite format 3\x00"


def _readme(created: datetime) -> str:
    return f"""ALFRED WORKFLOW DATA BACKUP

Created: {created:%Y-%m-%d %H:%M:%S}

WHAT THIS ARCHIVE CONTAINS
The "Workflow Data" folder contains local data created by Alfred workflows,
such as settings, history, and databases. Workflow definitions are stored in
the separate Alfred Preferences archive in the sibling "preferences" folder.

RESTORE LOCATION
Copy the enclosed "Workflow Data" folder to:
  ~/Library/Application Support/Alfred/Workflow Data/

HOW TO RESTORE
1. Restore an Alfred Preferences archive first, preferably from the same date,
   so the matching workflow definitions are installed.
2. Quit Alfred and Alfred Preferences.
3. If the destination already exists, copy or rename it before replacing it.
4. Copy the enclosed "Workflow Data" folder into
   ~/Library/Application Support/Alfred/ . The final path must be
   ~/Library/Application Support/Alfred/Workflow Data/ , without an extra
   "Alfred Workflow Data Backup" level.
5. Reopen Alfred and check the workflows you use. Some may require you to
   reconnect accounts or permissions stored in macOS Keychain.

This ZIP does not restore data automatically. Do not extract it while Alfred
is using the data. It is a snapshot of the files at creation time; SQLite
databases are copied using consistent snapshots.
"""


def _snapshot_databases(source: Path, snapshot: Path) -> None:
    for original in source.rglob("*"):
        if original.is_symlink() or not original.is_file():
            continue
        with original.open("rb") as stream:
            if stream.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                continue
        relative = original.relative_to(source)
        copied = snapshot / relative
        replacement = copied.with_name(copied.name + ".snapshot")
        try:
            sqlite_snapshot(original, replacement)
            os.replace(replacement, copied)
            for suffix in ("-wal", "-shm", "-journal"):
                (snapshot / relative.with_name(original.name + suffix)).unlink(missing_ok=True)
        finally:
            replacement.unlink(missing_ok=True)


def backup(
    *,
    home: Path | None = None,
    preferences_dir: Path | None = None,
    preferences_source: Path | None = None,
    keep: int = 12,
    machine: str | None = None,
) -> list[dict[str, str]]:
    if keep < 1:
        raise BackupError("The retention count must be at least 1")
    home = home or Path.home()
    alfred_home = home / "Library/Application Support/Alfred"
    source = preferences_source or alfred_home / "Alfred.alfredpreferences"
    workflow_data = alfred_home / "Workflow Data"
    if not source.is_dir() or not workflow_data.is_dir():
        raise BackupError("Alfred Preferences or Workflow Data is unavailable")
    if source.is_symlink() or workflow_data.is_symlink():
        raise BackupError("Alfred source folders must not be symbolic links")
    machine = machine or local_host_name()
    if any(char in machine for char in ("/", "\\", "\x00")):
        raise BackupError("Invalid machine name")

    os.umask(0o077)
    preferences_dir = restricted_directory(
        preferences_dir or default_output_dir("alfred", home)
    )
    data_dir = restricted_directory(preferences_dir.parent / "workflow-data")
    created = datetime.now()
    preferences_file = archive_path(
        preferences_dir, PREFERENCES_PREFIX + machine + " ", ".zip", created
    )
    data_file = archive_path(data_dir, DATA_PREFIX + machine + " ", ".zip", created)

    pending_preferences: Path | None = None
    pending_data: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".alfred-preferences-", suffix=".pending", dir=preferences_dir,
            delete=False,
        ) as pending:
            pending_preferences = Path(pending.name)
        pending_preferences.unlink()
        subprocess.run(
            ["/usr/bin/ditto", "-c", "-k", "--keepParent", str(source), str(pending_preferences)],
            check=True,
        )
        validate_zip(pending_preferences, PREFERENCES_ROOT)

        with tempfile.TemporaryDirectory(prefix="localbackup-alfred-") as temporary:
            stage = Path(temporary) / DATA_ROOT
            stage.mkdir()
            copied_data = stage / "Workflow Data"
            subprocess.run(["/usr/bin/ditto", str(workflow_data), str(copied_data)], check=True)
            _snapshot_databases(workflow_data, copied_data)
            (stage / "README.txt").write_text(_readme(created), encoding="utf-8")
            with tempfile.NamedTemporaryFile(
                prefix=".alfred-workflow-data-", suffix=".pending", dir=data_dir,
                delete=False,
            ) as pending:
                pending_data = Path(pending.name)
            pending_data.unlink()
            subprocess.run(
                ["/usr/bin/ditto", "-c", "-k", "--keepParent", str(stage), str(pending_data)],
                check=True,
            )
        check_zip(
            pending_data,
            (f"{DATA_ROOT}/README.txt",),
        )
        with ZipFile(pending_data) as archive:
            if not any(name.startswith(f"{DATA_ROOT}/Workflow Data/") for name in archive.namelist()):
                raise BackupError("Workflow Data ZIP is missing its data folder")

        os.replace(pending_preferences, preferences_file)
        pending_preferences = None
        os.replace(pending_data, data_file)
        pending_data = None
    finally:
        for pending in (pending_preferences, pending_data):
            if pending is not None:
                pending.unlink(missing_ok=True)

    prune(preferences_dir, PREFERENCES_PREFIX, ".zip", keep)
    prune(data_dir, DATA_PREFIX, ".zip", keep)
    return [
        {"kind": "preferences", "path": str(preferences_file)},
        {"kind": "workflow_data", "path": str(data_file)},
    ]
