# macbackup — Technical TODO & Review Findings

Open items from the code, test, and documentation review. Recheck each against the current script before implementation.

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
