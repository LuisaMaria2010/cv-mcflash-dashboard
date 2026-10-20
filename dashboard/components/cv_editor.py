"""Editor della bozza, comune alle pagine Crea e Aggiorna.

Flusso: carica il CV -> POST /api/extract?profile=mcflash -> bozza salvata
(PUT /api/drafts/<id>) -> la pagina passa a ?bozza=<id> -> form modificabile,
salvato da solo a ogni modifica, con accanto l'anteprima del CV MC
(POST /api/cv/render, rigenerata solo quando i dati cambiano).

Stato in st.session_state["editor"]:
- draft_id, kind, id_mcflash, extracted (backup), original_filename
- base: i dati da cui partono i widget. Resta fisso finche' i widget esistono,
  perche' st.data_editor registra le modifiche rispetto ai dati iniziali.
- gen: entra nelle chiavi dei widget. Streamlit cancella lo stato dei widget
  quando si cambia pagina: tornando, si riparte da `current` con chiavi nuove.
- exps: esperienze e progetti con un uid stabile, cosi' aggiungere o togliere
  una voce non sposta i valori delle altre.
- current: i dati del form all'ultimo giro; saved_hash/saved_at: ultimo salvataggio.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import date, datetime
from typing import Any, Callable

import pandas as pd
import streamlit as st

from dashboard import api
from dashboard.components import backend, cv_preview
from dashboard.components.draft import (
    SENIORITY_VALUES,
    SITE_VALUES,
    STATE_BADGES,
    STATUS_LABELS,
    STEP_LABELS,
    changed_fields,
    changed_labels,
    commit_blockers,
    full_name,
    list_to_text,
    mcflash_defaults,
    tariff_for,
    text_to_list,
    to_date,
    to_iso,
    trittico,
)
from dashboard.config import load_settings

STATE_KEY = "editor"
ORIGINALS_KEY = "editor_originals"
MIN_DATE = date(1960, 1, 1)
DOT = " :orange[●]"


# ---------------------------------------------------------------- stato

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _wrap_experiences(experiences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"uid": _uid(), "base": exp, "projects": [{"uid": _uid(), "base": p} for p in exp.get("projects") or []]}
        for exp in experiences
    ]


def _payload(ed: dict[str, Any], edited: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ed["kind"], "id_mcflash": ed["id_mcflash"], "edited": edited,
            "filename": ed.get("filename") or None, "user": load_settings().user or None}


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _state_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    edited = copy.deepcopy(draft.get("edited") or {})
    ed = {
        "draft_id": draft["draft_id"],
        "kind": draft["kind"],
        "id_mcflash": draft.get("id_mcflash"),
        "extracted": draft.get("extracted") or {},
        "original_filename": draft.get("original_filename"),
        "filename": draft.get("filename") or "",
        "filename_auto": not draft.get("filename"),
        "base": edited,
        "current": edited,
        "gen": 0,
        "exps": _wrap_experiences(edited.get("experiences") or []),
        "saved_at": draft.get("updated_at"),
        "operation_id": draft.get("operation_id"),
    }
    ed["saved_hash"] = _hash(_payload(ed, edited))
    return ed


def load(draft_id: str) -> dict[str, Any] | None:
    """Stato dell'editor per la bozza; la legge dal backend se e' un'altra bozza."""
    ed = st.session_state.get(STATE_KEY)
    if ed and ed["draft_id"] == draft_id:
        return ed
    draft = backend.call(api.get_client().get_draft, draft_id)
    if draft is None:
        return None
    ed = _state_from_draft(draft)
    st.session_state[STATE_KEY] = ed
    return ed


def forget() -> None:
    st.session_state.pop(STATE_KEY, None)


def _prefix(ed: dict[str, Any]) -> str:
    return f"ed_{ed['draft_id'][:8]}_{ed['gen']}_"


def _revive(ed: dict[str, Any]) -> None:
    """Rientro nella pagina dopo un cambio pagina: i widget non esistono piu'.
    Si riparte dai dati correnti con chiavi nuove."""
    if f"{_prefix(ed)}first_name" in st.session_state or ed["gen"] == 0 and ed["current"] is ed["base"]:
        return
    ed["gen"] += 1
    ed["base"] = copy.deepcopy(ed["current"])
    ed["exps"] = _wrap_experiences(ed["base"].get("experiences") or [])


def set_kind(ed: dict[str, Any], kind: str, id_mcflash: str | None) -> bool:
    """Trasforma la bozza (es. da Crea ad Aggiorna) e la salva subito."""
    ed["kind"], ed["id_mcflash"] = kind, id_mcflash
    ed["filename_auto"], ed["filename"] = True, ""
    return save(ed, force=True)


