# macbackup: technical changelog and test record

This record preserves decisions, changes, and tests useful to macbackup maintainers, including future agents. It covers major milestones rather than every intermediate version. The [user manual](README.md) describes current behavior; an [Italian translation](README.it.md) is available for readers who prefer it. The [policy reference](POLICY_DESIGN.md) separates detailed policy usage from the enduring rationale and invariants, outside this chronology. The script, tests, and local configuration remain authoritative. Counts and paths below are **historical snapshots**, not values to copy or claims about the current backup.

When a rule changes, update the manual first if the user contract changes. Then record the reason, risk, tests, and remaining limits here. Do not publish secrets, tokens, or personal inventories.

---

## 2026-11-09 — inspect planned archives after local selection changes (0.14.3)

- Remote `preview` now lists every current copy that remains classified in its area but is absent from the local selection, in readable output and the additive JSON field `archive_deleted_paths`. This is an observation about selection, not proof of physical deletion. Policy archives remain a separate list.
- Display original Mac paths for symlinks and Finder icons instead of their rclone representations. The readable output escapes the icon filename's carriage return. The plan still respects `max_delete`; preview remains read-only and does not reserve state for `run`.
- Synthetic plain, private, symlink, and Finder icon cases cover the reported paths without accessing a live cloud provider.
- Moved the implemented typed-rule and overlap rationale out of the TODO into `POLICY_DESIGN.md`. The manuals retain the user-facing precedence and hard-link safety explanation; the TODO now contains only the pending live archive-path review.
- Format elapsed times and `run` estimates consistently as compact days, hours, minutes, and seconds, omitting zero-valued units. This affects the interactive bar, completed phase lines, and transfer screen; it does not alter JSON fields or backup behavior.

## 2026-11-08 — retain final progress counts (0.14.2)

- Completed, interrupted, and failed progress phases retain their last count in the final status line. This makes fast `verify --size-only` comparisons visible after the remote inventory phase and also preserves the final counters for scans, inventories, searches, removals, and restores.
- `verify` still shows `Checked x/y` during content comparison; its size-only variant first shows `Entries read x` while listing cloud `current`, then `Checked x/y` while comparing selected local files. The final count is taken from the validated comparison report when available.
- The dry-run part of `preview --simulate` uses `Processed x/y` for rclone decisions; it does not label those decisions as content checks. Other phases retain their own units, such as paths visited, entries read, copies removed or archived, and bytes received.

## 2026-11-07 — consistent operation progress (0.14.1)

- Local scans show visited paths. Cloud `current` inventories show entries read separately in `check --remote`, `preview --target`, and `run`; a live count does not imply a known final total. The same streaming reader is used for size-only verification and searches in `versions`, `forget`, and `restore`, without adding a second inventory pass.
- Simulated preview counts selected paths reported by rclone. Verification retains completed file checks out of selected files. `forget` and policy archiving show completed removals or moves out of the known plan; restore shows downloaded bytes against the known file size. Merged mount inventories also show live entries read. Structured JSON fields remain unchanged except for the local `summary` added to remote check.
- Progress stays on stderr, and read-only commands do not write to cloud storage. Synthetic local and crypt remotes cover the revised phases; no live provider verification is claimed.
- Human-readable remote identifiers use a theme-aware blue distinct from muted file paths; `versions` also marks each remote group with `▸`. JSON and output without color keep their existing structure.

## 2026-11-07 — fast remote preview (0.14.0)

- `preview --target` now builds the archive plan from the local selection and cloud `current` inventories, without the expensive content comparison or rclone transfer dry run. It still reports policy and local-deletion archives and whether `max_delete` would be exceeded. It cannot predict changed-file uploads or transfer-only failures.
- `preview --target ... --simulate` retains the former deeper, read-only comparison and dry run. Activity indicators identify the active target and area, show elapsed time, and count completed private comparisons. JSON stdout remains parseable; progress is on stderr. The English and Italian manuals, help, and Zsh completions describe both modes.

