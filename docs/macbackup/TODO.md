# macbackup — Technical TODO & Review Findings

Open items from the code, test, and documentation review. Recheck each against the current script before implementation.

---

## Validation pending: Explicit File/Directory Syntax and Policy Rules

**Status:** implemented locally in 0.13.0. The old and new selectors selected the same 62,571 entries on this Mac at comparison time, and the 187-test synthetic suite passed after the later preview changes. On 2026-11-07, a read-only Google preview with the full transfer simulation completed successfully: zero policy archives in both areas, 20 plain and one private copies planned for archiving because they were no longer in the local selection, and no Finder-icon archives. This confirms that the preview itself finished without policy reclassification, but it does not establish why the 21 copies are absent locally. Review their paths before the next `run`; the user has deferred that review. The current default `preview --target` is a faster inventory-based plan; `--simulate` retains the full comparison. Retain this section until the pending paths have been reviewed, then move any lasting rationale to the changelog and remove the completed design notes.

### Agreed syntax and behavior

- In `plain-paths.txt`, `private-paths.txt`, and `exclude-paths.txt`, an absolute path ending in `/` declares a directory and its subtree. A path without `/` declares a file or symlink and matches only that path. A symlink to a directory is still a symlink, not a traversed directory. Existing paths whose actual type disagrees with the declaration are configuration errors: `check` reports them and `run` stops before cloud access. A directly included source that is missing remains an error when it is active. An exclusion may name an absent future path; its declared type is checked when it appears.
- Change `explicit-only-patterns.txt` to use `name/` (or `name*/`) for directory basenames and `name` (or `name*`) for file/symlink basenames. Only a final `/` is permitted; it is a type marker, not a path component. Keep literal names and `*` matching as before. A directory pattern must also protect descendants by pruning traversal unless the directory is included exactly. Update the pre-stat scan and remote classification so file patterns cannot accidentally classify directories or vice versa.
- `private_directory_names` and `ignored_file_names` already declare their types through their TOML keys; retain names without `/`. `private_directory_names` applies to directories and their descendants; `ignored_file_names` applies to non-directories, including symlinks, but not to directories. An exact file inclusion can override `ignored_file_names`; an absolute exclusion still wins. Preserve existing deliberate precedence between plain, private, explicit-only, Git ignore, and absolute exclusions.
- **Confirmed:** name policies (`private_directory_names`, `ignored_file_names`, and explicit-only patterns) remain case-insensitive, including on a case-sensitive volume. This conservatively protects names such as `.ENV`. Reject duplicate literal names or same-type patterns differing only by case. Absolute path lists remain case-sensitive and retain exact spelling: a case-sensitive filesystem can contain distinct paths. Reject repeated normalized paths within the same list, while preserving intentional parent/child rules. Explain this difference explicitly in both user manuals and record the behavioral/validation change in the changelog when implemented.
- Reject a directory-only explicit-only pattern if it matches any `private_directory_names` entry, including via `*` and case-insensitive matching. The automatic private rule makes the explicit-only directory rule ineffective for that name. Report the TOML entry and pattern file line; `check` fails and `run` stops before cloud access. Do not reject a file-only `.git` pattern against the directory-only private name `.git`—they govern different objects.
- **Confirmed safety rule:** reject any overlap between `ignored_file_names` and a file-only explicit-only pattern, including `*` and case-insensitive matches. The current selector checks `ignored_file_names` first and returns before recording the explicit-only protected pattern. This can disable explicit-only's hardlink-alias safeguard: in a synthetic reproduction, `.env` plus a hard link named `public.txt` was allowed into plain with **no scan error** when `.env` was in both policies; removing `.env` from `ignored_file_names` made the scan reject the unprotected alias. A warning alone would leave the weaker behavior active. Validate this conflict before scanning or cloud access, report both policy entries, and add a regression test. Exact plain inclusion warnings are another behavior contributed by explicit-only.
  **Rationale to carry into the manuals and changelog:** both policies skip an inherited filename and allow its exact inclusion, so they look interchangeable if one examines only that path. They serve different purposes: `ignored_file_names` is for harmless noise, while explicit-only marks names whose contents need an intentional decision and protects against a second hard-link name exposing the same bytes. A hard link is another directory entry for the same inode, not a symlink. Because the current early return makes the combination *less* protective than explicit-only alone, retaining both with only a warning would be unsafe. A configuration error forces the user to keep the sensitive name in explicit-only only, or consciously choose the weaker ignore-only behavior. This validation must run before any cloud inventory or transfer and should name the matching TOML value and pattern line.