def save(ed: dict[str, Any], *, force: bool = False) -> bool:
    payload = _payload(ed, ed["current"])
    digest = _hash(payload)
    if digest == ed["saved_hash"] and not force:
        return True
    saved = backend.call(api.get_client().save_draft, ed["draft_id"], payload)
    if saved is None:
        return False
    ed["saved_hash"], ed["saved_at"] = digest, saved.get("updated_at")
    backend.list_drafts.clear()
    return True


# ---------------------------------------------------------------- caricamento ed estrazione

def upload_and_extract(kind: str, id_mcflash: str | None = None,
                       adjust: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> str | None:
    """Caricatore del CV + pulsante "Estrai". Restituisce il draft_id della bozza creata."""
    uploaded = st.file_uploader("CV del candidato (PDF o DOCX)", type=["pdf", "docx"],
                                key=f"upload_{kind}_{id_mcflash or ''}")
    if uploaded is None:
        return None
    st.caption(f"«{uploaded.name}» · {uploaded.size / 1024:.0f} KB")
    if not st.button("Estrai i dati dal CV", type="primary", icon=":material/auto_awesome:"):
        return None
    return extract_to_draft(kind, id_mcflash, uploaded.getvalue(), uploaded.name, adjust=adjust)


def start_from_data(kind: str, id_mcflash: str | None, edited: dict[str, Any]) -> str | None:
    """Bozza senza CV, con i dati gia' noti (es. il record MCFlash): il form si
    compila da qui e il CV si aggiunge dopo, caricandolo o cercandolo nell'archivio."""
    draft_id = uuid.uuid4().hex
    payload = {"kind": kind, "id_mcflash": id_mcflash, "extracted": edited, "edited": edited,
               "user": load_settings().user or None}
    if backend.call(api.get_client().save_draft, draft_id, payload) is None:
        return None
    backend.list_drafts.clear()
    forget()
    return draft_id


def extract_to_draft(kind: str, id_mcflash: str | None, data: bytes, filename: str,
                     label: str = "Estrazione dei dati dal CV…",
                     adjust: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> str | None:
    """Estrae i dati da un CV (caricato o gia' indicizzato) e li salva in una bozza nuova.
    `adjust` corregge l'estratto prima di salvarlo (es. identita' dal record MCFlash)."""
    client = api.get_client()
    with st.status(label, expanded=True) as status:
        st.write("L'LLM legge il CV e compila i campi del modello MC: per un CV lungo servono fino a un paio di minuti.")
        extraction = backend.call(client.extract, data, filename)
        if extraction is None:
            status.update(label="Estrazione non riuscita", state="error")
            return None
        draft_id = uuid.uuid4().hex
        original_blob = extraction.pop("original_blob", None)
        original_filename = extraction.pop("original_filename", None) or filename
        if adjust:
            extraction = adjust(extraction)
        payload = {"kind": kind, "id_mcflash": id_mcflash, "extracted": extraction, "edited": extraction,
                   "original_blob": original_blob, "original_filename": original_filename,
                   "user": load_settings().user or None}
        if backend.call(client.save_draft, draft_id, payload) is None:
            status.update(label="Dati estratti, ma la bozza non è stata salvata", state="error")
            return None
        status.update(label="Dati estratti e bozza salvata", state="complete")
    st.session_state.setdefault(ORIGINALS_KEY, {})[draft_id] = data
    backend.list_drafts.clear()
    forget()
    return draft_id


def original_bytes(ed: dict[str, Any]) -> bytes | None:
    cached = st.session_state.get(ORIGINALS_KEY, {}).get(ed["draft_id"])
    if cached:
        return cached
    try:
        return backend.draft_original(ed["draft_id"])
    except api.BackendError:
        return None


def drafts_to_resume(kind: str, id_mcflash: str | None, page: str, extra_params: dict[str, str] | None = None) -> None:
    """Elenco delle bozze da riprendere, con un link per ciascuna."""
    drafts = backend.call(backend.list_drafts, kind, id_mcflash)
    if not drafts:
        return
    st.markdown("##### :material/history: Bozze da riprendere")
    for d in drafts[:10]:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            when = _local_time(d.get("updated_at"), with_date=True)
            c1.markdown(f"**{d.get('nome') or 'senza nome'}** `{d.get('trittico') or '—'}` · "
                        f"{d.get('original_filename') or ''}  \n:gray[ultima modifica {when}]")
            c2.page_link(page, label="Riprendi", icon=":material/edit_note:",
                         query_params={**(extra_params or {}), "bozza": d["draft_id"]})


def _local_time(iso: str | None, *, with_date: bool = False) -> str:
    if not iso:
        return "—"
    try:
        moment = datetime.fromisoformat(iso).astimezone()
    except ValueError:
        return iso
    return moment.strftime("%d/%m %H:%M" if with_date else "%H:%M:%S")


# ---------------------------------------------------------------- widget di supporto

def _label(text: str, changed: bool) -> str:
    return text + (DOT if changed else "")


def _table(ed: dict[str, Any], key: str, rows: list[dict[str, Any]], columns: dict[str, str],
           config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Lista modificabile (righe aggiungibili e cancellabili) -> lista di dizionari."""
    frame = pd.DataFrame([{c: r.get(c) for c in columns} for r in rows], columns=list(columns))
    frame = frame.astype(object).where(frame.notna(), None).rename(columns=columns)
    out = st.data_editor(frame, key=f"{_prefix(ed)}{key}", num_rows="dynamic", hide_index=True,
                         width="stretch", column_config=config or {})
    back = {v: k for k, v in columns.items()}
    result = []
    for rec in out.to_dict("records"):
        item = {back[c]: (None if pd.isna(v) else v) if not isinstance(v, (list, dict)) else v for c, v in rec.items()}
        if any(v not in (None, "") for v in item.values()):
            result.append(item)
    return result


def _levels(kind: str, rows: list[dict[str, Any]]) -> list[str]:
    try:
        scale = list(backend.mc_levels().get(kind) or [])
    except api.BackendError:
        scale = []
    extra = [r.get("level") for r in rows if r.get("level") and r.get("level") not in scale]
    return scale + sorted(set(extra))


def _date(label: str, value: Any, key: str, col) -> str | None:
    picked = col.date_input(label, value=to_date(value), min_value=MIN_DATE, max_value=date.today(),
                            format="DD/MM/YYYY", key=key)
    return to_iso(picked)


# ---------------------------------------------------------------- sezioni del form

def _personal(ed: dict[str, Any], base: dict[str, Any], changed: set[str]) -> dict[str, Any]:
    p = _prefix(ed)
    c1, c2 = st.columns(2)
    first = c1.text_input(_label("Nome", "first_name" in changed), value=base.get("first_name") or "", key=f"{p}first_name")
    last = c2.text_input(_label("Cognome", "last_name" in changed), value=base.get("last_name") or "", key=f"{p}last_name")
    tri = trittico(first, last)
    if tri:
        st.markdown(f"Trittico: :blue-badge[**{tri}**] :gray[(prima lettera del nome + prime due del cognome)]")
    else:
        st.warning("Trittico non calcolabile: servono nome e cognome (almeno due lettere).")
    c1, c2 = st.columns(2)
    email = c1.text_input(_label("Email", "email" in changed), value=base.get("email") or "", key=f"{p}email",
                          help="Va solo su MCFlash: il CV MC resta anonimo.")
    phone = c2.text_input(_label("Telefono", "phone" in changed), value=base.get("phone") or "", key=f"{p}phone",
                          help="Va solo su MCFlash: il CV MC resta anonimo.")
    c1, c2, c3 = st.columns(3)
    age = c1.number_input(_label("Età", "age" in changed), min_value=0, max_value=99, step=1,
                          value=int(base["age"]) if str(base.get("age") or "").isdigit() else None, key=f"{p}age")
    birth = _date(_label("Data di nascita", "birth_date" in changed), base.get("birth_date"), f"{p}birth_date", c2)
    location = c3.text_input(_label("Città", "location" in changed), value=base.get("location") or "", key=f"{p}location")
    return {"first_name": first.strip() or None, "last_name": last.strip() or None, "email": email.strip() or None,
            "phone": phone.strip() or None, "age": age, "birth_date": birth, "location": location.strip() or None,
            "trittico": tri, "full_name": full_name(first, last)}


def _profile(ed: dict[str, Any], base: dict[str, Any], changed: set[str]) -> dict[str, Any]:
    p = _prefix(ed)
    try:
        catalog = backend.roles()
    except api.BackendError:
        catalog = []
    labels = {r["role"]: r["label"] for r in catalog}
    current = base.get("catalog_role")
    options = ([current] if current and current not in labels else []) + list(labels)
    budget = {r["role"]: r.get("budget") or {} for r in catalog}

    def fmt(role: str) -> str:
        tariffe = budget.get(role) or {}
        values = " / ".join(f"{int(v)}" for v in (tariffe.get("junior"), tariffe.get("mid"), tariffe.get("senior")) if v)
        return f"{labels.get(role, role)}" + (f"  ·  € {values}" if values else "")

    catalog_role = st.selectbox(_label("Ruolo in alto nel CV (catalogo MC)", "catalog_role" in changed), options,
                                index=options.index(current) if current in options else None, format_func=fmt,
                                placeholder="Scegli un ruolo del catalogo", key=f"{p}catalog_role",
                                on_change=_refill_budget, args=(ed,),
                                help="Tariffe junior / mid / senior dal catalogo MC.")
    role = st.text_input(_label("Ruolo scritto nel CV", "role" in changed), value=base.get("role") or "", key=f"{p}role")
    return {"catalog_role": catalog_role, "role": role.strip() or None}


def _skills_and_languages(ed: dict[str, Any], base: dict[str, Any], changed: set[str]) -> dict[str, Any]:
    skills_rows = base.get("cv_skills") or []
    st.markdown(_label("**Skill**", "cv_skills" in changed))
    skills = _table(ed, "cv_skills", skills_rows, {"name": "Skill", "level": "Livello"}, {
        "Skill": st.column_config.TextColumn(required=True, width="medium"),
        "Livello": st.column_config.SelectboxColumn(options=_levels("skill", skills_rows), width="medium"),
    })
    lang_rows = base.get("languages") or []
    st.markdown(_label("**Lingue**", "languages" in changed))
    languages = _table(ed, "languages", lang_rows, {"lang": "Lingua", "level": "Livello"}, {
        "Lingua": st.column_config.TextColumn(required=True),
        "Livello": st.column_config.SelectboxColumn(options=_levels("lingua", lang_rows)),
    })
    return {"cv_skills": skills, "languages": languages}


def _period_widgets(p: str, base: dict[str, Any], changed: set[str], prefix: str) -> dict[str, Any]:
    c1, c2, c3 = st.columns([1, 1, 0.7], vertical_alignment="bottom")
    start = _date(_label("Inizio", f"{prefix}.start_date" in changed), base.get("start_date"), f"{p}start", c1)
    ongoing = c3.checkbox(_label("In corso", f"{prefix}.ongoing" in changed), value=bool(base.get("ongoing")),
                          key=f"{p}ongoing")
    end = None if ongoing else _date(_label("Fine", f"{prefix}.end_date" in changed), base.get("end_date"), f"{p}end", c2)
    if ongoing:
        c2.text_input("Fine", value="in corso", disabled=True, key=f"{p}end_off")
    return {"start_date": start, "end_date": end, "ongoing": ongoing}


def _project(ed: dict[str, Any], exp_uid: str, item: dict[str, Any], on_remove: Callable[[], None]) -> dict[str, Any]:
    base, p = item["base"], f"{_prefix(ed)}prj_{item['uid']}_"
    with st.container(border=True):
        out = _period_widgets(p, base, set(), "")
        c1, c2 = st.columns(2)
        name = c1.text_input("Progetto", value=base.get("name") or "", key=f"{p}name")
        role = c2.text_input("Ruolo nel progetto (se diverso)", value=base.get("role") or "", key=f"{p}role")
        activities = st.text_area("Attività", value=base.get("activities") or "", height=90, key=f"{p}activities")
        techs = st.text_input("Tecnologie utilizzate (separate da virgola)",
                              value=list_to_text(base.get("technologies")), key=f"{p}techs")
        st.button("Togli progetto", icon=":material/delete:", key=f"{p}remove", on_click=on_remove)
    return {**out, "name": name.strip() or None, "role": role.strip() or None,
            "activities": activities.strip() or None, "technologies": text_to_list(techs)}


def _experiences(ed: dict[str, Any], changed: set[str]) -> list[dict[str, Any]]:
    p0 = _prefix(ed)
    result = []

    def remove_exp(uid: str) -> Callable[[], None]:
        return lambda: ed.__setitem__("exps", [e for e in ed["exps"] if e["uid"] != uid])

    def add_project(exp: dict[str, Any]) -> Callable[[], None]:
        return lambda: exp["projects"].append({"uid": _uid(), "base": {}})

    def remove_project(exp: dict[str, Any], uid: str) -> Callable[[], None]:
        return lambda: exp.__setitem__("projects", [x for x in exp["projects"] if x["uid"] != uid])

    for i, exp in enumerate(ed["exps"]):
        base, p = exp["base"], f"{p0}exp_{exp['uid']}_"
        path = f"experiences[{i}]"
        company_now = st.session_state.get(f"{p}company", base.get("company")) or "Nuova esperienza"
        role_now = st.session_state.get(f"{p}role", base.get("role")) or "ruolo da indicare"
        mark = " ●" if any(c.startswith(path + ".") for c in changed) else ""
        with st.expander(f"{company_now} · {role_now}{mark}", key=f"{p}box"):
            period = _period_widgets(p, base, changed, path)
            c1, c2 = st.columns(2)
            company = c1.text_input(_label("Azienda", f"{path}.company" in changed), value=base.get("company") or "",
                                    key=f"{p}company")
            role = c2.text_input(_label("Ruolo", f"{path}.role" in changed), value=base.get("role") or "",
                                 key=f"{p}role", help="Obbligatorio: nel CV compare come «Ruolo: …».")
            if not role.strip():
                st.warning("Manca il ruolo: nel CV MC ogni esperienza ha «Ruolo: …».")
            description = st.text_area(_label("Attività", f"{path}.description" in changed),
                                       value=base.get("description") or "", height=110, key=f"{p}description")
            techs = st.text_input(_label("Tecnologie utilizzate (separate da virgola)", f"{path}.technologies" in changed),
                                  value=list_to_text(base.get("technologies")), key=f"{p}techs")
            st.markdown(_label("**Progetti**", f"{path}.projects" in changed))
            projects = [_project(ed, exp["uid"], prj, remove_project(exp, prj["uid"])) for prj in exp["projects"]]
            b1, b2 = st.columns(2)
            b1.button("Aggiungi progetto", icon=":material/add:", key=f"{p}add_prj", on_click=add_project(exp))
            b2.button("Togli esperienza", icon=":material/delete:", key=f"{p}remove", on_click=remove_exp(exp["uid"]))
        result.append({**base, **period, "company": company.strip() or None, "role": role.strip() or None,
                       "description": description.strip() or None, "technologies": text_to_list(techs),
                       "projects": [x for x in projects if any(v for k, v in x.items() if k != "ongoing")]})

    def add_exp() -> None:
        ed["exps"].insert(0, {"uid": _uid(), "base": {}, "projects": []})

    st.button("Aggiungi esperienza", icon=":material/add:", key=f"{p0}add_exp", on_click=add_exp)
    return result


def _education(ed: dict[str, Any], base: dict[str, Any], changed: set[str]) -> dict[str, Any]:
    st.markdown(_label("**Formazione**", "education" in changed))
    education = _table(ed, "education", base.get("education") or [],
                       {"year": "Anno", "title": "Titolo", "institution": "Istituto"},
                       {"Anno": st.column_config.TextColumn(width="small"), "Titolo": st.column_config.TextColumn(width="large")})
    st.markdown(_label("**Trainings**", "trainings" in changed))
    trainings = _table(ed, "trainings", base.get("trainings") or [],
                       {"year": "Anno", "title": "Titolo", "provider": "Ente"},
                       {"Anno": st.column_config.TextColumn(width="small"), "Titolo": st.column_config.TextColumn(width="large")})
    st.markdown(_label("**Certificazioni**", "certifications" in changed))
    certs = _table(ed, "certifications", [{"name": c} for c in base.get("certifications") or []],
                   {"name": "Certificazione"})
    return {"education": education, "trainings": trainings, "certifications": [c["name"] for c in certs if c.get("name")]}


def _refill_budget(ed: dict[str, Any]) -> None:
    """Cambiano seniority o ruolo: il budget prende la tariffa del catalogo, se
    e' vuoto o se era la tariffa proposta prima (non un valore scritto a mano)."""
    p = _prefix(ed)
    try:
        catalog = {r["role"]: r.get("budget") or {} for r in backend.roles()}
    except api.BackendError:
        return
    tariff = tariff_for(catalog.get(st.session_state.get(f"{p}catalog_role")), st.session_state.get(f"{p}mc_seniority"))
    current = st.session_state.get(f"{p}mc_budget")
    if tariff and (current in (None, 0) or current == ed.get("proposed_tariff")):
        st.session_state[f"{p}mc_budget"] = tariff
    ed["proposed_tariff"] = tariff


def _mcflash(ed: dict[str, Any], base: dict[str, Any], candidate: dict[str, Any] | None) -> dict[str, Any]:
    """Campi che stanno su MCFlash ma non nel CV: seniority, disponibilita', budget, site."""
    p = _prefix(ed)
    try:
        catalog = {r["role"]: r.get("budget") or {} for r in backend.roles()}
    except api.BackendError:
        catalog = {}
    role_key = st.session_state.get(f"{p}catalog_role", base.get("catalog_role"))
    defaults = mcflash_defaults(base, candidate, catalog.get(role_key))
    st.caption("Questi dati vanno solo su MCFlash, non nel CV."
               + (" Valori attuali del record: cambiali solo se serve." if candidate else ""))
    c1, c2 = st.columns(2)
    seniority_opts = list(SENIORITY_VALUES)
    if defaults.get("seniority") and defaults["seniority"] not in seniority_opts:
        seniority_opts.append(defaults["seniority"])
    seniority = c1.selectbox("Seniority", seniority_opts, key=f"{p}mc_seniority", on_change=_refill_budget, args=(ed,),
                             index=seniority_opts.index(defaults["seniority"]) if defaults.get("seniority") in seniority_opts else None,
                             placeholder="Scegli la seniority")
    site_opts = list(SITE_VALUES)
    if defaults.get("site") and defaults["site"] not in site_opts:
        site_opts.append(defaults["site"])
    site = c2.selectbox("Site", site_opts, key=f"{p}mc_site",
                        index=site_opts.index(defaults["site"]) if defaults.get("site") in site_opts else None)
    c1, c2 = st.columns(2)
    disponibilita = c1.text_input("Disponibilità", value=defaults.get("disponibilita") or "",
                                  key=f"{p}mc_disponibilita", placeholder="Immediata, 15 gg, 30 gg…")
    tariff = tariff_for(catalog.get(role_key), seniority)
    budget = c2.number_input("Budget (€/giorno)", min_value=0, max_value=5000, step=5, key=f"{p}mc_budget",
                             value=int(defaults["budget"]) if str(defaults.get("budget") or "").replace(".0", "").isdigit() else None,
                             help=f"Tariffa del catalogo MC per questo ruolo e seniority: € {tariff}" if tariff else None)
    return {"mcflash": {"seniority": seniority, "site": site, "disponibilita": disponibilita.strip() or None,
                        "budget": budget}}


# ---------------------------------------------------------------- form completo

def form(ed: dict[str, Any], candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    """Disegna il form e restituisce i dati correnti (salvati da `autosave`)."""
    _revive(ed)
    base = ed["base"]
    changed = changed_fields(ed["extracted"], ed["current"])

    def tab_label(icon: str, text: str, keys: tuple[str, ...]) -> str:
        hit = any(c.split("[")[0].split(".")[0] in keys for c in changed)
        return f"{icon} {text}" + (" ●" if hit else "")

    tabs = st.tabs([
        tab_label(":material/person:", "Anagrafica", ("first_name", "last_name", "email", "phone", "age",
                                                       "birth_date", "location", "catalog_role", "role")),
        tab_label(":material/psychology:", "Skill e lingue", ("cv_skills", "languages")),
        tab_label(":material/work:", "Esperienze", ("experiences",)),
        tab_label(":material/school:", "Formazione", ("education", "trainings", "certifications")),
        ":material/badge: MCFlash",
    ], key=f"{_prefix(ed)}tabs")
    edited = copy.deepcopy(base)
    with tabs[0]:
        edited.update(_personal(ed, base, changed))
        st.divider()
        edited.update(_profile(ed, base, changed))
    with tabs[1]:
        edited.update(_skills_and_languages(ed, base, changed))
    with tabs[2]:
        st.caption("Le date dei progetti spesso mancano nel CV: vanno completate a mano.")
        edited["experiences"] = _experiences(ed, changed)
    with tabs[3]:
        edited.update(_education(ed, base, changed))
    with tabs[4]:
        edited.update(_mcflash(ed, base, candidate))
    ed["current"] = edited
    return edited


def summary_bar(ed: dict[str, Any], on_discarded: Callable[[], None]) -> None:
    """Barra sopra le colonne: trittico, modifiche, nome del file, stato della bozza e azioni."""
    edited = ed["current"]
    tri = edited.get("trittico")
    with st.container(border=True):
        c_tri, c_changes, c_file, c_save = st.columns([0.7, 1.6, 1.8, 1.5], vertical_alignment="top")
        c_tri.metric("Trittico", tri or "—")
        changed = changed_labels(changed_fields(ed["extracted"], edited))
        with c_changes:
            st.markdown(":gray[Modifiche rispetto all'estratto]")
            if changed:
                st.markdown(" ".join(f":orange-badge[{label}]" for label in changed))
            else:
                st.caption("Nessuna modifica.")
        with c_file:
            _filename_input(ed, tri)
        with c_save:
            autosave(ed)
            actions(ed, on_discarded)


def _filename_input(ed: dict[str, Any], tri: str | None) -> None:
    key = f"ed_{ed['draft_id'][:8]}_filename"
    note = ""
    if tri:
        proposal = backend.call(backend.cv_filename, tri, ed["id_mcflash"])
        if proposal and ed["filename_auto"] and st.session_state.get(key) != proposal["filename"]:
            st.session_state[key] = proposal["filename"]
        if proposal and proposal.get("reused"):
            note = "Stesso nome del CV attuale: l'indice sostituirà il vecchio CV."
    st.session_state.setdefault(key, ed["filename"])

    def manual() -> None:
        ed["filename_auto"] = False

    ed["filename"] = st.text_input("Nome del file CV", key=key, on_change=manual,
                                   help="Proposto dal backend in base al trittico; si può cambiare.")
    if note:
        st.caption(note)


def autosave(ed: dict[str, Any]) -> None:
    """Salva la bozza se qualcosa e' cambiato; mostra quando e' stata salvata."""
    ok = save(ed)
    when = _local_time(ed.get("saved_at"))
    if ok:
        st.caption(f":material/cloud_done: Bozza salvata alle {when}")
    else:
        st.caption(f":material/cloud_off: Ultimo salvataggio alle {when}: le ultime modifiche non sono salvate")


def actions(ed: dict[str, Any], on_discarded: Callable[[], None]) -> None:
    confirm_panel(ed)
    c1, c2, c3 = st.columns(3)
    if c1.button("Salva", icon=":material/save:", width="stretch", key="ed_save",
                 help="La bozza si salva già da sola a ogni modifica"):
        if save(ed, force=True):
            st.toast("Bozza salvata", icon=":material/check:")
    c2.download_button("Dati", json.dumps(ed["current"], ensure_ascii=False, indent=2, default=str),
                       file_name=f"bozza_{ed['draft_id'][:8]}.json", mime="application/json",
                       icon=":material/download:", width="stretch", key="ed_download",
                       help="Scarica i dati della bozza in JSON")
    with c3.popover("Scarta", icon=":material/delete:", width="stretch"):
        st.caption("La bozza viene cancellata. Il CV caricato resta nell'archivio degli originali.")
        if st.button("Scarta definitivamente", type="primary", key="ed_discard"):
            if backend.call(api.get_client().delete_draft, ed["draft_id"]) is not None:
                backend.list_drafts.clear()
                forget()
                on_discarded()


def _commit_summary(ed: dict[str, Any]) -> list[str]:
    edited = ed["current"]
    name = ed.get("filename") or "—"
    stem = name.rsplit(".", 1)[0]
    if ed["kind"] == "crea":
        mcflash = f"si crea il candidato **{edited.get('full_name') or '—'}** (`{edited.get('trittico') or '—'}`)"
    else:
        mcflash = f"si aggiorna la riga **Id {ed['id_mcflash']}**"
    return [
        f"**Storage**: il CV originale resta in archivio"
        + ("; il CV MC attuale va nello storico" if ed["kind"] == "aggiorna" else ""),
        f"**MCFlash** (finto finché non arriva l'endpoint di scrittura): {mcflash}",
        f"**Indice**: il CV MC «{stem}.docx» va in `incoming-cv` e la pipeline lo indicizza"
        + (" sostituendo il CV attuale" if ed["kind"] == "aggiorna" else ""),
        "**Mappa**: il CV viene collegato al candidato appena è indicizzato",
    ]


def confirm_panel(ed: dict[str, Any]) -> None:
    """Pulsante "Conferma e carica" con il riepilogo di cosa succede."""
    blockers = commit_blockers(ed["current"], ed["kind"])
    with st.popover("Conferma e carica", icon=":material/rocket_launch:", type="primary",
                    width="stretch", disabled=bool(blockers),
                    help=("Mancano: " + ", ".join(blockers)) if blockers else None):
        st.markdown("**Alla conferma:**")
        for line in _commit_summary(ed):
            st.markdown(f"- {line}")
        st.caption("Dopo la conferma la bozza non si modifica più.")
        if st.button("Conferma", type="primary", key="ed_commit", icon=":material/check:"):
            if not save(ed):
                return
            op = backend.call(api.get_client().commit, ed["draft_id"], user=load_settings().user or None)
            if op is not None:
                ed["operation_id"] = op["id"]
                st.session_state[f"op_{op['id']}"] = op
                backend.clear_cache()
                backend.list_drafts.clear()
                st.rerun()
    if blockers:
        st.caption(":orange[Per confermare mancano: " + ", ".join(blockers) + "]")


def operation_panel(op_id: str) -> dict[str, Any] | None:
    """Stato di un'operazione di conferma: un passo per riga. Si aggiorna da solo
    ogni 5 secondi finche' e' in corso (l'indicizzazione richiede qualche minuto)."""
    key = f"op_{op_id}"

    @st.fragment(run_every=5 if (st.session_state.get(key) or {}).get("status", "in_corso") == "in_corso" else None)
    def _panel() -> None:
        op = backend.call(api.get_client().get_operation, op_id)
        if op is None:
            return
        previous = (st.session_state.get(key) or {}).get("status")
        st.session_state[key] = op
        status = op.get("status")
        color = {"completata": "green", "fallita": "red"}.get(status, "blue")
        with st.container(border=True):
            st.markdown(f"##### :material/conveyor_belt: Operazione :{color}-badge[{STATUS_LABELS.get(status, status)}]")
            for step, label in STEP_LABELS.items():
                c1, c2 = st.columns([1, 3])
                c1.markdown(f"**{label}**")
                c2.markdown(STATE_BADGES.get(op.get(f"step_{step}"), op.get(f"step_{step}") or "—"))
            if op.get("error"):
                st.error(f"{STEP_LABELS.get(op.get('error_step'), op.get('error_step'))}: {op['error']}")
                if st.button("Riprova", icon=":material/replay:", key=f"retry_{op_id}"):
                    retried = backend.call(api.get_client().retry_operation, op_id)
                    if retried:
                        st.session_state[key] = retried
                        st.rerun()
            details = [("Id MCFlash", op.get("id_mcflash")), ("CV nell'indice", op.get("incoming_blob")),
                       ("document_id", op.get("document_id")), ("Storico", op.get("history_blob")),
                       ("MCFlash", op.get("mcflash_mode")), ("operation_id", op.get("id")),
                       ("request_id", op.get("last_request_id"))]
            st.caption(" · ".join(f"{k}: `{v}`" for k, v in details if v))
            if status == "in_corso":
                st.caption("Si aggiorna da solo ogni 5 secondi: l'indicizzazione richiede qualche minuto.")
        if previous == "in_corso" and status != "in_corso":
            backend.clear_cache()
            st.rerun()  # ferma l'aggiornamento automatico

    _panel()
    return st.session_state.get(key)


def committed_view(ed: dict[str, Any]) -> None:
    """Bozza gia' confermata: stato dell'operazione e CV generato, in sola lettura."""
    col_op, col_mc = st.columns([1, 1.15], gap="medium")
    with col_op:
        op = operation_panel(ed["operation_id"])
        if op and op.get("id_mcflash"):
            st.page_link("views/aggiorna.py", label="Apri il candidato", icon=":material/person:",
                         query_params={"id": op["id_mcflash"]})
        st.page_link("views/operazioni.py", label="Tutte le operazioni", icon=":material/monitoring:")
    with col_mc:
        st.markdown("##### :material/preview: CV MC caricato")
        mc_preview(ed)


def _docx_name(ed: dict[str, Any]) -> str:
    stem = (ed.get("filename") or f"CV_{ed['current'].get('trittico') or 'MC'}").rsplit(".", 1)[0]
    return f"{stem}.docx"


def mc_preview(ed: dict[str, Any]) -> None:
    """Anteprima del CV nel modello MC, rigenerata quando cambiano i dati."""
    data_json = json.dumps(ed["current"], sort_keys=True, ensure_ascii=False, default=str)
    with st.spinner("Genero il CV MC…"):
        result = backend.call(backend.render_cv, data_json)
    if result is None:
        return
    checks = result.get("checks") or []
    if checks:
        with st.expander(f"Da completare ({len(checks)})", icon=":material/rule:", expanded=len(checks) <= 3):
            for item in checks:
                st.markdown(f"- {item}")
    else:
        st.success("Il CV ha tutte le informazioni principali.", icon=":material/task_alt:")
    with st.container(height=cv_preview.PREVIEW_HEIGHT, border=False):
        st.html(result.get("html") or "")
    st.caption("Impaginazione indicativa: nel .docx le pagine hanno intestazione e footer ripetuti.")
    st.download_button("Scarica .docx", result.get("docx") or b"", file_name=_docx_name(ed),
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       icon=":material/download:", type="primary", width="stretch",
                       disabled=not result.get("docx"), key="ed_docx")


def workspace(ed: dict[str, Any], on_discarded: Callable[[], None],
              above: Callable[[dict[str, Any]], None] | None = None,
              candidate: dict[str, Any] | None = None,
              no_cv: Callable[[dict[str, Any]], None] | None = None) -> None:
    """Barra di riepilogo e tre colonne: CV caricato, dati estratti, anteprima del CV MC.
    Una bozza senza CV (partita dai dati MCFlash) mostra nella prima colonna `no_cv`:
    caricamento e ricerca nell'archivio. Una bozza gia' confermata mostra invece
    lo stato della sua operazione."""
    if ed.get("operation_id"):
        committed_view(ed)
        return
    bar = st.container()
    extra = st.container()
    col_cv, col_form, col_mc = st.columns([1.05, 1.3, 1.15], gap="medium")
    with col_form:
        st.markdown("##### :material/edit_note: 2 · Dati estratti")
        form(ed, candidate)
    with col_cv:
        if not ed.get("original_filename") and no_cv:
            st.markdown("##### :material/upload_file: 1 · CV")
            st.info("Nessun CV: il form è compilato con i dati già noti. Carica il CV oppure cercalo nell'archivio.",
                    icon=":material/description:")
            no_cv(ed)
        else:
            st.markdown("##### :material/upload_file: 1 · CV caricato")
            cv_preview.show_original(ed["original_filename"], original_bytes(ed))
    with col_mc:
        st.markdown("##### :material/preview: 3 · Anteprima CV MCFlash")
        mc_preview(ed)
    # Riepilogo dopo il form (servono i dati correnti), mostrato sopra le colonne.
    with bar:
        summary_bar(ed, on_discarded)
    if above:
        with extra:
            above(ed)
