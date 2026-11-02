# macbackup: guida operativa e progetto del backup

Documento aggiornato il 2 novembre 2026.

**Stato: versione 0.9.5.** Sono disponibili `init`, `check`, `explain`, `layout`, `preview --local`, `check --remote`, `preview --target`, `run --target`, `status`, `restore-icon`, `forget`, `versions`, `restore` per un file e `verify` della copia corrente. Le funzioni remote usano rclone, comprese cifratura e archiviazione delle vecchie versioni. Le destinazioni sono disabilitate nella configurazione iniziale. Non sono ancora disponibili il ripristino di interi alberi e il montaggio del disco. `restore-icon` recupera soltanto un'icona da un file locale.

È disponibile anche il completamento nativo per Zsh di comandi, opzioni e percorsi, integrato nei dotfiles.

Il trasferimento è stato collaudato con veri comandi rclone su remotes locali e crypt sintetici, e poi su Google Drive con soli file fittizi in cartelle di test separate. Su Google sono riusciti copia consultabile, recupero del file cifrato, esclusione del file non autorizzato e recupero di una versione storica cifrata. Il primo backup reale Google è stato avviato e poi interrotto su richiesta dell’utente: non è completo. Proton non è ancora configurato. Alla verifica immediatamente successiva risultavano 216 file plain per 429.002.179 byte e nessun file nell’area private. `status` non registrava una run conclusa. Le sezioni indicate come future non sono funzionalità già presenti.

## Avvio della versione locale

Tutti i comandi richiedono Python 3.11 o successivo, senza pacchetti aggiuntivi. Sul Mac è stato verificato Python 3.14.0 in `/opt/homebrew/bin/python3`. Il file eseguibile usa `python3` disponibile nel PATH; le future automazioni richiederanno una configurazione esplicita dell'interprete.

```sh
macbackup --version
macbackup --help
macbackup init
```

`init` crea quattro elenchi e `settings.toml`: i tre elenchi di percorsi sono vuoti salvo esempi commentati, mentre explicit-only contiene `.env` e `.env.*`; entrambe le destinazioni sono disabilitate. Non sovrascrive una configurazione esistente, nemmeno parziale. I file nuovi hanno permessi 600 e la nuova directory 700. Se l'inizializzazione è già stata eseguita, non serve ripeterla: l'aggiornamento alla versione 0.2 aggiunge il solo settings.toml se assente, senza cambiare gli elenchi.

Per modificare gli elenchi si usa il proprio editor, quindi:

```sh
macbackup check
macbackup explain "/Users/kevinmuka/Desktop/progetto/.env"
macbackup layout  # nella cartella del progetto
macbackup layout "/Users/kevinmuka/Desktop/progetto"
macbackup preview --local
```

`check` scansiona le sorgenti selezionate usando nomi e metadati; non legge il contenuto dei file da salvare. Legge invece il contenuto dei quattro elenchi di configurazione. `explain` controlla un solo percorso, anche ipotetico o attualmente assente; non certifica che l'intera selezione sia valida. Per esempio, se nessuna directory è ancora inclusa, un `.env` può risultare semplicemente «non selezionato».

`preview --local` mostra le classificazioni locali e i motivi degli scarti. Non confronta il cloud e non stima quanti byte sarà necessario trasferire. Se trova errori, non presenta la scansione parziale come un piano utilizzabile. Per le directory escluse mostra una voce relativa al sottoalbero senza visitarne tutti i file: il numero delle voci saltate non è un conteggio esatto di tutti i file esclusi.

`layout` usa la directory corrente se non gli passi un percorso; per esempio, dentro `~/Desktop/project` può mostrare `PRIVATE /Users/kevinmuka/Desktop/project/.git`. Richiede una directory locale selezionata in `plain` e mostra le parti al suo interno che sono instradate in `private`. Per ciascuna mostra soltanto la radice del sottoalbero, il numero di elementi selezionati e i byte locali; non elenca i nomi di ogni file privato. Con `--json` aggiunge il percorso logico `private/current/...` e si può usare in altri strumenti. Esegue una scansione locale completa, senza accesso al cloud. Non mostra vecchie copie in chiaro o nello storico, né directory private vuote, che il backup non conserva come oggetti autonomi. Se la scansione trova errori, non mostra un risultato parziale come valido.

I quattro comandi di lettura supportano `--json`. `--config-dir` sostituisce `~/.config/macbackup` per i quattro elenchi e `settings.toml`; non cambia le sorgenti dei dati, il file di stato sotto `~/.local/state/macbackup` o la configurazione delle credenziali rclone. La directory alternativa si specifica prima del sottocomando:

```sh
macbackup --config-dir "/percorso/assoluto/configurazione" check --json
```

Codici di uscita: 0 per il completamento del controllo richiesto, 1 per errori rilevati nelle sorgenti o conflitti, 2 per errori di sintassi, configurazione o utilizzo. Un controllo con elenchi vuoti restituisce 0 con un avviso: non è un backup eseguito.

I collegamenti simbolici vengono identificati come elementi da conservare, senza attraversarne le directory di destinazione. I file speciali scoperti durante la scansione vengono saltati con avviso; se selezionati come sorgenti esatte producono errore. La scansione blocca conflitti di identità fra file normali e privati, e alias osservati di file protetti che ne aggirerebbero l'inclusione esatta. Non riconosce copie indipendenti del medesimo contenuto.

Il selettore protegge le posizioni standard della configurazione rclone, anche quando collegate a un percorso reale diverso, e lo stato operativo standard di macbackup. L'uso di un percorso rclone personalizzato richiede di includerlo esplicitamente nelle protezioni: non è ancora rilevato automaticamente dal selettore. Il controllo dell'identità attesa dei volumi esterni non è implementato; attualmente una sorgente mancante produce errore, ma un mount errato non è certificato.

Per eseguire i test dal repository dotfiles, senza creare cache Python:

```sh
python3 -B -m unittest discover -s /Users/kevinmuka/.dotfiles/tests -p 'test_macbackup*.py' -v
```

## Configurazione dei trasferimenti

`/Users/kevinmuka/.config/macbackup/settings.toml` non contiene password:

```toml
schema_version = 1
max_delete = 25

[policy]
private_directory_names = [".git"]
ignored_file_names = [".DS_Store", " ← ", ".localized"]

[targets.google]
enabled = true
plain = "gdrive:MacBackup/plain"
private = "gdrive-private:"

[targets.proton]
enabled = false
plain = "pdrive:MacBackup/plain"
private = "pdrive-private:"
```

Il remote gdrive deve essere di tipo drive e usare il tuo client OAuth. Per il backup dedicato si usa lo scope drive.file: i file già esistenti e creati da altre app non saranno automaticamente accessibili. Il remote gdrive-private deve essere di tipo crypt e avvolgere `gdrive:MacBackup/private`, con cifratura standard dei nomi e delle directory. Conservare password ed eventuale salt anche nel gestore di password, recuperabile senza questo Mac.

### Cosa rappresentano gdrive e gdrive-private

I due nomi sono due modi di accedere allo stesso account Google: non sono due servizi o due copie indipendenti. `gdrive:` è il collegamento a Drive; non punta intrinsecamente alla cartella plain. È macbackup, attraverso settings.toml, a scegliere `gdrive:MacBackup/plain` come destinazione dei file consultabili. `gdrive-private:` applica invece la cifratura rclone alla cartella fisica `gdrive:MacBackup/private`.

| Percorso usato da macbackup | Posizione su Google Drive | Cosa si vede dal telefono o dal sito |
| --- | --- | --- |
| `gdrive:MacBackup/plain/current` | `My Drive/MacBackup/plain/current` | File consultabili con percorsi originali sotto `Users/...` |
| `gdrive:MacBackup/plain/history/RUN_ID` | `My Drive/MacBackup/plain/history/RUN_ID` | Vecchie versioni consultabili, organizzate per esecuzione |
| `gdrive-private:current` | Dentro `My Drive/MacBackup/private` | Nomi e contenuti cifrati; anche il nome current è cifrato |
| `gdrive-private:history/RUN_ID` | Dentro `My Drive/MacBackup/private` | Vecchie versioni cifrate, con nomi delle directory cifrati |
| `gdrive:MacBackup/plain/macos-icons/current` | `My Drive/MacBackup/plain/macos-icons/current` | File icon.json con i dati necessari al recupero delle icone su Mac |
| `gdrive-private:macos-icons/current` | Dentro `My Drive/MacBackup/private` | Gli stessi dati delle icone per le cartelle private, cifrati |

La cartella esterna `private` mantiene questo nome leggibile; la cifratura si applica a ciò che viene scritto attraverso il remote crypt al suo interno. Usare direttamente `gdrive:MacBackup/private/...` per un caricamento aggirerebbe la cifratura: per i dati privati va sempre usato `gdrive-private:`. Nell'app Google Drive sul telefono si possono aprire i file plain supportati dall'app; i file private richiedono un client compatibile con rclone crypt e le chiavi corrette.

Entrambe le aree consumano lo stesso spazio Google. La futura copia su Proton richiederà collegamenti separati, `pdrive` e `pdrive-private`, e sarà una seconda destinazione indipendente.

Per Proton Pass, la voce di recupero suggerita si chiama `MacBackup — Google Drive — Crypt key`. Crearla come elemento personalizzato tramite Altro → Inizia da zero. I campi `Encryption password` e `Salt / password2` sono nascosti e contengono le due stringhe originali generate da rclone, non il loro offuscamento nella configurazione. I campi testuali sono `Remote name = gdrive-private`, `Storage path = gdrive:MacBackup/private`, `Filename encryption = standard` e `Directory name encryption = true`. Conservare separatamente Client ID e Client secret nella voce `MacBackup — Google OAuth`; il secondo è un campo nascosto. Non servono codici TOTP per rappresentare queste due password statiche.

Abilitare una destinazione solo dopo aver configurato i due remotes, rivisto gli elenchi e completato la prova di recupero con file sintetici. Le operazioni di esempio successive diventano eseguibili dopo quell'abilitazione. `--target all` richiede entrambe le destinazioni abilitate: non salta silenziosamente Proton se manca.

