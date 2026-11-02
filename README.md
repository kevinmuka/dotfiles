# Dotfiles

Repository personale per gestire configurazioni, script e tema condiviso tra shell, terminale, editor e tool macOS.

L'obiettivo non e' symlinkare l'intera home directory, ma avere un layout prevedibile:

- tutto cio' che sta in `home/` replica il path relativo a `$HOME`
- lo script `dot.sh` applica i symlink in modo conservativo
- `~/.config` resta una directory reale, mentre vengono linkati solo i suoi figli
- Neovim vive come submodule separato
- il tema condiviso parte da `~/.config/theme` ed e' consumato da Zsh, WezTerm, Neovim e Gemini CLI

## Bootstrap E Struttura

La root del repo e' `~/.dotfiles`. Il layout principale e':

```text
~/.dotfiles
├── home
│   ├── .zshrc
│   ├── .zshenv
│   ├── .zprofile
│   ├── .zsh
│   │   ├── functions.zsh
│   │   ├── integrations
│   │   ├── profiles
│   │   └── theme
│   ├── .config
│   │   ├── karabiner
│   │   ├── nvim
│   │   ├── scripts
│   │   ├── theme
│   │   └── wezterm
│   ├── .ideavimrc
│   ├── .tmux.conf
│   ├── .p10k.zsh
│   └── .p10k-theme.zsh
├── scripts
│   └── dot.sh
├── docs
│   ├── DEPENDENCIES.md
│   └── MODULES.md
├── .gitmodules
└── README.md
```

Regola fondamentale:

- `home/.zshrc` diventa `~/.zshrc`
- `home/.zsh/` diventa `~/.zsh/`
- `home/.config/wezterm` diventa `~/.config/wezterm`
- `home/.config/nvim` diventa `~/.config/nvim`

## Come Funziona `dot.sh`

Lo script principale e' [`scripts/dot.sh`](./scripts/dot.sh). Espone due comandi:

- `dot.sh plan`: mostra cosa verrebbe fatto, senza modificare nulla
- `dot.sh apply`: applica solo operazioni sicure
- `dot.sh conflicts`: mostra solo i conflitti
- `dot.sh add <path>` / `dot.sh adopt <path>`: sposta un file o una directory esistente dentro `home/` e crea il symlink
- `dot.sh replace <path>`: sostituisce una directory esistente con il symlink gestito, facendo prima backup

Il comportamento e' intenzionalmente conservativo:

- se il target esiste gia' ed e' un file o directory reale, non viene rimosso
- se il target e' un symlink che punta altrove, non viene sovrascritto
- se il symlink e' gia' corretto, viene lasciato invariato
- se `~/.config` e' un symlink, lo script si ferma
- se una directory reale esiste gia', viene segnalata come conflitto

La fusione dentro directory gia' esistenti e' disponibile solo quando richiesta esplicitamente:

```sh
~/.dotfiles/scripts/dot.sh plan --merge-existing-dirs
~/.dotfiles/scripts/dot.sh apply --merge-existing-dirs
```

Anche in questa modalita' lo script non cancella e non sovrascrive: entra nelle directory esistenti e crea solo symlink mancanti.

`replace` e' volutamente piu' stretto: funziona solo se nel repo esiste gia' la directory corrispondente sotto `home/`. Per esempio:

```sh
~/.dotfiles/scripts/dot.sh replace ~/.config/wezterm
```

Questo comando:

- rifiuta sempre `~/.config`
- rifiuta path che non esistono in `~/.dotfiles/home`
- rifiuta path che nel repo non sono directory
- sposta il target esistente in `~/.dotfiles/backups/<timestamp>/...`
- crea il symlink verso la directory gestita dal repo

La parte speciale e' `~/.config`: lo script non crea mai un symlink unico `~/.config -> ~/.dotfiles/home/.config`. Crea invece symlink separati:

```text
~/.config/wezterm   -> ~/.dotfiles/home/.config/wezterm
~/.config/theme     -> ~/.dotfiles/home/.config/theme
~/.config/karabiner -> ~/.dotfiles/home/.config/karabiner
~/.config/nvim      -> ~/.dotfiles/home/.config/nvim
```

Questo evita di rompere configurazioni non gestite dal repo.

## Installazione Su Una Nuova Macchina

Percorso minimo:

1. clona il repo in `~/.dotfiles`
2. inizializza i submodule
3. rendi eseguibile lo script
4. applica i symlink
5. installa le dipendenze delle sezioni che vuoi usare

```sh
git clone <URL_REPO_DOTFILES> ~/.dotfiles
cd ~/.dotfiles
git submodule update --init --recursive
chmod +x scripts/dot.sh
./scripts/dot.sh plan
./scripts/dot.sh apply
```

Se `~/.config` e' un symlink, va sistemato prima:

```sh
mv ~/.config ~/.config.backup
mkdir -p ~/.config
~/.dotfiles/scripts/dot.sh apply
```

