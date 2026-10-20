"""Pannello "Cerca nell'archivio": CV gia' indicizzati probabilmente della persona.

Stesse regole della ricostruzione della tabella CV -> MCFlash (nel backend,
domain/cv_matching.py). Un pulsante cerca i CV con lo stesso codice
(POST /api/cv-finder, modo "codice") e mostra l'esito che darebbe la
ricostruzione: CV assegnato, caso dubbio, nessun CV o decisione manuale. Se non
convince, "Cerca ancora" allarga a codici simili con eta' o mestiere
compatibili (modo "esteso"), senza ripetere i CV gia' mostrati.

Ogni CV ha il livello (eta' e mestiere), il giudizio dell'LLM sul mestiere e
l'eventuale candidato a cui e' gia' collegato. Dal risultato si apre
l'anteprima, si usa il CV come se fosse stato caricato ("Usa il CV") oppure,
per un candidato senza CV, lo si collega cosi' com'e' ("Collega").

I risultati restano in st.session_state["cv_finder"][<chiave>] finche' non si
ricomincia la ricerca.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

import streamlit as st

from dashboard import api
from dashboard.components import backend, cv_preview

STATE_KEY = "cv_finder"
LEVELS = {
    1: ":green-badge[:material/verified: età e mestiere compatibili]",
    2: ":green-badge[:material/check: mestiere compatibile, età non verificabile]",
    3: ":orange-badge[età compatibile, mestiere diverso]",
    4: ":orange-badge[mestiere compatibile, età che non torna]",
    9: ":gray-badge[né età né mestiere]",
}


def _state(key: str) -> dict[str, Any]:
    return st.session_state.setdefault(STATE_KEY, {}).setdefault(
        key, {"results": [], "modes": [], "esito": None, "codici": []})


def reset(key: str) -> None:
    st.session_state.setdefault(STATE_KEY, {}).pop(key, None)


def _search(key: str, person: dict[str, Any], mode: str) -> None:
    state = _state(key)
    shown = [r["document_id"] for r in state["results"]]
    with st.spinner("Cerco nell'archivio e valuto ogni CV con le regole della ricostruzione…"):
        found = backend.call(api.get_client().find_cvs, modo=mode, escludi=shown, **person)
    if found is None:
        return
    state["results"] += found["risultati"]
    if mode == "codice":
        state["esito"] = found.get("esito")
        persona = found.get("persona") or {}
        state["codici"] = persona.get("codici") or [c for c in [persona.get("trittico")] if c]
    state["modes"].append(mode)


def search_now(key: str, person: dict[str, Any]) -> None:
    """Nuova ricerca per codice (si perdono i risultati precedenti)."""
    reset(key)
    _search(key, person, "codice")


def _when(iso: str | None) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"
    except ValueError:
        return iso or "—"


def _outcome(esito: dict[str, Any] | None) -> None:
    """Esito della ricostruzione per la persona."""
    if not esito:
        return
    decision, why = esito.get("decisione"), esito.get("motivo") or ""
    if decision == "assegnato":
        st.success(f"Con le regole della ricostruzione il CV è **{esito['file']}** ({why}).", icon=":material/task_alt:")
    elif decision == "manuale":
        target = f" CV: **{esito['file']}**." if esito.get("file") else ""
        st.info(f"Decisione manuale già presa: {why}.{target}", icon=":material/gavel:")
    elif decision == "solo codice":
        st.info("Ecco i CV con questo codice. Aggiungi ruolo ed età e cerca di nuovo per valutarli con le regole "
                "della ricostruzione.", icon=":material/info:")
    elif decision == "dubbio":
        st.warning(f"Caso dubbio ({why}): scegli tu tra i CV qui sotto.", icon=":material/help:")
    else:
        st.info("Nessun CV con questo codice ha età o mestiere compatibili.", icon=":material/search_off:")


def _card(key: str, r: dict[str, Any], on_use: Callable[[str, bytes], None],
          on_link: Callable[[dict[str, Any]], None] | None) -> None:
    doc = r["document_id"]
    with st.container(border=True):
        chosen = " :blue-badge[:material/star: proposto]" if r.get("scelto") else ""
        level = LEVELS.get(r.get("livello"), ":gray-badge[da valutare]")
        st.markdown(f"**{r['file']}**{chosen}  \n{level}")
        age = ""
        if r.get("eta_cv") is not None:
            delta = f", {r['eta_delta']:+d} rispetto a MCFlash" if r.get("eta_delta") is not None else ""
            age = f" ({r['eta_cv']} anni{delta})"
        st.markdown(f":gray[Nato {_when(r.get('nato'))}{age} · {r.get('citta') or 'città —'} · "
                    f"{r.get('ruolo_cv') or 'ruolo —'}]")
        if r.get("mestiere_ok") is not None:
            st.caption(f"Mestiere {'compatibile' if r.get('mestiere_ok') else 'diverso'}: {r.get('motivo') or '—'}"
                       + (" · stessa città" if r.get("stessa_citta") else ""))
        if r.get("collegato_a"):
            owner = r["collegato_a"]
            st.warning(f"Già collegato a {owner.get('nome') or 'un altro candidato'} (Id {owner.get('id')}).",
                       icon=":material/link:")
        if r.get("riservato"):
            st.warning(r["riservato"].capitalize() + ".", icon=":material/gavel:")
        if r.get("gia_suo"):
            st.info("È già il CV collegato a questo candidato.", icon=":material/link:")
        show = st.toggle("Anteprima", key=f"fp_{key}_{doc}")
        can_link = on_link and not r.get("collegato_a") and not r.get("gia_suo") and not r.get("riservato")
        c1, c2 = st.columns(2)
        if c1.button("Usa il CV", key=f"fu_{key}_{doc}", icon=":material/auto_awesome:", width="stretch",
                     help="Estrae i dati dal CV e apre il form, come se l'avessi caricato"):
            got = backend.call(backend.cv_file, doc)
            if got:
                on_use(*got)
        if can_link and c2.button("Collega", key=f"fl_{key}_{doc}", icon=":material/link:", width="stretch",
                                  help="Collega questo CV al candidato su MCFlash così com'è, senza modificarlo"):
            on_link(r)
        if show:
            got = backend.call(backend.cv_file, doc)
            if got:
                cv_preview.show_original(got[0], got[1], height=520)


def panel(key: str, person: dict[str, Any], *, on_use: Callable[[str, bytes], None],
          on_link: Callable[[dict[str, Any]], None] | None = None, title: str = "Cerca nell'archivio",
          show_start: bool = True) -> None:
    """Pannello completo. `person` va a /api/cv-finder (id_mcflash, oppure nome, cognome, trittico, ruolo,
    eta, sede). Con show_start=False la ricerca la avvia la pagina (search_now) e qui si vedono i risultati."""
    state = _state(key)
    if "codice" not in state["modes"] and not show_start:
        return
    st.markdown(f"##### :material/manage_search: {title}")
    if "codice" not in state["modes"]:
        st.caption("Cerca tra i CV dell'archivio quelli con il codice della persona e li valuta con le stesse "
                   "regole della ricostruzione: età, mestiere (giudizio dell'LLM), città, CV già collegati.")
        if st.button("Cerca nell'archivio", key=f"fs_{key}", type="primary", icon=":material/search:"):
            _search(key, person, "codice")
            st.rerun()
        return

    if state.get("codici"):
        st.caption(f"Codici cercati: {', '.join(state['codici'])}")
    _outcome(state["esito"])
    good = [r for r in state["results"] if r.get("scelto") or r.get("livello") is None or r["livello"] < 9]
    other = [r for r in state["results"] if r not in good]
    if not state["results"]:
        st.caption("Nessun CV nell'archivio con questo codice." if state["modes"] == ["codice"]
                   else "Nessun CV nell'archivio sembra di questa persona.")
    for r in good:
        _card(key, r, on_use, on_link)
    if other:
        with st.expander(f"CV scartati ({len(other)})", icon=":material/filter_alt_off:"):
            for r in other:
                _card(key, r, on_use, on_link)

    c1, c2 = st.columns(2)
    if "esteso" not in state["modes"]:
        if c1.button("Non mi convince: cerca ancora", key=f"fe_{key}", icon=":material/travel_explore:",
                     help="Allarga a codici simili (refusi, lettere scambiate) con età o mestiere compatibili"):
            _search(key, person, "esteso")
            st.rerun()
    else:
        c1.caption("Ricerca estesa fatta: oltre a questi non ci sono altri CV compatibili.")
    if c2.button("Ricomincia", key=f"fr_{key}", icon=":material/restart_alt:"):
        reset(key)
        st.rerun()
