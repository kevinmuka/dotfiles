# localbackup

`localbackup` creates local, app-specific archives, restores them, and manages
optional user LaunchAgents. It does not contact a cloud service. Run
`macbackup` separately after the archives are ready.

The launcher is `~/.config/scripts/localbackup` when the dotfiles are installed.
The implementation lives in `lib/localbackup/`. Application modules are under
`lib/localbackup/apps/`; shared archive validation, configuration, restore,
scheduling, and CLI modules stay at the package root. The initial applications
are `alfred` and `bartender`. The command discovers application modules by
filename instead of maintaining an app-name list in the shared code.

## Requirements and installation

`localbackup` runs on macOS with Python 3.11 or later and uses only the Python
standard library. The built-in modules also use macOS `ditto`, `defaults`,
`pgrep`, `scutil`, and `launchctl`; Bartender backup requires Bartender 7 and
its local settings database. Run the launcher in this checkout to check the
interpreter and module discovery before installing it:

```sh
python3 --version
./home/.config/scripts/localbackup list
```

The launcher locates `lib/localbackup/` relative to its **resolved** file
path. Install it as a symlink to `home/.config/scripts/localbackup` in a
permanent checkout; copying only the launcher does not install the package.
The dotfiles root README explains the repository's symlink installer. For a
manual installation, from the permanent checkout and only if the destination
does not already exist:

```sh
mkdir -p "$HOME/.config/scripts"
ln -s "$PWD/home/.config/scripts/localbackup" "$HOME/.config/scripts/localbackup"
"$HOME/.config/scripts/localbackup" list
```

Inspect an existing destination before replacing it; `ln -s` will fail rather
than overwrite it. Use the full launcher path if `~/.config/scripts` is not in
`PATH`. Install the Zsh completion and integration from `home/.zsh/` if you
want Tab completion. Do not enable a LaunchAgent from a temporary checkout:
it records an absolute launcher and Python interpreter path.

Installing files or creating a TOML config does not start automatic backups.
Use `now APP` for a first manual backup and inspect its archive before using
`start APP` to enable a schedule.

```sh
localbackup list
localbackup now alfred
localbackup now bartender
localbackup now all
localbackup start all
localbackup status
localbackup stop all
localbackup archives alfred
```

All built-in commands and archive README files are in English. `run` remains
an alias for `now`. Commands with `--json` print one JSON object; failures use
a nonzero status. This makes `now` suitable for an Alfred Run Script action:

Place global `--config` before the command and `--json` after the command or
app name. Run `localbackup now alfred --help` or the corresponding app help to
see only valid flags. A successful operation exits with status 0, an operation
failure with 1, and an invalid command line with 2. For multi-app operations,
JSON contains `ok`, `results`, and `errors`; `list` and `init` have their own
small JSON shapes. Invalid command lines are reported by the argument parser,
not as JSON. Automation should check the exit status and inspect errors, not
infer success from the presence of some `results`.

```sh
"$HOME/.config/scripts/localbackup" now alfred --json
"$HOME/.config/scripts/localbackup" now bartender --json
```

The separate Alfred Backup Preferences workflow, if installed, has its own
backup implementation and schedule. This repository does not install or
update that workflow. Check its installed version and archive format
separately. If you connect its Run Script action to `localbackup`, pass the
workflow's configured preferences path and retention count:

```sh
"$HOME/.config/scripts/localbackup" now alfred \
  --preferences-source "$alfred_preferences" \
  --output-dir "$backup_target" \
  --keep "$backup_count" --json
```

## Alfred

`localbackup now alfred` creates two separate archives:

- `~/.backups/apps/customization/alfred/preferences/Alfred Backup ... .zip`
- `~/.backups/apps/customization/alfred/workflow-data/Alfred Workflow Data ... .zip`

