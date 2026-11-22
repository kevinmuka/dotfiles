"""Manage one user LaunchAgent per local backup module."""

from __future__ import annotations

from pathlib import Path
import os
import plistlib
import subprocess
import sys
import tempfile

from .common import BackupError, restricted_directory
from .config import AppConfig


def label(app: str) -> str:
    return f"com.localbackup.user{os.getuid()}.{app}"


def plist_path(app: str, home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library/LaunchAgents" / f"{label(app)}.plist"


def service(app: str) -> str:
    return f"gui/{os.getuid()}/{label(app)}"


def _loaded(name: str) -> bool:
    return subprocess.run(
        ["/bin/launchctl", "print", f"gui/{os.getuid()}/{name}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def _launchctl(*args: str) -> None:
    result = subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True)
    if result.returncode:
        raise BackupError(result.stderr.strip() or f"launchctl {args[0]} failed")


def agent(app: str, config: AppConfig, launcher: Path, config_path: Path, python: str | None = None) -> dict[str, object]:
    if config.schedule.frequency == "off":
        raise BackupError(f"{app} has no automatic schedule; change its TOML frequency")
    logs = Path.home() / "Library/Logs/localbackup"
    return {
        "Label": label(app),
        "ProgramArguments": [python or sys.executable, str(launcher), "--config", str(config_path), "now", app, "--json"],
        "StartCalendarInterval": config.schedule.calendar(),
        "StandardOutPath": str(logs / f"{app}.out.log"),
        "StandardErrorPath": str(logs / f"{app}.err.log"),
        "RunAtLoad": False,
    }


def preflight(app: str, config: AppConfig, launcher: Path, config_path: Path) -> None:
    from .apps import discover

    for name in discover()[app].conflicting_agents.values():
        if _loaded(name):
            raise BackupError(f"A conflicting schedule is loaded: {name}; stop it before enabling localbackup")
    if not launcher.is_file():
        raise BackupError(f"localbackup launcher is unavailable: {launcher}")
    agent(app, config, launcher, config_path)


def start(app: str, config: AppConfig, launcher: Path, config_path: Path) -> dict[str, object]:
    preflight(app, config, launcher, config_path)
    expected = agent(app, config, launcher, config_path)
    path = plist_path(app)
    if path.is_symlink():
        raise BackupError(f"LaunchAgent path must not be a symbolic link: {path}")
    old_bytes = path.read_bytes() if path.exists() else None
    if old_bytes is not None:
        try:
            previous = plistlib.loads(old_bytes)
        except (ValueError, TypeError) as error:
            raise BackupError(f"Could not read existing LaunchAgent: {error}") from error
        if previous.get("Label") != label(app):
            raise BackupError(f"Refusing to replace a different LaunchAgent: {path}")
    was_loaded = _loaded(label(app))
    if old_bytes is not None and plistlib.loads(old_bytes) == expected and was_loaded:
        return status(app, config, launcher, config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    restricted_directory(Path.home() / "Library/Logs/localbackup")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{label(app)}-", delete=False) as stream:
        pending = Path(stream.name)
        os.chmod(pending, 0o600)
        plistlib.dump(expected, stream)
    try:
        if was_loaded:
            _launchctl("bootout", service(app))
        os.replace(pending, path)
        try:
            _launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
        except BackupError:
            if old_bytes is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old_bytes)
                os.chmod(path, 0o600)
                if was_loaded:
                    _launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
            raise
    finally:
        pending.unlink(missing_ok=True)
    return status(app, config, launcher, config_path)


def stop(app: str) -> dict[str, object]:
    path = plist_path(app)
    if path.is_symlink():
        raise BackupError(f"LaunchAgent path must not be a symbolic link: {path}")
    if path.exists():
        try:
            if plistlib.loads(path.read_bytes()).get("Label") != label(app):
                raise BackupError(f"Refusing to remove a different LaunchAgent: {path}")
        except (ValueError, TypeError) as error:
            raise BackupError(f"Could not read existing LaunchAgent: {error}") from error
    if _loaded(label(app)):
        _launchctl("bootout", service(app))
    path.unlink(missing_ok=True)
    return {"app": app, "loaded": False, "installed": False}


def status(app: str, config: AppConfig, launcher: Path, config_path: Path) -> dict[str, object]:
    from .apps import discover

    path = plist_path(app)
    actual = None
    if path.is_file() and not path.is_symlink():
        try:
            actual = plistlib.loads(path.read_bytes())
        except (ValueError, TypeError, OSError):
            pass
    loaded = _loaded(label(app))
    expected = agent(app, config, launcher, config_path) if config.schedule.frequency != "off" else None
    result = {
        "app": app,
        "loaded": loaded,
        "installed": path.exists(),
        "configured": config.schedule.frequency,
        "time": config.schedule.time,
        "weekday": config.schedule.weekday if config.schedule.frequency == "weekly" else None,
        "matches_config": actual == expected if actual is not None else False,
    }
    result.update({key: _loaded(name) for key, name in discover()[app].conflicting_agents.items()})
    return result