## 2026-11-07 — typed selection rules and overlap validation (0.13.0)

The lasting reasons for these rules and their safety boundaries are collected in [POLICY_DESIGN.md](POLICY_DESIGN.md).

- Path lists now require a trailing `/` for directories and no trailing `/` for files or symlinks. Existing paths with a mismatched declared type fail before cloud access; missing exclusions retain their declared type until they appear. A directly included source covered by an ancestor exclusion is suspended, reported as a warning, and may be absent. Identical normalized paths within or across lists are rejected; distinct overlapping parent and child paths retain their precedence.
- Explicit-only patterns now declare their type in the same way: `.env` protects files or symlinks, and `node_modules/` protects directories. `init` and the migrated configuration include both file and directory forms of `.env` and `.env.*`, preserving protection for future directories with those names. Name policies remain case-insensitive while absolute paths remain case-sensitive. Case-only duplicates and unsafe overlaps with `private_directory_names` or `ignored_file_names` are rejected. In particular, combining an ignored filename with an explicit-only file pattern could bypass explicit-only's hard-link alias check; the error keeps that protection visible. Fully redundant patterns fail; demonstrable partial overlap warns.
- When Git ignore processing is enabled, local `check` warns if an exact inclusion overrides an effective ignore rule, or if automatic private-directory routing overrides one. Automatic routing produces at most one warning per directory. Normal ignored paths do not warn, and these overrides do not block a run. An exact directory inclusion still does not grant exact exceptions to its descendants.
- Remote previews now report the active target, area, and phase after planning. Private comparisons show completed files while `cryptcheck` runs; subsequent rclone dry-run sync phases show elapsed time. Progress stays on stderr so JSON output remains parseable. This does not change preview's read-only behavior.
- Migrated the local path and pattern lists together. A synthetic test suite exercises the new validation. A read-only comparison of the old and new selectors on the current Mac found 62,571 selected entries in each, with no additions or removals at comparison time. This is a selection comparison, not a cloud verification.

## 2026-11-06 — verification progress (0.12.8)

- Interactive `verify` displays completed file checks against the selected count for each area and kind. The count includes differences and errors; it may pause during remote listing or large-file checks. JSON fields and verification semantics are unchanged.

## 2026-11-06 — English primary documentation

- Rewrote `README.md` as the primary English user manual and retained the earlier Italian manual in `README.it.md`. The technical changelog is maintained in English only. Command examples remain generic, with no personal configuration or backup inventory.
- The English manual keeps the operational contracts for selection precedence, local and remote checks, archives, mounts, version search, restore, verification, and two-phase removal. Review script and tests before treating this record as the current behavioral specification.

---

## 2026-11-06 — interface language

- Terminal output, `--help`, Zsh completion descriptions, and progress bars default to English. `MACBACKUP_LANG=it` selects Italian without a new flag; reloading the Zsh integration refreshes completion in an open shell.
- Command names, options, JSON field names, and displayed paths remain stable. New reports may contain explanatory strings in the active language. `status` reads old reports without rewriting them.
- This change was tested with synthetic local files and remotes, without contacting live cloud accounts.

---

## 2026-11-06 — user manual separated from technical history

- Rebuilt the manual around configuration, precedence, remote layout, commands, and recovery. Removed personal home paths, temporary preview counts, one account's state, and chronological test stories.
- The example TOML uses `max_delete = 100` as a **configurable example**, while explaining that `init` creates `25`. The explicit-only example has eight names including `.git` and `.astro`; two generated-output exclusions demonstrate absolute paths rather than global basename rules.
- This file became the archive for maintainers. Check current behavior against script and tests before reusing a historical note.
- Cross-checked the parser and transport functions: the manual covers subcommands and flags, local versus remote checks, target enablement order, recovery, and error handling. This documentation review did not contact live remotes.
- Local suite at that point, without script changes: `python3 -B -m unittest discover -s tests/macbackup -t tests -p 'test_*.py'` (168 passing tests). Synthetic tests do not certify the current state of live cloud accounts.

