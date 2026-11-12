# macbackup: user manual

**Documented macbackup version: `0.14.5`.** Check the installed version with `macbackup --version`.

`macbackup` selects files and directories on a Mac, copies them through rclone, and separates readable files (`plain`) from files encrypted with rclone crypt (`private`). The remote layout mirrors original paths and keeps previous copies in `history`. It is neither a bootable Mac backup nor a consistent snapshot of running applications.

This is the **primary, current manual**. It uses examples rather than one computer's configuration. An [Italian translation](README.it.md) is also available. The [policy reference](POLICY_DESIGN.md) separates detailed usage and examples from design reasons and invariants; the [technical changelog](CHANGELOG.md) records when behavior changed and how it was tested. For your actual selection, use `macbackup check` and `macbackup preview --local`; for the last transfer, use `macbackup status`.

## 1. Installation and first check

You need macOS, Python 3.11 or later, and rclone in `PATH`. The Python script has no external package dependencies. `use_gitignore = true` also requires Git. The versioned script is at `home/.config/scripts/macbackup` in the dotfiles repository. If your dotfiles link that directory to `~/.config/scripts`, the executable is `~/.config/scripts/macbackup`; put it in `PATH` to invoke `macbackup` by name. The default operating configuration is `~/.config/macbackup/`; state is stored in `~/.local/state/macbackup/`. Run `rclone config file` to locate rclone's configuration.

```sh
macbackup --version
macbackup init
macbackup check
macbackup preview --local
```

`init` creates four lists and `settings.toml` with no active inclusions or enabled targets. It refuses to overwrite even a partially existing configuration. New files have mode 600 and a new configuration directory has mode 700. Lists and state may expose sensitive names: protect them and review them before adding them to Git. Keep a secure copy of rclone configuration and crypt keys independently of the Mac.

### Interface language

Terminal messages, progress bars, `--help`, and Zsh completion descriptions default to **English**. Set `MACBACKUP_LANG=it` for Italian:

```sh
MACBACKUP_LANG=it macbackup check           # this command only
export MACBACKUP_LANG=it                    # subsequent commands too
source ~/.zsh/integrations/macbackup.zsh    # reload completion in this shell
```

Use `unset MACBACKUP_LANG` and reload the integration to return to English; `MACBACKUP_LANG=en` explicitly selects English. This setting does not change commands, flags, JSON field names, paths, or backup rules. Explanatory strings in new reports use the active language. `status` displays previously saved reports in their original language without rewriting them. Completion chooses its language when the Zsh integration is loaded, so changing the variable in an open shell requires sourcing it again.

## 2. Location on the Mac and relationship with Git

| Item | Typical location |
|---|---|
| Versioned script | `<dotfiles-repo>/home/.config/scripts/macbackup` |
| Command through dotfile symlinks | `~/.config/scripts/macbackup` |
| Lists and settings | `~/.config/macbackup/` |
| State and `forget` plans | `~/.local/state/macbackup/` |
| rclone configuration | Path returned by `rclone config file` |

`~` denotes the user's home in this table. The path lists require **absolute** paths, such as `/Users/example/Documents/`. The script, tests, and manual can be versioned; tokens, crypt passwords, operational state, and personal path lists need separate protection. Global `--config-dir PATH` changes the lists and `settings.toml` directory, not the location of state or rclone credentials.

## 3. Configuration

The configuration directory contains `plain-paths.txt`, `private-paths.txt`, `exclude-paths.txt`, `explicit-only-patterns.txt`, and `settings.toml`. The first three list absolute paths. The fourth lists names requiring exact inclusion. Targets and name-based policies live in TOML.

Adapt this **example**; it is neither the default nor a snapshot of a particular installation:

```toml
schema_version = 1
max_delete = 100

[policy]
private_directory_names = [".git"]
ignored_file_names = [".DS_Store", ".localized"]
use_gitignore = false

[targets.google]
enabled = false
plain = "gdrive:MacBackup/plain"
private = "gdrive-private:"

[targets.proton]
enabled = false
plain = "pdrive:MacBackup/plain"
private = "pdrive-private:"
```

`init` writes `max_delete = 25`; `100` above is an example of a deliberate choice. Valid values are integers from 0 to 10,000. The limit applies per target and area to copies archived because of local deletion or policy changes, including icons. It does not expire history. Configure and test both rclone remotes before enabling a target in `settings.toml`. `check --remote`, `preview --target`, `run`, and `mount` require an enabled target; for these commands `--target all` requires both targets to be enabled. `versions`, `restore`, `verify`, and `forget` can read a disabled target if its remotes remain configured.

A plain remote such as `gdrive:` accesses the provider. A crypt remote such as `gdrive-private:` wraps the **same account's** private directory; it is not an independent second copy. In the example, `gdrive-private:` must point at `gdrive:MacBackup/private`. Proton needs its own separate remote pair. These names are examples; `settings.toml` is authoritative. Plain files can be opened in the provider's app when their format is supported. Private files require rclone crypt and its keys.

### 3.1 Path-list syntax

- Each line contains one literal absolute path. Blank lines and lines starting with `#` are ignored.
- Do not quote paths in the lists, even when they contain spaces. Trailing inline comments are unsupported.
- `~`, `$HOME`, variables, commands, and wildcards are not expanded.
- A directory path **must** end in `/`; a file or symlink path **must not**. A type mismatch on an existing path is a configuration error before cloud access. A missing exclusion may name a future path; its declared type is checked when it appears. A directly included missing source is an error unless an ancestor exclusion suspends it.
- A file or symlink selects only itself. A directory selects descendants recursively, including hidden files, subject to the other rules. A symlink to a directory remains a symlink; its target is not traversed.
- Relative paths, `..` components, and selecting the entire `/` root are rejected. `/` is only the reference for reconstructing original paths.
- Names that cannot be represented unambiguously in a line-based list, such as names with newlines, cause an explicit error instead of being silently skipped.

Paths are literal: `[` or `*` inside a filename must not accidentally become an rclone filter.

### 3.2 Rule precedence

