# macbackup — Technical TODO & Review Findings

Open items from the code, test, and documentation review. Recheck each against the current script before implementation.

---

## Pending live review: paths planned for archiving

The explicit file/directory syntax and policy overlap checks were implemented in 0.13.0. Their current contract and design reasons are in [POLICY_DESIGN.md](POLICY_DESIGN.md); the [manual](README.md) explains how to use them, and the [changelog](CHANGELOG.md) records the migration and synthetic tests. No syntax or overlap implementation remains open in this section.

A read-only Google preview on 2026-11-07 reported zero policy archives and 20 plain plus one private copies absent from the local selection. These counts are historical and may have changed. The completed preview did not establish why those copies were absent. Before the next `run`, repeat `macbackup preview --target google` with the current policy and inspect every path now listed as absent from the local selection. Decide whether each archive is intended; use `--json` for the complete structured list. Do not treat this review as a content verification or as a reserved plan for a later run. Record the outcome, then remove this completed TODO item.

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

---

## 6. To Discuss (No Implementation Agreed Yet)

- **Renamed files and directories:** decide whether a pure rename should create an entry in `history`, or whether macbackup should recognize and move the existing cloud copy while retaining the current backup contract. Define how to distinguish a rename from an unrelated deletion plus addition, what evidence is reliable for both plain and crypt remotes, and how `preview`, `status`, and interrupted runs would explain the result. No rename-detection change has been approved.
- **Atomicity and recovery of `run`:** the current run is not atomic across files, areas, or providers; `status` reports a partial or interrupted result after transfer has started. Decide whether stronger guarantees are needed, and at what scope, before proposing a transaction-like design. In particular, discuss interruption during planning or policy archiving, retries, and whether a complete multi-provider snapshot is actually required. This is a question for design, not a promise that a fully atomic cloud backup is feasible.
- **Viewing backups on a phone:** confirm the desired mobile workflow once the Proton target is configured. Plain files can be browsed through a provider app when their formats are supported; rclone-crypt private copies require a compatible decryption workflow and should not be presented as directly readable there. Decide whether phone access is needed only for plain `current`, whether historical copies matter, and how to keep the private area protected.
- **Following selected symlinks:** consider an explicit opt-in list of symlinks whose targets should also be backed up; keep the current link-only behavior for all others unless a different policy is deliberately chosen. Decide whether target contents should appear under the symlink path or their real path, how plain/private/exclude and explicit-only rules apply, and whether the link itself is still saved separately. Specify handling for cycles, duplicate targets, missing or changing targets, symlinks that escape selected sources, and external volumes. Do not enable following all symlinks by default without resolving these cases. No behavior change is planned now.
