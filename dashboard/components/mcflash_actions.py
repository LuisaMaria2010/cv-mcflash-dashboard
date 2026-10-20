"""Azioni sul record MCFlash di un candidato: per ora "Nascondi candidato".

I candidati non si eliminano: si nascondono con il comando di MCFlash
(POST /api/candidates/<id>/nascondi). MCFlash non li restituisce piu', quindi
spariscono anche dalla dashboard. Il CV resta nell'archivio e nell'indice, e il
collegamento CV -> MCFlash resta nella tabella. Il pulsante apre un riquadro
con la conferma esplicita, non una finestra modale.
"""
from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from dashboard import api
from dashboard.components import backend
from dashboard.components.candidates import candidate_title, text
from dashboard.config import load_settings


def hide_button(row: dict[str, Any], on_hidden: Callable[[], None], *, key: str) -> None:
    """Pulsante "Nascondi candidato" con conferma; `on_hidden` dopo l'operazione riuscita."""
    with st.popover("Nascondi candidato", icon=":material/visibility_off:", width="stretch"):
        st.markdown(f"**{text(row.get('nome_completo'))}** · {candidate_title(row)} · Id {row['id']}")
        st.warning("Il candidato viene nascosto su MCFlash e non compare più, nemmeno qui. Il CV resta "
                   "nell'archivio e il collegamento CV → MCFlash resta nella tabella.", icon=":material/warning:")
        sure = st.checkbox("Confermo: nascondi questo candidato", key=f"{key}_sure")
        if st.button("Nascondi", key=f"{key}_go", type="primary", icon=":material/visibility_off:",
                     disabled=not sure, width="stretch"):
            done = backend.call(api.get_client().hide_candidate, row["id"], user=load_settings().user or None)
            if done:
                backend.clear_cache()
                note = " (MCFlash finto: su MCFlash vero non è cambiato nulla)" if done.get("modalita") == "finto" else ""
                st.toast(f"{text(row.get('nome_completo'))} nascosto{note}.", icon=":material/visibility_off:")
                on_hidden()