```sh
macbackup check --remote --target google
macbackup preview --target google
macbackup run --target google
macbackup status
```

`check --remote` legge gli inventari e controlla tipi e capacità necessari; non scrive sul cloud e non prova un recupero. `preview --target` legge anche i contenuti locali necessari ai confronti di integrità ed esegue il dry-run di rclone: non modifica il cloud. Mostra quanti file sono selezionati e quanti verrebbero archiviati perché cancellati; non mostra ancora un elenco completo di tutte le sostituzioni.

`run` trasferisce soltanto i percorsi ammessi, conserva le copie sostituite o cancellate sotto history/RUN_ID e registra gli esiti distinti delle aree. Non esegue pulizie dello storico. `max_delete` è il limite di archiviazioni dovute a cancellazioni per area e per destinazione: viene controllato prima dei trasferimenti e passato anche a rclone. Il valore iniziale 25 va rivisto prima dell'automazione; non è una politica di conservazione.

Un percorso incluso singolarmente deve esistere: se manca una sorgente obbligatoria, la run si ferma prima dei trasferimenti. L'archiviazione automatica per cancellazione riguarda invece i file mancanti dentro una cartella selezionata che esiste ancora. Per esempio, cancellare `.ssh/config` può archiviarne la copia se `.ssh` è selezionata ed esiste; la scomparsa dell'intera `.ssh` blocca il backup. Togliere una voce dagli elenchi interrompe la gestione futura di quella voce e conserva le copie cloud.

Le operazioni remote condividono un blocco locale per impedire esecuzioni contemporanee. Gli elenchi temporanei e lo stato sono protetti e rimangono fuori dal repository. Non sono conservati contenuti dei file nei registri. `status` descrive l'ultima run richiesta, anche parziale: non certifica ogni destinazione da sempre, non verifica la raggiungibilità attuale e non implica un controllo completo dello storico. Durante `run`, rclone mostra nel terminale l’avanzamento della fase in corso; `status` si aggiorna soltanto al termine della run. Un’interruzione durante la fase di pianificazione può ancora non produrre un nuovo stato.

Nelle aree normali si richiedono hash disponibili sul backend. Per le aree crypt il confronto viene effettuato con cryptcheck: in questo modo una modifica di contenuto della stessa dimensione e con lo stesso orario non viene persa. Vengono trasferiti e archiviati soltanto i file privati nuovi, diversi o da rimuovere da current; una run senza modifiche non deve generare nuove copie storiche. Se il confronto cifrato non è completo, l'operazione sull'area viene bloccata.

Il trasferimento salva file, rappresentazioni dei collegamenti e dati delle icone Finder nelle aree dedicate. Non conserva ancora le directory vuote prive di icone o l'intero insieme dei metadati macOS: ACL, attributi estesi e resource fork degli altri file non sono coperti da questa funzione. Non attivare ancora un backup reale di database aperti senza una procedura di esportazione o chiusura appropriata.

### Icone personalizzate delle cartelle macOS

La scelta concordata è conservare le icone, senza escludere i file `Icon\r`. In questo nome `\r` indica un vero carattere di ritorno carrello. Il selettore riconosce questo caso specifico; gli altri nomi con caratteri di controllo rimangono bloccati.

Il contenuto ordinario di Icon\r può essere vuoto: l'immagine spesso risiede nel resource fork. Per ogni icona selezionata viene quindi generato un piccolo snapshot JSON che contiene i dati del file, gli attributi `com.apple.ResourceFork` e `com.apple.FinderInfo` del file e il FinderInfo della cartella. Il percorso sorgente compare nel JSON soltanto come informazione, senza essere usato come destinazione dal comando di recupero. Non vengono letti o impacchettati gli altri documenti della cartella: un .env non autorizzato resta escluso.

Le icone vengono recuperate su macOS; l'app Google Drive sul telefono usa la propria presentazione delle cartelle. Una prova con un'icona valida generata tramite AppKit ha confrontato l'immagine renderizzata prima e dopo il recupero, trovandole uguali. Non è stata effettuata una verifica visiva dentro una finestra Finder.

Uno snapshot per la cartella `/Users/kevinmuka/Desktop/Photography` viene salvato in `plain/macos-icons/current/Users/kevinmuka/Desktop/Photography/icon.json`. Le versioni precedenti stanno in `plain/macos-icons/history/RUN_ID/.../icon.json`. Per una cartella privata la stessa struttura è sotto il remote crypt, quindi anche i dati delle icone sono cifrati.

Gli snapshot seguono inclusioni ed esclusioni come i file ordinari. Una nuova esclusione conserva la copia remota esistente. La rimozione locale di un'icona dentro una cartella ancora selezionata archivia la vecchia copia; un'icona invariata non deve creare nuove versioni storiche. Il limite max_delete comprende file e snapshot delle icone per ciascuna area. Gli snapshot temporanei sono nella directory di stato protetta e vengono rimossi alla fine dell'operazione. Un file o un singolo attributo icona oltre 64 MiB blocca la relativa area con errore, senza ometterlo silenziosamente.

`check` conta le icone usando i soli nomi e metadati ordinari; non legge il resource fork. La lettura dei contenuti necessari avviene durante l'anteprima remota o il trasferimento. La stima dei byte della scansione locale non include i resource fork né l'aumento di dimensione dovuto alla codifica JSON.

Per provare un recupero, dopo il primo caricamento scaricare uno snapshot e applicarlo a una cartella di prova esistente. Esempio per una normale cartella:

```sh
mkdir -p "$HOME/Downloads/macbackup-restore/Photography"
rclone copyto \
  "gdrive:MacBackup/plain/macos-icons/current/Users/kevinmuka/Desktop/Photography/icon.json" \
  "$HOME/Downloads/macbackup-restore/icon.json"
macbackup restore-icon \
  --file "$HOME/Downloads/macbackup-restore/icon.json" \
  --folder "$HOME/Downloads/macbackup-restore/Photography"
```

Per le icone private il download si effettua da `gdrive-private:macos-icons/current/.../icon.json`. Il comando restore-icon non accede al cloud, non legge gli elenchi e non scrive nel percorso sorgente registrato nello snapshot. La destinazione è soltanto la cartella indicata con --folder, che deve esistere e non essere un collegamento simbolico. Ripristina il file Icon\r e il bit Finder che attiva l'icona personalizzata, preservando gli altri indicatori Finder della cartella. I documenti della cartella restano intatti.

Se un'icona è già presente, il comando si ferma. Per sostituire esplicitamente soltanto quell'icona si aggiunge `--replace`. Il comando supporta --json e l'autocompletamento di tutte le opzioni. Come le altre operazioni su filesystem, il recupero non promette una transazione atomica tra file e metadati: un errore durante l'applicazione dei metadati va controllato e può richiedere di ripetere con --replace.

## Accesso Google e problemi OAuth

La configurazione Google si effettua nel proprio terminale con `rclone config`, inserendo Client ID e Client secret. Non condividere il riepilogo: può contenere token. Il client deve essere Desktop app, il remote si chiama gdrive e lo scope è drive.file. Un errore «client_secret is missing» richiede di modificare il remote e compilare il campo Client secret, non di ricreare il progetto Google.

Se l'app è in Testing, il proprio account deve essere aggiunto in Google Auth Platform → Audience → Test users. Per un backup automatico duraturo occorre poi risolvere il limite di scadenza settimanale degli accessi delle app in Testing, valutando il passaggio a Production per uso personale; non è una modifica automatica eseguita dallo script. Nella schermata Audience mostrata il 30 ottobre lo stato era ancora Testing: il messaggio Google ha confermato che per Production servono un nome valido, email di supporto, homepage e privacy policy. I primi due erano già presenti; occorrono due URL reali e pubblici, senza inventare indirizzi né ampliare le autorizzazioni Drive. Logo e termini di servizio non sono stati richiesti da quel messaggio. Riferimenti: [configurazione del consenso](https://developers.google.com/workspace/guides/configure-oauth-consent), [scadenza dei refresh token in Testing](https://developers.google.com/identity/protocols/oauth2#expiration), [passaggio a Production nella guida rclone](https://rclone.org/drive/#making-your-own-client-id).

### Pagine pubbliche per il consenso Google

