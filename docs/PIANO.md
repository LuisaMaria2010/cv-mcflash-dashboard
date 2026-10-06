# Piano di battaglia

Due repo lavorano insieme:

- **Autocompilazione CV_ON_SITE** (backend, Azure Functions): endpoint, generazione del CV MC, scrittura su MCFlash, storage e indice.
- **cv-mcflash-dashboard** (questo repo): interfaccia Streamlit, in locale. Per il front end **niente servizi Azure**: se va pubblicata si usa un hosting gratuito (fase 7).

Schemi: [architettura](img/01-architettura.svg) · [flusso](img/02-flusso.svg).

Ogni fase finisce con qualcosa che si può provare.

---

## Stato al 05/10/2026

| Fase | Stato | Cosa manca |
|---|---|---|
| 0 · Sblocchi | ✔ | la specifica dell'endpoint di scrittura MCFlash (intanto c'è il MCFlash finto) |
| 1 · Backend: lettura e match | ✔ | — |
| 2 · Pagina Candidati | ✔ | — |
| 3 · Caricamento, estrazione e revisione | ✔ | — |
| 4 · CV MC e anteprima | ✔ | — |
| 5 · Conferma | ◐ creazione provata sui sistemi reali | deploy del backend, poi prova dell'aggiornamento |
| 6 · Monitor delle operazioni | ✔ | una decisione sulle operazioni fallite per dati sbagliati |
| 7 · Rifinitura e consegna | ◐ README fatto | prova con 5–10 CV reali, casi limite, pubblicazione |

Test: 47 nella dashboard e 461 nel backend, tutti verdi. Nessun commit e nessun deploy in questo ciclo: tutto è nei working tree dei due repo.

### Cosa resta

Si può fare subito:

- prova con 5–10 CV reali, compresi aggiornamenti e omonimi di trittico (fase 7);
- revisione dei casi limite (fase 7);
- decidere se riaprire la bozza di un'operazione fallita prima dell'indice (fase 6).

Dipende dal deploy o da altri:

- pubblicare il backend sulla Function App (serve `az login`), poi ripetere la prova di un aggiornamento (fase 5);
- conversione del CV MC in PDF (LibreOffice in un container);
- endpoint di scrittura MCFlash: URL, autenticazione, payload, codici d'errore;
- pubblicazione della dashboard, con autenticazione e verifica privacy.

### Quale CV va dove

| CV | Uso | Destinazione |
|---|---|---|
| CV del dipendente (caricato) | solo `POST /api/extract?profile=mcflash`, per riempire il form | `incoming-cv-originals` (backup, lo salva già `/api/extract`); mai nell'indice |
| CV generato nel modello MC | depositato da `/api/cv/commit` in `incoming-cv` | ingestione esistente (blob trigger, profilo base) → indice |

---

## Fase 0 · Sblocchi

Da chiarire prima di scrivere codice.

