# macbackup: manuale d'uso

`macbackup` seleziona file e directory del Mac, li copia tramite rclone e separa i dati consultabili (`plain`) da quelli cifrati con rclone crypt (`private`). La struttura remota conserva i percorsi originali e archivia le copie precedenti in `history`. Non è un backup avviabile del Mac né uno snapshot consistente di applicazioni in esecuzione.

Questo manuale descrive il comportamento del programma e usa **esempi**, non la configurazione di un computer specifico. Per vedere la propria selezione usare `macbackup check` e `macbackup preview --local`; per l'ultimo trasferimento usare `macbackup status`. Cronologia, decisioni e collaudi sono in [MACBACKUP_CHANGELOG.md](MACBACKUP_CHANGELOG.md).

## 1. Installazione e primo controllo

Servono macOS, Python 3.11 o successivo e rclone installati nel `PATH`; lo script Python non richiede pacchetti esterni. Per usare `use_gitignore = true` serve anche Git. Lo script versionato si trova in `home/.config/scripts/macbackup` del repository dotfiles. Se i dotfiles collegano quella directory a `~/.config/scripts`, il comando è `~/.config/scripts/macbackup`; deve essere nel `PATH` per usare `macbackup` senza percorso. La configurazione operativa predefinita è `~/.config/macbackup/` e lo stato è in `~/.local/state/macbackup/`. Verificare la posizione della configurazione rclone con `rclone config file`.

```sh
macbackup --version
macbackup init
macbackup check
macbackup preview --local
```

`init` crea i quattro elenchi e `settings.toml` senza inclusioni attive né destinazioni abilitate; se trova anche solo un file di configurazione già presente, si ferma senza sovrascriverlo. I file nuovi hanno permessi 600 e la directory nuova 700. Gli elenchi e lo stato possono contenere nomi sensibili: proteggerli e non aggiungerli a Git senza una revisione esplicita. La configurazione rclone e le chiavi crypt richiedono una copia sicura indipendente dal Mac.

## 2. Posizione sul Mac e rapporto con Git

| Elemento | Percorso tipico |
|---|---|
| Script versionato | `<repo-dotfiles>/home/.config/scripts/macbackup` |
| Comando tramite symlink dei dotfiles | `~/.config/scripts/macbackup` |
| Elenchi e impostazioni | `~/.config/macbackup/` |
| Stato e piani `forget` | `~/.local/state/macbackup/` |
| Configurazione rclone | percorso restituito da `rclone config file` |

`~` in questa tabella indica la home dell'utente; negli elenchi di inclusione ed esclusione vanno invece scritti percorsi **assoluti**, per esempio `/Users/example/Documents/`. Lo script, i test e il manuale possono essere versionati; token, password, chiavi crypt, stato operativo ed elenchi personali richiedono protezione separata. L'opzione globale `--config-dir PATH` cambia la directory degli elenchi e di `settings.toml`, non la posizione dello stato o delle credenziali rclone.

## 3. Configurazione

La directory di configurazione contiene `plain-paths.txt`, `private-paths.txt`, `exclude-paths.txt`, `explicit-only-patterns.txt` e `settings.toml`. I primi tre elencano percorsi assoluti. Il quarto elenca nomi che richiedono un'inclusione esatta. Le destinazioni e le policy per nome sono in TOML.

Esempio da adattare, **non valore predefinito né fotografia di un'installazione**:

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

`init` usa `max_delete = 25`; l'esempio mostra `100` come scelta possibile. Il valore accettato è un intero fra 0 e 10.000. Il limite si applica per destinazione e area alle copie da archiviare per cancellazione locale o cambio di policy, incluse le icone. Non è una scadenza dello storico. Configurare e provare i due remotes rclone prima di abilitare una destinazione; per eseguire `check --remote`, `preview --target`, `run` e `mount`, impostare poi `enabled = true`. Per questi comandi, `--target all` richiede entrambe le destinazioni abilitate. `versions`, `restore`, `verify` e `forget` possono leggere una destinazione disabilitata, purché i suoi remotes siano ancora configurati.

Un remote plain, come `gdrive:`, accede al servizio. Un remote crypt, come `gdrive-private:`, avvolge la directory privata dello **stesso** account; non è una seconda copia indipendente. Nella tabella sopra, `gdrive-private:` deve puntare a `gdrive:MacBackup/private`. Per Proton occorre una coppia di remotes distinta. I nomi sono esempi: fa fede `settings.toml`. I file plain possono essere consultati dall'app del provider se il formato è supportato; i file private richiedono rclone crypt e le relative chiavi.

### 3.1 Sintassi dei tre elenchi di percorsi

- Una riga contiene un percorso assoluto e letterale.
- Righe vuote e righe che iniziano con `#` sono ignorate.
- Non si usano virgolette negli elenchi, nemmeno per nomi con spazi.
- Non si espandono `~`, `$HOME`, variabili, comandi o caratteri jolly.
- Non si supportano commenti alla fine di una riga che contiene un percorso.
- Un file seleziona quel file; una directory seleziona ricorsivamente i discendenti, compresi i file nascosti, ma senza autorizzare implicitamente file o directory soggetti alla regola explicit-only.
- La barra finale può indicare una directory; non cambia la precedenza delle regole.
- Il programma rifiuta percorsi relativi e componenti `..`, invece di interpretarli in modo dipendente dalla posizione del terminale.
- La selezione della radice `/` come intera sorgente è rifiutata. `/` è soltanto il riferimento per ricostruire i percorsi.
- Nomi non rappresentabili senza ambiguità nel formato a righe, per esempio contenenti un ritorno a capo, devono produrre un errore esplicito. Il programma non deve saltarli silenziosamente.

Le regole sono letterali: un percorso che contiene `[` o `*` nel nome non deve diventare accidentalmente un filtro. La generazione delle regole rclone deve gestire correttamente questi caratteri.

### 3.2 Precedenza

1. Un'esclusione assoluta prevale su tutto: il percorso non viene salvato, nemmeno se elencato direttamente in plain o private.
2. Un file con un nome in `[policy].ignored_file_names` viene saltato se è incluso soltanto tramite una directory superiore. Un'inclusione esatta del file in plain o private lo autorizza; la regola riguarda i file, non una directory con lo stesso nome.
3. Se il nome di un file o di una directory corrisponde a explicit-only, l'elemento non viene salvato a meno che il suo percorso completo compaia direttamente in `plain-paths.txt` o `private-paths.txt`. Elencare soltanto una directory superiore non soddisfa questo requisito, neppure nell'area privata. Una directory saltata non viene attraversata. Eccezione deliberata: una directory che corrisponde anche a `private_directory_names` viene attraversata e cifrata automaticamente, salvo inclusione esatta in plain; altre protezioni al suo interno continuano a valere.
4. Se `use_gitignore = true`, le regole `.gitignore` possono escludere i percorsi selezionati soltanto tramite una directory superiore. Un'inclusione esatta del percorso e la cifratura automatica tramite `private_directory_names` prevalgono. Una directory ignorata non viene attraversata.
5. Superati questi controlli, un'inclusione privata vince su plain. Una directory che corrisponde a `private_directory_names` e i suoi discendenti vengono cifrati, salvo che quella directory sia stata inclusa **esattamente** in `plain-paths.txt` e non sia coperta da `private-paths.txt`. Una sola inclusione della directory superiore non disattiva la cifratura automatica.
6. Un'inclusione normale non privata viene salvata nell'area `plain`.
7. Un percorso non selezionato non viene salvato.

Le policy per nome danno il comportamento predefinito; un'inclusione **esatta** può autorizzare un file ignorato o rendere plain una directory cifrata automaticamente per nome. `private-paths.txt` prevale su `plain-paths.txt` per lo stesso percorso, mentre `exclude-paths.txt` prevale su entrambi. Includere soltanto la directory superiore non crea eccezioni esatte per i suoi discendenti.

