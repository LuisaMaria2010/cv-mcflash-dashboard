# Piano di battaglia

Due repo lavorano insieme:

- **Autocompilazione CV_ON_SITE** (backend, Azure Functions): nuovi endpoint, generazione del CV MCFlash, scrittura su MCFlash, storage e indice.
- **cv-mcflash-dashboard** (questo repo): interfaccia Streamlit in locale.

Ogni fase finisce con qualcosa che si può provare. Le fasi 1 e 2 si possono fare in parallelo.

**Quale CV va dove**

| CV | Uso | Destinazione |
|---|---|---|
| CV del dipendente (caricato) | solo `POST /api/extract?profile=mcflash`, per riempire il form | `incoming-cv-originals` (backup, lo salva già `/api/extract`); mai nell'indice |
| CV generato nel modello MC | depositato da `/api/cv/commit` in `incoming-cv` | ingestione esistente (blob trigger, profilo base) → indice |

---

## Fase 0 · Sblocchi (prima di scrivere codice)

- [x] **Modello CV MCFlash**: preso come riferimento un CV MC reale. Struttura, campi e segnaposto sono in [MODELLO_MCFLASH.md](MODELLO_MCFLASH.md).
- [x] **Modello `.docx`/`.dotx` ricostruito** nel backend (`templates/`, generato da `scripts/build_mcflash_template.py`). Provato su due CV reali, con risultato fedele all'originale.
- [x] **Email, telefono ed età**: `/api/extract?profile=mcflash` li include (oppure `include_contacts=true` nel profilo base). Vanno solo sul record MCFlash, mai nel CV, che resta anonimo.
- [x] **Estrazione estesa** (`profile=mcflash`): nome e cognome separati, trittico, esperienze con azienda, ruolo e descrizione, formazione con anno e istituto, lingue con livello, skill con le maiuscole originali. L'ingestione resta sul profilo base: indice e costi non cambiano.
- [x] **Trittico**: prima lettera del nome + prime due lettere del cognome (`domain/candidate_identity.py`).
- [x] **Nome file**: `GET /api/cv/filename` propone il nome e le varianti libere; per un candidato esistente riusa il suo file, così l'indice lo sostituisce.
- [x] **Endpoint MCFlash di scrittura**: arriverà dopo. Intanto ci sono i segnaposto `MCFLASH_CANDIDATI_WRITE_URL` e `MCFLASH_CANDIDATI_WRITE_API_KEY` in `.env.example` del backend. Finché sono vuoti, il backend usa un **MCFlash finto**: registra cosa avrebbe scritto e restituisce un Id fittizio.
- [ ] Quando arriva l'endpoint servono: URL, autenticazione, payload di creazione e aggiornamento, codici d'errore, se restituisce l'`Id`.
- [ ] Definire chi può usare la dashboard e come la riconosciamo. In locale basta una chiave Function per le chiamate e il nome utente nel log.

## Fase 1 · Backend: lettura e match

Nel repo backend, nuovo blueprint `functions/dashboard_api.py`.

- [ ] `GET /api/candidates`: lista dei candidati per la home. Riusa `MCFlashCandidatesClient.fetch_candidates` (oppure legge `CandidatesSnapshot` se serve velocità) e aggiunge, da `CvMcflashMap`, se c'è un CV indicizzato e la sua versione. Supporta paginazione e ricerca testuale.
- [ ] `GET /api/candidates/{id}`: dettaglio di un candidato, per pre-impostare la pagina Aggiorna.
- [ ] `POST /api/candidates/match` `{trittico, nome, cognome}` → `{esito: nuovo|aggiorna|scegli, candidati: [...]}`. Implementa la regola trittico, poi nome (vedi `docs/img/05-match-candidato.svg`). Il nome si normalizza togliendo maiuscole, accenti e spazi doppi.
- [ ] Test: casi 0, 1 e più trittici; omonimi; nome con accenti.

**Fatto quando**: da Postman o pytest si ottengono la lista e un esito di match corretto su candidati reali.

## Fase 2 · Dashboard: scheletro e pagina Candidati

In questo repo.

- [ ] Struttura del progetto:
  ```
  app.py                  # entry Streamlit, navigazione con st.navigation (tab in alto)
  pages/candidati.py
  pages/crea.py
  pages/aggiorna.py
  pages/operazioni.py
  dashboard/api.py        # client HTTP verso il backend
  dashboard/config.py     # BACKEND_URL, FUNCTION_KEY da .env
  dashboard/components/   # anteprima CV, form dati, anteprima MCFlash
  tests/
  ```
