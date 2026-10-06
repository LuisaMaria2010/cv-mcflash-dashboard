"""Chiamate al backend dalle pagine: cache di Streamlit e messaggi d'errore uniformi."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

import streamlit as st

from dashboard import api

T = TypeVar("T")

# Il backend tiene gia' i record MCFlash in memoria per 2 minuti: qui basta
# evitare di richiamarlo a ogni interazione con la pagina.
_TTL_SECONDS = 60


@st.cache_data(ttl=_TTL_SECONDS, show_spinner=False)
def list_candidates(q: str, sede: str, has_cv: bool | None, tutti: bool, limit: int, offset: int,
                    refresh: bool = False) -> dict[str, Any]:
    return api.get_client().list_candidates(q=q, sede=sede, has_cv=has_cv, tutti=tutti,
                                            limit=limit, offset=offset, refresh=refresh)


@st.cache_data(ttl=_TTL_SECONDS, show_spinner=False)
def all_candidates() -> list[dict[str, Any]]:
    """Tutti i record (anche non idonei): servono per le opzioni dei filtri."""
    return api.get_client().list_candidates(tutti=True, limit=1000)["items"]


@st.cache_data(ttl=_TTL_SECONDS, show_spinner=False)
def get_candidate(candidate_id: str) -> dict[str, Any]:
    return api.get_client().get_candidate(candidate_id)


@st.cache_data(ttl=3600, show_spinner=False)
def roles() -> list[dict[str, Any]]:
    return api.get_client().roles()


@st.cache_data(ttl=3600, show_spinner=False)
def mc_levels() -> dict[str, list[str]]:
    return api.get_client().mc_levels()


@st.cache_data(ttl=_TTL_SECONDS, show_spinner=False)
def cv_filename(trittico: str, id_mcflash: str | None) -> dict[str, Any]:
    return api.get_client().cv_filename(trittico=trittico, id_mcflash=id_mcflash)


@st.cache_data(ttl=_TTL_SECONDS, show_spinner=False)
def match_candidate(nome: str, cognome: str) -> dict[str, Any]:
    return api.get_client().match_candidate(nome=nome, cognome=cognome)


@st.cache_data(ttl=_TTL_SECONDS, show_spinner=False)
def list_drafts(kind: str | None, id_mcflash: str | None) -> list[dict[str, Any]]:
    return api.get_client().list_drafts(kind=kind, id_mcflash=id_mcflash)


@st.cache_data(ttl=600, show_spinner=False, max_entries=30)
def render_cv(data_json: str) -> dict[str, Any]:
    """Anteprima e .docx del CV MC. La chiave e' il JSON dei dati: stessi dati,
    nessuna nuova chiamata (le modifiche che non toccano il CV non lo rigenerano)."""
    import base64
    import json

    out = api.get_client().render_cv(json.loads(data_json))
    out["docx"] = base64.b64decode(out.pop("docx_base64", "") or "")
    return out


@st.cache_data(ttl=3600, show_spinner=False, max_entries=20)
def draft_original(draft_id: str) -> bytes:
    return api.get_client().draft_original(draft_id)


def clear_cache() -> None:
    list_candidates.clear()
    all_candidates.clear()
    get_candidate.clear()


def call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T | None:
    """Esegue una chiamata al backend; in caso di errore lo mostra e restituisce None."""
    try:
        return fn(*args, **kwargs)
    except api.BackendError as exc:
        st.error(str(exc))
        if exc.request_id:
            st.caption(f"request_id: `{exc.request_id}` (per cercare l'errore nei log della Function)")
        return None
