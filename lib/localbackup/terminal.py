"""Human-readable reports and terminal colors for localbackup."""

from __future__ import annotations

import os
import sys


COLORS = {
    "info": "1;36", "success": "1;32", "warning": "1;33", "error": "1;31",
    "subtle": "2;90", "path": "2", "bar": "34",
}


def plain(value: object) -> str:
    # Paths and error messages may contain literal terminal control characters.
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in str(value))


def style(value: object, kind: str, stream=None) -> str:
    stream = sys.stdout if stream is None else stream
    label = plain(value)
    python_colors = os.environ.get("PYTHON_COLORS")
    if stream.isatty() and python_colors != "0" and (
        python_colors == "1" or (
            not os.environ.get("NO_COLOR")
            and (os.environ.get("FORCE_COLOR") or os.environ.get("TERM") != "dumb")
        )
    ):
        return f"\x1b[{COLORS[kind]}m{label}\x1b[0m"
    return label


def kind_name(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").capitalize()


def field(label: str, value: object, kind: str = "path") -> None:
    print(f"  {style(label, 'subtle')} {style(value, kind)}")


def schedule_text(entry: dict) -> str:
    frequency = entry.get("configured")
    if frequency == "weekly":
        return f"Every {entry['weekday'].capitalize()} at {entry['time']}"
    if frequency == "daily":
        return f"Daily at {entry['time']}"
    return "Off"


def schedule(entry: dict) -> None:
    from .apps import discover

    if entry["loaded"]:
        state, tone = "Active", "success"
    elif entry["installed"]:
        state, tone = "Installed but inactive", "warning"
    else:
        state, tone = "Stopped", "subtle"
    field("LaunchAgent", state, tone)
    field("Configured schedule", schedule_text(entry), "info")
    if (entry["loaded"] or entry["installed"]) and not entry["matches_config"]:
        field("Warning", "LaunchAgent differs from configuration. Run start to apply it, or stop to disable it.", "warning")
    for key, label in discover()[entry["app"]].conflicting_agents.items():
        if entry.get(key):
            field("Warning", f"Conflicting LaunchAgent is active: {label}", "warning")


def archives(entries: list[dict]) -> None:
    for item in entries:
        detail = f" ({item['modified'].replace('T', ' ', 1).split('.')[0]})" if "modified" in item else ""
        field(kind_name(item["kind"]) + detail, item["path"])


def restore(entry: dict, apply: bool) -> None:
    apply = entry.get("apply", apply)
    label, tone = ("Restore complete", "success") if apply else ("Restore preview", "info")
    print(f"{style(label, tone)}  {style(entry['app'], 'info')}")
    handled = {"app", "ok", "apply", "targets", "archive", "destination", "previous_copy", "previous_copies"}
    paths = entry.get("targets", [entry])
    for item in paths:
        if "kind" in item:
            field("Settings", kind_name(item["kind"]), "info")
        for key in ("archive", "destination"):
            if key in item:
                field(kind_name(key), item[key])
    for path in entry.get("previous_copies", []):
        field("Previous copy", path)
    if "previous_copy" in entry:
        field("Previous copy", entry["previous_copy"])
    for key, value in entry.items():
        if key not in handled:
            field(kind_name(key), value)
    if not apply:
        field("Apply", "Run again with --apply to replace current settings.", "warning")


def report(command: str, output: dict, *, apply: bool = False) -> None:
    if command == "list" and "apps" in output:
        print(style("Supported applications", "info"))
        for name in output.get("apps", []):
            print(f"  {style(name, 'path')}")
    elif command == "init" and output.get("created"):
        print(style("Configuration created", "success"))
        field("Config", output["config"])
    elif command == "restore" and output.get("ok"):
        restore(output, apply)
    for entry in output.get("results", []):
        name = style(entry["app"], "info")
        if command in ("now", "run", "start"):
            print(f"{style('Backup complete', 'success')}  {name}")
            archives(entry["archives"])
            if "schedule" in entry:
                schedule(entry["schedule"])
        elif command == "status":
            print(f"{style('Schedule status', 'info')}  {name}")
            schedule(entry)
        elif command == "stop":
            print(f"{style('Automatic backups stopped', 'success')}  {name}")
        elif command == "archives":
            entries = entry["archives"]
            print(f"{style('Archives', 'info')}  {name}  {style(f'({len(entries)})', 'subtle')}")
            if entries:
                archives(entries)
            else:
                print(f"  {style('No archives found.', 'subtle')}")
    sys.stdout.flush()
    for error in output.get("errors", []):
        label = style("ERROR:", "error", sys.stderr)
        app = style(error["app"], "info", sys.stderr)
        print(f"{label} {app}: {plain(error['message'])}", file=sys.stderr)