Non si consente di reincludere un discendente di una directory esclusa. Dentro una directory cifrata per inclusione in `private-paths.txt`, plain non può prevalere; l'eccezione plain riguarda soltanto la cifratura automatica per nome e richiede l'inclusione esatta della directory. Queste scelte mantengono prevedibili le regole indipendentemente dall'ordine delle righe.

Con `private_directory_names = [".git"]`, una directory `.git` sotto una sorgente selezionata viene cifrata anche se `.git` compare in `explicit-only-patterns.txt`: questa è l'eccezione esplicita al blocco per nome. Se aggiungi `/Users/example/Desktop/project/.git` direttamente a `plain-paths.txt`, la directory e i file ammessi al suo interno diventano plain. Se lo stesso percorso è anche in `private-paths.txt`, resta cifrato. Un `.env` al suo interno rimane soggetto alla propria regola explicit-only. La regola automatica riguarda le **directory** chiamate `.git`, non un file ordinario con quel nome; un'esclusione assoluta continua a prevalere. Cambiare una `.git` da private a plain sposta la vecchia copia da `private/current` a `private/history` e carica la nuova in `plain/current`: per rimuovere anche la vecchia copia cifrata serve `forget --area private`.

Un percorso indica se stesso e i propri discendenti, non nomi simili: `/a/karabiner/` non comprende `/a/karabiner-old/`.

Per ignorare altri nomi di file in tutta la selezione, aggiungerli come stringhe letterali a `ignored_file_names` in `settings.toml`, per esempio `ignored_file_names = [".DS_Store", "Thumbs.db"]`. Il confronto non distingue maiuscole e minuscole; non sono ammessi percorsi o wildcard. Gli spazi dentro le stringhe TOML sono significativi: `" ← "` indica esattamente un nome con uno spazio prima e uno dopo la freccia. Per esempio, una policy può ignorare `.DS_Store`, ` ← ` e `.localized` quando sono inclusi tramite una directory superiore. Per salvarne una specifica copia, aggiungi il percorso assoluto del file a `plain-paths.txt` o `private-paths.txt`; private vince se il percorso compare in entrambi ed exclude prevale sempre. Questa inclusione non autorizza altri file con lo stesso nome. Una nuova regola archivia nella prossima `run` le copie non più ammesse presenti in `current`, lasciandole in `history`; per rimuoverle da tutte le versioni si usa `forget`. La regola non cancella file locali.

`use_gitignore = true` usa Git per leggere i file `.gitignore` lungo i percorsi inclusi, anche in directory che non sono repository Git. Sono supportati i pattern e le negazioni di Git; non vengono consultati l'indice, `.git/info/exclude` e i file globali di esclusione. La ricerca parte dalla radice del filesystem, quindi può applicare anche `.gitignore` in directory antenate della sorgente selezionata. I collegamenti simbolici non vengono attraversati. Il file `.gitignore` stesso resta selezionabile come gli altri file, a meno che una regola non lo escluda. Serve Git nel `PATH`; se il controllo fallisce, la selezione si ferma.

`init` imposta questa opzione a `false`. Prima di passare a `true`, confrontare `macbackup preview --local` con il risultato precedente: i file ignorati verranno omessi anche se la directory che li contiene è in `plain-paths.txt` o `private-paths.txt`. Un file elencato direttamente in `plain-paths.txt` o `private-paths.txt` resta incluso anche se il suo nome o una directory antenata è ignorata da `.gitignore`; `private` mantiene la precedenza su `plain`. Un'inclusione esatta di una directory non disattiva le regole per i suoi discendenti. Le cartelle `.git` cifrate automaticamente tramite `private_directory_names` restano incluse. L'aggiunta di un `.gitignore` o l'attivazione dell'opzione fa archiviare nella prossima `run` le vecchie copie non più selezionate da `current` allo storico della stessa area. Non le elimina; per rimuoverle da tutte le versioni si usa `forget`.

### 3.2.1 Nomi ammessi soltanto tramite inclusione esatta

Configurazione iniziale di `explicit-only-patterns.txt`:

```text
.env
.env.*
```

Qui si descrivono nomi, non percorsi assoluti. La regola `.env` corrisponde a quel nome in qualsiasi directory; `.env.*` comprende per esempio `.env.local`, `.env.production` e anche `.env.example`. Un file di esempio eventualmente innocuo va incluso direttamente se lo si desidera: non si presume che sia privo di segreti. Si possono aggiungere nomi come `node_modules`, `.venv`, `venv` e `myenv`: una directory con uno di questi nomi viene saltata ovunque si trovi.

La sintassi accetta nomi e il carattere jolly `*`, limitato al nome finale del file o della directory; non accetta `/`, `**`, espressioni regolari o regole con segno `+` o `-`. Righe vuote e commenti a inizio riga funzionano come negli altri elenchi. Per prudenza questi soli controlli sui nomi sono senza distinzione tra maiuscole e minuscole: anche `.ENV` richiede un'inclusione esatta. Gli altri percorsi mantengono la propria semantica e non diventano globalmente insensibili alle maiuscole.

La regola riguarda file, directory ed elementi simbolici con quei nomi. Per autorizzare esplicitamente una directory protetta si aggiunge il suo percorso completo a un elenco di inclusione; i file al suo interno seguono comunque le altre regole, quindi un `.env` resta protetto. La selezione di un collegamento salva il collegamento secondo la politica descritta sotto e non autorizza automaticamente la copia della destinazione.

Esempio con `/Users/example/Desktop/progetto/` in plain:

| Configurazione aggiuntiva | Esito per `/Users/example/Desktop/progetto/.env` |
|---|---|
| Nessuna | Saltato: incluso soltanto attraverso la directory |
| Percorso esatto in plain | Salvato nell'area normale, con avviso di inclusione esplicita di un nome protetto |
| Percorso esatto in private | Salvato cifrato e assente dalla copia normale |
| Directory progetto in private, senza il percorso esatto del file | Saltato: anche l'inclusione privata è soltanto ereditata |
| Percorso esatto in entrambi gli elenchi | Salvato cifrato: private prevale |
| Percorso del file o di un suo antenato in exclude | Saltato in ogni caso |

L'autorizzazione è soltanto per il percorso scritto: elencare esattamente `progetto/.env` non autorizza `progetto/subdir/.env`, `altro-progetto/.env` o `progetto/.env.local`.

Questa regola vale sia nell'anteprima sia nei trasferimenti. Un nuovo `.env` creato dentro una cartella durante la run non deve passare attraverso una semplice inclusione ricorsiva della directory.

Rimuovere il percorso esatto dall'elenco, oppure aggiungere un nuovo pattern di protezione, fa archiviare nella prossima `run` la copia già presente in `current`. Le versioni in `history` restano conservate; per rimuoverle resta necessario `forget`. `preview --local` mostra i nomi bloccati; `versions` e `forget` permettono di trovare le copie cloud precedenti. `preview --target` e `status` distinguono le archiviazioni dovute alla policy dalle cancellazioni locali e registrano la regola attuale che ha causato la nuova esclusione. Non possono ricostruire la regola storica che aveva originariamente incluso il file.

Questa protezione si applica ai caricamenti di macbackup sui cloud. Non configura Git, non crea regole `.gitignore` e non impedisce un push Git effettuato con altri strumenti. Non riconosce un segreto copiato dentro un file con altro nome o un archivio. Se `.git` è in `private_directory_names`, le directory corrispondenti sono cifrate automaticamente; ciò non elimina eventuali copie precedenti in chiaro, che si possono cercare e rimuovere con `versions` e `forget`.

Il file di regole deve essere creato all’inizializzazione. Se manca o non è leggibile, `check`, `preview` e `run` si fermano: non viene interpretato come un elenco di protezioni vuoto.