- **Confirmed path-list overlap rule:** the identical normalized absolute path cannot appear in two of `plain-paths.txt`, `private-paths.txt`, and `exclude-paths.txt`; report both file/line locations as a configuration error before cloud access. A parent/child overlap is valid: `/Documents/` in plain and `/Documents/project/.git/` in private; `/Documents/project/build/` in exclude under a plain parent; or `/Documents/private-project/cache/` in exclude under a private parent. Existing private-over-plain and exclude-over-both precedence continues to govern those *different* paths. Update the manuals because an identical path in multiple lists was previously allowed by precedence.
- **Confirmed suspended-source rule:** if a directly listed inclusion is covered by an exclusion of an **ancestor** path, local `check` warns and names both lines, but the missing or existing source is suspended and does not block `run`. Removing the exclusion makes source existence mandatory again. An identical inclusion/exclusion path is disallowed by the preceding rule; suspend such a path by removing its direct inclusion or by using a meaningful ancestor exclusion. A run may still archive old `current` copies due to the exclusion, subject to `max_delete`; show that plan in `preview`.
- Migrate existing list entries atomically: add `/` to directory paths in all three path lists; leave file/symlink paths without it. Convert directory patterns such as `node_modules`, `.venv`, `venv`, `myenv`, and `.astro` to their `/` forms. Keep `.git` as a file-only explicit-only pattern for Git worktree files; do not add `.git/` while `.git` remains in `private_directory_names`. `init` should produce valid typed defaults. Review generated examples, help/completion text, English and Italian manuals, and the changelog.
- Test both kinds with the same basename, missing and later-appearing exclusions, type mismatch before any rclone call, exact overrides, wildcard collision with a private directory name, case-only duplicates in name policies, normalized duplicate paths, symlinks, and migration preserving the selected file set. Run local `check` and `preview --local` before any real backup; review remote plans before the next `run` so no unintended archives consume `max_delete`.

### Implemented overlap diagnostics

- **Confirmed pattern overlap rule:** for explicit-only patterns of the same type, reject exact duplicates (including case-only duplicates) and complete containment whenever it can be proven, including containment between two wildcard patterns. For example, `node*/` makes `node_modules/` redundant. Warn without blocking for demonstrable partial overlap where each pattern also covers distinct names: `node*/` and `*modules/` both match `node_modules/` but each has other matches. Do not claim containment or overlap when the validator cannot establish it; document the supported pattern syntax and validation limits.
- **Confirmed `.gitignore` diagnostic rule:** do not treat dynamic Git ignore intersections as static configuration errors. Ordinary effective exclusions, including a name also protected by explicit-only, need no warning. When an exact inclusion overrides an effective `.gitignore` exclusion, local `check` warns with the included path, path-list line, and Git ignore source/line; `run` may proceed. When automatic `private_directory_names` routing overrides an effective `.gitignore` exclusion, warn at most once per affected directory, not per child. Preserve absolute exclusion precedence. The current selector bypasses Git ignore for these overrides, so the diagnostic requires an additional read-only matcher query. Document that an exact directory inclusion does not grant exact exceptions to its descendants; the manuals already explain the current selection scope, but update them again if the planned typed syntax changes examples.

---

## 1. `mount` Invokes `rclone nfsmount` Without Resolved Path or `--ask-password=false`

