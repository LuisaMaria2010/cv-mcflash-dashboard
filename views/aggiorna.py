"""Pagina Aggiorna: nuovo CV per un candidato MCFlash esistente.

Il candidato arriva dall'URL (aggiorna?id=<IdMCFlash>), quindi la pagina si apre
gia' impostata dalla home e si puo' salvare tra i preferiti. Con &bozza=<id> si
lavora su una bozza: CV caricato, dati estratti modificabili e, accanto, i dati
MCFlash attuali per vedere cosa cambia.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.components import backend, cv_editor, ui
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


if not draft_id:
    current_mcflash()
    st.divider()
    col_up, col_drafts = st.columns([3, 2], gap="large")
    with col_up:
        st.markdown("##### :material/upload_file: Carica il nuovo CV")
        new_id = cv_editor.upload_and_extract("aggiorna", candidate_id)
        if new_id:
            st.query_params["bozza"] = new_id
            st.rerun()
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
    st.query_params.from_dict({"id": candidate_id})
    st.rerun()


cv_editor.workspace(ed, _discarded, above=None if ed.get("operation_id") else comparison, candidate=row)