### 3.3 Esempio di selezione

Questi file mostrano la sintassi. Sostituire `/Users/example` con il percorso assoluto della propria home e scegliere consapevolmente cosa rendere consultabile.

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
/Users/example/.config/app-con-token/
/Users/example/Documents/site/dist/
/Users/example/Documents/site/.vercel/output/
```

```text
# explicit-only-patterns.txt
.env
.env.*
node_modules
.venv
venv
myenv
.git
.astro
```

Sono **otto pattern di esempio**; `init` ne crea soltanto due (`.env` e `.env.*`). Le esclusioni `dist/` e `.vercel/output/` qui sono assolute e limitate a un solo progetto: non escludono directory con gli stessi nomi altrove. Se si vuole una regola globale per nome, usare `explicit-only-patterns.txt`. Con `private_directory_names = [".git"]`, le directory `.git` sotto una sorgente inclusa sono cifrate automaticamente anche se `.git` è explicit-only; la precedenza completa è in §3.2.

Per conoscere la configurazione effettiva aprire i cinque file di `~/.config/macbackup/`, oppure usare `macbackup check`, `macbackup explain ABS_PATH` e `macbackup preview --local`. Non dedurre la selezione da questi esempi.

### 3.4 Credenziali e collegamenti simbolici

Non si può promettere di riconoscere automaticamente ogni segreto dentro Desktop, Documents, repository o `.config`. Prima del primo caricamento occorre rivedere le selezioni. Il selettore protegge la posizione standard della configurazione rclone e lo stato standard di macbackup, anche quando sono raggiunti tramite collegamenti. Se rclone usa una posizione personalizzata, il selettore non la rileva automaticamente: aggiungerla esplicitamente a `private-paths.txt` quando deve essere salvata e controllarne la classificazione con `explain`.

I link simbolici non devono essere seguiti automaticamente. Possono essere conservati mediante `--links`, che rclone rappresenta sul cloud con file aventi suffisso `.rclonelink`. Il contenuto del link è il percorso della destinazione, non il contenuto della destinazione.

Per questo selezionare `.config/` non basta a salvare il contenuto di un repository raggiunto soltanto attraverso un collegamento: anche il percorso reale deve essere incluso. Una directory raggiungibile solo tramite symlink va inclusa anche dal suo percorso reale se si desiderano i contenuti.

### 3.5 Preparare i remotes rclone

Configurare una coppia `plain`/`private` per ogni servizio che si intende usare. La voce `private` di `settings.toml` deve riferirsi a un remote rclone di tipo `crypt` che avvolge l'area privata **dello stesso servizio**, comprese `current`, `history` e `macos-icons`. Usare il remote crypt per leggere e ripristinare i file riservati; accedere direttamente alla cartella sottostante mostra soltanto oggetti cifrati. Conservare password crypt ed eventuale salt in un gestore di password recuperabile senza il Mac.

Per Google, seguire la [guida rclone per Drive](https://rclone.org/drive/) per l'OAuth e verificare il remote con `rclone about NOME_REMOTE:`. Il permesso `drive.file` consente di gestire i file autorizzati all'app; non concede automaticamente accesso a ogni file già presente in Drive. Un client OAuth personale in stato Testing può avere refresh token con durata limitata: verificare lo stato dell'app e le regole Google prima di affidare il backup a un'esecuzione automatica. Il montaggio in sola lettura non cambia i permessi OAuth del remote. Per Proton usare la [guida rclone Proton Drive](https://rclone.org/protondrive/) e provare separatamente copia e recupero. I remotes vanno configurati in rclone, non contengono credenziali in `settings.toml`.

L'ordine operativo è: configurare i remotes in rclone e provarne l'accesso, compilare gli elenchi, eseguire `macbackup check` e `macbackup preview --local`, abilitare la destinazione in `settings.toml`, quindi eseguire `macbackup check --remote --target google` e `macbackup preview --target google`. Sostituire `google` con il target da configurare. Solo dopo aver controllato le operazioni previste eseguire `run`; verificare il risultato con `status`, `verify` e una prova di recupero di un file non sensibile in una directory separata. Il controllo remoto legge inventari e capacità, non certifica la recuperabilità di ogni file. `preview --target` è una simulazione e non prenota lo stato dei file: `run` ripete i controlli.

## 4. Struttura delle destinazioni

Ogni servizio contiene un'area dedicata a questo backup:

```text
MacBackup/
  plain/
    current/
      Users/example/...
      etc/hosts
      Volumes/Archivio/...
    history/
      RUN_ID/...
  private/
    [nomi e contenuti cifrati]
```

La vista logica dell'area privata, attraverso il remote crypt, è:

```text
current/Users/example/.ssh/...
history/RUN_ID/Users/example/.ssh/...
```

Il remote crypt deve comprendere l'intera area privata, incluso lo storico. Il backup privato non deve essere eseguito direttamente sul remote sottostante. Ogni servizio ha un proprio collegamento crypt; non serve una copia da Google a Proton, perché entrambi leggono le sorgenti locali.

La struttura riproduce i percorsi, ma non conserva le directory vuote prive di icone, ACL, tutti gli attributi estesi o i resource fork dei file ordinari. Il recupero non ricostruisce tutte le proprietà del filesystem macOS. Un database applicativo aperto richiede una procedura di esportazione o chiusura coerente prima della copia.

Conservare fuori dal Mac i parametri necessari a ricreare il remote crypt, inclusi password e salt personalizzato se usato. Non basta conoscere la password di Google o Proton. La configurazione rclone deve essere protetta anche localmente: il normale offuscamento delle password non è cifratura sicura della configurazione.

### 4.1 Icone Finder personalizzate

Un file macOS chiamato `Icon\r` può contenere l'immagine nel resource fork anche quando il file ordinario è vuoto. `macbackup` salva uno snapshot `icon.json` con i dati necessari del file, il resource fork e i FinderInfo della cartella. Gli altri nomi con caratteri di controllo restano bloccati. Gli snapshot seguono le stesse inclusioni, esclusioni e regole di archiviazione dei file; quelli privati attraversano il remote crypt. La stima di `check` non comprende i byte dei resource fork. Un file o attributo icona oltre 64 MiB blocca la fase interessata.

Per recuperare un'icona, scaricare il suo `icon.json` dalla corrispondente area `macos-icons/current` o `history/RUN_ID`, poi applicarlo a una **cartella di prova già esistente**:

```sh
rclone copyto "gdrive:MacBackup/plain/macos-icons/current/Users/example/Documents/Foto/icon.json" \
  "$HOME/Downloads/icon.json"
macbackup restore-icon --file "$HOME/Downloads/icon.json" \
  --folder "$HOME/Downloads/Foto"
