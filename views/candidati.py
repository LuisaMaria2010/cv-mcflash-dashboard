"""Pagina Candidati (home): tutti i record MCFlash in una tabella, con lo stato del CV.

Si vedono tutti i candidati e tutti i campi MCFlash. C'e' un filtro per ogni
campo MCFlash (vedi FILTERS); sono facoltativi e vivono nell'URL
(?sede=Roma&sede=Torino&eta=30-45&cv=manca...), cosi' una ricerca si puo'
salvare tra i preferiti. Selezionando una riga, a destra della tabella compare
l'anteprima del CV allegato (se c'e') con "Aggiorna dati", che apre
aggiorna?id=<IdMCFlash>.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import api
from dashboard.components import backend, cv_preview, mcflash_actions, ui
from dashboard.components.candidates import (
    FILTERS,
    OPEN_MARK,
    candidate_title,
    candidates_frame,
    distinct_values,
    filter_rows,
    flag_options,
    style_frame,
    summary,
    text,
    value_range,
)

# ---------------------------------------------------------------- stato

# Valore "spento" di ogni tipo di filtro, nella forma tenuta in cand_filters.
_EMPTY = {"text": "", "choice": [], "range": None, "flag": "tutti"}


def _from_url(key: str, kind: str) -> Any:
    params = st.query_params
    if kind == "choice":
        return params.get_all(key)
    raw = params.get(key, "")
    if kind == "range":
        lo, sep, hi = raw.partition("-")
        try:
            return (int(lo), int(hi)) if sep else None
        except ValueError:
            return None
    if kind == "flag":
        return raw if raw in flag_options(key) else "tutti"
    return raw


def _to_url(kind: str, value: Any) -> Any:
    if kind == "range":
        return f"{value[0]}-{value[1]}" if value else ""
    if kind == "flag":
        return "" if value == "tutti" else value
    return value


def _reset() -> None:
    st.session_state.cand_filters = {key: _EMPTY[kind] for key, (_, kind) in FILTERS.items()}
    for key in FILTERS:
        st.session_state.pop(f"f_{key}", None)


# Streamlit cancella lo stato dei widget quando si cambia pagina: i filtri
# restano in "cand_filters" (letto dall'URL alla prima apertura) e i widget
# vengono reinizializzati da li' quando si torna su questa pagina.
if "cand_filters" not in st.session_state:
    st.session_state.cand_filters = {key: _from_url(key, kind) for key, (_, kind) in FILTERS.items()}
filters = st.session_state.cand_filters

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

# Il riquadro si chiude con la freccia; chiuso, i filtri restano applicati.
with st.expander("Filtri MCFlash", expanded=True, icon=":material/filter_list:", key="cand_filters_box"):
    head, b1, b2, b3 = st.columns([4, 1.4, 1.6, 1.8], vertical_alignment="center")
    head.caption("Ogni filtro è facoltativo; si combinano tra loro.")
    b1.button("Azzera filtri", icon=":material/filter_alt_off:", on_click=_reset, width="stretch")
    b2.page_link("views/crea.py", label="Nuovo candidato", icon=":material/person_add:")
    if b3.button("Ricarica da MCFlash", icon=":material/refresh:", help="Rilegge MCFlash e lo stato dei CV",
                 width="stretch"):
        backend.call(api.get_client().list_candidates, limit=1, refresh=True)
        backend.clear_cache()
        st.rerun()

    cols = st.columns(5)
    for i, (key, (label, kind)) in enumerate(FILTERS.items()):
        col, state_key, stored = cols[i % 5], f"f_{key}", filters[key]
        if kind == "text":
            st.session_state.setdefault(state_key, stored)
            col.text_input(label, key=state_key, placeholder="contiene…")
        elif kind == "choice":
            options = distinct_values(all_rows, key)
            folded = {o.casefold(): o for o in options}
            current = st.session_state.get(state_key, stored)
            st.session_state[state_key] = [folded[v.casefold()] for v in current if v.casefold() in folded]
            col.multiselect(label, options, key=state_key, placeholder="tutti")
        elif kind == "flag":
            options = list(flag_options(key))
            if st.session_state.get(state_key, stored) not in options:
                st.session_state[state_key] = "tutti"
            st.session_state.setdefault(state_key, stored)
            col.selectbox(label, options, key=state_key)
        else:
            bounds = value_range(all_rows, key)
            if bounds is None or bounds[0] == bounds[1]:
                st.session_state[state_key] = None
                col.text_input(label, value="—" if bounds is None else str(bounds[0]), disabled=True,
                               key=f"{state_key}_off")
                continue
            lo, hi = st.session_state.get(state_key) or stored or bounds
            st.session_state[state_key] = (max(lo, bounds[0]), min(max(hi, bounds[0]), bounds[1]))
            col.slider(label, bounds[0], bounds[1], key=state_key,
                       format="€ %d" if key == "budget" else "%d")

    for key, (_, kind) in FILTERS.items():
        value = st.session_state.get(f"f_{key}")
        if kind == "range":
            bounds = value_range(all_rows, key)
            value = None if not value or tuple(value) == bounds else tuple(value)
        filters[key] = _EMPTY[kind] if value is None and kind != "range" else value

st.query_params.from_dict({
    key: v for key, (_, kind) in FILTERS.items() if (v := _to_url(kind, filters[key]))
})

active = {
    key: flag_options(key)[value] if kind == "flag" else value
    for key, (_, kind) in FILTERS.items() for value in [filters[key]]
}
rows = filter_rows(all_rows, active)

# ---------------------------------------------------------------- tabella

if not rows:
    st.info("Nessun candidato con questi filtri.")
    st.stop()

n_active = sum(1 for value in filters.values() if value not in ("", [], None, "tutti"))
active_note = f" · filtri attivi: {n_active}" if n_active else ""
st.caption(f"{len(rows)} candidati{active_note} · clicca una riga per vedere il CV · "
           "verde = CV indicizzato, arancio = CV mancante, grigio = record disabilitato")

TABLE_HEIGHT = 640

# Il candidato aperto nel pannello a destra e' "cand_open" (Id MCFlash), non la
# selezione della tabella: evidenziare la riga cambia i dati della tabella e
# Streamlit ne azzera la selezione. La tabella serve solo a sceglierlo: un clic
# su una cella qualsiasi apre quel candidato. Niente selezione per riga: la sua
# colonna di quadratini prende il blu dell'intestazione e la spunta non si vede;
# la riga aperta ha invece la sua spunta in OPEN_MARK.
def _on_pick() -> None:
    selection = st.session_state.cand_table.selection
    picked = [cell[0] for cell in selection.get("cells", [])]
    shown = st.session_state.get("cand_shown_ids", [])  # le righe che l'utente aveva davanti
    if picked and picked[0] < len(shown):
        st.session_state.cand_open = shown[picked[0]]


def _close_panel() -> None:
    st.session_state.cand_open = None


st.session_state.cand_shown_ids = [r["id"] for r in rows]
open_id = st.session_state.get("cand_open")
open_at = next((i for i, r in enumerate(rows) if r["id"] == open_id), None)
row = rows[open_at] if open_at is not None else None
table_col, side_col = st.columns([3, 2]) if row else (st.container(), None)

frame = candidates_frame(rows, open_at)
table_col.dataframe(
    style_frame(frame, open_at),
    key="cand_table",
    on_select=_on_pick,
    selection_mode="single-cell",
    hide_index=True,
    height=TABLE_HEIGHT,
    column_config={
        OPEN_MARK: st.column_config.TextColumn(width=36, help="Candidato aperto nel pannello a destra"),
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

if row is not None:
    with side_col.container(border=True):
        info, action, close = st.columns([3, 2, 0.5], vertical_alignment="center")
        info.markdown(f"**{text(row.get('nome_completo'))}**  \n{candidate_title(row)}")
        if action.button("Aggiorna dati", icon=":material/edit:", type="primary", width="stretch"):
            st.switch_page("views/aggiorna.py", query_params={"id": row["id"]})
        close.button("", icon=":material/close:", key="close_panel", on_click=_close_panel, type="tertiary",
                     help="Chiudi il pannello (clicca un candidato per riaprirlo)")
        mcflash_actions.hide_button(row, lambda: (_close_panel(), st.rerun()), key=f"hide_{row['id']}")
        cv = row.get("cv")
        if not cv:
            st.info("Nessun CV allegato a questo candidato.", icon=":material/description:")
        else:
            with st.spinner("Carico il CV…"):
                found = backend.call(backend.candidate_cv, str(row["id"]), str(cv.get("version") or ""))
            if found:
                cv_preview.show_original(found[0], found[1], height=TABLE_HEIGHT - 140)
