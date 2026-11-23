# Writing an application module

This guide builds a complete `exampleapp` module. It covers discovery,
configuration, manual and scheduled backups, archive listing, restore,
completion, tests, and deployment. Replace the example paths and process name
with facts verified for the real application. A module cannot infer every
setting an application uses: first decide what “complete” means for that app.

## 1. Inventory the application

Locate its configuration, databases, exported settings, and any additional
state needed on a new Mac. Check whether the app offers a native export, whether
it must be quit before copying files, and whether SQLite databases may be open.
Identify data that cannot be restored from files alone, such as Keychain items,
licenses, macOS permissions, or server-side accounts. Record the app versions
for which the backup and restore were tested. Keep cache and temporary files
out of the archive unless they are actually needed for recovery.

The example below assumes all recoverable settings are regular files beneath
`~/Library/Application Support/ExampleApp/`, and that the app is not writing
them during backup. **That assumption is app-specific.** For live SQLite data,
use `sqlite_snapshot` from `lib.localbackup.common` to capture committed data,
including WAL transactions, instead of copying the database file directly.
For a native export, capture and validate that export instead. Do not use the
example unchanged for an app with either of those requirements.

## 2. Add one module

Create `lib/localbackup/apps/exampleapp.py` with the following content. The
filename and `APP.name` must match. Public `.py` files in `apps/` are discovered
automatically; helper modules should start with `_`.

```python
"""Back up ExampleApp's file-based settings."""

from datetime import datetime
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from ..archive import validate_zip
from ..common import BackupError, archive_path, prune, restricted_directory
from ._api import App, Option


ROOT = "ExampleApp Backup"
PREFIX = "ExampleApp Settings "
DEFAULT_SOURCE = Path.home() / "Library/Application Support/ExampleApp"


def _source(settings, override=None):
    return override or settings.options.get("source") or DEFAULT_SOURCE


def backup(settings, args):
    source = _source(settings, args.source)
    if not source.is_dir() or source.is_symlink():
        raise BackupError(f"ExampleApp settings folder is unavailable: {source}")
    entries = list(source.rglob("*"))
    if not any(path.is_file() for path in entries):
        raise BackupError("ExampleApp settings folder contains no files")
    if any(path.is_symlink() or not (path.is_dir() or path.is_file()) for path in entries):
        raise BackupError("ExampleApp settings contain a link or special file")

    keep = settings.keep if args.keep is None else args.keep
    if keep < 1:
        raise BackupError("The retention count must be at least 1")
    directory = restricted_directory(args.output_dir or settings.output_dir)
    output = archive_path(directory, PREFIX, ".zip", datetime.now())
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".exampleapp-", delete=False) as stream:
        pending = Path(stream.name)
    try:
        pending.chmod(0o600)
        with ZipFile(pending, "w", ZIP_DEFLATED) as archive:
            archive.writestr(ROOT + "/", b"")
            archive.writestr(
                ROOT + "/README.txt",
                "ExampleApp settings backup. Quit ExampleApp before restoring. "
                "The Settings folder belongs at ~/Library/Application Support/ExampleApp/.\n",
            )
            archive.write(source, ROOT + "/Settings/")
            for path in entries:
                archive.write(path, ROOT + "/Settings/" + path.relative_to(source).as_posix())
        validate_zip(pending, ROOT)
        os.replace(pending, output)
    finally:
        pending.unlink(missing_ok=True)
    prune(directory, PREFIX, ".zip", keep)
    return [{"kind": "settings", "path": str(output)}]


def restore(settings, args):
    if args.archive is None:
        raise BackupError("Select --archive for ExampleApp")
    source = args.archive.expanduser()
    if source.is_symlink() or not source.is_file() or source.suffix != ".zip":
        raise BackupError(f"Expected a regular ZIP archive: {source}")
    validate_zip(source, ROOT)
    target = _source(settings)
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise BackupError(f"Unsafe ExampleApp destination: {target}")
    plan = {
        "app": "exampleapp", "apply": args.apply,
        "archive": str(source), "destination": str(target),
    }
    if args.apply:
        running = subprocess.run(
            ["/usr/bin/pgrep", "-x", "ExampleApp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        if running.returncode == 0:
            raise BackupError("Quit ExampleApp before restoring")
        if running.returncode != 1:
            raise BackupError(f"Could not check ExampleApp process: {running.stderr.strip()}")
        target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="localbackup-exampleapp-",
        dir=target.parent if args.apply else None,
    ) as temporary:
        with ZipFile(source) as archive:
            if any(stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK
                   for item in archive.infolist()):
                raise BackupError("ExampleApp archive contains a symbolic link")
            archive.extractall(temporary)
        staged = Path(temporary) / ROOT / "Settings"
        if not staged.is_dir() or not any(path.is_file() for path in staged.rglob("*")):
            raise BackupError("ExampleApp archive is missing its settings")
        if not args.apply:
            return plan

        previous = target.with_name(
            f"{target.name}.before-localbackup-{datetime.now():%Y%m%d-%H%M%S}"
        )
        if previous.exists():
            raise BackupError(f"Previous restore copy already exists: {previous}")
        had_target = target.exists()
        if had_target:
            os.replace(target, previous)
        try:
            os.replace(staged, target)
        except Exception:
            if had_target:
                os.replace(previous, target)
            raise
        if had_target:
            plan["previous_copy"] = str(previous)
        return plan


def archive_sources(settings):
    return (("settings", settings.output_dir, PREFIX, ".zip"),)


def parse_config(table):
    from ..config import path_setting

    if "source" not in table:
        return {}
    return {"source": path_setting(table["source"], "exampleapp.source")}


APP = App(
    name="exampleapp",
    default_subdir="apps/customization/exampleapp",
    default_time="03:30",
    example_config='''[exampleapp]
subdir = "apps/customization/exampleapp"
keep = 12
# source = "~/Library/Application Support/ExampleApp"

[exampleapp.schedule]
frequency = "weekly"
weekday = "monday"
time = "03:30"''',
    backup=backup,
    restore=restore,
    archive_sources=archive_sources,
    now_options=(Option("--source", "ExampleApp settings folder", "path"),),
    restore_options=(Option("--archive", "ExampleApp settings ZIP", "archive"),),
    config_keys=("source",),
    parse_config=parse_config,
)
```