```

`restore-icon` lavora solo in locale e non usa il percorso sorgente scritto nello snapshot come destinazione. La cartella indicata da `--folder` deve esistere e non essere un symlink. Se contiene già un'icona, serve `--replace`; `--json` restituisce il risultato strutturato. Per un'icona privata scaricare lo snapshot attraverso il remote crypt.

## 5. Cosa accade durante il backup

| Evento | Effetto |
|---|---|
| Nuovo file selezionato e ammesso dalle protezioni | Caricato nell'area assegnata, sotto `current` |
| Nuovo `.env` incluso soltanto tramite una directory | Saltato, con motivazione explicit-only |
| Percorso esatto di un file protetto tolto dagli elenchi | Copia in `current` archiviata nella stessa area alla prossima run; storici conservati |
| File modificato | Copia precedente nello storico; nuova copia in `current` |
| File cancellato dentro una directory selezionata e disponibile | Copia precedente spostata nello storico |
| Percorso aggiunto alle esclusioni | Copia in `current` archiviata nella stessa area; storici conservati |
| Percorso tolto dagli elenchi | Copia in `current` archiviata nella stessa area; storici conservati |
| Percorso passato da normale a privato | Vecchia copia plain archiviata in `plain/history`; nuova copia cifrata in `private/current` |
| Percorso passato da privato a normale | Vecchia copia private archiviata in `private/history`; nuova copia consultabile in `plain/current` |
| Sorgente esplicitamente inclusa mancante o illeggibile | Operazione interessata bloccata; nessuna interpretazione come directory vuota |
| Spazio remoto insufficiente | Errore; nessuna pulizia automatica dello storico |

Dopo una `run` riuscita, `current` contiene i percorsi selezionati dalla policy attuale. Le copie non più selezionate vengono spostate in `history` nella stessa area, senza cancellarle. Una run interrotta o fallita può lasciare uno stato parziale; `status` mostra le archiviazioni riuscite e quelle ancora previste.

Se entrambi gli elenchi di inclusione vengono svuotati, una `run` può ancora archiviare le copie già presenti in `current`, sempre entro `max_delete`. Se non esiste neppure una copia corrente da archiviare, l'operazione remota si ferma senza fare nulla.

La sparizione di una sorgente esplicitamente elencata è ambigua e blocca il backup: potrebbe essere un disco scollegato o una cancellazione intenzionale. La cancellazione di un file figlio dentro una directory selezionata e correttamente disponibile è invece una normale cancellazione da archiviare.

Per i volumi esterni, la presenza di una directory non prova da sola che il volume previsto sia montato; il programma non verifica ancora l’identità del volume.

Non è prevista alcuna scadenza automatica degli storici di macbackup. Cestino e versioni interne dei servizi seguono invece le rispettive regole del provider.

Ogni tentativo usa un identificativo unico per lo storico. Un nuovo tentativo non deve riusare una cartella di storico in cui potrebbe sovrascrivere una versione conservata. Un'esecuzione interrotta può avere già trasferito o archiviato alcuni file: non è una transazione atomica, né tra file né tra servizi.

## 6. Comandi

Sono sottocomandi di macbackup, non di rclone. Il ripristino generale di un albero rimane non disponibile.

| Comando | Effetto principale |
|---|---|
| `init` | Crea localmente quattro elenchi e `settings.toml`, senza inclusioni attive |
| `check` | Controlla sorgenti locali; con `--remote --target` legge anche inventari e remotes |
| `explain PATH` | Spiega la classificazione locale di un singolo percorso |
| `layout [PATH]` | Mostra le parti private dentro una directory plain; senza PATH usa la directory corrente |
| `preview --local` / `preview --target` | Mostra la selezione locale o simula il trasferimento remoto senza modifiche |
| `run --target` | Trasferisce nelle aree abilitate, conserva versioni e mostra l'avanzamento |
| `mount --target` | Monta plain, private o entrambe in sola lettura su macOS; Ctrl-C o espulsione dal Finder smonta |
| `status` | Legge il resoconto locale dell'ultima run, anche interrotta |
| `restore-icon` | Ricrea localmente un'icona Finder da uno snapshot già scaricato |
| `versions PATH` | Elenca le copie di un file o riepiloga quelle sotto una directory |
| `restore PATH` | Scarica un file in una destinazione esplicita; con `--links` ricrea un symlink |
| `verify --target` | Confronta le sorgenti attuali con `current`, senza modifiche |
| `forget` | Prepara un piano di rimozione e, con `--plan ID --apply`, lo applica |

L'opzione globale `--config-dir PATH` va prima del sottocomando e fa leggere elenchi e `settings.toml` da una directory alternativa. La selezione può quindi cambiare; la posizione dello stato e delle credenziali rclone resta quella predefinita. I comandi di lettura e di esecuzione che prevedono `--json` restituiscono JSON UTF-8.

Nei terminali interattivi, le fasi lunghe di scansione, pianificazione, ricerca delle versioni, recupero e verifica mostrano una barra ASCII animata su stderr. La durata è in secondi e la barra non mostra una percentuale quando il totale non è noto. Durante queste fasi i tasti ordinari vengono scartati senza apparire nel terminale; `Ctrl-C` resta disponibile. `run` conserva invece i propri tasti `u` e `?` durante il trasferimento. I comandi immediati, come `explain` e `status`, non mostrano una barra. Gli esiti, gli avvisi e gli errori usano colori quando il terminale li supporta; `NO_COLOR=1` o `PYTHON_COLORS=0` li disattivano. In `check` e `preview --local` i percorsi sono attenuati e il riepilogo è separato dagli avvisi. Anche gli identificatori di versione, i percorsi negli elenchi e le note finali degli altri comandi sono attenuati nei terminali a colori; conteggi ed esiti restano in evidenza. L'output reindirizzato e il JSON non contengono codici colore; gli indicatori non cambiano il formato JSON su stdout. Il completamento Zsh usa descrizioni brevi: i nomi sono blu e le descrizioni grigie nei terminali che supportano i colori, salvo `NO_COLOR`. Prima del comando mostra soltanto le opzioni globali; dopo il comando mostra quelle specifiche, senza eseguire macbackup o rclone.

Valori uniformi:

- `--target google|proton|all`: destinazioni.
- `--area plain|private|all`: aree, quando il comando lo richiede.
- I percorsi contenenti spazi devono essere tra virgolette nella shell.
- Un'opzione che seleziona un'area privata non deve richiedere di digitare nomi cifrati.

I codici d'uscita sono `0` per un'operazione completata, `1` per un controllo fallito o un errore di trasporto e `2` per configurazione o uso non validi. `Ctrl-C` restituisce di norma `130`; durante `run` l'interruzione viene invece registrata come risultato parziale e il comando restituisce `1`. Un `check` con elenchi vuoti restituisce `0` con un avviso: non significa che esista un backup.

### 6.1 `check`: controllo locale e remoto

```sh
macbackup check
macbackup check --json
```

`check` carica gli elenchi e le policy, verifica sintassi e precedenze, attraversa le sorgenti incluse, controlla che i percorsi richiesti esistano e che i file selezionati siano leggibili. Usa nomi e metadati senza leggere il contenuto dei file da salvare; legge però i file di configurazione. Segnala file speciali saltati, collegamenti simbolici conservati senza seguire la destinazione, nomi protetti autorizzati esplicitamente in chiaro e conflitti locali fra aree. La scansione considera anche `.gitignore` quando `use_gitignore` è attivo. Senza `--remote` non apre il cloud. Nel riepilogo leggibile la dimensione è mostrata in unità decimali (`kB`, `MB`, `GB`); `--json` conserva il numero esatto di byte in `summary.selected_bytes`.

L'avviso «collegamento; destinazione non attraversata» significa che viene conservato il symlink, senza copiarne anche il contenuto di destinazione attraverso quel percorso. Se serve salvare pure la destinazione, questa deve rientrare autonomamente nelle sorgenti selezionate. L'avviso «socket, FIFO o dispositivo saltato» riguarda un oggetto speciale che non viene copiato: per esempio un socket usato da un'applicazione in esecuzione non è un normale file da recuperare. Gli avvisi descrivono ciò che la scansione ha trovato; il riepilogo finale conta separatamente elementi normali, privati e saltati.

`check --remote` esegue prima la stessa scansione locale. Poi legge `settings.toml`, verifica che la destinazione sia abilitata e che i remotes esistano, richiede un remote `crypt` per private e un backend con hash per plain. Legge una volta gli inventari di `plain/current`, `private/current` e delle icone delle due aree: rifiuta nomi invalidi o duplicati nella stessa area, valuta quali copie non corrispondono più alle policy e rileva conflitti fra le due aree di `current`. Il conflitto è un percorso condiviso che è un file in almeno un'area; due directory con lo stesso percorso sono ammesse. L'errore indica fino a cinque percorsi di esempio. Senza `--target` usa Google; con `--target all` controlla entrambe le destinazioni abilitate.

Il controllo remoto non modifica il cloud e non verifica il contenuto o la recuperabilità dei file; non scandisce `history` e non applica `max_delete`. Per vedere il piano di archiviazione e l'eventuale superamento del limite, usare `preview --target google`. Per confrontare i dati locali con `current`, usare `verify --target google`. La lettura delle sorgenti può richiedere il consenso di macOS per Desktop o Documents: un rifiuto è un errore da risolvere, non un'esclusione silenziosa.

### 6.2 `preview`: mostrare le operazioni

```sh
macbackup preview --local
macbackup preview --local --json
```

La modalità locale mostra i percorsi e la loro classificazione locale, i motivi di esclusione e gli avvisi. Le inclusioni esatte di nomi protetti nell'area normale sono evidenziate. Un file bloccato da explicit-only riporta anche il pattern responsabile nel risultato JSON e nella spiegazione individuale. Non confronta il cloud né stima quanti byte restano da trasferire. Se la scansione trova errori, non presenta le voci parziali come un piano valido. Per una directory esclusa mostra il sottoalbero senza visitarne tutti i file: il numero degli elementi saltati non è un conteggio completo dei discendenti esclusi.

La modalità `preview --target google` esegue il dry-run remoto e riporta per destinazione e area i file selezionati, le archiviazioni dovute a cancellazioni locali e quelle dovute alla policy. Per queste ultime mostra percorso, nuova classificazione, motivo e regola attuale, se disponibile. Legge i contenuti locali necessari al confronto, ma non modifica il cloud. Non elenca necessariamente tutte le future sostituzioni dei file modificati. Se il totale delle archiviazioni supera `max_delete`, l'anteprima lo segnala; una `run` con la stessa selezione si fermerà prima dei trasferimenti.

La modalità locale non accede al cloud e non scrive un resoconto: stampa il risultato.

Per capire la classificazione di un singolo percorso, senza scandire tutte le sorgenti:

```sh
macbackup explain "/Users/example/Desktop/progetto/.env"
macbackup explain "/Users/example/Desktop/progetto/.env" --json
```

Le spiegazioni e le anteprime locali non provano che i file siano già salvati o cifrati. La presenza di una cartella privata sul cloud dipende dalla configurazione dei remotes e dai trasferimenti già eseguiti.

Per vedere quali parti private si trovano dentro una cartella selezionata in plain, usare `macbackup layout "/Users/example/Desktop/progetto"`. Senza percorso il comando usa la directory corrente. Richiede una directory locale classificata plain, esegue una scansione locale completa e riporta le radici dei sottoalberi privati con conteggi e dimensioni, senza elencarne tutti i file. `--json` aggiunge i percorsi logici in `private/current`. Non accede al cloud, non mostra storici o vecchie copie in chiaro e non legge il contenuto dei file. Se la scansione fallisce, non presenta un risultato parziale come valido.

L'anteprima non congela i file né le destinazioni. Una successiva esecuzione deve rivalidare la situazione: non si promette che eseguirà esattamente un elenco calcolato ore prima.

### 6.3 `run`: eseguire il backup

```sh
macbackup run --target all
macbackup run --target google
macbackup run --target proton
```

Il programma ricontrolla la configurazione, acquisisce un blocco contro esecuzioni concorrenti e svolge le operazioni nelle aree assegnate. Un percorso privato non deve essere caricato nell'area normale in caso di errore della cifratura. Durante `run`, macbackup mostra i rapporti di rclone ogni 5 secondi in una schermata dedicata, se il terminale è interattivo. Le barre ASCII distinguono il progresso in byte da quello in file. La velocità complessiva è in evidenza; per ciascun file attivo, percorso e velocità sono su righe diverse. Tempo trascorso e stima sono arrotondati ai secondi, senza millisecondi. Premi `u` per alternare unità binarie (KiB, MiB, GiB e relative velocità) e decimali (kB, MB, GB); premi `?` per mostrare o nascondere la legenda. La riga dei tasti indica quale unità verrà scelta e se `?` mostrerà o nasconderà la legenda. La legenda descrive soltanto la fase corrente; i percorsi dei file attivi sono attenuati nei terminali a colori per distinguerli dalle statistiche. È una scelta di visualizzazione durante la fase corrente e non modifica i file né il resoconto. Ctrl-C interrompe il trasferimento come prima; il terminale viene ripristinato. Senza terminale interattivo, le stesse informazioni vengono stampate periodicamente come testo e non si possono usare i tasti. Più file e più cartelle possono essere trasferiti contemporaneamente: non esiste sempre un'unica «directory corrente». Ogni rapporto riassume le cartelle dei file attivi, raggruppandole per due livelli sotto la home. Si può scegliere da uno a cinque livelli con `--progress-depth N`, per esempio `macbackup run --target google --progress-depth 3`. I percorsi dei file attivi non vengono troncati. Le statistiche sono della fase plain, icone o private in corso, non dell'intero backup. `status` viene scritto al termine; dopo Ctrl+C durante il trasferimento registra la fase interrotta. Alla run successiva vengono confrontati i file già completi; macbackup non conserva byte parziali per riprendere il file interrotto, che viene ritrasferito dall'inizio.

`run --json` esegue lo stesso backup reale e cambia soltanto il riepilogo finale su stdout. L'avanzamento resta sul terminale tramite stderr. Senza `--json`, il riepilogo finale distingue i selezionati dai trasferiti e dai controllati; `status` conserva gli stessi conteggi per ogni fase conclusa o interrotta. Lo stato viene scritto al termine del tentativo, non durante il trasferimento; un'interruzione nella pianificazione iniziale può non produrre un nuovo stato.

Prima di una quantità anomala di spostamenti da `current` a `history`, il programma si ferma. La soglia è `max_delete` in `settings.toml`, applicata per area e destinazione (25 dopo `init`), e comprende sia le cancellazioni locali sia i cambi di policy. L'anteprima remota segnala il superamento della soglia senza modificare nulla; una run con lo stesso piano si ferma prima dei trasferimenti. Il confronto ordinario dell'area privata usa `rclone cryptcheck` per rilevare anche modifiche a parità di dimensione e orario; se non è completo, la fase viene bloccata. Un file privato invariato non dovrebbe generare una nuova versione storica.

L'esito è separato per Google/Proton e plain/private. Una destinazione può riuscire mentre l'altra fallisce: il riepilogo e il codice di uscita devono indicare il risultato parziale. Un successo richiede il completamento di tutte le operazioni richieste.

La singola esecuzione non garantisce la stessa fotografia temporale sui due servizi: se i file locali cambiano tra le letture, le copie possono riferirsi a istanti diversi. Il backup non va presentato come snapshot simultaneo.

### 6.4 `mount`: consultare le copie in sola lettura

```sh
macbackup mount --target google                 # equivalente a --area all: un volume google
macbackup mount --target google --area all      # current/ unificato, storici separati per area
macbackup mount --target google --area plain    # solo google-plain
macbackup mount --target google --area private  # solo google-private
```

Il comando usa i percorsi `plain` e `private` di `settings.toml`. La sintassi è `--area all`, non `--all`: `--area` sceglie quali aree mostrare, mentre `--target` sceglie il servizio. Con `--area all` (il valore predefinito) crea direttamente sul Desktop un solo volume `google`. `current/` mostra i file normali e quelli privati nello stesso albero dei percorsi originali; una `.git` privata appare così accanto ai file normali del suo progetto. `history/plain/` e `history/private/` rimangono separati, perché una versione precedente potrebbe esistere in entrambe le aree. Gli snapshot delle icone Finder restano consultabili sotto `icons/plain/` e `icons/private/`. Questa è solo una vista in lettura: i percorsi cloud, la classificazione e la cifratura non cambiano. Rclone crea la vista con `union` per `current` e `combine` per gli altri rami, usando remotes temporanei solo nel processo di montaggio. Con `--area plain` o `--area private` monta invece il solo volume `google-plain` o `google-private`. `--mountpoint /percorso/assoluto` cambia la cartella **base** e conserva questi nomi al suo interno. È previsto anche `--target proton` quando quel servizio sarà configurato e abilitato; `--target all` richiede entrambi i servizi abilitati e monta un volume per servizio.

Prima di montare `--area all`, macbackup legge gli inventari di `plain/current` e `private/current`. Le directory condivise sono normali; se lo stesso percorso è un file in entrambe le aree, o è un file in una e una directory nell’altra, il montaggio viene bloccato con i percorsi in conflitto. Non viene scelta silenziosamente una copia. Durante le due letture degli inventari e l’avvio del volume, il terminale mostra una barra ASCII animata con il tempo trascorso; per gli inventari indica anche i MiB di metadati ricevuti. Anche durante queste fasi, i tasti ordinari vengono scartati senza comparire nel terminale e `Ctrl-C` interrompe l'operazione. La barra è intenzionalmente senza percentuale, perché la dimensione totale e la durata della scansione non sono note in anticipo. Nei terminali che supportano il colore, fasi, barre ed esiti sono evidenziati; `NO_COLOR=1` o `PYTHON_COLORS=0` li disattivano. Quando l’output è reindirizzato, i codici colore non vengono emessi. Senza terminale interattivo stampa soltanto l’inizio e la fine di ogni fase. `Ctrl-C` durante la scansione interrompe il processo rclone avviato per l’inventario. La scansione iniziale può richiedere tempo su backup grandi. Per ispezionare comunque le copie si possono montare separatamente `--area plain` e `--area private`.

Su macOS usa `rclone nfsmount` con `--read-only`, senza richiedere macFUSE. Lascia aperto il terminale del comando: mentre il volume è montato, i tasti digitati non vengono mostrati né eseguiti; `Ctrl-C` smonta il volume. Puoi anche selezionarlo nel Finder e premere `⌘E`. In entrambi i casi macbackup conferma con `Volume smontato: <percorso>` quando il volume non risulta più montato, ripristina l'input del terminale e rimuove i punti di montaggio vuoti creati da questa esecuzione. Un arresto anomalo di rclone resta invece un errore. Una cartella vuota preesistente viene conservata. I montaggi predefiniti sul Desktop sono esclusi automaticamente da `macbackup run`, anche se il Desktop è incluso. Ciascun punto deve essere vuoto e non può attraversare collegamenti simbolici; un `--mountpoint` alternativo non può sovrapporsi a una sorgente del backup. Il comando non esegue un backup e non applica gli elenchi di selezione ai file copiati manualmente. I tentativi di scrittura attraverso il montaggio sono bloccati da rclone; con NFS alcune applicazioni potrebbero non mostrare un errore evidente, quindi non usare il montaggio come cartella di lavoro. I file `.rclonelink` restano rappresentazioni dei collegamenti e gli snapshot delle icone Finder restano JSON; per ricrearli usare i comandi di ripristino.

Questa funzione è distinta dal trasferimento: il token Google mantiene i permessi OAuth già concessi per il backup. Il flag `--read-only` riguarda l'accesso attraverso questo montaggio. Riferimento: [documentazione ufficiale rclone nfsmount](https://rclone.org/commands/rclone_nfsmount/) e [combine](https://rclone.org/combine/) e [union](https://rclone.org/union/).

### 6.5 `status`: conoscere l'esito memorizzato

L'output è sempre JSON. La flag `--json` è accettata per compatibilità e non cambia il formato.

```sh
macbackup status
```

Mostra il resoconto dell'ultima run, con gli esiti per destinazione e area richieste in quella run. Per ogni fase distingue `selected` (elementi previsti), `transferred_files` (trasferimenti completati secondo rclone), `transferred_bytes` (byte contabilizzati da rclone nella fase), `checked_files` (verifiche di rclone) e `listed_items` (file e cartelle incontrati durante l'esplorazione, non il totale già presente nel cloud). `archive_deleted` conta le copie da archiviare per cancellazione locale; `archive_policy` conta quelle da archiviare per cambio di policy. `policy_archives` descrive ciascuno spostamento previsto con percorso, area originaria, nuova classificazione, motivo e regola attuale; `policy_archived` elenca gli spostamenti riusciti, con il percorso in `history`. In una run parziale i due elenchi possono avere lunghezze diverse. `renamed_files`, `server_side_moves` e `server_side_move_bytes` riportano gli spostamenti rilevati da rclone nella fase di sincronizzazione: con `--backup-dir` includono le copie precedenti spostate nello storico, ma non gli spostamenti per policy eseguiti successivamente con `moveto`. Non si sommano ai file caricati dal Mac. `counts_complete: true` indica statistiche finali ricevute dopo una fase riuscita. Dopo Ctrl+C, se rclone ha già emesso statistiche periodiche, mostra l'ultimo conteggio con `counts_complete: false`: può essere inferiore ai file effettivamente completati prima del segnale, e i byte possono includere parte del file interrotto. Se non è arrivato nessun rapporto, i valori sono `null` anziché zero. I testi JSON sono stampati in UTF-8 leggibile, senza sequenze `\u2019` per gli apostrofi. Il comando non conserva una vista separata dell’ultimo successo per ciascuna destinazione né la data di verifica. Lo stato locale memorizzato non certifica che il cloud sia raggiungibile in quel momento, che tutti gli storici siano integri o che una prova di recupero sia riuscita.

### 6.6 `versions`: trovare le copie di un file o di una directory

```sh
macbackup versions "/Users/example/Documents/tesi.docx" --target google
macbackup versions "/Users/example/.ssh/config" --target google --area private
macbackup versions ~/Documents/project --target google
macbackup versions ~/Documents/project --target google --files
```

Il comando legge `current` e tutti gli storici delle aree richieste, anche se il percorso è stato tolto dagli elenchi o il file locale non esiste più. `--target` è obbligatorio; `--area` vale `all` se omesso, perché la ricerca è soltanto in lettura. Per un file serve il percorso originale esatto; l'output mostra area, servizio, dimensione, data di modifica disponibile e identificativo di versione: `current` oppure l'ID della directory sotto `history`. La data di modifica non è la data di archiviazione.

Per una directory esistente sul Mac, basta il suo percorso (`~` viene espanso dalla shell). Se la directory locale non esiste più, aggiungere `/` in fondo al percorso assoluto per chiedere la ricerca ricorsiva. L'output normale mostra, per area e destinazione, un gruppo `current` con il numero di elementi attuali e un gruppo per ciascuna run che ha elementi storici sotto quella directory, con conteggio e byte. `--files` aggiunge percorsi originali, dimensioni e tipo (`files` o `macos-icons`) **solo per i gruppi `history`**; del gruppo `current` restano visibili conteggio e byte, senza l’elenco dei file attuali. `--json` restituisce gli stessi gruppi e i dettagli di ogni elemento, incluso il percorso remoto. `--files` è valido soltanto per una directory. La ricerca include sia plain sia private salvo `--area` esplicito: con una policy che cifra `.git`, gli oggetti Git compaiono sotto private e i file ordinari del progetto sotto plain.

Ogni `history/RUN_ID` contiene **soltanto gli elementi spostati in quella run**, non una fotografia completa della directory a quella data. Cambiare un file sul Mac non crea subito uno storico: serve una copia precedente già caricata e una successiva run che la sostituisca. `versions` non ripristina un'intera directory; `restore` continua a lavorare su un file alla volta.

Le destinazioni possono essere disabilitate in `settings.toml`, purché i rispettivi remote rclone esistano. Il comando non richiede lo stato locale di vecchie run: ricostruisce l'elenco dal cloud. `--json` restituisce anche il percorso remoto esatto per ciascuna copia e conserva i dettagli degli elementi `current`. La ricerca è circoscritta al percorso richiesto in `current` e in ogni directory `history/RUN_ID`; con molti storici può richiedere numerose richieste al provider. Non calcola hash né ID originali. `forget` esegue un proprio inventario e le proprie verifiche prima di qualsiasi rimozione.

### 6.7 `restore`: recuperare un singolo file

Dopo aver letto l'identificativo con `versions`, si sceglie esplicitamente una destinazione locale:

```sh
macbackup restore "/Users/example/Documents/tesi.docx" \
  --target google --area plain --version current \
  --to "/Users/example/Restore/tesi-recuperata.docx"