---

## Early tests and design decisions (October–November 2026)

- **Local selection:** the first large scan included many rebuildable dependency directories. Basename patterns in `explicit-only-patterns.txt` replaced dozens of absolute exclusions. The policy later added `.git` and `.astro`; the manual's example contains eight patterns. A `.git` directory beneath a selected source is encrypted by `private_directory_names` even when explicit-only, unless exactly included as plain and not covered by private. Project-specific `dist/` and `.vercel/output/` exclusions need absolute paths, not global-name examples.
- **Finder icons:** `Icon\r` files initially caused selection errors. Version 0.3 added resource-fork and FinderInfo snapshots. An AppKit test compared rendered images before and after recovery, which does not prove every icon will render identically in Finder.
- **Google OAuth:** a personal client moved from Testing to Production and its remote was reconnected. With `drive.file`, creation, reading, trash moves, and test-folder removal were exercised. Cleanup of deep trees saw intermediate `403 appNotAuthorizedToChild` failures; final checks found test namespaces absent, but the intermediate cause was not isolated. Full `drive` scope was not requested.
- **Isolated remote tests:** synthetic plain and crypt files covered copy, same-size/same-time edits, history, `forget`, `restore`, ordinary and downloaded `verify`, and icon recovery. Authorized test namespaces were removed and checked absent from active backup areas. These tests do not certify the full personal backup, native revisions, or items already in trash.
- **First real selection:** local and remote preview counts changed substantially as policy was revised; each was a point-in-time snapshot. An early run was intentionally interrupted, after which partial-transfer reporting was added. Historical counts are not program parameters and do not belong in the manual.
- **Mounting:** `--area all` was exercised with local remotes and read-only Google access. It merges `current`, keeps `history/plain` separate from `history/private`, and rejects file/file or file/directory collisions. `Ctrl-C` and Finder eject were tested. These tests did not read every file's contents.
- **Still to verify on a fresh installation:** recovery on another Mac using separately recovered keys, complete Proton backend behavior, open application databases, and every current and historical copy. Use the manual for available commands; this record does not establish the present operational state of an account.

---

## Architecture notes for future changes

Rclone handles provider access, transfer, `crypt`, and moves of replaced or deleted copies through `sync --backup-dir`. Macbackup interprets the four lists, classifies files, blocks concurrent operations, and plans transfer, recovery, and selective removal. Mounted external-volume identity is not checked.

`explicit-only` is not an rclone feature. The Python selector applies precedence to local files and current copies. Transport gives rclone an exact NUL-delimited list with `--files-from0`. Do not add rclone exclusion filters to that command: with files-from, rclone ignores other filters. The manifest includes allowed files and still-managed old copies to archive after local deletion. Policy-excluded or reclassified copies move separately into their original area's history. A new file appearing after manifest creation waits until the next run. Recursive rclone inclusions could bypass per-name protection.

Maintainers can run `python3 -B -m unittest discover -s tests/macbackup -t tests -p 'test_*.py'`. Synthetic tests do not replace a live remote check, sample recovery, or inspection of effective permissions.

---

## [0.12.7] — 2026-11-06 (commit `8b11f68`)

- `check --remote` compares `plain/current` with `private/current`. A shared path is a conflict when it is a file in at least one area; common ancestor directories are allowed.
- `verify --size-only` compares path and size from one remote inventory per area. It is faster but does not check contents. Ordinary private verification remains `cryptcheck`; `Ctrl-C` exits without a traceback.
- The `run` UI distinguishes keys, units, legend, active paths, and statistics. Identifiers and secondary notes in other commands are muted only on color terminals; JSON is unchanged.
- Zsh completion offers `--size-only`. Synthetic tests cover collisions, rapid comparison, symlinks, and color. That commit's suite had 168 passing tests.
- Rapid verification still reads provider inventory; its duration on a full backup depends on the service. `verify` does not cover `history`.

