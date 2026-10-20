"""Pagina Aggiorna: nuovo CV per un candidato MCFlash esistente.

Il candidato arriva dall'URL (aggiorna?id=<IdMCFlash>), quindi la pagina si apre
gia' impostata dalla home e si puo' salvare tra i preferiti. Con &bozza=<id> si
lavora su una bozza: CV, dati estratti modificabili e, accanto, i dati MCFlash
attuali per vedere cosa cambia.

Senza bozza la pagina riprende l'ultima bozza del candidato. Se non ce ne sono:
- con un CV indicizzato lo estrae e apre il form come se fosse stato caricato,
  per correggere il CV attuale;
- senza CV apre il form compilato con i dati MCFlash; nella prima colonna si
  carica il CV o lo si cerca nell'archivio (dashboard/components/cv_finder.py).
Altri ingressi:
- &nuovo=1   caricatore per un CV totalmente nuovo, ricerca nell'archivio e
             bozze da riprendere;
- &da_cv=1   nuova bozza estratta dal CV attuale (riparte da zero).
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import api
from dashboard.components import backend, cv_editor, cv_finder, mcflash_actions, ui
from dashboard.components.draft import draft_from_record, fill_from_record, identity_from_record
from dashboard.config import load_settings
from dashboard.components.candidates import (
    candidate_title,
    comparison_frame,
    cv_label,
    cv_replacement_note,
    style_comparison,
    text,
)

candidate_id = (st.query_params.get("id") or "").strip()
draft_id = (st.query_params.get("bozza") or "").strip()
upload_new = st.query_params.get("nuovo") == "1"
from_current = st.query_params.get("da_cv") == "1"

if not candidate_id or not candidate_id.isdigit():
    ui.hero("Aggiorna", "Nuovo CV per un candidato già su MCFlash.")
    if candidate_id:
        st.error(f"Id candidato non valido: «{candidate_id}».")
    else:
        st.info("Nessun candidato scelto. Apri la pagina Candidati, seleziona una riga e premi «Aggiorna».")
    st.page_link("views/candidati.py", label="Vai ai candidati", icon=":material/groups:")
    st.stop()

row = backend.call(backend.get_candidate, candidate_id)
if row is None:
    st.page_link("views/candidati.py", label="Torna ai candidati", icon=":material/arrow_back:")
    st.stop()

ui.hero(f"Aggiorna · {candidate_title(row)}", f"{text(row.get('nome_completo'))} · Id MCFlash {row['id']}")
for warning in row.get("warnings") or []:
    st.warning(warning)
with st.container(horizontal=True, horizontal_alignment="right"):
    with st.container(width=260):
        mcflash_actions.hide_button(row, lambda: st.switch_page("views/candidati.py"), key=f"hide_agg_{candidate_id}")
if row.get("abilitato") is False or row.get("is_talent_up") is True:
    st.warning("Il record è disabilitato o TalentUp, quindi fuori dalla ricerca: l'aggiornamento è comunque possibile.")
(st.info if row.get("cv") else st.success)(cv_replacement_note(row), icon=":material/description:")


def current_mcflash() -> None:
    k = st.columns(4)
    ui.kpi(k[0], "blue", "Seniority", text(row.get("seniority")) or "—")
    ui.kpi(k[1], "violet", "Età", text(row.get("eta")) or "—")
    budget = row.get("budget")
    ui.kpi(k[2], "orange", "Budget", f"€ {budget}" if budget not in (None, "") else "—")
    ui.kpi(k[3], "green" if row.get("cv") else "orange", "CV indicizzato", cv_label(row))
    with st.container(border=True):
        st.markdown("##### :material/badge: Dati attuali su MCFlash")
        fields = [
            ("Ruolo", row.get("ruolo")), ("Sede", row.get("sede")), ("Disponibilità", row.get("disponibilita")),
            ("Lingue", row.get("lingue")), ("Site", row.get("site")),
            ("Abilitato", "sì" if row.get("abilitato") else "no"),
            ("TalentUp", "sì" if row.get("is_talent_up") else "no"),
            ("File CV", (row.get("cv") or {}).get("file")),
        ]
        cols = st.columns(4)
        for i, (label, value) in enumerate(fields):
            cols[i % 4].markdown(f":gray[{label}]  \n**{text(value) or '—'}**")


def open_draft(new_id: str) -> None:
    st.query_params.from_dict({"id": candidate_id, "bozza": new_id})
    st.rerun()


def extract_current_cv() -> str | None:
    """Bozza nuova con i dati estratti dal CV indicizzato del candidato."""
    cv = row["cv"]
    found = backend.call(backend.candidate_cv, candidate_id, str(cv.get("version") or ""))
    if not found:
        return None
    filename, data = found
    return cv_editor.extract_to_draft("aggiorna", candidate_id, data, filename,
                                      label=f"Estraggo i dati dal CV attuale «{filename}»…",
                                      adjust=lambda extraction: identity_from_record(extraction, row))


def use_cv(filename: str, data: bytes) -> None:
    """CV caricato o trovato nell'archivio: estrazione e form, come per un CV nuovo.
    Se il CV e' anonimo nome e codice vengono dal record; si tengono i dati
    MCFlash gia' corretti nella bozza aperta."""
    current = (st.session_state.get(cv_editor.STATE_KEY) or {}).get("current") or {}

    def adjust(extraction: dict[str, Any]) -> dict[str, Any]:
        out = fill_from_record(extraction, row)
        if current.get("mcflash"):
            out["mcflash"] = current["mcflash"]
        return out

    new_id = cv_editor.extract_to_draft("aggiorna", candidate_id, data, filename, adjust=adjust,
                                        label=f"Estraggo i dati da «{filename}»…")
    if new_id:
        cv_finder.reset(f"agg_{candidate_id}")
        open_draft(new_id)