```

Per un collegamento, scegliere un percorso di prova diverso dall’originale e aggiungere `--links`:

```sh
macbackup restore "/Users/example/.zprofile" \
  --target google --area plain --version current \
  --to "/Users/example/Downloads/macbackup-restore/.zprofile" --links
```

La directory di destinazione deve già esistere. Il collegamento ricreato punta al percorso originale registrato; la destinazione va recuperata separatamente. Un collegamento assoluto può risultare non funzionante su un Mac con nome home diverso.

Per una vecchia versione si usa come valore di `--version` l'ID della relativa directory `history` mostrato da `versions`. Il comando richiede un solo servizio e una sola area. La directory di destinazione deve esistere e non attraversare collegamenti simbolici. Il programma rifiuta il percorso originale come destinazione e non sovrascrive un file già presente, salvo `--replace` esplicito; anche allora rifiuta una destinazione simbolica o non regolare. Scarica prima in un file temporaneo con permessi 600, verifica dimensione e, quando il backend espone hash utilizzabili, confronta gli hash. Rilegge l'inventario prima di rendere visibile il file recuperato. Se non è disponibile un hash, lo dichiara: dimensione e metadati non certificano da soli l'integrità del contenuto.

Un collegamento simbolico può essere recuperato con `restore --links`: senza il flag, il comando si ferma e non crea un normale `.rclonelink`. Scarica e controlla il piccolo file di destinazione, quindi ricrea un collegamento con il medesimo target, anche se assoluto o contenente `..`; non crea il file a cui il collegamento punta. Il ripristino del solo symlink in una cartella di prova non ricompone automaticamente i contenuti dei dotfiles. `--links` è rifiutato per file normali. Il comando non ripristina directory intere, permessi di directory, ACL, attributi macOS o date originali. Per una chiave `.ssh` il file recuperato ha permessi 600, ma bisogna preparare separatamente la directory di destinazione con permessi appropriati, normalmente 700. Le icone Finder seguono la procedura `restore-icon` descritta sopra. Un file scaricato dentro una sorgente ancora selezionata può essere incluso nella run successiva.

**Limite dello storico:** ogni directory `history/RUN_ID` contiene soltanto i file archiviati in quel tentativo. Il programma non promette il ripristino di un intero albero a una data arbitraria. Per offrirlo servono inventari completi e una ricostruzione collaudata, oppure uno strumento basato su snapshot.

### 6.8 `verify`: confrontare la selezione locale con `current`

```sh
macbackup verify --target google
macbackup verify --target google --size-only
macbackup verify --target google --area private --download
```

Il comando scansiona le sorgenti locali selezionate e confronta i file ammessi con `current` nel servizio richiesto. Non modifica sorgenti o cloud. La modalità ordinaria usa `rclone check` per l'area normale e `rclone cryptcheck` per l'area cifrata; entrambe richiedono una corrispondenza completa nel rapporto di rclone. `--download` usa `rclone check --download` e legge il contenuto remoto per confrontarlo con quello locale: può generare molto traffico e richiedere molto tempo. Per la cartella normale Google rclone usa gli hash comuni quando disponibili; la verifica cifrata usa il metodo apposito di cryptcheck. La verifica comprende anche gli snapshot correnti delle icone Finder che macbackup genera dalle sorgenti selezionate.

`--size-only` legge una volta l'inventario di `current` per area e confronta percorsi e dimensioni locali, anche per l'area privata. Non legge né confronta il contenuto dei file e quindi non dimostra che i byte siano identici. La durata dipende comunque dalla scansione locale e dalla lettura dell'inventario del servizio. Non si combina con `--download`. La verifica completa dell'area privata richiede di leggere i file locali e cifrarli nuovamente per confrontare gli hash; su molte migliaia di file può durare ore. `Ctrl-C` interrompe il comando con codice 130 senza traceback; una verifica interrotta non produce un risultato completo.

Il risultato separa file corrispondenti, diversi, mancanti e errori di lettura per servizio, area e tipo. Una differenza fra `current` e il file locale attuale **non prova** che il backup sia corrotto: il file potrebbe essere stato modificato dopo la copia. Il comando non verifica gli storici, le copie conservate dopo un'esclusione, l'intero insieme dei metadati macOS o le revisioni native del provider. Senza un manifesto dei contenuti registrato al momento della run, non certifica il contenuto di un vecchio file confrontandolo con l'originale attuale. Le destinazioni possono essere disabilitate in `settings.toml`, purché i remote rclone esistano.

### 6.9 `forget`: rimuovere copie conservate

`forget` usa due passaggi. Il primo legge il cloud e crea soltanto un piano; il secondo applica quel piano dopo una nuova verifica. Area, destinazione e modalità sono sempre esplicite. Per un file si indica il percorso originale esatto; per una directory si aggiunge `/` finale, anche se la directory locale non esiste più:

```sh
macbackup forget "/Users/example/Desktop/old-project/" \
  --area plain --target google --mode trash
