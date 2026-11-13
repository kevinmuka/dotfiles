# macbackup: selection policy design

This is a detailed reference for **using and maintaining** the implemented selection policy. It covers configuration syntax, the full decision order, the scope of each exception, examples, cloud consequences, and the reasons behind the rules. The [English user manual](README.md) and [Italian manual](README.it.md) cover the complete command workflow; the [changelog](CHANGELOG.md) records when behavior changed; the [TODO](TODO.md) holds unfinished work. For a behavior change, check the current script and tests before relying on this document. Examples here are synthetic and do not describe anyone's current backup.

Use **Part I** as a configuration and troubleshooting reference. **Part II** records the design reasons, safety properties, and known limits for readers changing the implementation or evaluating a validation rule.

## Part I: Using the policy

Read this part to choose entries and predict what will be backed up. [Part II](#part-ii-design-reasons-and-invariants) explains why the safeguards exist.

### Configuration files and scope

The default directory is `~/.config/macbackup/`. The command-level `--config-dir PATH` selects another directory containing the same five files. These are macbackup policy files, not rclone filters:

| File | What an entry does | Scope |
|---|---|---|
| `plain-paths.txt` | Selects one file/symlink or a directory subtree for readable backup, subject to other rules. | Literal absolute path |
| `private-paths.txt` | Selects one file/symlink or a directory subtree for the rclone-crypt area, subject to other rules. | Literal absolute path |
| `exclude-paths.txt` | Hard-excludes a file/symlink or entire directory subtree. An inclusion cannot reopen it. | Literal absolute path |
| `explicit-only-patterns.txt` | Requires an exact path-list inclusion before a matching basename is admitted. A matching directory is pruned until included exactly. | Case-insensitive basename, any depth beneath a selected source |
| `settings.toml` | Holds targets, `max_delete`, and the optional `[policy]` settings `ignored_file_names`, `private_directory_names`, and `use_gitignore`. | Target/area or basename, depending on key |

Path-list lines and explicit-only pattern lines may be blank or start with `#`; trailing inline comments are not supported. Do not quote paths with spaces inside these files. Shell examples *do* need quoting when a path has spaces. The lists do not expand `~`, environment variables, or command substitutions. `init` creates valid empty inclusion lists and conservative `.env` file/directory patterns; its example paths are comments, not active sources. An absent or unreadable explicit-only file is an error, not an empty policy.

The policy portion of `settings.toml` uses literal names for the two arrays and a Boolean for Git ignore. This is a synthetic example, not a recommended list of names for every computer:

```toml
schema_version = 1
max_delete = 25

[policy]
private_directory_names = [".git"]
ignored_file_names = [".DS_Store"]
use_gitignore = true
```

The same TOML file also contains `[targets.<name>]` tables with `enabled`, `plain`, and `private` remote settings; see the [user manual](README.md#3-configuration) for a complete example. `init` sets `use_gitignore = false` and `max_delete = 25`. The archive limit accepts integers from 0 through 10,000. Target settings determine where selected files go; they do not change how a path is classified.

A selected source can be anywhere on the Mac, not only below the home directory. External volumes need an additional identity safeguard before they can be treated as reliably present; that work remains in [TODO](TODO.md). A file in a selected directory may still be skipped or routed to the other area. `plain` and `private` are distinct outputs; listing a directory in plain does not force its protected or private descendants into plain.

#### A worked selection

Assume these synthetic settings and paths, with `/Users/example/Desktop/project/` existing:

```text
plain-paths.txt:          /Users/example/Desktop/project/
private-paths.txt:        /Users/example/Desktop/project/secret.txt
exclude-paths.txt:        /Users/example/Desktop/project/cache/
explicit-only-patterns:  .env   .env.*   .env/   .env.*/   node_modules/
```

Assume also `private_directory_names = [".git"]`, `ignored_file_names = [".DS_Store"]`, and `use_gitignore = true`. The entries below explain the **logical** result before any cloud transfer:

| Path under `project/` | Result | Why |
|---|---|---|
| `README.md` | plain | Inherited from the project directory; no other rule changes it. |
| `secret.txt` | private | Its exact private entry beats the plain parent. |
| `cache/data.bin` | skipped | The absolute directory exclusion cannot be reopened by a child entry. |
| `.env` or `.env.local` | skipped | The explicit-only file pattern requires an exact entry for each file. |
| `.env/notes.txt` | skipped | The explicit-only directory is pruned; an exact `.env/` entry would permit traversal, but protected children would still need their own entries. |
| `node_modules/package.json` | skipped | The protected directory is pruned unless `node_modules/` is listed exactly. |
| `.DS_Store` | skipped | An inherited file matches `ignored_file_names`; a single exact file entry would allow only that copy. |
| `.git/objects/ab` | private | Automatic directory routing encrypts otherwise eligible descendants, even if Git ignores `.git/`. |
| `.git/.env` | skipped | Automatic encryption does not grant an exact exception to the `.env` file. |
| `build/generated.txt` when `build/` is Git-ignored | skipped | The ignored directory is pruned unless separately entered as a root; children still face their own ignore rules. |

Listing `/Users/example/Desktop/project/.env` exactly in `plain-paths.txt` would make that one file plain and warn that a protected name was intentionally allowed in plain. Listing it in `private-paths.txt` instead would encrypt that one file. Do not list the identical path in both files: that is a configuration error. Listing `/Users/example/Desktop/project/node_modules/` exactly lets macbackup visit that directory, but does not authorize a nested `.env`. Listing `/Users/example/Desktop/project/.git/` exactly in plain disables **automatic** private routing for that directory, unless an explicit private ancestor covers it; a nested `.env` still needs its own exact entry. These exceptions apply only at their exact path, never to every descendant by implication.

An exact file path can also override an effective `.gitignore` rule for that file, including an ignored ancestor, because each directly listed source is visited on its own. An exact ignored **directory** permits traversal of that directory; it does not override Git ignore for all of its descendants. An absolute exclusion of the file or any ancestor still blocks it. If an included source is below an excluded ancestor, it is suspended with a warning rather than treated as an active missing source.

### Typed paths and exactness

The three absolute path lists use a final `/` to declare a directory and its subtree. Without it, a line declares one file or symlink. The final slash is a type marker, not an optional spelling. Existing objects whose actual type differs are configuration errors before cloud access. A missing active inclusion is an error; a missing exclusion may describe a future path, whose type is checked if it appears. A directly included path beneath an excluded **ancestor** is suspended: `check` warns with both source lines, and its absence does not block a run. The identical normalized path in inclusion and exclusion lists is rejected instead.

Paths are absolute and literal, with case-sensitive spelling. The parser does not expand `~`, variables, commands, or wildcards. It rejects relative paths, `..`, the entire `/` root, ambiguous whitespace, and control characters. A directory inclusion supplies a source for recursive traversal; it does **not** make every descendant an exact inclusion. An exact file entry authorizes that file only. An exact directory entry permits traversal of that directory, while each child is classified again. This distinction is central to `.env`, ignored names, `.gitignore`, and automatic private directories.

Symlinks are individual entries, even if their target is a directory. The scanner does not traverse a selected link, and the stored `.rclonelink` suffix is a transport representation rather than part of the policy path. The link target must be selected separately if its content is needed. Ordinary selected files named with the reserved `.rclonelink` suffix are rejected to prevent representation collisions. Finder's `Icon\r` is a special supported file and is stored separately as an `icon.json` snapshot; its logical selection still follows the policy.

Sockets, FIFOs, and devices inherited through a selected directory are skipped with a warning; listing one of them directly is an error. A selected symlink produces a warning that its target is not traversed, but the link itself remains selected. Other control-character names cannot be represented by the backup. Finder icon snapshots retain their special handling in both areas and in archive planning; ordinary files' resource forks, ACLs, and extended attributes are not reconstructed by this backup.

### Decision order

`Policy.decide` first excludes macbackup's operational state and default Desktop mountpoints, including the physical state path, then applies absolute exclusions. Those are hard boundaries: no descendant inclusion reopens an excluded directory. If neither plain nor private inclusion reaches a path, it is skipped.

For an included path, `ignored_file_names` skips a non-directory entry unless that exact path is listed. `private_directory_names` then identifies matching directory ancestors for automatic encryption, except where that directory itself is exactly listed in plain. Directory explicit-only protection can prune an ancestor; a directory automatically routed to private is its deliberate exception. A matching file or directory explicit-only pattern otherwise requires an exact path entry. Effective `.gitignore` exclusion applies next when enabled, except for an exact path entry or automatic private-directory routing. An explicit private inclusion wins over an overlapping plain inclusion at a **different** path. Automatic private-directory routing follows; an allowed plain inclusion is the final case. The order of lines in a list does not alter this decision order.

Two identical normalized absolute paths in the same list or across `plain-paths.txt`, `private-paths.txt`, and `exclude-paths.txt` are errors. This makes an otherwise invisible precedence choice explicit. Parent/child overlaps remain valid: a plain project can contain a private subtree, and either a plain or private subtree can contain an excluded child. An exact plain entry cannot override an explicit private ancestor. It can override only automatic `private_directory_names` routing when the **matching directory itself** is listed in plain and no explicit private rule covers it.

For example, with `project/` selected as plain and `private_directory_names = [".git"]`, `project/.git/` and its otherwise allowed descendants go to private. Listing `project/.git/` exactly in plain disables that automatic routing for that directory; listing only `project/` does not. A protected `.env` within `.git/` still needs its own exact inclusion. A private rule covering `project/` still takes precedence over an exact plain `.git/` child. An absolute exclusion remains final.

### Validation outcomes: errors and warnings

Validation errors stop `check` and prevent `run` from transferring files. They include a repeated normalized absolute path anywhere in the three path lists; an existing path whose type disagrees with its trailing `/`; a missing active inclusion; a directly selected special file; an unreadable selected file; a selected ordinary file ending in `.rclonelink`; and one underlying file selected into both areas through hard-link names. A selected rclone configuration file in plain is also an error: the default `~/.config/rclone/` and `~/Library/Preferences/rclone/` locations, their physical targets, and an active `RCLONE_CONFIG` path are protected. Route a selected configuration file to private or exclude it.

Name-rule errors include case-insensitive duplicate literal names within either TOML list; duplicate or fully contained explicit-only patterns of the same file/directory type; a directory explicit-only pattern matching a `private_directory_names` value; and a file explicit-only pattern matching an `ignored_file_names` value. These conflicts are rejected before cloud access. The last pairing is unsafe for protected hard-link aliases; [Part II](#safety-checks-and-overlap-rationale) explains why. A file pattern `.git` and a private directory name `.git` are valid together because they cover different types.

Warnings allow the run to proceed. Examples are a directly included source suspended by an excluded **ancestor**, a selected symlink whose target is not traversed, an inherited special file that was skipped, an exact plain inclusion of a protected name, and a demonstrable partial overlap between same-type explicit-only patterns. When Git ignore is enabled, an exact inclusion or automatic private-directory routing that overrides an effective `.gitignore` rule also warns; ordinary ignored paths do not. Each warning describes the rule or path involved so it can be reviewed before transfer.

### Name-based rules

`explicit-only-patterns.txt` protects basenames across selected sources. A trailing `/` selects directory names; no slash selects file and symlink names. Its supported wildcard is `*` in a single basename. It is not a path glob, regex, `.gitignore` rule, or rclone filter. A protected directory is pruned with its descendants until listed exactly. A protected file is omitted unless listed exactly. This makes sensitive names opt-in, even beneath an explicitly private parent.

`private_directory_names` contains literal directory names. It routes matching directories and otherwise eligible descendants into crypt, but does not make every protected descendant eligible. `ignored_file_names` contains literal names for non-directory entries, including symlinks. It is suited to harmless noise such as `.DS_Store`; an exact inclusion may override it. Both TOML lists and explicit-only patterns compare names case-insensitively with Unicode `casefold`, including on case-sensitive volumes. That conservative rule protects case variants such as `.ENV`. Absolute path lists remain case-sensitive so distinct filesystem paths remain distinct. Duplicate TOML names differing only by case fail; exact and case-only duplicate explicit-only patterns of the same type fail.

### Git ignore integration

`use_gitignore` defaults to `false`. When enabled, macbackup asks Git to evaluate effective `.gitignore` rules, including ancestor and nested files, along physical parent paths. This works outside Git repositories. It does not consult the index, `.git/info/exclude`, or global excludes. Git patterns and negation are interpreted by Git, not reimplemented by macbackup. A Git failure stops selection rather than silently disabling the rule. An ignored directory is pruned; a later exact file entry can still be visited as its own root.

An exact inclusion overrides an effective Git ignore rule **only for that path**. Exactly including an ignored directory permits traversal, but descendants can still be ignored. Automatic private-directory routing also overrides Git ignore for the matching directory, so an ignored `.git/` can be encrypted when that policy is active. `check` warns when either exception actually overrides an effective ignore rule, naming the exact path-list source and Git source/line, or at most once per automatically private directory. Ordinary ignored paths do not warn. These are dynamic observations, not static configuration errors: `.gitignore` files can change independently inside projects, and the exceptions may be intentional. Absolute exclusions still win.

### What a policy change does to remote copies

`transfer_plan` compares each existing `current` object with today's policy. If it still belongs in its current area but is absent from today's local selection, it belongs to the local-absence archive plan (`archive_deleted` is the retained JSON field name). Absence from selection does not prove a file was physically removed. If today's policy classifies it as `skip` or into the other area, it belongs to `policy_archives`, with the current decision reason and rule when available. That rule is **not** a reconstruction of the rule that originally uploaded the copy. Remote preview lists both categories separately; Finder icon snapshots are planned under their own `macos-icons` kind.

During `run`, old copies move from their original area's `current` into that area's sparse `history/<RUN_ID>`. For a plain/private reclassification, the old copy moves **before** the new-area upload begins. This prevents a macbackup run from creating two current copies of the same logical path. It can leave a temporary gap in `current` if the run stops after the move; the old copy remains in its original area's history and the next run can upload the new-area copy. A move from plain to private does not encrypt or erase the old plain history; a new private copy is uploaded separately. `forget` is the deliberate operation for removing retained current and historical copies. `max_delete` bounds the combined local-absence and policy archive count, including icons, **per target and area**. The current plan can change between preview and run. The run is not atomic across files, areas, or providers; direct cloud or rclone changes are outside its local lock.

If the same file path is already present in both current areas, `check --remote` reports a warning only when the policy identifies a file copy to archive first. Remote preview shows the same conflict and the proposed archive area; run may repair it within `max_delete`. A conflict without an identifiable file move, including an ambiguous file/directory collision, stops check, preview, and run before cloud writes. The merged mount always refuses an existing conflict rather than hiding either copy. These checks concern current file paths; shared directory ancestors are normal.

A directly listed inclusion that disappears is an error, not permission to treat its entire former subtree as deleted. First correct or remove that path-list entry; if an excluded ancestor suspends it, the missing source only warns. By contrast, a child that disappears beneath an existing selected directory can be archived as absent from the local selection. This distinction matters for disconnected external volumes: macbackup does not verify volume identity, so an existing mountpoint alone is not proof that the intended disk is attached.

Removing **all** entries from both inclusion lists does not by itself protect already uploaded copies from archiving. If a target still has files in `current`, `run` can plan their move to history, subject to `max_delete`; inspect `preview --target` before proceeding. If the lists are empty and there are no current copies to archive, the remote operation stops without work. An interrupted or failed run can leave some moves or uploads complete and others pending; `status` reports the partial outcome rather than turning the whole run into an atomic transaction.

Changing a policy must not directly remove history. This preserves older recoverable copies, but it also means reclassifying a secret from plain to private can leave readable plain history. Review `versions`, plan a scoped `forget`, and apply it intentionally if that history must be removed. The same caveat applies to copies already in provider trash or native revisions, which the selection policy does not inventory.

### Inspecting a change before a backup

After editing a policy, run `macbackup check` first. It validates syntax and existing source types, scans the selected paths, and reports errors and warnings without accessing the cloud. A missing active inclusion, a type mismatch, a prohibited overlap, or an unreadable selected file blocks the backup; a suspended inclusion or an intentional Git ignore override is a warning. `macbackup explain ABS_PATH` classifies one path and shows its current reason, but does not prove that the file is in the scanned set or already saved. `macbackup preview --local` shows the complete local classification without cloud access. `macbackup layout PATH` can summarize private subtrees inside a selected plain directory.

For an enabled target, `macbackup preview --target google` reads `current` and lists proposed archives without writing to the cloud. The human output and JSON distinguish copies absent from the local selection (`archive_deleted_paths`) from copies reclassified by the current policy (`policy_archives`). Review every listed path and whether the combined count exceeds `max_delete`. `--simulate` also performs slower content comparisons and rclone dry-run transfer checks; neither mode reserves the plan. `run` rescans and rebuilds it. After a real run, `status` records both planned archive lists. `archive_deleted_completed_paths` separately records planned absence archives confirmed in that run's history after a partial phase; `null` means the history could not be read or the process stopped before reconciliation. An unfinished phase does not prove every planned move completed. `versions` can find retained copies, and `forget` requires a separate explicit plan and apply step to remove them. `verify` compares today's selected sources with `current`; it is a different question from policy planning.

## Part II: Design reasons and invariants

Read this part when changing the selector or reviewing a policy validation error. The operational rules and examples are in [Part I](#part-i-using-the-policy).

### Why the selector owns these rules

`macbackup` classifies local paths before giving rclone an exact NUL-delimited manifest. rclone then transfers only those names with `--files-from0`, preserving symlinks via `--links` without copying their targets. `explicit-only-patterns.txt` and the other selection rules belong to macbackup, not rclone. Replacing the manifest with recursive rclone includes could admit a newly created protected file. Adding rclone filters beside `--files-from0` would not implement these rules reliably.

The same policy classifies objects already in remote `current`. This is necessary when a rule changes: an old copy that is no longer allowed in its original area must be planned for archiving, not mistaken for an ordinary local deletion. Local scanning and remote classification therefore need the same directory-pruning and area-routing semantics. A remote preview reads inventories and makes a plan; it does not prove physical deletion, compare all content, or reserve state for `run`.

### Safety checks and overlap rationale

A directory explicit-only pattern that matches a `private_directory_names` value is rejected, including through `*`: automatic private routing makes that directory protection ineffective. A file pattern `.git` is compatible with a private **directory** name `.git`, because the two rules govern different object types. A file explicit-only pattern matching an `ignored_file_names` value is also rejected. Although both rules skip an inherited name and permit exact inclusion, ignored-name handling returns before explicit-only can mark a protected inode. That can let a second hard-link name expose the same bytes through plain selection. The error preserves the stronger explicit-only safeguard instead of silently weakening it. A hard link is another name for the same file and inode, not a symlink.

For two explicit-only patterns of the same type, provable full containment is an error: `node*/` makes `node_modules/` redundant. A provable partial overlap is a warning: `node*/` and `*modules/` share some names but each covers other names too. File and directory patterns with the same spelling are not redundant because they govern different types. The validator reasons about its supported `*` syntax and should not claim relationships it cannot establish. Error messages identify relevant file/line or TOML values; overlaps that are legal but worth attention remain warnings.

The scanner also checks selected regular files by `(device, inode)`. It rejects one underlying file selected into both plain and private. When a protected-name file is observed, a different selected hard-link alias must have its own exact inclusion; its innocent-looking name cannot silently bypass the protected-name decision. This check applies to aliases the local scan actually observes. It is not a content scanner and cannot detect secrets inside unrelated files or archives.

### Evidence and current limits

The focused tests in `tests/macbackup/` cover typed file/directory rules, missing inclusions and future exclusions, exact versus inherited decisions, symlinks, case variants, duplicate and overlapping patterns, Git ignore exceptions, hard-link aliases, policy reclassification, local-absence archiving, icons, and `max_delete`. Local `check` and `preview --local` validate a selection without cloud writes; `preview --target` reads `current` and shows the proposed archives. Synthetic remotes validate transfer behavior, but do not certify a live provider or every historical copy.

The rclone configuration guard covers the default config directories and their physical targets. If `RCLONE_CONFIG` is set, it also covers that file and its physical target; macbackup resolves a relative value against its working directory. This guard does not discover other credential files or arbitrary secrets. External volume identity is also not validated. Keep these limits visible rather than assuming that all credentials or all mounted sources are protected automatically.
