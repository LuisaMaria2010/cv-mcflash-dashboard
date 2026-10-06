"""Dati della bozza: trittico, confronto tra estratto e versione corretta, conversioni.

La bozza segue il formato di POST /api/extract?profile=mcflash (CVExtraction del
backend): lo stesso dizionario andra' poi a /api/cv/render. Nessuna chiamata a
Streamlit qui.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Iterable

# Campi modificabili nel form -> etichetta per il riepilogo delle modifiche.
FIELD_LABELS: dict[str, str] = {
    "first_name": "Nome",
    "last_name": "Cognome",
    "email": "Email",
    "phone": "Telefono",
    "age": "Età",
    "birth_date": "Data di nascita",
    "location": "Città",
    "catalog_role": "Ruolo MC",
    "role": "Ruolo nel CV",
    "cv_skills": "Skill",
    "languages": "Lingue",
    "experiences": "Esperienze",
    "education": "Formazione",
    "trainings": "Trainings",
    "certifications": "Certificazioni",
}

EXPERIENCE_FIELDS = ("start_date", "end_date", "ongoing", "company", "role", "description", "technologies", "projects")
PROJECT_FIELDS = ("start_date", "end_date", "ongoing", "name", "role", "activities", "technologies")


# ---------------------------------------------------------------- trittico

def _ascii_letters(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z]", "", no_marks).upper()


def trittico(first_name: str | None, last_name: str | None) -> str | None:
    """Prima lettera del nome + prime due lettere del cognome.

    Stessa regola di domain/candidate_identity.trittico nel backend: si ricalcola
    qui mentre l'utente scrive, senza una chiamata per ogni tasto.
    """
    first = _ascii_letters(first_name or "")
    last = _ascii_letters(last_name or "")
    if not first or len(last) < 2:
        return None
    return first[0] + last[:2]


# ---------------------------------------------------------------- confronto

def normalize(value: Any) -> Any:
    """Forma canonica per il confronto: stringhe ripulite, vuoti -> None,
    righe vuote tolte dalle liste."""
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [normalize(v) for v in value]
        return [v for v in items if not _is_empty(v)]
    return value


def _is_empty(value: Any) -> bool:
    if value is None or value == [] or value is False:
        return True
    if isinstance(value, dict):
        return all(_is_empty(v) for v in value.values())
    return False


def changed_fields(extracted: dict[str, Any] | None, edited: dict[str, Any]) -> set[str]:
    """Percorsi modificati rispetto all'estratto: "email", "experiences",
    "experiences[1].role", "experiences[1].projects"..."""
    base = extracted or {}
    changed: set[str] = set()
    for key in FIELD_LABELS:
        if normalize(base.get(key)) != normalize(edited.get(key)):
            changed.add(key)
    old_exps = base.get("experiences") or []
    for i, exp in enumerate(edited.get("experiences") or []):
        old = old_exps[i] if i < len(old_exps) else {}
        for field in EXPERIENCE_FIELDS:
            if normalize(old.get(field)) != normalize(exp.get(field)):
                changed.add(f"experiences[{i}].{field}")
    return changed


def changed_labels(changed: Iterable[str]) -> list[str]:
    """Sezioni modificate, in ordine di form: ["Email", "Esperienze"]."""
    tops = {path.split("[")[0].split(".")[0] for path in changed}
    return [label for key, label in FIELD_LABELS.items() if key in tops]


# ---------------------------------------------------------------- conversioni

def to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def to_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def list_to_text(items: Iterable[Any] | None) -> str:
    return ", ".join(str(i).strip() for i in (items or []) if str(i).strip())


def text_to_list(text: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]", text or "") if part.strip()]


def full_name(first: str | None, last: str | None) -> str | None:
    name = " ".join(p.strip() for p in (first or "", last or "") if p and p.strip())
    return name or None


# ---------------------------------------------------------------- dati MCFlash e conferma

SENIORITY_VALUES = ("Neo", "Junior", "Medium", "Senior")
SITE_VALUES = ("mcflashcandidati.mcengineering.eu", "mcflashrisorse")
DEFAULT_SITE = SITE_VALUES[0]
# Seniority stimata dall'estrazione -> valore MCFlash; seniority MCFlash -> colonna delle tariffe.
_SENIORITY_FROM_EXTRACTION = {"junior": "Junior", "mid": "Medium", "medium": "Medium", "senior": "Senior"}
_TARIFF_COLUMN = {"Neo": "junior", "Junior": "junior", "Medium": "mid", "Senior": "senior"}


def tariff_for(budget: dict[str, Any] | None, seniority: str | None) -> int | None:
    """Tariffa del catalogo MC per la seniority (Neo e Junior usano la junior)."""
    value = (budget or {}).get(_TARIFF_COLUMN.get(seniority or "", ""))
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def mcflash_defaults(edited: dict[str, Any], candidate: dict[str, Any] | None,
                     role_budget: dict[str, Any] | None) -> dict[str, Any]:
    """Valori iniziali della sezione "Dati MCFlash": quelli del record per un
    aggiornamento, altrimenti seniority stimata dall'estrazione e tariffa del ruolo."""
    if edited.get("mcflash"):
        return dict(edited["mcflash"])
    if candidate:
        return {"seniority": candidate.get("seniority"), "disponibilita": candidate.get("disponibilita"),
                "budget": candidate.get("budget"), "site": candidate.get("site")}
    seniority = _SENIORITY_FROM_EXTRACTION.get(str(edited.get("seniority") or "").lower())
    return {"seniority": seniority, "disponibilita": "Immediata",
            "budget": tariff_for(role_budget, seniority), "site": DEFAULT_SITE}


def commit_blockers(edited: dict[str, Any], kind: str) -> list[str]:
    """Cosa impedisce la conferma (stesse regole del backend)."""
    missing = []
    if not edited.get("trittico"):
        missing.append("nome e cognome (per il trittico)")
    if not (edited.get("catalog_role") or edited.get("role")):
        missing.append("ruolo")
    extra = edited.get("mcflash") or {}
    if kind == "crea":
        if not extra.get("seniority"):
            missing.append("seniority")
        if not extra.get("site"):
            missing.append("site")
    return missing


# ---------------------------------------------------------------- operazioni

STEP_LABELS = {"blob": "Storage", "mcflash": "MCFlash", "indice": "Indice", "mappa": "Mappa CV → MCFlash"}
STATE_BADGES = {
    "ok": ":green-badge[:material/check: fatto]",
    "in_attesa": ":blue-badge[:material/hourglass_top: in attesa dell'indicizzazione]",
    "errore": ":red-badge[:material/error: errore]",
    "da_fare": ":gray-badge[da fare]",
}
STATUS_LABELS = {"completata": "Completata", "in_corso": "In corso", "fallita": "Fallita"}