- **Location:** [`home/.config/scripts/macbackup`](../../home/.config/scripts/macbackup) (`_mount_operation`)
- **Issue:** Every other `rclone` call in `macbackup` (`rclone_call`, `rclone_progress_call`, `mount_inventory`, `restore_operation`) resolves `executable = shutil.which('rclone')` and passes `'--ask-password=false'` so `rclone` never hangs waiting for an interactive config password on `stdin` (which is `DEVNULL` in `nfsmount`). `_mount_operation` invokes `['rclone', 'nfsmount', ...]` directly without `--ask-password=false`.
- **Proposed Fix:** Resolve `shutil.which('rclone')` (or keep `'rclone'` if tests mock `subprocess.Popen` expecting `'rclone'`) and include `'--ask-password=false'` (updating `test_macbackup_mount.py` command assertions accordingly if needed).

---

## 2. Cross-Area Conflict Check (`check_conflicts`) Only Enabled in `check --remote`

- **Location:** [`home/.config/scripts/macbackup`](../../home/.config/scripts/macbackup) (`transport_operation`)
- **Issue:** `transfer_plan()` accepts `check_conflicts=(args.command == 'check')`. As a result, `macbackup check --remote` and `macbackup mount --area all` both block if a file exists at the same path in both `plain/current` and `private/current`, whereas `macbackup preview --target` and `macbackup run --target` do not enable `check_conflicts`.
  - Note: in normal operation, `transfer_plan` classifies any existing remote object that belongs to the *other* area into `policy_archives`, so `run` will move the old copy to `history` at the end of the phase. However, if a conflict arises from external manual modification or an interrupted run where `archive_policy_copies` did not run, deciding whether `preview` / `run` should warn or auto-heal via `policy_archives` is worth confirming.

---

## 3. `mount` Does Not Acquire `operation_lock` During Inventory / Startup

- **Location:** [`home/.config/scripts/macbackup`](../../home/.config/scripts/macbackup) (`mount_operation` / `_mount_operation`)
- **Issue:** While `mount` is a long-running foreground command (so holding an exclusive lock for the entire duration of the mount would prevent `status` or `versions` from running while mounted), `_mount_operation` does not check whether a `run` or `forget --apply` is actively mutating `current` while `mount_current_conflicts` reads the inventories.
- **Proposed Fix:** Optionally acquire a short-lived lock during `mount_current_conflicts`, or document that mounting while `run` / `forget` is in flight may see a mid-transfer inventory.

---

## 4. Custom `RCLONE_CONFIG` Path Not Added to `Policy.credential_roots`

- **Location:** [`home/.config/scripts/macbackup`](../../home/.config/scripts/macbackup) (`Policy.__init__`)
- **Issue:** `Policy.credential_roots` automatically blocks accidental `plain` selection of `~/.config/rclone` and `~/Library/Preferences/rclone` (and their symlink targets). If the user sets `RCLONE_CONFIG=/custom/path/rclone.conf` in the environment, that custom file path is not automatically added to `credential_roots`.
- **Proposed Fix:** Include `Path(os.environ['RCLONE_CONFIG'])` (and its `realpath`) in `credential_roots` when `RCLONE_CONFIG` is set to an absolute path.

---

## 5. Future Roadmap Items (Tracked from Architecture Design)

- **Proton Drive target setup & verification:** configure `pdrive:` and `pdrive-private:` (`crypt`), test `run`, `verify`, `restore`, `mount`, and `forget --mode trash`.
- **External volume identity verification:** verify volume UUID / mount identity when backing up paths under `/Volumes/...` so an unmounted or wrong volume is never mistaken for a valid source.
- **Full-directory / subtree restore:** extend `restore` (or add a dedicated command) to recompose a directory tree from `plain/current` and `private/current` (and optionally apply `macos-icons` snapshots) into a target restore folder.
- **Scheduled automation (`launchd`):** configure unattended periodic execution with explicit binary paths (`/opt/homebrew/bin/python3`, `/usr/local/bin/rclone`) once both targets and `max_delete` thresholds are finalized.
- **Repository documentation links:** add `macbackup` to the root `README.md`, `docs/MODULES.md`, and `docs/DEPENDENCIES.md` (and sync the English/Italian pages in `dotfiles-site` when ready).