- [x] **Modello CV MC**: preso come riferimento un CV MC reale. Struttura, campi e segnaposto sono in [MODELLO_MCFLASH.md](MODELLO_MCFLASH.md) ([schema](img/07-modello-mcflash.svg)).
- [x] **Modello `.docx`/`.dotx`** ricostruito nel backend (`templates/`, generato da `scripts/build_mcflash_template.py`). Provato su due CV reali, con risultato fedele all'originale.
- [x] **Email, telefono ed età**: li restituisce `/api/extract?profile=mcflash` (oppure `include_contacts=true` nel profilo base). Vanno solo sul record MCFlash, mai nel CV, che resta anonimo.
- [x] **Estrazione estesa** (`profile=mcflash`): nome e cognome separati, trittico, esperienze con azienda, ruolo e descrizione, formazione con anno e istituto, lingue con livello, skill con le maiuscole originali. L'ingestione resta sul profilo base, quindi indice e costi non cambiano.
- [x] **Progetti dentro il posto di lavoro**: ogni esperienza ha i suoi progetti, con periodo, nome, eventuale ruolo diverso, attività e tecnologie ("Attività: …", "Tecnologie utilizzate: …", come nei CV MC). Dalle tecnologie si tolgono i termini generici ("AI", "LLM", "frontend"…).
- [x] **Ruolo in ogni esperienza**: obbligatorio. Se il CV non lo dice lo deduce l'LLM; nel CV compare come "Ruolo: …".
- [x] **Ruolo in alto dal catalogo MC**: l'LLM sceglie uno dei ruoli di `infra/mcflash_budget_placeholders.json`, coerente con tutte le esperienze (`domain/role_catalog.py`). `GET /api/roles` restituisce il catalogo con le tariffe per il menu a tendina.
- [x] **Trainings** con anno, titolo ed ente.
- [x] **Livelli nella scala MC** (`domain/mc_levels.py`): skill → Conoscenza base / Buona / Ottima conoscenza; lingue → Base / Intermedio / Avanzato / Fluente / Madrelingua.
- [x] **Trittico**: prima lettera del nome + prime due lettere del cognome (`domain/candidate_identity.py`).
- [x] **Nome file**: `GET /api/cv/filename` propone il nome e le varianti libere; per un candidato esistente riusa il suo file, così l'indice lo sostituisce.
- [x] **Endpoint MCFlash di scrittura, segnaposto**: `MCFLASH_CANDIDATI_WRITE_URL` e `MCFLASH_CANDIDATI_WRITE_API_KEY` in `.env.example` del backend. Finché sono vuoti si usa il MCFlash finto (`infra/mcflash_writer.py`, fase 5).
- [x] **Chi usa la dashboard, in locale**: le chiamate al backend usano la chiave della Function (`FUNCTION_KEY`); il nome utente di bozze, operazioni e log viene da `DASHBOARD_USER` (di default l'utente Windows). Per una pubblicazione serve un'autenticazione vera (fase 7).
- [ ] **Specifica dell'endpoint MCFlash**, quando arriva: URL, autenticazione, payload di creazione e aggiornamento, codici d'errore, se restituisce l'`Id`.

## Fase 1 · Backend: lettura e match

Nel backend, blueprint `functions/dashboard_api.py`.

- [x] **`GET /api/candidates`**: lista dei candidati per la home. Legge tutti i record MCFlash e aggiunge, da `CvMcflashMap` e `DocumentRegistry`, il CV indicizzato con versione e stato.
  - Cache in memoria (`DASHBOARD_CANDIDATES_TTL_SECONDS`, default 120 s); `refresh=true` la salta.
  - Query: `q` (ricerca su id, trittico, nome, ruolo, sede), `sede`, `has_cv`, `tutti` (anche disabilitati e TalentUp), `limit`, `offset`.
  - Se lo storage non risponde la lista esce lo stesso, senza CV, con un avviso in `warnings`.
- [x] **`GET /api/candidates/{id}`**: dettaglio di un candidato (anche non idoneo), per pre-impostare la pagina Aggiorna; 404 se non esiste.
- [x] **`POST /api/candidates/match`** `{nome, cognome, trittico?}` (oppure `nome_completo`) → `{trittico, esito: nuovo|aggiorna|scegli, motivo, candidati, stesso_trittico}`. Prima il trittico, poi il nome (`domain/candidate_match.py`, [schema](img/05-match-candidato.svg)).
  - Il nome si confronta senza maiuscole, accenti, punteggiatura e spazi doppi, in qualunque ordine ("Rossi Mario" = "Mario Rossi") e con o senza spazi nel cognome ("D'Amico" = "Damico").
  - Il match guarda tutti i record, anche quelli non idonei, per non creare doppioni.
  - *Rete di sicurezza*: con lo stesso trittico e un nome simile (secondo nome solo nel CV o solo su MCFlash: "Maria Rossi" / "Maria Grazia Rossi") l'esito è "scegli", non "nuovo".
  - *Rete di sicurezza*: su MCFlash 16 record su 263 hanno un trittico fuori regola (nomi di 3–4 parole). Se per trittico il nome non si trova, ma lo stesso nome esiste con un altro trittico, l'esito è "scegli" su quei record.
- [x] **Test** (`tests/test_candidate_match.py`, `tests/test_dashboard_candidates_api.py`): 0, 1 e più trittici; omonimi; nome con accenti e in ordine inverso; trittico diverso su MCFlash; filtri, paginazione, cache, storage non disponibile, 404.
- [x] **Prova sui dati reali**: 98 candidati idonei (88 con CV e versione), 263 record in tutto. Ogni record cercato per trittico + nome dà "aggiorna"; con il trittico calcolato dal nome nessuno risulta "nuovo".

**Fatto quando**: da Postman o pytest si ottengono la lista e un esito di match corretto su candidati reali. ✔

## Fase 2 · Dashboard: scheletro e pagina Candidati

In questo repo ([schema della pagina](img/03-pagina-candidati.svg)).

- [x] **Struttura** (Streamlit 1.65, Python 3.12):
  ```
  app.py                  # entry Streamlit, navigazione con st.navigation (tab in alto)
  views/candidati.py      # le pagine stanno in views/: con pages/ Streamlit le mostrerebbe da sola nella barra laterale
  views/crea.py
  views/aggiorna.py
  views/operazioni.py
  dashboard/api.py        # client HTTP verso il backend
  dashboard/config.py     # BACKEND_URL, FUNCTION_KEY, DASHBOARD_USER da .env
  dashboard/components/   # anteprima CV, form dati, anteprima MCFlash, operazioni
  tests/
  ```
- [x] **Navigazione** con le tab in alto (`st.navigation(position="top")`). I pulsanti delle righe aprono `aggiorna?id=<IdMCFlash>`: la pagina è pre-impostata e si può salvare tra i preferiti.
- [x] **Pagina Candidati**: una tabella con **tutti** i record MCFlash (anche disabilitati e TalentUp) e **tutti i campi in chiaro**: id, codice, nome, CV, ruolo, seniority, età, sede, lingue, disponibilità, budget, site, abilitato, TalentUp, file CV.
  - Contatori in cima; ricerca e filtri (sede, CV) facoltativi, salvati nell'URL (`?q=&sede=&cv=`).
  - Selezionando una riga compare **Aggiorna**; ci sono anche **Nuovo candidato** e **Ricarica da MCFlash**.
- [x] **Veste grafica**: tema con i colori del modello CV MC (blu `#1F3864`) in `.streamlit/config.toml`, font Barlow, fascia blu in testa a ogni pagina, celle colorate (CV presente in verde, mancante in arancio, record disabilitati in grigio).
- [x] **Stato tra le pagine**: passa dall'URL (`st.query_params`) e da `st.session_state`, mai da finestre modali.
- [x] **Pagina Aggiorna**: intestazione del candidato (trittico, ruolo, sede), dati MCFlash attuali e cosa succede all'indice ("il nuovo CV sostituirà il v2").
- [x] **Errori del backend** mostrati nella pagina con il `request_id`; il backend risponde 502 se MCFlash non è raggiungibile.
- [x] **Test** (17): client HTTP, testi derivati, pagine con `streamlit.testing` e backend finto. Prova sul backend locale reale: 98 candidati, filtri e link Aggiorna corretti.

**Fatto quando**: `streamlit run app.py` mostra la lista reale e il click su Aggiorna apre la pagina giusta. ✔

## Fase 3 · Caricamento, estrazione e revisione

Nei due repo ([schema delle pagine Crea e Aggiorna](img/04-pagina-crea-aggiorna.svg)).

- [x] **Anteprima del CV originale** (`dashboard/components/cv_preview.py`): PDF incorporato con `st.pdf`, DOCX convertito in HTML con `mammoth`. Riaprendo una bozza il file arriva da `GET /api/drafts/{id}/original`.
- [x] **Estrazione**: `POST /api/extract?profile=mcflash` (multipart `file`, timeout 5 minuti) con indicatore di avanzamento. La risposta include `original_blob` e `original_filename`, così la bozza resta legata al file salvato in `incoming-cv-originals`.
- [x] **Trittico e nome file**: il trittico si ricalcola mentre l'utente modifica nome e cognome (stessa regola e stessi casi di test del backend). Il nome file proposto da `GET /api/cv/filename` resta modificabile; se l'utente lo cambia, non viene più sovrascritto.
- [x] **Form dei dati estratti** (`dashboard/components/cv_editor.py`), in quattro schede:
  - *Anagrafica*: nome, cognome, email, telefono, età, data di nascita, città, ruolo MC dal catalogo con le tariffe, ruolo scritto nel CV;
  - *Skill e lingue*: tabelle con il livello della scala MC (`GET /api/mc-levels`);
  - *Esperienze*: una scheda per esperienza, con progetti, attività e tecnologie; si aggiungono e si tolgono;
  - *Formazione*: formazione, trainings, certificazioni.

  Campi e schede modificati rispetto all'estratto hanno un pallino arancio, e il riepilogo elenca le sezioni cambiate. A mano si completano date dei progetti, anno dei corsi e livelli delle skill; se manca il ruolo di un'esperienza compare un avviso.
- [x] **Bozza** (`functions/drafts_api.py`): `PUT/GET/DELETE /api/drafts/{draft_id}`, `GET /api/drafts?kind=&id_mcflash=` e `GET /api/drafts/{id}/original`, su Blob `cv-drafts/<id>.json`.
  - Conserva l'estratto originale (mai sovrascritto: è il backup), la versione modificata e chi l'ha modificata (`DASHBOARD_USER`).
  - Salvataggio automatico a ogni modifica, più **Salva bozza**, **Scarica dati** (JSON) e **Scarta la bozza**.
  - La bozza sta nell'URL (`crea?bozza=<id>`, `aggiorna?id=<IdMCFlash>&bozza=<id>`); Crea e Aggiorna elencano le bozze da riprendere.
- [x] **Candidato già esistente**: nella pagina Crea, appena nome e cognome sono noti, la dashboard chiama `match`. Se il candidato esiste già lo segnala con ruolo, sede, età e CV: **È questa persona: aggiorna** trasforma la stessa bozza in un aggiornamento e apre la pagina Aggiorna; **È una persona diversa** lascia proseguire con la creazione.
- [x] **Confronto con MCFlash**: nella pagina Aggiorna una tabella affianca i dati MCFlash attuali (nome, codice, ruolo, sede, età, lingue) a quelli del CV, con in arancio i valori che cambiano.
- [x] **Bug corretto nel backend, DOCX letto come testo**: un DOCX inviato a `/api/extract` senza MIME veniva letto come testo; l'LLM riceveva lo ZIP grezzo, inventava i dati e il risultato restava in cache. Ora il DOCX si riconosce anche dal contenuto (`extraction/extract.py`) e la pipeline scarta il testo in cache che è uno ZIP grezzo, con l'estrazione LLM collegata (`db_data/pipeline.py`). L'ingestione non era colpita, perché passa il MIME.
- [x] **Test**: 35 nella dashboard (bozza, form, salvataggio automatico, passaggio da Crea ad Aggiorna, confronto); 8 per le bozze e 4 per il DOCX nel backend. Prova nel browser con `tests/sample_cv.docx`: caricamento, estrazione, correzione dell'email, pagina chiusa, bozza ripresa con la correzione.

**Fatto quando**: si carica un CV, si correggono i dati, si chiude la pagina e la bozza si ritrova. ✔

## Fase 4 · Generazione del CV MC e anteprima

Nel backend:

- [x] **Motore di compilazione**: `services/cv_mcflash_renderer.py` (`build_context` + `render_docx`, con `docxtpl`). Gestisce progetti, "Ruolo:", "Attività:", "Tecnologie utilizzate:", Trainings, ruolo dal catalogo, e righe di skill, lingue e titoli che non si spezzano tra due pagine. I test verificano compilazione, sezioni vuote omesse e anonimato.
- [x] **Prova locale del giro completo**: `scripts/render_mcflash_cv.py <cv> --out-dir … --pdf` (estrazione → CV MC → PDF con Word).
- [x] **`POST /api/cv/render`** `{data, format: both|docx|html}` (`functions/cv_render_api.py`) → `{html, docx_base64, docx_bytes, checks}`.
  - Il `.docx` esce dal motore; l'HTML da `services/cv_mcflash_preview.py` con **lo stesso contesto**, quindi contenuti e ordine delle sezioni coincidono.
  - Email, telefono, età e nome si tolgono prima della validazione: non entrano nel CV, e un'email scritta male non blocca l'anteprima.
  - `checks` elenca cosa completare: ruolo MC, data di nascita, città, ruoli e periodi delle esperienze, progetti senza date, skill senza livello, trainings senza anno.
- [x] **Anteprima HTML** con il layout del modello (logo, figura vitruviana, "Candidate Profile", barre grigie con titolo blu in maiuscoletto, etichette in corsivo, footer con le sedi), su una pagina continua. Il PDF si genera solo alla conferma (fase 5): in locale con Word, sulla Function App serve LibreOffice in un container.

Nella dashboard:

- [x] **Colonna Anteprima CV MC** con l'elenco "Da completare" e **Scarica .docx** (nome dal campo "Nome del file CV"). Si rigenera solo quando i dati cambiano: Streamlit riesegue la pagina a ogni modifica confermata di un campo (invio o uscita dal campo), che fa da debounce, e la chiamata è in cache sul JSON dei dati.
- [x] **Layout come nel disegno**: barra di riepilogo in alto (trittico, modifiche, nome file, stato della bozza, Salva/Dati/Scarta) e tre colonne: CV caricato, dati estratti, anteprima del CV MC. Nella pagina Aggiorna il confronto con MCFlash sta sopra le colonne.
- [x] **Test**: 6 nel backend (formati, testo escapato, CV anonimo, email non valida, controlli, sezioni vuote) e 1 nella dashboard (l'anteprima segue il form e non si rigenera senza modifiche). Prova nel browser: cambiata la città nel form, l'anteprima si aggiorna; il `.docx` scaricato è valido, ha la nuova città e non contiene nome, email o telefono.

**Fatto quando**: l'anteprima riflette subito le correzioni del form. ✔

## Fase 5 · Conferma: storage, MCFlash, indice, mappa

Nel backend, `POST /api/cv/commit` `{draft_id}` (`functions/operations_api.py`, logica in `services/cv_commit.py`). Ogni conferma crea una riga in `CvOperations` (Table Storage), con una colonna per passo; i passi si eseguono in ordine e l'operazione si salva dopo ognuno.

### I quattro passi

1. [x] **Storage (storico)**: il CV originale è già in `incoming-cv-originals` (lo salva `/api/extract`) e il commit ne registra il percorso. In un aggiornamento il CV MC attuale (trovato da `CvMcflashMap` + `DocumentRegistry`) si copia in `cv-history/<id_mcflash>/<data>_<nome file>`.
2. [x] **MCFlash**: crea o aggiorna la riga.
   - Finché `MCFLASH_CANDIDATI_WRITE_URL` è vuoto si usa il **MCFlash finto** (`infra/mcflash_writer.py`): le scritture vanno nella tabella `McflashFake` (Id dei creati da 900001) e la lista della dashboard le sovrappone ai record veri, quindi un candidato creato compare subito, con "(finto)" accanto al nome. La ricerca non lo vede.
   - Quando arriva l'endpoint vero basta valorizzare URL e chiave: `HttpMCFlashWriter` fa POST per creare e PUT `/<id>` per aggiornare (payload e risposta da verificare con la specifica).
   - Per *crea* l'`Id` si salva subito nell'operazione, così un nuovo tentativo non crea un secondo candidato.
   - I campi che il CV non ha (seniority, disponibilità, budget, site) stanno nella scheda **MCFlash** del form. In un aggiornamento valgono quelli del record; per un nuovo candidato la seniority è quella stimata dall'estrazione e il budget viene dalla tariffa del catalogo per ruolo e seniority (si ricalcola quando cambiano, se non è stato scritto a mano). Email e telefono vanno su MCFlash, mai nel CV.
3. [x] **Indice**: genera il CV MC e lo deposita in `incoming-cv` con il nome della bozza; la pipeline esistente lo normalizza e lo indicizza. **Per ora `.docx`**: il PDF arriverà con la conversione, e il nome resterà lo stesso cambiando solo l'estensione.
   - *Nuovo*: il nome non deve essere già usato da un altro CV (`incoming-cv` e `CvMcflashMap`), altrimenti il passo si ferma e chiede di cambiarlo.
   - *Aggiorna*: stesso nome del CV attuale → stesso `document_id` (l'estensione non conta) e versione +1, quindi l'indice sostituisce il vecchio CV. Con una versione nuova l'ingestione cancella prima tutti i chunk del documento, e un CV più corto non lascia chunk in più. Il vecchio file, già nello storico, si toglie da `incoming-cv`.
   - *Registro* (`infra/document_registry.py`, corretto): lo stesso documento da un percorso diverso (`X.pdf` → `X.docx`) ripartiva da versione 1 in una riga nuova; ora continua dalla versione più alta e la dashboard mostra quella.
4. [x] **Mappa**: quando `DocumentRegistry` segna il nuovo file come `processed`, aggiorna `CvMcflashMap` (`document_id → id_mcflash`, `file`, `codice`, `criterio = "dashboard"`, `updated_at`) e toglie le altre righe dello stesso candidato: un solo CV per candidato. Fino ad allora il passo è "in attesa" e l'operazione "in corso"; `GET /api/operations/{id}` ricontrolla e completa.

### Garanzie

- [x] **Passi idempotenti**: `POST /api/operations/{id}/retry` (pulsante **Riprova**) riparte dal passo fallito o in attesa, senza ripetere quelli fatti.
- [x] **Ordine sicuro**: se MCFlash fallisce, l'indice non viene toccato (c'è un test).
- [x] **Una conferma sola**: una seconda conferma della stessa bozza restituisce la stessa operazione; dopo, la bozza non si modifica più ed esce da "Bozze da riprendere".

### Dashboard e strumenti

- [x] **Conferma e carica**, con il riepilogo di cosa succede; disattivato finché mancano trittico, ruolo, seniority o site. Dopo la conferma la pagina mostra il pannello dell'operazione (un badge per passo, errore e **Riprova**), aggiornato ogni 5 secondi finché è in corso, accanto al CV MC caricato.
- [x] **`scripts/delete_dashboard_cv.py <operation_id> [--yes] [--with-original]`**: toglie tutto ciò che una conferma "crea" ha prodotto (indice, registro, markdown, `incoming-cv`, mappa, MCFlash finto, bozza). Serve per i CV di prova; rifiuta le operazioni "aggiorna".
- [x] **Test**: 10 sul servizio (passi, attesa dell'indicizzazione, errore MCFlash e ripresa, nome già usato, dati MCFlash mancanti, storico e sostituzione, cambio di nome), 4 sugli endpoint, 2 sul registro; 4 nella dashboard (dati MCFlash, budget dalla tariffa, conferma, bozza confermata in sola lettura).

### Prova sull'ambiente reale (05/10/2026)

- [x] CV finto di Mario Rossi, confermato dal browser: MCFlash finto Id 900001 → `.docx` in `incoming-cv` → la Function App pubblicata lo indicizza in circa 8 minuti → mappa aggiornata, candidato in lista con CV v1. Poi tutto il materiale di prova è stato tolto (indice, registro, mappa, MCFlash finto, bozze, storico, originali).
- [x] La prova ha trovato tre bug, corretti nel codice ma **non ancora pubblicati**:
  - **Mappa aggiornata troppo presto negli aggiornamenti.** Con lo stesso nome file, la riga della versione vecchia sembrava già quella nuova. Ora l'operazione registra la versione presente prima del caricamento e aspetta una versione più alta.
  - **DOCX senza tabelle** (`extraction/extract.py`). L'estrazione leggeva solo i paragrafi: un CV nel modello MC, tutto in tabelle, diventava "Information, Education…". Nell'indice non entrava contenuto, e tutti i CV MC avevano lo stesso hash, quindi dal secondo in poi il registro li scartava come duplicati.
    - Ora le tabelle si leggono nell'ordine del documento, e le chiavi della cache di `/api/extract` hanno una versione, così i DOCX già estratti si rileggono.
    - Il registro (`DocumentRegistry.should_process`) non scarta più come duplicato un documento con meno di 300 caratteri di testo solo perché ha lo stesso hash di **un altro** documento: lo indicizza per conto suo e lo segnala nel log. Lo stesso CV caricato con un altro nome (testo pieno) resta un duplicato.
    - Archivio attuale: i DOCX sono 3 su 962 file (`Skill_Tecnico_FPA.docx`, `Skill_Tecnico_FPE_MC.docx` e il vecchio `sample_cv.docx`). FPA e FPE erano stati letti vuoti nel backfill del 07/05, ma **nessun contenuto è perso**: per entrambi c'è il PDF con lo stesso nome, che per l'indice è lo stesso documento ed è stato letto bene (v2). Rielaborare i DOCX sostituirebbe i chunk buoni del PDF, quindi **non si rielaborano** (decisione del 05/10). Per i casi futuri resta `scripts/reprocess_incoming_cv.py`, che rielabora da locale file già in `incoming-cv`.
  - **I chunk vecchi non si cancellavano mai** (`infra/search_service.py`, `await` mancante in `delete_chunks`). A ogni nuova versione di un CV i chunk della precedente restavano nell'indice, e la ricerca non filtra per versione. Le versioni vecchie venivano dalle rielaborazioni del 30/04 (6 documenti) e soprattutto dal backfill di tutto l'archivio del 07/05 (829 documenti).
    - **Pulizia fatta il 05/10** con `scripts/purge_stale_chunks.py --yes`, da locale: per ogni documento restano solo i chunk della versione più alta presente nell'indice. Cancellati 5.462 chunk di 835 documenti; l'indice è passato da 10.177 a 4.715 chunk, sempre 949 documenti, senza versioni vecchie residue. I markdown delle versioni vecchie restano in `normalized-cv-md`.
    - Finché la Function App gira con il codice vecchio, una nuova versione lascia di nuovo indietro i chunk precedenti: lo script si può rilanciare.

### Per chiudere la fase

- [ ] Pubblicare il backend sulla Function App: le correzioni su DOCX con tabelle, registro e `delete_chunks` servono all'ingestione. Da qui il deploy non si può fare senza `az login`.
- [ ] Ripetere la prova con un aggiornamento (crea + aggiorna sul candidato finto), verificare che nell'indice resti solo la versione nuova, poi cancellare di nuovo il materiale di prova.

**Fatto quando**: un aggiornamento lascia nell'indice un solo CV per quel candidato, quello nuovo, e la ricerca lo restituisce.

## Fase 6 · Monitor delle operazioni

Nei due repo ([schema della pagina](img/06-pagina-operazioni.svg)).

- [x] **`GET /api/operations?da=&stato=&utente=`**: legge `CvOperations` (fatto con la fase 5).
- [x] **`POST /api/operations/{id}/retry`**: fatto con la fase 5; il pulsante **Riprova** c'è sia nel pannello dopo la conferma sia nella pagina Operazioni.
- [x] **Pagina Operazioni** (`views/operazioni.py`, `dashboard/components/operations.py`):
  - filtri per periodo (oggi, 7 giorni, 30 giorni, tutte), stato e utente, salvati nell'URL insieme all'operazione scelta (`?periodo=&stato=&utente=&op=`);
  - contatori colorati: operazioni, completate, in corso, fallite;
  - tabella con una colonna per passo (Storage, MCFlash, Indice, Mappa), colorata per esito (fatto, in attesa, errore, da fare), e il testo dell'errore;
  - selezionando una riga, il dettaglio: passi, errore leggibile, **Riprova**, link al candidato e alla bozza confermata, `operation_id` e `request_id` da cercare nei log;
  - finché ci sono operazioni in corso, un controllo ogni 5 secondi le fa avanzare (il passo mappa aspetta l'indicizzazione) e ridisegna la pagina solo se qualcosa è cambiato.
- [x] **Log**: ogni passo della conferma emette l'evento `cv_commit_step` con `operation_id`, passo, esito, Id MCFlash, `document_id` ed errore; l'operazione conserva l'ultimo `request_id`. Nei log della Function si cerca prima per `operation_id`, poi per `request_id`.
- [x] **Test**: 4 sulle funzioni della pagina, 3 sulla pagina (contatori e avanzamento delle operazioni in corso, dettaglio e **Riprova** dall'URL, filtri), 1 sui log nel backend. Prova nel browser sul backend reale con un'operazione fallita di proposito (dati MCFlash mancanti, indice non toccato), poi cancellata.
- [ ] **Da decidere: operazioni fallite per dati sbagliati.** Oggi non si correggono: la bozza confermata non si modifica più e **Riprova** rifà lo stesso passo con gli stessi dati. Dalla dashboard il caso è raro, perché la conferma è bloccata finché mancano dati, ma l'endpoint MCFlash reale potrebbe rifiutare dei valori. Proposta: se l'operazione è fallita prima dell'indice, permettere di riaprire la bozza, correggerla e riprovare.

## Fase 7 · Rifinitura e consegna

- [x] **README** con l'avvio locale: `.env`, `pip install -r requirements.txt`, `streamlit run app.py`, e il `func start --functions …` del backend con solo gli endpoint della dashboard.
- [ ] **Prova con 5–10 CV reali**: nuovi, aggiornamenti, omonimi di trittico. Finora 3 CV per estrazione e generazione (DCA, ADA e LSE), tra cui un CV non MC, in inglese, su due colonne.
- [ ] **Revisione dei casi limite**: CV senza codice, nome assente, CV in inglese, file danneggiati, file troppo grandi.
- [ ] **Pubblicazione della dashboard** (fuori da questo ciclo). Vincolo: niente servizi Azure per il front end, solo hosting gratuito.
  - Proposta: **Streamlit Community Cloud**, gratuito, con app privata visibile solo agli indirizzi invitati e collegata al repo GitHub (anche privato). `BACKEND_URL` e `FUNCTION_KEY` vanno nei *secrets* dell'app. La dashboard chiama il backend dal server Streamlit, quindi non serve CORS sulla Function.
  - Alternativa: Hugging Face Spaces privato.
  - Da valutare prima: i dati personali dei candidati passerebbero da un servizio esterno all'azienda.

---

## Endpoint del backend per la dashboard

| Metodo | Route | Scopo | Fase |
|---|---|---|---|
| POST | `/api/extract?profile=mcflash` | estrazione completa per il modello MC, contatti inclusi | 0 ✔ |
| GET | `/api/cv/filename` | trittico → nome file libero (o quello attuale per un aggiornamento) | 0 ✔ |
| GET | `/api/roles` | catalogo dei ruoli MC con tariffe, per il menu "Ruolo" | 0 ✔ |
| GET | `/api/candidates` | lista candidati + stato CV | 1 ✔ |
| GET | `/api/candidates/{id}` | dettaglio candidato | 1 ✔ |
| POST | `/api/candidates/match` | trittico + nome → nuovo / aggiorna / scegli | 1 ✔ |
| GET | `/api/mc-levels` | scale dei livelli MC per skill e lingue | 3 ✔ |
| PUT/GET/DELETE | `/api/drafts/{draft_id}` | bozza dei dati modificati (backup) | 3 ✔ |
| GET | `/api/drafts` | bozze da riprendere (filtri `kind`, `id_mcflash`) | 3 ✔ |
| GET | `/api/drafts/{draft_id}/original` | CV originale della bozza, per l'anteprima | 3 ✔ |
| POST | `/api/cv/render` | CV MC dal modello + anteprima | 4 ✔ |
| POST | `/api/cv/commit` | storage, MCFlash, indice, mappa | 5 ✔ (manca il deploy) |
| GET | `/api/operations/{id}` | stato di un'operazione (avanza se aspetta l'indicizzazione) | 5 ✔ |
| GET | `/api/operations` | monitor delle operazioni | 6 ✔ |
| POST | `/api/operations/{id}/retry` | riprova dal passo fallito | 6 ✔ |

## Rischi e domande aperte

- **Backend non pubblicato**: le correzioni di questo ciclo (DOCX con tabelle, cache di `/api/extract`, registro, `delete_chunks`, MCFlash finto, conferma) sono solo nel codice locale. La Function App pubblicata ha ancora i bug: un DOCX a tabelle viene letto vuoto, e una nuova versione di un CV lascia nell'indice i chunk della precedente.
- **Endpoint di scrittura MCFlash**: finché non arriva, il passo 2 della fase 5 usa il MCFlash finto (tabella `McflashFake`). Quando arriva basta riempire `MCFLASH_CANDIDATI_WRITE_URL` e la chiave, e verificare payload e risposta (`HttpMCFlashWriter` assume POST per creare, con `{"id"}` in risposta, e PUT `/<id>` per aggiornare).
- **CV MC in PDF**: l'indice deve ricevere il PDF, ma per ora la conferma carica il `.docx`. Serve la conversione: Word in locale, LibreOffice in un container sulla Function App.
- **Font**: il modello usa Bahnschrift Light e Calibri, presenti su Windows. Per convertire in PDF su Linux vanno installati nel container, altrimenti vengono sostituiti.
- **Fedeltà del modello**: il `.docx` è ricostruito da un PDF. Se in azienda esiste il `.dotx` originale conviene confrontarlo; per cambiare il layout si modifica `scripts/build_mcflash_template.py` e si rigenera il modello.
- **Sostituzione nell'indice**: l'indicizzazione è asincrona (blob trigger → code; nella prova circa 8 minuti), quindi la mappa si aggiorna solo quando il registro mostra una versione nuova elaborata. Un CV ricaricato identico (stesso testo) non crea una versione nuova, e l'operazione resterebbe "in attesa".
- **Costi e tempi del profilo mcflash**: l'output è molto più lungo di quello base (limite portato a 8000 token, timeout 180 s, configurabili con `MCFLASH_LLM_MAX_TOKENS` e `MCFLASH_LLM_TIMEOUT_SECONDS`). Va bene per l'uso puntuale della dashboard, non per un'ingestione massiva.
- **Trittico non univoco**: è un problema noto (vedi `build_cv_mcflash_map.py`). Il nome risolve quasi tutti i casi; quelli restanti li sceglie l'utente.
- **Dati personali**: la dashboard mostra contatti e data di nascita. In locale va bene, ma prima di qualunque pubblicazione serve l'autenticazione. Con un hosting gratuito esterno i dati passano da un fornitore terzo: va verificato con chi si occupa di privacy.