- [ ] Navigazione con le tab in alto (`st.navigation(position="top")`). I pulsanti delle righe aprono `aggiorna` passando `?id=<IdMCFlash>` nell'URL, così la pagina è pre-impostata e si può anche salvare tra i preferiti.
- [ ] Pagina **Candidati**: tabella con ricerca e filtri (sede, CV presente sì/no), il pulsante Aggiorna per riga e il pulsante "+ Nuovo candidato".
- [ ] Lo stato tra le pagine passa dall'URL (`st.query_params`) e da `st.session_state`, mai da finestre modali.

**Fatto quando**: `streamlit run app.py` mostra la lista reale e il click su Aggiorna apre la pagina giusta.

## Fase 3 · Caricamento, estrazione e revisione

- [ ] Componente **anteprima CV originale**: PDF incorporato; DOCX convertito in HTML (es. `mammoth`).
- [ ] Chiamata a `POST /api/extract?profile=mcflash` (multipart `file`) con indicatore di avanzamento: su un CV lungo l'LLM impiega fino a un paio di minuti.
- [ ] Nel form, il trittico si ricalcola mentre l'utente modifica nome e cognome (stessa regola del backend). Il nome file proposto da `GET /api/cv/filename` resta modificabile.
- [ ] **Form dati estratti**: campi semplici e liste modificabili per skill, esperienze, lingue e titoli. I campi modificati dall'utente vengono evidenziati.
- [ ] **Bozza**: nuovo endpoint `PUT /api/drafts/{draft_id}` (Blob `cv-drafts/`). Salva l'estratto originale e la versione modificata, così resta il backup e si vede cosa è stato corretto. Il salvataggio è automatico a ogni modifica e c'è anche il pulsante "Salva bozza".
- [ ] Nella pagina **Crea**, dopo l'estrazione, la dashboard chiama `match`: se il candidato esiste già lo segnala e propone di passare ad Aggiorna.
- [ ] Nella pagina **Aggiorna**, i dati MCFlash attuali sono affiancati a quelli estratti, per vedere cosa cambia.

**Fatto quando**: si carica un CV, si correggono i dati, si chiude la pagina e la bozza si ritrova.

## Fase 4 · Generazione CV MCFlash e anteprima

Nel backend.

- [x] Modello e motore di compilazione: `services/cv_mcflash_renderer.py` (`build_context` + `render_docx`, con `docxtpl`). I test verificano compilazione, sezioni vuote omesse e anonimato.
- [ ] `POST /api/cv/render` `{dati}` → `.docx` compilato, più un PDF o HTML per l'anteprima.
- [ ] Conversione in PDF: in locale funziona con Word (`scripts/render_mcflash_cv.py --pdf`); sulla Function App (Linux) serve LibreOffice headless in un container, oppure un'anteprima HTML. Proposta: HTML per l'anteprima live e PDF solo alla conferma.

Nella dashboard:

- [ ] Colonna **Anteprima CV MCFlash**, rigenerata dopo una pausa nelle modifiche (debounce), e pulsante "Scarica .docx".

**Fatto quando**: l'anteprima riflette subito le correzioni del form.

## Fase 5 · Conferma: storage, MCFlash, indice, mappa

Nel backend, `POST /api/cv/commit` `{draft_id, esito, id_mcflash?}`. Per ogni operazione si crea una riga in `CvOperations` (Table Storage) e i passi si eseguono in ordine, aggiornando lo stato:

1. [ ] **Blob (storico)**: il CV originale è già in `incoming-cv-originals` (lo salva `/api/extract`): il commit ne registra solo il percorso. Per un aggiornamento copia il vecchio CV MC in uno storico (es. `cv-history/<id_mcflash>/<data>_<nome file>`) prima che venga sovrascritto.
2. [ ] **MCFlash**: crea o aggiorna la riga con l'endpoint di scrittura (per ora il MCFlash finto). Per *crea* salva l'`Id` restituito.
3. [ ] **Indice**: deposita il CV MC generato in `incoming-cv` con il nome proposto da `/api/cv/filename`, così la pipeline esistente lo normalizza e lo indicizza.
   - *nuovo*: nome libero (variante con spazi, underscore o trattini), quindi documento nuovo e semplice aggiunta;
   - *aggiorna*: **stesso nome file** del CV attuale del candidato, quindi stesso `document_id` e versione +1: l'indice sostituisce il vecchio CV. Da verificare in fase 5 che l'indicizzatore cancelli i chunk in più quando il nuovo CV è più corto del vecchio.
