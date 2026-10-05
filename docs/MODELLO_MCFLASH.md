# Modello CV MCFlash

Il CV che la dashboard genera è il "Candidate Profile" MC Engineering. Il modello è stato ricostruito da un CV MC reale e vive nel backend (**Autocompilazione CV_ON_SITE**):

| File | A cosa serve |
|---|---|
| `templates/cv_mcflash.docx` | modello con i segnaposto, usato dal backend per generare il CV |
| `templates/cv_mcflash.dotx` | lo stesso documento come modello di Word, da aprire e ritoccare a mano |
| `templates/assets/` | logo, figura vitruviana, footer con le sedi (estratti dal CV di riferimento) |
| `scripts/build_mcflash_template.py` | rigenera `.docx` e `.dotx`: il layout si cambia qui, non a mano nel file |
| `services/cv_mcflash_renderer.py` | dati estratti (anche corretti dalla dashboard) → contesto → `.docx` |
| `scripts/render_mcflash_cv.py` | prova locale del giro completo: CV → estrazione → CV MCFlash (`--pdf` con Word) |

Il CV di riferimento è in `docs/modello/riferimento/`, solo in locale ed escluso da git perché contiene i dati di un candidato.

![Modello MCFlash](img/07-modello-mcflash.svg)

## Sezioni, segnaposto e origine dei dati

Le sezioni sono in quest'ordine; quelle con lista vuota spariscono dal CV.

| Sezione | Segnaposto | Da `/api/extract?profile=mcflash` | Formato nel CV |
|---|---|---|---|
| Information | `codice` | `trittico` | 3 lettere maiuscole, grassetto |
| | `data_nascita` | `birth_date` | `GG/MM/AAAA` |
| | `citta` | `location` | |
| | `ruolo` | `catalog_role`: uno dei ruoli di `infra/mcflash_budget_placeholders.json`, scelto dall'LLM in modo coerente con tutte le esperienze; se manca, `role` | grassetto; nella dashboard è un menu a tendina alimentato da `GET /api/roles` |
| Education | `formazione[]` → `anno`, `titolo`, `istituto` | `education[]` (`year`, `title`, `institution`); se manca, `education_titles` | titolo in grassetto, istituto sotto |
| Training | `training[]` → `titolo` | `certifications` | una riga per corso o certificazione |
| Work Experiences | `esperienze[]` → `periodo`, `azienda`, `ruolo`, `righe[]`, `tecnologie`, `progetti[]` (`periodo`, `nome`, `ruolo`, `righe[]`, `tecnologie`) | `experiences[]` con `projects[]` | "Da 06/2023 ad Oggi"; azienda in grassetto; "Ruolo: …" sempre presente (se il CV non lo dice lo deduce l'LLM); per ogni progetto periodo, nome, "Attività: …", "Tecnologie utilizzate: …" |
| Synthesis of Technical Skills | `skills[]` → `nome`, `livello` | `cv_skills` (maiuscole e ordine del CV); se manca, `skills` | livelli tipici: Conoscenza base, Buona conoscenza, Ottima conoscenza |
| Languages | `lingue[]` → `lingua`, `livello` | `languages[]` (`lang`, `level`) | livello in grassetto: Base, Intermedio, Avanzato, Fluente, Madrelingua |

Intestazione (logo, figura vitruviana, titolo "Candidate Profile") e footer giallo con le sedi si ripetono su ogni pagina.

## Il CV è anonimo

Nome, cognome, **email, telefono ed età** si estraggono (`profile=mcflash` li include) e si modificano nel form, ma vanno solo sul **record MCFlash**. Nel CV compare solo il trittico. Un test (`tests/test_cv_mcflash_renderer.py`) verifica che non finiscano nel documento.

## Trittico

**Prima lettera del nome + prime due lettere del cognome**, maiuscole, senza accenti né apostrofi (`domain/candidate_identity.py`):

| Nome | Cognome | Trittico |
|---|---|---|
| Davide | Carbone | `DCA` |
| Mario | De Luca | `MDE` |
| Luca | D'Amico | `LDA` |

- L'estrazione `profile=mcflash` restituisce `first_name` e `last_name` separati. L'LLM gestisce anche "ROSSI Mario". Se mancano, il nome completo si divide con un'euristica che riconosce cognomi in maiuscolo e particelle come De, Della, Van.
- Se il CV caricato è **già nel modello MC** (al posto del nome c'è il codice, es. "Nome DCA"), il trittico si legge direttamente e nome e cognome restano vuoti: li inserisce l'utente nel form.

## Nome del file

`GET /api/cv/filename?trittico=DCA[&id_mcflash=…][&ext=.pdf]` propone il nome e tre alternative.

- **Candidato esistente** (`id_mcflash` presente in `CvMcflashMap`): si riusa **lo stesso nome file** del suo CV attuale. Stesso percorso con contenuto nuovo significa stesso `document_id` e versione +1, quindi l'indice sostituisce il vecchio CV senza passi extra.
- **Candidato nuovo**: si parte da `Skill Tecnico_DCA_MC Engineering` e, se il nome è già usato da un altro CV (blob di `incoming-cv` e `incoming-cv-originals`, più i file in `CvMcflashMap`), si passa alle varianti con spazi, underscore e trattini già in uso nell'archivio:
  `Skill_Tecnico_DCA_MC_Engineering` → `Skill Tecnico_DCA_MC` → `Skill_Tecnico_DCA_MC` → `Skill Tecnico_DCA_MC_` → … → `Skill Tecnico_DCA_MC Engineering (2)`.
- Il confronto ignora maiuscole ed estensione, quindi `.pdf` e `.docx` con lo stesso nome contano come duplicati.
- Nella dashboard la proposta è un campo modificabile; prima di salvare il backend ricontrolla che il nome sia libero.
