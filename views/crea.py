"""Pagina Crea: nuovo candidato MCFlash da un CV.

Senza ?bozza: si carica il CV e si estraggono i dati, oppure si riprende una bozza.
Con ?bozza=<id>: il form con i dati estratti, salvato da solo. Appena nome e
cognome sono noti la pagina chiama /api/candidates/match: se il candidato
esiste gia' propone di passare ad Aggiorna con la stessa bozza.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.components import backend, cv_editor, ui
from dashboard.components.candidates import candidate_title, text

draft_id = (st.query_params.get("bozza") or "").strip()

if not draft_id:
    ui.hero("Nuovo candidato", "Si carica il CV, si correggono i dati estratti e alla conferma si crea la riga su MCFlash.")
    col_up, col_drafts = st.columns([3, 2], gap="large")
    with col_up:
        st.markdown("##### :material/upload_file: Carica il CV")
        new_id = cv_editor.upload_and_extract("crea")
        if new_id:
            st.query_params["bozza"] = new_id
            st.rerun()
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
