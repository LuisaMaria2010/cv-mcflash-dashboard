"""Dashboard CV -> MCFlash. Avvio: streamlit run app.py

Navigazione con le tab in alto. Lo stato tra le pagine passa dall'URL
(st.query_params, es. aggiorna?id=1884) e da st.session_state, mai da finestre
modali: ogni pagina si puo' aprire e salvare tra i preferiti.
"""
from __future__ import annotations

import streamlit as st

from dashboard.components import ui

st.set_page_config(page_title="CV · MCFlash", page_icon=":material/badge:", layout="wide")
ui.inject_css()

PAGES = [
    st.Page("views/candidati.py", title="Candidati", icon=":material/groups:", url_path="candidati", default=True),
    st.Page("views/crea.py", title="Crea", icon=":material/person_add:", url_path="crea"),
    st.Page("views/aggiorna.py", title="Aggiorna", icon=":material/edit_document:", url_path="aggiorna"),
    st.Page("views/operazioni.py", title="Operazioni", icon=":material/monitoring:", url_path="operazioni"),
]

st.navigation(PAGES, position="top").run()