1. An absolute entry in `exclude-paths.txt` wins over every inclusion, including an exact private one.
2. `ignored_file_names` skips a matching **file** inherited from a parent directory; an exact file entry in plain or private overrides it. The rule does not apply to a directory of the same name.
3. A file or directory matching `explicit-only-patterns.txt` requires its complete path directly in plain or private. A parent-directory entry is insufficient; a skipped directory is not traversed. Exception: a directory also matched by `private_directory_names` is traversed and encrypted unless exactly included in plain. Other rules still apply inside it.
4. With `use_gitignore = true`, `.gitignore` can exclude a path inherited from a parent directory. An exact inclusion and automatic routing via `private_directory_names` override that exclusion. An ignored directory is not traversed.
5. After these checks, a private rule wins over an overlapping plain rule at a **different** path. The identical normalized path in two path lists is a configuration error. A directory named in `private_directory_names` and its descendants go to private unless that directory is **exactly** listed in plain and is not covered by private. Listing only a parent does not disable automatic encryption.
6. An allowed plain inclusion goes to `plain`; a path with no applicable inclusion is skipped.

An excluded directory cannot be reopened by including a descendant. Plain cannot override an explicit private directory inclusion; its exception applies only to automatic name-based privacy and requires the directory's exact path. The order of lines does not change these rules.

The validator also checks rules that would conceal one another. It rejects the same normalized absolute path repeated within one list or across the three path lists, with both file and line numbers. Different parent and child paths are allowed: a plain project can contain a private `.git/` and an excluded `build/`. If an excluded **ancestor** covers a directly included source, `check` warns with both lines and suspends that source; its absence does not block `run`. Removing the ancestor exclusion makes the source mandatory again. An identical include and exclude path is an error, not a suspended source.

Name rules are compared without regard to case, while absolute paths keep their exact spelling. Duplicate TOML names, a directory explicit-only pattern matching a `private_directory_names` value, and a file explicit-only pattern matching an `ignored_file_names` value are configuration errors. This includes wildcard matches such as `.g*/` against `.git` and `.D*` against `.DS_Store`. The latter combination is rejected because the ignored-name check would bypass explicit-only's hard-link alias protection. A file-only `.git` pattern and a private directory name `.git` are compatible: they apply to different object types. Among explicit-only patterns of the same type, full containment is an error (`node*/` makes `node_modules/` redundant), while demonstrable partial overlap is a warning (`node*/` and `*modules/`). These checks run when the policy is loaded, before cloud access.

For sensitive names, keep the name in explicit-only rather than also adding it to `ignored_file_names`. The ignored-name check would otherwise return before the scanner records that the file's inode is protected; a second hard-link name could then expose the same bytes in plain. A hard link is another filename for the same file, unlike a symlink. The [policy design reference](POLICY_DESIGN.md) records this and the other overlap decisions in detail.

`.gitignore` intersections are checked during the local scan. An effective ignore rule normally skips a path without a warning. If an exact inclusion overrides it, `check` reports the included path, its path-list line, and the `.gitignore` source and line. Automatic private-directory routing that overrides an ignore rule produces at most one warning per directory. Both are intentional exceptions: warnings do not block `run`, and an exact directory exception does not extend to its descendants.

**Scope of an inclusion versus scope of an exception.** Listing a directory selects its subtree, but it does not turn every descendant into an *exact* inclusion. Each child is classified against the rules again. Listing one exact file or directory grants an exception only at that path; it does not grant exact exceptions to its children or to another path with the same name.

| Rule | What happens under a selected directory | What an exact entry changes |
|---|---|---|
| `ignored_file_names` | Matching non-directory entries are skipped at any depth. | Listing one matching file or symlink directly in plain or private includes that entry; other matches stay skipped. |
| `explicit-only-patterns.txt` | A matching file is skipped; a matching directory is pruned with its descendants. | Listing the protected path directly allows that entry. If it is a directory, traversal resumes, but protected descendants still require their own exact entries. |
| `.gitignore` with `use_gitignore = true` | Git's effective ignore rules are checked for each inherited path; an ignored directory is pruned. | Listing one path directly overrides Git ignore for that path. Listing an ignored directory does not override ignore rules for all its descendants. |
| `private_directory_names` | A matching directory and its otherwise eligible descendants go to private. | Listing that directory itself in plain overrides automatic encryption for its subtree, unless an explicit private inclusion also covers it. Other child-level rules still apply. |
| `exclude-paths.txt` | An excluded directory and its entire subtree are skipped. | No exact inclusion can reopen an excluded path or child. |

For example, with `project/` selected, an ignored `project/build/` is skipped. Listing `project/build/` directly allows the directory to be visited, but files under it can still be ignored; list a specific file directly if it too needs an exception. Likewise, listing a protected `project/node_modules/` allows traversal but does not authorize a protected `.env` inside it. Use `explain ABS_PATH` to inspect one classification and `preview --local` to inspect the selected set before a run.

With `private_directory_names = [".git"]`, a `.git` directory beneath a selected source is encrypted. A file named `.git` can separately be explicit-only; the directory pattern `.git/` would be redundant and is rejected. Listing `/Users/example/Desktop/project/.git/` directly in `plain-paths.txt` instead makes that directory and its otherwise allowed contents plain. Do not list that identical path in private too: it is an error. An explicit private **ancestor** still wins over the plain child. A `.env` inside it still needs its own exact inclusion. Absolute exclusions still win. Changing `.git` from private to plain archives the old copy under `private/history` and uploads the new copy under `plain/current`; use `forget --area private` to remove the old encrypted copy as well.

A path covers itself and descendants, not similar names: `/a/karabiner/` does not cover `/a/karabiner-old/`.

`ignored_file_names` entries are literal case-insensitive basenames, without paths or wildcards. TOML spaces matter: `" ← "` matches a filename with spaces on both sides of the arrow. An exact file inclusion overrides this policy only for that file; an identical plain/private path is rejected, and an absolute exclude always wins. Do not repeat a sensitive name in both `ignored_file_names` and a file-only explicit-only pattern: it is a configuration error because the former can bypass the latter's hard-link alias protection. A newly ignored current copy is archived in the same area's history on the next `run`. Local files are not deleted. Use `forget` to remove all cloud versions intentionally.

`use_gitignore = true` asks Git to read `.gitignore` files along included physical paths, even outside Git repositories. Git patterns and negation work. The index, `.git/info/exclude`, and global exclusion files are not consulted. The search starts at filesystem root, so an ancestor `.gitignore` can apply. Symlinks are not traversed. A `.gitignore` file itself remains eligible unless a rule excludes it. Git must be in `PATH`; a failed check stops selection. `init` sets this option to `false`.

