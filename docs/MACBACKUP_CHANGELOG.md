# macbackup — registro tecnico e dei collaudi

Questo registro conserva decisioni, modifiche e prove utili a chi mantiene `macbackup`, inclusi gli agenti. Riporta i principali traguardi, non ogni versione intermedia; le voci tecniche più vecchie mantengono la lingua originale inglese. Il [manuale](macbackup.md) descrive l'uso corrente. Per verificare il comportamento effettivo prevalgono lo script, i test e la configurazione locale: numeri e percorsi riportati qui sono **fotografie storiche**, non valori da copiare o stato attuale del backup.

Quando si cambia una regola, aggiornare prima il manuale se cambia il contratto per l'utente; aggiungere poi qui il motivo, il rischio, i test eseguiti e le limitazioni residue. Non pubblicare segreti, token o inventari personali.

---

## 2026-11-06 — separazione del manuale dal registro

- Il manuale è stato ricostruito attorno a configurazione, precedenze, struttura remota, comandi e recupero. Sono stati rimossi i percorsi della home personale, i conteggi temporanei delle anteprime, lo stato di un singolo account e i resoconti cronologici dei collaudi.
- L'esempio TOML usa `max_delete = 100` come **esempio configurabile** e chiarisce che `init` genera `25`; evita di presentare il file di un Mac come valore universale. L'esempio explicit-only contiene otto nomi, inclusi `.git` e `.astro`; due esclusioni di output generato mostrano la differenza fra percorso assoluto e regola globale per nome.
- Questo file diventa l'archivio per chi modifica il programma. Le affermazioni sul comportamento corrente vanno verificate nello script e nei test prima di riutilizzare una nota storica.
- Revisione incrociata con il parser e le funzioni di trasporto: il manuale copre ogni sottocomando e flag, distingue il controllo locale da quello remoto, descrive l'ordine corretto di abilitazione dei remotes, il recupero e la gestione degli errori. Nessun remote reale è stato contattato per questa revisione documentale.
- Verifica locale della suite, senza modifiche allo script: `python3 -B -m unittest discover -s tests/macbackup -t tests -p 'test_*.py'` (168 test riusciti). La suite usa dati sintetici; non certifica lo stato corrente degli account cloud.

---

## Registro dei collaudi e delle decisioni iniziali (ottobre–novembre 2026)

- **Selezione locale:** la prima scansione ampia comprendeva molte directory di dipendenze ricreabili. La scelta fu introdurre pattern per nome in `explicit-only-patterns.txt` invece di mantenere decine di esclusioni assolute. La policy è stata poi estesa a `.git` e `.astro`; l'esempio corrente nel manuale contiene otto pattern. Una directory `.git` sotto una sorgente inclusa è cifrata dalla policy `private_directory_names` anche quando il suo nome è explicit-only, salvo inclusione esatta in plain non coperta da private. Le esclusioni `dist/` e `.vercel/output/` per un singolo progetto vanno espresse come percorsi assoluti, non come esempi di regole globali.
- **Icone Finder:** i file `Icon\r` inizialmente producevano errori di selezione. La versione 0.3 ha aggiunto snapshot dei resource fork e dei FinderInfo; un test AppKit ha confrontato l'immagine renderizzata prima e dopo il recupero. Questo non prova la resa di ogni icona in Finder.
- **Google OAuth:** il client personale è passato da Testing a Production e il remote è stato riconnesso. Con `drive.file` sono state provate creazione, lettura, spostamento nel cestino e rimozione di cartelle di prova. Durante una pulizia di alberi profondi si sono verificati rifiuti `403 appNotAuthorizedToChild`; i controlli finali hanno mostrato i namespace di prova assenti, ma la causa dei rifiuti intermedi non è stata isolata. Non fu richiesto lo scope completo `drive`.
- **Prove remote isolate:** file sintetici plain e crypt hanno coperto copia, modifica a parità di dimensione e orario, storico, `forget`, `restore`, `verify` ordinario e con download, e recupero delle icone. I namespace di prova autorizzati furono rimossi e verificati assenti dall'area attiva. Queste prove non certificano la copia completa dei dati personali né le revisioni native o gli elementi già nel cestino.
- **Prima selezione reale:** le anteprime locali e remote riportavano conteggi molto diversi dopo ogni revisione della policy; erano fotografie del momento. Una run iniziale fu interrotta intenzionalmente, poi il progetto ha aggiunto il resoconto parziale dei trasferimenti. I conteggi storici non sono parametri del programma e non devono essere ripetuti nel manuale.
- **Montaggio:** la vista `--area all` è stata collaudata con remotes locali e, in sola lettura, su Google. Unisce `current` e separa `history/plain` da `history/private`; rifiuta collisioni tra file o tra file e directory. Sono state provate interruzione con `Ctrl-C` ed espulsione dal Finder. Queste prove non leggono il contenuto di tutti i file.
- **Limiti ancora da verificare in un'installazione nuova:** ripristino da un Mac diverso con chiavi recuperate separatamente, comportamento completo del provider Proton, database applicativi aperti e contenuto di ogni copia corrente e storica. Consultare il manuale per i comandi disponibili; non dedurre da questo registro lo stato operativo attuale di un account.

