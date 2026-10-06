"""Pagina Candidati (home): tutti i record MCFlash in una tabella, con lo stato del CV.

Si vedono tutti i candidati e tutti i campi MCFlash. La ricerca e i filtri sono
facoltativi e vivono nell'URL (?q=&sede=&cv=), cosi' una ricerca si puo'
salvare tra i preferiti. Selezionando una riga compare "Aggiorna", che apre
aggiorna?id=<IdMCFlash>.
"""
from __future__ import annotations

import streamlit as st

from dashboard import api
from dashboard.components import backend, ui
from dashboard.components.candidates import (
    CV_FILTERS,
    candidate_title,
    candidates_frame,
    sede_options,
    style_frame,
    summary,
    text,
)

ALL_SEDI = "tutte"

# ---------------------------------------------------------------- stato

# Streamlit cancella lo stato dei widget quando si cambia pagina: i filtri
# restano in "cand_filters" (letto dall'URL alla prima apertura) e i widget
# vengono reinizializzati da li' quando si torna su questa pagina.
if "cand_filters" not in st.session_state:
    params = st.query_params
    st.session_state.cand_filters = {
        "q": params.get("q", ""),
        "sede": params.get("sede", ALL_SEDI),
        "cv": params.get("cv") if params.get("cv") in CV_FILTERS else "tutti",
    }
filters = st.session_state.cand_filters
for name in ("q", "sede", "cv"):
    st.session_state.setdefault(f"f_{name}", filters[name])

# ---------------------------------------------------------------- intestazione

ui.hero("Candidati", "Tutti i record MCFlash, con il CV indicizzato di ciascuno.")

all_rows = backend.call(backend.all_candidates)
if all_rows is None:
    st.stop()

counts = summary(all_rows)
k = st.columns(5)
ui.kpi(k[0], "blue", "Candidati", counts["totale"])
ui.kpi(k[1], "violet", "Abilitati", counts["abilitati"])
ui.kpi(k[2], "green", "Con CV indicizzato", counts["con_cv"])
ui.kpi(k[3], "orange", "Senza CV", counts["senza_cv"])
ui.kpi(k[4], "gray", "TalentUp", counts["talent_up"])

# ---------------------------------------------------------------- filtri

sedi = [ALL_SEDI] + sede_options(all_rows)
if st.session_state.f_sede not in sedi:
    st.session_state.f_sede = ALL_SEDI

f1, f2, f3, f4, f5 = st.columns([4, 2, 1.5, 1.6, 1.6], vertical_alignment="bottom")
f1.text_input("Cerca", key="f_q", placeholder="codice, nome, ruolo, sede, id…")
f2.selectbox("Sede", sedi, key="f_sede")
f3.selectbox("CV indicizzato", list(CV_FILTERS), key="f_cv")
f4.page_link("views/crea.py", label="Nuovo candidato", icon=":material/person_add:")
if f5.button("Ricarica da MCFlash", icon=":material/refresh:", help="Rilegge MCFlash e lo stato dei CV"):
    backend.call(api.get_client().list_candidates, limit=1, refresh=True)
    backend.clear_cache()
    st.rerun()

filters.update(q=st.session_state.f_q, sede=st.session_state.f_sede, cv=st.session_state.f_cv)
query = filters["q"].strip()
sede = "" if filters["sede"] == ALL_SEDI else filters["sede"]
has_cv = CV_FILTERS[filters["cv"]]

st.query_params.from_dict({k: v for k, v in {
    "q": query, "sede": sede, "cv": "" if filters["cv"] == "tutti" else filters["cv"],
}.items() if v})

if query or sede or has_cv is not None:
    result = backend.call(backend.list_candidates, query, sede, has_cv, True, 1000, 0)
    if result is None:
        st.stop()
    rows, warnings = result["items"], result.get("warnings") or []
else:
    rows, warnings = all_rows, []

for warning in warnings:
    st.warning(warning)

# ---------------------------------------------------------------- tabella

if not rows:
    st.info("Nessun candidato con questi filtri.")
    st.stop()

st.caption(f"{len(rows)} candidati · seleziona una riga per aggiornarla · "
           "verde = CV indicizzato, arancio = CV mancante, grigio = record disabilitato")

# La barra "Aggiorna" sta sopra la tabella, cosi' si vede senza scorrere; si
# riempie dopo, quando la selezione e' nota.
action_bar = st.container()

frame = candidates_frame(rows)
event = st.dataframe(
    style_frame(frame),
    key="cand_table",
    on_select="rerun",
    selection_mode="single-row",
    hide_index=True,
    height=560,
    column_config={
        "Id": st.column_config.NumberColumn(format="%d", width="small"),
        "Codice": st.column_config.TextColumn(width="small"),
        "Nome": st.column_config.TextColumn(width="medium"),
        "Ruolo": st.column_config.TextColumn(width="medium"),
        "Età": st.column_config.NumberColumn(format="%d", width="small"),
        "Lingue": st.column_config.TextColumn(width="medium"),
        "Budget": st.column_config.NumberColumn(format="€ %d", width="small"),
        "Abilitato": st.column_config.CheckboxColumn(width="small"),
        "TalentUp": st.column_config.CheckboxColumn(width="small"),
        "CV": st.column_config.TextColumn(width="small", help="CV indicizzato: sì · versione, oppure manca"),
        "File CV": st.column_config.TextColumn(width="medium"),
    },
)

selected = event.selection.rows if event and event.selection else []
if selected and selected[0] < len(rows):
    row = rows[selected[0]]
    with action_bar.container(border=True):
        info, action = st.columns([4, 1], vertical_alignment="center")
        info.markdown(f"**{text(row.get('nome_completo'))}** · {candidate_title(row)}")
        if action.button("Aggiorna", icon=":material/edit:", type="primary", width="stretch"):
            st.switch_page("views/aggiorna.py", query_params={"id": row["id"]})
