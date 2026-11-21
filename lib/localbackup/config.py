"""Read the user-owned TOML configuration for local backups."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib

from .common import BackupError


APPS = ("alfred", "bartender")
WEEKDAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
DEFAULT_ROOT_RELATIVE = Path(".backups")
DEFAULT_ROOT = "~/" + DEFAULT_ROOT_RELATIVE.as_posix()
DEFAULT_SUBDIRS = {
    "alfred": "apps/customization/alfred/preferences",
    "bartender": "apps/customization/bartender",
}


def default_output_dir(app: str, home: Path | None = None) -> Path:
    return (home or Path.home()) / DEFAULT_ROOT_RELATIVE / DEFAULT_SUBDIRS[app]


@dataclass(frozen=True)
class Schedule:
    frequency: str
    time: str
    weekday: str

    def calendar(self) -> dict[str, int]:
        hour, minute = map(int, self.time.split(":"))
        interval = {"Hour": hour, "Minute": minute}
        if self.frequency == "weekly":
            interval["Weekday"] = WEEKDAYS.index(self.weekday)
        return interval


@dataclass(frozen=True)
class AppConfig:
    output_dir: Path
    keep: int
    schedule: Schedule
    preferences_source: Path | None = None


def default_path() -> Path:
    return Path.home() / ".config/localbackup/config.toml"


def example() -> str:
    return '''# localbackup creates local archives. It never sends them to the cloud.
# Run "localbackup start all" to make these schedules active.

[storage]
root_dir = "~/.backups"

[alfred]
subdir = "apps/customization/alfred/preferences"
keep = 12
# preferences_source = "~/Library/Application Support/Alfred/Alfred.alfredpreferences"

[alfred.schedule]
frequency = "weekly" # daily, weekly, or off
weekday = "monday"   # used only for weekly schedules
time = "03:00"       # 24-hour local time

[bartender]
subdir = "apps/customization/bartender"
keep = 12

[bartender.schedule]
frequency = "weekly"
weekday = "monday"
time = "03:15"
'''


def _table(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BackupError(f"{where} must be a TOML table")
    return value


def _keys(table: dict[str, object], allowed: set[str], where: str) -> None:
    unknown = set(table) - allowed
    if unknown:
        raise BackupError(f"Unknown {where} setting: {', '.join(sorted(unknown))}")


def _path(value: object, where: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BackupError(f"{where} must be a nonempty path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise BackupError(f"{where} must be an absolute path or start with ~")
    return path


def _subdir(value: object, where: str) -> Path:
    if not isinstance(value, str) or not value or value.startswith("~") or "\\" in value:
        raise BackupError(f"{where} must be a nonempty relative folder")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise BackupError(f"{where} must stay inside storage.root_dir")
    return path


def load(path: Path | None = None) -> dict[str, AppConfig]:
    path = (path or default_path()).expanduser()
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise BackupError(f"Configuration must be a regular file: {path}")
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            raise BackupError(f"Could not read configuration: {error}") from error
    else:
        raw = {}
    _keys(raw, {*APPS, "storage"}, "top-level")
    storage = _table(raw.get("storage", {}), "storage")
    _keys(storage, {"root_dir"}, "storage")
    root = _path(storage.get("root_dir", DEFAULT_ROOT), "storage.root_dir")
    result = {}
    for app in APPS:
        table = _table(raw.get(app, {}), app)
        allowed = {"subdir", "keep", "schedule"}
        if app == "alfred":
            allowed.add("preferences_source")
        _keys(table, allowed, app)
        output_dir = root / _subdir(table.get("subdir", DEFAULT_SUBDIRS[app]), f"{app}.subdir")
        keep = table.get("keep", 12)
        if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
            raise BackupError(f"{app}.keep must be a positive integer")
        schedule_table = _table(table.get("schedule", {}), f"{app}.schedule")
        _keys(schedule_table, {"frequency", "weekday", "time"}, f"{app}.schedule")
        frequency = schedule_table.get("frequency", "weekly")
        weekday = schedule_table.get("weekday", "monday")
        clock = schedule_table.get("time", "03:00" if app == "alfred" else "03:15")
        if frequency not in ("daily", "weekly", "off"):
            raise BackupError(f"{app}.schedule.frequency must be daily, weekly, or off")
        if weekday not in WEEKDAYS:
            raise BackupError(f"{app}.schedule.weekday must be an English weekday")
        if not isinstance(clock, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock):
            raise BackupError(f"{app}.schedule.time must be HH:MM in 24-hour format")
        source = table.get("preferences_source")
        result[app] = AppConfig(
            output_dir=output_dir,
            keep=keep,
            schedule=Schedule(frequency, clock, weekday),
            preferences_source=_path(source, "alfred.preferences_source") if source is not None else None,
        )
    locations = (
        result["alfred"].output_dir,
        result["alfred"].output_dir.parent / "workflow-data",
        result["bartender"].output_dir,
    )
    if len(set(locations)) != len(locations):
        raise BackupError("Application archive folders must be distinct")
    return result