---

## Note architetturali per le modifiche future

Rclone gestisce l'accesso ai provider, i trasferimenti, la cifratura `crypt` e lo spostamento delle copie sostituite o cancellate con `sync --backup-dir`. Macbackup interpreta i quattro elenchi, classifica i file, blocca le operazioni concorrenti e costruisce i piani di trasferimento, recupero e rimozione selettiva. Il controllo dell'identità di un volume esterno montato non è implementato.

`explicit-only` non è una funzionalità nativa di rclone. Il selettore Python applica le precedenze ai file locali e alle copie in `current`; il trasporto passa a rclone un elenco esatto separato da NUL con `--files-from0`. Non aggiungere filtri di esclusione rclone a quel comando: con `files-from`, rclone ignora gli altri filtri. L'elenco comprende i file ammessi e le vecchie copie ancora gestite da archiviare per cancellazione locale. Le copie escluse per policy o riclassificate nell'altra area vengono spostate separatamente nello storico dell'area originaria. Un file nuovo apparso dopo la generazione dell'elenco aspetta la run successiva. Non passare a rclone inclusioni ricorsive che potrebbero aggirare la protezione dei singoli nomi.

Chi modifica il programma può eseguire la suite locale con `python3 -B -m unittest discover -s tests/macbackup -t tests -p 'test_*.py'`. I test sintetici non sostituiscono un controllo dell'account remoto, una prova di recupero e un'ispezione dei permessi effettivi.

---

## [0.12.7] — 2026-11-06 (commit `8b11f68`)

- `check --remote` confronta `plain/current` e `private/current`; un percorso condiviso che è un file in almeno un'area è un conflitto, mentre directory antenate comuni sono ammesse.
- `verify --size-only` confronta percorso e dimensione tramite un inventario remoto per area. È una verifica più veloce ma non controlla i contenuti. La verifica ordinaria privata resta `cryptcheck`; `Ctrl-C` termina senza traceback.
- La UI di `run` distingue tasti, unità, legenda, percorsi attivi e statistiche. Gli identificatori e le note di altri comandi sono attenuati soltanto nei terminali a colori; il JSON resta invariato.
- Il completamento Zsh propone `--size-only`. Test sintetici coprono collisioni, confronto rapido, symlink e colori. La suite del commit comprendeva 168 test riusciti.
- Limite della verifica: il controllo rapido legge comunque l'inventario del provider; la durata sul backup completo dipende dal servizio. `verify` non controlla `history`.

## Lavoro preparatorio 0.12.6 — 2026-11-05 (confluito nel commit `8b11f68` e nella versione 0.12.7)

### Added
- **Interactive TTY Activity Indicator (`operation_activity`):**
  - Long-running synchronous phases (`check` local/remote, `layout`, `preview`, `versions`, `restore`, `verify`, `forget` plan/verify/apply) now display an animated indeterminate ASCII progress bar (`MountPulse`) on `stderr` when attached to a TTY, while suppressing and discarding stray keyboard input (`discard_mount_input`) and keeping `Ctrl-C` (`SIGINT`) active.
- **Colorized Terminal UI (`ui`, `issue_line`, `styled_progress_lines`):**
  - Added semantic ANSI styling (`info`, `success`, `warning`, `error`, `private`, `muted`) for human-readable output and the `run` live dashboard (`VELOCITÀ` in green, section headers in cyan).
  - File paths in warnings/errors (`issue_line`) and `preview --local` listings are visually muted (`\x1b[2m`) so severity labels and reasons stand out.
  - Strict compliance with `NO_COLOR=1`, `PYTHON_COLORS=0`, and non-TTY redirection; `--json` output on `stdout` remains pure unstyled JSON.
- **Cross-Area Conflict Detection in `check --remote`:**
  - `remote_current_objects` now records both files and directories (`IsDir: bool`) from `plain/current` and `private/current`.
  - `current_conflict_paths` blocks `check --remote` if any path exists in both `plain/current` and `private/current` where at least one side is a file (shared parent directories are permitted), surfacing up to 5 example conflicting paths.
- **Compact Zsh Global Options & Menu Selection:**
  - `home/.zsh/integrations/macbackup.zsh` loads `zsh/complist` and sets `menu select`, `last-prompt true`, and `list-colors` for `macbackup`.
  - `home/.zsh/completions/_macbackup` groups global options (`--config-dir`, `--help`, `--version`, `-h`) into a single compact `_describe` group when completing `-` at `CURRENT == 2`, and uses concise descriptions across all subcommands.
- **UI Test Suite (`tests/macbackup/test_macbackup_ui.py`):**
  - Added PTY and stream tests verifying `operation_activity` bar rendering, input discarding, terminal state restoration, `NO_COLOR` handling, dashboard highlighting, and `issue_line` formatting.

### Changed
- `progress_quantity()` now uses `"B"` instead of `"byte"` for sub-kilobyte quantities in both binary and decimal modes.

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
