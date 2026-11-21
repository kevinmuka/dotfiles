"""Shared local backup operations; no cloud access."""

from __future__ import annotations

from contextlib import closing
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import os
import fcntl
import socket
import sqlite3
import subprocess
import time
from urllib.parse import quote
from zipfile import ZipFile


class BackupError(Exception):
    """A local backup could not be completed or verified."""


@contextmanager
def app_lock(app: str):
    """Prevent a scheduled run, a manual run, and a restore from overlapping."""
    directory = restricted_directory(Path.home() / ".local/state/localbackup")
    path = directory / f"{app}.lock"
    if path.is_symlink():
        raise BackupError(f"Lock path must not be a symbolic link: {path}")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise BackupError(f"A {app} backup or restore is already in progress") from error
        yield
    finally:
        os.close(descriptor)


def restricted_directory(path: Path) -> Path:
    path = path.expanduser()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def archive_path(directory: Path, prefix: str, suffix: str, now: datetime) -> Path:
    base = f"{prefix}{now:%Y.%m.%d at %H.%M.%S}"
    path = directory / f"{base}{suffix}"
    counter = 2
    while path.exists():
        path = directory / f"{base}-{counter}{suffix}"
        counter += 1
    return path


def prune(directory: Path, prefix: str, suffix: str, keep: int) -> None:
    if keep < 1:
        raise BackupError("The retention count must be at least 1")
    archives = sorted(
        (p for p in directory.glob(f"{prefix}*{suffix}") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in archives[keep:]:
        old.unlink()


def local_host_name() -> str:
    result = subprocess.run(
        ["/usr/sbin/scutil", "--get", "LocalHostName"], capture_output=True, text=True
    )
    name = result.stdout.strip() if result.returncode == 0 else socket.gethostname().split(".")[0]
    if not name or any(char in name for char in ("/", "\\", "\x00")):
        raise BackupError("The Mac's local host name is invalid")
    return name


def sqlite_snapshot(source: Path, destination: Path) -> None:
    """Copy committed SQLite state, including active WAL transactions."""
    uri = "file:" + quote(str(source), safe="/") + "?mode=ro"
    deadline = time.monotonic() + 20

    def check_deadline(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise BackupError(f"Timed out while copying SQLite database: {source}")

    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as original:
        with closing(sqlite3.connect(destination)) as snapshot:
            original.backup(snapshot, pages=128, progress=check_deadline, sleep=0.1)
            if snapshot.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BackupError(f"SQLite snapshot failed validation: {source}")


def check_zip(path: Path, required: tuple[str, ...]) -> None:
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        if archive.testzip() is not None:
            raise BackupError(f"ZIP integrity check failed: {path}")
        missing = [name for name in required if name not in names]
        if missing:
            raise BackupError(f"ZIP is missing required entries: {', '.join(missing)}")
