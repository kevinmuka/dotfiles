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

All commands and archive README files are in English. `run` remains an alias
for `now`. Commands with `--json` print one JSON object; failures use a nonzero
status. This makes `now` suitable for an Alfred Run Script action:

```sh
"$HOME/.config/scripts/localbackup" now alfred --json
"$HOME/.config/scripts/localbackup" now bartender --json
```

The installed Alfred Backup Preferences workflow still has its own backup
implementation. It has been updated locally to create and restore preferences
ZIPs, but it does not call `localbackup`. If it is connected to this command
later, pass its configured preferences path and retention count:

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
listed or accepted by `localbackup restore` or the updated Alfred workflow.
The Workflow Data ZIP contains
its own English README with a manual restore procedure. Active SQLite
databases within Workflow Data are copied through SQLite's backup API. The
archives are verified before they are published, and 12 new ZIP versions of
each type are kept by default.

Alfred must use its local preferences folder for the default source to be
correct. If preferences live elsewhere, pass `--preferences-source PATH`.
The Alfred workflow's `backup restore` command restores preferences only;
`localbackup restore alfred` can restore preferences, Workflow Data, or both.

## Bartender

`localbackup now bartender` creates a ZIP in
`~/.backups/apps/customization/bartender/`. It contains a `defaults export` of
the Bartender preferences domain, a consistent snapshot of its group-container
SQLite database, and an English README with restore instructions. The archive
is a file-level fallback for Bartender 7. Bartender 7.1.0 and later provide a
native configuration export in Advanced settings, which is preferable for a
supported transfer between Macs.

The app bundle, license, macOS permissions, caches, and Keychain items are not
part of this archive. Restoring may require the same Bartender version and new
permission grants.

## Configuration and automatic backups

The configuration is `~/.config/localbackup/config.toml`. Run
`localbackup init` to create it when it does not exist. An alternate file can
be selected with `localbackup --config /absolute/path/config.toml COMMAND`.
The command requires Python 3.11 or later.

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
root moves both app destinations together. Alfred's Workflow Data ZIP goes
beside its preferences folder, under
`apps/customization/alfred/workflow-data`. The example retains the existing
archive locations. Changing this root does not update
macbackup's separate path policy; confirm that the new root is selected and
classified as intended before a cloud transfer. `--output-dir` is a one-run
override for a single app; it does not change the TOML or the automatic
schedule.

`frequency` accepts `daily`, `weekly`, or `off`; the weekday applies only to
weekly schedules. The clock uses local time in 24-hour `HH:MM` form.
`alfred.preferences_source` is optional when Alfred uses its default local
preferences location. Unknown settings and invalid values fail before any
backup or schedule change.

`localbackup start APP` creates a backup immediately, then installs or updates
that app's LaunchAgent. Use `all` to start both. A later configuration change
needs another `start` to update the loaded agent. `localbackup now APP` creates
one backup without changing any schedule. `localbackup stop APP` unloads and
removes only localbackup's LaunchAgent; it keeps archives. `status` reports
whether the agent is loaded, whether its file is installed, and whether it
matches the current TOML settings. A loaded calendar agent normally waits
between runs; this does not mean a backup process is active.

Alfred's existing Backup Preferences workflow has its own LaunchAgent.
`localbackup start alfred` refuses to enable a second schedule while that
agent is loaded. Stop the old schedule with the workflow's `backup stop`
command before starting the new one. The workflow itself still uses its own
backup implementation and settings.

Each scheduled agent uses the Python interpreter that installed it. If that
interpreter is removed or moved, run `localbackup start APP` again. Agent
output goes to `~/Library/Logs/localbackup/`. No schedule is enabled by
installing the code or writing the TOML file.

## Restore

`localbackup archives APP` lists local archives. `restore` validates an
archive and prints the destination without changing it. Add `--apply` only
after reviewing that plan and quitting the relevant app:

```sh
localbackup restore alfred --preferences "/path/to/Alfred Backup.zip"
localbackup restore alfred --preferences "/path/to/Alfred Backup.zip" --workflow-data "/path/to/Alfred Workflow Data.zip" --apply
localbackup restore bartender --archive "/path/to/Bartender 7 Settings.zip"
localbackup restore bartender --archive "/path/to/Bartender 7 Settings.zip" --apply
```

Alfred Preferences and Workflow Data can be restored separately or together.
The restore validates archive paths and contents, stages the replacement, and
keeps the previous settings beside the restored folders with a
`.before-localbackup-<timestamp>` suffix. Bartender restore validates the
preferences and SQLite database; before applying them, it saves the current
preferences and database in `<output_dir>/pre-restore/`. Restore refuses to
apply while the corresponding app is running. Reopen the app afterward and
check its settings; permissions and Keychain items may need to be granted
again.

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

Archive directories are restricted to the current user, and new archives are
created with a restrictive local file mode. The current macbackup path policy
classifies Alfred and Bartender app archives at the configured default root in
its readable `plain` area, as requested. Local file permissions do not encrypt
cloud copies. These archives can contain app settings, so review their contents
before a cloud transfer. A successful local `localbackup now` does not prove
that the cloud copy is current or restorable.

After changing sources or classification, inspect the local selection with
`macbackup check` and `macbackup preview --local`. Review the remote plan before
running a cloud transfer.