Before enabling `.gitignore` processing, compare `preview --local` with the previous selection. Ignored descendants are omitted even if their parent is in a path list; an exact file entry remains included. An exact directory entry does not override rules for every descendant. Automatically private `.git` directories remain included. `check`, including `check --remote`, warns when an exact inclusion overrides an effective Git ignore rule, naming both sources; automatic private-directory routing produces at most one warning per directory. Ordinary ignored files are not warnings. These overlaps do not block `run`. New `.gitignore` rules archive previously selected current copies in their original area on the next `run`; they do not delete history.

### 3.2.1 Explicit-only names

`init` creates this initial `explicit-only-patterns.txt`:

```text
.env
.env.*
.env/
.env.*/
```

These are basenames, not absolute paths. `.env` matches a file or symlink with that name anywhere; `.env.*` includes files such as `.env.local`, `.env.production`, and `.env.example`. The `/` variants protect directories with the same names and keep their descendants out unless the directory is included exactly. Include an innocuous example file exactly if wanted; do not assume it contains no secrets. Names such as `node_modules/`, `.venv/`, `venv/`, and `myenv/` can protect directories everywhere.

Syntax permits literal names and `*` within a basename. A final `/` marks a directory pattern; its absence marks a file or symlink pattern. Internal `/`, `**`, regular expressions, and signed `+`/`-` rules are not supported. Blank and comment lines work as in the other lists. Name policies are case-insensitive, so `.ENV` also needs exact inclusion. Absolute path lists are case-sensitive and are matched by their exact spelling. Duplicate names differing only by case, duplicate normalized paths, and identical paths in different lists are errors. Within explicit-only patterns of the same type, a provably redundant pattern is an error; a provable partial overlap is a warning.

Each pattern covers only its declared type. Exactly including a protected directory allows traversal, but descendants still follow their own rules: `.env` remains protected. Selecting a symlink saves the link, not the contents at its target.

With `/Users/example/Desktop/project/` in plain:

| Additional entry | Result for `project/.env` |
|---|---|
| None | Skipped: inherited from the parent directory only |
| Exact path in plain | Saved as plain, with an explicit protected-name warning |
| Exact path in private | Saved encrypted and absent from plain |
| Project directory in private, without the exact file path | Skipped: private inclusion is still inherited |
| Exact path in both lists | Configuration error; remove the duplicate entry |
| File or ancestor path in exclude | Skipped in every case |

An exact entry for `project/.env` does not authorize `project/subdir/.env`, `another-project/.env`, or `project/.env.local`. A new `.env` appearing during a run must not slip through a recursive directory rule. Removing an exact entry or adding a new protected pattern archives an existing current copy on the next `run`; old history remains until `forget`. `preview --local` shows protected names. `preview --target` and `status` distinguish policy archives from local deletions and record the **current** rule causing exclusion; they cannot reconstruct the historical rule that first included a file.

This protects macbackup uploads only. It does not configure Git, create `.gitignore` rules, prevent pushes by other tools, or detect secrets embedded in other filenames or archives. Automatically encrypting `.git` does not erase older plain copies; find and remove those with `versions` and `forget` if necessary. A missing or unreadable `explicit-only-patterns.txt` is an error, never an empty protection list.

### 3.3 Example selection

Replace `/Users/example` with your own absolute home path and decide deliberately what should be readable:

```text
# plain-paths.txt
/Users/example/Desktop/
/Users/example/Documents/
/Users/example/.config/
```

```text
# private-paths.txt
/Users/example/.ssh/
/Users/example/.config/rclone/
```

```text
# exclude-paths.txt
/Users/example/.config/app-with-token/
/Users/example/Documents/site/dist/
/Users/example/Documents/site/.vercel/output/
```

```text
# explicit-only-patterns.txt
.env
.env.*
.env/
.env.*/
node_modules/
.venv/
venv/
myenv/
.git
.astro/
```

These **ten patterns are examples**; `init` creates only the four `.env` file and directory patterns. The `dist/` and `.vercel/output/` exclusions are absolute and limited to one project. For a global basename policy use `explicit-only-patterns.txt`. Here `.git` protects files named `.git`; directories with that name are encrypted by `private_directory_names`. Inspect the five local configuration files, or use `check`, `explain ABS_PATH`, and `preview --local`, to learn the actual selection.

### 3.4 Credentials and symlinks

macbackup cannot automatically recognize every secret in Desktop, Documents, repositories, or `.config`. Review selection before the first upload. The selector protects the standard rclone configuration and macbackup state locations, even through links. A custom rclone configuration location is not discovered automatically: add its absolute path to `private-paths.txt` if it must be backed up, then inspect its classification with `explain`.

Symlinks are preserved without following them. With rclone `--links`, they appear in the cloud as files ending in `.rclonelink`; their contents record the target path, not target contents. Selecting `.config/` therefore does not back up a repository reached only through a symlink. Include the real directory path separately when its contents are needed.

### 3.5 Set up rclone remotes

Configure a `plain`/`private` pair for each provider. The private setting must point to a `crypt` remote wrapping that provider's **entire private area**, including `current`, `history`, and `macos-icons`. Use the crypt remote to read and restore private files; the underlying folder shows encrypted objects. Keep the crypt password and any custom salt in a password manager accessible without this Mac.

