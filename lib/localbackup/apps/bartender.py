"""Back up Bartender 7 preferences and its group-container database."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from ..common import BackupError, archive_path, check_zip, prune, restricted_directory, sqlite_snapshot
from ..config import default_output_dir


DOMAIN = "com.surteesstudios.Bartender"
GROUP_CONTAINER = "24J875RH8J.com.surteesstudios.Bartender"
ARCHIVE_ROOT = "Bartender 7 Backup"
ARCHIVE_PREFIX = "Bartender 7 Settings "


def _readme(created: datetime, version: str) -> str:
    return f"""BARTENDER 7 SETTINGS BACKUP

Created: {created:%Y-%m-%d %H:%M:%S}
Bartender version: {version}

WHAT THIS ARCHIVE CONTAINS
- Preferences exported from the {DOMAIN} defaults domain.
- A consistent SQLite snapshot of the group-container default.store database.

This is a file-level snapshot of Bartender 7, not Bartender's native configuration
export. Use the same Bartender version when possible. The app itself, license,
macOS permissions, caches, and clipboard history are not guaranteed to be
recoverable from this archive.

HOW TO RESTORE
1. Install Bartender 7, then quit Bartender and its Settings window.
2. Keep a separate copy of your current preferences and group-container data.
3. Extract this ZIP. Import the enclosed preferences file with:
     defaults import {DOMAIN} "/path/to/{DOMAIN}.plist"
4. Copy the enclosed default.store into:
     ~/Library/Group Containers/{GROUP_CONTAINER}/Library/Application Support/
   Move any existing default.store, default.store-wal, and default.store-shm
   aside before copying. Do not copy this archive's enclosing folders into
   Group Containers.
5. Reopen Bartender, verify your layout and automations, and grant any macOS
   permissions or account access that the new installation requests.

The database was captured with SQLite's backup API. Do not overwrite live
Bartender data while the app is running. Bartender 7.1.0 and later also offer a
native configuration export in Advanced settings; use that for a supported
cross-Mac transfer when it is available.
"""


def backup(
    *,
    home: Path | None = None,
    output_dir: Path | None = None,
    app_info: Path | None = None,
    preferences_bytes: bytes | None = None,
    keep: int = 12,
) -> list[dict[str, str]]:
    if keep < 1:
        raise BackupError("The retention count must be at least 1")
    home = home or Path.home()
    app_info = app_info or Path("/Applications/Bartender 7.app/Contents/Info.plist")
    database = (
        home / "Library/Group Containers" / GROUP_CONTAINER
        / "Library/Application Support/default.store"
    )
    if not app_info.is_file() or not database.is_file():
        raise BackupError("Bartender 7 or its settings database is unavailable")
    if database.is_symlink():
        raise BackupError("Bartender's settings database must not be a symbolic link")
    version = str(plistlib.loads(app_info.read_bytes())["CFBundleShortVersionString"])
    if not version.startswith("7."):
        raise BackupError(f"Unsupported Bartender version: {version}")

    if preferences_bytes is None:
        preferences_bytes = subprocess.run(
            ["/usr/bin/defaults", "export", DOMAIN, "-"],
            capture_output=True,
            check=True,
        ).stdout
    if not isinstance(plistlib.loads(preferences_bytes), dict):
        raise BackupError("Bartender preferences export is invalid")

    os.umask(0o077)
    output_dir = restricted_directory(
        output_dir or default_output_dir("bartender", home)
    )
    created = datetime.now()
    output = archive_path(output_dir, ARCHIVE_PREFIX, ".zip", created)
    pending: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="localbackup-bartender-") as temporary:
            snapshot = Path(temporary) / "default.store"
            sqlite_snapshot(database, snapshot)
            with tempfile.NamedTemporaryFile(
                prefix=".bartender-", suffix=".pending", dir=output_dir, delete=False
            ) as pending_file:
                pending = Path(pending_file.name)
                with ZipFile(pending_file, "w", compression=ZIP_DEFLATED) as archive:
                    archive.writestr(f"{ARCHIVE_ROOT}/README.txt", _readme(created, version))
                    archive.writestr(
                        f"{ARCHIVE_ROOT}/Preferences/{DOMAIN}.plist", preferences_bytes
                    )
                    archive.write(
                        snapshot,
                        f"{ARCHIVE_ROOT}/Group Containers/{GROUP_CONTAINER}/"
                        "Library/Application Support/default.store",
                    )
        check_zip(
            pending,
            (
                f"{ARCHIVE_ROOT}/README.txt",
                f"{ARCHIVE_ROOT}/Preferences/{DOMAIN}.plist",
                f"{ARCHIVE_ROOT}/Group Containers/{GROUP_CONTAINER}/"
                "Library/Application Support/default.store",
            ),
        )
        os.replace(pending, output)
        pending = None
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
    prune(output_dir, ARCHIVE_PREFIX, ".zip", keep)
    return [{"kind": "settings", "path": str(output)}]