Sposta o rimuovi `~/.config` solo dopo aver verificato dove punta e cosa contiene.

## Uso Quotidiano

### Applicare I Symlink

```sh
~/.dotfiles/scripts/dot.sh plan
~/.dotfiles/scripts/dot.sh apply
```

Per vedere solo i problemi:

```sh
~/.dotfiles/scripts/dot.sh conflicts
```

Per consentire allo script di entrare nelle directory reali gia' presenti e linkare solo i figli mancanti:

```sh
~/.dotfiles/scripts/dot.sh plan --merge-existing-dirs
~/.dotfiles/scripts/dot.sh apply --merge-existing-dirs
```

Per sostituire intenzionalmente una directory gia' presente con il symlink gestito dai dotfiles:

```sh
~/.dotfiles/scripts/dot.sh replace ~/.config/wezterm
```

Il target originale viene spostato in `~/.dotfiles/backups/<timestamp>/...`.

### Adottare Un File O Una Directory

```sh
~/.dotfiles/scripts/dot.sh add ~/.zshrc
~/.dotfiles/scripts/dot.sh add ~/.zsh
~/.dotfiles/scripts/dot.sh add ~/.config/wezterm
```

Lo script rifiuta esplicitamente:

```sh
~/.dotfiles/scripts/dot.sh add ~/.config
```

Per `~/.config` bisogna adottare i figli singolarmente.

## Moduli Principali

### Shell Zsh

La shell parte da:

- [`home/.zshenv`](./home/.zshenv): editor di default
- [`home/.zprofile`](./home/.zprofile): Homebrew, TeX Live, script locali e PATH
- [`home/.zshrc`](./home/.zshrc): tema, integrazioni, funzioni, profilo Oh My Zsh e completions

Il flusso di caricamento e':

```text
.zshrc
├── .zsh/theme.zsh
│   ├── .config/theme/colors.zsh
│   └── .zsh/theme/*.zsh
├── .zsh/integrations/*.zsh
├── .zsh/functions.zsh
├── .zsh/profiles/ohmyzsh.zsh
└── .p10k.zsh
```

Le funzioni e alias personali stanno in [`home/.zsh/functions.zsh`](./home/.zsh/functions.zsh). Le integrazioni runtime vivono invece in [`home/.zsh/integrations`](./home/.zsh/integrations), dove vengono caricati i bridge verso strumenti come WezTerm e Gemini CLI quando disponibili.

### Tema Condiviso

Il tema condiviso vive in [`home/.config/theme`](./home/.config/theme):

- `colors.env`: token base in formato shell
- `colors.zsh`: loader Zsh per i token
- `colors.lua`: loader Lua per Neovim e WezTerm

Lo stato runtime del tema e':

```text
~/.local/state/dotfiles/theme
```

Il comando shell:

```sh
theme light
theme dark
```

aggiorna il default globale e applica gli effetti runtime:

- esporta `NVIM_THEME`
- aggiorna `BAT_THEME`
- aggiorna colori di autosuggestions, `fzf`, `ls` e completions
- pubblica `theme_mode` a WezTerm quando la shell gira dentro WezTerm
- ricarica il prompt `p10k`

Alias disponibili:

```sh
light
dark
```

### WezTerm

La config WezTerm e' in [`home/.config/wezterm`](./home/.config/wezterm). L'entrypoint e' [`wezterm.lua`](./home/.config/wezterm/wezterm.lua):

```text
wezterm.lua
├── lua/theme.lua
├── lua/palettes.lua
├── lua/ui.lua
├── lua/keys.lua
└── lua/plugins
    ├── smart-splits.lua
    ├── bar.lua
    └── init.lua
```

Punti importanti:

- `lua/palettes.lua` legge `~/.config/theme/colors.lua`
- `lua/theme.lua` sincronizza tema globale, tab e pane tramite `theme_mode`
- `lua/plugins/smart-splits.lua` integra i pane WezTerm con `smart-splits`
- `CMD+t`, `CMD+n`, `CMD+w`, `CMD+d` e `CMD+SHIFT+d` sono rimappati in `lua/keys.lua`

### Neovim

Neovim e' gestito come submodule:

```text
home/.config/nvim
```

La configurazione ha un README dedicato in [`home/.config/nvim/README.md`](./home/.config/nvim/README.md). Da questo repo interessa soprattutto che:

- il submodule venga inizializzato con `git submodule update --init --recursive`
- `dot.sh apply` crei `~/.config/nvim -> ~/.dotfiles/home/.config/nvim`
- il tema condiviso in `~/.config/theme/colors.lua` sia presente

### Altri Moduli

Karabiner, tmux, IdeaVim e script custom sono documentati in [`docs/MODULES.md`](./docs/MODULES.md). Restano nel repo, ma non sono il percorso principale per capire o installare la configurazione.

## Dipendenze

