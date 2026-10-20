"""Pagina Crea: nuovo candidato MCFlash da un CV.

Senza ?bozza: si carica il CV e si estraggono i dati, si cerca un CV gia'
nell'archivio (la persona puo' avere un CV indicizzato anche senza riga su
MCFlash), oppure si riprende una bozza.
Con ?bozza=<id>: il form con i dati estratti, salvato da solo. Appena nome e
cognome sono noti la pagina chiama /api/candidates/match: se il candidato
esiste gia' propone di passare ad Aggiorna con la stessa bozza.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.components import backend, cv_editor, cv_finder, ui
from dashboard.components.candidates import candidate_title, text
from dashboard.components.draft import trittico, with_identity

draft_id = (st.query_params.get("bozza") or "").strip()


def use_archived_cv(person: dict[str, Any]):
    """Callback "Usa questo CV": nuova bozza dal CV dell'archivio, con nome e
    cognome scritti dall'utente se il CV e' anonimo."""
    def use(filename: str, data: bytes) -> None:
        new_id = cv_editor.extract_to_draft(
            "crea", None, data, filename, label=f"Estraggo i dati da «{filename}»…",
            adjust=lambda ex: with_identity(ex, person.get("nome"), person.get("cognome"), age=person.get("eta"),
                                            location=person.get("sede")))
        if new_id:
            st.query_params["bozza"] = new_id
            st.rerun()
    return use


def archive_search(key: str, defaults: dict[str, Any]) -> None:
    """Modulo con i dati noti della persona e ricerca dei suoi CV nell'archivio.
    La ricerca parte solo dal pulsante (Invio non la avvia); il codice (trittico),
    se scritto, vale al posto di quello calcolato da nome e cognome."""
    with st.container(border=True):
        st.caption("La persona potrebbe avere già un CV nell'archivio anche se non è su MCFlash.")
        with st.form(f"{key}_form", border=False, enter_to_submit=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            nome = c1.text_input("Nome", value=defaults.get("nome") or "", key=f"{key}_nome")
            cognome = c2.text_input("Cognome", value=defaults.get("cognome") or "", key=f"{key}_cognome")
            codice = c3.text_input("Codice", value="", max_chars=3, key=f"{key}_codice", placeholder="es. LSE",
                                   help="Trittico: prima lettera del nome + prime due del cognome. "
                                        "Se lo scrivi si cerca questo, oltre ai codici del nome")
            c1, c2, c3 = st.columns([2, 1, 1.2])
            ruolo = c1.text_input("Ruolo", value=defaults.get("ruolo") or "", key=f"{key}_ruolo")
            eta = c2.number_input("Età", min_value=0, max_value=99, value=defaults.get("eta"), key=f"{key}_eta")
            sede = c3.text_input("Città", value=defaults.get("sede") or "", key=f"{key}_sede")
            submitted = st.form_submit_button("Cerca nell'archivio", type="primary", icon=":material/search:")
        if submitted:
            tri = codice.strip().upper()
            if not (tri or trittico(nome, cognome) or ruolo.strip()):
                st.warning("Scrivi il codice, oppure nome e cognome, oppure almeno il ruolo.")
            else:
                person = {"nome": nome.strip(), "cognome": cognome.strip(), "trittico": tri or None,
                          "ruolo": ruolo.strip(), "eta": eta, "sede": sede.strip()}
                st.session_state[f"{key}_person"] = person
                cv_finder.search_now(key, person)
        person = st.session_state.get(f"{key}_person")
        if person:
            cv_finder.panel(key, person, on_use=use_archived_cv(person), show_start=False)


if not draft_id:
    ui.hero("Nuovo candidato", "Si carica il CV, si correggono i dati estratti e alla conferma si crea la riga su MCFlash.")
    col_up, col_drafts = st.columns([3, 2], gap="large")
    with col_up:
        st.markdown("##### :material/upload_file: Carica il CV")
        new_id = cv_editor.upload_and_extract("crea")
        if new_id:
            st.query_params["bozza"] = new_id
            st.rerun()
        st.divider()
        st.markdown("##### :material/manage_search: Oppure cerca un CV già nell'archivio")
        archive_search("crea_new", {})
    with col_drafts:
        cv_editor.drafts_to_resume("crea", None, "views/crea.py")
    st.stop()

ed = cv_editor.load(draft_id)
if ed is None:
    st.page_link("views/crea.py", label="Torna a Nuovo candidato", icon=":material/arrow_back:")
    st.stop()
if ed["kind"] == "aggiorna":
    st.switch_page("views/aggiorna.py", query_params={"id": ed["id_mcflash"], "bozza": draft_id})

current = ed["current"]
ui.hero(f"Nuovo candidato · {current.get('full_name') or 'senza nome'}",
        f"CV «{ed['original_filename'] or '—'}» · bozza {draft_id[:8]}")
banner = st.container()


def _to_update(candidate: dict[str, Any]) -> None:
    if cv_editor.set_kind(ed, "aggiorna", candidate["id"]):
        st.switch_page("views/aggiorna.py", query_params={"id": candidate["id"], "bozza": draft_id})


def match_banner() -> None:
    """Esito del confronto con MCFlash: nuovo, gia' presente, da scegliere."""
    first, last = (ed["current"].get("first_name") or ""), (ed["current"].get("last_name") or "")
    if not (first and last):
        st.info("Completa nome e cognome: servono per controllare se il candidato è già su MCFlash.")
        return
    result = backend.call(backend.match_candidate, first, last)
    if result is None:
        return
    if result["esito"] == "nuovo":
        st.success(f"Nessun candidato MCFlash corrisponde ({result['motivo']}): alla conferma verrà creato.",
                   icon=":material/person_add:")
        return
    dismissed = ed.setdefault("match_dismissed", set())
    if all(c["id"] in dismissed for c in result["candidati"]):
        st.info("Hai indicato che è una persona diversa dai candidati con lo stesso nome: si crea un nuovo record.")
        return
    with st.container(border=True):
        st.warning(f"Questo candidato potrebbe essere già su MCFlash ({result['motivo']}).", icon=":material/warning:")
        for cand in result["candidati"]:
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.markdown(f"**{text(cand.get('nome_completo'))}** · {candidate_title(cand)} · età {text(cand.get('eta')) or '—'} "
                        f"· CV {'presente' if cand.get('cv') else 'mancante'} · Id {cand['id']}")
            if c2.button("È questa persona: aggiorna", key=f"to_upd_{cand['id']}", type="primary", width="stretch"):
                _to_update(cand)
        if st.button("È una persona diversa: continua a creare", key="match_dismiss"):
            dismissed.update(c["id"] for c in result["candidati"])
            st.rerun()


def _discarded() -> None:
    st.query_params.clear()
    st.rerun()


cv_editor.workspace(ed, _discarded)
if not ed.get("operation_id"):
    with banner:
        match_banner()
        with st.expander("Esiste già un CV di questa persona nell'archivio?", icon=":material/manage_search:"):
            cur = ed["current"]
            archive_search(f"crea_{draft_id[:8]}", {"nome": cur.get("first_name"), "cognome": cur.get("last_name"),
                                                    "ruolo": cur.get("role"), "sede": cur.get("location"),
                                                    "eta": int(cur["age"]) if str(cur.get("age") or "").isdigit() else None})
