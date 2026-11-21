"""Command-line entry point for local application backups."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__, config, restore, scheduler
from .apps import alfred, bartender
from .common import BackupError, app_lock


APPS = config.APPS


def parser() -> argparse.ArgumentParser:
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
        for app in (*APPS, "all"):
            app_command = app_commands.add_parser(app, help=f"{app} local backup")
            if name in ("now", "run"):
                if app != "all":
                    app_command.add_argument("--output-dir", type=Path, help="Archive directory for this run")
                if app == "alfred":
                    app_command.add_argument("--preferences-source", type=Path, help="Alfred Preferences source folder")
                app_command.add_argument("--keep", type=int, help="Archives to retain per type")
            app_command.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    for name, help_text in (
        ("stop", "Disable automatic backups without removing archives"),
        ("status", "Show LaunchAgent and configured schedule status"),
        ("archives", "List existing local archives"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("app", nargs="?", choices=(*APPS, "all"), default="all")
        command.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    recovering = commands.add_parser("restore", help="Validate an archive or restore it explicitly")
    restore_apps = recovering.add_subparsers(dest="app", required=True)
    for app in APPS:
        app_command = restore_apps.add_parser(app, help=f"Restore {app} settings")
        if app == "alfred":
            app_command.add_argument("--preferences", type=Path, help="Alfred Preferences .zip archive")
            app_command.add_argument("--workflow-data", type=Path, help="Alfred Workflow Data .zip archive")
        elif app == "bartender":
            app_command.add_argument("--archive", type=Path, help="Bartender settings .zip archive")
        app_command.add_argument("--apply", action="store_true", help="Replace current settings after validation")
        app_command.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return result


def _selected(app: str) -> tuple[str, ...]:
    return APPS if app == "all" else (app,)


def _backup(app: str, settings: config.AppConfig, args: argparse.Namespace) -> list[dict[str, str]]:
    output = getattr(args, "output_dir", None) or settings.output_dir
    keep = getattr(args, "keep", None)
    keep = settings.keep if keep is None else keep
    if app == "alfred":
        return alfred.backup(
            preferences_dir=output,
            preferences_source=getattr(args, "preferences_source", None) or settings.preferences_source,
            keep=keep,
        )
    return bartender.backup(output_dir=output, keep=keep)


def _execute(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "list":
        return {"apps": list(APPS)}
    path = args.config.expanduser()
    if not path.is_absolute():
        raise BackupError("--config must be an absolute path or start with ~")
    if args.command == "init":
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(config.example())
            path.chmod(0o600)
        except FileExistsError as error:
            raise BackupError(f"Configuration already exists: {path}") from error
        return {"config": str(path), "created": True}
    if args.command == "restore":
        if args.app == "bartender" and args.archive is None:
            raise BackupError("Select --archive for Bartender")
    settings = config.load(path) if args.command != "stop" else {}
    if args.command == "restore":
        with app_lock(args.app):
            if args.app == "alfred":
                result = restore.restore_alfred(
                    settings["alfred"], preferences=args.preferences,
                    workflow_data=args.workflow_data, apply=args.apply,
                )
            else:
                result = restore.restore_bartender(settings["bartender"], archive=args.archive, apply=args.apply)
            return {"ok": True, **result}
    launcher = Path.home() / ".config/scripts/localbackup"
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for app in _selected(args.app):
        try:
            if args.command in ("now", "run", "start"):
                if args.command == "start":
                    scheduler.preflight(app, settings[app], launcher, path)
                with app_lock(app):
                    archives = _backup(app, settings[app], args)
                    entry: dict[str, object] = {"app": app, "archives": archives}
                    if args.command == "start":
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
    args = parser().parse_args(argv)
    try:
        output = _execute(args)
    except Exception as error:
        output = {"ok": False, "results": [], "errors": [
            {"app": getattr(args, "app", "localbackup"), "message": str(error)}
        ]}
    if getattr(args, "json", False):
        print(json.dumps(output))
    elif "errors" in output and output["errors"]:
        for error in output["errors"]:
            print(f"localbackup: {error['app']}: {error['message']}", file=sys.stderr)
        for result in output.get("results", []):
            print(json.dumps(result, indent=2))
    elif args.command == "list":
        print("\n".join(output["apps"]))
    elif args.command == "init":
        print(output["config"])
    else:
        for result in output.get("results", [output]):
            print(json.dumps(result, indent=2))
    return 0 if output.get("ok", True) else 1