Il README tiene solo una vista sintetica. La lista completa, divisa per componente, e' in [`docs/DEPENDENCIES.md`](./docs/DEPENDENCIES.md).

Dipendenze minime del repo:

| Dipendenza | Perche' serve |
| --- | --- |
| `git` | clone repo, submodule e plugin esterni |
| `bash` | esecuzione di `scripts/dot.sh` |
| utility base tipo `mkdir`, `mv`, `ln`, `readlink`, `date` | applicazione, adozione e backup dei symlink |
| `zsh` | shell principale configurata dal repo |

Le dipendenze interne a Neovim non sono duplicate qui: sono documentate nel README del submodule `home/.config/nvim`.

La configurazione e' oggi macOS-first. Su Linux la parte portabile e' principalmente `dot.sh`, Zsh, tmux, WezTerm, tema e script generici; vanno invece portati Karabiner, AppleScript, path Homebrew, path TeX Live macOS e funzioni shell basate su comandi macOS.

## Neovim Submodule

Il submodule e' dichiarato in [`.gitmodules`](./.gitmodules):

```ini
[submodule "home/.config/nvim"]
	path = home/.config/nvim
	url = https://github.com/kevinmuka/nvim.git
```

Comandi utili:

```sh
git submodule update --init --recursive
git submodule status
```

Quando aggiorni Neovim dentro `home/.config/nvim`, ricordati che il repo dotfiles traccia solo il puntatore del submodule. Dopo aver committato nel repo Neovim, torna in `~/.dotfiles` e committa l'aggiornamento del puntatore.

## Convenzioni Del Repo

- tutto cio' che deve finire in `$HOME` va sotto `home/`
- non aggiungere mai `home/.config` come symlink unico
- aggiungi i figli di `.config` uno per volta
- tieni gli script custom sotto `home/.config/scripts`
- tieni i token colore condivisi in `home/.config/theme/colors.env`
- evita path assoluti quando una dipendenza puo' vivere nel `PATH`
- se una config resta macOS-only, documentalo nella sezione dipendenze
- se aggiungi un tool esterno usato da alias, script o plugin, documentalo qui

## Bootstrap Rapido

Su una macchina nuova:

1. installa `git`, `bash`, `zsh` e le utility base del sistema
2. clona `~/.dotfiles`
3. esegui `git submodule update --init --recursive`
4. esegui `./scripts/dot.sh apply`
5. installa le dipendenze per le sezioni che vuoi usare, seguendo [`docs/DEPENDENCIES.md`](./docs/DEPENDENCIES.md)
6. installa Oh My Zsh, Powerlevel10k, `zsh-autosuggestions`, `zsh-vi-mode`
7. apri una nuova shell con `exec zsh -l`
8. verifica il tema con `theme light` e `theme dark`

## Troubleshooting

### `~/.config is a symlink`

Lo script si rifiuta di procedere per evitare di controllare tutta `~/.config` come singolo blocco.

```sh
mv ~/.config ~/.config.backup
mkdir -p ~/.config
~/.dotfiles/scripts/dot.sh apply
```

Prima di spostarla, controlla sempre il target:

```sh
readlink ~/.config
```

### Directory Gia' Esistente

Per default una directory reale gia' presente e' un conflitto. Questo evita di rimpiazzare intere configurazioni esistenti con symlink.

Se vuoi linkare solo i file mancanti dentro quella directory:

```sh
~/.dotfiles/scripts/dot.sh plan --merge-existing-dirs
~/.dotfiles/scripts/dot.sh apply --merge-existing-dirs
```

### File Gia' Esistente

Hai gia' un file reale nel path gestito. Lo script lo segnala come conflitto e non lo tocca. Decidi manualmente se adottarlo con `dot.sh add`, spostarlo altrove o lasciarlo fuori dal repo.

### Symlink Che Punta Altrove

Il path e' gia' un symlink ma punta a un'altra destinazione. Anche qui lo script non forza nulla: controlla il target attuale con `readlink` e decidi se sostituirlo.

### Tema Non Sincronizzato

Controlla:

```sh
cat ~/.local/state/dotfiles/theme
echo $ZSH_THEME_MODE
echo $NVIM_THEME
```

Dentro WezTerm, apri una nuova tab o esegui:

```sh
theme dark
theme light
```

### Submodule Neovim Non Presente

```sh
cd ~/.dotfiles
git submodule update --init --recursive
~/.dotfiles/scripts/dot.sh apply
```

## Cose Da Migliorare In Futuro

- rendere piu' portabile `.zprofile`, separando macOS, Linux e tool personali
- evitare `source $(brew --prefix)/...` senza check se Homebrew o il plugin mancano
- decidere se tenere le backup automatiche di Karabiner tracciate o ignorarle
- documentare o automatizzare l'installazione di Oh My Zsh, Powerlevel10k e plugin shell
- valutare uno script `doctor` che controlli symlink, submodule e dipendenze principali