The CLI supplies `args.output_dir`, `args.keep`, and the module's `now_options`
as `None` when absent, including for `start`. It supplies `args.apply` and the
module's `restore_options` for `restore`. A `backup` callback returns archive
records; a `restore` callback returns a plan or result dictionary. The app
module owns source selection, archive validation, restore safety, and any
app-specific configuration. `archive_sources` gives `localbackup archives`
the kind, directory, filename prefix, and extension to list. It also lets the
configuration parser detect archive-directory collisions between apps.

This example restores ordinary settings files with Python's ZIP extraction.
It does not preserve executable bits or other macOS metadata. If the app needs
those, use a format and extraction method that preserve them and test the
round trip; Alfred's module demonstrates a `ditto`-based archive. The example
also rejects links and special files rather than silently following them.

`Option.kind` may be `path`, `archive`, `int`, or `text`. It determines the
`argparse` value type and the completion style. Add app-specific options only
to `now_options` or `restore_options`; common `--output-dir`, `--keep`, `--apply`,
and `--json` are provided by the CLI. An app with an existing automatic backup
agent can set `conflicting_agents={"old_agent_loaded": "its.launchd.label"}`
on `APP`; `start` then refuses to create a second schedule while that label
is loaded, and `status` includes the named flag.

## 3. Configure and exercise it

The module is discovered as soon as it is in the `apps/` package used by the
launcher. `localbackup init` includes `APP.example_config` in a newly created
TOML file. An existing TOML need not gain an `[exampleapp]` section unless you
want to change its defaults; the shared `storage.root_dir` still applies.
Check that an existing config has no stale or misspelled app sections, because
unknown settings are rejected.