Con l'autorizzazione dell'utente è stato creato direttamente su GitHub il branch [gh-pages di kevinmuka/dotfiles](https://github.com/kevinmuka/dotfiles/tree/gh-pages). GitHub Pages pubblica quel branch dalla sua radice. Il sito è stato verificato con risposte HTTP 200 e confronto dei contenuti pubblici con i file preparati. Il branch contiene soltanto cinque file statici:

```text
index.html
macbackup/index.html
macbackup/privacy.html
macbackup/style.css
.nojekyll
```

La radice [kevinmuka.github.io/dotfiles/](https://kevinmuka.github.io/dotfiles/) può essere usata in futuro per documentare altri strumenti dei dotfiles. La sezione macbackup mantiene URL distinti e stabili:

| Campo in Google Auth Platform → Branding | Valore |
| --- | --- |
| Application home page | `https://kevinmuka.github.io/dotfiles/macbackup/` |
| Application privacy policy link | `https://kevinmuka.github.io/dotfiles/macbackup/privacy.html` |
| Authorised domains | `kevinmuka.github.io` |

Dopo il salvataggio si torna in Audience → Publish app. Se si cambiano gli URL in futuro, bisogna aggiornare Branding; se cambia il dominio, anche Authorised domains. Il passaggio a Production riguarda la disponibilità del client OAuth e il limite di Testing: non condivide le cartelle del backup e non pubblica token o chiavi.

Il branch è stato creato sul remoto tramite API, senza cambiare il checkout locale `/Users/kevinmuka/.dotfiles` e senza pubblicare le modifiche locali del programma su main. Un branch è una versione del repository, non una nuova directory sul Mac. Per vederne il riferimento nella copia locale si può eseguire `git -C /Users/kevinmuka/.dotfiles fetch origin`; questo non cambia il branch attualmente aperto. Per modificare gh-pages sul Mac è opportuno usare una copia o un worktree separato: cambiare branch nel checkout che alimenta i collegamenti dei dotfiles cambierebbe anche quelle configurazioni attive. Le pagine pubbliche includono l'email di supporto concordata, non la configurazione del backup.

Dopo aver confermato lo stato In production, occorre ricollegare il remote nel proprio terminale con `rclone config reconnect gdrive:` per ottenere una nuova autorizzazione nel nuovo stato. Client ID, Client secret e chiavi crypt rimangono quelli configurati; non vanno rigenerati. L'utente ha confermato di aver pubblicato l'app e ripetuto la riconnessione. Subito dopo `rclone about gdrive:` e `macbackup check --remote --target google` sono riusciti in sola lettura. Questi controlli verificano l'accesso, non leggono lo stato di pubblicazione da Google Auth Platform.

Il 30 ottobre 2026 la lettura della quota del remote gdrive è riuscita con scope drive.file; la configurazione locale risultava protetta con permessi 600. Questa prova non ha elencato o scaricato i file dell'account.

È poi stata completata una prova end-to-end nello stesso account, limitata a file sintetici sotto namespace connection-tests distinti dai percorsi del backup reale. Sono state verificate anche modifiche della stessa dimensione con lo stesso orario, in entrambe le aree. I namespace della prova 0.2 sono stati rimossi dall'area attiva di Drive; il cestino non è stato svuotato. Non è stata eseguita alcuna cancellazione dei tuoi file. Il resoconto operativo è conservato fuori dal repository. Prima del primo backup reale rimangono da completare la revisione dell’anteprima e l’abilitazione della destinazione Google. Proton resta da configurare per la seconda copia.

Il collaudo Google della versione 0.3 ha inoltre recuperato le icone plain e cifrate, conservato i file dopo una nuova esclusione e archiviato file e icone rimossi da cartelle ancora selezionate. È stato verificato anche il blocco per una sorgente esatta mancante. La suite locale comprende 122 test riusciti, oltre alla prova di resa dell'icona tramite AppKit. Nella pulizia 0.3 i file sintetici sono stati spostati nel cestino; la rimozione di alcune cartelle residue ha nuovamente restituito errori, registrati separatamente dal buon esito del backup. Il resoconto di pulizia è fuori dal repository e non viene confuso con l'esito delle prove di recupero.

Dopo il consenso esplicito dell'utente, la pulizia dei due namespace 0.3 autorizzati è stata completata eliminando i singoli elementi dal basso verso l'alto tramite i loro ID Google Drive. Prima della rimozione sono stati verificati tutti i discendenti, compresi quelli nel cestino: 155 elementi totali, con nove file di test, tutti posseduti dall'account e autorizzati all'app. I due ID radice sono stati poi verificati assenti e le cartelle di test rimaste vuote sono state rimosse. Lo scope è rimasto drive.file e il cestino complessivo non è stato svuotato; le vecchie prove 0.2 già nel cestino non rientravano in questa autorizzazione definitiva. Sono stati rimossi anche i fixture locali sintetici. Questa pulizia mirata precedeva l’implementazione generale del comando forget e non ne era una prova.

### Permessi di cancellazione e limite osservato

`drive.file` è un permesso di lettura e scrittura per i file autorizzati all'applicazione, non un permesso di sola lettura. Una prova separata, su nuove cartelle sintetiche sia plain sia crypt, ha verificato con successo: creazione e rimozione di una cartella vuota; spostamento nel cestino di un albero contenente un file; rimozione del file seguita dalla rimozione delle cartelle rimaste vuote. Lo scope completo `drive` non è stato richiesto.

La pulizia delle vecchie cartelle di prova ha inizialmente restituito `403 appNotAuthorizedToChild` per alcuni alberi profondi. Il controllo dei metadati dell'area normale ha trovato `isAppAuthorized=true` in tutti gli elementi visibili, inclusi i discendenti già nel cestino. I controlli finali hanno poi confermato l'assenza di entrambi i namespace di prova dall'area attiva. La causa esatta dei rifiuti intermedi non è stata isolata; non considerare il successo finale come una garanzia di cancellazione di qualsiasi albero. Non è stato necessario richiedere lo scope completo.

Con le impostazioni usate nelle prime prove, rclone spostava gli elementi nel cestino Google; non era una cancellazione definitiva e il cestino dell’account non veniva svuotato. La versione 0.4 di `forget` distingue `trash` da `permanent` e cerca anche le copie storiche del backup; non esplora automaticamente revisioni native o elementi già nel cestino.

Il montaggio in sola lettura, quando verrà aggiunto, impedirà modifiche attraverso quel montaggio. Non cambierà i permessi OAuth usati dai comandi di backup. Passare allo scope completo `drive` autorizzerebbe l'accesso a tutti i file di Drive: impostare MacBackup come cartella radice di rclone non limiterebbe il token Google a quella cartella.

Riferimenti: [scope di rclone](https://rclone.org/drive/#scopes), [cestino e cancellazione Google Drive](https://developers.google.com/workspace/drive/api/guides/delete), [metadati isAppAuthorized](https://developers.google.com/workspace/drive/api/reference/rest/v3/files).

## Autocompletamento Zsh

L'integrazione è caricata automaticamente dal normale avvio di Zsh nei tuoi dotfiles. Dopo l'installazione apri un nuovo terminale; per attivarla anche in un terminale già aperto, dove il completamento Zsh è già inizializzato:

```sh
source "$HOME/.zsh/integrations/macbackup.zsh"
```

Esempi di ciò che puoi digitare prima di premere il tasto Tab:

```text
macbackup ch                          → macbackup check
macbackup check --j                   → macbackup check --json
macbackup lay                         → macbackup layout
macbackup preview --lo                → macbackup preview --local
macbackup run --progress-d            → macbackup run --progress-depth=
macbackup restore --lin               → macbackup restore --links
macbackup --conf                      → macbackup --config-dir=…
macbackup explain /Users/kevinmuka/…   → completa file e directory
```

Il completamento è contestuale: `--config-dir` viene proposto prima del sottocomando; `--local` soltanto per preview; `--target` per i comandi remoti pertinenti. Completa anche i valori google, proton e all dove ammessi, le opzioni di `forget`, `--links` per `restore` e i valori da 1 a 5 di `--progress-depth`. `--json` è proposto per i comandi che lo supportano. Per `--config-dir` completa directory; per i percorsi originali completa file o directory. Se inizi un valore di percorso vuoto, propone `/`, perché il selettore richiede percorsi assoluti. Sono supportati il formato `--config-dir=PATH` e il formato `--config-dir PATH`, e l'escaping nativo dei nomi con spazi.

Il completamento non esegue macbackup o rclone, non legge gli elenchi e non accede al cloud. Completa i percorsi usando il normale sistema di completamento di Zsh. La configurazione dei tuoi tasti e degli stili del terminale rimane quella già esistente.

I file versionabili sono:

```text
/Users/kevinmuka/.dotfiles/home/.zsh/completions/_macbackup
/Users/kevinmuka/.dotfiles/home/.zsh/integrations/macbackup.zsh
/Users/kevinmuka/.dotfiles/tests/test_macbackup_completion.py
```

L'integrazione aggiunge la directory di completamento a fpath prima di compinit. Se viene ricaricata dopo compinit, registra direttamente il comando tramite compdef. Non richiede modifiche a `.zshrc`, che carica già i file di integrazione. Le definizioni devono essere mantenute coerenti con il parser quando si aggiungeranno nuovi comandi o opzioni.

## 1. Obiettivo e limiti

Salvare cartelle e file scelti del Mac su due destinazioni indipendenti: Google Drive e Proton Drive. I dati ordinari devono restare consultabili dalle app dei servizi, anche dal telefono. Le credenziali e gli altri dati riservati devono essere cifrati prima del caricamento con rclone crypt. Ogni area deve conservare le copie sostituite e cancellate.

Non è un backup avviabile del Mac e non equivale a Time Machine. Una lettura di file mentre un'applicazione li modifica non è uno snapshot consistente dell'intera applicazione: database, librerie fotografiche e altri insiemi di file attivi possono richiedere una chiusura dell'app o un'esportazione apposita.

La disponibilità di una copia su Google non certifica quella su Proton. La leggibilità dal telefono dipende anche dai formati supportati dalle app: un file può essere scaricabile senza essere visualizzabile direttamente.

## 2. Posizione sul Mac e rapporto con Git

Posizione scelta per il file eseguibile:

```text
/Users/kevinmuka/.config/scripts/macbackup
```

La cartella `scripts` è già un collegamento simbolico a:

```text
/Users/kevinmuka/.dotfiles/home/.config/scripts/
```

Di conseguenza il sorgente reale del comando sarà:

```text
/Users/kevinmuka/.dotfiles/home/.config/scripts/macbackup
```

La documentazione viene conservata nel repository in:

```text
/Users/kevinmuka/.dotfiles/docs/macbackup.md
```

Nell'ambiente del terminale ispezionato la cartella degli script compare già nel PATH. Questo andrà verificato anche da un nuovo terminale; un'eventuale automazione deve usare percorsi espliciti per lo script e per rclone, senza dipendere dal PATH della shell interattiva.

Disposizione proposta per gli altri elementi:

| Elemento | Posizione |
|---|---|
| Elenchi e impostazioni | `/Users/kevinmuka/.config/macbackup/` |
| Piani, stato e registri | `/Users/kevinmuka/.local/state/macbackup/` |
| Configurazione rclone | `/Users/kevinmuka/.config/rclone/rclone.conf` su questo Mac |
| Cartella di recupero negli esempi | `/Users/kevinmuka/Restore/` |

La posizione rclone è stata ottenuta con `rclone config file`; su un altro Mac bisogna ricontrollarla. Le operazioni remote usano la configurazione attraverso rclone; lo script non ne stampa i segreti.

Il repository deve contenere codice, documentazione, test e soli esempi di configurazione senza segreti. Le impostazioni operative e gli elenchi personali restano inizialmente fuori dal repository: anche i nomi dei percorsi possono rivelare informazioni personali. Un'eventuale aggiunta degli elenchi ai dotfiles deve essere una scelta separata.

Password, token OAuth, configurazione rclone, chiavi, piani e registri non devono essere aggiunti a Git. La cartella locale di stato deve avere accesso limitato all'utente; anche i registri possono contenere nomi di file sensibili. Non devono contenere il contenuto dei file o credenziali.

L'installazione non comprende commit, push, modifiche al profilo della shell o attivazione di esecuzioni automatiche.

L'autocompletamento aggiunge due file nel sistema di integrazioni Zsh già previsto dai dotfiles; non modifica i profili o il file `.zshrc`.

## 3. Configurazione: quattro elenchi e un file di impostazioni

Tre file descrivono percorsi assoluti da includere o escludere. Il quarto, `explicit-only-patterns.txt`, descrive nomi di file e directory che richiedono un'inclusione esatta e non possono entrare nel backup solo perché si è inclusa una directory superiore. `settings.toml` contiene destinazioni, limite di cancellazioni e nomi di directory da cifrare automaticamente.

```text
/Users/kevinmuka/.config/macbackup/
  plain-paths.txt
  private-paths.txt
  exclude-paths.txt
  explicit-only-patterns.txt
  settings.toml
```

`plain` significa consultabile attraverso le normali app del servizio, con i permessi del tuo account. Non abilita condivisioni pubbliche. Su Proton rimane attiva la cifratura nativa del servizio; `private` aggiunge inoltre la cifratura di rclone crypt.

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
2. Un file con un nome in `[policy].ignored_file_names` viene saltato ovunque, anche se incluso esattamente. La regola riguarda i file, non una directory con lo stesso nome.
3. Se il nome di un file o di una directory corrisponde a explicit-only, l'elemento non viene salvato a meno che il suo percorso completo compaia direttamente in `plain-paths.txt` o `private-paths.txt`. Elencare soltanto una directory superiore non soddisfa questo requisito, neppure nell'area privata. Una directory saltata non viene attraversata. Eccezione deliberata: una directory che corrisponde anche a `private_directory_names` viene attraversata e cifrata automaticamente; altre protezioni al suo interno continuano a valere.
4. Superati i due controlli, un'inclusione privata o la corrispondenza con `private_directory_names` viene salvata cifrata. L'appartenenza a una directory privata mantiene privata la copia: un'inclusione esatta in plain non la rende consultabile.
5. Un'inclusione normale non privata viene salvata nell'area `plain`.
6. Un percorso non selezionato non viene salvato.

Non si consente di reincludere un discendente di una directory esclusa. Non si consente di rendere normale un discendente di una directory privata. Queste scelte mantengono prevedibili le regole indipendentemente dall'ordine delle righe.

Un percorso indica se stesso e i propri discendenti, non nomi simili: `/a/karabiner/` non comprende `/a/karabiner-old/`.

Per ignorare altri nomi di file in tutta la selezione, aggiungerli come stringhe letterali a `ignored_file_names` in `settings.toml`, per esempio `ignored_file_names = [".DS_Store", "Thumbs.db"]`. Il confronto non distingue maiuscole e minuscole; non sono ammessi percorsi o wildcard. Gli spazi dentro le stringhe TOML sono significativi: `" ← "` indica esattamente un nome con uno spazio prima e uno dopo la freccia. La configurazione attiva ignora `.DS_Store`, ` ← ` e `.localized`. Una nuova regola blocca i caricamenti futuri, ma lascia intatte le copie già presenti in `current` e `history`, che si possono rimuovere con `forget`. La regola non cancella file locali.

### 3.2.1 Nomi ammessi soltanto tramite inclusione esatta

Configurazione iniziale di `explicit-only-patterns.txt`:

```text
.env
.env.*
```

Qui si descrivono nomi, non percorsi assoluti. La regola `.env` corrisponde a quel nome in qualsiasi directory; `.env.*` comprende per esempio `.env.local`, `.env.production` e anche `.env.example`. Un file di esempio eventualmente innocuo va incluso direttamente se lo si desidera: non si presume che sia privo di segreti. Nella configurazione attiva sono stati aggiunti `node_modules`, `.venv`, `venv` e `myenv`: una directory con uno di questi nomi viene saltata ovunque si trovi, anche se viene creata dopo questa revisione.

La sintassi accetta nomi e il carattere jolly `*`, limitato al nome finale del file o della directory; non accetta `/`, `**`, espressioni regolari o regole con segno `+` o `-`. Righe vuote e commenti a inizio riga funzionano come negli altri elenchi. Per prudenza questi soli controlli sui nomi sono senza distinzione tra maiuscole e minuscole: anche `.ENV` richiede un'inclusione esatta. Gli altri percorsi mantengono la propria semantica e non diventano globalmente insensibili alle maiuscole.

La regola riguarda file, directory ed elementi simbolici con quei nomi. Per autorizzare esplicitamente una directory protetta si aggiunge il suo percorso completo a un elenco di inclusione; i file al suo interno seguono comunque le altre regole, quindi un `.env` resta protetto. La selezione di un collegamento salva il collegamento secondo la politica descritta sotto e non autorizza automaticamente la copia della destinazione.

Esempio con `/Users/kevinmuka/Desktop/progetto/` in plain:

| Configurazione aggiuntiva | Esito per `/Users/kevinmuka/Desktop/progetto/.env` |
|---|---|
| Nessuna | Saltato: incluso soltanto attraverso la directory |
| Percorso esatto in plain | Salvato nell'area normale, con avviso di inclusione esplicita di un nome protetto |
| Percorso esatto in private | Salvato cifrato e assente dalla copia normale |
| Directory progetto in private, senza il percorso esatto del file | Saltato: anche l'inclusione privata è soltanto ereditata |
| Percorso esatto in entrambi gli elenchi | Salvato cifrato: private prevale |
| Percorso del file o di un suo antenato in exclude | Saltato in ogni caso |

L'autorizzazione è soltanto per il percorso scritto: elencare esattamente `progetto/.env` non autorizza `progetto/subdir/.env`, `altro-progetto/.env` o `progetto/.env.local`.

Questa regola deve essere attiva sia nel calcolo dell'anteprima sia nell'esecuzione dei trasferimenti, non soltanto nel controllo preliminare. Un nuovo `.env` creato dentro una cartella durante la run non deve passare attraverso una semplice inclusione ricorsiva della directory.

Rimuovere il percorso esatto dall'elenco, oppure aggiungere un nuovo pattern di protezione, interrompe i caricamenti futuri ma conserva le copie già presenti in current e history. Per rimuoverle resta necessario `forget`. `preview --local` mostra i nomi bloccati; `versions` e `forget` permettono di trovare le copie cloud precedenti. `run` e `status` non producono ancora un avviso automatico che collega queste due informazioni.

Questa protezione si applica ai caricamenti di macbackup sui cloud. Non configura Git, non crea regole `.gitignore` e non impedisce un push Git effettuato con altri strumenti. Non riconosce un segreto copiato dentro un file con altro nome o un archivio. Le directory `.git` selezionate sono ora cifrate automaticamente; ciò non elimina eventuali copie precedenti in chiaro, che si possono cercare e rimuovere con `versions` e `forget`.

Il file di regole deve essere creato esplicitamente all'inizializzazione. Se manca o non è leggibile in una configurazione attiva, check, preview e run devono fermarsi: non si deve interpretare il problema come un elenco di protezioni vuoto. Nessun flag temporaneo deve aggirare globalmente explicit-only.

### 3.3 Selezione reale concordata il 30 ottobre 2026

Questi percorsi sono stati inseriti nella configurazione locale. Google è ora abilitato nella configurazione locale per permettere all’utente di avviare la prima copia; Proton rimane disabilitato. Compilare gli elenchi da solo non avvia un trasferimento.

`plain-paths.txt`:

```text
/Users/kevinmuka/Desktop/
/Users/kevinmuka/Documents/
/Users/kevinmuka/.config/
/Users/kevinmuka/.dotfiles/
/Users/kevinmuka/.gitconfig
/Users/kevinmuka/.zshrc
/Users/kevinmuka/.zprofile
/Users/kevinmuka/.zshenv
/Users/kevinmuka/.zsh
```

`private-paths.txt`:

```text
/Users/kevinmuka/.ssh/
/Users/kevinmuka/.config/rclone/
```

`exclude-paths.txt`:

```text
/Users/kevinmuka/.config/gh/
/Users/kevinmuka/.config/github-copilot/
/Users/kevinmuka/.config/configstore/
/Users/kevinmuka/.config/opencode/
/Users/kevinmuka/.config/joplin-desktop/
```

`explicit-only-patterns.txt` contiene `.env`, `.env.*`, `node_modules`, `.venv`, `venv` e `myenv`. Nessun `.env` è stato autorizzato singolarmente: includere Desktop, Documents o .config non basta a caricarlo. Le quattro voci aggiunte fermano file o directory con questi nomi in tutta la selezione; le directory non vengono attraversate. Le 42 esclusioni assolute temporanee usate per la revisione sono state rimosse da `exclude-paths.txt`, che conserva soltanto le cinque esclusioni `.config` elencate sopra. La classificazione della directory protetta vale anche quando macbackup incontra una vecchia copia già presente nel cloud: interrompe gli aggiornamenti senza archiviarla come cancellazione. Lo storico esistente resta conservato finché non viene eseguita una rimozione esplicita.

Il 1 novembre l'utente ha scelto di cifrare tutte le directory `.git`. Nella configurazione attiva `settings.toml` contiene `[policy] private_directory_names = [".git"]`: ogni directory con questo nome, presente o futura, e i suoi discendenti entrano nell'area cifrata se si trovano sotto un percorso incluso. La voce `.git` resta anche in `explicit-only-patterns.txt`: se la regola di cifratura per nome viene rimossa, torna a essere richiesta un'inclusione esatta. Sono state rilevate 68 directory `.git` per circa 0,72 GiB. I file di lavoro dei progetti restano consultabili; `.env` e gli altri nomi protetti dentro `.git` richiedono comunque l'inclusione esatta. Un'esclusione assoluta continua a prevalere. La nuova classificazione non cancella eventuali vecchie copie `.git` in chiaro, incluse quelle nello storico.

Se `Desktop/progetto` è in plain, un file di lavoro come `README.md` va in `plain/current/Users/kevinmuka/Desktop/progetto/README.md`, mentre un oggetto Git va in `private/current/Users/kevinmuka/Desktop/progetto/.git/objects/...` attraverso rclone crypt. Nel sito Drive, la directory consultabile del progetto non contiene `.git`; nell'area privata nomi e contenuti sono cifrati. Il percorso originale viene conservato in entrambe le aree, così i due alberi si possono ricomporre durante un recupero. La versione attuale di `restore` recupera un file alla volta: la ricomposizione automatica di un intero progetto non è ancora implementata.

Karabiner è incluso: l'esclusione discussa inizialmente era soltanto un esempio. `.config/karabiner` è un collegamento; il contenuto reale viene salvato attraverso `.dotfiles/home/.config/karabiner`, incluso nel repository selezionato. Gli altri collegamenti .zsh vengono conservati come collegamenti e i loro contenuti nei dotfiles sono coperti separatamente. Un'esclusione di una posizione non esclude automaticamente una copia indipendente situata altrove.

La prima scansione dei soli nomi e metadati aveva contato circa 182,5 GB decimali di file selezionati e circa 488 mila elementi plain. La revisione ha individuato 42 directory `node_modules`, `.venv`, `venv` e `myenv` sotto Desktop e Documents: circa 8,6 GiB e 426 mila file, ricreabili dai rispettivi progetti. La cartella `Desktop/backup 25U3 0312-1112` contiene fotografie ed è rimasta inclusa. Con le esclusioni per nome la selezione locale è risultata intorno a 174,4 GB e 61,7 mila elementi plain; i numeri restano una fotografia del momento, non una run di backup riuscita. La versione 0.2 aveva segnalato 50 errori relativi ai file Icon\r. La scelta di conservarne anche i metadati è stata recepita nella versione 0.3, anziché aggiungere esclusioni. Non sono stati caricati dati reali.

La nuova scansione completa con il selettore 0.3 è riuscita senza errori. Il conteggio durante il collaudo includeva anche alcuni piccoli file sintetici nell'area di lavoro sotto Documents: i numeri sono una fotografia di quel momento, non un inventario immutabile. Gli avvisi sui collegamenti e sui socket esclusi rimangono distinti dagli errori.

Dopo il passaggio a Production dichiarato dall'utente e la riconnessione, il controllo remoto Google è riuscito. L'anteprima Google del 30 ottobre con le sei regole explicit-only ha completato senza errori: 61.664 file ordinari, 6 privati e 50 icone selezionati, nessuna archiviazione per cancellazione prevista. Era un dry-run: non ha caricato né cancellato file. Una correzione successiva ha esteso la classificazione delle directory protette anche alle vecchie copie cloud; la prova sintetica locale ha confermato che queste copie rimangono in current. Il target Google reale resta disabilitato in `settings.toml` e non è stata eseguita una run di dati personali.

L'anteprima del 1 novembre con `.git` temporaneamente esclusa aveva contato 35.526 file ordinari, 6 privati e 50 icone, zero archiviazioni per cancellazione, circa 173,7 GB locali. Era un dry-run. Dopo l'attivazione della regola cifrata, la scansione locale ha contato 35.576 elementi plain, 26.154 privati, 50 icone e circa 174,4 GB selezionati. La successiva anteprima Google ha previsto 35.526 file plain, 26.154 privati e 50 icone, senza archiviazioni per cancellazione. La differenza di 50 nel conteggio plain è dovuta alle icone Finder, contate separatamente nell'anteprima. Anche questa era un'anteprima; in seguito Google è stato abilitato e il primo trasferimento reale è stato interrotto su richiesta dell’utente dopo alcuni file. Non è un backup completo.

Prima di lasciare all'utente l'avvio manuale, è stata aggiunta la policy per ignorare i nomi `.DS_Store`, ` ← ` (con gli spazi) e `.localized`. La nuova anteprima Google è riuscita: 34.656 file plain, 26.078 privati, 50 icone; una sola archiviazione prevista. Il file era `Desktop/modern-download-upload-web-symbol-cloud-storage_1017-59711.xmp`, presente nella copia parziale ma ormai assente sul Mac: la run lo sposterà nello storico, conservandolo. Non sono state proposte archiviazioni dovute ai nuovi nomi ignorati. I conteggi sono una fotografia del 1 novembre, non una garanzia per una run successiva.

### 3.4 Credenziali e collegamenti simbolici

Non si può promettere di riconoscere automaticamente ogni segreto dentro Desktop, Documents, repository o `.config`. Prima del primo caricamento occorre rivedere le selezioni. Il percorso effettivo della configurazione rclone, quando selezionato, deve essere protetto dalla classificazione privata; una configurazione incoerente deve essere bloccata.

I link simbolici non devono essere seguiti automaticamente. Possono essere conservati mediante `--links`, che rclone rappresenta sul cloud con file aventi suffisso `.rclonelink`. Il contenuto del link è il percorso della destinazione, non il contenuto della destinazione.

Per questo selezionare `.config/` non basta a salvare il contenuto di un repository raggiunto soltanto attraverso un collegamento: anche il percorso reale deve essere incluso. È il caso della cartella degli script nei dotfiles.

La conservazione dei collegamenti e il controllo di collisioni con veri file `.rclonelink` devono essere collaudati. Se la stessa sorgente riservata viene raggiunta anche da un percorso selezionato come normale, il controllo deve bloccare o risolvere esplicitamente il conflitto; non deve procedere con una copia in chiaro. Non è un sistema di riconoscimento di copie indipendenti aventi lo stesso contenuto.

## 4. Struttura delle destinazioni

Ogni servizio contiene un'area dedicata a questo backup:

```text
MacBackup/
  plain/
    current/
      Users/kevinmuka/...
      etc/hosts
      Volumes/Archivio/...
    history/
      RUN_ID/...
  private/
    [nomi e contenuti cifrati]
```

La vista logica dell'area privata, attraverso il remote crypt, è:

```text
current/Users/kevinmuka/.ssh/...
history/RUN_ID/Users/kevinmuka/.ssh/...
```

Il remote crypt deve comprendere l'intera area privata, incluso lo storico. Il backup privato non deve essere eseguito direttamente sul remote sottostante. Ogni servizio ha un proprio collegamento crypt; non serve una copia da Google a Proton, perché entrambi leggono le sorgenti locali.

La struttura riproduce i percorsi, ma non certifica da sola la conservazione di permessi, attributi estesi o tutte le proprietà del filesystem macOS. Servono scelte e prove specifiche per i metadati necessari al recupero.

Conservare fuori dal Mac i parametri necessari a ricreare il remote crypt, inclusi password e salt personalizzato se usato. Non basta conoscere la password di Google o Proton. La configurazione rclone deve essere protetta anche localmente: il normale offuscamento delle password non è cifratura sicura della configurazione.

## 5. Cosa accade durante il backup

| Evento | Effetto |
|---|---|
| Nuovo file selezionato e ammesso dalle protezioni | Caricato nell'area assegnata, sotto `current` |
| Nuovo `.env` incluso soltanto tramite una directory | Saltato, con motivazione explicit-only |
| Percorso esatto di un file protetto tolto dagli elenchi | Copie già caricate mantenute senza aggiornamenti |
| File modificato | Copia precedente nello storico; nuova copia in `current` |
| File cancellato dentro una directory selezionata e disponibile | Copia precedente spostata nello storico |
| Percorso aggiunto alle esclusioni | Copie già caricate mantenute senza aggiornamenti |
| Percorso tolto dagli elenchi | Copie già caricate mantenute senza aggiornamenti |
| Percorso passato da normale a privato | Nuovi backup cifrati; vecchie copie normali mantenute e segnalate |
| Percorso passato da privato a normale | Avviso esplicito prima di caricarlo consultabile |
| Sorgente esplicitamente inclusa mancante o illeggibile | Operazione interessata bloccata; nessuna interpretazione come directory vuota |
| Spazio remoto insufficiente | Errore; nessuna pulizia automatica dello storico |

`current` significa ultima copia dei percorsi ancora gestiti, con eventuali vecchie copie rimaste ferme dopo un'esclusione. Non è necessariamente uno specchio esatto dell'attuale selezione. `status` e l'anteprima devono rendere visibili queste situazioni.

La sparizione di una sorgente esplicitamente elencata è ambigua e blocca il backup: potrebbe essere un disco scollegato o una cancellazione intenzionale. La cancellazione di un file figlio dentro una directory selezionata e correttamente disponibile è invece una normale cancellazione da archiviare.

Per i volumi esterni non basta controllare che una directory esista: bisogna verificare che il volume atteso sia montato e corrisponda a quello previsto.

Non è prevista alcuna scadenza automatica dei nostri storici. L'eventuale introduzione futura di una politica di conservazione richiede una scelta separata. Cestino e versioni interne dei servizi seguono invece le rispettive regole del provider.

Ogni tentativo usa un identificativo unico per lo storico. Un nuovo tentativo non deve riusare una cartella di storico in cui potrebbe sovrascrivere una versione conservata. Un'esecuzione interrotta può avere già trasferito o archiviato alcuni file: non è una transazione atomica, né tra file né tra servizi.

## 6. Comandi proposti

Sono sottocomandi di macbackup, non di rclone. Il ripristino generale di un albero rimane una funzione futura.

| Comando | Effetto principale |
|---|---|
| `init` | Crea localmente quattro elenchi e `settings.toml`, senza inclusioni attive |
| `check` | Controlla sorgenti locali; con `--remote --target` legge anche inventari e remotes |
| `explain PATH` | Spiega la classificazione locale di un singolo percorso |
| `layout [PATH]` | Mostra le parti private dentro una directory plain; senza PATH usa la directory corrente |
| `preview --local` / `preview --target` | Mostra la selezione locale o simula il trasferimento remoto senza modifiche |
| `run --target` | Trasferisce nelle aree abilitate, conserva versioni e mostra l'avanzamento |
| `status` | Legge il resoconto locale dell'ultima run, anche interrotta |
| `restore-icon` | Ricrea localmente un'icona Finder da uno snapshot già scaricato |
| `versions PATH` | Elenca le copie di un file o riepiloga quelle sotto una directory |
| `restore PATH` | Scarica un file in una destinazione esplicita; con `--links` ricrea un symlink |
| `verify --target` | Confronta le sorgenti attuali con `current`, senza modifiche |
| `forget` | Prepara un piano di rimozione e, con `--plan ID --apply`, lo applica |

L'opzione globale `--config-dir PATH` va prima del sottocomando e cambia soltanto la directory degli elenchi e di `settings.toml`; non cambia sorgenti, stato o credenziali rclone. I comandi di lettura e di esecuzione che prevedono `--json` restituiscono JSON UTF-8.

Valori uniformi:

- `--target google|proton|all`: destinazioni.
- `--area plain|private|all`: aree, quando il comando lo richiede.
- I percorsi contenenti spazi devono essere tra virgolette nella shell.
- Un'opzione che seleziona un'area privata non deve richiedere di digitare nomi cifrati.

### 6.1 `check`: controllo locale e remoto

```sh
macbackup check
macbackup check --json
```

Controlla sintassi, precedenze, sorgenti, permessi di lettura, link, conflitti e presenza del file explicit-only. Evidenzia le inclusioni esatte che autorizzano nomi protetti nell'area plain. `check --remote --target google` legge anche gli inventari e controlla i remotes; il target è obbligatorio se si vuole evitare il valore predefinito google del controllo remoto. Non elabora quote o costi non disponibili.

Non crea un backup e non dimostra che un recupero funzioni. La lettura delle sorgenti può richiedere il consenso di macOS per Desktop o Documents: un rifiuto è un errore da risolvere, non un'esclusione silenziosa.

### 6.2 `preview`: mostrare le operazioni

```sh
macbackup preview --local
macbackup preview --local --json
```

La modalità disponibile mostra i percorsi e la loro classificazione locale, i motivi di esclusione e gli avvisi. Le inclusioni esatte di nomi protetti nell'area normale sono evidenziate. Un file bloccato da explicit-only riporta anche il pattern responsabile nel risultato JSON e nella spiegazione individuale.

La modalità disponibile `preview --target google` esegue il dry-run remoto e riporta per destinazione e area file selezionati e archiviazioni dovute a cancellazioni. La presentazione completa delle singole differenze e delle vecchie copie diventate non gestite resta da completare.

La modalità locale non accede al cloud e non scrive un resoconto: stampa il risultato. La versione futura potrà salvare un resoconto locale protetto. Dimensioni e durata del trasferimento, quando stimate, dovranno essere indicate come stime.

Per capire la classificazione di un singolo percorso, senza scandire tutte le sorgenti:

```sh
macbackup explain "/Users/kevinmuka/Desktop/progetto/.env"
macbackup explain "/Users/kevinmuka/Desktop/progetto/.env" --json
```

Le spiegazioni e le anteprime locali non provano che i file siano già salvati o cifrati. La cartella privata sul cloud non esiste finché non viene configurata la parte di trasferimento.

L'anteprima non congela i file né le destinazioni. Una successiva esecuzione deve rivalidare la situazione: non si promette che eseguirà esattamente un elenco calcolato ore prima.

### 6.3 `run`: eseguire il backup

```sh
macbackup run --target all
macbackup run --target google
macbackup run --target proton
```

Il programma ricontrolla la configurazione, acquisisce un blocco contro esecuzioni concorrenti e svolge le operazioni nelle aree assegnate. Un percorso privato non deve essere caricato nell'area normale in caso di errore della cifratura. Durante `run`, macbackup mostra i rapporti di rclone ogni 5 secondi in una schermata dedicata, se il terminale è interattivo. Le barre ASCII distinguono il progresso in byte da quello in file. La velocità complessiva è in evidenza; per ciascun file attivo, percorso e velocità sono su righe diverse. Tempo trascorso e stima sono arrotondati ai secondi, senza millisecondi. Premi `u` per alternare unità binarie (KiB, MiB, GiB e relative velocità) e decimali (kB, MB, GB); premi `?` per mostrare o nascondere la legenda. È una scelta di visualizzazione durante la fase corrente e non modifica i file né il resoconto. Ctrl-C interrompe il trasferimento come prima; il terminale viene ripristinato. Senza terminale interattivo, le stesse informazioni vengono stampate periodicamente come testo e non si possono usare i tasti. Più file e più cartelle possono essere trasferiti contemporaneamente: non esiste sempre un'unica «directory corrente». Ogni rapporto riassume le cartelle dei file attivi, raggruppandole per due livelli sotto la home. Si può scegliere da uno a cinque livelli con `--progress-depth N`, per esempio `macbackup run --target google --progress-depth 3`. I percorsi dei file attivi non vengono troncati. Le statistiche sono della fase plain, icone o private in corso, non dell'intero backup. `status` viene scritto al termine; dopo Ctrl+C durante il trasferimento registra la fase interrotta. Alla run successiva vengono confrontati i file già completi; macbackup non conserva byte parziali per riprendere il file interrotto, che viene ritrasferito dall'inizio.

`run --json` esegue lo stesso backup reale e cambia soltanto il riepilogo finale su stdout. L'avanzamento resta sul terminale tramite stderr. Senza `--json`, il riepilogo finale distingue i selezionati dai trasferiti e dai controllati; `status` conserva gli stessi conteggi per ogni fase conclusa o interrotta.

Prima di una quantità anomala di rimozioni da `current`, il programma si ferma. La soglia è max_delete in settings.toml, inizialmente 25 per area e destinazione; va rivista prima di abilitare l'automazione.

L'esito è separato per Google/Proton e plain/private. Una destinazione può riuscire mentre l'altra fallisce: il riepilogo e il codice di uscita devono indicare il risultato parziale. Un successo richiede il completamento di tutte le operazioni richieste.

La singola esecuzione non garantisce la stessa fotografia temporale sui due servizi: se i file locali cambiano tra le letture, le copie possono riferirsi a istanti diversi. Il backup non va presentato come snapshot simultaneo.

### 6.4 `status`: conoscere l'esito memorizzato

```sh
macbackup status
```

Mostra il resoconto dell'ultima run, con gli esiti per destinazione e area richieste in quella run. Per ogni fase distingue `selected` (elementi previsti), `transferred_files` (trasferimenti completati secondo rclone), `transferred_bytes` (byte contabilizzati da rclone nella fase), `checked_files` (verifiche di rclone) e `listed_items` (file e cartelle incontrati durante l'esplorazione, non il totale già presente nel cloud). `renamed_files`, `server_side_moves` e `server_side_move_bytes` riportano gli spostamenti fatti sul cloud: con `--backup-dir` includono le copie precedenti spostate nello storico. Non si sommano ai file caricati dal Mac. `counts_complete: true` indica statistiche finali ricevute dopo una fase riuscita. Dopo Ctrl+C, se rclone ha già emesso statistiche periodiche, mostra l'ultimo conteggio con `counts_complete: false`: può essere inferiore ai file effettivamente completati prima del segnale, e i byte possono includere parte del file interrotto. Se non è arrivato nessun rapporto, i valori sono `null` anziché zero. La versione 0.9.1 mostrava i progressi nel terminale ma non catturava i rapporti periodici durante Ctrl+C: i suoi `null` non si possono ricostruire dallo stato locale. Dalla 0.9.2 il riepilogo periodico viene sia mostrato sia registrato come ultima fotografia disponibile. I testi JSON sono stampati in UTF-8 leggibile, senza sequenze `\u2019` per gli apostrofi. La vista storica dell'ultimo successo per ogni destinazione e la data di verifica non sono ancora implementate. Lo stato locale memorizzato non certifica che il cloud sia raggiungibile in quel momento, che tutti gli storici siano integri o che una prova di recupero sia riuscita.

### 6.5 `versions`: trovare le copie di un file o di una directory

```sh
macbackup versions "/Users/kevinmuka/Documents/tesi.docx" --target google
macbackup versions "/Users/kevinmuka/.ssh/config" --target google --area private
macbackup versions ~/.dotfiles --target google
macbackup versions ~/.dotfiles --target google --files
```

Il comando legge `current` e tutti gli storici delle aree richieste, anche se il percorso è stato tolto dagli elenchi o il file locale non esiste più. `--target` è obbligatorio; `--area` vale `all` se omesso, perché la ricerca è soltanto in lettura. Per un file serve il percorso originale esatto; l'output mostra area, servizio, dimensione, data di modifica disponibile e identificativo di versione: `current` oppure l'ID della directory sotto `history`. La data di modifica non è la data di archiviazione.

Per una directory esistente sul Mac, basta il suo percorso (`~/.dotfiles` viene espanso dalla shell). Se la directory locale non esiste più, aggiungere `/` in fondo al percorso assoluto per chiedere la ricerca ricorsiva. L'output normale mostra, per area e destinazione, un gruppo `current` con il numero di elementi attuali e un gruppo per ciascuna run che ha elementi storici sotto quella directory, con conteggio e byte. `--files` aggiunge percorsi originali, dimensioni e tipo (`files` o `macos-icons`) **solo per i gruppi `history`**; del gruppo `current` restano visibili conteggio e byte, senza l’elenco dei file attuali. `--json` restituisce gli stessi gruppi e i dettagli di ogni elemento, incluso il percorso remoto. `--files` è valido soltanto per una directory. La ricerca include sia l'area plain sia private salvo `--area` esplicito: per `.dotfiles`, la directory `.git` cifrata compare sotto private, mentre i file consultabili compaiono sotto plain.

Ogni `history/RUN_ID` contiene **soltanto gli elementi spostati in quella run**, non una fotografia completa della directory a quella data. Cambiare un file sul Mac non crea subito uno storico: serve una copia precedente già caricata e una successiva run che la sostituisca. `versions` non ripristina un'intera directory; `restore` continua a lavorare su un file alla volta.

Le destinazioni possono essere disabilitate in `settings.toml`, purché i rispettivi remote rclone esistano. Il comando non richiede lo stato locale di vecchie run: ricostruisce l'elenco dal cloud. `--json` restituisce anche il percorso remoto esatto per ciascuna copia e conserva i dettagli degli elementi `current`. Dalla versione 0.9.5 `versions` usa una ricerca in sola lettura propria: cerca il percorso richiesto in `current`, elenca gli ID delle run in `history` e cerca lo stesso percorso dentro ciascuna run. Per un singolo file cerca nella sua directory superiore. Non calcola hash né ID originali; `forget` continua a fare il proprio inventario e le proprie verifiche prima di qualsiasi rimozione. La ricerca circoscritta dovrebbe essere più rapida soprattutto per percorsi piccoli e poche run; con molte run può comportare più richieste separate. Non è stata misurata sul Drive reale.

### 6.6 `restore`: recuperare un singolo file

Dopo aver letto l'identificativo con `versions`, si sceglie esplicitamente una destinazione locale:

```sh
macbackup restore "/Users/kevinmuka/Documents/tesi.docx" \
  --target google --area plain --version current \
  --to "/Users/kevinmuka/Restore/tesi-recuperata.docx"
```

Per un collegamento, scegliere un percorso di prova diverso dall’originale e aggiungere `--links`:

```sh
macbackup restore "/Users/kevinmuka/.zprofile" \
  --target google --area plain --version current \
  --to "/Users/kevinmuka/Downloads/macbackup-restore/.zprofile" --links
```

La directory `Downloads/macbackup-restore` deve già esistere. Il collegamento ricreato punta al percorso originale registrato, `/Users/kevinmuka/.dotfiles/home/.zprofile`; la destinazione va recuperata separatamente. Un collegamento assoluto può risultare non funzionante su un Mac con nome home diverso.

Per una vecchia versione si usa come valore di `--version` l'ID della relativa directory `history` mostrato da `versions`. Il comando richiede un solo servizio e una sola area. La directory di destinazione deve esistere e non attraversare collegamenti simbolici. Il programma rifiuta il percorso originale come destinazione e non sovrascrive un file già presente, salvo `--replace` esplicito; anche allora rifiuta una destinazione simbolica o non regolare. Scarica prima in un file temporaneo con permessi 600, verifica dimensione e, quando il backend espone hash utilizzabili, confronta gli hash. Rilegge l'inventario prima di rendere visibile il file recuperato. Se non è disponibile un hash, lo dichiara: dimensione e metadati non certificano da soli l'integrità del contenuto.

Un collegamento simbolico può essere recuperato con `restore --links`: senza il flag, il comando si ferma e non crea un normale `.rclonelink`. Scarica e controlla il piccolo file di destinazione, quindi ricrea un collegamento con il medesimo target, anche se assoluto o contenente `..`; non crea il file a cui il collegamento punta. Il ripristino del solo symlink in una cartella di prova non ricompone automaticamente i contenuti dei dotfiles. `--links` è rifiutato per file normali. Il comando non ripristina directory intere, permessi di directory, ACL, attributi macOS o date originali. Per una chiave `.ssh` il file recuperato ha permessi 600, ma bisogna preparare separatamente la directory di destinazione con permessi appropriati, normalmente 700. Le icone Finder seguono la procedura `restore-icon` descritta sopra. Un file scaricato dentro una sorgente ancora selezionata può essere incluso nella run successiva.

Il collaudo isolato del 1 novembre ha trovato due versioni sintetiche su Google: una in `plain/history` e una in `private/current`. Entrambe sono state scaricate e confrontate con i file fittizi di partenza. L'hash della copia normale è stato verificato; il remote crypt non ha esposto un hash utilizzabile, e il risultato lo ha dichiarato. I due file cloud e le cartelle di prova sono stati rimossi e verificati assenti. Nessun file personale è stato recuperato o modificato.

**Limite dello storico:** ogni directory `history/RUN_ID` contiene soltanto i file archiviati in quel tentativo. Il programma non promette il ripristino di un intero albero a una data arbitraria. Per offrirlo servono inventari completi e una ricostruzione collaudata, oppure uno strumento basato su snapshot.

### 6.7 `verify`: confrontare la selezione locale con `current`

```sh
macbackup verify --target google
macbackup verify --target google --area private --download
```

Il comando scansiona le sorgenti locali selezionate e confronta i file ammessi con `current` nel servizio richiesto. Non modifica sorgenti o cloud. La modalità ordinaria usa `rclone check` per l'area normale e `rclone cryptcheck` per l'area cifrata; entrambe richiedono una corrispondenza completa nel rapporto di rclone. `--download` usa `rclone check --download` e legge il contenuto remoto per confrontarlo con quello locale: può generare molto traffico e richiedere molto tempo. Per la cartella normale Google rclone usa gli hash comuni quando disponibili; la verifica cifrata usa il metodo apposito di cryptcheck. La verifica comprende anche gli snapshot correnti delle icone Finder che macbackup genera dalle sorgenti selezionate.

Il risultato separa file corrispondenti, diversi, mancanti e errori di lettura per servizio, area e tipo. Una differenza fra `current` e il file locale attuale **non prova** che il backup sia corrotto: il file potrebbe essere stato modificato dopo la copia. Il comando non verifica gli storici, le copie conservate dopo un'esclusione, l'intero insieme dei metadati macOS o le revisioni native del provider. Senza un manifesto dei contenuti registrato al momento della run, non certifica il contenuto di un vecchio file confrontandolo con l'originale attuale. Le destinazioni possono essere disabilitate in `settings.toml`, purché i remote rclone esistano.

Nel collaudo isolato su Google del 1 novembre, `verify` ha trovato corrispondenti un file normale e uno cifrato sia con il metodo ordinario sia con `--download`. Una modifica locale fittizia che conservava dimensione e orario è stata segnalata come differenza. I due file e i namespace di prova sono stati rimossi e verificati assenti; i file personali non sono stati toccati.

### 6.8 `forget`: rimuovere copie conservate

`forget` usa due passaggi. Il primo legge il cloud e crea soltanto un piano; il secondo applica quel piano dopo una nuova verifica. Area, destinazione e modalità sono sempre esplicite. Per un file si indica il percorso originale esatto; per una directory si aggiunge `/` finale, anche se la directory locale non esiste più:

```sh
macbackup forget "/Users/kevinmuka/Desktop/old-project/" \
  --area plain --target google --mode trash
```

Per rimuovere anche gli storici plain di un file diventato privato, si può creare un piano Google con `--mode permanent` al posto di `trash`, dopo aver controllato il percorso e il piano stampato:

```sh
macbackup forget "/Users/kevinmuka/Desktop/progetto/segreto.txt" \
  --area plain --target google --mode permanent
```

Questo esempio non applica ancora la rimozione: soltanto il successivo `forget --plan ID --apply` usa il piano. `--area private` cerca invece la copia cifrata; `--area all` cerca entrambe.

Il piano elenca ogni file corrispondente in `current` e in tutte le directory sotto `history`, con area, servizio, posizione, numero e byte noti. Per una directory comprende anche gli snapshot `macos-icons` della cartella e dei discendenti. Il confronto usa i confini dei percorsi: `old-project/` non comprende `old-project-other/`. La ricerca non applica le regole di selezione correnti, così trova anche copie caricate prima di una nuova esclusione o classificazione privata. Le destinazioni possono essere disabilitate in `settings.toml`, purché i relativi remote rclone siano configurati. Un piano di oltre 10.000 file viene rifiutato: restringere il percorso e creare più piani.

Se non ci sono corrispondenze non viene creato un piano. Altrimenti macbackup genera un ID casuale e salva il piano in un file locale con permessi 600, sotto `~/.local/state/macbackup/forget-plans`. Il piano scade dopo un'ora e si usa una sola volta. L'output mostra il comando preciso per applicarlo:

```sh
macbackup forget --plan F0123456789ab --apply
```

Prima dell'applicazione macbackup rilegge gli inventari e confronta l'insieme completo delle corrispondenze, i percorsi remoti, le dimensioni, gli orari, gli ID e gli hash restituiti dal backend. Se una copia cambia o ne appare un'altra, blocca l'intero piano. Alcuni backend non espongono hash del contenuto: modifiche dello stesso file con identica dimensione e identico orario potrebbero non essere rilevate. Per questo il piano scade e non va usato mentre altri client modificano il backup.

L'applicazione rimuove i file uno alla volta, poi rilegge l'inventario. In caso di errore può esserci un risultato parziale, registrato sotto lo stesso ID; si crea un nuovo piano per gli elementi rimasti. Il comando non modifica sorgenti locali né elenchi. Se il percorso è ancora incluso, una successiva `run` potrebbe caricarlo nuovamente: prima si cambia la classificazione e poi si usa `forget`. Le directory vuote possono restare nel cloud dopo la rimozione dei file.

`--area plain` permette per esempio di rimuovere le vecchie copie consultabili dopo aver spostato un file nell'area privata. `--area all` cerca entrambe le aree. `--target all` richiede che siano configurati entrambi i servizi; non assume che una destinazione disabilitata sia assente.

### 6.9 Cestino, rimozione definitiva e revisioni del provider

`--mode trash` rimuove le copie individuate dalle cartelle del backup e le manda nel cestino del servizio. Non significa eliminazione definitiva e può non liberare spazio.

`--mode permanent` è accettato soltanto per `--target google` quando il remote normale è davvero di tipo Google Drive. Il collaudo isolato del 1 novembre ha creato quattro piccoli file fittizi (plain e private, current e history), generato un piano da quattro corrispondenze, applicato `permanent`, verificato zero file attivi residui e rimosso le due directory di prova rimaste vuote. Non sono stati toccati file personali. Non può essere combinato con `--target all`; una capacità non supportata viene rifiutata prima di qualsiasi rimozione e non viene trasformata silenziosamente in `trash`.

Su Google rclone supporta la cancellazione permanente dei file individuati tramite `--drive-use-trash=false`. L'ispezione di revisioni native e di copie già presenti nel cestino è distinta dall'ispezione delle nostre cartelle: non va dichiarata completa senza una funzionalità dedicata e verificata. Rimuovere un percorso non individua automaticamente duplicati con un altro nome o in altre cartelle.

Nel backend Proton di rclone 1.75.2, Remove sposta il file nel cestino e CleanUp svuota tutto il cestino. Non risulta un comando rclone esposto da questo backend per la rimozione definitiva selettiva: macbackup rifiuta `permanent` su Proton. `trash` sarà da collaudare sull’account Proton quando il remote sarà configurato. La rimozione definitiva selettiva di elementi già nel cestino Proton resta manuale; macbackup non fornisce ancora una mappa verificata dei nomi cifrati nel cestino.

Il risultato distingue la rimozione dalle cartelle attive e la modalità richiesta. `trash` lascia le copie recuperabili nel cestino del servizio; `permanent` chiede al provider Google la cancellazione definitiva dei file attivi selezionati. Il programma non certifica l’assenza di copie precedentemente nel cestino, revisioni native di Drive o duplicati con altri nomi.

## 7. Sicurezza operativa e recuperabilità

- Il programma deve controllare le sorgenti prima di qualsiasi archiviazione dovuta a cancellazione. Non deve usare `--ignore-errors` per forzare il backup oltre un errore di lettura.
- Non deve avviare due run contemporanee, né run e forget contemporaneamente.
- La cifratura deve fallire in modo chiuso: nessun ripiego su un caricamento in chiaro.
- Tutti i percorsi devono essere passati a rclone come argomenti, senza costruire comandi shell da testo non affidabile.
- I file locali di stato, le credenziali e le cartelle di recupero devono avere protezioni adeguate. Lo stato operativo deve essere escluso dal backup ordinario per evitare ricorsioni e caricamenti accidentali di piani o registri.
- La configurazione necessaria a ricostruire il backup deve essere esportabile in forma protetta; le chiavi di recupero devono essere disponibili senza dipendere dall'unico Mac salvato.
- I file cloud del backup vanno consultati come copie. Modifiche o cancellazioni dal telefono non vengono propagate al Mac e possono essere sovrascritte o ricreate dalla successiva esecuzione.
- I log non contengono contenuti dei file. L'eventuale inventario remoto dei percorsi privati deve essere cifrato a sua volta.
- Un semplice backup con accesso allo stesso account non è un archivio immutabile: un accesso compromesso può mettere a rischio anche le copie remote.

## 8. Cosa rclone fa già e cosa deve fare macbackup

| Compito | Responsabilità |
|---|---|
| Accesso ai provider e trasferimenti | rclone |
| Cifratura del contenuto privato e dei nomi | rclone crypt |
| Conservazione dei file sostituiti/cancellati | rclone sync con backup-dir, collaudato sul provider |
| Traduzione dei quattro elenchi in elenchi esatti per area, distinguendo inclusioni esatte da quelle ereditate | macbackup |
| Controlli delle sorgenti locali e classificazione | macbackup; l'identità di un mount esterno non è ancora verificata |
| Blocco delle esecuzioni concorrenti | macbackup |
| Riepilogo separato dei risultati | macbackup |
| Inventario delle versioni e recupero guidato | macbackup con operazioni rclone |
| Piani selettivi di forget e controllo dell'esito | macbackup con operazioni rclone supportate |

Non si devono combinare ingenuamente files-from con filtri di esclusione: rclone ignora gli altri filtri quando viene usato files-from. Gli elenchi dell'utente non devono essere presentati come un formato nativo di rclone.

Explicit-only non è un'opzione nativa di rclone. Il selettore applica le precedenze in Python sia ai file locali sia alle copie sotto current. Il trasporto passa a rclone soltanto un elenco esatto separato da NUL tramite files-from0, senza combinarlo con filtri di esclusione che sarebbero ignorati. L'elenco comprende i file ammessi e le vecchie copie ancora gestite da archiviare; le copie escluse o diventate dell'altra area non vi entrano e rimangono conservate. Un nuovo file apparso dopo la preparazione dell'elenco aspetta la run successiva. Non si passa a rclone un'inclusione ricorsiva della directory che possa aggirare la scelta dei singoli file protetti.

L'uso dei comandi rclone rimane possibile anche senza il programma, purché si conoscano i remotes e si usi quello crypt per l'area privata. Documentare i nomi effettivi dei remotes dopo la configurazione. Non fornire comandi distruttivi generici da eseguire a memoria.

## 9. Verifiche già fatte e verifiche necessarie

La suite locale attuale comprende 126 test con dati sintetici e veri comandi rclone su remotes locali e crypt. Copre la selezione e le precedenze, `.env` e gli altri nomi protetti, la cifratura automatica delle directory `.git`, i file ignorati con spazi nel nome, collegamenti simbolici, icone Finder, trasferimenti, storico, piani `forget`, `versions`, `restore` di file e symlink con `--links`, `verify`, il resoconto di run interrotte, i conteggi trasferiti e l'autocompletamento Zsh. La resa delle icone Finder è stata anche provata tramite AppKit.

Su Google Drive sono state eseguite prove isolate con file fittizi: copia plain e crypt, recupero di versioni correnti e storiche, `forget` permanente sulle copie di prova e `verify` ordinario e con download. I namespace di prova autorizzati sono stati rimossi e verificati assenti. Queste prove non equivalgono alla verifica dell'intera copia personale.

Il primo trasferimento dei dati personali su Google è stato interrotto e non ha ancora un esito `ok: true` per tutte le aree. Prima di chiamarlo backup riuscito occorrono una run completa, `macbackup verify --target google` e almeno tre prove di recupero in una directory separata: un file plain, un file private e un symlink con `restore --links`. `verify` confronta la copia corrente con i file locali del momento; eventuali modifiche locali dopo il backup vanno interpretate prima di concludere che la copia cloud è errata.

Proton non è ancora configurato né collaudato con l'account dell'utente. La rimozione `forget --mode trash` su Proton, una seconda run senza modifiche, il recupero delle chiavi da un Mac nuovo, il montaggio in sola lettura e l'automazione periodica restano da verificare o implementare come descritto nelle rispettive sezioni. La verifica dell'identità dei mount esterni, il ripristino automatico di un intero albero, le revisioni native e gli elementi già nel cestino dei provider non sono coperti dai comandi attuali.

## 10. Decisioni operative e lavoro rimanente

Sono già definite la posizione dello script nei dotfiles, i percorsi assoluti che rispecchiano il Mac, le aree plain/private, la cifratura di `.ssh`, `.config/rclone` e di tutte le directory `.git`, la protezione dei `.env`, le esclusioni concordate e i nomi ignorati in `settings.toml`. Una nuova esclusione o riclassificazione non elimina automaticamente le copie precedenti; per rimuoverle da `current` e `history` si usa un piano `forget` esplicito. Google è abilitato, Proton è ancora disabilitato.

Il prossimo traguardo è completare e verificare la copia Google avviata dall'utente. Poi si configura Proton Drive, si ripetono backup e recupero su quel servizio e si valuta il montaggio di consultazione in sola lettura. L'automazione si abilita solo dopo una prova riuscita di backup e recupero; non è prevista alcuna scadenza automatica dello storico.

Se diventa necessario ripristinare cartelle intere esattamente a una data, va valutato uno strumento a snapshot come restic. `macbackup` oggi conserva i file spostati nello storico per run, non fotografie complete della selezione a ogni data.

## 11. Fonti ufficiali

Consultate durante la progettazione e le verifiche dal 30 ottobre al 2 novembre 2026:

- [Rclone: filtri e files-from](https://rclone.org/filtering/)
- [Rclone: sync](https://rclone.org/commands/rclone_sync/)
- [Rclone: backup-dir](https://rclone.org/docs/#backup-dir-string)
- [Rclone: crypt e protezione della configurazione](https://rclone.org/crypt/)
- [Rclone: Google Drive, revisioni e cestino](https://rclone.org/drive/)
- [Rclone: Proton Drive e limitazioni](https://rclone.org/protondrive/)
- [Rclone 1.75.2: codice del backend Proton Drive](https://github.com/rclone/rclone/blob/v1.75.2/backend/protondrive/protondrive.go)
- [Rclone: delete e filtri](https://rclone.org/commands/rclone_delete/)
- [Rclone: purge ignora i filtri](https://rclone.org/commands/rclone_purge/)
- [Rclone: collegamenti simbolici](https://rclone.org/local/#symlinks-junction-points)
- [Rclone: cryptcheck](https://rclone.org/commands/rclone_cryptcheck/)
- [Google: gestione delle revisioni native](https://developers.google.com/workspace/drive/api/guides/manage-revisions)
- [Proton: eliminazione selettiva dal cestino nell'app](https://proton.me/support/proton-drive-mobile-manage-files-folders)
- [Proton: cancellazione e recupero di file sincronizzati](https://proton.me/support/proton-drive-delete-restore-synced-files)
- [Restic: snapshot e recupero](https://restic.readthedocs.io/en/stable/010_introduction.html)
- [Zsh: sistema di completamento, fpath, compinit e compdef](https://zsh.sourceforge.io/Doc/Release/Completion-System.html)
- [Proton Pass: elementi personalizzati](https://proton.me/support/create-custom-item)
- [Proton Pass: campi nascosti](https://proton.me/support/pass-custom-field)