4. [ ] **Mappa**: aggiorna `CvMcflashMap` (`document_id → id_mcflash`, `file`, `criterio = "dashboard"`, `updated_at`). Per un nuovo candidato il passo parte quando il `document_id` passa a `indexed` in `DocumentRegistry`; per un aggiornamento la riga c'è già e cambia solo `updated_at`.
- [ ] Ogni passo è **idempotente**, così "Riprova" riparte dal passo fallito senza duplicare righe su MCFlash o documenti nell'indice.
- [ ] Ordine sicuro: se MCFlash fallisce, l'indice non viene toccato.
- [ ] Test end-to-end su un ambiente di prova (non sulla tabella MCFlash reale) per entrambi i casi.

**Fatto quando**: un aggiornamento lascia nell'indice un solo CV per quel candidato, quello nuovo, e la ricerca lo restituisce.

## Fase 6 · Monitor delle operazioni

- [ ] `GET /api/operations?da=&stato=&utente=`: legge `CvOperations`.
- [ ] `POST /api/operations/{id}/retry`.
- [ ] Pagina **Operazioni**: contatori (completate, in corso, fallite), tabella con una colonna per passo, dettaglio dell'errore e pulsante Riprova. Aggiornamento automatico ogni pochi secondi mentre ci sono operazioni in corso.
- [ ] Log applicativi con `operation_id` (usando `utils/request_context.py` e `utils/observability.py`), così si collega la riga del monitor ai log della Function.

## Fase 7 · Rifinitura e consegna

- [ ] README con avvio locale: `.env`, `pip install -r requirements.txt`, `streamlit run app.py`.
- [ ] Prova con 5–10 CV reali (nuovi, aggiornamenti, omonimi di trittico).
- [ ] Revisione dei casi limite: CV senza codice, nome assente, CV in inglese, file danneggiati, file troppo grandi.
- [ ] Decidere se e dove pubblicare la dashboard (fuori da questo ciclo).

---

## Nuovi endpoint backend in sintesi

| Metodo | Route | Scopo | Fase |
|---|---|---|---|
| POST | `/api/extract?profile=mcflash` | estrazione completa per il modello MC, contatti inclusi | 0 ✔ |
| GET | `/api/cv/filename` | trittico → nome file libero (o quello attuale per un aggiornamento) | 0 ✔ |
| GET | `/api/candidates` | lista candidati + stato CV | 1 |
| GET | `/api/candidates/{id}` | dettaglio candidato | 1 |
| POST | `/api/candidates/match` | trittico + nome → nuovo / aggiorna / scegli | 1 |
| PUT/GET | `/api/drafts/{draft_id}` | bozza dei dati modificati (backup) | 3 |
| POST | `/api/cv/render` | CV MCFlash dal modello + anteprima | 4 |
| POST | `/api/cv/commit` | Blob, MCFlash, indice, mappa | 5 |
| GET | `/api/operations` | monitor | 6 |
| POST | `/api/operations/{id}/retry` | riprova dal passo fallito | 6 |

## Rischi e domande aperte

- **Fedeltà del modello**: il `.docx` è ricostruito da un PDF. Se in azienda esiste il `.dotx` originale conviene confrontarlo; per cambiare il layout si modifica `scripts/build_mcflash_template.py` e si rigenera il modello.
- **Font**: il modello usa Bahnschrift Light e Calibri, presenti su Windows. Una conversione in PDF su Linux richiede di installarli nel container, altrimenti vengono sostituiti.
- **Costi e tempi del profilo mcflash**: l'output è molto più lungo di quello base (limite portato a 8000 token, timeout 180 s, configurabili con `MCFLASH_LLM_MAX_TOKENS` e `MCFLASH_LLM_TIMEOUT_SECONDS`). Va bene per l'uso puntuale della dashboard, non per un'ingestione massiva.
- **Endpoint di scrittura MCFlash**: finché non arriva, il passo 2 della fase 5 usa il MCFlash finto. Quando arriva, basta riempire `MCFLASH_CANDIDATI_WRITE_URL` e la chiave.
- **Sostituzione nell'indice**: oggi l'indicizzazione è asincrona (code `document-processing` e `document-indexing`), quindi la mappa va aggiornata solo dopo che il nuovo documento è indicizzato, altrimenti per qualche minuto la ricerca non trova il CV.
- **Trittico non univoco**: lo sappiamo già (vedi `build_cv_mcflash_map.py`). Il nome risolve quasi tutti i casi, quelli restanti li sceglie l'utente.
- **Dati personali**: la dashboard mostra contatti e data di nascita. Va bene in locale, ma prima di qualunque pubblicazione serve l'autenticazione.