```

Per rimuovere anche gli storici plain di un file diventato privato, si può creare un piano Google con `--mode permanent` al posto di `trash`, dopo aver controllato il percorso e il piano stampato:

```sh
macbackup forget "/Users/example/Desktop/progetto/segreto.txt" \
  --area plain --target google --mode permanent
```

Questo esempio non applica ancora la rimozione: soltanto il successivo `forget --plan ID --apply` usa il piano. `--area private` cerca invece la copia cifrata; `--area all` cerca entrambe.

Il piano elenca ogni file corrispondente in `current` e in tutte le directory sotto `history`, con area, servizio, posizione, numero e byte noti. Per una directory comprende anche gli snapshot `macos-icons` della cartella e dei discendenti e le radici di directory esistenti da ripulire. Il confronto usa i confini dei percorsi: `old-project/` non comprende `old-project-other/`. La ricerca non applica le regole di selezione correnti, così trova anche copie caricate prima di una nuova esclusione o classificazione privata. Le destinazioni possono essere disabilitate in `settings.toml`, purché i relativi remote rclone siano configurati. Un piano di oltre 10.000 file viene rifiutato: restringere il percorso e creare più piani.

Se non ci sono file né directory corrispondenti non viene creato un piano. Per una directory rimasta vuota può invece essere creato un piano con zero file. Altrimenti macbackup genera un ID casuale e salva il piano in un file locale con permessi 600, sotto `~/.local/state/macbackup/forget-plans`. Il piano scade dopo un'ora e si usa una sola volta. L'output mostra il comando preciso per applicarlo:

```sh
macbackup forget --plan F0123456789ab --apply
```

Prima dell'applicazione macbackup rilegge gli inventari e confronta l'insieme completo delle corrispondenze, i percorsi remoti, le dimensioni, gli orari, gli ID e gli hash restituiti dal backend. Se una copia cambia o ne appare un'altra, blocca l'intero piano. Alcuni backend non espongono hash del contenuto: modifiche dello stesso file con identica dimensione e identico orario potrebbero non essere rilevate. Per questo il piano scade e non va usato mentre altri client modificano il backup.

L'applicazione rimuove i file uno alla volta, mostrando nel terminale il numero già elaborato. Poi rilegge l'inventario. Per un percorso di directory rimuove anche le directory rimaste vuote sotto le radici esatte indicate nel piano, sia in `current` sia nelle versioni di `history` trovate; non risale sopra il percorso richiesto. In caso di errore o `Ctrl-C` può esserci un risultato parziale, registrato sotto lo stesso ID; si crea un nuovo piano per gli elementi rimasti, anche quando restano soltanto directory vuote. Il comando non modifica sorgenti locali né elenchi. Se il percorso è ancora incluso, una successiva `run` potrebbe caricarlo nuovamente: prima si cambia la classificazione e poi si usa `forget`.

`--area plain` permette per esempio di rimuovere le vecchie copie consultabili dopo aver spostato un file nell'area privata. `--area all` cerca entrambe le aree. `--target all` richiede che siano configurati entrambi i servizi; non assume che una destinazione disabilitata sia assente.

### 6.10 Cestino, rimozione definitiva e revisioni del provider

`--mode trash` rimuove le copie individuate dalle cartelle del backup e le manda nel cestino del servizio. Non significa eliminazione definitiva e può non liberare spazio.

`--mode permanent` è accettato soltanto per `--target google` quando il remote normale è davvero di tipo Google Drive. Non può essere combinato con `--target all`; una capacità non supportata viene rifiutata prima della rimozione.

Su Google rclone supporta la cancellazione permanente dei file individuati tramite `--drive-use-trash=false`. L'ispezione di revisioni native e di copie già presenti nel cestino è distinta dall'ispezione delle nostre cartelle: non va dichiarata completa senza una funzionalità dedicata e verificata. Rimuovere un percorso non individua automaticamente duplicati con un altro nome o in altre cartelle.

macbackup rifiuta `permanent` su Proton: il backend rclone non espone una cancellazione definitiva selettiva equivalente a quella usata per Google. La rimozione definitiva selettiva di elementi già nel cestino Proton resta manuale; macbackup non fornisce ancora una mappa verificata dei nomi cifrati nel cestino.

Il risultato distingue la rimozione dalle cartelle attive e la modalità richiesta. `trash` lascia le copie recuperabili nel cestino del servizio; `permanent` chiede al provider Google la cancellazione definitiva dei file attivi selezionati. Il programma non certifica l’assenza di copie precedentemente nel cestino, revisioni native di Drive o duplicati con altri nomi.

### 6.11 Autocompletamento Zsh

Nei dotfiles sono presenti `home/.zsh/completions/_macbackup` e `home/.zsh/integrations/macbackup.zsh`. L'integrazione propone comandi, flag, valori di `--target` e `--area`, e percorsi. Se la shell è già aperta dopo un aggiornamento, aprire un nuovo terminale oppure ricaricare l'integrazione:

```sh
source "$HOME/.zsh/integrations/macbackup.zsh"
```

Il completamento non esegue `macbackup` o rclone e non accede al cloud. Le descrizioni sono compatte e colorate solo se il terminale lo consente. Quando si aggiungono flag al parser, aggiornare anche il completamento e i relativi test.

## 7. Se un controllo o una run fallisce

Un errore non equivale a una cancellazione riuscita. Leggere il messaggio della fase, poi `macbackup status` se era una `run`: il resoconto distingue destinazioni, aree e trasferimenti completati o soltanto stimati dall'ultimo rapporto. Correggere la causa e ripetere `check` e `preview --target` prima di una nuova `run`. Le copie già completate vengono confrontate alla nuova esecuzione; un file interrotto durante il caricamento riparte dall'inizio.

| Segnale | Controllo utile |
|---|---|
| Sorgente elencata direttamente ma mancante o illeggibile | Controllare percorso, permessi e dischi esterni; correggere l'elenco solo se la rimozione era voluta. La run non deve trattarla come cancellazione. |
| `max_delete` superato | Leggere il piano con `preview --target`; correggere eventuali esclusioni o percorsi errati. Aumentare il limite in `settings.toml` solo dopo aver verificato ogni archiviazione prevista. |
| Conflitto tra `plain/current` e `private/current`, o duplicati remoti | Usare `check --remote` e ispezionare i percorsi segnalati. Non montare la vista unificata o avviare una nuova run finché il conflitto non è risolto. |
| Errore OAuth o credenziali non valide | Verificare il remote con rclone e riconnetterlo se necessario; ripetere `check --remote`. Un successo passato di `status` non prova che il token sia ancora valido. |
| `verify` segnala differenze | Controllare se i file locali sono cambiati dopo il backup; `--size-only` confronta solo nomi e dimensioni, la verifica ordinaria legge più dati. |
| `Ctrl-C` durante `run` o `verify` | Il risultato è parziale. `status` conserva il rapporto dell'ultima `run`; una verifica interrotta non certifica nulla. |

Per provare il recupero senza toccare l'originale, cercare un file non sensibile con `versions`, usare `restore --to` in una directory di prova già esistente e aprire il file recuperato. Ripetere la prova anche per l'area privata, conservando le chiavi crypt fuori dal Mac. Questa prova è più forte di un controllo dei soli nomi, ma riguarda solo gli elementi effettivamente recuperati.

## 8. Sicurezza operativa e recuperabilità

Macbackup controlla le sorgenti prima di archiviare le copie mancanti e blocca le operazioni remote concorrenti tramite un lock locale. Un errore di lettura non viene forzato con `--ignore-errors`; un problema del remote crypt non provoca un caricamento alternativo in plain. Lo stato operativo standard è escluso dalla selezione, per non caricare piani `forget` o registri e per non creare ricorsioni. La protezione vale per i percorsi configurati: usare un altro strumento per trascinare file direttamente sul cloud aggira queste regole.

Conservare fuori dal Mac, in forma protetta, la configurazione e le chiavi necessarie a ricreare i remotes crypt. Proteggere anche le directory locali usate per lo stato e per i recuperi. I log non contengono i contenuti dei file, ma percorsi, regole e resoconti possono rivelare informazioni: non pubblicarli senza revisarli.

I file cloud sono copie. Modifiche o cancellazioni fatte dal telefono non modificano il Mac e possono essere sovrascritte o ricreate dalla run successiva. Il backup non è immutabile: chi ottiene accesso allo stesso account potrebbe compromettere anche le copie remote.

## 9. Fonti ufficiali

Riferimenti per i comportamenti di rclone e dei provider:

- [Rclone: filtri e files-from](https://rclone.org/filtering/)
- [Rclone: sync](https://rclone.org/commands/rclone_sync/)
- [Rclone: backup-dir](https://rclone.org/docs/#backup-dir-string)
- [Rclone: crypt e protezione della configurazione](https://rclone.org/crypt/)
- [Rclone: Google Drive, revisioni e cestino](https://rclone.org/drive/)
- [Rclone: Proton Drive e limitazioni](https://rclone.org/protondrive/)
- [Rclone: delete e filtri](https://rclone.org/commands/rclone_delete/)
- [Rclone: purge ignora i filtri](https://rclone.org/commands/rclone_purge/)
- [Rclone: collegamenti simbolici](https://rclone.org/local/#symlinks-junction-points)
- [Rclone: cryptcheck](https://rclone.org/commands/rclone_cryptcheck/)
- [Google: gestione delle revisioni native](https://developers.google.com/workspace/drive/api/guides/manage-revisions)
- [Proton: eliminazione selettiva dal cestino nell'app](https://proton.me/support/proton-drive-mobile-manage-files-folders)
- [Proton: cancellazione e recupero di file sincronizzati](https://proton.me/support/proton-drive-delete-restore-synced-files)
- [Zsh: sistema di completamento, fpath, compinit e compdef](https://zsh.sourceforge.io/Doc/Release/Completion-System.html)