## Preparatory work 0.12.6 — 2026-11-05 (included in commit `8b11f68` and version 0.12.7)

### Added
- **Interactive TTY activity indicator (`operation_activity`):**
  - Long-running synchronous phases (`check` local/remote, `layout`, `preview`, `versions`, `restore`, `verify`, `forget` plan/verify/apply) show an animated indeterminate ASCII bar (`MountPulse`) on `stderr` when attached to a TTY. Ordinary input is discarded (`discard_mount_input`) while `Ctrl-C` (`SIGINT`) stays active.
- **Colored terminal UI (`ui`, `issue_line`, `styled_progress_lines`):**
  - Semantic ANSI styling (`info`, `success`, `warning`, `error`, `private`, `muted`) was added for human-readable output and the `run` dashboard (speed in green, section headers in cyan).
  - Warning/error paths and `preview --local` listings are muted (`\x1b[2m`) so severity and reasons stand out.
  - `NO_COLOR=1`, `PYTHON_COLORS=0`, and non-TTY output have no color; `--json` stdout remains unstyled JSON.
- **Cross-area conflicts in `check --remote`:**
  - `remote_current_objects` records files and directories (`IsDir: bool`) from both current areas.
  - `current_conflict_paths` blocks remote checks when a shared path is a file in either area, while permitting common parent directories; it reports up to five example paths.
- **Compact Zsh global options and menu selection:**
  - The integration loads `zsh/complist`, sets `menu select`, `last-prompt true`, and `list-colors` for macbackup.
  - Completion groups `--config-dir`, `--help`, `--version`, and `-h` into one compact `_describe` group before a subcommand and uses concise subcommand descriptions.
- **UI tests:** PTY and stream tests cover activity bars, discarded input, terminal restoration, `NO_COLOR`, dashboard styling, and warning paths.

### Changed
- `progress_quantity()` now uses `B` instead of `byte` for sub-kilobyte amounts in both unit modes.

---

## [0.12.3] — 2026-11-05 (Commit `0bdfee8`)

### Added
- **Read-Only Cloud Mounts (`macbackup mount`):**
  - Uses `rclone nfsmount --read-only --vfs-cache-mode off --addr 127.0.0.1:0` on macOS (no macFUSE dependency).
  - Supports `--area plain`, `--area private`, and `--area all` (default).
  - `--area all` pre-checks `plain/current` and `private/current` inventories via `mount_current_conflicts` (with live metadata byte progress via `MountPulse`) and refuses to mount if a file-file or file-directory collision exists across areas.
  - Synthesizes ephemeral in-memory `rclone` remotes via environment variables (`mount_merged_env`): a `union` remote (`epall`, read-only) merging `plain/current` and `private/current` into a single `current/` tree, and `combine` remotes exposing `history/plain`, `history/private`, `icons/plain`, and `icons/private`.
  - Guards terminal input during inventory, startup, and active mount (`discard_mount_input`), cleans up created empty mountpoints on `Ctrl-C` or Finder eject (`⌘E`), and automatically excludes default Desktop mountpoints (`~/Desktop/<target>`, `~/Desktop/<target>-plain`, `~/Desktop/<target>-private`) from backup selection.
- **Automatic Policy-Change Archiving (`archive_policy_copies`):**
  - Remote objects in `current` (both regular files and `macos-icons` snapshots) that are no longer selected for that area due to policy changes (new exclusions, removed inclusions, new `explicit-only` patterns, new `ignored_file_names`, `.gitignore` rules, or plain↔private reclassification) are now distinguished from local file deletions.
  - During `run`, policy-revoked copies are moved from `<area>/current/...` to `<area>/history/<RUN_ID>/...` using `rclone moveto` and recorded in `policy_archives` / `policy_archived` with the new action, reason, and triggering rule.
  - `max_delete` now bounds the sum of local-deletion archives (`archive_deleted`) and policy-change archives (`archive_policy`) across both files and Finder icons per target and area. `preview --target` reports `archive_limit_exceeded` without failing; `run` aborts before any transfer if exceeded.
