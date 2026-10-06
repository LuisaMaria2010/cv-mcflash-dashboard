"""Anteprima del CV originale: PDF incorporato, DOCX convertito in HTML con mammoth."""
from __future__ import annotations

import io
from pathlib import PurePosixPath

import streamlit as st

PREVIEW_HEIGHT = 820

_DOCX_STYLE = """
<style>
.mc-docx { background: #FFFFFF; color: #2C2C2C; padding: 28px 34px; border-radius: 10px;
           border: 1px solid #D3DCEB; font-size: .92rem; line-height: 1.45; }
.mc-docx h1, .mc-docx h2, .mc-docx h3 { color: #1F3864; margin: .8em 0 .3em; }
.mc-docx table { border-collapse: collapse; width: 100%; }
.mc-docx td, .mc-docx th { border: 1px solid #E1E7F0; padding: 4px 6px; vertical-align: top; }
.mc-docx img { max-width: 100%; }
</style>
"""


def docx_to_html(data: bytes) -> str:
    import mammoth

    return mammoth.convert_to_html(io.BytesIO(data)).value


def show_original(filename: str | None, data: bytes | None) -> None:
    """Mostra il file nella colonna corrente. Senza byte mostra solo un avviso."""
    if not data:
        st.info("Il CV originale non è disponibile per l'anteprima.")
        return
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix == ".pdf":
        st.pdf(data, height=PREVIEW_HEIGHT)
    elif suffix == ".docx":
        try:
            body = docx_to_html(data)
        except Exception as exc:  # file danneggiato o non DOCX
            st.warning(f"Anteprima DOCX non riuscita: {exc}")
        else:
            with st.container(height=PREVIEW_HEIGHT, border=False):
                st.html(_DOCX_STYLE + f'<div class="mc-docx">{body}</div>')
    else:
        st.info(f"Anteprima non disponibile per i file «{suffix or 'senza estensione'}».")
    st.download_button("Scarica l'originale", data, file_name=filename or "cv", icon=":material/download:",
                       width="stretch")
