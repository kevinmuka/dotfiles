"""Read the user-owned TOML configuration for local backups."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib

from .common import BackupError


WEEKDAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
DEFAULT_ROOT_RELATIVE = Path(".backups")
DEFAULT_ROOT = "~/" + DEFAULT_ROOT_RELATIVE.as_posix()


def default_output_dir(app: str, home: Path | None = None) -> Path:
    from .apps import discover

    return (home or Path.home()) / DEFAULT_ROOT_RELATIVE / discover()[app].default_subdir


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
    options: dict[str, object] = field(default_factory=dict)


def default_path() -> Path:
    return Path.home() / ".config/localbackup/config.toml"


def example() -> str:
    from .apps import discover

    header = '''# localbackup creates local archives. It never sends them to the cloud.
# Run "localbackup start all" to make these schedules active.

[storage]
root_dir = "~/.backups"'''
    return header + "\n\n" + "\n\n".join(app.example_config for app in discover().values()) + "\n"


def _table(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BackupError(f"{where} must be a TOML table")
    return value


def _keys(table: dict[str, object], allowed: set[str], where: str) -> None:
    unknown = set(table) - allowed
    if unknown:
        raise BackupError(f"Unknown {where} setting: {', '.join(sorted(unknown))}")


def path_setting(value: object, where: str) -> Path:
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
    from .apps import discover

    apps = discover()
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
    _keys(raw, {*apps, "storage"}, "top-level")
    storage = _table(raw.get("storage", {}), "storage")
    _keys(storage, {"root_dir"}, "storage")
    root = path_setting(storage.get("root_dir", DEFAULT_ROOT), "storage.root_dir")
    result = {}
    for app, plugin in apps.items():
        table = _table(raw.get(app, {}), app)
        allowed = {"subdir", "keep", "schedule", *plugin.config_keys}
        _keys(table, allowed, app)
        output_dir = root / _subdir(table.get("subdir", plugin.default_subdir), f"{app}.subdir")
        keep = table.get("keep", 12)
        if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
            raise BackupError(f"{app}.keep must be a positive integer")
        schedule_table = _table(table.get("schedule", {}), f"{app}.schedule")
        _keys(schedule_table, {"frequency", "weekday", "time"}, f"{app}.schedule")
        frequency = schedule_table.get("frequency", "weekly")
        weekday = schedule_table.get("weekday", "monday")
        clock = schedule_table.get("time", plugin.default_time)
        if frequency not in ("daily", "weekly", "off"):
            raise BackupError(f"{app}.schedule.frequency must be daily, weekly, or off")
        if weekday not in WEEKDAYS:
            raise BackupError(f"{app}.schedule.weekday must be an English weekday")
        if not isinstance(clock, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock):
            raise BackupError(f"{app}.schedule.time must be HH:MM in 24-hour format")
        result[app] = AppConfig(
            output_dir=output_dir,
            keep=keep,
            schedule=Schedule(frequency, clock, weekday),
            options=plugin.parse_config(table),
        )
    locations = tuple(
        directory for name, plugin in apps.items()
        for _, directory, _, _ in plugin.archive_sources(result[name])
    )
    if len(set(locations)) != len(locations):
        raise BackupError("Application archive folders must be distinct")
    return result
