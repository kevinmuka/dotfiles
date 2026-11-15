# macbackup — Technical TODO & Review Findings

Open items from the code, test, and documentation review. Recheck each against the current script before implementation.

---

## Pending live review: paths planned for archiving

The explicit file/directory syntax and policy overlap checks were implemented in 0.13.0. Their current contract and design reasons are in [POLICY_DESIGN.md](POLICY_DESIGN.md); the [manual](README.md) explains how to use them, and the [changelog](CHANGELOG.md) records the migration and synthetic tests. No syntax or overlap implementation remains open in this section.

A read-only Google preview on 2026-11-07 reported zero policy archives and 20 plain plus one private copies absent from the local selection. The successful run recorded on 2026-11-09 archived 20 plain and one private copy. Those old counts are not a pending plan, and the old status format does not reliably identify which history entries were exactly those 21 absence archives. Before a future `run`, use a fresh `macbackup preview --target google` to inspect every path then planned for archiving. That preview does not verify contents or reserve a plan for the later run. Remove this item after reviewing the new plan, not by treating the 2026-11-07 counts as current.

---

## 1. Repeated `os.path.realpath` Calls in `Policy.decide` *(Gemini performance hypothesis reviewed on 2026-11-13)*

- **Source:** Gemini (`0.14.3` review). The call is unconditional. `scan_policy` calls `decide` twice for most visited entries (a preliminary subtree decision and the typed decision), and remote planning calls it for each existing current file. This is real repeated work, but no profile establishes its share of the observed end-to-end time; long remote inventories and private comparisons are separate costs.
- **Safety constraint:** The physical path is needed at the *start* of every decision to exclude the state directory even through a symlinked parent. A synthetic plain inclusion through a symlink alias into `.local/state/macbackup` currently returns `skip`. Merely deferring `realpath` until the plain-credential check would lose that protection.
- **Recommended work:** Profile local scan and remote planning separately before optimizing. If the cost is material, remove the duplicate call per local entry or use carefully validated resolution caching while preserving state and credential checks for aliases and path changes. Add regression tests for a symlinked state-directory ancestor and a symlinked rclone-credential ancestor before changing this logic. Treat performance improvement as unproven until measured.

---

## 2. Future Roadmap Items (Tracked from Architecture Design)

- **Proton Drive target setup & verification:** configure `pdrive:` and `pdrive-private:` (`crypt`) with a small pilot before enabling a full backup; test transfer, `verify`, restore, mount, and `forget --mode trash`. The [rclone Proton Drive backend](https://rclone.org/protondrive/) is documented as Beta and may be incompatible with some accounts; do not infer reliability from Google tests.
- **External volume identity verification:** verify volume UUID / mount identity when backing up paths under `/Volumes/...` so an unmounted or wrong volume is never mistaken for a valid source.
- **Full-directory / subtree restore:** extend `restore` (or add a dedicated command) to recompose a directory tree from `plain/current` and `private/current` into a chosen local folder. Gemini's note about recreating `.rclonelink` symlinks and optionally applying `macos-icons` snapshots is sound for a complete current-state restore. A historical directory snapshot is a separate, harder feature because each `history/<run_id>` is sparse rather than a full snapshot.
- **Scheduled automation (`launchd`):** after both targets and archive limits are settled, use the actual installed Python/rclone paths discovered at setup and report failures, including `max_delete` stops. Gemini's notification idea is useful; its example binary paths happen to match this Mac now but are not portable defaults. Define how credentials and noninteractive errors are handled before enabling unattended runs.
- **History retention / pruning (Gemini proposal):** an explicit inspect/plan/apply workflow could control unbounded history growth, but it must be designed separately from path-scoped `forget`. Never infer that `rclone cleanup` is safe for one history subtree: on Google Drive it empties the account's trash rather than pruning a selected `history/<run_id>`. Require a reviewed scope, a restore test, and clear treatment of provider trash/native revisions before any automatic retention.
- **Repository documentation links:** add `macbackup` to the root `README.md`, `docs/MODULES.md`, and `docs/DEPENDENCIES.md` (and sync the English/Italian pages in `dotfiles-site` when ready).

---

## 3. To Discuss (No Implementation Agreed Yet)

- **Renamed files and directories:** decide whether a pure rename should create an entry in `history`, or whether macbackup should recognize and move the existing cloud copy while retaining the current backup contract. Define how to distinguish a rename from an unrelated deletion plus addition, what evidence is reliable for both plain and crypt remotes, and how `preview`, `status`, and interrupted runs would explain the result. No rename-detection change has been approved.
- **Atomicity and recovery of `run`:** the current run is not atomic across files, areas, or providers; `status` reports a partial or interrupted result after transfer has started. Decide whether stronger guarantees are needed, and at what scope, before proposing a transaction-like design. In particular, discuss interruption during planning or policy archiving, retries, and whether a complete multi-provider snapshot is actually required. This is a question for design, not a promise that a fully atomic cloud backup is feasible.
- **Viewing backups on a phone:** confirm the desired mobile workflow once the Proton target is configured. Plain files can be browsed through a provider app when their formats are supported; rclone-crypt private copies require a compatible decryption workflow and should not be presented as directly readable there. Decide whether phone access is needed only for plain `current`, whether historical copies matter, and how to keep the private area protected.
- **Following selected symlinks:** consider an explicit opt-in list of symlinks whose targets should also be backed up; keep the current link-only behavior for all others unless a different policy is deliberately chosen. Decide whether target contents should appear under the symlink path or their real path, how plain/private/exclude and explicit-only rules apply, and whether the link itself is still saved separately. Specify handling for cycles, duplicate targets, missing or changing targets, symlinks that escape selected sources, and external volumes. Do not enable following all symlinks by default without resolving these cases. No behavior change is planned now.