The preferences ZIP keeps the `Alfred.alfredpreferences` root and executable
file permissions. Older TGZ files are left untouched on disk but are not
listed or accepted by `localbackup restore`. Whether a separate Alfred
workflow accepts them depends on that workflow's installed version. The
Workflow Data ZIP contains its own English README with a manual restore
procedure. Active SQLite
databases within Workflow Data are copied through SQLite's backup API. The
archives are verified before they are published, and 12 new ZIP versions of
each type are kept by default.

Alfred must use its local preferences folder for the default source to be
correct. If preferences live elsewhere, pass `--preferences-source PATH` or
set `alfred.preferences_source` in TOML. The Workflow Data source remains
`~/Library/Application Support/Alfred/Workflow Data/`; both source folders
must exist and cannot be symbolic links. There is no Workflow Data source
override at present.
Check the separately installed Alfred workflow's restore behavior independently.
`localbackup restore alfred` can restore preferences, Workflow Data, or both.

## Bartender

`localbackup now bartender` creates a ZIP in
`~/.backups/apps/customization/bartender/`. It contains a `defaults export` of
the Bartender preferences domain, a consistent snapshot of its group-container
SQLite database, and an English README with restore instructions. The archive
is a file-level fallback for Bartender 7. Bartender 7.1.0 and later provide a
native configuration export in Advanced settings, which is preferable for a
supported transfer between Macs. Bartender documents the export in its
[7.1.0 release notes](https://www.macbartender.com/Bartender7/release_notes/).

The app bundle, license, macOS permissions, caches, and Keychain items are not
part of this archive. Restoring may require the same Bartender version and new
permission grants. The built-in module currently checks for the app bundle at
`/Applications/Bartender 7.app` and reads its group-container database; it has
no CLI override for a different app-bundle location.

## Configuration and automatic backups

The configuration is `~/.config/localbackup/config.toml`. Run
`localbackup init` to create it when it does not exist. An alternate file can
be selected with `localbackup --config /absolute/path/config.toml COMMAND`.
`init` does not overwrite an existing file. If no config exists, commands use
the modules' defaults; use `init` when you want an editable starting point.

```toml
[storage]
root_dir = "~/.backups"

[alfred]
subdir = "apps/customization/alfred/preferences"
keep = 12

[alfred.schedule]
frequency = "weekly"
weekday = "monday"
time = "03:00"

[bartender]
subdir = "apps/customization/bartender"
keep = 12

[bartender.schedule]
frequency = "weekly"
weekday = "monday"
time = "03:15"
```

`storage.root_dir` is the single absolute base directory (or a path beginning
with `~`). Each app's `subdir` must be relative to that base; changing the
root moves all app destinations together. Alfred's Workflow Data ZIP goes
beside its preferences folder, under
`apps/customization/alfred/workflow-data`. The example retains the existing
archive locations. Changing this root does not update
macbackup's separate path policy; confirm that the new root is selected and
classified as intended before a cloud transfer. `--output-dir` is a one-run
override for a single app; it does not change the TOML or the automatic
schedule.

An app module may declare additional TOML keys. Put them in that app's table,
not in `[storage]`; the module validates them. Existing config files do not
need a new app table when its defaults are suitable. `localbackup init`
generates examples for all currently discovered modules, but it does not
merge new sections into an existing config.

`frequency` accepts `daily`, `weekly`, or `off`; the weekday applies only to
weekly schedules. The clock uses local time in 24-hour `HH:MM` form.
`alfred.preferences_source` is optional when Alfred uses its default local
preferences location. Unknown settings and invalid values fail before any
backup or schedule change.

`localbackup start APP` creates a backup immediately, then installs or updates
that app's user LaunchAgent. It refuses to start when `frequency = "off"` or
a declared conflicting agent is loaded. Use `all` to start every discovered
app. A later configuration change needs another `start` to update the loaded
agent; changing `frequency` to `off` in TOML does **not** unload an agent that
is already running. Use `stop APP` for that. `localbackup now APP` creates
one backup without changing any schedule. `localbackup stop APP` unloads and
removes only localbackup's LaunchAgent; it keeps archives. `status` reports
whether the agent is loaded, whether its file is installed, and whether it
matches the current TOML settings. A loaded calendar agent normally waits
between runs; this does not mean a backup process is active.

`now all`, `start all`, `stop all`, `status all`, and `archives all` process
apps individually. They are **not atomic**: one app may succeed while another
fails. Inspect every entry in `results` and `errors` in JSON output; any error
causes a nonzero exit. `start all` can leave earlier apps scheduled if a later
app fails. `run` is an alias of `now`. `stop` does not require a valid TOML
file; other app operations load and validate the whole config first.

Alfred's existing Backup Preferences workflow has its own LaunchAgent.
`localbackup start alfred` refuses to enable a second schedule while that
agent is loaded. Stop that schedule through the workflow's configured stop
command before starting the new one. The workflow itself still uses its own
backup implementation and settings.

Each scheduled agent uses the Python interpreter that installed it. If that
interpreter is removed or moved, run `localbackup start APP` again. Agent
output goes to `~/Library/Logs/localbackup/`. The agent runs in the user's
GUI launchd domain; it is not a system-wide daemon. No schedule is enabled by
installing the code or writing the TOML file. Stop an app's schedule **before
removing its module**: discovery controls which app names `stop` accepts, but
removing a module does not remove a LaunchAgent already installed for it.

## Restore

`localbackup archives APP` lists files matching the app's configured archive
directories, filename prefixes, and extensions. Listing does not validate
their contents. The built-in `restore` implementations validate and extract an
archive into a temporary area and print the destination without replacing app
data. Add `--apply` only after reviewing that plan and quitting the relevant
app:

```sh
localbackup restore alfred --preferences "/path/to/Alfred Backup.zip"
localbackup restore alfred --preferences "/path/to/Alfred Backup.zip" --workflow-data "/path/to/Alfred Workflow Data.zip" --apply
localbackup restore bartender --archive "/path/to/Bartender 7 Settings.zip"
localbackup restore bartender --archive "/path/to/Bartender 7 Settings.zip" --apply
```

Alfred Preferences and Workflow Data can be restored separately or together.
Alfred restore validates archive paths and contents, stages the replacement,
and keeps the previous settings beside the restored folders with a
`.before-localbackup-<timestamp>` suffix. The configured
`alfred.preferences_source`, if set, is also the preferences restore target.
Bartender restore validates the preferences and SQLite database; before
applying them, it saves the current preferences and database in
`<output_dir>/pre-restore/`. It requires Bartender's destination directory to
exist even for a preview. Restore checks known process names before applying,
but you must also quit the app yourself; other processes or background helpers
may not have those names. Reopen the app afterward and check its settings;
permissions and Keychain items may need to be granted again. If a restore
fails or is interrupted, inspect the destination and its saved previous copy
before retrying; do not assume the two are identical or that every app-level
setting was restored atomically.

The Zsh completion uses the same conditional menu colors as macbackup. Reload
an existing shell after installation, or source
`~/.zsh/integrations/localbackup.zsh` to register it. It asks the local
`localbackup --completion-spec` metadata path for app names and options. This
starts Python but does not read the TOML, run a backup, use launchctl, or access
the network. After an app is selected, completion and `--help` show only its
options. A newly added module appears without editing the completion file.

## Adding an application

For a start-to-finish example, including a complete module, configuration,
backup and restore checks, scheduling, completion, and deployment, see
[Writing an application module](APP_MODULE_GUIDE.md).

Add one public Python module, `lib/localbackup/apps/NAME.py`, and export an
`APP` value built with `App` from `._api`. The module filename and `APP.name`
must match. Modules whose names begin with `_` are reserved for shared helpers.
The descriptor supplies a default archive subfolder, schedule time, TOML
example, backup and restore callables, and archive source definitions. Optional
`Option` entries describe app-specific `now` and `restore` flags for both the
parser and Zsh completion. `config_keys` and `parse_config` let the same module
validate its own extra TOML fields; common storage, retention, and schedule
fields are handled centrally. An app can declare conflicting LaunchAgent
labels for schedule preflight and status.

The module's backup callable decides which app files and settings to include,
creates and validates its archive, and returns archive paths. Its restore
callable validates the selected archive and applies changes only when `--apply`
is set. The module must import without starting a backup or contacting the app,
because `list`, help, and completion discover modules. Adding an app needs no
edits to the CLI, configuration parser, scheduler, archive listing, or Zsh
completion. Test its backup contents and a restore preview with synthetic data
before using it on live settings.

## Local security and cloud transfer

The built-in modules restrict archive directories to the current user and
create archives with a restrictive local file mode. Their ZIPs are **not
encrypted**; the shared framework does not add encryption to future modules.
Alfred workflows and app settings may contain tokens, account
data, or other sensitive information. Local permissions do not encrypt cloud
copies. Review the archive and macbackup's path selection and `plain`/`private`
classification before transferring it; adding an app module does not update
that separate policy. A successful local `localbackup now` does not prove that
the cloud copy is current or restorable.

After changing sources or classification, inspect the local selection with
`macbackup check` and `macbackup preview --local`. Review the remote plan before
running a cloud transfer.

## Troubleshooting

If `localbackup list` fails to import the package, check that the installed
launcher resolves into the checkout containing `lib/localbackup/` and that its
`python3` is version 3.11 or later. A copied launcher by itself is not an
installation. If a newly added app is missing from `list` or completion, check
which checkout the installed launcher uses, whether the module's filename and
`APP.name` match, and the read-only `localbackup --completion-spec` output.
The module must import without requiring the app to be installed.

If `status APP` reports an installed or loaded agent but no recent archive,
inspect `~/Library/Logs/localbackup/APP.err.log` and run `now APP --json` with
the same config path. Check whether the source app, its data, the configured
archive directory, and the recorded Python interpreter still exist. If
`matches_config` is false after a config or checkout change, run `start APP`
again after a successful manual backup. If the configured frequency is `off`,
use `stop APP` instead. `stop APP` retains existing archives.

If restore fails, read its error and inspect the destination and saved previous
copy before retrying with `--apply`. A listed ZIP is not proof that it is valid,
and a valid ZIP is not proof that the app will accept every setting on another
Mac. Keep a known-good copy and rehearse the restore before depending on it.

## Maintainer map

`apps/_api.py` defines the module contract; `apps/__init__.py` discovers one
public module per app. `cli.py` builds app-specific parsers from those modules
and dispatches commands. `config.py` handles the shared TOML root, retention,
and schedule fields, while each module validates its own extra keys.
`scheduler.py` owns user LaunchAgent creation, status, and removal.
`common.py` and `archive.py` provide shared locking, archive, SQLite, and ZIP
checks. `restore.py` contains shared extraction helpers and the existing Alfred
and Bartender restore implementations; new modules can implement their own
restore without adding another branch to the CLI or configuration parser.

Keep the [application module guide](APP_MODULE_GUIDE.md), CLI help, TOML
examples, and Zsh completion in sync when changing the module contract. Test
with disposable app data and a temporary home; the focused suite is:

```sh
python3 -B -m unittest discover -s tests/localbackup -p 'test_*.py'
zsh -n home/.zsh/completions/_localbackup home/.zsh/integrations/localbackup.zsh
git diff --check
```

The tests do not prove behavior of a live Alfred or Bartender installation, a
loaded LaunchAgent, a restore across app versions, or a cloud transfer. Verify
those separately when changing their integration. The separately installed
Alfred Backup Preferences workflow is outside this repository and does not
change when this code changes.