For Google OAuth, follow the [rclone Drive guide](https://rclone.org/drive/) and test the remote with `rclone about REMOTE_NAME:`. The `drive.file` scope manages files authorized for that app; it does not grant access to every existing Drive file. A personal OAuth client left in Testing may have short-lived refresh tokens; inspect its publishing status and Google's rules before relying on unattended backups. A read-only mount does not change the remote's OAuth permissions. For Proton use the [rclone Proton Drive guide](https://rclone.org/protondrive/) and test copy and recovery separately. Credentials belong in rclone, not `settings.toml`.

The safe sequence is: configure and test remotes, fill the lists, run `check` and `preview --local`, enable the target in `settings.toml`, then run `check --remote --target google` and `preview --target google` (substitute your target). After reviewing the planned operations, run the backup; inspect `status`, use `verify`, and restore a nonsensitive sample file to a separate directory. A remote check reads inventories and capabilities; it does not prove every file can be restored. A preview does not reserve remote state; `run` checks again.

## 4. Remote layout

Each provider has a dedicated area:

```text
MacBackup/
  plain/
    current/
      Users/example/...
      etc/hosts
      Volumes/Archive/...
    history/
      RUN_ID/...
  private/
    [encrypted names and contents]
```

Through the crypt remote, the logical private layout is:

```text
current/Users/example/.ssh/...
history/RUN_ID/Users/example/.ssh/...
```

The crypt remote must cover the entire private area, including history. Never run the private backup directly against the underlying unencrypted remote. Each provider has its own crypt connection; both read local sources, without copying Google to Proton.

The path structure is mirrored, but empty directories without icons, ACLs, all extended attributes, and resource forks of ordinary files are not preserved. Restore does not reconstruct every macOS filesystem property. Export or consistently close a running application's database before copying it.

Keep everything needed to reconstruct crypt remotes outside the Mac, including passwords and any custom salt. Google or Proton account credentials alone are insufficient. Protect the local rclone configuration too: ordinary rclone password obscuring is not secure encryption of that file.

### 4.1 Custom Finder icons

A macOS file named `Icon\r` may store its image in a resource fork even if the ordinary file is empty. macbackup saves an `icon.json` snapshot of the file, resource fork, and folder FinderInfo. Other control-character names remain blocked. Icon snapshots follow the same inclusions, exclusions, and archiving rules as files; private ones pass through crypt. `check` does not include resource-fork bytes in its size estimate. An icon file or attribute over 64 MiB blocks that phase.

To restore an icon, download its `icon.json` from the appropriate `macos-icons/current` or `history/RUN_ID` area, then apply it to an **existing test folder**:

```sh
rclone copyto "gdrive:MacBackup/plain/macos-icons/current/Users/example/Documents/Photos/icon.json" \
  "$HOME/Downloads/icon.json"
macbackup restore-icon --file "$HOME/Downloads/icon.json" \
  --folder "$HOME/Downloads/Photos"
```

`restore-icon` works locally and does not use the source path inside the snapshot as its destination. `--folder` must exist and must not be a symlink. Use `--replace` when an icon already exists; `--json` returns structured output. Download a private snapshot through the crypt remote.

## 5. What a backup does

| Event | Effect |
|---|---|
| New selected and allowed file | Uploaded to its assigned area's `current` |
| New `.env` inherited only from a directory | Skipped with an explicit-only reason |
| Exact protected-file entry removed | Existing `current` copy archived in its area on the next run; history retained |
| File modified | Previous copy moved to history; new copy in `current` |
| Child file deleted inside an available selected directory | Previous copy moved to history |
| Path newly excluded or removed from lists | `current` copy archived in the same area; history retained |
| Path reclassified plain → private | Old plain copy in `plain/history`; new encrypted copy in `private/current` |
| Path reclassified private → plain | Old private copy in `private/history`; new readable copy in `plain/current` |
| Directly included source missing or unreadable | Affected operation blocked; never interpreted as an empty directory |
| Remote space exhausted | Error; no automatic history cleanup |

After a successful `run`, `current` reflects the current selection. Copies no longer selected are moved to the same area's `history`, never silently deleted. A failed or interrupted run can leave partial state; `status` distinguishes completed archives from planned ones. If both inclusion lists become empty, `run` may still archive existing current copies within `max_delete`; if there is no current copy either, the remote operation stops without work.

A directly listed source disappearing is ambiguous: perhaps an external disk is disconnected rather than intentionally deleted. It blocks backup. A child disappearing inside an available selected parent is an ordinary deletion to archive. Merely seeing a directory on an external path does not prove the intended volume is mounted; macbackup does not verify volume identity.

Macbackup does not automatically expire its history. Provider trash and native versions follow their own rules. Every attempt gets a unique history ID; a retry must not reuse a directory where it might overwrite a preserved version. A run is **not atomic** across files, areas, or providers. Some files may already have transferred or archived when it stops.

## 6. Commands

These are macbackup subcommands, not rclone commands. Restoring an entire tree at once is not available.

| Command | Main purpose |
|---|---|
| `init` | Create four local lists and `settings.toml` without active inclusions |
| `check` | Check local sources; `--remote --target` also reads remotes and inventories |
| `explain PATH` | Explain the local classification of one path |
| `layout [PATH]` | Summarize private subtrees within a plain directory; default to the current directory |
| `preview --local` / `preview --target` | Show local selection or plan remote archives without changes; `--simulate` also performs transfer checks |
| `run --target` | Transfer selected files, keep prior versions, and show progress |
| `mount --target` | Mount plain, private, or both read-only on macOS |
| `status` | Read the last run report; `--verify` reads the last verification report |
| `restore-icon` | Restore a Finder icon locally from a downloaded snapshot |
| `versions PATH` | List a file's copies or summarize copies under a directory |
| `restore PATH` | Download one file to an explicit destination; `--links` recreates a symlink |
| `verify --target` | Compare current local selection with cloud `current` without changing it |
| `forget` | Create and optionally apply a selective removal plan |

Global `--config-dir PATH` must precede the subcommand. It changes the list and `settings.toml` directory, potentially changing selection; state and rclone credentials retain their standard locations. Commands offering `--json` return UTF-8 JSON.

Long interactive scans, planning, version searches, and restores show an animated ASCII bar on stderr. Local scans in `check`, `preview`, `run`, `layout`, and `verify` show paths visited; the total is unknown until traversal ends, so they do not show `x/y`. Remote inventory phases show `Entries read` and, for `versions` and `forget`, matching copies. `check --remote`, remote `preview`, and `run` separate the local scan from each `current` inventory. Verification then shows completed file checks against the selected file count for each area and kind; `--size-only` first shows the entries in its remote inventory, then labels the local name-and-size pass `Comparing sizes` with `Checked x/y`. The final status line retains the last count even when a phase finishes between screen updates. A restore shows bytes received against the known file size, while removals and policy archives count completed items out of the known plan. Elapsed time and estimates are rounded to seconds and formatted compactly (`59s`, `2m30s`, `1h44m30s`), omitting zero-valued units except for `0s`; other bars have no percentage when total work is unknown. Ordinary keystrokes are discarded during these phases, while `Ctrl-C` remains available. `run` instead accepts `u` and `?` during transfer. Immediate commands such as `explain` and `status` do not show a bar. Supported terminals color results, warnings, errors, and selected labels. `NO_COLOR=1` or `PYTHON_COLORS=0` disables color; redirected output and JSON contain no ANSI codes. Local file paths and secondary notes are muted in color terminals; remote identifiers use a contrasting blue. In `versions`, `▸` also marks each remote group. Completion uses concise descriptions and colors only where supported, without running macbackup or rclone.

`--target google|proton|all` chooses providers; `--area plain|private|all` chooses areas where available. Quote paths containing spaces in the shell. Private commands use original readable paths, not encrypted remote names.

Exit code `0` means completion, `1` means a failed check or transport error, and `2` means invalid configuration or usage. `Ctrl-C` normally returns `130`; during `run`, an interrupted transfer is recorded as a partial result and returns `1`. Empty inclusion lists make local `check` return `0` with a warning; that does **not** mean a backup exists.

### 6.1 `check`: local and remote checks

```sh
macbackup check
macbackup check --json
macbackup check --remote --target google
```

Local `check` loads lists and policy, validates their syntax and precedence, traverses included sources, verifies directly requested paths exist and selected files are readable, and examines names and metadata without reading the contents of files to back up. It does read configuration files and, when enabled, `.gitignore`. It reports skipped special files, preserved symlinks whose targets are not traversed, explicitly allowed protected names in plain, and local conflicts between areas. Without `--remote`, it does not contact the cloud. Human-readable size is decimal (`kB`, `MB`, `GB`); JSON retains the exact byte count in `summary.selected_bytes`.

A warning that a symlink target was not traversed means only the link is saved through that path. Include its real target path independently if the target contents matter. A skipped socket, FIFO, or device is not a regular recoverable file; an application's active socket is one example. The summary counts plain, private, and skipped items separately.

`check --remote` first performs the same local scan. It then requires an enabled target and existing remotes, a `crypt` remote for private, and a hash-capable plain backend. It inventories `plain/current`, `private/current`, and both icon areas. It rejects invalid or duplicate paths within an area, determines which current copies no longer match policy, and detects cross-area `current` conflicts. The same path is a conflict if at least one side is a file; shared parent directories are allowed. An error displays up to five example paths. The default target is Google; `--target all` checks both enabled targets. Each remote `current` inventory has its own progress bar with a live `Entries read` count; it includes files and directories and has no known total until listing ends. Human-readable output ends with the same local selection totals as `check`; these are counts of selected Mac files, not cloud inventory totals. JSON includes them in `summary`.

Remote `check` reads only. It neither compares file contents nor proves recoverability, does not scan `history`, and does not apply `max_delete`. Use `preview --target google` for planned archives and limit checks; use `verify --target google` to compare current local data with cloud `current`. macOS may require access permission for Desktop or Documents. A denial is an error, not a silent exclusion.

### 6.2 `preview`, `explain`, and `layout`

```sh
macbackup preview --local
macbackup preview --local --json
macbackup preview --target google
macbackup preview --target google --simulate
macbackup explain "/Users/example/Desktop/project/.env" --json
macbackup layout "/Users/example/Desktop/project"
```

Local preview shows paths, classifications, exclusion reasons, and warnings. Exact plain inclusions of protected names are highlighted. An explicit-only rejection identifies its pattern in JSON and individual explanations. The local mode does not contact the cloud or estimate remaining upload bytes. If scanning fails, partial entries are not presented as a valid plan. A pruned directory is shown without visiting every descendant, so its skipped count is not a full subtree count.

Remote `preview --target google` reads the current cloud inventories and builds the archive plan without comparing file contents or simulating transfers. For each target, area, and kind (`files` or `macos-icons`), it reports selected files and both types of planned archive. Copies still classified in their original area but absent from the current local selection are listed individually as `Absent from local selection`; their original Mac paths also appear in the JSON array `results[].archive_deleted_paths`. This does not prove the file was physically deleted: it might no longer be reached by the local scan. Symlinks use their original path rather than the `.rclonelink` representation; Finder icons use the `Icon\r` path rather than `icon.json`. Paths containing a carriage return are escaped in the text output. The list is complete, even when it exceeds `max_delete`. Policy archives remain separate in `policy_archives`, with path, new classification, reason, and current rule when available. Exceeding `max_delete` is reported in the preview; `run` would stop before transfer for the same plan. This fast plan cannot tell which selected files would need uploading or detect errors that arise only during content comparison or transfer. Neither preview mode writes a run report or freezes source and remote state for a later run.

Add `--simulate` to retain the deeper, slower preview: after building the same plan, macbackup uses `rclone cryptcheck` to compare selected private files already in `private/current` and runs rclone dry-run sync where changes are needed. The private comparison bar shows completed file checks against its total. The dry-run bar shows `Processed x/y` for selected paths reported by rclone and elapsed time; this counts simulated decisions, not completed uploads or verified content. The count may pause while rclone lists the cloud or processes a large file. The plain dry run can also take time. This is not `macbackup verify`. Both preview modes are read-only; interrupting either with `Ctrl-C` does not modify the cloud. The active simulation phase is printed to stderr even without an interactive terminal. `--simulate` requires `--target`.

`explain ABS_PATH` classifies one path without scanning every source. Its explanation does not prove that the file has already been saved or encrypted. `layout [PATH]` scans the selected plain directory (or current directory) and summarizes roots, counts, and sizes of private subtrees within it. `--json` adds logical paths in `private/current`. It does not contact the cloud, list history or old plain copies, or read file contents. An invalid or failed scan does not yield a valid partial layout.

### 6.3 `run`: perform a backup

```sh
macbackup run --target all
macbackup run --target google
macbackup run --target proton
```

`run` rechecks configuration, takes a local lock against concurrent operations, and processes each assigned area. A crypt failure cannot send private data through plain as a fallback. On an interactive terminal, rclone statistics update a dedicated screen every five seconds. Separate ASCII bars show byte and file progress; overall speed stands out. Active file paths and speeds occupy separate lines, and elapsed time and ETA are rounded to seconds. Press `u` to alternate binary (KiB/MiB/GiB) and decimal (kB/MB/GB) units and speeds; press `?` to toggle the current phase's legend. These keys change presentation only. `Ctrl-C` interrupts transfer and restores the terminal. Without an interactive terminal, progress is printed periodically as text and keys are unavailable.

Several files and folders can transfer concurrently, so there is not always one “current directory.” Active folders are grouped by two levels below home by default; choose one to five with `--progress-depth N`, for example `--progress-depth 3`. Active file paths are not truncated. Progress belongs to the current plain, icon, or private phase, not the whole backup. After configuration and targets load, `status` is saved at the start of a run, after planning, and after each phase; `Ctrl-C` during transfer records an interrupted phase. A subsequent run compares already completed files. A partially transferred file is sent again from its beginning, never resumed from an arbitrary byte.

`run --json` performs the same real backup and changes only the final stdout summary; progress stays on stderr. Text and JSON distinguish selected, transferred, and checked counts. The readable summary shows up to 20 planned paths absent from the local selection per phase, plus the number confirmed archived or a warning that completion could not be verified; `status` and `run --json` keep the full path lists. The saved report is updated at phase boundaries, not for every transferred file. An interrupted run is marked incomplete even if some files reached the cloud.

`max_delete` (25 after `init`) limits moves from `current` to `history` per target and area, counting both local deletions and policy changes, including icons. A remote preview signals an exceeded limit; `run` stops before transfers. Ordinary private comparison uses `rclone cryptcheck` to detect changes even when size and modification time match. An incomplete crypt check blocks that phase. An unchanged private file should not create a new history version.

Results are separate per Google/Proton and plain/private. One target may succeed while another fails, so read the per-area report and exit code. Success requires every requested operation to complete. A run is not a simultaneous snapshot of both services: local files may change between reads.

### 6.4 `mount`: browse copies read-only

```sh
macbackup mount --target google                 # same as --area all
macbackup mount --target google --area all      # merged current, separate histories
macbackup mount --target google --area plain    # google-plain volume
macbackup mount --target google --area private  # google-private volume
```

`--target` chooses the service; `--area` chooses visible areas. There is no `--all` flag: use `--area all`, the default. On the Desktop it creates one `google` volume. Its `current/` merges plain and private files into their original path tree, so an encrypted `.git` appears alongside the project's plain files. `history/plain/` and `history/private/` remain separate because earlier versions may exist in both areas. Finder icon snapshots appear under `icons/plain/` and `icons/private/`. This is a read-only view; remote paths, classification, and encryption do not change. rclone `union` and `combine` remotes are created only in the mount process. `--area plain` or `private` instead creates `google-plain` or `google-private`. `--mountpoint ABS_PATH` changes the **base folder**, retaining these volume names beneath it. `--target proton` works when configured and enabled; `--target all` requires both services enabled and creates a volume for each.

Before mounting the merged view, macbackup inventories both current areas. Shared directories are fine; a file at the same path in both areas, or a file opposing a directory, blocks the mount and reports the conflict. Neither copy is silently hidden. An indeterminate ASCII bar shows elapsed time during inventories and startup; merged-view inventories also display received metadata MiB and a live `Entries read` count. Ordinary input is discarded, while `Ctrl-C` interrupts. The total duration is unknown, and large backups can take time to inventory. Mount individual areas when a merged inventory is inconvenient or blocked.

On macOS the command uses `rclone nfsmount --read-only` without macFUSE. Keep its terminal open. While mounted, ordinary keystrokes are discarded; `Ctrl-C` unmounts. Finder `⌘E` also ejects it. Both normal exit paths confirm `Volume unmounted: <path>`, restore terminal input, and remove empty mountpoints created by this invocation. An abnormal rclone exit remains an error; a preexisting empty folder is retained. Default Desktop mountpoints are automatically excluded from `run`, even when Desktop is selected. Every mountpoint must be empty and cannot cross a symlink; an alternate mountpoint cannot overlap a backup source. The mount does not run a backup or apply macbackup's selection rules to files dragged elsewhere. Writes through it are blocked by rclone, although some NFS clients may not show a clear error. `.rclonelink` and icon JSON remain their stored representations; use restore commands to recreate the originals.

The Google token keeps its existing OAuth permissions. Read-only applies to this mount, not to the underlying account. See [rclone nfsmount](https://rclone.org/commands/rclone_nfsmount/), [combine](https://rclone.org/combine/), and [union](https://rclone.org/union/).

### 6.5 `status`: inspect the saved result

```sh
macbackup status
macbackup status --verify
```

Output is always JSON; `--json` is accepted for compatibility. By default this reads the latest run; `--verify` reads the separate latest verification report. The run report is stored at `~/.local/state/macbackup/last-run.json` with owner-only permissions and updated after each phase. `complete: false` and `active_phase` mark an unfinished attempt; after an abrupt process exit they may describe the last recorded phase rather than a process still running. `ok: true` is possible only after a completed run. The report concerns the requested targets and areas. `selected` is the planned item count; `transferred_files` and `transferred_bytes` come from rclone's completed transfer statistics; `checked_files` counts rclone checks; `listed_items` counts files and directories enumerated, **not** everything already in the cloud.

**Planned and completed archives.** `archive_deleted` counts copies planned for archiving because they were absent from the local selection; the field name is retained for compatibility and does not prove physical deletion. Both remote preview and run status list their original Mac paths in `archive_deleted_paths`. `run --json` and run status also have `archive_deleted_completed_paths`: after a successful sync it contains all planned paths; after an interrupted or failed sync, macbackup reads that run's history and lists only planned copies found there. This read-only `Checking history` phase appears after an interrupted or failed sync with planned absence archives and can take time. If the cloud cannot be read, the value is `null` (unknown), not an empty list. While a phase is running, or if the process stops before updating status, the value may also be `null`. An empty list means either no absence archives were planned, or a completed history read found none of the planned copies. History can also contain previous versions of updated files, which are excluded from this list. For example, if two paths were planned and only one reached history before an interruption, `archive_deleted_paths` contains both and `archive_deleted_completed_paths` contains only the one found in history. Both arrays use original Mac paths, including for symlinks and Finder icons.

`archive_policy` counts copies planned for archiving after policy changes. `policy_archives` identifies each planned move, original area, new classification, reason, and current rule. `policy_archived` lists completed moves and their history paths; in a partial run these arrays may differ in length.

`renamed_files`, `server_side_moves`, and `server_side_move_bytes` reflect rclone sync operations. With `--backup-dir` they include prior copies moved into history but not later policy moves via `moveto`; do not add them to files uploaded from the Mac. `counts_complete: true` means final stats arrived after a successful phase. After `Ctrl-C`, a periodic report may yield counts with `counts_complete: false`; it may undercount files finished just before interruption and count bytes from an incomplete file. Before any report, fields are `null`, not zero. JSON is readable UTF-8, without escaped apostrophe sequences. Existing saved run reports are not backfilled with `archive_deleted_completed_paths`. The saved result does not provide a separate latest-success view per target; it does not prove the cloud is reachable now, every history item is intact, or recovery was tested.

### 6.6 `versions`: find file or directory copies

```sh
macbackup versions "/Users/example/Documents/thesis.docx" --target google
macbackup versions "/Users/example/.ssh/config" --target google --area private
macbackup versions ~/Documents/project --target google
macbackup versions ~/Documents/project --target google --files
```

`versions` reads `current` and history in the requested areas even if a path is no longer selected or the local file is gone. `--target` is required; `--area` defaults to `all` because this is read-only. A file needs its exact original path. Output identifies service, area, size, available modification time, and `current` or the history directory's run ID. Modification time is not archive time.

For an existing local directory, its path suffices (`~` is expanded by the shell). If it no longer exists, append `/` to its absolute path to request recursive directory mode. The ordinary result groups current and sparse history by service and area, with counts and bytes. `--files` adds original paths, sizes, and `files`/`macos-icons` type **only for history groups**; current keeps counts and bytes without listing every current file. `--json` includes groups and details of every item, including current remote paths. `--files` is only valid for a directory. Unless area is narrowed, plain project files and automatically private `.git` items appear in their respective groups.

Each `history/RUN_ID` contains **only items moved in that run**, not a complete directory snapshot. A local edit creates history only when a prior uploaded copy is replaced by a later run. `versions` does not restore a whole directory; `restore` handles one file at a time. A target may be disabled in settings if its remotes still exist. The search uses targeted current and per-history paths rather than a full-tree hash scan, but many history runs can still require many provider requests. It does not compute hashes or original IDs; `forget` performs its own inventory and checks before removal.

### 6.7 `restore`: recover one file

Choose a version found by `versions` and an explicit separate local destination:

```sh
macbackup restore "/Users/example/Documents/thesis.docx" \
  --target google --area plain --version current \
  --to "/Users/example/Restore/thesis-recovered.docx"
```

For a symlink, add `--links` and use a test path distinct from the original:

```sh
macbackup restore "/Users/example/.zprofile" \
  --target google --area plain --version current \
  --to "/Users/example/Downloads/macbackup-restore/.zprofile" --links
```

The destination directory must already exist. A recreated symlink points to its recorded original target; restore that target separately. An absolute link may be broken on a Mac with a different home path. Use the history run ID from `versions` for an older `--version`. Exactly one service and area are required. The destination cannot cross a symlink. The original path is rejected as a destination; an existing file is not replaced without `--replace`, which still rejects symlinks and nonregular destinations.

Download first goes to a mode-600 temporary file. macbackup checks its size and any usable backend hash, then rereads remote inventory before exposing the restored file. When no hash is available, it says so: size and metadata alone do not prove content integrity. Without `--links`, a link version is rejected instead of producing an ordinary `.rclonelink` file. With it, macbackup checks the small link-target file and recreates a symlink to the recorded target, even if absolute or containing `..`; it never creates the target's contents. `--links` is rejected for ordinary files.

Restore does not rebuild whole directories, directory permissions, ACLs, macOS attributes, or original timestamps. A recovered `.ssh` key gets mode 600, but prepare its parent directory separately, normally mode 700. Finder icons use `restore-icon`. A restored file placed inside an active source may be uploaded on the next run. History is sparse, so there is no arbitrary-date full-tree restore; that would need complete inventories and tested reconstruction or a snapshot-based tool.

### 6.8 `verify`: compare local selection with `current`

```sh
macbackup verify --target google
macbackup verify --target google --size-only
macbackup verify --target google --area private --download
```

`verify` scans selected local sources and compares allowed files against cloud `current` without modifying either. Ordinary mode uses `rclone check` for plain and `rclone cryptcheck` for private, requiring a complete rclone report. `--download` uses `rclone check --download` to read remote contents and may consume substantial time and bandwidth. Google plain comparison uses common hashes where available; private uses cryptcheck. Current Finder icon snapshots generated from selected sources are included.

In an interactive terminal, each phase shows `Checked N/total`. The total includes selected files nested under included directories. `N` counts completed results, including matches, differences, missing files, and errors; it is not a count of matching files. The counter can remain at zero while rclone prepares a remote listing or checks one large file, and results may appear in batches when rclone writes its report. The final result is authoritative; interrupted verification does not certify the remaining files. Use `--area private` to verify only that area.

`--size-only` inventories current once per area and compares paths and sizes, including for private. It does not compare content and cannot prove byte equality. It can still take time to scan local files and read the provider inventory. It cannot be combined with `--download`. Full private verification rereads and encrypts local files to compare hashes and may take hours for many thousands of files. `Ctrl-C` exits 130 without a traceback. After configuration and targets load, the latest verification is saved at `~/.local/state/macbackup/last-verify.json` with owner-only permissions and can be read with `macbackup status --verify`. It is updated after each phase. On interruption, `complete: false` and `active_phase` identify the incomplete phase; `results` contains only finished phases. An unfinished phase is not certified. The next started verification replaces the report, so save a copy elsewhere if you need to retain it.

The result separates matching, different, missing, and read-error counts per service, area, and kind. Normal text output shows up to 20 paths per category and phase; `status --verify` and `verify --json` contain the full lists. Symlink and Finder icon paths use their original Mac names in text output. A difference from the current local file does **not** by itself prove backup corruption: the local file may have changed since upload. `verify` does not check history, copies retained after exclusion, all macOS metadata, or native provider revisions. Without a manifest of content recorded at backup time, comparing an old copy with today's local original cannot certify that old copy. Disabled targets can be verified if their remotes still exist.

### 6.9 `forget`: remove retained copies

`forget` has two phases: a cloud read creates a plan, then a second invocation rechecks and applies it. Area, target, and mode are explicit. Give a file's exact original path, or append `/` for a directory even if it no longer exists locally:

```sh
macbackup forget "/Users/example/Desktop/old-project/" \
  --area plain --target google --mode trash
```

For a file moved from plain to private, a Google plan with `--mode permanent` can target old readable copies, after reviewing the exact path and printed plan:

```sh
macbackup forget "/Users/example/Desktop/project/secret.txt" \
  --area plain --target google --mode permanent
```

Neither command applies removal yet. `--area private` searches encrypted copies; `--area all` searches both. The plan lists every matching file in `current` and all history runs, with area, service, location, count, and known bytes. Directory plans also include matching `macos-icons` snapshots and existing directory roots for later cleanup. Path boundaries are respected: `old-project/` does not match `old-project-other/`. Current selection rules do not constrain the search, so copies uploaded before a new exclusion or privacy classification can still be found. Disabled targets may be searched if remotes remain configured. More than 10,000 files requires narrower, separate plans.

No plan is made if neither files nor directories match. An empty retained directory can yield a zero-file cleanup plan. Otherwise macbackup writes a random single-use, one-hour plan under `~/.local/state/macbackup/forget-plans/` with mode 600. It prints the exact apply command:

```sh
macbackup forget --plan F0123456789ab --apply
```

Before applying, it rereads inventories and compares the entire match set, remote paths, sizes, modification times, IDs, and backend hashes. A changed or newly appeared copy blocks the entire plan. Some backends expose no content hash, so same-size, same-time edits may not be detectable; do not apply a plan while another client edits the backup. Application removes files one by one and reports progress. It then rereads inventory and, for directory requests, cleans empty directories beneath the exact planned roots in current and matching history runs, without climbing above the requested path.

An error or `Ctrl-C` during application may leave a partial result recorded under that plan ID. Create a new plan for remaining items, even if only empty folders remain. `forget` does not alter local sources or lists. If a path is still included, the next `run` may upload it again; change its selection first. `--area plain` can remove old readable copies after private reclassification. `--target all` requires both services to be configured and does not assume a disabled target contains nothing.

### 6.10 Trash, permanent removal, and provider revisions

`--mode trash` removes matched copies from backup folders into provider trash; it is not permanent and may not free space. `--mode permanent` is accepted only with `--target google` and a verified Google Drive plain remote. It cannot be combined with `--target all`; unsupported permanent removal is rejected before deletion. For selected live Google files, rclone uses `--drive-use-trash=false`.

Native revisions and items already in trash are separate from the current/history folder inventory. Removing a path does not discover duplicates under other names or folders. macbackup rejects `permanent` for Proton because its rclone backend does not expose equivalent selective permanent deletion. Selective removal of items already in Proton trash remains manual; macbackup does not offer a verified map of encrypted names there. Results distinguish removal from active folders and requested mode. Neither mode certifies the absence of earlier trash copies, Drive revisions, or renamed duplicates.

### 6.11 Zsh completion

The dotfiles contain `home/.zsh/completions/_macbackup` (English), `_macbackup_it` (Italian), and `home/.zsh/integrations/macbackup.zsh`. Completion suggests subcommands, flags, targets, areas, and paths. In an existing shell after updating the files or changing `MACBACKUP_LANG`, open a new terminal or reload the integration:

```sh
source "$HOME/.zsh/integrations/macbackup.zsh"
```

Completion does not execute macbackup or rclone or contact the cloud. Descriptions are compact and colored only on supported terminals. When adding parser flags, update both completion files and their tests.

## 7. When a check or run fails

An error does not mean deletion succeeded. Read the affected phase's message, then `macbackup status` if it was a run. The report distinguishes completed transfers and archives from planned operations or the last incomplete periodic count. Fix the cause, rerun `check` and `preview --target`, then start a new `run`. Completed files are compared again; an interrupted file restarts from byte zero.

| Signal | What to inspect |
|---|---|
| Directly listed source missing or unreadable | Check path, permissions, and external disks. Change the list only if removal was intentional; it must not be treated as a deletion. |
| `max_delete` exceeded | Inspect `preview --target`, then incorrect exclusions or paths. Increase the limit only after reviewing every planned archive. |
| Conflict between `plain/current` and `private/current`, or remote duplicates | Run `check --remote` and inspect reported paths. Resolve the conflict before a merged mount or new run. |
| OAuth or credential error | Test and reconnect the rclone remote if necessary, then repeat `check --remote`. Old status success does not prove a token is still valid. |
| `verify` reports differences | Check whether local files changed after backup. `--size-only` compares paths and sizes; ordinary verification reads more data. |
| `Ctrl-C` during `run` or `verify` | Result is partial. `status` retains the run report; `status --verify` shows completed verification phases. Neither certifies the interrupted phase. |

For a practical restore test, use `versions` to find a nonsensitive file, `restore --to` into an existing test directory, and open it. Repeat for private while keeping crypt keys outside the Mac. Such a test is stronger than checking filenames, but proves only the sampled items.

## 8. Operational security and recoverability

Macbackup checks sources before archiving missing copies and uses a local lock against concurrent remote operations. Read errors are not bypassed with `--ignore-errors`; a crypt problem never falls back to plain. Standard state is excluded from selection to avoid uploading `forget` plans or logs and causing recursion. These safeguards apply only to macbackup's configured sources: manually dragging files into a writable provider location bypasses them.

Keep protected copies of crypt configuration and keys off the Mac. Protect local state and restore directories. Logs omit file contents, but paths, rules, and reports can reveal information; review them before publication. Cloud files are copies, not a live two-way sync. Phone edits or deletions do not modify the Mac and may be overwritten or recreated by the next run. The backup is not immutable: access to the same account can also compromise remote copies.

## 9. Official references

- [Rclone: filtering and files-from](https://rclone.org/filtering/)
- [Rclone: sync](https://rclone.org/commands/rclone_sync/)
- [Rclone: backup-dir](https://rclone.org/docs/#backup-dir-string)
- [Rclone: crypt and configuration protection](https://rclone.org/crypt/)
- [Rclone: Google Drive, revisions, and trash](https://rclone.org/drive/)
- [Rclone: Proton Drive and limitations](https://rclone.org/protondrive/)
- [Rclone: delete and filtering](https://rclone.org/commands/rclone_delete/)
- [Rclone: purge ignores filters](https://rclone.org/commands/rclone_purge/)
- [Rclone: symlinks](https://rclone.org/local/#symlinks-junction-points)
- [Rclone: cryptcheck](https://rclone.org/commands/rclone_cryptcheck/)
- [Google: native revision management](https://developers.google.com/workspace/drive/api/guides/manage-revisions)
- [Proton: selectively removing trash in the app](https://proton.me/support/proton-drive-mobile-manage-files-folders)
- [Proton: deleting and restoring synced files](https://proton.me/support/proton-drive-delete-restore-synced-files)
- [Zsh: completion system, fpath, compinit, and compdef](https://zsh.sourceforge.io/Doc/Release/Completion-System.html)