def link_cv(result: dict[str, Any]) -> None:
    """Collega il CV trovato al candidato senza toccarlo, poi ne apre i dati."""
    done = backend.call(api.get_client().link_cv, candidate_id, result["document_id"], user=load_settings().user)
    if done:
        backend.clear_cache()
        cv_finder.reset(f"agg_{candidate_id}")
        st.toast(f"CV «{done['file']}» collegato a {text(row.get('nome_completo'))}.", icon=":material/link:")
        st.query_params.from_dict({"id": candidate_id, "da_cv": "1"})
        st.rerun()


def find_in_archive() -> None:
    cv_finder.panel(f"agg_{candidate_id}", {"id_mcflash": candidate_id}, on_use=use_cv,
                    on_link=None if row.get("cv") else link_cv)


def no_cv(ed: dict[str, Any]) -> None:
    """Prima colonna di una bozza senza CV: caricamento e ricerca nell'archivio."""
    new_id = cv_editor.upload_and_extract("aggiorna", candidate_id, adjust=lambda ex: fill_from_record(ex, row))
    if new_id:
        open_draft(new_id)
    st.divider()
    find_in_archive()


if not draft_id and not upload_new:
    if from_current and row.get("cv"):
        new_id = extract_current_cv()
        if new_id:
            open_draft(new_id)
    else:
        drafts = backend.call(backend.list_drafts, "aggiorna", candidate_id) or []
        if drafts:
            open_draft(drafts[0]["draft_id"])
        # Un solo tentativo automatico per sessione: se l'estrazione fallisce si
        # resta sul caricatore invece di riprovare a ogni interazione.
        auto_key = f"auto_extract_{candidate_id}"
        if row.get("cv") and not st.session_state.get(auto_key):
            st.session_state[auto_key] = True
            new_id = extract_current_cv()
            if new_id:
                open_draft(new_id)
        if not row.get("cv"):
            # Nessun CV: il form parte da quello che MCFlash sa gia'.
            try:
                roles = backend.roles()
            except api.BackendError:
                roles = []
            new_id = cv_editor.start_from_data("aggiorna", candidate_id, draft_from_record(row, roles))
            if new_id:
                open_draft(new_id)
    st.query_params.from_dict({"id": candidate_id, "nuovo": "1"})
    upload_new = True

if not draft_id:
    current_mcflash()
    st.divider()
    col_up, col_drafts = st.columns([3, 2], gap="large")
    with col_up:
        st.markdown("##### :material/upload_file: Carica il nuovo CV")
        new_id = cv_editor.upload_and_extract("aggiorna", candidate_id)
        if new_id:
            open_draft(new_id)
        if row.get("cv"):
            st.page_link("views/aggiorna.py", label="Oppure modifica il CV attuale", icon=":material/edit_document:",
                         query_params={"id": candidate_id, "da_cv": "1"})
        st.divider()
        find_in_archive()
    with col_drafts:
        cv_editor.drafts_to_resume("aggiorna", candidate_id, "views/aggiorna.py", {"id": candidate_id})
    st.stop()

ed = cv_editor.load(draft_id)
if ed is None:
    st.page_link("views/aggiorna.py", label="Torna al candidato", icon=":material/arrow_back:",
                 query_params={"id": candidate_id})
    st.stop()
if ed["kind"] != "aggiorna" or ed["id_mcflash"] != candidate_id:
    st.error("Questa bozza non appartiene a questo candidato.")
    st.page_link("views/aggiorna.py", label="Torna al candidato", icon=":material/arrow_back:",
                 query_params={"id": candidate_id})
    st.stop()


def comparison(ed: dict[str, Any]) -> None:
    with st.expander("MCFlash attuale e CV: cosa cambia", icon=":material/compare_arrows:", expanded=True):
        st.dataframe(style_comparison(comparison_frame(row, ed["current"])), hide_index=True,
                     width="stretch")
        st.caption("In arancio i valori del CV diversi da quelli su MCFlash: alla conferma (fase 5) "
                   "si aggiorna il record.")


def _discarded() -> None:
    st.query_params.from_dict({"id": candidate_id, "nuovo": "1"})
    st.rerun()


if not ed.get("operation_id"):
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.page_link("views/aggiorna.py", label="Carica un CV nuovo", icon=":material/upload_file:",
                     query_params={"id": candidate_id, "nuovo": "1"})
        if row.get("cv"):
            st.page_link("views/aggiorna.py", label="Riparti dal CV attuale", icon=":material/restart_alt:",
                         query_params={"id": candidate_id, "da_cv": "1"},
                         help="Nuova bozza con i dati estratti di nuovo dal CV indicizzato")


cv_editor.workspace(ed, _discarded, above=None if ed.get("operation_id") else comparison, candidate=row,
                    no_cv=no_cv)
