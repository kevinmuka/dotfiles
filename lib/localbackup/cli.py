"""Command-line entry point for local application backups."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__, config, progress, restore, scheduler, terminal
from .apps import discover
from .common import BackupError, app_lock


def parser() -> argparse.ArgumentParser:
    apps = discover()
    result = argparse.ArgumentParser(
        prog="localbackup", description="Create and manage local archives for macbackup to transfer later."
    )
    result.add_argument("--version", action="version", version=f"localbackup {__version__}")
    result.add_argument("--config", type=Path, default=config.default_path(), help="TOML configuration file")
    commands = result.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List supported applications")
    listing.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    initialize = commands.add_parser("init", help="Create an editable TOML configuration")
    initialize.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    for name, help_text in (
        ("now", "Create a backup now without changing the schedule"),
        ("run", "Alias for now"),
        ("start", "Back up now and enable the configured schedule"),
    ):
        command = commands.add_parser(name, help=help_text)
        app_commands = command.add_subparsers(dest="app", required=True)
        for app in (*apps, "all"):
            app_command = app_commands.add_parser(app, help=f"{app} local backup")
            if name in ("now", "run"):
                if app != "all":
                    app_command.add_argument("--output-dir", type=Path, help="Archive directory for this run")
                    for option in apps[app].now_options:
                        option.add_to(app_command)
                app_command.add_argument("--keep", type=int, help="Archives to retain per type")
            app_command.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    for name, help_text in (
        ("stop", "Disable automatic backups without removing archives"),
        ("status", "Show LaunchAgent and configured schedule status"),
        ("archives", "List existing local archives"),
    ):
        command = commands.add_parser(name, help=help_text)
        if name == "stop":
            command.add_argument("app", choices=(*apps, "all"), help="Application to stop, or all")
        else:
            command.add_argument("app", nargs="?", choices=(*apps, "all"), default="all")
        command.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    recovering = commands.add_parser("restore", help="Validate an archive or restore it explicitly")
    restore_apps = recovering.add_subparsers(dest="app", required=True)
    for app, plugin in apps.items():
        app_command = restore_apps.add_parser(
            app,
            help=f"Restore {app} settings",
            epilog="Relative archive paths start in the configured directory for that archive type.",
        )
        for option in plugin.restore_options:
            option.add_to(app_command)
        app_command.add_argument("--apply", action="store_true", help="Replace current settings after validation")
        app_command.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return result


def _selected(app: str) -> tuple[str, ...]:
    return tuple(discover()) if app == "all" else (app,)


def completion_spec() -> str:
    """Read-only, tab-separated metadata for Zsh; no configuration or backup is run."""
    rows = []
    for name, app in discover().items():
        rows.append(f"app\t{name}")
        for command, options in (("now", app.now_options), ("restore", app.restore_options)):
            for option in options:
                description = option.help.replace("\t", " ").replace("\n", " ")
                rows.append(f"option\t{command}\t{name}\t{option.flag}\t{option.kind}\t{description}")
    return "\n".join(rows)


def _config_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        raise BackupError("--config must be an absolute path or start with ~")
    return path


def _complete_archive(arguments: list[str]) -> int:
    # Private protocol for Zsh. This loads config but never executes an operation.
    if len(arguments) not in (2, 3):
        return 2
    app_name, flag, *alternate = arguments
    try:
        app = discover()[app_name]
        option = next(opt for opt in app.restore_options if opt.flag == flag and opt.kind == "archive")
        path = _config_path(Path(alternate[0]) if alternate else config.default_path())
        directory, suffix = restore.archive_location(app, config.load(path)[app.name], option)
    except (BackupError, KeyError, StopIteration, OSError, RuntimeError):
        return 1
    sys.stdout.buffer.write(os.fsencode(directory) + b"\0" + os.fsencode(suffix) + b"\0")
    return 0


def _backup_args(args: argparse.Namespace, app: str) -> argparse.Namespace:
    result = argparse.Namespace(**vars(args))
    for name in ("output_dir", "keep"):
        if not hasattr(result, name):
            setattr(result, name, None)
    for option in discover()[app].now_options:
        name = option.destination
        if not hasattr(result, name):
            setattr(result, name, False if option.kind == "bool" else None)
    return result


def _execute(args: argparse.Namespace) -> dict[str, object]:
    apps = discover()
    if args.command == "list":
        return {"apps": list(apps)}
    path = _config_path(args.config)
    if args.command == "init":
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(config.example())
            path.chmod(0o600)
        except FileExistsError as error:
            raise BackupError(f"Configuration already exists: {path}") from error
        return {"config": str(path), "created": True}
    settings = config.load(path) if args.command != "stop" else {}
    interactive = not args.json
    if args.command == "restore":
        app = apps[args.app]
        app_settings = settings[args.app]
        for option in app.restore_options:
            if option.kind == "archive" and (value := getattr(args, option.destination)) is not None:
                setattr(args, option.destination, restore.archive_argument(app, app_settings, option, value))
        label = "Restore" if args.apply else "Validate restore"
        with app_lock(args.app), progress.activity(f"{args.app} · {label}", enabled=interactive):
            result = app.restore(app_settings, args)
            return {"ok": True, **result}
    launcher = Path.home() / ".config/scripts/localbackup"
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    names = _selected(args.app)
    action = {
        "now": "Backup", "run": "Backup", "start": "Start automatic backups",
        "stop": "Stop automatic backups", "status": "Check schedule", "archives": "Find archives",
    }[args.command]
    for index, app in enumerate(names, 1):
        count = f" ({index}/{len(names)})" if len(names) > 1 else ""
        try:
            with progress.activity(f"{app}{count} · {action}", enabled=interactive):
                if args.command in ("now", "run", "start"):
                    if args.command == "start":
                        progress.phase("Checking schedule")
                        scheduler.preflight(app, settings[app], launcher, path)
                    with app_lock(app):
                        progress.phase("Creating archives")
                        archives = apps[app].backup(settings[app], _backup_args(args, app))
                        entry: dict[str, object] = {"app": app, "archives": archives}
                        if args.command == "start":
                            progress.phase("Applying schedule")
                            entry["schedule"] = scheduler.start(app, settings[app], launcher, path)
                elif args.command == "stop":
                    entry = scheduler.stop(app)
                elif args.command == "status":
                    entry = scheduler.status(app, settings[app], launcher, path)
                else:
                    entry = {"app": app, "archives": restore.archives(app, settings[app])}
            results.append(entry)
        except Exception as error:
            errors.append({"app": app, "message": str(error)})
    return {"ok": not errors, "results": results, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--completion-spec"]:
        print(completion_spec())
        return 0
    if argv[:1] == ["--completion-archive"]:
        return _complete_archive(argv[1:])
    args = parser().parse_args(argv)
    interrupted = False
    try:
        output = _execute(args)
    except KeyboardInterrupt:
        interrupted = True
        output = {"ok": False, "results": [], "errors": [
            {"app": getattr(args, "app", "localbackup"), "message": "Interrupted"},
        ]}
    except Exception as error:
        output = {"ok": False, "results": [], "errors": [
            {"app": getattr(args, "app", "localbackup"), "message": str(error)}
        ]}
    if getattr(args, "json", False):
        print(json.dumps(output))
    else:
        terminal.report(args.command, output, apply=getattr(args, "apply", False))
    if interrupted:
        return 130
    return 0 if output.get("ok", True) else 1