```sh
localbackup list
localbackup now exampleapp --help
localbackup restore exampleapp --help
localbackup --completion-spec
localbackup --config /absolute/path/test-config.toml now exampleapp --json
localbackup --config /absolute/path/test-config.toml archives exampleapp --json
localbackup --config /absolute/path/test-config.toml restore exampleapp \
  --archive "/path/to/ExampleApp Settings.zip" --json
```

Use a disposable home and app data for the first backup and restore. Inspect
the ZIP root, README, file list, CRC, and permissions. Compare restored files
with the source. Verify that the preview leaves the destination untouched,
that `--apply` keeps the previous settings, and that failures leave a usable
previous copy. Test missing, empty, unreadable, symlinked, and malformed input;
test while the app is running. The repository's `tests/localbackup/` contains
an isolated third-app registration test and examples of synthetic app data.
Run:

```sh
python3 -B -m unittest discover -s tests/localbackup -p 'test_*.py'
zsh -n home/.zsh/completions/_localbackup
git diff --check
```

For the example module, a focused test can exercise the actual archive and
restore callbacks without touching the user's app data. Put a test like this
under `tests/localbackup/` and run it with the command above:

```python
from argparse import Namespace
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from lib.localbackup.apps import exampleapp
from lib.localbackup.config import AppConfig, Schedule


class ExampleAppTests(TestCase):
    def test_backup_preview_and_restore(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "ExampleApp"
            source.mkdir()
            (source / "settings.json").write_text('{"theme":"old"}')
            settings = AppConfig(
                root / "archives", 2, Schedule("weekly", "03:30", "monday")
            )
            with patch.object(exampleapp, "DEFAULT_SOURCE", source):
                archive = Path(exampleapp.backup(
                    settings, Namespace(source=None, output_dir=None, keep=None)
                )[0]["path"])
                (source / "settings.json").write_text('{"theme":"new"}')
                args = Namespace(archive=archive, apply=False)
                preview = exampleapp.restore(settings, args)
                self.assertFalse(preview["apply"])
                self.assertEqual((source / "settings.json").read_text(), '{"theme":"new"}')
                args.apply = True
                with patch.object(
                    exampleapp.subprocess, "run",
                    return_value=CompletedProcess([], 1, "", ""),
                ):
                    result = exampleapp.restore(settings, args)
                self.assertEqual((source / "settings.json").read_text(), '{"theme":"old"}')
                self.assertEqual(
                    (Path(result["previous_copy"]) / "settings.json").read_text(),
                    '{"theme":"new"}',
                )
```

The process check is mocked only for synthetic data. For a real app, confirm
that the check detects a running process and fails safely if macOS cannot
report process state. Add cases for damaged ZIPs, missing sources, symlinks,
wrong app versions, interruption, retention, and any database or native-export
logic specific to the app.

Once its archive and restore have been verified, `localbackup start exampleapp`
performs one backup and installs its weekly LaunchAgent from the TOML schedule.
`status exampleapp` reports the agent; `now exampleapp` makes an extra backup
without changing the schedule; `stop exampleapp` removes the agent but keeps
archives. `now all` and `start all` include the new module automatically, so
review its source and defaults before using those aggregate commands. `restore`
requires explicit `--apply` to replace files. Scheduled runs use the launcher
and Python interpreter recorded by the LaunchAgent; after moving the checkout
or interpreter, run `start exampleapp` again to update it.

Zsh completion discovers the module through the launcher's read-only
`--completion-spec` path. The completion invokes Python locally on Tab but does
not read the TOML or run backups. Install the updated launcher, package, and
completion together; adding a module to a different checkout will not change
the installed command's app list.

Finally, inspect macbackup's separate source-selection and plain/private
classification for the new archive path before transferring it to cloud
storage. Adding a localbackup module does not update macbackup policy, make a
cloud copy, or prove that the app can be restored on another Mac. Perform a
manual restore rehearsal before relying on the archive.
