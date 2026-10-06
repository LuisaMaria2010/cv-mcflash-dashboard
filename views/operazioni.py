"""Pagina Operazioni: monitor delle conferme (tabella CvOperations del backend).

Contatori, tabella con una colonna per passo, dettaglio dell'operazione scelta
con l'errore e "Riprova". Finche' ci sono operazioni in corso la pagina si
aggiorna da sola ogni 5 secondi e le fa avanzare (il passo "mappa" aspetta
l'indicizzazione, che richiede qualche minuto). Filtri e operazione scelta
stanno nell'URL (?periodo=&stato=&utente=&op=).
"""
from __future__ import annotations

import streamlit as st

from dashboard import api
from dashboard.components import backend, cv_editor, ui
from dashboard.components.operations import (
    PERIODS,
    STATUSES,
    counts,
    draft_link,
    operations_frame,
    since,
    style_operations,
)

REFRESH_SECONDS = 5

ui.hero("Operazioni", "Ogni conferma è un'operazione con un passo per storage, MCFlash, indice e mappa; "
                      "se un passo fallisce, «Riprova» riparte da lì.")

# ---------------------------------------------------------------- filtri (URL)

if "ops_filters" not in st.session_state:
    params = st.query_params
    st.session_state.ops_filters = {
        "periodo": params.get("periodo") if params.get("periodo") in PERIODS else "7 giorni",
        "stato": params.get("stato") if params.get("stato") in STATUSES else "tutte",
        "utente": params.get("utente", ""),
        "op": params.get("op", ""),
    }
filters = st.session_state.ops_filters
for name in ("periodo", "stato", "utente"):
    st.session_state.setdefault(f"ops_{name}", filters[name])

f1, f2, f3, f4 = st.columns([1.3, 1.3, 2, 1], vertical_alignment="bottom")
f1.selectbox("Periodo", list(PERIODS), key="ops_periodo")
f2.selectbox("Stato", list(STATUSES), key="ops_stato")
f3.text_input("Utente", key="ops_utente", placeholder="tutti")
if f4.button("Aggiorna", icon=":material/refresh:", width="stretch"):
    st.rerun()
filters.update(periodo=st.session_state.ops_periodo, stato=st.session_state.ops_stato,
               utente=st.session_state.ops_utente.strip())


def _load() -> list[dict] | None:
    return backend.call(api.get_client().list_operations, stato=STATUSES[filters["stato"]],
                        utente=filters["utente"] or None, da=since(filters["periodo"]))


def _advance_running(ops: list[dict]) -> list[dict]:
    """Le operazioni in corso avanzano solo quando qualcuno le interroga: lo fa il monitor."""
    out = []
    client = api.get_client()
    for op in ops:
        if op.get("status") == "in_corso":
            try:
                op = client.get_operation(op["id"])
            except api.BackendError:
                pass
        out.append(op)
    return out


def _sync_url() -> None:
    st.query_params.from_dict({k: v for k, v in {
        "periodo": "" if filters["periodo"] == "7 giorni" else filters["periodo"],
        "stato": "" if filters["stato"] == "tutte" else filters["stato"],
        "utente": filters["utente"], "op": filters["op"],
    }.items() if v})


def _signature(ops: list[dict]) -> list[tuple]:
    return [(o["id"], o.get("status"), *(o.get(f"step_{s}") for s in ("blob", "mcflash", "indice", "mappa")))
            for o in ops]


ops = _load()
if ops is None:
    st.stop()
ops = _advance_running(ops)
running = any(o.get("status") == "in_corso" for o in ops)


@st.fragment(run_every=REFRESH_SECONDS if running else None)
def _watch() -> None:
    """Controllo invisibile mentre ci sono operazioni in corso: le fa avanzare e,
    se qualcosa e' cambiato, ridisegna la pagina (tabella e dettaglio compresi)."""
    if not running:
        return
    fresh = _load()
    if fresh is not None and _signature(_advance_running(fresh)) != _signature(ops):
        st.rerun()


_watch()

c = counts(ops)
k = st.columns(4)
ui.kpi(k[0], "blue", "Operazioni", c["totale"])
ui.kpi(k[1], "green", "Completate", c["completata"])
ui.kpi(k[2], "violet", "In corso", c["in_corso"])
ui.kpi(k[3], "orange", "Fallite", c["fallita"])

if not ops:
    st.info("Nessuna operazione con questi filtri. Le operazioni nascono da «Conferma e carica» "
            "nelle pagine Crea e Aggiorna.")
    _sync_url()
    st.stop()
if running:
    st.caption(f":material/autorenew: Aggiornamento automatico ogni {REFRESH_SECONDS} secondi "
               "finché ci sono operazioni in corso.")

event = st.dataframe(
    style_operations(operations_frame(ops)), key="ops_table", on_select="rerun",
    selection_mode="single-row", hide_index=True, height=min(80 + 35 * len(ops), 460),
    column_config={"Errore": st.column_config.TextColumn(width="large"),
                   "Candidato": st.column_config.TextColumn(width="medium")},
)
selected = event.selection.rows if event and event.selection else []
if selected and selected[0] < len(ops):
    filters["op"] = ops[selected[0]]["id"]
elif filters["op"] not in {o["id"] for o in ops}:
    filters["op"] = ""
_sync_url()

# ---------------------------------------------------------------- dettaglio

if filters["op"]:
    op = next((o for o in ops if o["id"] == filters["op"]), None) or {"id": filters["op"]}
    st.markdown("##### :material/info: Dettaglio")
    col_op, col_links = st.columns([2, 1])
    with col_op:
        detail = cv_editor.operation_panel(filters["op"])
    with col_links:
        op = detail or op
        if op.get("id_mcflash"):
            st.page_link("views/aggiorna.py", label="Apri il candidato", icon=":material/person:",
                         query_params={"id": str(op["id_mcflash"])})
        if op.get("draft_id"):
            page, params = draft_link(op)
            st.page_link(page, label="Apri la bozza confermata", icon=":material/description:",
                         query_params=params)
        st.caption("Per cercare nei log della Function:")
        st.code(f"operation_id: {op['id']}\nrequest_id:   {op.get('last_request_id') or '—'}", language=None)
else:
    st.caption("Seleziona una riga per vedere il dettaglio e, se serve, riprovare.")