- **Optional `.gitignore` Evaluation (`GitIgnoreMatcher`):**
  - Added `use_gitignore` boolean setting in `settings.toml` (`[policy]`).
  - Spawns a persistent `git --git-dir <bare-temp> --work-tree / -c core.excludesFile=/dev/null check-ignore --no-index -z -v -n --stdin` subprocess to evaluate `.gitignore` files along physical parent paths (even outside Git repositories) without consulting the Git index or global excludes.
  - Exact path entries in `plain-paths.txt` or `private-paths.txt` and automatic `private_directory_names` routing override `.gitignore` exclusions.
- **Ignored File Basenames (`ignored_file_names`):**
  - Added `ignored_file_names` list in `settings.toml` (`[policy]`, default `[".DS_Store"]`).
  - Matches file basenames case-insensitively when inherited through a directory; can be overridden per file via an exact path entry in `plain-paths.txt` or `private-paths.txt`.
- **Automatic Private Directory Routing (`private_directory_names`) & `layout` Command:**
  - Added `private_directory_names` in `settings.toml` (`[policy]`) to automatically route matching directories (such as `.git`) and their descendants to `private`, overriding `explicit-only` directory pruning while still enforcing `explicit-only` on files inside them (e.g. `.git/.env`).
  - An exact directory entry in `plain-paths.txt` (when not covered by `private-paths.txt`) overrides automatic directory privacy back to `plain`.
  - Added `macbackup layout [PATH] [--json]` to inspect a `plain` local directory and summarize the root boundaries, item counts, and byte sizes of `private` subtrees inside it.
- **Scoped Empty-Directory Cleanup in `forget`:**
  - Directory `forget` plans (`PATH` ending with `/`) now record `cleanup_roots` in `current` and each `history/<RUN_ID>` (for both `files` and `macos-icons`) and remove empty directories under the requested root via `rclone rmdirs` after file deletion. Also allows planning and removing empty remote directory roots with 0 files.

### Changed
- Relocated test modules into `tests/macbackup/` and added `tests/macbackup/test_macbackup_mount.py`.
- Removed personal configuration files under `home/.config/macbackup/` from Git tracking (`.gitignore` updated) so user-specific paths remain local-only.

---

## [0.9.1 – 0.9.5] — 2026-11-01 to 2026-11-02 (Commit `90c2186`)

### Added
- **Scoped Read-Only `versions` Queries (v0.9.5):**
  - Replaced full-tree hash/original-ID inventory scans in `versions` with targeted `rclone lsjson` queries against `current/<scope>` and each `history/<RUN_ID>/<scope>` (or parent directory for single files), omitting `--hash` and `--original` for faster lookups.
  - Added directory mode to `versions` (grouping counts and bytes by `current` and each sparse `history/<RUN_ID>`) and `--files` flag to list historical entries under a directory.
- **Live Interactive Transfer Dashboard & Interrupted Run Metrics (v0.9.1 – v0.9.2):**
  - Added `ProgressDisplay` and `rclone_progress_call` parsing `rclone --use-json-log --stats 5s` events on `stderr`.
  - Displays separate byte and file ASCII progress bars, transfer speed, rounded elapsed time and ETA, active folder groups (`--progress-depth 1..5`), and per-file progress, with interactive keys `u` (binary/decimal units) and `?` (legend) in alternate-screen cbreak mode.
  - Added `TransferInterrupted` handling on `SIGINT` (`Ctrl-C`) so the latest periodic `rclone` stats are persisted to `last-run.json` with `counts_complete: false` instead of `null`.
- **Single-File & Symlink Restoration (`restore`) and Verification (`verify`):**
  - Added `macbackup restore` with `--version current|<RUN_ID>`, `--to ABS_PATH`, `--replace`, and `--links` (recreating `.rclonelink` symlinks safely without following targets), including pre/post-download inventory checks and local hash verification (`md5`, `sha1`, `sha256`).
  - Added `macbackup verify` comparing selected local files and generated `macos-icons` snapshots against remote `current` using `rclone check` (plain), `rclone cryptcheck` (private), or `rclone check --download` (`--download`).

