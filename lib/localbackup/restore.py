"""Validate local archives and restore settings with a recoverable old copy."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path, PurePosixPath
import os
import plistlib
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import quote
from zipfile import ZipFile

from .apps import alfred, bartender
from .common import BackupError, check_zip, restricted_directory
from .config import AppConfig


def _safe_name(name: str, root: str) -> tuple[str, ...] | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or "\x00" in name:
        raise BackupError(f"Archive contains an unsafe path: {name}")
    if path.parts == ("._" + root,):
        return None  # macOS metadata for the archive root
    if not path.parts or path.parts[0] != root:
        raise BackupError(f"Archive has an unexpected root: {name}")
    return path.parts[1:]


def _parent(destination: Path, root: Path) -> None:
    relative = destination.relative_to(root)
    cursor = root
    for part in relative.parts[:-1]:
        cursor /= part
        if cursor.is_symlink():
            raise BackupError(f"Archive tries to write through a symbolic link: {cursor}")
        cursor.mkdir(exist_ok=True)


def _extract_zip_tree(source: Path, destination: Path, root: str) -> None:
    destination.mkdir()
    count = 0
    directory_modes = []
    with ZipFile(source) as archive:
        if archive.testzip() is not None:
            raise BackupError("ZIP integrity check failed")
        for member in archive.infolist():
            relative = _safe_name(member.filename, root)
            if relative is None or not relative:
                continue
            target = destination.joinpath(*relative)
            _parent(target, destination)
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if member.is_dir():
                if target.is_symlink():
                    raise BackupError(f"Archive tries to write through a symbolic link: {member.filename}")
                target.mkdir(exist_ok=True)
                if mode & 0o777:
                    directory_modes.append((target, mode & 0o777))
                continue
            if target.exists() or target.is_symlink():
                raise BackupError(f"Duplicate archive entry: {member.filename}")
            if kind == stat.S_IFLNK:
                target.symlink_to(archive.read(member).decode("utf-8"))
            elif kind in (0, stat.S_IFREG):
                with target.open("xb") as output, archive.open(member) as input_file:
                    shutil.copyfileobj(input_file, output)
                if mode & 0o777:
                    target.chmod(mode & 0o777)
                count += 1
            else:
                raise BackupError(f"Unsupported ZIP entry: {member.filename}")
    for directory, mode in reversed(directory_modes):
        directory.chmod(mode)
    if count == 0:
        raise BackupError("ZIP contains no files")


def _app_running(app: str) -> bool:
    names = ("Alfred", "Alfred Preferences") if app == "alfred" else ("Bartender", "Bartender 7")
    for name in names:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-x", name], capture_output=True, text=True,
        )
        if result.returncode == 0:
            return True
        if result.returncode != 1:
            raise BackupError(f"Could not check whether {app} is running: {result.stderr.strip()}")
    return False


def _archive(path: Path, suffix: str) -> Path:
    path = path.expanduser()
    if path.is_symlink() or not path.is_file() or path.suffix != suffix:
        raise BackupError(f"Expected a regular {suffix} archive: {path}")
    return path


def archives(app: str, config: AppConfig) -> list[dict[str, str]]:
    if app == "alfred":
        sources = (
            ("preferences", config.output_dir, alfred.PREFERENCES_PREFIX, ".zip"),
            ("workflow_data", config.output_dir.parent / "workflow-data", alfred.DATA_PREFIX, ".zip"),
        )
    else:
        sources = (("settings", config.output_dir, bartender.ARCHIVE_PREFIX, ".zip"),)
    result = []
    for kind, directory, prefix, suffix in sources:
        if not directory.is_dir():
            continue
        for path in directory.glob(f"{prefix}*{suffix}"):
            if path.is_file() and not path.is_symlink():
                result.append({"kind": kind, "path": str(path), "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat()})
    return sorted(result, key=lambda item: item["modified"], reverse=True)


def _replace_tree(target: Path, staged: Path, token: str) -> Path | None:
    old = target.with_name(f"{target.name}.before-localbackup-{token}") if target.exists() else None
    if old is not None:
        if old.exists():
            raise BackupError(f"Previous restore copy already exists: {old}")
        os.replace(target, old)
    try:
        os.replace(staged, target)
    except Exception:
        if old is not None:
            os.replace(old, target)
        raise
    return old


def restore_alfred(
    config: AppConfig, *, preferences: Path | None, workflow_data: Path | None, apply: bool,
    home: Path | None = None,
) -> dict[str, object]:
    if preferences is None and workflow_data is None:
        raise BackupError("Select --preferences and/or --workflow-data")
    home = home or Path.home()
    base = home / "Library/Application Support/Alfred"
    targets = []
    if preferences is not None:
        source = _archive(preferences, ".zip")
        target = config.preferences_source or base / alfred.PREFERENCES_ROOT
        targets.append(("preferences", source, target))
    if workflow_data is not None:
        source = _archive(workflow_data, ".zip")
        targets.append(("workflow_data", source, base / "Workflow Data"))
    for _, _, target in targets:
        if target.is_symlink():
            raise BackupError(f"Refusing to replace a symbolic link: {target}")
        if target.exists() and not target.is_dir():
            raise BackupError(f"Expected a settings directory: {target}")
    plan = {"app": "alfred", "apply": apply, "targets": [
        {"kind": kind, "archive": str(source), "destination": str(target)}
        for kind, source, target in targets
    ]}
    if apply and _app_running("alfred"):
        raise BackupError("Quit Alfred and Alfred Preferences before restoring")
    staged = []
    try:
        for kind, source, target in targets:
            if apply:
                target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="localbackup-restore-") as temporary:
                extracted = Path(temporary) / "extract"
                if kind == "preferences":
                    _extract_zip_tree(source, extracted, alfred.PREFERENCES_ROOT)
                    staged_source = extracted
                else:
                    _extract_zip_tree(source, extracted, alfred.DATA_ROOT)
                    staged_source = extracted / "Workflow Data"
                    if not staged_source.is_dir():
                        raise BackupError("Workflow Data archive is missing its data folder")
                if apply:
                    persistent = Path(tempfile.mkdtemp(prefix=f".{target.name}.localbackup-", dir=target.parent))
                    shutil.rmtree(persistent)
                    shutil.copytree(staged_source, persistent, symlinks=True)
                    staged.append((target, persistent))
        if apply:
            token = datetime.now().strftime("%Y%m%d-%H%M%S")
            replaced = []
            try:
                for target, staged_source in staged:
                    old = _replace_tree(target, staged_source, token)
                    replaced.append((target, old))
            except Exception:
                for target, old in reversed(replaced):
                    if target.exists():
                        shutil.rmtree(target)
                    if old is not None:
                        os.replace(old, target)
                raise
            plan["previous_copies"] = [str(old) for _, old in replaced if old is not None]
    finally:
        for _, path in staged:
            if path.exists():
                shutil.rmtree(path)
    return plan


def restore_bartender(
    config: AppConfig, *, archive: Path, apply: bool, home: Path | None = None,
) -> dict[str, object]:
    source = _archive(archive, ".zip")
    home = home or Path.home()
    target = home / "Library/Group Containers" / bartender.GROUP_CONTAINER / "Library/Application Support/default.store"
    if target.is_symlink() or not target.parent.is_dir():
        raise BackupError("Bartender settings destination is missing or is a symbolic link")
    if apply and _app_running("bartender"):
        raise BackupError("Quit Bartender and its Settings window before restoring")
    with ZipFile(source) as contents:
        required = (
            f"{bartender.ARCHIVE_ROOT}/Preferences/{bartender.DOMAIN}.plist",
            f"{bartender.ARCHIVE_ROOT}/Group Containers/{bartender.GROUP_CONTAINER}/Library/Application Support/default.store",
        )
        if contents.testzip() is not None or any(name not in contents.namelist() for name in required):
            raise BackupError("Bartender archive is incomplete or damaged")
        preferences = contents.read(required[0])
        if not isinstance(plistlib.loads(preferences), dict):
            raise BackupError("Bartender preferences are invalid")
        database_bytes = contents.read(required[1])
    import sqlite3
    with tempfile.TemporaryDirectory(prefix="localbackup-bartender-restore-") as temporary:
        staged = Path(temporary) / "default.store"
        staged.write_bytes(database_bytes)
        uri = "file:" + quote(str(staged), safe="/") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BackupError("Bartender database failed validation")
        plan = {"app": "bartender", "apply": apply, "archive": str(source), "destination": str(target)}
        if not apply:
            return plan
        token = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_root = restricted_directory(config.output_dir / "pre-restore")
        safety = Path(tempfile.mkdtemp(prefix=f"{token}-", dir=safety_root))
        safety.chmod(0o700)
        previous_preferences = subprocess.run(
            ["/usr/bin/defaults", "export", bartender.DOMAIN, "-"], capture_output=True, check=True,
        ).stdout
        (safety / "preferences.plist").write_bytes(previous_preferences)
        for name in ("default.store", "default.store-wal", "default.store-shm"):
            existing = target.with_name(name)
            if existing.exists():
                shutil.copy2(existing, safety / name)
        staged_preferences = Path(temporary) / "preferences.plist"
        staged_preferences.write_bytes(preferences)
        descriptor, replacement_name = tempfile.mkstemp(prefix=".default.store.localbackup-", dir=target.parent)
        os.close(descriptor)
        replacement = Path(replacement_name)
        try:
            subprocess.run(["/usr/bin/defaults", "import", bartender.DOMAIN, str(staged_preferences)], check=True)
            shutil.copy2(staged, replacement)
            for suffix in ("-wal", "-shm"):
                target.with_name("default.store" + suffix).unlink(missing_ok=True)
            os.replace(replacement, target)
        except Exception:
            subprocess.run(["/usr/bin/defaults", "import", bartender.DOMAIN, str(safety / "preferences.plist")], check=False)
            for name in ("default.store", "default.store-wal", "default.store-shm"):
                saved = safety / name
                if saved.exists():
                    shutil.copy2(saved, target.with_name(name))
            raise
        finally:
            replacement.unlink(missing_ok=True)
        plan["previous_copy"] = str(safety)
        return plan