---

## [0.4.0] — Two-Phase Selective Deletion (`forget`)

### Added
- Implemented `macbackup forget` with a strict two-step workflow:
  1. **Plan generation:** scans `current` and all `history/<RUN_ID>` across `files` and `macos-icons` (ignoring active local selection rules so previously excluded or reclassified files are still found), enforces path boundaries and a 10,000-file cap, and writes a 1-hour single-use plan (`F<12-hex>.json`, mode `0600`) in `~/.local/state/macbackup/forget-plans/`.
  2. **Plan application (`--plan ID --apply`):** re-reads remote inventories and aborts if any matched file path, size, mtime, ID, or hash changed, then deletes files individually via `rclone deletefile` with `--drive-use-trash=true` (`trash`) or `--drive-use-trash=false` (`permanent`, restricted to verified Google Drive `drive` remotes).

---

## [0.3.0] — macOS Custom Folder Icons (`Icon\r`)

### Added
- **Native Extended Attribute Engine (`MacXattrs`):**
  - Uses `ctypes` bindings to `/usr/lib/libSystem.B.dylib` (`fgetxattr` / `fsetxattr` on file descriptors opened with `O_NOFOLLOW`) because standard Python on macOS does not expose `os.getxattr` / `os.setxattr`.
- **Sidecar Snapshot Packaging (`icon_snapshot`) & Restoration (`restore-icon`):**
  - Recognizes regular `"Icon\r"` files as `finder-icon` entries while keeping all other control-character filenames blocked.
  - Packages `"Icon\r"` file bytes, `com.apple.ResourceFork`, file `com.apple.FinderInfo`, and parent directory `com.apple.FinderInfo` (32 bytes) into `<area>/macos-icons/current/<folder-path>/icon.json` (with 64 MiB size guards and mid-read modification detection).
  - Added `macbackup restore-icon --file ... --folder ... [--replace]` to restore `"Icon\r"` and set the Finder custom-icon bit (`0x0400`) while preserving other Finder flags and folder contents.
  - Verified icon visual fidelity before and after round-trip restoration using `AppKit` rendering.

---

## [0.1.0 – 0.2.0] — Core Selector, `rclone` Transport & Zsh Completion

### Added
- **Local Selector (`Policy`, `scan_policy`, `init`, `check`, `explain`, `preview --local`):**
  - Designed the 4-list configuration model (`plain-paths.txt`, `private-paths.txt`, `exclude-paths.txt`, `explicit-only-patterns.txt`) plus `settings.toml`.
  - Implemented descriptor-anchored directory traversal (`O_DIRECTORY | O_NOFOLLOW`), symlink preservation without traversal (`.rclonelink`), hardlink identity conflict detection (`(st_dev, st_ino)`), and automatic protection of `~/.local/state/macbackup` and `rclone` credential directories.
- **Remote Transport (`check --remote`, `preview --target`, `run`, `status`):**
  - Passed exact NUL-delimited file manifests (`--files-from0`) to `rclone sync` with `--backup-dir <area>/history/<RUN_ID>`, avoiding `rclone` filter flags that conflict with `--files-from`.
  - Used `rclone cryptcheck --one-way` on `private` areas to detect same-size/same-mtime content changes while avoiding redundant re-uploads of unchanged encrypted files.
  - Added `operation_lock` (`flock`) and sanitized `RCLONE_*` environment variables.
  - Verified Google Drive OAuth `drive.file` scope behavior (including production OAuth consent requirements and bottom-up Drive ID cleanup of deep test hierarchies).
- **Native Zsh Completion (`_macbackup`, `macbackup.zsh`, `test_macbackup_completion.py`):**
  - Context-aware tab completion tested in an isolated PTY without executing `macbackup` or `rclone`.
